"""夜审引擎（M4）集成测试：房租过账 / 营业日报 / 在住房房态不变式 / 快照对比。

回归说明：夜审**不得**再做「预离翻房」（occupied→vacant_dirty）。在住房必须保持
occupied 直到真实退房，否则 rooms.state 与 bookings.status 不一致，且真实退房会因
源状态非 OCCUPIED 抛 InvalidTransition 而被卡死。
"""

import json

from fastapi.testclient import TestClient

from app.services.night_audit_scheduler import _categorize_suspended


def _seed(client: TestClient) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "na", "name": "夜审测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0101"}],
    )
    return t, h, rt


def _check_in(
    client: TestClient, t: dict, rt: dict, h: dict, room_no: str, phone: str, cin: str, cout: str
) -> dict:
    bk = client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": "G",
            "guest_phone": phone,
            "check_in_date": cin,
            "check_out_date": cout,
            "room_no": room_no,
        },
    ).json()
    client.post(
        f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
        json={"room_no": room_no},
    )
    return bk


class TestNightAudit:
    def test_room_charge_and_report(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "0101", "13700000001", "2026-10-01", "2026-10-03")

        rep = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        ).json()
        assert rep["occupied_rooms"] == 1
        assert rep["room_revenue"] == 30000  # 当日房租过账
        assert rep["total_revenue"] == 30000

        # 营业日已关闭
        bds = client.get(f"/api/v1/tenants/{t['code']}/business-days").json()
        assert bds[0]["status"] == "CLOSED"

    def test_room_charge_basis_is_booking_coverage(self, client: TestClient) -> None:
        """过账口径 = 「订单覆盖营业日」：check_in_date <= business_date < check_out_date。

        住 2026-10-01 → 10-03（2 晚）应恰好过账 2 笔房租：
          10-01 覆盖 → 计费；10-02 覆盖 → 计费；10-03 == 离店日 → 不计费。
        """
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "0101", "13700000041", "2026-10-01", "2026-10-03")

        for biz_date, expected in (
            ("2026-10-01", 30000),  # check_in <= d < check_out → 计费
            ("2026-10-02", 30000),  # 同上
            ("2026-10-03", 0),      # check_out == d（当天离店）→ 当晚不计费
        ):
            rep = client.post(
                f"/api/v1/tenants/{t['code']}/night-audit",
                json={"hotel_id": h["id"], "business_date": biz_date},
            ).json()
            assert rep["room_revenue"] == expected, f"{biz_date} → {rep['room_revenue']}"

        # 账单侧：恰好 2 笔房租，合计 60000（证明不是只改了报表数字）
        bill = client.get(f"/api/v1/tenants/{t['code']}/bills").json()[0]
        detail = client.get(f"/api/v1/tenants/{t['code']}/bills/{bill['id']}").json()
        room_items = [i for i in detail["items"] if i["type"] == "ROOM_CHARGE"]
        assert len(room_items) == 2, detail["items"]
        assert detail["balance"] == 60000

    def test_no_charge_on_departure_date_while_still_occupied(self, client: TestClient) -> None:
        """核心回归：当天应离店但尚未办退房 → 房间仍在住，但当日**不**产生房费。

        旧实现靠「预离翻房」把房间提前踢出在住集来规避多收；翻房删除后改为按订单
        覆盖营业日判断，从口径上杜绝「多收一晚」。
        """
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "0101", "13700000042", "2026-10-01", "2026-10-02")

        # 10-01 覆盖 → 计费一晚
        rep1 = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        ).json()
        assert rep1["room_revenue"] == 30000

        # 10-02 是离店日，客人尚未办退房：房间物理仍在住
        occupied = client.get(f"/api/v1/tenants/{t['code']}/rooms?state=occupied").json()
        assert [r["room_no"] for r in occupied] == ["0101"]

        rep2 = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-02"},
        ).json()
        assert rep2["occupied_rooms"] == 1  # 在住数仍按物理房态统计
        assert rep2["room_revenue"] == 0    # 但当日房费为 0，不得多收一晚

        # 账单侧：只有 10-01 那一笔
        bill = client.get(f"/api/v1/tenants/{t['code']}/bills").json()[0]
        detail = client.get(f"/api/v1/tenants/{t['code']}/bills/{bill['id']}").json()
        room_items = [i for i in detail["items"] if i["type"] == "ROOM_CHARGE"]
        assert len(room_items) == 1, detail["items"]
        assert detail["balance"] == 30000

    def test_no_pre_departure_flip_keeps_room_occupied(self, client: TestClient) -> None:
        """回归：夜审不得把「次日应离店」的在住房提前翻成空脏（房态/订单必须一致）。"""
        t, h, rt = _seed(client)
        bk = _check_in(client, t, rt, h, "0101", "13700000002", "2026-10-01", "2026-10-03")

        # 夜审 2026-10-02：次日(10-03)应离店 —— 房间必须仍在住，不得被翻脏
        client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-02"},
        )
        occupied = client.get(f"/api/v1/tenants/{t['code']}/rooms?state=occupied").json()
        assert [r["room_no"] for r in occupied] == ["0101"]
        dirty = client.get(f"/api/v1/tenants/{t['code']}/rooms?state=vacant_dirty").json()
        assert dirty == []
        # 订单仍是在住，未随房态被改动
        cur = next(
            b for b in client.get(f"/api/v1/tenants/{t['code']}/bookings").json()
            if b["id"] == bk["id"]
        )
        assert cur["status"] == "checked_in"

    def test_duplicate_audit_blocked(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "0101", "13700000003", "2026-10-01", "2026-10-03")
        client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        )
        resp = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        )
        assert resp.status_code == 409  # 已关闭不可重复夜审

    def test_snapshot_before_after_distribution(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "0101", "13700000011", "2026-10-01", "2026-10-03")

        rep = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        ).json()

        snap = json.loads(rep["snapshot"])
        assert "before" in snap and "after" in snap
        # 夜审前：1 间在住
        assert snap["before"]["occupied_rooms"] == 1
        assert snap["before"]["room_state_distribution"]["occupied"] == 1
        # 夜审后：过账房租写入快照
        assert snap["after"]["posted_room_charge"] == 30000

    def test_snapshot_no_flip_delta(self, client: TestClient) -> None:
        """回归：夜审不再翻房 → 在住数不跳变、flipped_rooms 恒为空数组。"""
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "0101", "13700000012", "2026-10-01", "2026-10-03")

        # 夜审 2026-10-02：次日(10-03)应离店，但房态保持不变
        rep = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-02"},
        ).json()

        snap = json.loads(rep["snapshot"])
        assert snap["diff"]["occupied_delta"] == 0  # 在住数不变
        assert snap["after"]["flipped_rooms"] == []  # 字段保留但不再有翻房
        # 该房仍是在住
        occupied = client.get(f"/api/v1/tenants/{t['code']}/rooms?state=occupied").json()
        assert any(r["room_no"] == "0101" for r in occupied)

    def test_night_audit_does_not_block_real_checkout(self, client: TestClient) -> None:
        """回归（核心）：夜审后「房间仍 occupied + 订单仍 checked_in」，真实退房必须成功。

        历史 bug：夜审按 check_out_date == business_date + 1 把房间翻成 vacant_dirty 却不动
        bookings.status；随后真实退房走 CHECK_OUT 流转时源状态非 OCCUPIED →
        InvalidTransition → 409，客人永远退不掉房，且空房可被重卖（重房）。
        """
        t, h, rt = _seed(client)
        client.post(
            f"/api/v1/hotels/{h['id']}/rooms",
            json=[{"room_type_id": rt["id"], "room_no": "0102"}],
        )
        bks = [
            _check_in(client, t, rt, h, "0101", "13700000031", "2026-10-01", "2026-10-03"),
            _check_in(client, t, rt, h, "0102", "13700000032", "2026-10-01", "2026-10-03"),
        ]
        client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-02"},
        )

        # 1) 夜审后：两间房仍在住
        occupied = {
            r["room_no"]
            for r in client.get(f"/api/v1/tenants/{t['code']}/rooms?state=occupied").json()
        }
        assert occupied == {"0101", "0102"}
        # 2) 夜审后：两笔订单仍是 checked_in
        listed = client.get(f"/api/v1/tenants/{t['code']}/bookings").json()
        for bk in bks:
            cur = next(b for b in listed if b["id"] == bk["id"])
            assert cur["status"] == "checked_in"

        # 3) 真实退房必须成功（被该 bug 卡死的路径）
        for bk in bks:
            resp = client.post(
                f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-out", json={}
            )
            assert resp.status_code == 200, resp.text
        dirty = {
            r["room_no"]
            for r in client.get(f"/api/v1/tenants/{t['code']}/rooms?state=vacant_dirty").json()
        }
        assert dirty == {"0101", "0102"}

    def test_snapshot_detects_occupied_without_booking(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        # 直接把房间翻成在住（无对应在住预订），制造房态差异
        tr = client.post(
            f"/api/v1/tenants/{t['code']}/rooms/0101/transition",
            json={"trigger": "check_in"},
        )
        assert tr.status_code == 200
        assert tr.json()["state"] == "occupied"

        rep = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        ).json()

        snap = json.loads(rep["snapshot"])
        anomalies = snap["before"]["anomalies"]
        assert any(a["room_no"] == "0101" and a["type"] == "occupied_without_booking" for a in anomalies)


