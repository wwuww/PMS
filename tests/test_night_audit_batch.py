"""M30 T2 批量化重构语义等价——QA 补充验证（严过关）。

针对 commit f299144 把夜审主循环从「逐房 14 查询 + 1 commit」批量化后，
已有测试未覆盖的批量化特有边界，做独立黑盒验证（仅走 API + 直查 SQLite）。

覆盖场景：
1. 同房型多房间 → 两间房租价一致（price_by_rt 按房型缓存正确）；
2. 无 booking 的在住房 → room_rev 仍按房型价累加，且不 KeyError / 不 500；
3. RateCode 折扣生效 + 房型专属优先于通用（rc_map 取值顺序）；
4. RateCode 通用兜底（无专属码时回落通用码）。

说明：重复入住最优单（同房多笔在住单取「住期覆盖营业日的最新一笔」）已由
tests/test_auto_night_audit.py::test_auto_run_survives_duplicate_checked_in 覆盖，
此处不重复。
"""

from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "qa30", "name": "QA补充"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    return t, h, rt


def _add_rooms(client: TestClient, h: dict, rt: dict, room_nos: list[str]) -> None:
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": n} for n in room_nos],
    )


def _check_in(
    client: TestClient, t: dict, rt: dict, h: dict, room_no: str, phone: str
) -> dict:
    bk = client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": "G",
            "guest_phone": phone,
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-03",
            "room_no": room_no,
        },
    ).json()
    client.post(
        f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
        json={"room_no": room_no},
    )
    return bk


def _night_audit(client: TestClient, t: dict, h: dict, business_date: str):
    return client.post(
        f"/api/v1/tenants/{t['code']}/night-audit",
        json={"hotel_id": h["id"], "business_date": business_date},
    )


def _room_charges(tmp_path, business_date: str) -> list[tuple]:
    con = sqlite3.connect(str(tmp_path / "test.db"))
    rows = con.execute(
        "select b.room_no, i.amount, i.business_date from bill_items i "
        "join bills b on b.id = i.bill_id "
        "where i.type = 'ROOM_CHARGE' and i.business_date = ?",
        (business_date,),
    ).fetchall()
    con.close()
    return rows


class TestM30T2BatchSemantics:
    def test_same_room_type_two_rooms_same_price(self, client: TestClient, tmp_path) -> None:
        """两间同房型房，夜审后房租价一致、room_rev 为两倍房价。"""
        t, h, rt = _seed(client)
        _add_rooms(client, h, rt, ["0101", "0102"])
        _check_in(client, t, rt, h, "0101", "13700000101")
        _check_in(client, t, rt, h, "0102", "13700000102")

        rep = _night_audit(client, t, h, "2026-10-01").json()
        assert rep["room_revenue"] == 60000, rep
        assert rep["occupied_rooms"] == 2

        charges = _room_charges(tmp_path, "2026-10-01")
        assert len(charges) == 2, charges
        amounts = sorted(a for _, a, _ in charges)
        assert amounts == [30000, 30000], charges  # 两间价一致，均按房型基准价

    def test_occupied_without_booking_not_posted(
        self, client: TestClient
    ) -> None:
        """无 booking 的在住房（无单脏房）：夜审不 500、一律不过账、不计当日房费。

        过账口径（f0a1936 起）以「订单覆盖营业日」为准：房间物理在住但无覆盖本营业日
        的 CHECKED_IN 订单时，不生成房租、room_revenue 为 0，并作为 occupied_without_booking
        异常上报前台，而非按房型价累加（避免对无源订单错误计费）。
        """
        t, h, rt = _seed(client)
        _add_rooms(client, h, rt, ["0101"])
        # 直接把房间翻成在住（无对应 CHECKED_IN 预订）
        tr = client.post(
            f"/api/v1/tenants/{t['code']}/rooms/0101/transition",
            json={"trigger": "check_in"},
        )
        assert tr.status_code == 200, tr.text
        assert tr.json()["state"] == "occupied"

        resp = _night_audit(client, t, h, "2026-10-01")
        assert resp.status_code == 201, resp.text  # 201 Created，不 500
        rep = resp.json()
        assert rep["room_revenue"] == 0, rep  # 无单脏房一律不过账
        # 无单脏房异常上报前台（补退房 / 续住 / 超时加收），存于日报 snapshot.before.anomalies
        snap = json.loads(rep["snapshot"]) if rep.get("snapshot") else {}
        anomalies = snap.get("before", {}).get("anomalies", [])
        assert any(
            a.get("room_no") == "0101"
            and a.get("type") == "occupied_without_booking"
            for a in anomalies
        ), snap

    def test_rate_code_specific_beats_generic(self, client: TestClient, tmp_path) -> None:
        """RateCode 折扣生效，且「房型专属优先于通用」的取值顺序正确。

        通用码 5 折、专属码 8 折：夜审过账房租 = 30000 * 8000 // 10000 = 24000。
        """
        t, h, rt = _seed(client)
        _add_rooms(client, h, rt, ["0101"])
        _check_in(client, t, rt, h, "0101", "13700000103")

        # 通用码（room_type_id=None）5 折
        client.post(
            f"/api/v1/tenants/{t['code']}/rate-codes",
            json={
                "code": "GEN",
                "name": "通用价",
                "channel": "direct",
                "member_level": "none",
                "agreement_type": "none",
                "room_type_id": None,
                "discount_pct": 5000,
            },
        )
        # 房型专属码 8 折
        client.post(
            f"/api/v1/tenants/{t['code']}/rate-codes",
            json={
                "code": "SPC",
                "name": "专属价",
                "channel": "direct",
                "member_level": "none",
                "agreement_type": "none",
                "room_type_id": rt["id"],
                "discount_pct": 8000,
            },
        )

        rep = _night_audit(client, t, h, "2026-10-01").json()
        assert rep["room_revenue"] == 24000, rep  # 30000 * 0.8，专属优先

        charges = _room_charges(tmp_path, "2026-10-01")
        assert len(charges) == 1, charges
        assert charges[0][1] == 24000, charges

    def test_rate_code_generic_fallback(self, client: TestClient, tmp_path) -> None:
        """无房型专属码时，回落通用码（rc_map.get(0) 兜底）。"""
        t, h, rt = _seed(client)
        _add_rooms(client, h, rt, ["0101"])
        _check_in(client, t, rt, h, "0101", "13700000104")

        client.post(
            f"/api/v1/tenants/{t['code']}/rate-codes",
            json={
                "code": "GEN",
                "name": "通用价",
                "channel": "direct",
                "member_level": "none",
                "agreement_type": "none",
                "room_type_id": None,
                "discount_pct": 5000,
            },
        )

        rep = _night_audit(client, t, h, "2026-10-01").json()
        assert rep["room_revenue"] == 15000, rep  # 30000 * 0.5，通用兜底

        charges = _room_charges(tmp_path, "2026-10-01")
        assert len(charges) == 1, charges
        assert charges[0][1] == 15000, charges
