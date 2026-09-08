"""M32 MAX_LIST_ROWS 推广回归门禁：9 高基数端点 + housekeeping 2 处 SQL 改造。

设计意图
--------
M32 把审计 D1（51 个无 limit 端点）的护栏抽成 ``Paged`` 公共依赖，并接入 9 个
高基数端点 + housekeeping 2 处内存过滤改为 SQL 下推。本测试作为永久门禁：

1. ``Paged`` 依赖注入：``?limit=N&offset=M`` 走标准分页；``?limit>MAX_LIST_ROWS``
   被 FastAPI Query 校验拦截；不传时默认 ``MAX_LIST_ROWS``。
2. 9 个高基数端点显式 limit/offset 后返回行数 ≤ N；显式 ``?offset=M`` 跳过前 M 行。
3. ``staff_performance`` 起止日期下推到 SQL（结果与原版一致）。
4. ``overdue_count`` SQL ``COUNT(*)`` 语义正确（含「含 end 当天」「过去/未来
   due_at」两侧断言）。
5. Paged 边界：「超过硬上限返 422」「offset < 0 返 422」「未传 limit 不破坏既有」。

任何一项失败都意味着 Paged 接入造成行为漂移或 SQL 下推改坏了语义，必须修复后再合。
"""

from __future__ import annotations

import asyncio
import uuid as _uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import MAX_LIST_ROWS


# =========================================================================
# 公共 fixture / 工具
# =========================================================================


def _seed_basic(client: TestClient, code: str) -> tuple[dict, dict, dict]:
    """1 店 1 房型 1 房的最小组。"""
    t = client.post("/api/v1/tenants", json={"code": code, "name": "M32"}).json()
    assert "id" in t, f"创建租户失败：{t}"
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    assert "id" in h, f"创建门店失败：{h}"
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    assert "id" in rt, f"创建房型失败：{rt}"
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "0101"}])
    return t, h, rt


def _open_api_key_for(client: TestClient, code: str) -> str:
    """为已存在的租户创建开放平台应用并签发 API Key，返回明文 secret。

    前置：调用方已用 ``_seed_basic`` 建好租户。
    """
    resp = client.post(
        f"/api/v1/tenants/{code}/openapi/apps",
        json={"app_code": f"app-{_uuid.uuid4().hex[:6]}", "name": "M32 App"},
    )
    assert resp.status_code == 201, f"创建应用失败：{resp.text}"
    app_id = resp.json()["id"]
    key_resp = client.post(f"/api/v1/tenants/{code}/openapi/apps/{app_id}/keys")
    assert key_resp.status_code == 201, f"签发 Key 失败：{key_resp.text}"
    return key_resp.json()["secret"]


# =========================================================================
# 1. Paged 依赖注入：Query 校验 + 默认值 + 透传 (limit, offset) tuple
# =========================================================================


class TestPagedDependency:
    """Paged 工厂：Query 校验 + 默认值 + 透传。"""

    def test_max_list_rows_constant(self) -> None:
        """MAX_LIST_ROWS 常量定义在 dependencies 模块，值固定 5000。"""
        # 防止 audit D1 模板错把 MAX_LIST_ROWS 重定义为 routes.py 局部导致依赖失效
        import app.api.routes as _r

        # 关键约束：常量值等于公共依赖模块的定义，且 routes.py 通过 import 复用
        assert MAX_LIST_ROWS == 5000
        assert _r.MAX_LIST_ROWS == 5000  # 引用的是依赖模块里的同一常量

    def test_query_validation_limit_too_large(self, client: TestClient) -> None:
        """``?limit=10000`` 超过硬上限 → FastAPI Query 拦截 422。"""
        t, h, _ = _seed_basic(client, f"m32v1{_uuid.uuid4().hex[:6]}")
        r = client.get(
            f"/api/v1/tenants/{t['code']}/business-days",
            params={"hotel_id": h["id"], "limit": 10000},
        )
        assert r.status_code == 422, r.text

    def test_query_validation_limit_zero(self, client: TestClient) -> None:
        """``?limit=0`` 不满足 ``ge=1`` → 422。"""
        t, _, _ = _seed_basic(client, f"m32v2{_uuid.uuid4().hex[:6]}")
        r = client.get(
            f"/api/v1/tenants/{t['code']}/business-days",
            params={"limit": 0},
        )
        assert r.status_code == 422

    def test_query_validation_offset_negative(self, client: TestClient) -> None:
        """``?offset=-1`` 不满足 ``ge=0`` → 422。"""
        t, _, _ = _seed_basic(client, f"m32v3{_uuid.uuid4().hex[:6]}")
        r = client.get(
            f"/api/v1/tenants/{t['code']}/business-days",
            params={"offset": -1},
        )
        assert r.status_code == 422


