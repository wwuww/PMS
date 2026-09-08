"""M15 收益管理测试：需求指数、规则化调价、周末因子、竞品对标、规则读写。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_engine
from app.models import DailyReport
from app.services.yield_service import YieldService


def _recent_dates(n: int) -> list[str]:
    today = datetime.now()
    return [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


@pytest.fixture()
def tenant_id() -> str:
    return "yield_tenant"


@pytest.fixture()
def setup(client, tenant_id):  # noqa: ANN001
    """建租户（M15 端点不校验酒店存在，直接用固定 hotel_id 并直写 DailyReport）。

    注：create_hotel 路由的 tenant_id 为 int 类型，与字符串 code 不一致；
    调价建议服务仅依赖 DailyReport 历史出租率，故无需经该端点建酒店。
    """
    client.post("/api/v1/tenants", json={"code": tenant_id, "name": "Yield Tenant"})
    return 1


def _seed_daily_reports(tenant_id: str, hotel_id: int, occ_values: list[int]) -> None:
    """直接写入 DailyReport 历史出租率（近 window_days 内）。"""
    engine = get_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _run() -> None:
        async with factory() as session:
            for date, occ in zip(_recent_dates(len(occ_values)), occ_values):
                session.add(
                    DailyReport(
                        tenant_id=tenant_id,
                        hotel_id=hotel_id,
                        business_date=date,
                        occupied_rooms=occ,
                        total_rooms=100,
                        occ_pct=occ,
                    )
                )
            await session.commit()

    asyncio.run(_run())


def test_high_occupancy_recommends_uplift(client, tenant_id, setup):  # noqa: ANN001
    """高出租率（>阈值）→ 建议价高于基价且上调。"""
    hotel_id = setup
    _seed_daily_reports(tenant_id, hotel_id, [95, 92, 96])
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/yield/pricing/recommend",
        json={
            "hotel_id": hotel_id,
            "business_date": "2026-09-10",  # 周四，非周末
            "base_price_cents": 30000,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["recommended_price_cents"] > 30000
    assert data["adjustment_bps"] > 0
    assert any("出租率高" in r for r in data["rationale"])


def test_low_occupancy_recommends_discount(client, tenant_id, setup):  # noqa: ANN001
    """低出租率（<阈值）→ 建议价低于基价且下调。"""
    hotel_id = setup
    _seed_daily_reports(tenant_id, hotel_id, [30, 35, 28])
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/yield/pricing/recommend",
        json={
            "hotel_id": hotel_id,
            "business_date": "2026-09-09",  # 周三，非周末，隔离需求侧折扣
            "base_price_cents": 30000,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["recommended_price_cents"] < 30000
    assert data["adjustment_bps"] < 0
    assert any("出租率低" in r for r in data["rationale"])


def test_weekend_peak_adds_uplift(client, tenant_id, setup):  # noqa: ANN001
    """中性出租率 + 周六高峰 → 叠加周末上调。"""
    hotel_id = setup
    _seed_daily_reports(tenant_id, hotel_id, [60, 62, 58])
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/yield/pricing/recommend",
        json={
            "hotel_id": hotel_id,
            "business_date": "2026-09-05",  # 周六
            "base_price_cents": 30000,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["recommended_price_cents"] == 31500  # 30000 * 1.05
    assert any("周末" in r for r in data["rationale"])


def test_competitor_undercut(client, tenant_id, setup):  # noqa: ANN001
    """高出租率触发上调，但竞品 undercut 策略将建议价压到竞品 97% 以下。"""
    hotel_id = setup
    _seed_daily_reports(tenant_id, hotel_id, [95, 94, 96])
    client.put(
        f"/api/v1/tenants/{tenant_id}/yield/rules",
        json={"competitor_strategy": "undercut", "competitor_undercut_bps": 300},
    )
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/yield/pricing/recommend",
        json={
            "hotel_id": hotel_id,
            "business_date": "2026-09-10",
            "base_price_cents": 30000,
            "competitor_price_cents": 25000,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    # demand_price ~ 33000，cap = 25000*0.97 = 24250 → 建议价被压到 24250
    assert data["recommended_price_cents"] == 24250
    assert any("undercut" in r for r in data["rationale"])


def test_rule_update_and_get(client, tenant_id, setup):  # noqa: ANN001
    """规则读写：PUT 后 GET 反映最新值。"""
    resp = client.put(
        f"/api/v1/tenants/{tenant_id}/yield/rules",
        json={
            "competitor_strategy": "match",
            "max_uplift_bps": 2000,
            "high_occ_threshold": 90,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["competitor_strategy"] == "match"
    assert resp.json()["max_uplift_bps"] == 2000

    resp = client.get(f"/api/v1/tenants/{tenant_id}/yield/rules")
    assert resp.status_code == 200
    assert resp.json()["competitor_strategy"] == "match"
    assert resp.json()["high_occ_threshold"] == 90


def test_recommendation_list(client, tenant_id, setup):  # noqa: ANN001
    """生成的建议可经列表接口查询。"""
    hotel_id = setup
    _seed_daily_reports(tenant_id, hotel_id, [70, 72, 68])
    client.post(
        f"/api/v1/tenants/{tenant_id}/yield/pricing/recommend",
        json={
            "hotel_id": hotel_id,
            "business_date": "2026-09-10",
            "base_price_cents": 30000,
        },
    )
    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/yield/pricing/recommendations",
        params={"hotel_id": hotel_id},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    # 响应 id 为字符串（雪花 ID），与入参 int 比较需同类型
    assert str(rows[0]["hotel_id"]) == str(hotel_id)


def test_recommend_pushes_notification(client, tenant_id, setup):  # noqa: ANN001
    """② 生成收益建议即向通知中心推送（点击深链直达建议详情）。"""
    hotel_id = setup
    _seed_daily_reports(tenant_id, hotel_id, [70, 72, 68])
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/yield/pricing/recommend",
        json={"hotel_id": hotel_id, "business_date": "2026-09-10", "base_price_cents": 30000},
    )
    rec_id = resp.json()["id"]
    notifs = client.get(f"/api/v1/tenants/{tenant_id}/notifications").json()
    recs = [n for n in notifs if n["ref_type"] == "yield_recommendation"]
    assert len(recs) == 1
    assert recs[0]["ref_id"] == str(rec_id)
    assert recs[0]["link"] == f"/yield?rec={rec_id}"
