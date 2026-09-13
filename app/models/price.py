"""价格日历（FR-JG 全量：价格库存中心为唯一房价房量源，DEC-01）。

以「房型 × 日期」维度维护基准价覆盖（如节假日/周末溢价、促销底价），
与 RateCode 五维折扣（FR-JG-06）共同构成价格解析管线。
"""

from sqlalchemy import ForeignKey, BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class PriceCalendar(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "price_calendar"
    # D1（M0 多店）：唯一约束升门店级 —— 两店同房型同日可有各自的价格覆盖。
    __table_args__ = (
        UniqueConstraint("tenant_id", "hotel_id", "room_type_id", "date"),
    )

    # D1：价格覆盖归属门店（NOT NULL）—— 支撑"两店独立定价"。
    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False, index=True
    )
    room_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("room_types.id"), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # 分
