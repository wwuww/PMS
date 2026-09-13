"""共享测试 fixture：每个测试独立 SQLite，隔离状态。

鉴权旁路（Sprint 14）
--------------------
M8-3 起全量业务路由强制鉴权：``require_auth``（认证层，无会话 401）+ 敏感路由
``require_perm``（授权层，缺权限 403）。既有功能测试均不带登录会话，整体被拦截。

本模块用 autouse fixture 以 FastAPI 标准机制 ``app.dependency_overrides`` 覆写
``require_auth``，语义为「该租户默认管理员已登录」：返回带真实 ``user_id`` 的会话对象，
因此 ``require_perm`` 授权层仍走真实 RBAC 校验（管理员拥有全部权限点），
功能测试聚焦业务、又不掩盖授权逻辑。

验证鉴权本身的用例用 ``@pytest.mark.auth`` 显式退出旁路。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    from app.core.config import get_settings
    from app.db import session as db_session

    monkeypatch.setenv("PMS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    db_session.reset_engine()
    with TestClient(app) as tc:
        yield tc
    get_settings.cache_clear()
    db_session.reset_engine()


async def _seed_admin_committed(tenant_id: str):  # noqa: ANN202
    """在独立会话中播种默认管理员并**立即提交**（M30 性能修复）。

    ``RbacService.seed_default_admin`` 只 flush 不 commit。若直接复用业务会话播种，
    请求结束时会话回滚 → 下个请求 admin 又不存在 → **每个请求都重新播种一次**
    （含 bcrypt 口令哈希，实测约 60ms/次）。

    后果有二：① 性能基线凭空 +60ms 固定开销，掩盖真实业务耗时；
    ② 整个测试套件每个请求多付 60ms。

    这里改用独立会话播种并提交：既让 admin 持久化（后续请求直接命中），
    又不触碰业务会话事务语义（业务测试仍可依赖回滚做隔离）。

    ⚠️ 必须先 ``seed_default_roles``：本旁路会把「无角色绑定」的 admin 交给
    ``require_perm``，缺角色即缺全部权限点 → 需要权限的接口全 403。
    历史用例多经 ``/api/v1/tenants`` 开通流程隐式播种角色，掩盖了此问题；
    自建独立库的用例（如 test_ota_mappings）会直接踩中。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.session import get_engine
    from app.services.rbac_service import RbacService

    seed_session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with seed_session_factory() as seed_session:
        svc = RbacService(seed_session)
        await svc.seed_default_roles(tenant_id)
        await seed_session.flush()
        user = await svc.seed_default_admin(tenant_id)
        await seed_session.commit()
        return user


@pytest.fixture(autouse=True)
def auth_bypass(request):  # noqa: ANN001, ANN201
    """将请求视为「该租户默认管理员已登录」，除非用例标记 ``@pytest.mark.auth``。"""
    if request.node.get_closest_marker("auth") is not None:
        yield
        return

    from app.api.routes import get_session, require_auth, resolve_tenant_id
    from app.services.rbac_service import RbacService

    async def _as_admin(  # noqa: ANN202
        request: Request, session: AsyncSession = Depends(get_session)
    ):
        # 复用生产同一套租户解析逻辑，避免测试与实现漂移
        tenant_id = await resolve_tenant_id(request.url.path, session)
        if not tenant_id:
            return None  # 无法识别租户的路径交由白名单/公开端点处理

        svc = RbacService(session)
        user = await svc.get_user(tenant_id, "admin")
        if user is None:
            user = await _seed_admin_committed(tenant_id)
        return SimpleNamespace(
            id=-1, user_id=user.id, tenant_id=tenant_id, token="test-bypass-token"
        )

    app.dependency_overrides[require_auth] = _as_admin
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_auth, None)
