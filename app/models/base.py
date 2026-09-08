"""数据模型基类：多租户隔离（BLK-01）与审计字段基线。"""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.core.snowflake import next_id


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class TenantMixin:
    """多租户隔离：tenant_id 贯穿所有业务表（分片路由键，dev-plan 2.2）。"""

    @declared_attr.directive
    def tenant_id(cls) -> Mapped[str]:  # noqa: N805
        return mapped_column(String(32), nullable=False, index=True)


class IntPkMixin:
    # 128 分库分表：主键改用 BigInteger + 雪花 ID（见 app.core.snowflake）
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False, default=lambda: next_id()
    )
