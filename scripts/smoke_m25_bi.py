"""M25 店总 BI 真实栈 E2E 冒烟（超卖预警 / 在手预测 / 自定义报表）。

用法：
  python scripts/smoke_m25_bi.py            # 复用 127.0.0.1:8000 已起实例
  python scripts/smoke_m25_bi.py --spawn    # 自起 uvicorn，跑完自毁
"""

from __future__ import annotations

import datetime as dt
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
    try:
        payload = json.loads(raw)
    except Exception:
        payload = raw.decode(errors="replace")
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

    ok, code, t = http_req("POST", "/api/v1/tenants", body={"code": f"m25-{stamp}", "name": "M25冒烟"})
    check("开租户", ok)
    tenant, tid = t["code"], t["id"]
    ok, code, auth = http_req("POST", f"/api/v1/tenants/{tenant}/auth/login", body={"username": "admin", "password": "admin123"})
    token = auth["token"] if ok else None
    check("管理员登录", ok)

    ok, code, h = http_req("POST", f"/api/v1/tenants/{tenant}/hotels", token=token, body={"code": "H1", "name": "店"})
    check("建酒店", ok)
    hotel = h["id"]
    ok, code, rt = http_req("POST", f"/api/v1/tenants/{tenant}/room-types", token=token, body={"code": "STD", "name": "标间", "base_price": 30000})
    check("建房型", ok)
    ok, code, _ = http_req("POST", f"/api/v1/hotels/{hotel}/rooms", token=token, body=[
        {"room_type_id": rt["id"], "room_no": "0101"},
        {"room_type_id": rt["id"], "room_no": "0102"},
        {"room_type_id": rt["id"], "room_no": "0103"},
    ])
    check("建 3 间房", ok)

    far1 = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    far2 = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    for i in range(3):
        ok, code, bk = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
            "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": f"客{i}",
            "check_in_date": far1, "check_out_date": far2, "channel": "ota" if i == 0 else "direct"})
        check(f"预订 {i+1}/3（远期 {far1}）", ok, str(code))

    # ---- 超卖预警（3 房 3 单：临界而非超卖；1 房转维修后 → 超卖）----
    ok, code, w = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/oversell-warnings?hotel_id={hotel}&start_date={far1}&end_date={far2}", token=token)
    check("预警接口：满房日 CRITICAL 临界", ok and any(x["level"] == "CRITICAL" for x in w.get("warnings", [])), str(w.get("warnings")))
    ok, code, _r = http_req("POST", f"/api/v1/tenants/{tenant}/rooms/0103/transition", token=token, body={"trigger": "start_maintenance"})
    check("1 间房转入维修", ok)
    ok, code, w = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/oversell-warnings?hotel_id={hotel}&start_date={far1}&end_date={far2}", token=token)
    oversell_days = [x for x in w.get("warnings", []) if x["level"] == "OVERSELL"]
    check("维修后 → OVERSELL 超卖告警", ok and oversell_days and oversell_days[0]["gap"] == -1, str(w.get("warnings")))

    # ---- 远期预测 ----
    ok, code, fc = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/forecast?hotel_id={hotel}&days=7", token=token)
    check("预测接口 7 天结构", ok and len(fc.get("forecast", [])) == 7)
    target = next((x for x in fc.get("forecast", []) if x["date"] == far1), None)
    # 该日 3 在手 / 2 可售（超卖）→ 入住率 1.5（>100% 即超卖信号）
    check("预测：超卖日在手入住率 3/2=1.5", ok and target and abs(target["occupancy_rate"] - 1.5) < 0.01, str(target))
    check("预订增速（近14天 ≥3 笔）", ok and sum(p["bookings"] for p in fc.get("booking_pace", [])) >= 3, str(fc.get("booking_pace")))

    # ---- 自定义报表 ----
    ok, code, rep = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/custom-report?hotel_id={hotel}&group_by=channel", token=token)
    groups = {r["group"]: r for r in rep.get("rows", [])}
    check("报表(渠道)：OTA 1 笔 / 直订 2 笔", ok and groups.get("ota", {}).get("booking_count") == 1 and groups.get("direct", {}).get("booking_count") == 2, str(groups))
    ok, code, rep2 = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/custom-report?hotel_id={hotel}&group_by=room_type", token=token)
    check("报表(房型)：标间 3 笔", ok and rep2.get("rows") and rep2["rows"][0]["booking_count"] == 3, str(rep2.get("rows")))
    ok, code, rep3 = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/custom-report?hotel_id={hotel}&group_by=day&start_date={far1}&end_date={far1}", token=token)
    check("报表(按日)：入住日 3 笔", ok and rep3.get("total_bookings") == 3, str(rep3.get("total_bookings")))
    ok, code, _e = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/custom-report?hotel_id={hotel}&group_by=bogus", token=token, expect=(400,))
    check("非法 group_by → 400", ok)

    print()
    print(f"M25 smoke: {PASS} passed, {FAIL} failed")
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
