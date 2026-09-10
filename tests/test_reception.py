"""统一接待办理测试（M14-3，FR-RECEPTION）。"""

import pytest
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-recept", "name": "接待测试"}
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "R1", "name": "店"}
    ).json()
    room_type = client.post(
        f"/api/v1/tenants/{tenant['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{hotel['id']}/rooms",
        json=[{"room_type_id": room_type["id"], "room_no": "0101"}],
    )
    return {"tenant": tenant, "hotel": hotel, "room_type": room_type}


class TestReception:
    def test_reservation_check_in(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        # 建预订（不预分配房）
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "预订客",
                "guest_phone": "13800000201",
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
            },
        )
        assert bk.status_code == 201
        booking_id = bk.json()["id"]
        # 统一接待：预订模式入住
        resp = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={"booking_id": booking_id, "room_no": "0101", "operator": "front_desk"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "checked_in"
        assert body["room_no"] == "0101"
        # 客史累计
        found = client.get(
            f"/api/v1/tenants/{code}/guests/search", params={"phone": "13800000201"}
        ).json()
        assert len(found) == 1 and found[0]["stay_count"] >= 1

    def test_walk_in_check_in_links_member(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        phone = "13800000202"
        # 先注册会员
        client.post(
            f"/api/v1/tenants/{code}/members",
            json={"hotel_id": hid, "name": "散客会员", "phone": phone},
        )
        # 统一接待：散客模式（无 booking_id）
        resp = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={
                "room_no": "0101",
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "散客会员",
                "guest_phone": phone,
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
                "operator": "front_desk",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "checked_in"
        assert body["channel"] == "walk_in"
        # 客档自动建档并关联会员
        g = client.get(
            f"/api/v1/tenants/{code}/guests/search", params={"phone": phone}
        ).json()
        assert len(g) == 1
        assert g[0]["member_id"] is not None
        assert g[0]["member_level"] is not None

    def test_booking_not_found_404(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        resp = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={"booking_id": 999999, "room_no": "0101"},
        )
        assert resp.status_code == 404

    def test_reception_persists_batch2_fields(self, client: TestClient) -> None:
        """批次②：登记页 6 个 checkbox + 客源/会员号/担保 经 reception 接线后落库。

        覆盖散客（walk-in 新建预订）与预订（既有 booking 回写）两种模式，
        并验证返回与重查均携带新字段（避免「前端发了但后端丢弃」）。
        """
        s = _seed(client)
        code = s["tenant"]["code"]
        batch2 = {
            "guest_source_type": "IM",
            "member_no": "M370001",
            "is_vip": True,
            "is_secret": True,
            "is_quick_depart": True,
            "is_print_real_price": False,
            "is_add_point": False,
            "is_guarantee": True,
            "guarantee_hold_until": "2026-09-22T18:00:00",
        }

        # 散客模式：新字段随建预订落库
        resp = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={
                "room_no": "0101",
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "批次二散客",
                "guest_phone": "13800000301",
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
                "operator": "front_desk",
                **batch2,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for k, v in batch2.items():
            assert body.get(k) == v, f"{k}: {body.get(k)} != {v}"
        bid = body["id"]
        # 重查确认 DB 持久化（非仅响应回显）—— list_bookings 返回 ORM 全列
        relist = client.get(
            f"/api/v1/tenants/{code}/bookings", params={"member_no": "M370001"}
        ).json()
        assert any(b["id"] == bid and b["is_vip"] is True for b in relist), relist
        assert any(b["member_no"] == "M370001" for b in relist)

        # 预订模式：在既有 booking 上回写新字段（用第二间房，避免与散客同房冲突）
        client.post(
            f"/api/v1/hotels/{s['hotel']['id']}/rooms",
            json=[{"room_type_id": s["room_type"]["id"], "room_no": "0102"}],
        )
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "批次二预订客",
                "guest_phone": "13800000302",
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
            },
        ).json()
        resp2 = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={
                "booking_id": bk["id"],
                "room_no": "0102",
                "operator": "front_desk",
                **batch2,
            },
        )
        assert resp2.status_code == 200, resp2.text
        relist2 = client.get(
            f"/api/v1/tenants/{code}/bookings", params={"member_no": "M370001"}
        ).json()
        assert any(
            b["id"] == bk["id"] and b["is_secret"] is True and b["guest_source_type"] == "IM"
            for b in relist2
        ), relist2

    def test_double_check_in_conflict_409(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "重复客",
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
            },
        ).json()
        first = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={"booking_id": bk["id"], "room_no": "0101"},
        )
        assert first.status_code == 200
        # 再次办理同一预订 → 非 CREATED，409
        again = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={"booking_id": bk["id"], "room_no": "0101"},
        )
        assert again.status_code == 409

    def test_walk_in_missing_fields_409(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        # 散客缺房型/姓名/日期 → 409
        resp = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={"room_no": "0101"},
        )
        assert resp.status_code == 409


