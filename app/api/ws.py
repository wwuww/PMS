"""WebSocket 房态订阅端点（Sprint 1 验收：房态事件可订阅）。

连接: ws://host/ws/rooms?tenant_id=xxx&token=<登录会话 token>
鉴权（M18-3）：必须携带有效登录会话（与 HTTP 端同一套 LoginSession 校验），
无效连接立即以 4401 关闭；订阅后仅推送该租户事件（多租户隔离）。
S2 演进: 独立连接网关（dev-plan 2.2 扇出拓扑），本端点逻辑平移。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.events.base import DomainEvent
from app.events.bus import QueuedSubscriber, event_bus
from app.models.rbac import Role, UserRole
from app.services.notification_service import ROLE_TAG_MAP, recipient_tags_for_roles

logger = logging.getLogger(__name__)
router = APIRouter()

ROOM_TOPIC = "room.room.state_changed"
NOTIF_TOPIC = "notification.pushed"
WS_UNAUTHORIZED = 4401


def notification_matches(user_tags: set[str], recipients: list[str], muted: bool) -> bool:
    """⑤ 实时路由判定：用户标签与通知接收人存在交集、且非静音，才实时下发。"""
    if muted:
        return False
    if not recipients:
        return False  # ④ 空 recipients=不推送任何人
    return bool(user_tags & set(recipients))


async def _authorize(tenant_id: str, token: str) -> bool:
    """校验 WS 订阅者会话（与 HTTP require_auth 同一套 LoginSession）。"""
    if not tenant_id or not token:
        return False
    from app.db import session as db_session  # noqa: PLC0415
    from app.services.rbac_service import RbacService  # noqa: PLC0415

    db_session.get_engine()
    factory = db_session._session_factory  # noqa: SLF001 与 main.py 同一访问约定
    if factory is None:
        return False
    async with factory() as session:
        sess = await RbacService(session).get_session(tenant_id, token)
        return sess is not None


@router.websocket("/ws/rooms")
async def subscribe_room_events(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "")
    tenant_id = websocket.query_params.get("tenant_id", "")

    await websocket.accept()

    # M18-3：WebSocket 强制鉴权（此前任何连接都可订阅，属安全缺口）
    if not await _authorize(tenant_id, token):
        await websocket.send_json({"type": "error", "detail": "未授权的 WebSocket 订阅"})
        await websocket.close(code=WS_UNAUTHORIZED)
        logger.warning("房态订阅拒绝（无效会话）: tenant=%s", tenant_id)
        return

    subscriber = QueuedSubscriber()
    unsubscribe = event_bus.subscribe(ROOM_TOPIC, subscriber)

    try:
        await websocket.send_json({"type": "subscribed", "topic": ROOM_TOPIC})
        while True:
            event: DomainEvent = await subscriber.queue.get()
            if tenant_id and event.tenant_id != tenant_id:
                continue  # 多租户隔离：不跨租户推送
            await websocket.send_json({"type": "event", "data": event.payload()})
    except WebSocketDisconnect:
        logger.info("房态订阅断开: tenant=%s", tenant_id)
    finally:
        unsubscribe()
    # 让出控制权，避免竞态
    await asyncio.sleep(0)


async def _resolve_user_tags(tenant_id: str, token: str) -> set[str]:
    """按登录会话解析用户角色档位，映射为通知接收标签集合（用于 WS 实时路由）。

    鉴权失败或无角色绑定返回空集（仅能收到租户级全员推送，当前无此类通知）。
    """
    from app.db import session as db_session  # noqa: PLC0415
    from app.services.rbac_service import RbacService  # noqa: PLC0415

    factory = db_session._session_factory  # noqa: SLF001 与 main.py 同一访问约定
    if factory is None:
        db_session.get_engine()
        factory = db_session._session_factory
    if factory is None:
        return set()
    async with factory() as session:
        rbac = RbacService(session)
        sess = await rbac.get_session(tenant_id, token)
        if sess is None:
            return set()
        bindings = await rbac.list_user_roles(tenant_id, sess.user_id)
        if not bindings:
            return set()
        role_ids = [b.role_id for b in bindings]
        res = await session.execute(
            select(Role.level).where(
                Role.tenant_id == tenant_id, Role.id.in_(role_ids)
            )
        )
        levels = set(res.scalars())
    return recipient_tags_for_roles(levels)


@router.websocket("/ws/notifications")
async def subscribe_notifications(websocket: WebSocket) -> None:
    """⑤ 通知实时订阅端点：按连接用户的 RBAC 角色做 recipients 路由扇出。

    连接: ws://host/ws/notifications?tenant_id=xxx&token=<登录会话 token>
    鉴权同 /ws/rooms（M18-3 强制会话）；订阅后仅推送命中本人角色且非静音的租户内通知。
    """
    token = websocket.query_params.get("token", "")
    tenant_id = websocket.query_params.get("tenant_id", "")

    await websocket.accept()

    if not await _authorize(tenant_id, token):
        await websocket.send_json({"type": "error", "detail": "未授权的 WebSocket 订阅"})
        await websocket.close(code=WS_UNAUTHORIZED)
        logger.warning("通知订阅拒绝（无效会话）: tenant=%s", tenant_id)
        return

    user_tags = await _resolve_user_tags(tenant_id, token)

    subscriber = QueuedSubscriber(maxsize=500)
    unsubscribe = event_bus.subscribe(NOTIF_TOPIC, subscriber)

    try:
        await websocket.send_json(
            {"type": "subscribed", "topic": NOTIF_TOPIC, "tags": sorted(user_tags)}
        )
        while True:
            event: DomainEvent = await subscriber.queue.get()
            if event.tenant_id != tenant_id:
                continue  # 多租户隔离：不跨租户推送
            payload = event.payload()
            recipients = list(payload.get("recipients") or [])
            muted = bool(payload.get("muted"))
            if not notification_matches(user_tags, recipients, muted):
                continue  # 仅下发命中本人角色且非静音的通知
            await websocket.send_json({"type": "notification", "data": payload})
    except WebSocketDisconnect:
        logger.info("通知订阅断开: tenant=%s tags=%s", tenant_id, sorted(user_tags))
    finally:
        unsubscribe()
