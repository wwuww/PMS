"""M31：NoShow 自动扣首晚房费（酒店级 + 租户级默认两层兜底）门禁测试。

覆盖场景（与 PRD §验收清单#3 / M31 一一对应）：
1. 默认关闭：不配任何配置 → NoShow 订单**无** ROOM_CHARGE 账单（首晚不扣）；
2. 租户级启用：Tenant.noshow_charge_first_night=True → 夜审后 NoShow 订单生成
   一张 ``type=ROOM_CHARGE, business_date=check_in_date, description 含 "NoShow首晚"``
   的 BillItem，金额=首晚房费；
3. 酒店级覆盖：Tenant=True + Hotel=False → 不扣（Hotel 覆盖 Tenant）；
   Tenant=False + Hotel=True → 扣（Hotel 覆盖 Tenant）；
4. 时租跳过：stay_type=hourly 的 NoShow 订单不扣；
5. 防重复/幂等：同一 booking 夜审两次（或预置一张同 check_in_date 的 ROOM_CHARGE），
   第二次不重复扣；
6. 无 OPEN 账单：NoShow 订单无账单时，首晚扣款能自动开账（open_bill）并过账。

幂等性
-------
5 通过两种方式验证：
- 夜审连续跑两次：第二次应跳过（_auto_noshow 内 status!=CREATED，已不再选；或即便
  防重，状态已变 NOSHOW 不会再次扫描）—— 主要验证「同状态多次扫描不重复扣」。
- 预置同 business_date 的 ROOM_CHARGE：再触发时 _charge_noshow_first_night 内
  显式判重（select BillItem by bill+type+business_date）→ 跳过。
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[dict, dict, dict]:
    """播种租户 + 门店 + 房型 + 房间。"""
    t = client.post("/api/v1/tenants", json={"code": "m31", "name": "M31测试"}).json()
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


def _create_booking(
    client: TestClient,
    t: dict,
    h: dict,
    rt: dict,
    *,
    check_in: str = "2026-10-01",
    check_out: str = "2026-10-03",
    stay_type: str = "daily",
    rate_code_code: str | None = None,
) -> dict:
    """创建 CREATED 状态预订（不入住）。"""
    body: dict = {
        "hotel_id": h["id"],
        "room_type_id": rt["id"],
        "guest_name": "G",
        "check_in_date": check_in,
        "check_out_date": check_out,
        "room_no": "0101",
    }
    if rate_code_code is not None:
        body["rate_code_code"] = rate_code_code
    if stay_type == "hourly":
        body["stay_type"] = "hourly"
        body["hourly_hours"] = 4
    return client.post(
        f"/api/v1/tenants/{t['code']}/bookings", json=body
    ).json()


def _room_charges(test_db: str, business_date: str | None = None) -> list[tuple]:
    """直查 SQLite：所有 ROOM_CHARGE 条目（可按营业日过滤）。"""
    con = sqlite3.connect(test_db)
    if business_date is None:
        rows = con.execute(
            "select b.room_no, i.amount, i.business_date, i.description "
            "from bill_items i join bills b on b.id = i.bill_id "
            "where i.type = 'ROOM_CHARGE' order by i.id"
        ).fetchall()
    else:
        rows = con.execute(
            "select b.room_no, i.amount, i.business_date, i.description "
            "from bill_items i join bills b on b.id = i.bill_id "
            "where i.type = 'ROOM_CHARGE' and i.business_date = ?",
            (business_date,),
        ).fetchall()
    con.close()
    return rows


def _run_night_audit(
    client: TestClient, t: dict, h: dict, business_date: str = "2026-10-02"
) -> dict:
    """夜审。business_date 晚于 check_in_date 以触发 NoShow 自动扫描。"""
    r = client.post(
        f"/api/v1/tenants/{t['code']}/night-audit",
        json={"hotel_id": h["id"], "business_date": business_date},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _set_tenant_flag(
    client: TestClient, t: dict, noshow_charge_first_night: bool
) -> None:
    r = client.patch(
        f"/api/v1/tenants/{t['code']}/settings",
        json={"noshow_charge_first_night": noshow_charge_first_night},
    )
    assert r.status_code == 200, r.text


def _set_hotel_flag(
    client: TestClient, t: dict, h: dict, noshow_charge_first_night: bool | None
) -> None:
    """酒店级覆盖：None=回落租户默认（落库 NULL）。"""
    r = client.patch(
        f"/api/v1/tenants/{t['code']}/hotels/{h['id']}/settings",
        json={"noshow_charge_first_night": noshow_charge_first_night},
    )
    assert r.status_code == 200, r.text


class TestM31NoshowChargeDefault:
    def test_default_off_does_not_charge(self, client: TestClient, tmp_path) -> None:
        """默认关闭：不配任何配置，夜审后 NoShow 订单无 ROOM_CHARGE 账单。"""
        t, h, rt = _seed(client)
        _create_booking(client, t, h, rt)
        # 显式清零（防御：其它测试可能改了默认值；新 DB 默认 False，无需 patch）
        _run_night_audit(client, t, h, "2026-10-02")
        assert _room_charges(str(tmp_path / "test.db")) == []

    def test_tenant_enabled_charges_first_night(
        self, client: TestClient, tmp_path
    ) -> None:
        """租户级启用：夜审后 NoShow 订单生成 ROOM_CHARGE，金额=首晚房费。"""
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        _create_booking(client, t, h, rt)
        _run_night_audit(client, t, h, "2026-10-02")
        charges = _room_charges(str(tmp_path / "test.db"), "2026-10-01")
        assert len(charges) == 1, charges
        room_no, amount, bdate, desc = charges[0]
        assert room_no == "0101"
        assert amount == 30000  # base_price
        assert bdate == "2026-10-01"
        assert "NoShow首晚" in desc


class TestM31HotelOverride:
    def test_hotel_false_overrides_tenant_true(
        self, client: TestClient, tmp_path
    ) -> None:
        """酒店级覆盖：Tenant=True + Hotel=False → 不扣。"""
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        _set_hotel_flag(client, t, h, False)
        _create_booking(client, t, h, rt)
        _run_night_audit(client, t, h, "2026-10-02")
        assert _room_charges(str(tmp_path / "test.db")) == []

    def test_hotel_true_overrides_tenant_false(
        self, client: TestClient, tmp_path
    ) -> None:
        """酒店级覆盖：Tenant=False + Hotel=True → 扣。"""
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, False)
        _set_hotel_flag(client, t, h, True)
        _create_booking(client, t, h, rt)
        _run_night_audit(client, t, h, "2026-10-02")
        charges = _room_charges(str(tmp_path / "test.db"), "2026-10-01")
        assert len(charges) == 1, charges
        assert charges[0][1] == 30000

    def test_hotel_none_falls_back_to_tenant(self, client: TestClient, tmp_path) -> None:
        """酒店级未设置（None）→ 继承租户默认；Tenant=True 时应扣。"""
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        # _set_hotel_flag 不调（默认 None = 继承）
        _create_booking(client, t, h, rt)
        _run_night_audit(client, t, h, "2026-10-02")
        charges = _room_charges(str(tmp_path / "test.db"), "2026-10-01")
        assert len(charges) == 1, charges

    def test_hotel_null_explicitly_clears_override(
        self, client: TestClient, tmp_path
    ) -> None:
        """酒店级显式置 null（清除覆盖）→ 回落租户默认。"""
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        _set_hotel_flag(client, t, h, False)  # 先设 False
        _set_hotel_flag(client, t, h, None)  # 再清回 None
        _create_booking(client, t, h, rt)
        _run_night_audit(client, t, h, "2026-10-02")
        charges = _room_charges(str(tmp_path / "test.db"), "2026-10-01")
        assert len(charges) == 1, charges  # 继承 Tenant=True → 扣


class TestM31HourlySkipped:
    def test_hourly_booking_not_charged(self, client: TestClient, tmp_path) -> None:
        """时租（stay_type=hourly）的 NoShow 订单不扣。"""
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        _create_booking(client, t, h, rt, stay_type="hourly")
        _run_night_audit(client, t, h, "2026-10-02")
        assert _room_charges(str(tmp_path / "test.db")) == []


class TestM31Idempotent:
    def test_double_night_audit_does_not_double_charge(
        self, client: TestClient, tmp_path
    ) -> None:
        """防重复：同 booking 夜审两次不重复扣。

        走真实路径：第一次夜审将 booking 标 NOSHOW；第二次 _auto_noshow 扫描
        status=CREATED 已不再命中 → 不会再次过账。
        """
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        _create_booking(client, t, h, rt)
        # 第一次夜审（business_date 10-02，booking 应到 10-01）
        r1 = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-02"},
        )
        assert r1.status_code == 201, r1.text
        # 第二次夜审：业务日已 CLOSED，应被 _get_or_open_day 拒绝（409）
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-02"},
        )
        assert r2.status_code == 409, r2.text
        # 仍只 1 条 ROOM_CHARGE
        charges = _room_charges(str(tmp_path / "test.db"), "2026-10-01")
        assert len(charges) == 1, charges

    def test_existing_room_charge_skipped_idempotent(
        self, client: TestClient, tmp_path
    ) -> None:
        """防重复：预置同 (bill, type, business_date) 的 ROOM_CHARGE → 二次扫描跳过。

        模拟「半路崩溃重跑」：业务上已开账并过账了首晚，再触发时不再重复。
        通过直接对 booking 重置 status=CREATED（模拟「上一轮被回滚」）并预置
        一条 ROOM_CHARGE 条目，验证 _charge_noshow_first_night 内的等值判重。
        """
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        bk = _create_booking(client, t, h, rt)
        # 第 1 次夜审：完成过账
        _run_night_audit(client, t, h, "2026-10-02")
        assert len(_room_charges(str(tmp_path / "test.db"), "2026-10-01")) == 1
        # 手工把 booking 倒回 CREATED + 清 noshow_reason + 删 ROOM_CHARGE，模拟重跑场景
        # 同时把营业日从 CLOSED 倒回 OPEN（重开），让第二次夜审能跑通
        db = str(tmp_path / "test.db")
        con = sqlite3.connect(db)
        con.execute(
            "update bookings set status='created', noshow_reason=NULL where id=?",
            (bk["id"],),
        )
        con.execute(
            "delete from bill_items where type='ROOM_CHARGE' and business_date='2026-10-01'"
        )
        con.execute(
            "update business_days set status='OPEN', suspended_reason=NULL, "
            "audited_at=NULL, audited_by=NULL where business_date='2026-10-02'"
        )
        con.execute("delete from daily_reports where business_date='2026-10-02'")
        con.commit()
        con.close()
        # 预先手工插入同 business_date 的 ROOM_CHARGE（金额任意不同）
        # 雪花 ID 由 SQLAlchemy 默认生成（不显式给值时为 NULL），手工 INSERT 必须显式赋值。
        from app.core.snowflake import next_id

        con = sqlite3.connect(db)
        bill_id = con.execute(
            "select id from bills where booking_id=? and status='OPEN'", (bk["id"],)
        ).fetchone()[0]
        con.execute(
            "insert into bill_items (id, tenant_id, bill_id, type, amount, "
            "description, business_date, created_by, created_at, updated_at) "
            "values (?, ?, ?, 'ROOM_CHARGE', 1, 'pre-existing', '2026-10-01', 'test', "
            "datetime('now'), datetime('now'))",
            (next_id(), t["code"], bill_id),
        )
        con.commit()
        con.close()
        # 第 2 次夜审：状态又变为 CREATED，_auto_noshow 命中；_charge_noshow_first_night
        # 看到已有同 business_date 的 ROOM_CHARGE 应跳过 → 仍只 1 条，金额保留 1
        _run_night_audit(client, t, h, "2026-10-02")
        charges = _room_charges(str(tmp_path / "test.db"), "2026-10-01")
        assert len(charges) == 1, charges
        assert charges[0][1] == 1  # 保留预置的 1 分


class TestM31NoOpenBill:
    def test_no_existing_bill_auto_opens_and_charges(
        self, client: TestClient, tmp_path
    ) -> None:
        """无 OPEN 账单：NoShow 订单无账单时，首晚扣款能自动开账（open_bill）并过账。

        CREATED 状态预订从未入住，没有 Bill。_charge_noshow_first_night 内部自动
        open_bill → add_charge，全程 self-contained。
        """
        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        bk = _create_booking(client, t, h, rt)
        _run_night_audit(client, t, h, "2026-10-02")
        # 验证开账 + 过账
        db = str(tmp_path / "test.db")
        con = sqlite3.connect(db)
        bills = con.execute(
            "select id, booking_id, status, balance from bills where booking_id=?",
            (bk["id"],),
        ).fetchall()
        con.close()
        assert len(bills) == 1, bills
        bill_id, _, status, balance = bills[0]
        assert status == "OPEN"
        assert balance == 30000
        # BillItem 落库
        charges = _room_charges(db, "2026-10-01")
        assert len(charges) == 1
        assert charges[0][0] == "0101"


class TestM31FailureIsolation:
    def test_charge_failure_does_not_block_noshow_marking(
        self, client: TestClient, tmp_path
    ) -> None:
        """首晚扣款失败（如价格解析异常）不阻断 NoShow 标记。

        用 monkeypatch 替换 batch_resolve 让它抛异常，验证：
        1) booking 仍被标 NOSHOW；
        2) 不留 ROOM_CHARGE 条目。
        """
        from app.services import price_service as ps_module

        t, h, rt = _seed(client)
        _set_tenant_flag(client, t, True)
        bk = _create_booking(client, t, h, rt)

        async def _boom(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise RuntimeError("simulated price resolve failure")

        orig = ps_module.PriceService.batch_resolve
        ps_module.PriceService.batch_resolve = _boom
        try:
            r = client.post(
                f"/api/v1/tenants/{t['code']}/night-audit",
                json={"hotel_id": h["id"], "business_date": "2026-10-02"},
            )
            # 夜审主流程不挂起（异常被 _auto_noshow 内 try/except 吞掉）
            assert r.status_code == 201, r.text
        finally:
            ps_module.PriceService.batch_resolve = orig

        # booking 仍标 NOSHOW
        db = str(tmp_path / "test.db")
        con = sqlite3.connect(db)
        row = con.execute(
            "select status, noshow_reason from bookings where id=?", (bk["id"],)
        ).fetchone()
        con.close()
        assert row[0] == "noshow", row
        assert row[1] is not None
        # 没有 ROOM_CHARGE 落库
        assert _room_charges(db) == []


class TestM31SettingsAPI:
    def test_tenant_settings_roundtrip(self, client: TestClient) -> None:
        """PATCH /tenants/{code}/settings 落库与回读。"""
        t, h, _ = _seed(client)
        # 默认 False
        r0 = client.get(f"/api/v1/tenants").json()
        tenant0 = next(x for x in r0 if x["id"] == t["id"])
        assert tenant0["noshow_charge_first_night"] is False
        # 改 True
        r1 = client.patch(
            f"/api/v1/tenants/{t['code']}/settings",
            json={"noshow_charge_first_night": True},
        )
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body["noshow_charge_first_night"] is True
        # 回读
        r2 = client.get(f"/api/v1/tenants").json()
        tenant2 = next(x for x in r2 if x["id"] == t["id"])
        assert tenant2["noshow_charge_first_night"] is True

    def test_hotel_settings_roundtrip(self, client: TestClient) -> None:
        """PATCH /tenants/{code}/hotels/{id}/settings 落库与回读（含 null 清除）。"""
        t, h, _ = _seed(client)
        # 默认 None
        r0 = client.get(f"/api/v1/tenants/{t['code']}/hotels").json()
        hotel0 = next(x for x in r0 if x["id"] == h["id"])
        assert hotel0["noshow_charge_first_night"] is None
        # 设 True
        r1 = client.patch(
            f"/api/v1/tenants/{t['code']}/hotels/{h['id']}/settings",
            json={"noshow_charge_first_night": True},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["noshow_charge_first_night"] is True
        # 显式置 null 清除
        r2 = client.patch(
            f"/api/v1/tenants/{t['code']}/hotels/{h['id']}/settings",
            json={"noshow_charge_first_night": None},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["noshow_charge_first_night"] is None

    def test_tenant_settings_404_or_403(self, client: TestClient) -> None:
        """PATCH /tenants/{nonexistent}/settings —— 不存在租户应拒绝。

        实际状态码取决于授权层 vs 路由层的执行顺序：
        路由 ``require_perm`` 依赖 ``resolve_tenant_id`` 提取 tenant code；对不存在的
        租户，``seed_default_admin`` 会创 user 但无 admin role（roles 仅在真实开通
        租户时播种），因此 ``require_perm`` 命中 night_audit.run 缺失 → 403。
        不论 403/404，目的都是拒绝非授权租户。
        """
        r = client.patch(
            "/api/v1/tenants/nonexistent_tenant/settings",
            json={"noshow_charge_first_night": True},
        )
        assert r.status_code in (403, 404), r.text
