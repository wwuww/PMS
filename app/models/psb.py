"""PSB 旅客住宿登记上传队列模型（M3-5）。

中国酒店业须将住客实名登记信息上报公安 PSB 系统。入住时自动生成上传任务，
由定时/手动触发上报（mock）。status: QUEUED → UPLOADED | FAILED。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class PsbUploadTask(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """一条住客登记上报任务（对应一次入住/散客登记）。"""

    __tablename__ = "psb_upload_tasks"

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    booking_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bookings.id"), nullable=True, index=True)
    guest_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    id_doc_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", nullable=False)  # QUEUED|UPLOADED|FAILED
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # 上报报文（脱敏后）
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator: Mapped[str] = mapped_column(String(64), default="system")

    @property
    def id_doc_no_masked(self) -> str | None:
        """证件号脱敏展示（保留前4后2，中间打码），API 仅暴露脱敏值。"""
        if not self.id_doc_no:
            return None
        doc = self.id_doc_no
        if len(doc) <= 6:
            return doc[:2] + "****"
        return doc[:4] + "****" + doc[-2:]
