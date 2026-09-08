"""店长经营看板服务（M10-1，FR-APP-01）：实时房态盘 + 当日核心指标 + 待办提醒。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApprovalTicket, Booking, DailyReport, Room
from app.services.approval_service import ApprovalService
from app.services.housekeeping_service import HousekeepingService
from app.services.notification_service import NotificationService


class ManagerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dashboard(
        self, tenant_id: str, hotel_id: int, business_date: str | None = None
    ) -> dict[str, Any]:
        """手机端看板：房态盘汇总 / 在住·预抵·预离 / 核心指标 / 待办提醒。"""
        date = business_date or datetime.now(UTC).date().isoformat()

        # 房态盘：按状态计数
        rows = await self.session.execute(
            select(Room.state, func.count())
            .where(Room.tenant_id == tenant_id, Room.hotel_id == hotel_id)
            .group_by(Room.state)
        )
        by_state = {state: int(n) for state, n in rows.all()}
        total = sum(by_state.values())
        occupied = by_state.get("occupied", 0)
        occupancy_pct = (occupied * 100 // total) if total else 0

        # 预抵 / 预离 / 在住
        arrivals = await self._bookings(tenant_id, hotel_id, "created", check_in_date=date)
        departures = await self._bookings(tenant_id, hotel_id, "checked_in", check_out_date=date)
        in_house = await self._count(
            Booking.tenant_id == tenant_id,
            Booking.hotel_id == hotel_id,
            Booking.status == "checked_in",
        )

        # 最新营业日报（夜审后生成）
        report = await self.session.execute(
            select(DailyReport)
            .where(DailyReport.tenant_id == tenant_id, DailyReport.hotel_id == hotel_id)
            .order_by(DailyReport.id.desc())
            .limit(1)
        )
        latest_report = report.scalar_one_or_none()

        # 待办提醒（FR-APP-02/03/04 汇聚）
        overdue_tasks = await HousekeepingService(self.session).overdue_count(tenant_id, hotel_id)
        pending_rows = await self.session.execute(
            select(func.count())
            .select_from(ApprovalTicket)
            .where(
                ApprovalTicket.tenant_id == tenant_id,
                ApprovalTicket.hotel_id == hotel_id,
                ApprovalTicket.status == "PENDING",
            )
        )
        pending_approvals = int(pending_rows.scalar() or 0)
        unread = await NotificationService(self.session).list_notifications(
            tenant_id, hotel_id, unread_only=True
        )

        return {
            "hotel_id": hotel_id,
            "business_date": date,
            "rooms": {"total": total, "by_state": by_state},
            "occupancy_pct": occupancy_pct,
            "in_house": in_house,
            "arrivals": arrivals,
            "departures": departures,
            "latest_report": latest_report,
            "alerts": {
                "overdue_tasks": overdue_tasks,
                "pending_approvals": pending_approvals,
                "unread_notifications": len(unread),
            },
        }

    async def _bookings(
        self, tenant_id: str, hotel_id: int, status: str, **date_filter: str
    ) -> list[Booking]:
        stmt = select(Booking).where(
            Booking.tenant_id == tenant_id,
            Booking.hotel_id == hotel_id,
            Booking.status == status,
        )
        for col, val in date_filter.items():
            stmt = stmt.where(getattr(Booking, col) == val)
        rows = await self.session.execute(stmt)
        return list(rows.scalars())

    async def _count(self, *where: object) -> int:
        row = await self.session.execute(
            select(func.count()).select_from(Booking).where(*where)
        )
        return int(row.scalar() or 0)
