"""夜审自动调度（M4-2）测试：批量跑批成功 / 单日异常挂起 / 挂起日重试。"""

from fastapi.testclient import TestClient

from app.services import night_audit_service as nas_module


def _seed(client: TestClient) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "aut", "name": "调度测试"}).json()
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


def _check_in(client: TestClient, t: dict, rt: dict, h: dict, phone: str) -> None:
    bk = client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": "G",
            "guest_phone": phone,
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-03",
            "room_no": "0101",
        },
    ).json()
    client.post(f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in", json={"room_no": "0101"})


class TestNightAuditAutoRun:
    def test_auto_run_success(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "13700000001")

        r = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
        ).json()
        assert r["ran"] == 1
        assert r["suspended"] == 0

        # 营业日已关闭、日报已生成
        bds = client.get(f"/api/v1/tenants/{t['code']}/business-days").json()
        assert bds[0]["status"] == "CLOSED"
        reps = client.get(f"/api/v1/tenants/{t['code']}/daily-reports").json()
        assert reps[0]["room_revenue"] == 30000

    def test_auto_run_suspends_on_failure(self, client: TestClient, monkeypatch) -> None:
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "13700000002")

        async def _boom(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise RuntimeError("forced failure")

        monkeypatch.setattr(nas_module.NightAuditService, "run_night_audit", _boom)

        r = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
        ).json()
        assert r["ran"] == 0
        assert r["suspended"] == 1
        assert "forced failure" in r["errors"][0]["error"]

        bds = client.get(f"/api/v1/tenants/{t['code']}/business-days").json()
        assert bds[0]["status"] == "SUSPENDED"
        # 挂账原因已归因（未知异常兜底，消息保留原文）
        assert bds[0]["suspended_reason"].startswith("[未知异常]")
        assert "forced failure" in bds[0]["suspended_reason"]

    def test_suspended_reason_categorized(self, client: TestClient, monkeypatch) -> None:
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "13700000003")

        async def _boom(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            # 模拟重复入住脏数据导致的 MultipleResultsFound
            raise RuntimeError("Multiple rows were found when one or none was required")

        monkeypatch.setattr(nas_module.NightAuditService, "run_night_audit", _boom)

        r = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
        ).json()
        assert r["suspended"] == 1

        bds = client.get(f"/api/v1/tenants/{t['code']}/business-days").json()
        assert bds[0]["status"] == "SUSPENDED"
        # 原因归因命中「重复入住脏数据」分类
        assert bds[0]["suspended_reason"].startswith("[重复入住脏数据]")

    def test_auto_run_survives_duplicate_checked_in(self, client: TestClient, tmp_path) -> None:
        """同房间残留多笔在住订单：夜审不挂起，房租入账到住期覆盖营业日的那笔。

        回归：旧实现用 scalar_one_or_none() 取单，遇多笔在住单抛
        MultipleResultsFound，导致整个营业日 SUSPENDED、房租无法入账（dev 库 500）。
        """
        import sqlite3

        t, h, rt = _seed(client)
        # 多建一间房作库存缓冲，使第二笔同房订单能过房量校验
        client.post(
            f"/api/v1/hotels/{h['id']}/rooms",
            json=[{"room_type_id": rt["id"], "room_no": "0102"}],
        )
        _check_in(client, t, rt, h, "13700000005")  # 第 1 笔：10-01 ~ 10-03，房 0101

        # 第 2 笔先落在 0102，再直接改库为「房 0101 + checked_in」，模拟重复入住脏数据
        bk2 = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "G2",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-05",
                "room_no": "0102",
            },
        ).json()
        con = sqlite3.connect(str(tmp_path / "test.db"))
        con.execute(
            "update bookings set room_no='0101', status='checked_in' where id=?",
            (bk2["id"],),
        )
        con.commit()
        con.close()

        r = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
        ).json()
        assert r["ran"] == 1, r
        assert r["suspended"] == 0, r
        assert r["errors"] == []

        # 房租只入账一次，且落在住期覆盖营业日的那笔（最新一笔）
        con = sqlite3.connect(str(tmp_path / "test.db"))
        rows = con.execute(
            "select b.booking_id, i.amount from bill_items i "
            "join bills b on b.id = i.bill_id "
            "where i.type = 'ROOM_CHARGE' and i.business_date = '2026-10-01'"
        ).fetchall()
        con.close()
        assert len(rows) == 1
        # 直查 DB 为 int，API 响应为 str（雪花 ID），比较需同类型
        assert str(rows[0][0]) == str(bk2["id"])
        assert rows[0][1] == 30000

    def test_auto_run_skips_closed_day(self, client: TestClient) -> None:
        """已夜审（CLOSED）的营业日重复 auto-run：跳过且不 500。

        回归：旧实现「无待审日即插入 as_of」会撞 business_days 唯一约束，
        且插入在异常隔离块之外，导致接口 500。
        """
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "13700000004")

        first = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["ran"] == 1

        second = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
        )
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["ran"] == 0
        assert body["suspended"] == 0
        assert body["skipped"] == 1
        assert body["skips"][0]["status"] == "CLOSED"
        assert body["errors"] == []

        # 未重复插入营业日，也未重复出日报（防重复过账）
        bds = client.get(f"/api/v1/tenants/{t['code']}/business-days").json()
        assert len(bds) == 1
        reps = client.get(f"/api/v1/tenants/{t['code']}/daily-reports").json()
        assert len(reps) == 1

    def test_auto_run_reruns_suspended(self, client: TestClient, monkeypatch) -> None:
        t, h, rt = _seed(client)
        _check_in(client, t, rt, h, "13700000003")

        orig = nas_module.NightAuditService.run_night_audit  # 先捕获真实实现

        async def _boom(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise RuntimeError("forced failure")

        monkeypatch.setattr(nas_module.NightAuditService, "run_night_audit", _boom)
        client.post(
            f"/api/v1/tenants/{t['code']}/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
        )
        monkeypatch.setattr(nas_module.NightAuditService, "run_night_audit", orig)  # 恢复真实夜审

        r = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
        ).json()
        assert r["ran"] == 1
        assert r["suspended"] == 0
        bds = client.get(f"/api/v1/tenants/{t['code']}/business-days").json()
        assert bds[0]["status"] == "CLOSED"
