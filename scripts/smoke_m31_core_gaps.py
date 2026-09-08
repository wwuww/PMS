"""M31 核心缺口关闭 真实栈 E2E 冒烟。

覆盖验收三大核心缺口：
  #9  会员积分支付（部分抵扣 / 不足 409 / 防回流）
  #10 团队分批结账（逐间结清 + 汇总进度）
  #34 免打扰 DND（开关 + 清扫派单守卫）

用法：
  python scripts/smoke_m31_core_gaps.py            # 复用 127.0.0.1:8000 已起实例
  python scripts/smoke_m31_core_gaps.py --spawn    # 自起 uvicorn，跑完自毁
"""

from __future__ import annotations

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


def http_req(method, path, *, token=None, body=None, raw=None, expect=(200, 201)):
    url = BASE.rstrip("/") + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
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

    ok, code, t = http_req("POST", "/api/v1/tenants", body={"code": f"m31-{stamp}", "name": "M31冒烟"})
    check("开租户", ok)
    tenant = t["code"]
    ok, code, auth = http_req("POST", f"/api/v1/tenants/{tenant}/auth/login", body={"username": "admin", "password": "admin123"})
    token = auth["token"] if ok else None
    check("管理员登录", ok)

    ok, code, h = http_req("POST", f"/api/v1/tenants/{tenant}/hotels", token=token, body={"code": "H1", "name": "店"})
    hotel = h["id"]
    check("建酒店", ok)
    ok, code, rt = http_req("POST", f"/api/v1/tenants/{tenant}/room-types", token=token, body={"code": "STD", "name": "标间", "base_price": 30000})
    check("建房型", ok)
    ok, code, _ = http_req("POST", f"/api/v1/hotels/{hotel}/rooms", token=token, body=[
        {"room_type_id": rt["id"], "room_no": "0101", "floor": "1"},
        {"room_type_id": rt["id"], "room_no": "0102", "floor": "1"},
        {"room_type_id": rt["id"], "room_no": "0103", "floor": "1"},
        {"room_type_id": rt["id"], "room_no": "0104", "floor": "1"},
    ])
    check("建 4 间房", ok)

    # ================= #9 会员积分支付 =================
    ok, code, m = http_req("POST", f"/api/v1/tenants/{tenant}/members", token=token, body={
        "hotel_id": hotel, "name": "积分客", "phone": "13900700001"})
    check("注册会员", ok and m.get("points") == 0)

    ok, code, bk = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": "积分客", "guest_phone": "13900700001",
        "check_in_date": "2026-10-01", "check_out_date": "2026-10-02", "room_no": "0101"})
    check("会员预订", ok)
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{bk['id']}/check-in", token=token, body={"room_no": "0101"})
    check("入住", ok)

    ok, code, b1 = http_req("POST", f"/api/v1/tenants/{tenant}/bills", token=token, body={
        "hotel_id": hotel, "guest_name": "积分客", "booking_id": bk["id"]})
    http_req("POST", f"/api/v1/tenants/{tenant}/bills/{b1['id']}/charges", token=token,
             body={"charge_type": "ROOM_CHARGE", "amount": 30000, "description": "房租"})
    http_req("POST", f"/api/v1/tenants/{tenant}/bills/{b1['id']}/payments", token=token,
             body={"method": "CASH", "amount": 30000})
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/bills/{b1['id']}/settle", token=token)
    ok, code, m = http_req("GET", f"/api/v1/tenants/{tenant}/members/13900700001", token=token)
    check("结账累积积分（30000 分 → 300 积分）", ok and m.get("points") == 300, str(m))

    ok, code, bk2 = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": "积分客", "guest_phone": "13900700001",
        "check_in_date": "2026-10-05", "check_out_date": "2026-10-06"})
    check("会员第二笔预订（累积关联用）", ok)
    ok, code, b2 = http_req("POST", f"/api/v1/tenants/{tenant}/bills", token=token, body={
        "hotel_id": hotel, "guest_name": "积分客", "booking_id": bk2["id"]})
    http_req("POST", f"/api/v1/tenants/{tenant}/bills/{b2['id']}/charges", token=token,
             body={"charge_type": "ROOM_CHARGE", "amount": 30000, "description": "房租"})
    ok, code, pr = http_req("POST", f"/api/v1/tenants/{tenant}/bills/{b2['id']}/pay-points", token=token,
                            body={"member_phone": "13900700001", "points": 300, "operator": "fd"})
    check("积分部分抵扣（300 积分 → 300 分）", ok and pr.get("amount_cents") == 300 and pr.get("member_points_left") == 0 and pr.get("bill_balance") == 29700, str(pr))

    ok, code, e = http_req("POST", f"/api/v1/tenants/{tenant}/bills/{b2['id']}/pay-points", token=token,
                           body={"member_phone": "13900700001", "points": 1}, expect=(409,))
    check("积分不足 → 409", ok)

    # 防回流：结账再累积扣除积分支付部分
    http_req("POST", f"/api/v1/tenants/{tenant}/bills/{b2['id']}/payments", token=token, body={"method": "CASH", "amount": 29700})
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/bills/{b2['id']}/settle", token=token)
    ok, code, m = http_req("GET", f"/api/v1/tenants/{tenant}/members/13900700001", token=token)
    check("防回流：再累积基数扣除积分支付（+297 非 +300）", ok and m.get("points") == 297, str(m))

    # ================= #10 团队分批结账 =================
    ok, code, blk = http_req("POST", f"/api/v1/tenants/{tenant}/group-blocks", token=token, body={
        "hotel_id": hotel, "name": "分批团", "arrival_date": "2026-10-10", "departure_date": "2026-10-12"})
    check("建团队排房", ok)
    block_id = blk["id"]
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/group-blocks/{block_id}/assign", token=token, body={
        "allocations": [
            {"room_no": "0103", "room_type_id": rt["id"], "guest_name": "团员甲", "guest_phone": "13900800001"},
            {"room_no": "0104", "room_type_id": rt["id"], "guest_name": "团员乙"},
        ]})
    check("批量排房 2 间", ok)
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/group-blocks/{block_id}/check-in?operator=fd", token=token, body={})
    check("整团入住", ok)

    allocs = http_req("GET", f"/api/v1/tenants/{tenant}/group-blocks/{block_id}", token=token)[2]["allocations"]
    a1 = next(a for a in allocs if a["room_no"] == "0103")
    ok, code, row = http_req("POST", f"/api/v1/tenants/{tenant}/group-blocks/{block_id}/allocations/{a1['id']}/settle",
                             token=token, body={"operator": "fd"})
    check("分批结账第 1 间（结清+退房）", ok and row.get("settled") is True and row.get("block_settled_count") == 1, str(row))

    ok, code, st = http_req("GET", f"/api/v1/tenants/{tenant}/group-blocks/{block_id}/settlement", token=token)
    check("结算汇总进度 1/2", ok and st.get("settled_allocations") == 1 and st.get("total_allocations") == 2, str(st)[:160])

    a2 = next(a for a in allocs if a["room_no"] == "0104")
    ok, code, row = http_req("POST", f"/api/v1/tenants/{tenant}/group-blocks/{block_id}/allocations/{a2['id']}/settle",
                             token=token, body={"operator": "fd"})
    check("分批结账第 2 间 → 2/2", ok and st and row.get("block_settled_count") == 2, str(row))
    ok, code, rooms = http_req("GET", f"/api/v1/tenants/{tenant}/rooms", token=token)
    states = {r["room_no"]: r["state"] for r in rooms}
    check("两间均已退房释放", states["0103"] != "occupied" and states["0104"] != "occupied", str(states))

    # ================= #34 免打扰 DND =================
    ok, code, r = http_req("POST", f"/api/v1/tenants/{tenant}/rooms/0102/dnd", token=token, body={"dnd": True, "operator": "fd"})
    check("设免打扰", ok and r.get("dnd") == 1)
    ok, code, rooms = http_req("GET", f"/api/v1/tenants/{tenant}/rooms", token=token)
    d = {x["room_no"]: x for x in rooms}["0102"]
    check("房态图 DND 标识（不影响可售状态）", d.get("dnd") == 1 and d.get("state") == "vacant_clean", str(d))

    ok, code, task = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks", token=token, body={
        "hotel_id": hotel, "room_no": "0102", "task_type": "CLEANUP", "priority": "NORMAL"})
    check("创建清扫工单", ok)
    ok, code, e = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/{task['id']}/assign", token=token,
                           body={"assignee": "阿姨A"}, expect=(400, 409))
    check("DND 守卫：清扫派单被拒", ok)
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/rooms/0102/dnd", token=token, body={"dnd": False, "operator": "fd"})
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/{task['id']}/assign", token=token,
                           body={"assignee": "阿姨A"})
    check("取消 DND 后派单成功", ok)

    print()
    print(f"M31 smoke: {PASS} passed, {FAIL} failed")
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
