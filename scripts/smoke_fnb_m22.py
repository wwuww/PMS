"""M22 餐饮报表 + 厨房出单(KDS) 真实栈端到端冒烟。

直接打真实 uvicorn (http://127.0.0.1:8000)，不走 TestClient，验证报表聚合与 KDS
状态流转在真实 HTTP 栈下生效。
"""
import sys
import time
import httpx

BASE = "http://127.0.0.1:8000/api/v1"
TENANT = f"fnb-m22-{int(time.time()) % 100000:05d}"

results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main():
    with httpx.Client(base_url=BASE, timeout=20) as c:
        # 开通租户 + 登录
        r = c.post("/tenants", json={"code": TENANT, "name": "M22冒烟"})
        check("POST /tenants", r.status_code in (200, 201, 409), f"HTTP {r.status_code}")
        r = c.post(f"/tenants/{TENANT}/auth/login", json={"username": "admin", "password": "admin123"})
        check("登录", r.status_code == 200 and r.json().get("token"), f"HTTP {r.status_code}")
        H = {"Authorization": f"Bearer {r.json()['token']}"}

        # 酒店 + 菜品(带品类) + 餐桌
        r = c.post(f"/tenants/{TENANT}/hotels", headers=H, json={"code": "H1", "name": "一号店"})
        hotel_id = r.json()["id"]
        mi = c.post(f"/tenants/{TENANT}/fnb/menu-items", headers=H,
                    json={"hotel_id": hotel_id, "name": "牛排", "category": "热菜", "price_cents": 8800}).json()
        tbl = c.post(f"/tenants/{TENANT}/fnb/tables", headers=H,
                     json={"hotel_id": hotel_id, "table_no": "A1", "seats": 4}).json()

        # 开台 → 点菜单品(带category) + 手动菜(兜底其他) → 现金结账
        order = c.post(f"/tenants/{TENANT}/fnb/orders", headers=H,
                       json={"hotel_id": hotel_id, "table_id": tbl["id"]}).json()
        c.post(f"/tenants/{TENANT}/fnb/orders/{order['id']}/items", headers=H,
               json={"name": "牛排", "qty": 1, "unit_price_cents": 8800, "item_id": mi["id"]})
        c.post(f"/tenants/{TENANT}/fnb/orders/{order['id']}/items", headers=H,
               json={"name": "米饭", "qty": 2, "unit_price_cents": 300})
        r = c.post(f"/tenants/{TENANT}/fnb/orders/{order['id']}/settle-cash", headers=H, json={})
        check("现金结账", r.status_code == 200 and r.json().get("settle_type") == "cash", f"HTTP {r.status_code}")

        # 报表
        r = c.get(f"/tenants/{TENANT}/fnb/reports/sales", headers=H, params={"hotel_id": hotel_id})
        check("GET /fnb/reports/sales", r.status_code == 200, f"HTTP {r.status_code}")
        rep = r.json()
        check("报表: 总营收4400/单数1/品类正确",
              rep["total_revenue_cents"] == 9400 and rep["order_count"] == 1
              and any(c["category"] == "热菜" and c["revenue_cents"] == 8800 for c in rep["by_category"])
              and any(c["category"] == "其他" and c["revenue_cents"] == 600 for c in rep["by_category"]),
              f"total={rep['total_revenue_cents']} orders={rep['order_count']} cats={rep['by_category']}")
        check("报表: 桌均消费=A1营收9400",
              rep["avg_per_table_cents"] == 9400
              and any(t["table_no"] == "A1" and t["revenue_cents"] == 9400 for t in rep["by_table"]),
              f"avg={rep['avg_per_table_cents']} by_table={rep['by_table']}")

        # KDS：开单 → 加两道 → 出单屏默认取 pending|ready
        ko = c.post(f"/tenants/{TENANT}/fnb/orders", headers=H,
                    json={"hotel_id": hotel_id, "guest_name": "王五"}).json()
        i1 = c.post(f"/tenants/{TENANT}/fnb/orders/{ko['id']}/items", headers=H,
                    json={"name": "牛排", "qty": 1, "unit_price_cents": 8800}).json()
        i2 = c.post(f"/tenants/{TENANT}/fnb/orders/{ko['id']}/items", headers=H,
                    json={"name": "沙拉", "qty": 1, "unit_price_cents": 2200}).json()
        check("加菜后 kds_status=pending", i1["kds_status"] == "pending" and i2["kds_status"] == "pending",
              f"i1={i1['kds_status']} i2={i2['kds_status']}")

        r = c.get(f"/tenants/{TENANT}/fnb/kitchen/tickets", headers=H, params={"hotel_id": hotel_id})
        check("GET /fnb/kitchen/tickets", r.status_code == 200, f"HTTP {r.status_code}")
        ids = [t["item_id"] for t in r.json()]
        check("出单屏含两道待做", i1["id"] in ids and i2["id"] in ids, f"ids={ids}")

        # 牛排出餐 → 上菜
        r = c.post(f"/tenants/{TENANT}/fnb/orders/{ko['id']}/items/{i1['id']}/ready", headers=H)
        check("POST .../items/{id}/ready", r.status_code == 200 and r.json()["kds_status"] == "ready", f"HTTP {r.status_code}")
        r = c.post(f"/tenants/{TENANT}/fnb/orders/{ko['id']}/items/{i1['id']}/served", headers=H)
        check("POST .../items/{id}/served", r.status_code == 200 and r.json()["kds_status"] == "served", f"HTTP {r.status_code}")

        # 默认列表(pending|ready)不再含已上菜
        r = c.get(f"/tenants/{TENANT}/fnb/kitchen/tickets", headers=H, params={"hotel_id": hotel_id})
        ids = [t["item_id"] for t in r.json()]
        check("served 后退出默认出单列表(仍含沙拉)", i1["id"] not in ids and i2["id"] in ids, f"ids={ids}")
        # 取 served 可看到牛排
        r = c.get(f"/tenants/{TENANT}/fnb/kitchen/tickets", headers=H, params={"hotel_id": hotel_id, "states": "served"})
        check("states=served 可查到上菜项", i1["id"] in [t["item_id"] for t in r.json()], f"ids={[t['item_id'] for t in r.json()]}")

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n==== M22 冒烟汇总: {passed}/{total} 通过 ====")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
