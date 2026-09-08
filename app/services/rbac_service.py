"""RBAC 服务（M8-1）与登录安全（M8-3）。

职责：
- 账号/角色/授权：创建用户、创建角色、绑定用户角色、列示；
- 租户开通时播种默认三档角色（管理员/门店经理/前台）；
- 登录鉴权：密码校验、失败锁定（5 次锁定 30 分钟）、生成会话；
- 权限解析：聚合用户全部角色权限，门店级角色仅对绑定门店生效。
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import (
    PWD_ALGO_ARGON2ID,
    PWD_ALGO_SHA256,
    ROLE_LEVEL_ADMIN,
    USER_STATUS_ACTIVE,
    USER_STATUS_DISABLED,
    USER_STATUS_LOCKED,
    LoginSession,
    RefreshToken,
    Role,
    User,
    UserRole,
    refresh_ttl,
    session_ttl,
)
from app.services.permissions import DEFAULT_ROLES

logger = logging.getLogger(__name__)


MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=30)

# 开发/测试默认 bootstrap 口令；生产（``PMS_ENV=prod``）必须显式设置环境变量
# ``PMS_BOOTSTRAP_ADMIN_PASSWORD``，否则会随机生成并写入日志。
_DEFAULT_DEV_BOOTSTRAP_PASSWORD = "admin123"


# ---------- 密码工具（M32.18 P0-3 加固） ----------
def _hash_legacy(password: str, salt: str) -> str:
    """历史算法：单次 SHA-256(salt+pwd)。仅用于透明升级校验，**不再用于创建新账号**。"""
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def _hash_argon2id(password: str) -> str:
    """新算法：argon2id（OWASP 推荐默认）。argon2 自身生成 salt 并编码进 hash 字符串。"""
    from argon2 import PasswordHasher  # 延迟导入，便于测试环境单独屏蔽

    return PasswordHasher().hash(password)


def _verify_argon2id(stored_hash: str, password: str) -> bool:
    from argon2 import PasswordHasher
    from argon2.exceptions import (
        InvalidHashError,
        VerificationError,
        VerifyMismatchError,
    )

    try:
        return PasswordHasher().verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:  # noqa: BLE001
        return False


def _new_salt() -> str:
    """保留字段 ``users.salt`` 兼容老 schema，argon2 用户也填一个 16 字节 hex 占位。"""
    return secrets.token_hex(16)


def _resolve_bootstrap_password() -> str:
    """解析默认管理员的初始口令。

    优先级：
      1. 环境变量 ``PMS_BOOTSTRAP_ADMIN_PASSWORD``（生产必须显式设置）；
      2. ``PMS_ENV=prod`` 但未设置 → 随机生成 24 字符强口令并日志告警；
      3. 其它（dev / test / 默认）→ 回退为 ``admin123``，日志警告一次。
    """
    env = os.environ.get("PMS_BOOTSTRAP_ADMIN_PASSWORD")
    if env:
        return env
    if os.environ.get("PMS_ENV", "").lower() == "prod":
        pwd = secrets.token_urlsafe(18)
        logger.critical(
            "[SECURITY] PMS_ENV=prod but PMS_BOOTSTRAP_ADMIN_PASSWORD is unset. "
            "Randomly generated one-shot bootstrap password: %s — deliver to admin NOW.",
            pwd,
        )
        return pwd
    logger.warning(
        "[SECURITY] PMS_BOOTSTRAP_ADMIN_PASSWORD is unset and PMS_ENV!=prod. "
        "Falling back to default bootstrap password 'admin123' (dev/test only). "
        "Set PMS_BOOTSTRAP_ADMIN_PASSWORD in production deployments.",
    )
    return _DEFAULT_DEV_BOOTSTRAP_PASSWORD


def verify_password(user: User, password: str) -> bool:
    """按 ``user.pwd_algo`` 分发校验。"""
    algo = getattr(user, "pwd_algo", None) or PWD_ALGO_SHA256
    if algo == PWD_ALGO_ARGON2ID:
        return _verify_argon2id(user.password_hash, password)
    # legacy: 历史 sha256(salt+pwd) 算法
    return _hash_legacy(password, user.salt) == user.password_hash


def maybe_upgrade_to_argon2id(user: User, password: str) -> bool:
    """登录成功后，若老算法则透明重哈希。返回是否修改了用户（需要 flush）。"""
    algo = getattr(user, "pwd_algo", None) or PWD_ALGO_SHA256
    if algo == PWD_ALGO_ARGON2ID:
        return False
    user.password_hash = _hash_argon2id(password)
    user.pwd_algo = PWD_ALGO_ARGON2ID
    return True


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite 不保存时区信息，返回 naive datetime；统一按 UTC 视为感知时间，避免比较报错。"""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


