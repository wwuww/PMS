"""M18 开放 API 平台服务：应用注册、API Key 鉴权、Webhook 订阅与事件投递。"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OpenApiApp, OpenApiKey, WebhookDelivery, WebhookSubscription

HttpPost = Callable[[str, dict[str, Any], dict[str, str]], Awaitable[tuple[int, str]]]


def _generate_api_key() -> str:
    """生成 32 字节 URL-safe 随机 API Key。"""
    return "pms_" + secrets.token_urlsafe(32)


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _sign_payload(secret: str, payload_bytes: bytes) -> str:
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


class OpenApiService:
    """开放 API 平台服务。

    默认使用 httpx 做外发投递；测试可注入 http_post 替代。
    """

    def __init__(
        self,
        session: AsyncSession,
        http_post: HttpPost | None = None,
    ) -> None:
        self.session = session
        self._http_post = http_post

    # ---- 应用管理 ----

    async def register_app(
        self,
        tenant_id: str,
        app_code: str,
        name: str,
        callback_url: str | None = None,
        events_subscribed: list[str] | None = None,
    ) -> OpenApiApp:
        exists = await self.session.execute(
            select(OpenApiApp).where(
                OpenApiApp.tenant_id == tenant_id, OpenApiApp.app_code == app_code
            )
        )
        if exists.scalar_one_or_none():
            raise ValueError("应用编码已存在")
        app = OpenApiApp(
            tenant_id=tenant_id,
            app_code=app_code,
            name=name,
            callback_url=callback_url,
            events_subscribed=events_subscribed or [],
        )
        self.session.add(app)
        await self.session.flush()
        await self.session.refresh(app)
        return app

    async def list_apps(self, tenant_id: str) -> list[OpenApiApp]:
        result = await self.session.execute(
            select(OpenApiApp).where(OpenApiApp.tenant_id == tenant_id)
        )
        return list(result.scalars())

    async def get_app(self, tenant_id: str, app_id: int) -> OpenApiApp | None:
        app = await self.session.get(OpenApiApp, app_id)
        if app and app.tenant_id == tenant_id:
            return app
        return None

    # ---- API Key 管理 ----

    async def create_key(self, app: OpenApiApp) -> tuple[OpenApiKey, str]:
        plaintext = _generate_api_key()
        key = OpenApiKey(
            app_id=app.id,
            key_hash=_hash_key(plaintext),
            key_mask=plaintext[-4:],
            status="active",
        )
        self.session.add(key)
        await self.session.flush()
        await self.session.refresh(key)
        return key, plaintext

    async def list_keys(self, app: OpenApiApp) -> list[OpenApiKey]:
        result = await self.session.execute(
            select(OpenApiKey).where(OpenApiKey.app_id == app.id)
        )
        return list(result.scalars())

    async def revoke_key(self, key_id: int) -> OpenApiKey:
        key = await self.session.get(OpenApiKey, key_id)
        if not key:
            raise ValueError("API Key 不存在")
        key.status = "revoked"
        key.revoked_at = datetime.now(UTC).isoformat()
        await self.session.flush()
        await self.session.refresh(key)
        return key

    async def verify_key(self, tenant_id: str, plaintext: str) -> OpenApiApp | None:
        """校验 API Key 并返回对应应用（仅 active）。"""
        if not plaintext.startswith("pms_"):
            return None
        key_hash = _hash_key(plaintext)
        result = await self.session.execute(
            select(OpenApiKey)
            .join(OpenApiApp, OpenApiApp.id == OpenApiKey.app_id)
            .where(
                OpenApiKey.key_hash == key_hash,
                OpenApiKey.status == "active",
                OpenApiApp.tenant_id == tenant_id,
                OpenApiApp.status == "active",
            )
        )
        key = result.scalar_one_or_none()
        if key is None:
            return None
        return await self.session.get(OpenApiApp, key.app_id)

    # ---- Webhook 订阅 ----

    async def subscribe(
        self,
        tenant_id: str,
        app_id: int,
        topic: str,
        endpoint_url: str,
        secret: str | None = None,
    ) -> WebhookSubscription:
        app = await self.get_app(tenant_id, app_id)
        if app is None:
            raise ValueError("应用不存在")
        if secret is None:
            secret = secrets.token_urlsafe(32)
        sub = WebhookSubscription(
            tenant_id=tenant_id,
            app_id=app_id,
            topic=topic,
            endpoint_url=endpoint_url,
            secret=secret,
            status="active",
        )
        self.session.add(sub)
        await self.session.flush()
        await self.session.refresh(sub)
        return sub

    async def list_subscriptions(
        self, tenant_id: str, app_id: int | None = None
    ) -> list[WebhookSubscription]:
        stmt = select(WebhookSubscription).where(WebhookSubscription.tenant_id == tenant_id)
        if app_id is not None:
            stmt = stmt.where(WebhookSubscription.app_id == app_id)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def pause_subscription(self, subscription_id: int) -> WebhookSubscription:
        sub = await self.session.get(WebhookSubscription, subscription_id)
        if not sub:
            raise ValueError("订阅不存在")
        sub.status = "paused"
        await self.session.flush()
        await self.session.refresh(sub)
        return sub

    # ---- 事件投递 ----

    async def deliver_event(self, event: Any) -> dict[str, Any]:
        """领域事件总线订阅入口：匹配活跃订阅并投递。"""
        topic = getattr(event, "topic", None)
        if topic is None:
            return {"matched": 0, "delivered": 0}
        payload = event.payload()
        payload_bytes = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")

        result = await self.session.execute(
            select(WebhookSubscription)
            .join(OpenApiApp, OpenApiApp.id == WebhookSubscription.app_id)
            .where(
                WebhookSubscription.tenant_id == event.tenant_id,
                WebhookSubscription.status == "active",
                OpenApiApp.status == "active",
            )
        )
        subs = list(result.scalars())
        matched = [s for s in subs if s.topic == topic or s.topic == "*"]

        delivered = 0
        for sub in matched:
            delivery = WebhookDelivery(
                subscription_id=sub.id,
                event_topic=topic,
                event_payload=payload_bytes.decode("utf-8"),
                status="pending",
            )
            self.session.add(delivery)
            await self.session.flush()
            ok = await self._deliver_one(sub, delivery, payload_bytes)
            if ok:
                delivered += 1
        await self.session.flush()
        return {"matched": len(matched), "delivered": delivered}

    async def test_webhook(
        self, tenant_id: str, subscription_id: int
    ) -> WebhookDelivery:
        """手动触发测试事件，验证 Webhook 可达性。"""
        sub = await self.session.get(WebhookSubscription, subscription_id)
        if not sub or sub.tenant_id != tenant_id:
            raise ValueError("订阅不存在")
        payload = {
            "topic": "openapi.test_event",
            "occurred_at": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "message": "This is a test event from PMS OpenAPI platform.",
        }
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        delivery = WebhookDelivery(
            subscription_id=sub.id,
            event_topic="openapi.test_event",
            event_payload=payload_bytes.decode("utf-8"),
            status="pending",
        )
        self.session.add(delivery)
        await self.session.flush()
        await self._deliver_one(sub, delivery, payload_bytes)
        await self.session.flush()
        await self.session.refresh(delivery)
        return delivery

    async def _deliver_one(
        self, sub: WebhookSubscription, delivery: WebhookDelivery, payload_bytes: bytes
    ) -> bool:
        signature = _sign_payload(sub.secret, payload_bytes)
        headers = {
            "Content-Type": "application/json",
            "X-PMS-Signature": signature,
            "X-PMS-Topic": delivery.event_topic,
        }
        post = self._http_post or self._default_http_post
        delivery.attempted_at = datetime.now(UTC).isoformat()
        try:
            http_status, response_body = await post(
                sub.endpoint_url, payload_bytes.decode("utf-8"), headers
            )
            delivery.http_status = http_status
            delivery.response_body = response_body[:2048] if response_body else None
            if 200 <= http_status < 300:
                delivery.status = "success"
                return True
            delivery.status = "failed"
            delivery.error_message = f"HTTP {http_status}"
        except Exception as exc:  # noqa: BLE001
            delivery.status = "failed"
            delivery.error_message = str(exc)[:512]
        return False

    @staticmethod
    async def _default_http_post(
        url: str, body_json: str, headers: dict[str, str]
    ) -> tuple[int, str]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for webhook delivery") from exc
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, content=body_json.encode("utf-8"), headers=headers)
            return response.status_code, response.text