class TestReceptionFlow:
    """M1 基座：单客上下文聚合（R1）+ 编排状态机（R2）。

    走半自动单步「继续」链路：register → check_in → open_folio → check_out。
    """

    def test_context_fresh_guest_is_query(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        resp = client.get(
            f"/api/v1/tenants/{code}/reception/context",
            params={"guest_phone": "13800000999"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["flow_state"] == "query"
        assert set(body["can_advance"]) >= {"register", "check_in"}
        assert body["guest"] is None
        assert body["booking"] is None
        assert body["folio"] is None

    def test_context_after_checkin_aggregates_all(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        phone = "13800000301"
        # 散客入住
        ci = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={
                "room_no": "0101",
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "聚合客",
                "guest_phone": phone,
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
                "operator": "front_desk",
            },
        )
        assert ci.status_code == 200
        booking_id = ci.json()["id"]
        # 上下文聚合
        ctx = client.get(
            f"/api/v1/tenants/{code}/reception/context",
            params={"booking_id": booking_id},
        ).json()
        assert ctx["flow_state"] == "inhouse"
        assert ctx["booking"]["status"] == "checked_in"
        assert ctx["room_no"] == "0101"
        assert ctx["room_state"] == "occupied"
        assert ctx["guest"]["phone"] == phone
        assert ctx["folio"] is not None  # 入住自动开账
        assert ctx["folio"]["status"] == "OPEN"
        assert len(ctx["audit_log"]) >= 1  # booking.checked_in 审计

    def test_advance_walkin_flow_register_then_checkin(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        phone = "13800000302"
        # 1) register：建档
        r1 = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={
                "action": "register",
                "hotel_id": hid,
                "guest_name": "步进客",
                "guest_phone": phone,
            },
        )
        assert r1.status_code == 200
        assert r1.json()["guest"]["phone"] == phone
        # 2) check_in（散客）：register → inhouse
        r2 = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={
                "action": "check_in",
                "room_no": "0101",
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "步进客",
                "guest_phone": phone,
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
                "operator": "front_desk",
            },
        )
        assert r2.status_code == 200
        assert r2.json()["flow_state"] == "inhouse"
        assert r2.json()["booking"]["status"] == "checked_in"

    def test_advance_open_folio_and_checkout(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        phone = "13800000303"
        ci = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={
                "room_no": "0101",
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "结账客",
                "guest_phone": phone,
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
                "operator": "front_desk",
            },
        )
        booking_id = ci.json()["id"]
        # inhouse 状态允许 open_folio / check_out
        fo = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={"action": "open_folio", "booking_id": booking_id},
        )
        assert fo.status_code == 200
        assert fo.json()["folio"] is not None
        # checkout
        co = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={"action": "check_out", "booking_id": booking_id},
        )
        assert co.status_code == 200
        assert co.json()["flow_state"] == "checkout"
        assert co.json()["booking"]["status"] == "checked_out"

    def test_advance_illegal_transition_409(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        # 全新客人处于 query，不允许 open_folio
        resp = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={"action": "open_folio", "guest_phone": "13800000988"},
        )
        assert resp.status_code == 409
        assert "非法办理流流转" in resp.json()["detail"]

    def test_context_insights_r7(self, client: TestClient) -> None:
        """R7 客史洞察：入住后回填 VIP/标签/备注，context.insights 应派生提示。"""
        s = _seed(client)
        code = s["tenant"]["code"]
        phone = "13800000304"
        ci = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={
                "room_no": "0101",
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "洞察客",
                "guest_phone": phone,
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
                "operator": "front_desk",
            },
        )
        assert ci.status_code == 200
        booking_id = ci.json()["id"]
        # 回填客档：VIP + 标签 + 备注（均经既有 API 可写）
        found = client.get(
            f"/api/v1/tenants/{code}/guests/search", params={"phone": phone}
        ).json()
        gid = found[0]["id"]
        patch = client.patch(
            f"/api/v1/tenants/{code}/guests/{gid}",
            json={"vip_level": "GOLD", "tags": ["吸烟房", "高楼层"], "notes": "偏好安静"},
        )
        assert patch.status_code == 200
        # 重新聚合上下文
        ctx = client.get(
            f"/api/v1/tenants/{code}/reception/context",
            params={"booking_id": booking_id},
        ).json()
        insights = ctx["insights"]
        assert any("VIP 等级：GOLD" in x for x in insights)
        assert any("标签：吸烟房" in x for x in insights)
        assert any("标签：高楼层" in x for x in insights)
        assert any("客史备注：偏好安静" in x for x in insights)

    def test_advance_enroll_member_links_guest(self, client: TestClient) -> None:
        """① 客档联动会员·深度联动：建档后现场办会员，关联客档并可幂等重办。"""
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        phone = "13800000305"
        # 1) register 建档
        r1 = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={"action": "register", "hotel_id": hid, "guest_name": "会员客", "guest_phone": phone},
        )
        assert r1.status_code == 200
        # 2) enroll_member 办会员
        r2 = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={"action": "enroll_member", "hotel_id": hid, "guest_phone": phone},
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["membership"] is not None
        assert body2["membership"]["level"] == "NORMAL"
        assert body2["guest"]["member_id"] == body2["membership"]["member_id"]
        assert any("会员等级：NORMAL" in x for x in body2["insights"])
        # 3) 幂等重办：同手机号命中既有会员，不报错且 member_id 不变
        r3 = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={"action": "enroll_member", "hotel_id": hid, "guest_phone": phone},
        )
        assert r3.status_code == 200
        assert r3.json()["membership"]["member_id"] == body2["membership"]["member_id"]

    def test_advance_enroll_member_requires_guest(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        # 无客档直接办会员 → 409
        resp = client.post(
            f"/api/v1/tenants/{code}/reception/advance",
            json={"action": "enroll_member", "hotel_id": hid, "guest_phone": "13800000977"},
        )
        assert resp.status_code == 409
        assert "先建档" in resp.json()["detail"]

    def test_context_not_degraded_on_happy_path(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        # query 阶段无聚合异常 → 降级关闭
        resp = client.get(
            f"/api/v1/tenants/{code}/reception/context",
            params={"guest_phone": "13800000988"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["degraded"] is False
        assert body["degradation_notes"] == []

    def test_context_degrades_when_audit_aggregation_fails(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """审计聚合异常时降级而非整页 500（Q4 容错）。"""
        from app.services import reception_service as rs_mod

        async def _boom(self, *a, **k):  # noqa: ANN001
            raise RuntimeError("audit store unreachable")

        monkeypatch.setattr(rs_mod.ReceptionService, "_load_audit_log", _boom)

        s = _seed(client)
        code = s["tenant"]["code"]
        # 建预订（产生 booking，使 audit 聚合分支被执行）
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "降级客",
                "guest_phone": "13800000966",
                "check_in_date": "2026-09-20",
                "check_out_date": "2026-09-22",
            },
        )
        assert bk.status_code == 201
        booking_id = bk.json()["id"]
        # 按 booking_id 查上下文：audit 故障应被隔离
        resp = client.get(
            f"/api/v1/tenants/{code}/reception/context",
            params={"booking_id": booking_id},
        )
        assert resp.status_code == 200  # 非 500
        body = resp.json()
        assert body["degraded"] is True
        assert any("审计" in n for n in body["degradation_notes"])
        # 其余核心字段仍然返回
        assert body["booking"] is not None
        assert body["flow_state"] == "register"
