"""权限审计（M8）RBAC 三级模型 + 登录会话（M8-3）。

三级角色档位 level：
- ADMIN   租户级超级管理员（所有权限）
- MANAGER 门店经理（改价/取消/冲账/折扣/夜审/审计查看）
- STAFF   前台（折扣/退款/取消等受限操作）

User 为门店登录账号；UserRole 将用户与角色绑定，可限定到具体门店（hotel_scoped 角色）。
LoginSession 记录登录会话（M8-3 会话安全）。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import BigInteger, JSON, Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


# 角色档位（三级）
ROLE_LEVEL_ADMIN = "ADMIN"
ROLE_LEVEL_MANAGER = "MANAGER"
ROLE_LEVEL_STAFF = "STAFF"

# 账号状态
USER_STATUS_ACTIVE = "active"
USER_STATUS_DISABLED = "disabled"
USER_STATUS_LOCKED = "locked"

# 账号作用域
SCOPE_TENANT = "tenant"  # 租户级（跨门店）
SCOPE_HOTEL = "hotel"    # 门店级

# 口令哈希算法版本（M32.18 P0-3 加固引入）
PWD_ALGO_SHA256 = "sha256"        # 历史算法：hashlib.sha256(salt+pwd)，保留用于透明升级
PWD_ALGO_ARGON2ID = "argon2id"    # 新算法：argon2-cffi 包装的 OWASP 推荐默认
PWD_ALGO_LEGACY = PWD_ALGO_SHA256


class User(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """门店登录账号（M8-1）。"""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    pwd_algo: Mapped[str] = mapped_column(String(16), default=PWD_ALGO_LEGACY)
    status: Mapped[str] = mapped_column(String(16), default=USER_STATUS_ACTIVE)
    scope: Mapped[str] = mapped_column(String(16), default=SCOPE_TENANT)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # 同租户内用户名唯一
        UniqueConstraint("tenant_id", "username", name="uq_user_tenant_username"),
    )


class Role(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """角色（含权限码集合，M8-1）。"""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default=ROLE_LEVEL_STAFF)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # 系统默认角色不可删
    hotel_scoped: Mapped[bool] = mapped_column(Boolean, default=False)  # 角色是否绑定具体门店
    permissions: Mapped[list] = mapped_column(JSON, default=list)  # 权限码列表


class UserRole(IntPkMixin, TenantMixin, Base):
    """用户-角色绑定（可限定到门店，M8-1）。"""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hotel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # 非空=仅对该门店生效


class LoginSession(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """登录会话（M8-3 会话安全）。"""

    __tablename__ = "login_sessions"

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|revoked


class RefreshToken(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """刷新令牌（M18-2）：access 会话过期后凭 refresh 换新，一次性旋转防重放。"""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|revoked


def session_ttl() -> datetime:
    """会话默认有效期：12 小时。"""
    return datetime.now(UTC) + timedelta(hours=12)


def refresh_ttl() -> datetime:
    """刷新令牌默认有效期：14 天。"""
    return datetime.now(UTC) + timedelta(days=14)