class TestSuspendedReasonCategorize:
    def test_categorize_suspended(self) -> None:
        assert (
            _categorize_suspended(Exception("Multiple rows were found when one or none was required"))
            == "重复入住脏数据"
        )
        assert _categorize_suspended(Exception("room_type 不存在")) == "房型数据缺失"
        assert (
            _categorize_suspended(Exception("非法流转: 当前状态 occupied 不允许触发 check_out"))
            == "房态流转非法"
        )
        assert _categorize_suspended(Exception("UNIQUE constraint failed: business_days")) == "数据完整性冲突"
        assert _categorize_suspended(Exception("database connection timeout")) == "数据库/连接异常"
        assert _categorize_suspended(Exception("some weird failure")) == "未知异常"


class TestNightAuditBoard:
    def _seed_hotel(self, client, t, code, name):
        return client.post(
            f"/api/v1/tenants/{t['id']}/hotels", json={"code": code, "name": name}
        ).json()

    def test_board_multi_hotel(self, client: TestClient) -> None:
        t = client.post("/api/v1/tenants", json={"code": "nab", "name": "看板测试"}).json()
        h1 = self._seed_hotel(client, t, "H1", "店一")
        h2 = self._seed_hotel(client, t, "H2", "店二")
        # D1（M0 多店）：房型归属门店 —— 两店各建一个同名 STD 房型（门店级唯一）
        rt1 = client.post(
            f"/api/v1/tenants/{t['id']}/room-types",
            json={"code": "STD", "name": "标间", "base_price": 30000, "hotel_id": h1["id"]},
        ).json()
        rt2 = client.post(
            f"/api/v1/tenants/{t['id']}/room-types",
            json={"code": "STD", "name": "标间", "base_price": 30000, "hotel_id": h2["id"]},
        ).json()
        # 注意：Room 唯一约束为 (tenant_id, room_no)，同一租户下两店须用不同房号
        client.post(f"/api/v1/hotels/{h1['id']}/rooms", json=[{"room_type_id": rt1["id"], "room_no": "0101"}])
        client.post(f"/api/v1/hotels/{h2['id']}/rooms", json=[{"room_type_id": rt2["id"], "room_no": "0201"}])

        for hid, rtid, phone, rno in (
            (h1["id"], rt1["id"], "13700000021", "0101"),
            (h2["id"], rt2["id"], "13700000022", "0201"),
        ):
            bk = client.post(
                f"/api/v1/tenants/{t['code']}/bookings",
                json={
                    "hotel_id": hid,
                    "room_type_id": rtid,
                    "guest_name": "G",
                    "guest_phone": phone,
                    "check_in_date": "2026-10-01",
                    "check_out_date": "2026-10-03",
                    "room_no": rno,
                },
            ).json()
            client.post(
                f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in", json={"room_no": rno}
            )
            client.post(
                f"/api/v1/tenants/{t['code']}/night-audit",
                json={"hotel_id": hid, "business_date": "2026-10-01"},
            )

        board = client.get(f"/api/v1/tenants/{t['code']}/night-audit/board").json()
        assert board["hotel_count"] == 2
        assert board["total_suspended"] == 0
        assert {h["name"] for h in board["hotels"]} == {"店一", "店二"}
        for h in board["hotels"]:
            assert h["latest_status"] == "CLOSED"
            assert h["latest_report"]["room_revenue"] == 30000
            assert h["latest_report"]["occ_pct"] == 100