# =========================================================================
# 2. 9 个高基数端点的 limit/offset 行为
# =========================================================================


class TestHighCardinalityEndpoints:
    """9 个高基数端点显式 limit/offset 后行为正确。"""

    # ---------- 2.1 list_business_days (inline 模式 + order_by) ----------

    def test_business_days_limit_offset(self, client: TestClient) -> None:
        """list_business_days：limit/offset + order_by 稳定分页。"""
        code = f"m32bd{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        # 跑两次夜审（不同日期）→ 两条 BusinessDay + 两条 DailyReport
        for biz_date in ("2026-10-01", "2026-10-02"):
            r = client.post(
                f"/api/v1/tenants/{code}/night-audit",
                json={"hotel_id": h["id"], "business_date": biz_date, "operator": "test"},
            )
            assert r.status_code == 201, r.text

        # 不传 limit → 默认 MAX_LIST_ROWS（5000），全量返回（2 条）
        full = client.get(f"/api/v1/tenants/{code}/business-days").json()
        assert len(full) == 2

        # 显式 limit=1 + offset=0 → 1 条（id desc，最新优先）
        one = client.get(
            f"/api/v1/tenants/{code}/business-days",
            params={"limit": 1, "offset": 0},
        ).json()
        assert len(one) == 1

        # 显式 limit=1 + offset=1 → 另一条（跳过最新）
        one_offset = client.get(
            f"/api/v1/tenants/{code}/business-days",
            params={"limit": 1, "offset": 1},
        ).json()
        assert len(one_offset) == 1
        # id desc 排序 → offset=1 跳过最新，第二条应该是更早的营业日
        assert one[0]["business_date"] != one_offset[0]["business_date"]

    # ---------- 2.2 list_daily_reports (inline 模式 + order_by) ----------

    def test_daily_reports_limit_offset(self, client: TestClient) -> None:
        """list_daily_reports：limit/offset + order_by 稳定分页。"""
        code = f"m32dr{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        for biz_date in ("2026-10-01", "2026-10-02", "2026-10-03"):
            r = client.post(
                f"/api/v1/tenants/{code}/night-audit",
                json={"hotel_id": h["id"], "business_date": biz_date, "operator": "test"},
            )
            assert r.status_code == 201, r.text

        full = client.get(f"/api/v1/tenants/{code}/daily-reports").json()
        assert len(full) == 3

        two = client.get(
            f"/api/v1/tenants/{code}/daily-reports",
            params={"limit": 2, "offset": 0},
        ).json()
        assert len(two) == 2

    # ---------- 2.3 list_shifts (service 模式 + ShiftService.list_shifts) ----------

    def test_shifts_limit_offset(self, client: TestClient) -> None:
        """list_shifts：limit/offset 透传到 ShiftService.list_shifts。"""
        code = f"m32sf{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        # 建 3 个 open 班（合计 3 条 ShiftHandover）
        for cashier in ("收银A", "收银B", "收银C"):
            client.post(
                f"/api/v1/tenants/{code}/shifts/open",
                json={"hotel_id": h["id"], "cashier": cashier, "opening_float_cents": 0},
            )
        full = client.get(
            f"/api/v1/tenants/{code}/shifts",
            params={"hotel_id": h["id"]},
        ).json()
        assert len(full) == 3

        two = client.get(
            f"/api/v1/tenants/{code}/shifts",
            params={"hotel_id": h["id"], "limit": 2, "offset": 0},
        ).json()
        assert len(two) == 2

        # offset=2 跳过前 2 → 剩 1
        tail = client.get(
            f"/api/v1/tenants/{code}/shifts",
            params={"hotel_id": h["id"], "limit": 5, "offset": 2},
        ).json()
        assert len(tail) == 1

    # ---------- 2.4 list_price_calendar (inline 模式 + (date, room_type_id) 排序) ----------

    def test_price_calendar_limit_offset(self, client: TestClient) -> None:
        """list_price_calendar：limit/offset + (date, room_type_id) 排序。"""
        code = f"m32pc{_uuid.uuid4().hex[:6]}"
        t, h, rt = _seed_basic(client, code)
        # 批量建价格日历：3 天（字段名是 ``price``，不是 ``price_cents``）
        upsert = client.post(
            f"/api/v1/tenants/{code}/price-calendar/batch",
            json=[
                {"hotel_id": h["id"], "room_type_id": rt["id"], "date": d, "price": 30000}
                for d in ("2026-11-01", "2026-11-02", "2026-11-03")
            ],
        )
        assert upsert.status_code == 200, upsert.text
        assert upsert.json()["updated"] == 3

        full = client.get(
            f"/api/v1/tenants/{code}/price-calendar",
            params={"start": "2026-11-01", "end": "2026-11-03"},
        ).json()
        assert len(full) == 3

        # limit=1 + offset=0 → 第一天（按 date asc）
        one = client.get(
            f"/api/v1/tenants/{code}/price-calendar",
            params={"start": "2026-11-01", "end": "2026-11-03", "limit": 1, "offset": 0},
        ).json()
        assert len(one) == 1
        assert one[0]["date"] == "2026-11-01"

    # ---------- 2.5 list_group_blocks (service 模式 + GroupBlockService.list_blocks) ----------

    def test_group_blocks_limit_offset(self, client: TestClient) -> None:
        """list_group_blocks：limit/offset 透传到 GroupBlockService.list_blocks。"""
        code = f"m32gb{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        # 建 2 个 group block
        for name in ("团A", "团B"):
            r = client.post(
                f"/api/v1/tenants/{code}/group-blocks",
                json={
                    "hotel_id": h["id"],
                    "name": name,
                    "arrival_date": "2026-12-01",
                    "departure_date": "2026-12-03",
                },
            )
            assert r.status_code == 201, r.text

        full = client.get(f"/api/v1/tenants/{code}/group-blocks").json()
        assert len(full) == 2

        one = client.get(
            f"/api/v1/tenants/{code}/group-blocks",
            params={"limit": 1, "offset": 0},
        ).json()
        assert len(one) == 1

    # ---------- 2.6 list_alerts (service 模式 + AnomalyService.list_alerts) ----------

    def test_alerts_limit_offset(self, client: TestClient) -> None:
        """list_alerts：limit/offset 透传到 AnomalyService.list_alerts。"""
        code = f"m32al{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        # 直接 ORM 建 3 条预警（绕开夜审路径，避免引入额外依赖）
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.db.session import get_engine
        from app.models import AlertNotification

        async def _seed_alerts() -> None:
            sf = async_sessionmaker(get_engine(), expire_on_commit=False)
            async with sf() as s:
                for i in range(3):
                    s.add(
                        AlertNotification(
                            tenant_id=code,  # 用租户 code（URL 解析的就是 code）
                            hotel_id=h["id"],
                            alert_type="amount_anomaly",
                            severity="warning",
                            title=f"预警{i+1}",
                            description=f"desc{i+1}",
                            ref_type="bill",
                            ref_id=str(i + 1),
                        )
                    )
                await s.commit()

        asyncio.run(_seed_alerts())

        full = client.get(f"/api/v1/tenants/{code}/ai/alerts").json()
        assert len(full) == 3

        two = client.get(
            f"/api/v1/tenants/{code}/ai/alerts",
            params={"limit": 2, "offset": 0},
        ).json()
        assert len(two) == 2

    # ---------- 2.7 list_yield_recommendations (service 模式 + YieldService.list_recommendations) ----------

    def test_yield_recommendations_limit_offset(self, client: TestClient) -> None:
        """list_yield_recommendations：limit/offset 透传 YieldService.list_recommendations。"""
        code = f"m32yr{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)

        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.db.session import get_engine
        from app.models import PriceRecommendation

        async def _seed_recs() -> None:
            sf = async_sessionmaker(get_engine(), expire_on_commit=False)
            async with sf() as s:
                for biz in ("2026-12-01", "2026-12-02", "2026-12-03"):
                    s.add(
                        PriceRecommendation(
                            tenant_id=code,  # URL 解析出的是 code
                            hotel_id=h["id"],
                            business_date=biz,
                            base_price_cents=30000,
                            recommended_price_cents=35000,
                            adjustment_bps=1667,  # ≈16.67%
                            status="suggested",
                        )
                    )
                await s.commit()

        asyncio.run(_seed_recs())

        full = client.get(f"/api/v1/tenants/{code}/yield/pricing/recommendations").json()
        assert len(full) == 3

        one = client.get(
            f"/api/v1/tenants/{code}/yield/pricing/recommendations",
            params={"limit": 1, "offset": 0},
        ).json()
        assert len(one) == 1

    # ---------- 2.8 openapi_read_rooms (第三方 API + inline 模式) ----------

    def test_openapi_read_rooms_limit_offset(self, client: TestClient) -> None:
        """openapi_read_rooms：limit/offset 走 inline + Room.id 升序。"""
        code = f"m32o1{_uuid.uuid4().hex[:6]}"
        t, h, rt = _seed_basic(client, code)
        api_key = _open_api_key_for(client, code)  # 必须在 _seed_basic 之后
        # _seed_basic 已建 0101；新增 0201/0202（避免与 0101 的 (tenant_id, room_no) 唯一约束冲突）
        for room_no in ("0201", "0202"):
            r = client.post(
                f"/api/v1/hotels/{h['id']}/rooms",
                json=[{"room_type_id": rt["id"], "room_no": room_no}],
            )
            assert r.status_code == 201, r.text

        # 显式 limit=2 + offset=0：应返 0101（id 最小）+ 0201
        r = client.get(
            f"/api/v1/tenants/{code}/openapi/v1/hotels/{h['id']}/rooms",
            params={"limit": 2, "offset": 0},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert r.status_code == 200, r.text
        rooms = r.json()
        assert len(rooms) == 2
        # id asc 排序：offset=0 是 id 最小的 2 间房
        assert rooms[0]["room_no"] == "0101"
        assert rooms[1]["room_no"] == "0201"

        # offset=2 → 第 3 间（0202）
        r2 = client.get(
            f"/api/v1/tenants/{code}/openapi/v1/hotels/{h['id']}/rooms",
            params={"limit": 5, "offset": 2},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert r2.status_code == 200
        rooms2 = r2.json()
        assert len(rooms2) == 1
        assert rooms2[0]["room_no"] == "0202"

    # ---------- 2.9 openapi_read_bookings (第三方 API + inline 模式) ----------

    def test_openapi_read_bookings_limit_offset(self, client: TestClient) -> None:
        """openapi_read_bookings：limit/offset 走 inline + Booking.id desc。"""
        code = f"m32o2{_uuid.uuid4().hex[:6]}"
        t, h, rt = _seed_basic(client, code)
        # 多建 2 间房（0201/0202）以容纳 2 笔订单不撞房
        for room_no in ("0201", "0202"):
            client.post(
                f"/api/v1/hotels/{h['id']}/rooms",
                json=[{"room_type_id": rt["id"], "room_no": room_no}],
            )
        api_key = _open_api_key_for(client, code)
        # 建 2 笔订单（不同房号，不撞房）
        for room_no in ("0201", "0202"):
            client.post(
                f"/api/v1/tenants/{code}/bookings",
                json={
                    "hotel_id": h["id"],
                    "room_type_id": rt["id"],
                    "guest_name": f"渠道客{room_no}",
                    "check_in_date": "2026-12-01",
                    "check_out_date": "2026-12-02",
                    "room_no": room_no,
                },
            )

        # 显式 limit=1 + offset=0
        r = client.get(
            f"/api/v1/tenants/{code}/openapi/v1/bookings",
            params={"limit": 1, "offset": 0},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert r.status_code == 200, r.text
        bookings = r.json()
        assert len(bookings) == 1

        # 不传 limit → 默认 MAX_LIST_ROWS（5000），全量
        full = client.get(
            f"/api/v1/tenants/{code}/openapi/v1/bookings",
            headers={"Authorization": f"Bearer {api_key}"},
        ).json()
        assert len(full) == 2


# =========================================================================
# 3. housekeeping.staff_performance：日期范围下推到 SQL
# =========================================================================


class TestStaffPerformanceSqlPushdown:
    """staff_performance：日期范围 WHERE 下推 + LIMIT 5000 + 触顶 warning。"""

    def _make_done_task(
        self,
        tenant_code: str,
        hotel_id: int,
        room_no: str,
        assignee: str,
        done_at: datetime,
    ) -> None:
        """直接 ORM 建一条 DONE 工单（绕过退房自动路径）。

    注意：tenant_id 字段值用 ``code``（与 URL 路径解析出的字符串一致），
    而**不是** int id（int id 在 routes 里不会被 URL 路径匹配到）。
    """
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.db.session import get_engine
        from app.models import HousekeepingTask

        async def _seed() -> None:
            sf = async_sessionmaker(get_engine(), expire_on_commit=False)
            async with sf() as s:
                s.add(
                    HousekeepingTask(
                        tenant_id=tenant_code,
                        hotel_id=hotel_id,
                        room_no=room_no,
                        task_type="MAINTENANCE",  # 非 CLEANUP，done() 直接置 DONE
                        status="DONE",
                        assignee=assignee,
                        done_at=done_at,
                        created_at=done_at - timedelta(minutes=30),
                    )
                )
                await s.commit()

        asyncio.run(_seed())

    def test_date_range_filter_sql_pushdown(self, client: TestClient) -> None:
        """start_date/end_date 下推到 SQL：窗口外的工单不计入聚合。"""
        code = f"m32sp{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        # 在窗内的 1 单（10-05）+ 窗外（早于 start）的 1 单（10-01）
        self._make_done_task(
            code, h["id"], "0101", "王姐",
            datetime(2026, 10, 5, 10, 0, tzinfo=UTC),
        )
        self._make_done_task(
            code, h["id"], "0101", "王姐",
            datetime(2026, 10, 1, 10, 0, tzinfo=UTC),  # 窗前
        )

        r = client.get(
            f"/api/v1/tenants/{code}/analytics/housekeeping-performance",
            params={"hotel_id": h["id"], "start_date": "2026-10-03", "end_date": "2026-10-07"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # 窗口内只有 1 单（10-05），窗外 10-01 被 SQL 排除
        assert body["total_done"] == 1
        staff = {s["assignee"]: s for s in body["staff"]}
        assert "王姐" in staff
        assert staff["王姐"]["done_count"] == 1
        # 触顶字段：单店聚合 < 5000，truncated 应为 False
        assert body.get("truncated") is False

    def test_end_date_inclusive(self, client: TestClient) -> None:
        """end_date 含当天全天（exclusive 下界为次日 00:00）。"""
        code = f"m32sp2{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        # end_date 当天 23:30 的工单应被纳入
        self._make_done_task(
            code, h["id"], "0101", "王姐",
            datetime(2026, 10, 7, 23, 30, tzinfo=UTC),
        )

        r = client.get(
            f"/api/v1/tenants/{code}/analytics/housekeeping-performance",
            params={"hotel_id": h["id"], "start_date": "2026-10-07", "end_date": "2026-10-07"},
        )
        assert r.status_code == 200
        assert r.json()["total_done"] == 1

    def test_staff_aggregation_correct(self, client: TestClient) -> None:
        """多员工聚合：done_count / avg_minutes 与手工计算一致。"""
        code = f"m32sp3{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        # 王姐 2 单（耗时 30 分钟），李姐 1 单（耗时 60 分钟）
        # 用 hours 偏移避免 minute 60 触发 ValueError
        self._make_done_task(
            code, h["id"], "0101", "王姐",
            datetime(2026, 10, 5, 10, 0, tzinfo=UTC),
        )
        self._make_done_task(
            code, h["id"], "0101", "王姐",
            datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
        )
        self._make_done_task(
            code, h["id"], "0101", "李姐",
            datetime(2026, 10, 5, 14, 0, tzinfo=UTC),
        )

        r = client.get(
            f"/api/v1/tenants/{code}/analytics/housekeeping-performance",
            params={"hotel_id": h["id"], "start_date": "2026-10-01", "end_date": "2026-10-31"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total_done"] == 3
        staff = {s["assignee"]: s for s in body["staff"]}
        assert staff["王姐"]["done_count"] == 2
        assert staff["王姐"]["avg_minutes"] == 30.0
        assert staff["李姐"]["done_count"] == 1
        # 王姐 done_count 更高 → 排序在前
        assert body["staff"][0]["assignee"] == "王姐"


# =========================================================================
# 4. housekeeping.overdue_count：SELECT COUNT(*) SQL 下推
# =========================================================================


class TestOverdueCountSqlPushdown:
    """overdue_count：SQL COUNT(*) + due_at < now()（避 deprecation）。"""

    def _make_pending_task(
        self,
        tenant_code: str,
        hotel_id: int,
        room_no: str,
        due_at: datetime | None,
        status: str = "PENDING",
    ) -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.db.session import get_engine
        from app.models import HousekeepingTask

        async def _seed() -> None:
            sf = async_sessionmaker(get_engine(), expire_on_commit=False)
            async with sf() as s:
                s.add(
                    HousekeepingTask(
                        tenant_id=tenant_code,
                        hotel_id=hotel_id,
                        room_no=room_no,
                        task_type="MAINTENANCE",
                        status=status,
                        assignee="staff",
                        due_at=due_at,
                    )
                )
                await s.commit()

        asyncio.run(_seed())

    def test_overdue_counts_only_past_due_pending_or_assigned(self, client: TestClient) -> None:
        """只统计「PENDING/ASSIGNED + due_at 已过」的工单；DONE/CANCELLED 与未来 due_at 不计。"""
        code = f"m32od{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=2)

        # 应计入：PENDING + 过去 due_at
        self._make_pending_task(code, h["id"], "0101", past, status="PENDING")
        # 应计入：ASSIGNED + 过去 due_at
        self._make_pending_task(code, h["id"], "0101", past, status="ASSIGNED")
        # 不应计入：PENDING + 未来 due_at
        self._make_pending_task(code, h["id"], "0101", future, status="PENDING")
        # 不应计入：PENDING + due_at=None
        self._make_pending_task(code, h["id"], "0101", None, status="PENDING")
        # 不应计入：DONE（已结束）+ 过去 due_at
        self._make_pending_task(code, h["id"], "0101", past, status="DONE")
        # 不应计入：CANCELLED + 过去 due_at
        self._make_pending_task(code, h["id"], "0101", past, status="CANCELLED")

        # overdue_count 没有公开 API 端点，直接调服务
        from app.db.session import get_session
        from app.services.housekeeping_service import HousekeepingService

        async def _call_svc() -> int:
            async for s in get_session():
                return await HousekeepingService(s).overdue_count(code, h["id"])

        n = asyncio.run(_call_svc())
        # 应只计 2（PENDING+过去、ASSIGNED+过去）
        assert n == 2

    def test_overdue_count_zero_when_empty(self, client: TestClient) -> None:
        """无任何工单 → 计数为 0（SQL COUNT(*) 无匹配返 0，不抛异常）。"""
        code = f"m32od2{_uuid.uuid4().hex[:6]}"
        t, h, _ = _seed_basic(client, code)

        from app.db.session import get_session
        from app.services.housekeeping_service import HousekeepingService

        async def _call_svc() -> int:
            async for s in get_session():
                return await HousekeepingService(s).overdue_count(code, h["id"])

        n = asyncio.run(_call_svc())
        assert n == 0