"""租户与酒店（BLK-01 多租户框架）。"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class Tenant(IntPkMixin, TimestampMixin, Base):
    """租户（集团/单店开通单元，MAStore 北极星指标载体）。"""

    __tablename__ = "tenants"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_chain: Mapped[bool] = mapped_column(Boolean, default=False)  # 连锁/单体
    status: Mapped[str] = mapped_column(String(16), default="active")
    # M31：NoShow 自动扣首晚房费（租户级默认，Hotel 字段为 None 时继承本字段）
    noshow_charge_first_night: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class Hotel(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """门店。"""

    __tablename__ = "hotels"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    room_count: Mapped[int] = mapped_column(default=0)  # 冗余计数
    # M31：NoShow 自动扣首晚房费（酒店级覆盖，None=继承 Tenant.noshow_charge_first_night）
    noshow_charge_first_night: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
