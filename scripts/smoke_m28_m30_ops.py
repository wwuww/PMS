"""M28 A2 收尾 + M29 OTA 直连 + M30 缓存/压测 真实栈 E2E 冒烟。

用法：
  python scripts/smoke_m28_m30_ops.py            # 复用 127.0.0.1:8000 已起实例
  python scripts/smoke_m28_m30_ops.py --spawn    # 自起 uvicorn，跑完自毁
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def http_req(method, path, *, token=None, body=None, headers=None, raw=None, expect=(200, 201)):
    url = BASE.rstrip("/") + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, data=data, timeout=15) as resp:
            code = resp.status
            payload = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        code = e.code
        payload = e.read()
        ctype = e.headers.get("Content-Type", "")
    if "json" in ctype:
        try:
            payload = json.loads(payload)
        except Exception:
            payload = payload.decode(errors="replace")
    else:
        payload = payload.decode(errors="replace")
    ok = code in expect
    return ok, code, payload


def main() -> int:
    stamp = str(int(time.time()))
    checks = []

    def check(name, ok, detail=""):
        global PASS, FAIL
        if ok:
            PASS += 1
        else:
            FAIL += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail and not ok else ""))

    ok, code, t = http_req("POST", "/api/v1/tenants", body={"code": f"m2830-{stamp}", "name": "M2830冒烟"})
    check("开租户", ok)
    tenant = t["code"]
    ok, code, auth = http_req("POST", f"/api/v1/tenants/{tenant}/auth/login", body={"username": "admin", "password": "admin123"})
    token = auth["token"] if ok else None
    check("管理员登录", ok)

    ok, code, h = http_req("POST", f"/api/v1/tenants/{tenant}/hotels", token=token, body={"code": "H1", "name": "店"})
    check("建酒店", ok)
    hotel = h["id"]
    ok, code, rt = http_req("POST", f"/api/v1/tenants/{tenant}/room-types", token=token, body={"code": "STD", "name": "标间", "base_price": 30000})
    check("建房型", ok)
    ok, code, _ = http_req("POST", f"/api/v1/hotels/{hotel}/rooms", token=token, body=[
        {"room_type_id": rt["id"], "room_no": "0101", "floor": "1"}])
    check("建 1 间房", ok)

    # ================= M28 投诉 =================
    ok, code, bk = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": "投诉客",
        "guest_phone": "13900500001", "check_in_date": "2026-10-01", "check_out_date": "2026-10-02"})
    check("建预订（投诉关联用）", ok)

    ok, code, c = http_req("POST", f"/api/v1/tenants/{tenant}/complaints", token=token, body={
        "hotel_id": hotel, "guest_name": "占位", "booking_id": bk["id"], "category": "NOISE", "description": "空调噪音"})
    check("投诉登记（关联预订自动回填住客）", ok and c.get("guest_name") == "投诉客" and c.get("guest_phone") == "13900500001", str(c))

    ok, code, c = http_req("POST", f"/api/v1/tenants/{tenant}/complaints/{c['id']}/transition", token=token,
                           body={"to_status": "HANDLING", "handler": "前台小王"})
    check("投诉受理", ok and c.get("status") == "HANDLING")
    ok, code, c = http_req("POST", f"/api/v1/tenants/{tenant}/complaints/{c['id']}/transition", token=token,
                           body={"to_status": "RESOLVED", "resolution": "已换房并补偿", "handler": "前台小王"})
    check("投诉办结（handled_at 落库）", ok and c.get("status") == "RESOLVED" and c.get("handled_at"))

    # ================= M28 留存导出 =================
    ok, code, csv_text = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/data-export?entity=bookings", token=token)
    check("CSV 导出：BOM + 表头 + 数据行", ok and isinstance(csv_text, str) and csv_text.startswith("\ufeff") and "投诉客" in csv_text, str(csv_text)[:120])
    ok, code, _e = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/data-export?entity=bogus", token=token, expect=(400,))
    check("非法 entity → 400", ok)

    # ================= M29 OTA 直连 =================
    secret = "sandbox-secret-9527"
    ok, code, cfg = http_req("PUT", f"/api/v1/tenants/{tenant}/ota/configs", token=token, body={
        "hotel_id": hotel, "channel": "sandbox", "secret": secret})
    check("OTA 渠道配置", ok and cfg.get("channel") == "sandbox", str(cfg))

    webhook_payload = {
        "external_ref": f"SBX-{stamp}",
        "room_type_code": "STD",
        "guest_name": "OTA沙箱客",
        "guest_phone": "13900600001",
        "check_in_date": "2026-10-01",
        "check_out_date": "2026-10-02",
        "total_price_cents": 27600,
    }
    raw = json.dumps(webhook_payload).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    hdrs = {"X-Ota-Sign": sig}
    ok, code, r1 = http_req("POST", f"/api/v1/tenants/{tenant}/ota/sandbox/webhook/orders", raw=raw, headers=hdrs)
    check("OTA webhook 注入（签名通过）", ok and r1.get("created") is True, str(r1))
    ok, code, r2 = http_req("POST", f"/api/v1/tenants/{tenant}/ota/sandbox/webhook/orders", raw=raw, headers=hdrs)
    check("重推同单幂等（created=false 同单号）", ok and r2.get("created") is False and r2.get("booking_id") == r1.get("booking_id"), str(r2))
    bad_raw = json.dumps(webhook_payload).encode()
    ok, code, _e = http_req("POST", f"/api/v1/tenants/{tenant}/ota/sandbox/webhook/orders", raw=bad_raw, headers={"X-Ota-Sign": "deadbeef"}, expect=(400,))
    check("错误签名 → 400", ok)
    ok, code, ack = http_req("POST", f"/api/v1/tenants/{tenant}/ota/sandbox/inventory/push?days=5", token=token)
    check("房量推送沙箱回执（accepted + trace_id）", ok and ack.get("accepted") is True and ack.get("trace_id"), str(ack))
    check("推送明细含房型与总房量", ok and ack.get("items") and ack["items"][0]["room_type_code"] == "STD" and ack.get("total_rooms") == 1, str(ack))

    # ================= M30 dashboard 缓存 =================
    ok, code, d1 = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/dashboard?hotel_id={hotel}", token=token)
    check("dashboard 首查（回填缓存）", ok)
    ok, code, d2 = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/dashboard?hotel_id={hotel}", token=token)
    check("dashboard 二查（缓存命中，结构一致）", ok and d1 == d2)

    print()
    print(f"M28-M30 smoke: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


def spawn_backend():
    env = dict(os.environ)
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    env["NO_PROXY"] = "*"
    proc = subprocess.Popen(
        [".venv/Scripts/python.exe", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
    )
    for _ in range(40):
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("backend failed to start")


if __name__ == "__main__":
    proc = None
    if "--spawn" in sys.argv:
        proc = spawn_backend()
    try:
        sys.exit(main())
    finally:
        if proc:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
