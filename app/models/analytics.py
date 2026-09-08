"""数据中台/经营分析模型（M16，FR-RP）。

ClickHouse 生产部署时，MetricSnapshot 可对应物化视图；开发期以 SQLite/PostgreSQL
存储预聚合快照，保证报表接口稳定。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class ReportTemplate(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """报表模板：店长/总部保存的常用维度与指标组合。"""

    __tablename__ = "report_templates"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), default="hotel")  # hotel | group
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)  # dashboard | channel | room_type | hotel_ranking
    dimensions: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    metrics: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    filters: Mapped[str] = mapped_column(Text, default="{}")  # JSON dict
    created_by: Mapped[str] = mapped_column(String(64), default="system")


class MetricSnapshot(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """指标快照：按酒店+营业日预聚合的核心指标，可离线图/ClickHouse 同步。"""

    __tablename__ = "metric_snapshots"

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    metric_type: Mapped[str] = mapped_column(String(32), nullable=False)  # kpi | channel | room_type
    dimension: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 维度值，如渠道名/房型编码
    metric_name: Mapped[str] = mapped_column(String(32), nullable=False)  # revpar | occ | adr | revenue | rooms_sold
    metric_value: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="{}")  # JSON 明细
