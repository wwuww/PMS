"""通知中心点击跳转深链（M10-4 增强）。

覆盖：
1. build_link 按 ref_type 推导前端路由（含未知类型/缺 ref_id 的降级）；
2. 列表返回 link，点击 read 幂等且返回 link；
3. 一键已读（read-all，幂等）与未读计数（unread-count，顶栏角标）；
4. unread_only 过滤、消息不存在 404；
5. 夜审日报推送自带 business_date 深链。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_engine
from app.models import DailyReport
from app.services.notification_service import NotificationService, build_link


@pytest.fixture()
def tenant_id() -> str:
    return "notif_tenant"


@pytest.fixture()
def setup(client: TestClient, tenant_id: str) -> int:
    """建租户 + 门店，返回 hotel_id（建门店路由的 tenant_id 为整型主键）。"""
    t = client.post("/api/v1/tenants", json={"code": tenant_id, "name": "通知测试租户"}).json()
    h = client.post(
        f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "测试店"}
    ).json()
    return int(h["id"])


def _run(coro):  # noqa: ANN001, ANN202
    return asyncio.run(coro)


def _push(tenant_id: str, hotel_id: int, items: list[dict]) -> None:
    """绕过 HTTP 直接落库消息（等价于各业务点的 NotificationService.push）。"""
    factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

    async def _go() -> None:
        async with factory() as session:
            for it in items:
                await NotificationService(session).push(tenant_id=tenant_id, hotel_id=hotel_id, **it)
            await session.commit()

    _run(_go())


def _seed(tenant_id: str, hotel_id: int) -> None:
    _push(
        tenant_id,
        hotel_id,
        [
            {
                "title": "营业日报 2026-09-03",
                "body": "总营收 120000 分",
                "ref_type": "daily_report",
                "ref_id": 1,
            },
            {
                "title": "AI客服转人工",
                "body": "客人张先生请求人工接入",
                "recipient": "front_desk",
                "ref_type": "chat_session",
                "ref_id": 7,
            },
            {"title": "系统公告", "body": "今晚 02:00 例行维护"},
        ],
    )


# ---------- 1. 深链推导 ----------


def test_build_link_by_ref_type() -> None:
    assert build_link("daily_report", 1) == "/reports?type=dashboard"
    assert build_link("chat_session", 7) == "/ai-chat?session=7"
    assert build_link("booking", 12) == "/bookings?booking=12"
    assert build_link("alert", 3) == "/alerts?alert=3"


def test_build_link_degrades_gracefully() -> None:
    """未知类型 / 缺 ref_id / 无 ref_type → 无深链，前端退化为仅标记已读。"""
    assert build_link("unknown_type", 1) is None
    assert build_link("chat_session", None) is None
    assert build_link(None, 1) is None


# ---------- 2. 列表与点击已读 ----------


def test_list_returns_link(client: TestClient, tenant_id: str, setup: int) -> None:
    _seed(tenant_id, setup)
    rows = client.get(f"/api/v1/tenants/{tenant_id}/notifications").json()
    assert len(rows) == 3
    by_title = {r["title"]: r for r in rows}
    assert by_title["营业日报 2026-09-03"]["link"] == "/reports?type=dashboard"
    assert by_title["AI客服转人工"]["link"] == "/ai-chat?session=7"
    assert by_title["系统公告"]["link"] is None
    assert all(r["read_at"] is None for r in rows)


def test_read_is_idempotent_and_returns_link(
    client: TestClient, tenant_id: str, setup: int
) -> None:
    _seed(tenant_id, setup)
    nid = client.get(f"/api/v1/tenants/{tenant_id}/notifications").json()[0]["id"]

    first = client.post(f"/api/v1/tenants/{tenant_id}/notifications/{nid}/read")
    assert first.status_code == 200
    read_at = first.json()["read_at"]
    assert read_at is not None
    assert "link" in first.json()

    # 重复点击（幂等）：read_at 不回退、状态仍为已读
    second = client.post(f"/api/v1/tenants/{tenant_id}/notifications/{nid}/read")
    assert second.status_code == 200
    assert second.json()["read_at"] == read_at


def test_read_not_found(client: TestClient, tenant_id: str, setup: int) -> None:
    resp = client.post(f"/api/v1/tenants/{tenant_id}/notifications/999999/read")
    assert resp.status_code == 404


# ---------- 3. 一键已读与未读计数 ----------


def test_read_all_and_unread_count(client: TestClient, tenant_id: str, setup: int) -> None:
    _seed(tenant_id, setup)
    count_url = f"/api/v1/tenants/{tenant_id}/notifications/unread-count"
    all_url = f"/api/v1/tenants/{tenant_id}/notifications/read-all"

    assert client.get(count_url).json()["unread"] == 3

    res = client.post(all_url)
    assert res.status_code == 200
    assert res.json()["updated"] == 3
    assert client.get(count_url).json()["unread"] == 0

    # 再次调用幂等：没有未读可更新
    assert client.post(all_url).json()["updated"] == 0


def test_unread_only_filter(client: TestClient, tenant_id: str, setup: int) -> None:
    _seed(tenant_id, setup)
    rows = client.get(f"/api/v1/tenants/{tenant_id}/notifications").json()
    client.post(f"/api/v1/tenants/{tenant_id}/notifications/{rows[0]['id']}/read")

    unread = client.get(
        f"/api/v1/tenants/{tenant_id}/notifications", params={"unread_only": True}
    ).json()
    assert len(unread) == 2
    assert all(r["read_at"] is None for r in unread)


# ---------- 4. 夜审日报自带营业日深链 ----------


def test_daily_report_notification_links_business_date(
    client: TestClient, tenant_id: str, setup: int
) -> None:
    factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

    async def _go() -> None:
        async with factory() as session:
            report = DailyReport(
                tenant_id=tenant_id,
                hotel_id=setup,
                business_date="2026-09-03",
                total_rooms=12,
                occupied_rooms=9,
                occ_pct=75,
                room_revenue=90000,
                total_revenue=95000,
                adr=10000,
            )
            session.add(report)
            await session.flush()
            await NotificationService(session).push_daily_report(report)
            await session.commit()

    _run(_go())

    rows = client.get(f"/api/v1/tenants/{tenant_id}/notifications").json()
    assert len(rows) == 1
    assert rows[0]["ref_type"] == "daily_report"
    assert rows[0]["link"] == "/reports?type=dashboard&date=2026-09-03"
    assert "2026-09-03" in rows[0]["body"]


def test_explicit_link_overrides_template(client: TestClient, tenant_id: str, setup: int) -> None:
    """调用方显式指定 link 时优先使用（不被 ref_type 模板覆盖）。"""
    _push(
        tenant_id,
        setup,
        [
            {
                "title": "自定义跳转",
                "body": "带指定落点",
                "ref_type": "booking",
                "ref_id": 5,
                "link": "/bookings?booking=5&tab=folio",
            }
        ],
    )
    row = client.get(f"/api/v1/tenants/{tenant_id}/notifications").json()[0]
    assert row["link"] == "/bookings?booking=5&tab=folio"
