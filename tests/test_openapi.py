"""M18 开放 API 平台测试：应用注册、API Key、Webhook 订阅与事件投递。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_engine
from app.events.base import RoomStateChanged
from app.events.bus import event_bus
from app.services.openapi_service import OpenApiService


@pytest.fixture()
def tenant_id() -> str:
    return "openapi_tenant"


@pytest.fixture()
def app_base(client, tenant_id):  # noqa: ANN001
    """创建测试租户与应用，供后续用例复用。"""
    client.post("/api/v1/tenants", json={"code": tenant_id, "name": "OpenAPI Tenant"})
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/apps",
        json={
            "app_code": "channel_sync",
            "name": "渠道同步助手",
            "callback_url": "https://example.com/callback",
            "events_subscribed": ["room.room.state_changed", "booking.state_changed"],
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_register_and_list_apps(client, tenant_id, app_base):  # noqa: ANN001
    """应用注册与列表。"""
    assert app_base["app_code"] == "channel_sync"
    assert app_base["status"] == "active"
    assert "room.room.state_changed" in app_base["events_subscribed"]

    resp = client.get(f"/api/v1/tenants/{tenant_id}/openapi/apps")
    assert resp.status_code == 200
    apps = resp.json()
    assert len(apps) == 1
    assert apps[0]["name"] == "渠道同步助手"


def test_register_duplicate_app_code(client, tenant_id, app_base):  # noqa: ANN001
    """同一租户内 app_code 唯一。"""
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/apps",
        json={"app_code": "channel_sync", "name": "重复应用"},
    )
    assert resp.status_code == 409


def test_create_list_revoke_keys(client, tenant_id, app_base):  # noqa: ANN001
    """API Key 创建、列表、吊销。"""
    app_id = app_base["id"]
    resp = client.post(f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys")
    assert resp.status_code == 201
    key_data = resp.json()
    assert key_data["secret"].startswith("pms_")
    assert key_data["key"]["key_mask"] == key_data["secret"][-4:]
    assert key_data["key"]["status"] == "active"

    # 列表
    resp = client.get(f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) == 1

    # 吊销
    key_id = key_data["key"]["id"]
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys/{key_id}/revoke"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


def test_verify_key_valid_and_invalid(client, tenant_id, app_base):  # noqa: ANN001
    """API Key 校验：有效 key 通过，吊销/错误 key 拒绝。"""
    app_id = app_base["id"]
    resp = client.post(f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys")
    secret = resp.json()["secret"]

    # 有效
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/verify-key", json={"api_key": secret}
    )
    assert resp.status_code == 200
    assert resp.json()["app_code"] == "channel_sync"

    # 无效
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/verify-key", json={"api_key": "pms_invalid"}
    )
    assert resp.status_code == 401

    # 吊销后无效
    key_id = client.get(f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys").json()[0]["id"]
    client.post(f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys/{key_id}/revoke")
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/verify-key", json={"api_key": secret}
    )
    assert resp.status_code == 401


def test_subscribe_and_test_webhook(client, tenant_id, app_base, monkeypatch):  # noqa: ANN001
    """Webhook 订阅与测试投递，验证 HMAC 签名头。"""
    app_id = app_base["id"]
    captured: list[dict[str, Any]] = []

    async def mock_post(url: str, body: str, headers: dict[str, str]) -> tuple[int, str]:
        captured.append({"url": url, "body": body, "headers": headers})
        return 200, "ok"

    # 使用 monkeypatch 让 service 的默认投递走 mock（ lifespan 注册的全局 handler 不会触发此测试）
    monkeypatch.setattr(OpenApiService, "_default_http_post", staticmethod(mock_post))

    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/webhooks",
        json={
            "app_id": app_id,
            "topic": "room.room.state_changed",
            "endpoint_url": "https://receiver.example.com/webhook",
        },
    )
    assert resp.status_code == 201
    sub = resp.json()
    assert sub["topic"] == "room.room.state_changed"
    assert sub["status"] == "active"

    # 手动测试投递
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/webhooks/{sub['id']}/test"
    )
    assert resp.status_code == 200
    delivery = resp.json()
    assert delivery["event_topic"] == "openapi.test_event"
    assert delivery["status"] == "success"

    assert len(captured) == 1
    assert captured[0]["headers"]["X-PMS-Topic"] == "openapi.test_event"
    assert "X-PMS-Signature" in captured[0]["headers"]


async def _async_session() -> AsyncSession:
    engine = get_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        return session


@pytest.mark.asyncio
async def test_deliver_event_matches_topic_and_wildcard(client, tenant_id, app_base):  # noqa: ANN001
    """OpenApiService.deliver_event 按 topic 精确匹配或 * 通配符匹配。"""
    from contextlib import asynccontextmanager  # noqa: PLC0415

    app_id = app_base["id"]
    captured: list[dict[str, Any]] = []

    async def mock_post(url: str, body: str, headers: dict[str, str]) -> tuple[int, str]:
        captured.append({"url": url, "body": json.loads(body), "headers": headers})
        return 200, "ok"

    engine = get_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def session_scope():
        async with factory() as session:
            yield session

    async with session_scope() as session:
        svc = OpenApiService(session, http_post=mock_post)
        # 精确订阅
        await svc.subscribe(
            tenant_id, app_id, "room.room.state_changed", "https://a.example.com/hook"
        )
        # 通配订阅
        await svc.subscribe(
            tenant_id, app_id, "*", "https://b.example.com/hook"
        )
        await session.commit()

    event = RoomStateChanged(
        tenant_id=tenant_id,
        room_id=1,
        room_no="101",
        from_state="VACANT_CLEAN",
        to_state="OCCUPIED",
        trigger="check_in",
        operator="front_desk",
    )

    async with session_scope() as session:
        svc = OpenApiService(session, http_post=mock_post)
        result = await svc.deliver_event(event)
        await session.commit()

    # 精确 + 通配两条匹配，均投递成功
    assert result["matched"] == 2
    assert result["delivered"] == 2
    urls = {c["url"] for c in captured}
    assert "https://a.example.com/hook" in urls
    assert "https://b.example.com/hook" in urls


@pytest.mark.asyncio
async def test_event_bus_dispatches_to_webhooks(client, tenant_id, app_base, monkeypatch):  # noqa: ANN001
    """事件总线发布领域事件后，Webhook 订阅者应被触发并记录投递。"""
    app_id = app_base["id"]
    captured: list[dict[str, Any]] = []

    async def mock_post(url: str, body: str, headers: dict[str, str]) -> tuple[int, str]:
        captured.append({"url": url, "body": json.loads(body), "headers": headers})
        return 200, "ok"

    monkeypatch.setattr(OpenApiService, "_default_http_post", staticmethod(mock_post))

    # 通过 HTTP 创建订阅
    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/webhooks",
        json={
            "app_id": app_id,
            "topic": "room.room.state_changed",
            "endpoint_url": "https://bus.example.com/hook",
        },
    )
    assert resp.status_code == 201

    event = RoomStateChanged(
        tenant_id=tenant_id,
        room_id=1,
        room_no="101",
        from_state="VACANT_CLEAN",
        to_state="OCCUPIED",
        trigger="check_in",
        operator="front_desk",
    )
    await event_bus.publish(event)

    assert len(captured) == 1
    assert captured[0]["url"] == "https://bus.example.com/hook"
    assert captured[0]["body"]["topic"] == "room.room.state_changed"
    assert captured[0]["headers"]["X-PMS-Topic"] == "room.room.state_changed"
    assert "X-PMS-Signature" in captured[0]["headers"]


# ---------- 第三方只读开放接口（API-Key 鉴权） ----------


@pytest.fixture()
def api_key(client, tenant_id, app_base):  # noqa: ANN001
    """为测试应用创建一把 API Key，返回明文 secret（仅此一次可见）。"""
    app_id = app_base["id"]
    resp = client.post(f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys")
    assert resp.status_code == 201
    return resp.json()["secret"]


@pytest.fixture()
def seeded(client, tenant_id):  # noqa: ANN001
    """在测试租户下播种门店/房型/房间/预订，供只读接口断言。"""
    # 确保租户存在（部分用例不依赖 app_base，需自建）
    client.post("/api/v1/tenants", json={"code": tenant_id, "name": "OpenAPI Tenant"})
    h = client.post(
        f"/api/v1/tenants/{tenant_id}/hotels", json={"code": "H1", "name": "一号店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{tenant_id}/room-types",
        json={"code": "STD", "name": "标准间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0101"}],
    )
    bk = client.post(
        f"/api/v1/tenants/{tenant_id}/bookings",
        json={
            "hotel_id": int(h["id"]),
            "room_type_id": int(rt["id"]),
            "guest_name": "渠道客",
            "guest_phone": "13800000555",
            "check_in_date": "2026-09-20",
            "check_out_date": "2026-09-22",
        },
    ).json()
    return {
        "hotel_id": int(h["id"]),
        "room_type_id": int(rt["id"]),
        "booking_id": bk["id"],
    }


def test_openapi_read_hotels_ok(client, tenant_id, api_key, seeded):  # noqa: ANN001
    """持有效 API Key 可读门店列表。"""
    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/openapi/v1/hotels",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "一号店"


def test_openapi_read_requires_key(client, tenant_id, seeded):  # noqa: ANN001
    """无 Bearer 头 → 401。"""
    resp = client.get(f"/api/v1/tenants/{tenant_id}/openapi/v1/hotels")
    assert resp.status_code == 401


def test_openapi_read_rejects_invalid_key(client, tenant_id, seeded):  # noqa: ANN001
    """非法 Key → 401。"""
    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/openapi/v1/hotels",
        headers={"Authorization": "Bearer pms_invalid"},
    )
    assert resp.status_code == 401


def test_openapi_read_rejects_revoked_key(client, tenant_id, app_base, api_key, seeded):  # noqa: ANN001
    """吊销后的 Key → 401。"""
    app_id = app_base["id"]
    key_id = client.get(
        f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys"
    ).json()[0]["id"]
    client.post(
        f"/api/v1/tenants/{tenant_id}/openapi/apps/{app_id}/keys/{key_id}/revoke"
    )
    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/openapi/v1/hotels",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 401


def test_openapi_read_rooms_bookings_availability_board(client, tenant_id, api_key, seeded):  # noqa: ANN001
    """持 Key 可读取房间/预订/房量/夜审看板。"""
    hid = seeded["hotel_id"]
    rtid = seeded["room_type_id"]

    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/openapi/v1/hotels/{hid}/rooms",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    assert resp.json()[0]["room_no"] == "0101"

    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/openapi/v1/bookings",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/openapi/v1/availability"
        f"?room_type_id={rtid}&date=2026-09-20",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)

    resp = client.get(
        f"/api/v1/tenants/{tenant_id}/openapi/v1/night-audit/board",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    assert "hotel_count" in resp.json()
