"""M21 餐饮 POS 真实栈端到端冒烟：开台→点菜→现金结账 + 挂房账，校验 Bill 入账联动。

直接打真实 uvicorn (http://127.0.0.1:8000)，不走 TestClient，验证 F&B 在真实 HTTP 栈下生效。
"""
import sys
import time
import httpx

BASE = "http://127.0.0.1:8000/api/v1"
TENANT = f"fnb-smoke-{int(time.time())%100000:05d}"

results = []
def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main():
    with httpx.Client(base_url=BASE, timeout=20) as c:
        # 1) 开通租户（白名单，无需认证）
        r = c.post("/tenants", json={"code": TENANT, "name": "餐饮冒烟"})
        check("POST /tenants 开通租户", r.status_code in (200, 201, 409), f"HTTP {r.status_code} body={r.text[:120]}")
        if r.status_code >= 400 and r.status_code != 409:
            print("致命：无法开通租户，终止"); sys.exit(1)

        # 2) 登录拿 token（默认管理员 admin/admin123，由开通租户时 seed）。
        #    注意：除 /tenants 创建与 /auth/* 外均需认证，故先登录再建酒店/F&B。
        r = c.post(f"/tenants/{TENANT}/auth/login", json={"username": "admin", "password": "admin123"})
        check("POST auth/login 登录", r.status_code == 200 and (r.json().get("token")), f"HTTP {r.status_code} body={r.text[:160]}")
        token = r.json().get("token")
        if not token:
            print("致命：登录失败无 token，终止"); sys.exit(1)
        H = {"Authorization": f"Bearer {token}"}

        # 3) 开通酒店（需认证）
        r = c.post(f"/tenants/{TENANT}/hotels", headers=H, json={"code": "HSMOKE", "name": "冒烟酒店"})
        check("POST /tenants/{t}/hotels 开通酒店", r.status_code in (200, 201), f"HTTP {r.status_code} body={r.text[:160]}")
        if r.status_code >= 400:
            print("致命：无法开通酒店，终止"); sys.exit(1)
        hotel_id = r.json()["id"]
        print(f"  -> hotel_id={hotel_id}")

        # 4) 菜品
        r = c.post(f"/tenants/{TENANT}/fnb/menu-items", headers=H,
                   json={"hotel_id": hotel_id, "name": "拿铁", "category": "饮品", "price_cents": 3200, "is_active": 1})
        check("POST fnb/menu-items 新增菜品", r.status_code in (200, 201), f"HTTP {r.status_code} body={r.text[:160]}")
        item_id = r.json().get("id") if r.status_code < 400 else None

        r = c.get(f"/tenants/{TENANT}/fnb/menu-items", headers=H, params={"hotel_id": hotel_id, "active_only": "true"})
        check("GET fnb/menu-items 列表", r.status_code == 200 and len(r.json()) >= 1, f"HTTP {r.status_code} n={len(r.json()) if r.status_code==200 else '?'}")
        # 下架过滤
        r2 = c.get(f"/tenants/{TENANT}/fnb/menu-items", headers=H, params={"hotel_id": hotel_id, "active_only": "false"})
        check("GET fnb/menu-items active_only=false", r.status_code == 200, f"HTTP {r.status_code}")

        # 5) 餐桌
        r = c.post(f"/tenants/{TENANT}/fnb/tables", headers=H,
                   json={"hotel_id": hotel_id, "table_no": "A1", "seats": 4, "zone": "大厅"})
        check("POST fnb/tables 新增餐桌", r.status_code in (200, 201), f"HTTP {r.status_code} body={r.text[:160]}")
        table_id = r.json().get("id") if r.status_code < 400 else None
        r = c.patch(f"/tenants/{TENANT}/fnb/tables/{table_id}/state", headers=H, params={"state": "occupied"})
        check("PATCH fnb/tables/{id}/state occupied", r.status_code == 200 and r.json().get("state") == "occupied", f"HTTP {r.status_code} state={r.json().get('state') if r.status_code==200 else '?'}")

        # ===== 链路 A：开台→点菜→现金结账 =====
        r = c.post(f"/tenants/{TENANT}/fnb/orders", headers=H,
                   json={"hotel_id": hotel_id, "table_id": table_id, "guest_name": "张三"})
        check("POST fnb/orders 开台(关联餐桌)", r.status_code in (200, 201), f"HTTP {r.status_code} body={r.text[:160]}")
        order_a = r.json()
        order_a_id = order_a["id"]

        r = c.post(f"/tenants/{TENANT}/fnb/orders/{order_a_id}/items", headers=H,
                   json={"name": "拿铁", "qty": 2, "unit_price_cents": 3200, "item_id": item_id})
        check("POST fnb/orders/{id}/items 加菜(目录单价)", r.status_code in (200, 201) and r.json().get("subtotal_cents") == 6400, f"HTTP {r.status_code} sub={r.json().get('subtotal_cents')}")
        r = c.post(f"/tenants/{TENANT}/fnb/orders/{order_a_id}/items", headers=H,
                   json={"name": "手冲单品", "qty": 1, "unit_price_cents": 4800})
        check("POST fnb/orders/{id}/items 加菜(手动价)", r.status_code in (200, 201) and r.json().get("subtotal_cents") == 4800, f"HTTP {r.status_code} sub={r.json().get('subtotal_cents')}")

        r = c.post(f"/tenants/{TENANT}/fnb/orders/{order_a_id}/settle-cash", headers=H, json={})
        check("POST fnb/orders/{id}/settle-cash 现金结账", r.status_code == 200, f"HTTP {r.status_code} body={r.text[:160]}")
        oa = r.json()
        check("现金结账: status=settled & settle_type=cash & total=11200",
              oa.get("status") == "settled" and oa.get("settle_type") == "cash" and oa.get("total_cents") == 11200,
              f"status={oa.get('status')} type={oa.get('settle_type')} total={oa.get('total_cents')}")

        # 餐桌应被释放为 cleaning
        r = c.get(f"/tenants/{TENANT}/fnb/tables", headers=H, params={"hotel_id": hotel_id})
        tbl = next((t for t in r.json() if t["id"] == table_id), None)
        check("现金结账后餐桌释放为 cleaning", tbl is not None and tbl.get("state") == "cleaning", f"state={tbl.get('state') if tbl else '?'}")
        # 已结账加菜应 409
        r = c.post(f"/tenants/{TENANT}/fnb/orders/{order_a_id}/items", headers=H, json={"name": "x", "qty": 1, "unit_price_cents": 100})
        check("已结账账单加菜 409", r.status_code == 409, f"HTTP {r.status_code}")

        # ===== 链路 B：散客→点菜→挂房账 =====
        r = c.post(f"/tenants/{TENANT}/fnb/orders", headers=H,
                   json={"hotel_id": hotel_id, "room_no": "808", "guest_name": "李四"})
        check("POST fnb/orders 开单(挂房账,无餐桌)", r.status_code in (200, 201), f"HTTP {r.status_code} body={r.text[:160]}")
        order_b_id = r.json()["id"]
        r = c.post(f"/tenants/{TENANT}/fnb/orders/{order_b_id}/items", headers=H,
                   json={"name": "红酒", "qty": 1, "unit_price_cents": 19800})
        check("POST fnb/orders/{id}/items 加菜(挂房账)", r.status_code in (200, 201), f"HTTP {r.status_code} sub={r.json().get('subtotal_cents')}")
        r = c.post(f"/tenants/{TENANT}/fnb/orders/{order_b_id}/settle-room", headers=H, json={"room_no": "808"})
        check("POST fnb/orders/{id}/settle-room 挂房账", r.status_code == 200, f"HTTP {r.status_code} body={r.text[:160]}")
        ob = r.json()
        check("挂房账: status=settled & settle_type=room & room_no=808",
              ob.get("status") == "settled" and ob.get("settle_type") == "room" and ob.get("room_no") == "808",
              f"status={ob.get('status')} type={ob.get('settle_type')} room={ob.get('room_no')}")

        # ===== Bill 入账联动校验 =====
        r = c.get(f"/tenants/{TENANT}/bills", headers=H, params={"source": "FNB"})
        check("GET /bills?source=FNB 出现餐饮账单", r.status_code == 200, f"HTTP {r.status_code}")
        bills = r.json()
        fnb_bills = [b for b in bills if b.get("source") == "FNB"]
        cash_bills = [b for b in fnb_bills if b.get("status") == "SETTLED"]
        room_bills = [b for b in fnb_bills if b.get("status") == "OPEN"]
        check("FNB 账单: 现金单已 SETTLED(余额0) / 挂房账单仍 OPEN",
              len(cash_bills) >= 1 and len(room_bills) >= 1,
              f"FNB总数={len(fnb_bills)} SETTLED={len(cash_bills)} OPEN={len(room_bills)}")
        if cash_bills:
            cb = cash_bills[0]
            paid_ok = any(p.get("method") == "CASH" for p in cb.get("payments", []))
            check("现金 FNB 账单: balance=0 & 已挂 CASH 收款",
                  cb.get("balance") == 0 and cb.get("status") == "SETTLED" and paid_ok,
                  f"balance={cb.get('balance')} status={cb.get('status')} payments={len(cb.get('payments', []))}")

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n==== 冒烟汇总: {passed}/{total} 通过 ====")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
