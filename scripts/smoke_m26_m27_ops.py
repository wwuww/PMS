"""M26 客房深度 + M27 餐饮运营深度 真实栈 E2E 冒烟。

M26：批量派单/完成、多维过滤、员工清扫绩效。
M27：沽清拒点、退菜重算、整单折扣（金额/百分比）、结账净额。

用法：
  python scripts/smoke_m26_m27_ops.py            # 复用 127.0.0.1:8000 已起实例
  python scripts/smoke_m26_m27_ops.py --spawn    # 自起 uvicorn，跑完自毁
"""

from __future__ import annotations

import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
import urllib.parse
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

    today = dt.date.today().isoformat()
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    ok, code, t = http_req("POST", "/api/v1/tenants", body={"code": f"m2627-{stamp}", "name": "M2627冒烟"})
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
        {"room_type_id": rt["id"], "room_no": "0101", "floor": "1"},
        {"room_type_id": rt["id"], "room_no": "0102", "floor": "1"},
        {"room_type_id": rt["id"], "room_no": "0201", "floor": "2"},
    ])
    check("建 3 间房", ok)

    def book_checkin_checkout(phone, room_no):
        ok, code, bk = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
            "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": f"客{phone[-2:]}",
            "guest_phone": phone, "check_in_date": today, "check_out_date": tomorrow, "room_no": room_no})
        if not ok:
            return None
        ok2, code2, _ = http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{bk['id']}/check-in", token=token, body={"room_no": room_no})
        ok3, code3, _ = http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{bk['id']}/check-out", token=token, body={})
        return bk if (ok2 and ok3) else None

    # ================= M26 客房深度 =================
    ok1 = book_checkin_checkout("13900110001", "0101")
    ok2 = book_checkin_checkout("13900110002", "0102")
    check("两间入住再退房（生成清扫单）", ok1 is not None and ok2 is not None)

    ok, code, tasks = http_req("GET", f"/api/v1/tenants/{tenant}/housekeeping-tasks?hotel_id={hotel}&status=PENDING", token=token)
    check("工单列表：2 张待派清扫单", ok and len(tasks) == 2, str(len(tasks if isinstance(tasks, list) else [])))
    ids = [x["id"] for x in tasks] if isinstance(tasks, list) else []

    ok, code, r = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/batch-assign", token=token, body={"task_ids": ids, "assignee": "阿姨王"})
    check("批量派单 → 全部成功", ok and len(r.get("assigned", [])) == len(ids), str(r))

    ok, code, rooms = http_req("GET", f"/api/v1/tenants/{tenant}/rooms", token=token)
    st = {x["room_no"]: x["state"] for x in rooms} if isinstance(rooms, list) else {}
    check("派单后房态=空脏", st.get("0102") == "vacant_dirty", str(st))

    ok, code, r2 = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/batch-done", token=token, body={"task_ids": ids})
    check("批量完成 → 全部成功", ok and len(r2.get("done", [])) == len(ids), str(r2))
    ok, code, rooms = http_req("GET", f"/api/v1/tenants/{tenant}/rooms", token=token)
    st = {x["room_no"]: x["state"] for x in rooms} if isinstance(rooms, list) else {}
    check("完成后房态联动=空净", st.get("0102") == "vacant_clean", str(st))

    ok, code, r3 = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/batch-assign", token=token, body={"task_ids": ids, "assignee": "李阿姨"})
    check("已完成单再派 → 失败明细", ok and len(r3.get("failed", [])) == len(ids), str(r3))

    ok, code, tasks2 = http_req("GET", f"/api/v1/tenants/{tenant}/housekeeping-tasks?hotel_id={hotel}&assignee=" + urllib.parse.quote("阿姨王") + "&task_type=CLEANUP", token=token)
    check("过滤：责任人+类型命中", ok and isinstance(tasks2, list) and len(tasks2) == 2 and all(x["assignee"] == "阿姨王" for x in tasks2), str(len(tasks2 if isinstance(tasks2, list) else [])))
    ok, code, tasks3 = http_req("GET", f"/api/v1/tenants/{tenant}/housekeeping-tasks?hotel_id={hotel}&floor=2", token=token)
    check("过滤：2 层无工单", ok and tasks3 == [], str(tasks3))

    ok, code, perf = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/housekeeping-performance?hotel_id={hotel}", token=token)
    staff = {s["assignee"]: s for s in perf.get("staff", [])} if isinstance(perf, dict) else {}
    check("绩效：阿姨王 完成 ≥2 单", ok and "阿姨王" in staff and staff["阿姨王"]["done_count"] >= 2, str(perf))
    check("绩效：平均耗时字段存在", ok and "avg_minutes" in staff.get("阿姨王", {}))

    # ================= M27 餐饮运营深度 =================
    ok, code, menu = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/menu-items", token=token, body={"hotel_id": hotel, "name": "宫保鸡丁", "category": "热菜", "price_cents": 3200})
    check("建菜品", ok)
    ok, code, menu2 = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/menu-items", token=token, body={"hotel_id": hotel, "name": "凉粉", "category": "凉菜", "price_cents": 1200})
    check("建菜品2", ok)
    ok, code, table = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/tables", token=token, body={"hotel_id": hotel, "table_no": "T01", "seats": 4})
    check("建餐桌", ok)
    ok, code, order = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/orders", token=token, body={"hotel_id": hotel, "table_id": table["id"], "guest_name": "餐客"})
    check("开单", ok)
    order_id = order["id"]

    def add_item(mid, mname, price, qty):
        return http_req("POST", f"/api/v1/tenants/{tenant}/fnb/orders/{order_id}/items", token=token, body={
            "item_id": mid, "name": mname, "unit_price_cents": price, "qty": qty})

    # 沽清 → 拒点 → 恢复
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/menu-items/{menu2['id']}/sold-out", token=token, body={"sold_out": True})
    check("沽清标记成功", ok)
    ok, code, _e = add_item(menu2["id"], "凉粉", 1200, 1)
    check("沽清菜拒点 → 409", code == 409, str(code))
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/menu-items/{menu2['id']}/sold-out", token=token, body={"sold_out": False})
    check("恢复供应", ok)
    ok, code, _ = add_item(menu2["id"], "凉粉", 1200, 1)
    check("恢复后可点", ok and code == 201, str(code))

    # 点菜 + 退菜
    ok, code, line1 = add_item(menu["id"], "宫保鸡丁", 3200, 2)  # 6400
    check("加菜 宫保鸡丁×2", ok)
    ok, code, line2 = add_item(menu2["id"], "凉粉", 1200, 1)  # 1200
    check("加菜 凉粉×1", ok)

    ok, code, od = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/orders/{order_id}/items/{line1['id']}/void", token=token, body={"reason": "客人不吃辣"})
    check("退菜 1 行 → 总额重算 2400", ok and od.get("total_cents") == 2400, str(od.get("total_cents")))  # 恢复验证凉粉×1 仍在单
    ok, code, _e = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/orders/{order_id}/items/{line1['id']}/void", token=token, body={})
    check("重复退菜 → 409", code == 409, str(code))

    # 折扣
    ok, code, _e = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/orders/{order_id}/discount", token=token, body={"discount_cents": 99999})
    check("超额折扣 → 409", code == 409, str(code))
    ok, code, od = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/orders/{order_id}/discount", token=token, body={"percent": 50})
    check("折扣 50% → 1200", ok and od.get("discount_cents") == 1200, str(od.get("discount_cents")))

    # 现金结账按净额
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/fnb/orders/{order_id}/settle-cash", token=token, body={"operator": "smoke"})
    check("现金结账成功", ok)
    ok, code, bills = http_req("GET", f"/api/v1/tenants/{tenant}/bills?source=FNB", token=token)
    target = bills[0] if isinstance(bills, list) and bills else {}
    charge = next((i for i in target.get("items", []) if i.get("type") == "FNB"), {})
    check("FNB 账单以净额 1200 入账", ok and charge.get("amount") == 1200, str(charge))

    # 报表净额（折扣单营收按折后）
    ok, code, rep = http_req("GET", f"/api/v1/tenants/{tenant}/fnb/reports/sales?hotel_id={hotel}", token=token)
    check("销售报表：折后净额 1200", ok and rep.get("total_revenue_cents") == 1200, str(rep.get("total_revenue_cents")))

    print()
    print(f"M26+M27 smoke: {PASS} passed, {FAIL} failed")
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
