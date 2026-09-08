"""价格日历（FR-JG 全量：价格库存中心为唯一房价房量源，DEC-01）。

以「房型 × 日期」维度维护基准价覆盖（如节假日/周末溢价、促销底价），
与 RateCode 五维折扣（FR-JG-06）共同构成价格解析管线。
"""

from sqlalchemy import ForeignKey, BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class PriceCalendar(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_calendar"
    __table_args__ = (UniqueConstraint("tenant_id", "room_type_id", "date"),)

    room_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("room_types.id"), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # 分
