"""M37-④ 早餐券 + 优惠券 + 房间属性 + 黑名单 端到端测试。

覆盖：
1. 房间属性：全量覆盖（幂等）→ 列表 → 按属性编码过滤房号（AND 语义）。
2. 黑名单：加入 → 命中检查（id_no/phone 强命中、name 弱命中）→ 移出后不再命中；
   命中**不硬阻断**建单/入住（D1）。
3. 早餐券：发券 N 张 → 核销 → 重复核销 409 → 过期 409 → 作废（已核销不可作废 409）。
4. 优惠券：模板创建 → 按模板发券（发行总量护栏）→ 核销（转应收写 BillItem
   DISCOUNT 并冲减 balance）→ 重复核销 409 → 作废（已核销不可作废 409）。

鉴权：conftest 的 ``auth_bypass`` 将请求视为「该租户默认管理员已登录」，
因此需权限点（blacklist.manage / coupon.manage / breakfast.manage）的端点均放行。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
FAR_FUTURE = (date.today() + timedelta(days=365)).isoformat()


def _seed(client: TestClient) -> dict:
    """建租户 + 门店 + 房型 + 两间房（返回含 room id 列表）。"""
    t = client.post("/api/v1/tenants", json={"code": "qa37-4", "name": "④测试"}).json()
    h = client.post(
        f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H4", "name": "店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0401"}],
    )
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0402"}],
    )
    rooms = client.get(f"/api/v1/tenants/{t['code']}/rooms").json()
    return {"tenant": t, "hotel": h, "room_type": rt, "rooms": rooms}


def _room_id_by_no(s: dict, room_no: str) -> int:
    for room in s["rooms"]:
        if room["room_no"] == room_no:
            return int(room["id"])
    raise AssertionError(f"未找到房号 {room_no}")


def _check_in(client: TestClient, s: dict, room_no: str = "0401") -> dict:
    """建预订并入住（供早餐券/优惠券挂 booking_id）。"""
    code = s["tenant"]["code"]
    bk = client.post(
        f"/api/v1/tenants/{code}/bookings",
        json={
            "hotel_id": int(s["hotel"]["id"]),
            "room_type_id": int(s["room_type"]["id"]),
            "guest_name": "④客",
            "guest_phone": "13800000904",
            "check_in_date": TODAY,
            "check_out_date": TOMORROW,
        },
    ).json()
    r = client.post(
        f"/api/v1/tenants/{code}/reception/check-in",
        json={"booking_id": bk["id"], "room_no": room_no, "operator": "front_desk"},
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestRoomAttributes:
    def test_set_list_and_query_by_code(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        rid = _room_id_by_no(s, "0401")

        # 首次覆盖：无烟 + 大床
        r = client.put(
            f"/api/v1/tenants/{code}/rooms/{rid}/attributes",
            json={"codes": ["SMOKE_FREE", "BIG_BED"], "operator": "front_desk"},
        )
        assert r.status_code == 200, r.text
        codes = {a["attribute_code"] for a in r.json()}
        assert codes == {"SMOKE_FREE", "BIG_BED"}
        # attribute_name 取自码表
        names = {a["attribute_code"]: a["attribute_name"] for a in r.json()}
        assert names["SMOKE_FREE"] == "无烟房"
        assert names["BIG_BED"] == "大床"

        # 列表读回
        r = client.get(f"/api/v1/tenants/{code}/rooms/{rid}/attributes")
        assert r.status_code == 200, r.text
        assert {a["attribute_code"] for a in r.json()} == {"SMOKE_FREE", "BIG_BED"}

        # 幂等全量覆盖：去掉 BIG_BED，加 WINDOW
        r = client.put(
            f"/api/v1/tenants/{code}/rooms/{rid}/attributes",
            json={"codes": ["SMOKE_FREE", "WINDOW"], "operator": "front_desk"},
        )
        assert r.status_code == 200, r.text
        assert {a["attribute_code"] for a in r.json()} == {"SMOKE_FREE", "WINDOW"}

        # 按属性过滤房号（AND 语义）
        r = client.get(
            f"/api/v1/tenants/{code}/room-attributes",
            params={"code": ["SMOKE_FREE", "WINDOW"]},
        )
        assert r.status_code == 200, r.text
        assert r.json() == ["0401"]

        # 只按 WINDOW 过滤：0402 无属性，仅 0401 命中
        r = client.get(f"/api/v1/tenants/{code}/room-attributes", params={"code": ["WINDOW"]})
        assert r.json() == ["0401"]

        # 0402 加 BIG_BED 后：SMOKE_FREE+BIG_BED 组合仍只有 0401
        rid2 = _room_id_by_no(s, "0402")
        client.put(
            f"/api/v1/tenants/{code}/rooms/{rid2}/attributes",
            json={"codes": ["BIG_BED"], "operator": "front_desk"},
        )
        r = client.get(
            f"/api/v1/tenants/{code}/room-attributes", params={"code": ["BIG_BED"]}
        )
        assert r.json() == ["0402"]

    def test_set_attributes_unknown_room_returns_404(self, client: TestClient) -> None:
        s = _seed(client)
        r = client.put(
            f"/api/v1/tenants/{s['tenant']['code']}/rooms/999999/attributes",
            json={"codes": ["QUIET"]},
        )
        assert r.status_code == 404, r.text


class TestBlacklist:
    def test_add_check_and_remove(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]

        r = client.post(
            f"/api/v1/tenants/{code}/blacklist",
            json={
                "name": "李四",
                "id_no": "110101199001011234",
                "phone": "13900000404",
                "reason": "恶意损坏设施",
                "level": 2,
                "operator": "manager",
            },
        )
        assert r.status_code == 201, r.text
        row = r.json()
        assert row["is_valid"] is True
        assert row["level"] == 2

        # 证件号命中 → 强命中
        r = client.get(
            f"/api/v1/tenants/{code}/blacklist/check",
            params={"id_no": "110101199001011234"},
        )
        assert r.status_code == 200, r.text
        hits = r.json()["hits"]
        assert len(hits) == 1
        assert hits[0]["matched_by"] == "id_no"
        assert hits[0]["strong"] is True

        # 手机号命中 → 强命中
        hits = client.get(
            f"/api/v1/tenants/{code}/blacklist/check", params={"phone": "13900000404"}
        ).json()["hits"]
        assert hits[0]["matched_by"] == "phone"
        assert hits[0]["strong"] is True

        # 仅姓名命中 → 弱命中（不阻断依据）
        hits = client.get(
            f"/api/v1/tenants/{code}/blacklist/check", params={"name": "李四"}
        ).json()["hits"]
        assert len(hits) == 1
        assert hits[0]["matched_by"] == "name"
        assert hits[0]["strong"] is False

        # 未命中
        assert (
            client.get(
                f"/api/v1/tenants/{code}/blacklist/check", params={"phone": "13800000000"}
            ).json()["hits"]
            == []
        )

        # 列表可查
        lst = client.get(f"/api/v1/tenants/{code}/blacklist").json()
        assert len(lst) == 1

        # 移出（软删）→ 不再命中，但列表按 is_valid=False 仍可查
        rv = client.delete(
            f"/api/v1/tenants/{code}/blacklist/{row['id']}", params={"operator": "manager"}
        )
        assert rv.status_code == 200, rv.text
        assert rv.json()["is_valid"] is False
        assert (
            client.get(
                f"/api/v1/tenants/{code}/blacklist/check", params={"id_no": "110101199001011234"}
            ).json()["hits"]
            == []
        )
        assert client.get(
            f"/api/v1/tenants/{code}/blacklist", params={"is_valid": False}
        ).json()[0]["id"] == row["id"]

    def test_hit_does_not_block_booking(self, client: TestClient) -> None:
        """D1：命中黑名单**仅提醒**，建单/入住正常成功。"""
        s = _seed(client)
        code = s["tenant"]["code"]
        client.post(
            f"/api/v1/tenants/{code}/blacklist",
            json={
                "name": "⑤黑名单客",
                "phone": "13800000909",
                "id_no": "110101199001019999",
                "reason": "逃单",
                "level": 3,
            },
        ).json()
        # 同手机号建单 → 仍应成功（不硬阻断）
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "⑤黑名单客",
                "guest_phone": "13800000909",
                "id_doc_no": "110101199001019999",
                "check_in_date": TODAY,
                "check_out_date": TOMORROW,
            },
        )
        assert bk.status_code in (200, 201), bk.text
        # 入住也正常
        r = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={"booking_id": bk.json()["id"], "room_no": "0401", "operator": "front_desk"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "checked_in"

        # 仅提醒：命中已落审计（guest.blacklist_warning），但业务未被拦截
        logs = client.get(
            f"/api/v1/tenants/{code}/audit-logs",
            params={"action": "guest.blacklist_warning"},
        ).json()
        assert len(logs) >= 1
        assert logs[0]["detail"]["hits"][0]["matched_by"] == "id_no"


class TestBreakfastTickets:
    def test_issue_use_twice_conflict_and_void(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = _check_in(client, s)

        r = client.post(
            f"/api/v1/tenants/{code}/breakfast-tickets/issue",
            json={
                "booking_id": bk["id"],
                "room_no": "0401",
                "ticket_type": 0,
                "ticket_type_name": "送早",
                "count": 2,
                "valid_from": TODAY,
                "valid_to": TOMORROW,
                "operator": "front_desk",
            },
        )
        assert r.status_code == 201, r.text
        tickets = r.json()
        assert len(tickets) == 2
        assert tickets[0]["ticket_no"].startswith("BF")
        assert tickets[0]["is_used"] is False

        # 列表
        lst = client.get(
            f"/api/v1/tenants/{code}/breakfast-tickets", params={"booking_id": bk["id"]}
        ).json()
        assert len(lst) == 2

        # 核销（营业日 = 今天，在有效期内）
        no = tickets[0]["ticket_no"]
        ru = client.post(
            f"/api/v1/tenants/{code}/breakfast-tickets/use",
            json={"ticket_no": no, "business_date": TODAY, "operator": "front_desk"},
        )
        assert ru.status_code == 200, ru.text
        assert ru.json()["is_used"] is True
        assert ru.json()["used_business_date"] == TODAY

        # 重复核销 → 409
        r2 = client.post(
            f"/api/v1/tenants/{code}/breakfast-tickets/use",
            json={"ticket_no": no, "business_date": TODAY},
        )
        assert r2.status_code == 409, r2.text

        # 已核销不可作废 → 409
        rv = client.post(f"/api/v1/tenants/{code}/breakfast-tickets/{tickets[0]['id']}/void")
        assert rv.status_code == 409, rv.text

        # 未核销的可作废
        rv = client.post(f"/api/v1/tenants/{code}/breakfast-tickets/{tickets[1]['id']}/void")
        assert rv.status_code == 200, rv.text
        assert rv.json()["is_valid"] is False

    def test_use_unknown_404_and_expired_409(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _check_in(client, s)

        r = client.post(
            f"/api/v1/tenants/{code}/breakfast-tickets/use",
            json={"ticket_no": "BF-NOT-EXIST", "business_date": TODAY},
        )
        assert r.status_code == 404, r.text

        # 有效期截至昨天 → 过期
        issued = client.post(
            f"/api/v1/tenants/{code}/breakfast-tickets/issue",
            json={"count": 1, "valid_from": YESTERDAY, "valid_to": YESTERDAY},
        ).json()
        r = client.post(
            f"/api/v1/tenants/{code}/breakfast-tickets/use",
            json={"ticket_no": issued[0]["ticket_no"], "business_date": TODAY},
        )
        assert r.status_code == 409, r.text
        assert "过期" in r.text


class TestCoupons:
    def test_template_issue_quantity_guard(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]

        tpl = client.post(
            f"/api/v1/tenants/{code}/coupon-templates",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "code": "TPL-50",
                "name": "50 元代金券",
                "ticket_type": "VOUCHER",
                "discount_type": "AMOUNT",
                "discount_value": 5000,
                "valid_from": TODAY,
                "valid_to": FAR_FUTURE,
                "total_quantity": 2,
            },
        )
        assert tpl.status_code == 201, tpl.text
        tpl = tpl.json()
        assert client.get(f"/api/v1/tenants/{code}/coupon-templates").json()[0]["code"] == "TPL-50"

        # 发 2 张（= 发行总量）→ OK
        r = client.post(
            f"/api/v1/tenants/{code}/coupons",
            json={"template_id": tpl["id"], "count": 2, "hotel_id": int(s["hotel"]["id"])},
        )
        assert r.status_code == 201, r.text
        coupons = r.json()
        assert len(coupons) == 2
        assert coupons[0]["coupon_no"].startswith("CP")
        assert coupons[0]["discount_value"] == 5000  # 继承模板
        assert coupons[0]["status"] == "ISSUED"

        # 再发 1 张 → 超出发行总量（409）
        r = client.post(
            f"/api/v1/tenants/{code}/coupons",
            json={"template_id": tpl["id"], "count": 1, "hotel_id": int(s["hotel"]["id"])},
        )
        assert r.status_code == 409, r.text
        assert "发行总量" in r.text

    def test_use_transfer_to_account_writes_discount_item(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]

        # 开账 → 加收 300.00 元 → balance = 30000
        bill = client.post(
            f"/api/v1/tenants/{code}/bills",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "guest_name": "券客",
                "room_no": "0401",
                "source": "WALK_IN",
            },
        ).json()
        bill = client.post(
            f"/api/v1/tenants/{code}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 30000, "description": "杂费"},
        ).json()
        assert bill["balance"] == 30000

        # 发券（转应收）并核销
        issued = client.post(
            f"/api/v1/tenants/{code}/coupons",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "count": 1,
                "ticket_type": "VOUCHER",
                "discount_type": "AMOUNT",
                "discount_value": 5000,
                "valid_from": TODAY,
                "valid_to": FAR_FUTURE,
                "is_transfer_to_account": True,
            },
        ).json()
        coupon_no = issued[0]["coupon_no"]
        ru = client.post(
            f"/api/v1/tenants/{code}/coupons/use",
            json={"coupon_no": coupon_no, "bill_id": bill["id"], "operator": "front_desk"},
        )
        assert ru.status_code == 200, ru.text
        assert ru.json()["status"] == "USED"

        # 账单：转应收写 DISCOUNT -5000，balance 30000 → 25000
        after = client.get(f"/api/v1/tenants/{code}/bills/{bill['id']}").json()
        assert after["balance"] == 25000
        discounts = [i for i in after["items"] if i["type"] == "DISCOUNT"]
        assert len(discounts) == 1
        assert discounts[0]["amount"] == -5000
        assert coupon_no in discounts[0]["description"]

        # 重复核销 → 409
        r2 = client.post(
            f"/api/v1/tenants/{code}/coupons/use",
            json={"coupon_no": coupon_no, "bill_id": bill["id"]},
        )
        assert r2.status_code == 409, r2.text

        # 已核销不可作废 → 409
        rv = client.post(f"/api/v1/tenants/{code}/coupons/{issued[0]['id']}/void")
        assert rv.status_code == 409, rv.text

        # 未核销的可作废
        issued2 = client.post(
            f"/api/v1/tenants/{code}/coupons",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "count": 1,
                "discount_type": "AMOUNT",
                "discount_value": 1000,
                "valid_from": TODAY,
                "valid_to": FAR_FUTURE,
            },
        ).json()
        rv = client.post(f"/api/v1/tenants/{code}/coupons/{issued2[0]['id']}/void")
        assert rv.status_code == 200, rv.text
        assert rv.json()["status"] == "VOID"

    def test_use_expired_coupon_returns_409(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        issued = client.post(
            f"/api/v1/tenants/{code}/coupons",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "count": 1,
                "discount_type": "AMOUNT",
                "discount_value": 1000,
                "valid_from": YESTERDAY,
                "valid_to": YESTERDAY,
            },
        ).json()
        r = client.post(
            f"/api/v1/tenants/{code}/coupons/use", json={"coupon_no": issued[0]["coupon_no"]}
        )
        assert r.status_code == 409, r.text
        assert "过期" in r.text
        # 过期券落 EXPIRED（状态迁移即使拒绝核销也要持久化）
        lst = client.get(
            f"/api/v1/tenants/{code}/coupons", params={"status": "EXPIRED"}
        ).json()
        assert len(lst) == 1

    @pytest.mark.parametrize("missing", ["name", "reason"])
    def test_blacklist_required_fields(self, client: TestClient, missing: str) -> None:
        """姓名/原因为必填（BlackGuestIn 的 min_length 兜底）。"""
        s = _seed(client)
        payload = {"name": "王五", "reason": "测试"}
        payload.pop(missing)
        r = client.post(f"/api/v1/tenants/{s['tenant']['code']}/blacklist", json=payload)
        assert r.status_code == 422, r.text
