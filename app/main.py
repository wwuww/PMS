"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router, require_auth
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.db import session as db_session
from app.events.base import DomainEvent
from app.events.bus import event_bus
from app.infra.ratelimit import RateLimitMiddleware
from app.services.openapi_service import OpenApiService


async def _dispatch_webhooks(event: DomainEvent) -> None:
    """M18：全局 Webhook 投递器，订阅所有领域事件并分发给第三方应用。

    注意：必须经由 db_session 模块访问 _session_factory，否则导入时的
    绑定会因 reset_engine()/get_engine() 重新赋值而失效（始终保持旧值 None）。
    """
    factory = db_session._session_factory
    if factory is None:
        db_session.get_engine()
        factory = db_session._session_factory
    if factory is None:
        return
    async with factory() as session:
        await OpenApiService(session).deliver_event(event)


_webhook_subscribed = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _webhook_subscribed
    await db_session.init_db()  # 开发模式建表；生产走 Alembic
    # M18 开放 API 平台：订阅全部领域事件并尝试 Webhook 投递（仅注册一次，避免测试重复）
    if not _webhook_subscribed:
        event_bus.subscribe("#", _dispatch_webhooks)
        _webhook_subscribed = True
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    # 前端开发跨端口调用（Vite 默认 5173）所需 CORS；生产应在网关层收敛来源。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # M18-2 接口限流：默认关闭（PMS_RATE_LIMIT_ENABLED=true 开启），auth 端点单独收紧
    app.add_middleware(RateLimitMiddleware)
    # M8-3 强制会话鉴权：挂载到全部业务路由（公开端点见 require_auth 白名单）
    app.include_router(
        api_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_auth)]
    )
    app.include_router(ws_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
