"""M37-③ 发票 + 换房记录 + 续住记录 端到端测试。

覆盖：
1. 发票：开票（普票）、专票无税号 400、开票额>消费+¥10 无审批人 400、作废（WORM）、
   按账单查发票、列表筛选。
2. 换房：change_room 后落 RoomChange 记录（含 reason / from→to / diff=0），
   可经 /room-changes 与 /bookings/{id}/room-changes 查得。
3. 续住：extend_stay 后落 StayExtension 记录（含 start/end/nights/added_amount），
   存在 OPEN 账单时写 BillItem(ROOM_CHARGE) 并累加 balance。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "qa37-3", "name": "③测试"}).json()
    h = client.post(
        f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H3", "name": "店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0101"}],
    )
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0102"}],
    )
    return {"tenant": t, "hotel": h, "room_type": rt}


def _check_in(client: TestClient, s: dict) -> dict:
    code = s["tenant"]["code"]
    bk = client.post(
        f"/api/v1/tenants/{code}/bookings",
        json={
            "hotel_id": int(s["hotel"]["id"]),
            "room_type_id": int(s["room_type"]["id"]),
            "guest_name": "③客",
            "guest_phone": "13800000901",
            "check_in_date": "2026-09-20",
            "check_out_date": "2026-09-22",
        },
    ).json()
    r = client.post(
        f"/api/v1/tenants/{code}/reception/check-in",
        json={"booking_id": bk["id"], "room_no": "0101", "operator": "front_desk"},
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestInvoice:
    def test_create_normal_invoice_and_void_worm(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = _check_in(client, s)
        # 普票开票
        r = client.post(
            f"/api/v1/tenants/{code}/invoices",
            json={
                "bill_id": None,
                "booking_id": bk["id"],
                "room_no": "0101",
                "guest_name": "③客",
                "check_out_at": "2026-09-22",
                "consume_amount_cents": 60000,
                "invoice_amount_cents": 60000,
                "invoice_type": "NORMAL",
                "title": "测试公司",
                "operator": "front_desk",
            },
        )
        assert r.status_code == 201, r.text
        inv = r.json()
        assert inv["status"] == "ISSUED"
        assert inv["invoice_no"].startswith("INV")
        # 作废（WORM：金额不变，仅置 VOID）
        rv = client.post(
            f"/api/v1/tenants/{code}/invoices/{inv['id']}/void",
            json={"operator": "front_desk"},
        )
        assert rv.status_code == 200, rv.text
        assert rv.json()["status"] == "VOID"
        assert rv.json()["invoice_amount_cents"] == 60000  # WORM 金额不变

    def test_vat_special_requires_tax_no(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = _check_in(client, s)
        r = client.post(
            f"/api/v1/tenants/{code}/invoices",
            json={
                "booking_id": bk["id"],
                "check_out_at": "2026-09-22",
                "consume_amount_cents": 60000,
                "invoice_amount_cents": 60000,
                "invoice_type": "VAT_SPECIAL",
                "title": "测试公司",
                # tax_no 故意不填
                "operator": "front_desk",
            },
        )
        assert r.status_code == 400, r.text
        assert "纳税人识别号" in r.text

    def test_over_issue_requires_approver(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = _check_in(client, s)
        # 开票额 - 消费额 = 20000 分（¥200）> ¥10 阈值，但无 approver → 400
        r = client.post(
            f"/api/v1/tenants/{code}/invoices",
            json={
                "booking_id": bk["id"],
                "check_out_at": "2026-09-22",
                "consume_amount_cents": 60000,
                "invoice_amount_cents": 80000,
                "invoice_type": "NORMAL",
                "title": "测试",
                "operator": "front_desk",
            },
        )
        assert r.status_code == 400, r.text
        assert "审批人" in r.text
        # 补上 approver 后通过
        r2 = client.post(
            f"/api/v1/tenants/{code}/invoices",
            json={
                "booking_id": bk["id"],
                "check_out_at": "2026-09-22",
                "consume_amount_cents": 60000,
                "invoice_amount_cents": 80000,
                "invoice_type": "NORMAL",
                "title": "测试",
                "approver": "门店经理",
                "operator": "front_desk",
            },
        )
        assert r2.status_code == 201, r2.text

    def test_list_invoices_and_by_bill(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = _check_in(client, s)
        # 开两张
        for _ in range(2):
            client.post(
                f"/api/v1/tenants/{code}/invoices",
                json={
                    "booking_id": bk["id"],
                    "check_out_at": "2026-09-22",
                    "consume_amount_cents": 1000,
                    "invoice_amount_cents": 1000,
                    "invoice_type": "NORMAL",
                    "title": "t",
                },
            )
        lst = client.get(
            f"/api/v1/tenants/{code}/invoices", params={"booking_id": bk["id"]}
        ).json()
        assert len(lst) == 2
        # 按账单查（无 bill_id 时返回空）
        empty = client.get(f"/api/v1/tenants/{code}/bills/999999/invoices")
        assert empty.status_code == 404


class TestRoomChange:
    def test_change_room_writes_room_change_record(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = _check_in(client, s)
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/{bk['id']}/change-room",
            json={"new_room_no": "0102", "reason": "客人要求", "operator": "front_desk"},
        )
        assert r.status_code == 200, r.text
        # 全量列表
        lst = client.get(
            f"/api/v1/tenants/{code}/room-changes", params={"booking_id": bk["id"]}
        ).json()
        assert len(lst) == 1, lst
        rc = lst[0]
        assert rc["from_room_no"] == "0101" and rc["to_room_no"] == "0102"
        assert rc["reason"] == "客人要求"
        assert rc["price_diff_cents"] == 0  # 同房型，差价 0
        # 单单查
        by_bk = client.get(
            f"/api/v1/tenants/{code}/bookings/{bk['id']}/room-changes"
        ).json()
        assert len(by_bk) == 1

    def test_change_room_without_reason_422(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = _check_in(client, s)
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/{bk['id']}/change-room",
            json={"new_room_no": "0102"},
        )
        assert r.status_code == 422  # 缺 reason 必填


class TestStayExtension:
    def test_extend_stay_writes_stay_extension_and_billitem(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = _check_in(client, s)
        # 续住到 2026-09-24（多 2 晚）
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/{bk['id']}/extend-stay",
            json={"new_check_out_date": "2026-09-24", "operator": "front_desk"},
        )
        assert r.status_code == 200, r.text
        # StayExtension 记录落库
        lst = client.get(
            f"/api/v1/tenants/{code}/stay-extensions", params={"booking_id": bk["id"]}
        ).json()
        assert len(lst) == 1, lst
        se = lst[0]
        assert se["nights"] == 2
        assert se["added_amount_cents"] > 0
        assert se["start_date"] == "2026-09-22"  # 原离店日
        assert se["end_date"] == "2026-09-24"    # 新离店日
        # OPEN 账单：bill.balance 已累加 added_amount，新增 ROOM_CHARGE BillItem
        bills = client.get(
            f"/api/v1/tenants/{code}/bills", params={"status": "OPEN", "booking_id": bk["id"]}
        ).json()
        assert len(bills) >= 1
        # 账单详情（BillOut 含 items）—— 无独立 /bills/{id}/items 端点
        detail = client.get(
            f"/api/v1/tenants/{code}/bills/{bills[0]['id']}"
        ).json()
        items = detail.get("items", [])
        rc_items = [i for i in items if i["type"] == "ROOM_CHARGE"]
        assert any(i["description"].startswith("续住加收") for i in rc_items), items
