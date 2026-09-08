"""M24 前台深度 II 真实栈 E2E 冒烟（协议挂账 / 时租房 / 智能排房）。

用法：
  python scripts/smoke_m24_frontdesk.py            # 复用 127.0.0.1:8000 已起实例
  python scripts/smoke_m24_frontdesk.py --spawn    # 自起 uvicorn，跑完自毁

零三方依赖（urllib）。零漂移与单测由 pytest/alembic 负责，此处只验真实 HTTP 链路。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def http_req(method, path, *, token=None, body=None, expect=(200, 201)):
    url = BASE.rstrip("/") + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=15) as resp:
            code = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as e:
        code = e.code
        raw = e.read()
    payload = None
    try:
        payload = json.loads(raw)
    except Exception:
        payload = raw.decode(errors="replace")
    ok = code in expect
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
    return ok, code, payload


def main() -> int:
    stamp = str(int(time.time()))
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail and not ok else ""))

    # 租户（开租户免认证）
    ok, code, t = http_req("POST", "/api/v1/tenants", body={"code": f"m24-{stamp}", "name": "M24冒烟"})
    check("开租户", ok, f"{code} {t}")
    tid = t["id"]
    tenant = t["code"]

    # 登录（默认管理员 seed 于开租户）
    ok, code, auth = http_req("POST", f"/api/v1/tenants/{tenant}/auth/login", body={"username": "admin", "password": "admin123"})
    check("管理员登录", ok, f"{code} {auth}")
    token = auth["token"] if ok and isinstance(auth, dict) else None

    ok, code, h = http_req("POST", f"/api/v1/tenants/{tenant}/hotels", token=token, body={"code": "H1", "name": "冒烟店"})
    check("建酒店", ok)
    hotel = h["id"]
    ok, code, rt = http_req("POST", f"/api/v1/tenants/{tenant}/room-types", token=token, body={"code": "STD", "name": "标间", "base_price": 30000, "hourly_rate": 5000})
    check("建房型(含时租价)", ok and rt.get("hourly_rate") == 5000)
    ok, code, _ = http_req("POST", f"/api/v1/hotels/{hotel}/rooms", token=token, body=[{"room_type_id": rt["id"], "room_no": "0101", "floor": "1"}, {"room_type_id": rt["id"], "room_no": "0102", "floor": "1"}, {"room_type_id": rt["id"], "room_no": "0201", "floor": "2"}])
    check("建房间", ok)

    # ---- 时租房计价 ----
    ok, code, bk = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": "时租客", "guest_phone": "13900007777",
        "check_in_date": "2026-10-01", "check_out_date": "2026-10-01", "stay_type": "hourly", "hourly_hours": 4})
    check("时租预订创建(同日)", ok)
    check("时租计价 = 5000分/时 × 4 = 20000", ok and bk.get("total_price") == 20000, str(bk.get("total_price")))

    # ---- 智能排房：历史偏好 ----
    ok, code, hist = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": "回头客", "guest_phone": "13900008888",
        "check_in_date": "2026-09-01", "check_out_date": "2026-09-02", "room_no": "0201"})
    ok1, c1, _r = http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{hist['id']}/check-in", token=token, body={"room_no": "0201"})
    ok2, c2, _r = http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{hist['id']}/check-out", token=token, body={})
    check("历史住客 入住/退房(0201→空脏)", ok1 and ok2, f"{c1}/{c2}")
    ok, code, rec = http_req("GET", f"/api/v1/tenants/{tenant}/rooms/recommend?hotel_id={hotel}&guest_phone=13900008888", token=token)
    top = rec[0] if ok and rec else {}
    check("排房推荐：曾住房 0201 排第一(历史加分胜空净)", ok and top.get("room_no") == "0201", str(top))
    check("排房推荐：排除在住/锁房", ok and all(x["room_no"] != "0201" or x["state"] == "vacant_dirty" for x in rec))

    # ---- 协议挂账 / 月结 ----
    ok, code, acct = http_req("POST", f"/api/v1/tenants/{tenant}/ar-accounts", token=token, body={"hotel_id": hotel, "name": "华创旅行社", "credit_limit_cents": 100000})
    check("创建协议单位", ok)
    ok, code, bill = http_req("POST", f"/api/v1/tenants/{tenant}/bills", token=token, body={"hotel_id": hotel, "guest_name": "协议宴请"})
    ok, code, _r = http_req("POST", f"/api/v1/tenants/{tenant}/bills/{bill['id']}/charges", token=token, body={"charge_type": "ROOM_CHARGE", "amount": 88000, "operator": "gm"})
    check("账单加应收 88000", ok)
    ok, code, settled = http_req("POST", f"/api/v1/tenants/{tenant}/ar-accounts/{acct['id']}/charge", token=token, body={"bill_id": bill["id"], "operator": "gm"})
    check("账单挂账(整笔转协议单位)", ok and settled.get("status") == "SETTLED" and settled.get("balance") == 0)
    check("挂账回填 ar_account_id", ok and str(settled.get("ar_account_id")) == str(acct["id"]))
    check("挂账产生 COMPANY 收款", ok and any(p["method"] == "COMPANY" for p in settled.get("payments", [])))
    ok, code, ar_bills = http_req("GET", f"/api/v1/tenants/{tenant}/ar-accounts/{acct['id']}/bills", token=token)
    check("协议账单列表可查", ok and len(ar_bills) == 1)
    ok, code, after = http_req("POST", f"/api/v1/tenants/{tenant}/ar-accounts/{acct['id']}/repayments", token=token, body={"amount": 50000, "method": "BANK", "operator": "fin"})
    check("还款 50000 → 欠款余 38000", ok and after.get("balance_cents") == 38000, str(after.get("balance_cents")))

    # 信用额度拦截
    ok, code, acct2 = http_req("POST", f"/api/v1/tenants/{tenant}/ar-accounts", token=token, body={"hotel_id": hotel, "name": "限额单位", "credit_limit_cents": 10000})
    ok, code, bill2 = http_req("POST", f"/api/v1/tenants/{tenant}/bills", token=token, body={"hotel_id": hotel, "guest_name": "超限客"})
    http_req("POST", f"/api/v1/tenants/{tenant}/bills/{bill2['id']}/charges", token=token, body={"charge_type": "MISC", "amount": 20000, "operator": "gm"})
    ok, code, _e = http_req("POST", f"/api/v1/tenants/{tenant}/ar-accounts/{acct2['id']}/charge", token=token, body={"bill_id": bill2["id"]}, expect=(409,))
    check("超信用额度挂账被拒(409)", ok)

    print()
    print(f"M24 smoke: {PASS} passed, {FAIL} failed")
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