# ---------- 服务 ----------
class RbacService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ----- 播种默认角色（租户开通时调用） -----
    async def seed_default_roles(self, tenant_id: str) -> list[Role]:
        roles: list[Role] = []
        for name, level, hotel_scoped, perms in DEFAULT_ROLES:
            existing = await self.session.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.name == name)
            )
            if existing.scalar_one_or_none():
                continue
            role = Role(
                tenant_id=tenant_id,
                name=name,
                level=level,
                is_system=True,
                hotel_scoped=hotel_scoped,
                permissions=list(perms),
            )
            self.session.add(role)
            roles.append(role)
        await self.session.flush()
        return roles

    # ----- 用户 -----
    async def create_user(
        self,
        tenant_id: str,
        username: str,
        password: str,
        display_name: str = "",
        scope: str = "tenant",
    ) -> User:
        dup = await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.username == username)
        )
        if dup.scalar_one_or_none():
            raise ValueError("用户名已存在")
        salt = _new_salt()
        user = User(
            tenant_id=tenant_id,
            username=username,
            display_name=display_name or username,
            salt=salt,
            password_hash=_hash_argon2id(password),
            pwd_algo=PWD_ALGO_ARGON2ID,
            status=USER_STATUS_ACTIVE,
            scope=scope,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def seed_default_admin(
        self,
        tenant_id: str,
        username: str = "admin",
        password: str | None = None,
    ) -> User:
        """租户开通时播种默认管理员引导账号（M8-3 强制鉴权落地）。

        已存在同名用户则跳过（幂等）；并绑定 ADMIN 角色使其拥有完整权限集，
        从而登录后可正常访问受保护业务接口。

        口令来源：``password`` 参数 > ``PMS_BOOTSTRAP_ADMIN_PASSWORD`` 环境变量 >
        ``_resolve_bootstrap_password()`` 推导（生产随机 / 非生产回退 ``admin123``）。
        """
        existing = await self.get_user(tenant_id, username)
        if existing:
            return existing
        if password is None:
            password = _resolve_bootstrap_password()
        user = await self.create_user(
            tenant_id, username, password, display_name="系统管理员"
        )
        res = await self.session.execute(
            select(Role).where(
                Role.tenant_id == tenant_id, Role.level == ROLE_LEVEL_ADMIN
            )
        )
        admin_role = res.scalar_one_or_none()
        if admin_role:
            await self.assign_role(tenant_id, user.id, admin_role.id)
        await self.session.flush()
        return user

    async def get_user(self, tenant_id: str, username: str) -> User | None:
        res = await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.username == username)
        )
        return res.scalar_one_or_none()

    async def list_users(self, tenant_id: str) -> list[User]:
        res = await self.session.execute(select(User).where(User.tenant_id == tenant_id))
        return list(res.scalars())

    # ----- 角色 -----
    async def create_role(
        self,
        tenant_id: str,
        name: str,
        level: str,
        permissions: list[str],
        hotel_scoped: bool = False,
    ) -> Role:
        dup = await self.session.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.name == name)
        )
        if dup.scalar_one_or_none():
            raise ValueError("角色名已存在")
        role = Role(
            tenant_id=tenant_id,
            name=name,
            level=level,
            is_system=False,
            hotel_scoped=hotel_scoped,
            permissions=list(permissions),
        )
        self.session.add(role)
        await self.session.flush()
        return role

    async def list_roles(self, tenant_id: str) -> list[Role]:
        res = await self.session.execute(select(Role).where(Role.tenant_id == tenant_id))
        return list(res.scalars())

    # ----- 授权（用户-角色绑定） -----
    async def assign_role(
        self, tenant_id: str, user_id: int, role_id: int, hotel_id: int | None = None
    ) -> UserRole:
        user = await self.session.get(User, user_id)
        role = await self.session.get(Role, role_id)
        if not user or user.tenant_id != tenant_id:
            raise ValueError("用户不存在")
        if not role or role.tenant_id != tenant_id:
            raise ValueError("角色不存在")
        if role.hotel_scoped and hotel_id is None:
            raise ValueError("该角色必须绑定门店")
        binding = UserRole(
            tenant_id=tenant_id, user_id=user_id, role_id=role_id, hotel_id=hotel_id
        )
        self.session.add(binding)
        await self.session.flush()
        return binding

    async def list_user_roles(self, tenant_id: str, user_id: int) -> list[UserRole]:
        res = await self.session.execute(
            select(UserRole).where(
                UserRole.tenant_id == tenant_id, UserRole.user_id == user_id
            )
        )
        return list(res.scalars())

    # ----- 权限解析 -----
    async def _load_role_map(self, user: User) -> tuple[list[UserRole], dict[int, Role]]:
        bindings = await self.list_user_roles(user.tenant_id, user.id)
        if not bindings:
            return [], {}
        role_ids = {b.role_id for b in bindings}
        res = await self.session.execute(select(Role).where(Role.id.in_(role_ids)))
        return bindings, {r.id: r for r in res.scalars()}

    async def effective_permissions(self, user: User, hotel_id: int | None = None) -> set[str]:
        """聚合用户有效权限。

        - hotel_id 为空：返回用户在任意门店拥有的权限并集（登录态概览）；
        - hotel_id 给定：严格按门店作用域——租户级角色全量生效，
          门店级角色（hotel_scoped）仅当绑定门店与 hotel_id 一致时生效。
        """
        bindings, roles = await self._load_role_map(user)
        perms: set[str] = set()
        for b in bindings:
            role = roles.get(b.role_id)
            if not role:
                continue
            if hotel_id is None:
                perms.update(role.permissions)
            elif role.hotel_scoped:
                if b.hotel_id == hotel_id:
                    perms.update(role.permissions)
            else:
                perms.update(role.permissions)
        return perms

    async def has_tenant_scope_permission(self, user: User, permission: str) -> bool:
        """跨门店资源（如租户级审计查询）鉴权：只认可非门店绑定的角色权限。"""
        bindings, roles = await self._load_role_map(user)
        for b in bindings:
            role = roles.get(b.role_id)
            if role and not role.hotel_scoped and permission in role.permissions:
                return True
        return False

    async def has_permission(
        self, user: User, permission: str, hotel_id: int | None = None
    ) -> bool:
        perms = await self.effective_permissions(user, hotel_id)
        return permission in perms

    # ----- 登录安全（M8-3） -----
    async def authenticate(
        self, tenant_id: str, username: str, password: str, ip: str | None = None
    ) -> User:
        """登录校验。失败计数、超阈值锁定 30 分钟；成功重置计数并写登录时间。

        异常：ValueError("locked") 账号锁定中；ValueError("bad_credentials") 凭证错误；
        ValueError("disabled") 账号禁用；ValueError("not_found") 用户不存在。
        """
        user = await self.get_user(tenant_id, username)
        if user is None:
            raise ValueError("not_found")
        if user.status == USER_STATUS_DISABLED:
            raise ValueError("disabled")

        # 锁定过期自动解锁
        if user.status == USER_STATUS_LOCKED and user.locked_until:
            if _as_utc(user.locked_until) <= datetime.now(UTC):
                user.status = USER_STATUS_ACTIVE
                user.failed_attempts = 0
                user.locked_until = None

        if user.status == USER_STATUS_LOCKED:
            raise ValueError("locked")

        if not verify_password(user, password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
                user.status = USER_STATUS_LOCKED
                user.locked_until = datetime.now(UTC) + LOCK_DURATION
            self.session.add(user)
            await self.session.flush()
            raise ValueError("bad_credentials")

        # 成功：重置失败计数、写登录信息 + 透明升级口令哈希
        user.failed_attempts = 0
        user.locked_until = None
        user.status = USER_STATUS_ACTIVE
        user.last_login_at = datetime.now(UTC)
        user.last_login_ip = ip
        # 透明升级：老算法（sha256）→ argon2id，存量账号一个不掉
        upgraded = maybe_upgrade_to_argon2id(user, password)
        self.session.add(user)
        await self.session.flush()
        if upgraded:
            logger.info(
                "rbac.auth.upgraded_algo tenant=%s user=%s algo=%s",
                user.tenant_id,
                user.username,
                PWD_ALGO_ARGON2ID,
            )
        return user

    async def create_session(self, user: User, ip: str | None = None) -> LoginSession:
        session = LoginSession(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token=uuid.uuid4().hex,
            ip=ip,
            expired_at=session_ttl(),
            status="active",
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def revoke_session(self, tenant_id: str, token: str) -> bool:
        res = await self.session.execute(
            select(LoginSession).where(
                LoginSession.tenant_id == tenant_id, LoginSession.token == token
            )
        )
        sess = res.scalar_one_or_none()
        if not sess or sess.status != "active":
            return False
        sess.status = "revoked"
        self.session.add(sess)
        await self.session.flush()
        return True

    async def get_session(self, tenant_id: str, token: str) -> LoginSession | None:
        res = await self.session.execute(
            select(LoginSession).where(
                LoginSession.tenant_id == tenant_id, LoginSession.token == token
            )
        )
        sess = res.scalar_one_or_none()
        if not sess or sess.status != "active":
            return None
        if _as_utc(sess.expired_at) <= datetime.now(UTC):
            sess.status = "revoked"
            self.session.add(sess)
            await self.session.flush()
            return None
        return sess

    # ----- 刷新令牌（M18-2）：一次性旋转，防重放 -----

    async def create_refresh_token(self, user: User) -> RefreshToken:
        rt = RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token=uuid.uuid4().hex,
            expires_at=refresh_ttl(),
            status="active",
        )
        self.session.add(rt)
        await self.session.flush()
        return rt

    async def rotate_refresh_token(
        self, tenant_id: str, token: str
    ) -> tuple[User, RefreshToken] | None:
        """校验并旋转刷新令牌：旧令牌立即作废，签发新令牌。

        无效/过期/已撤销返回 None。
        """
        res = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.tenant_id == tenant_id, RefreshToken.token == token
            )
        )
        rt = res.scalar_one_or_none()
        if not rt or rt.status != "active":
            return None
        if _as_utc(rt.expires_at) <= datetime.now(UTC):
            rt.status = "revoked"
            self.session.add(rt)
            await self.session.flush()
            return None
        user = await self.session.get(User, rt.user_id)
        if not user or user.tenant_id != tenant_id or user.status != USER_STATUS_ACTIVE:
            rt.status = "revoked"
            self.session.add(rt)
            await self.session.flush()
            return None
        # 旋转：旧令牌作废 + 新令牌签发（同事务原子完成）
        rt.status = "revoked"
        self.session.add(rt)
        new_rt = await self.create_refresh_token(user)
        return user, new_rt

    async def revoke_user_refresh_tokens(self, tenant_id: str, user_id: int) -> int:
        """登出/改密时吊销该用户全部刷新令牌。返回吊销数量。"""
        res = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.tenant_id == tenant_id,
                RefreshToken.user_id == user_id,
                RefreshToken.status == "active",
            )
        )
        rows = list(res.scalars())
        for rt in rows:
            rt.status = "revoked"
            self.session.add(rt)
        if rows:
            await self.session.flush()
        return len(rows)
