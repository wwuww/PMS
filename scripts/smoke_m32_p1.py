"""M32 P1 四项 真实栈 E2E 冒烟。

1. 排房推荐维修/噪音维度（降权 + 原因）
2. 周报/月报快照（手动生成幂等 + 夜审周一自动周报）
3. 挂账前房号查询（在住客人信息 / 无在住警示）
4. 清洁待检查态（done → PENDING_INSPECT + 主管通知 → 检查通过放行 / 退回返工）

用法：
  python scripts/smoke_m32_p1.py            # 复用 127.0.0.1:8000 已起实例
  python scripts/smoke_m32_p1.py --spawn    # 自起 uvicorn，跑完自毁
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

    ok, code, t = http_req("POST", "/api/v1/tenants", body={"code": f"m32-{stamp}", "name": "M32冒烟"})
    tenant = t["code"]
    check("开租户", ok)
    ok, code, auth = http_req("POST", f"/api/v1/tenants/{tenant}/auth/login", body={"username": "admin", "password": "admin123"})
    token = auth["token"] if ok else None
    check("管理员登录", ok)
    ok, code, h = http_req("POST", f"/api/v1/tenants/{tenant}/hotels", token=token, body={"code": "H1", "name": "店"})
    hotel, hid = h["id"], h["id"]
    ok, code, rt = http_req("POST", f"/api/v1/tenants/{tenant}/room-types", token=token, body={"code": "STD", "name": "标间", "base_price": 30000})
    ok, code, _ = http_req("POST", f"/api/v1/hotels/{hotel}/rooms", token=token, body=[
        {"room_type_id": rt["id"], "room_no": "0101", "floor": "1"},
        {"room_type_id": rt["id"], "room_no": "0102", "floor": "1"},
        {"room_type_id": rt["id"], "room_no": "0103", "floor": "1"},
        {"room_type_id": rt["id"], "room_no": "0201", "floor": "2"},
    ])
    check("建 4 间房", ok)

    # ================= 1. 排房推荐：维修/噪音维度 =================
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks", token=token, body={
        "hotel_id": hotel, "room_no": "0101", "task_type": "MAINTENANCE", "priority": "HIGH"})
    check("建维修工单（0101）", ok)
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/complaints", token=token, body={
        "hotel_id": hotel, "guest_name": "噪音客", "room_no": "0102", "category": "NOISE", "description": "空调外机噪音"})
    check("登记噪音投诉（0102）", ok)
    ok, code, rec = http_req("GET", f"/api/v1/tenants/{tenant}/rooms/recommend?hotel_id={hotel}&room_type_id={rt['id']}", token=token)
    by_no = {x["room_no"]: x for x in rec}
    check("推荐排序：无记录房 > 维修房/噪音房", ok and by_no["0103"]["score"] > by_no["0101"]["score"] and by_no["0103"]["score"] > by_no["0102"]["score"], str(rec)[:200])
    check("评分原因输出维修/噪音维度", any("维修" in x for x in by_no["0101"]["reasons"]) and any("噪音" in x for x in by_no["0102"]["reasons"]))

    # ================= 2. 周报/月报快照 =================
    ok, code, snap = http_req("POST", f"/api/v1/tenants/{tenant}/analytics/snapshots/generate", token=token, body={
        "hotel_id": hotel, "period_type": "WEEKLY", "start_date": "2026-08-24", "end_date": "2026-08-30"})
    check("手动生成周报快照", ok and snap.get("source") == "MANUAL", str(snap)[:160])
    ok, code, snap2 = http_req("POST", f"/api/v1/tenants/{tenant}/analytics/snapshots/generate", token=token, body={
        "hotel_id": hotel, "period_type": "WEEKLY", "start_date": "2026-08-24", "end_date": "2026-08-30"})
    ok, code, lst = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/snapshots?hotel_id={hotel}&period_type=WEEKLY", token=token)
    check("同周期幂等（仅 1 条）", ok and len(lst) == 1)
    ok, code, na = http_req("POST", f"/api/v1/tenants/{tenant}/night-audit", token=token, body={
        "hotel_id": hotel, "business_date": "2026-08-31", "operator": "auditor"})  # 周一
    check("周一夜审成功", ok, str(na)[:200])
    ok, code, lst = http_req("GET", f"/api/v1/tenants/{tenant}/analytics/snapshots?hotel_id={hotel}&period_type=WEEKLY", token=token)
    check("周一夜审自动固化上周周报（AUTO，同周期幂等覆盖）", ok and any(x["source"] == "AUTO" for x in lst), str(lst)[:300])

    # ================= 3. 挂账前房号查询 =================
    ok, code, bk = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": "挂账客", "guest_phone": "13933550001",
        "check_in_date": "2026-10-01", "check_out_date": "2026-10-06", "room_no": "0201"})
    http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{bk['id']}/check-in", token=token, body={"room_no": "0201"})
    ok, code, info = http_req("GET", f"/api/v1/tenants/{tenant}/fnb/room-lookup?room_no=0201", token=token)
    check("在住房查询：姓名/离店日期/脱敏手机号", ok and info.get("guest_name") == "挂账客" and info.get("check_out_date") == "2026-10-06" and info.get("guest_phone_masked") == "139****0001", str(info))
    ok, code, info = http_req("GET", f"/api/v1/tenants/{tenant}/fnb/room-lookup?room_no=0103", token=token)
    check("无在住警示", ok and info.get("occupied") is False and "无在住客人" in (info.get("warning") or ""))

    # ================= 4. 清洁待检查态 =================
    ok, code, bkc = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": "退房客",
        "check_in_date": "2026-10-01", "check_out_date": "2026-10-02", "room_no": "0103"})
    http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{bkc['id']}/check-in", token=token, body={"room_no": "0103"})
    ok, code, _ = http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{bkc['id']}/check-out", token=token, body={})
    check("退房造空脏房+自动工单", ok)
    ok, code, tasks = http_req("GET", f"/api/v1/tenants/{tenant}/housekeeping-tasks?room_no=0103", token=token)
    task = tasks[0]
    http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/{task['id']}/assign", token=token, body={"assignee": "保洁王姐"})
    ok, code, done = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/{task['id']}/done", token=token)
    check("保洁完成 → 待检查", ok and done.get("status") == "PENDING_INSPECT", str(done))
    ok, code, notifs = http_req("GET", f"/api/v1/tenants/{tenant}/notifications", token=token)
    check("主管收到待检查通知", any("待检查" in n["title"] and "0103" in n["title"] for n in notifs))
    ok, code, rooms = http_req("GET", f"/api/v1/tenants/{tenant}/rooms?state=vacant_clean", token=token)
    check("待检查期间不放行（仍空脏）", not any(r["room_no"] == "0103" for r in rooms))
    ok, code, ins = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/{task['id']}/inspect", token=token, body={"passed": True, "operator": "主管老李"})
    check("检查通过 → 净房可售", ok and ins.get("status") == "DONE" and ins.get("done_at"), str(ins))
    ok, code, rooms = http_req("GET", f"/api/v1/tenants/{tenant}/rooms?state=vacant_clean", token=token)
    check("房间已回归空净", any(r["room_no"] == "0103" for r in rooms))
    # 返工链路：0201 退房 → done → inspect fail → ASSIGNED
    ok, code, bkr = http_req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hotel, "room_type_id": rt["id"], "guest_name": "返工客",
        "check_in_date": "2026-10-01", "check_out_date": "2026-10-02", "room_no": "0102"})
    http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{bkr['id']}/check-in", token=token, body={"room_no": "0102"})
    http_req("POST", f"/api/v1/tenants/{tenant}/bookings/{bkr['id']}/check-out", token=token, body={})
    ok, code, tasks = http_req("GET", f"/api/v1/tenants/{tenant}/housekeeping-tasks?room_no=0102", token=token)
    t2 = tasks[0]
    http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/{t2['id']}/assign", token=token, body={"assignee": "保洁小李"})
    http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/{t2['id']}/done", token=token)
    ok, code, ins2 = http_req("POST", f"/api/v1/tenants/{tenant}/housekeeping-tasks/{t2['id']}/inspect", token=token, body={"passed": False, "note": "马桶未刷"})
    check("检查不通过 → 退回返工（带原因）", ok and ins2.get("status") == "ASSIGNED" and "马桶未刷" in (ins2.get("note") or ""), str(ins2))

    print()
    print(f"M32 smoke: {PASS} passed, {FAIL} failed")
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
