"""移动审批中心（M10-2，FR-APP-02）：提交 → 一键审批 → 自动执行动作。

审批≤2步（前台/系统提交 + 店长一键决策）；折扣类审批通过后自动落账
（复用 CashierService.add_charge，保持收银单一事实源）；决策全程审计留痕。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import ApprovalDecided
from app.events.bus import event_bus
from app.models import ApprovalTicket, Bill
from app.services.audit_service import record as audit_record
from app.services.cashier_service import CashierService
from app.services.notification_service import NotificationService

APPROVAL_TYPES = ("DISCOUNT", "ADJUST", "OVERBOOK", "REFUND")
EXECUTABLE = {"DISCOUNT"}  # 审批通过即自动执行的类型（其余为放行标记）


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def submit(
        self,
        tenant_id: str,
        hotel_id: int,
        approval_type: str,
        payload: dict[str, Any],
        reason: str,
        applicant: str,
    ) -> ApprovalTicket:
        if approval_type not in APPROVAL_TYPES:
            raise ValueError(f"未知审批类型: {approval_type}")
        ticket = ApprovalTicket(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            type=approval_type,
            payload=payload,
            reason=reason,
            applicant=applicant,
            status="PENDING",
        )
        self.session.add(ticket)
        await self.session.flush()
        # ② 通知中心推送点：提交即提醒店长待审批（点击深链直达审批单）
        await NotificationService(self.session).push(
            tenant_id,
            f"待审批：{approval_type} 申请",
            body=f"{applicant} 提交，原因：{reason}",
            hotel_id=hotel_id,
            ref_type="approval",
            ref_id=ticket.id,
        )
        return ticket

    async def decide(
        self, ticket: ApprovalTicket, decision: str, approver: str, note: str = ""
    ) -> ApprovalTicket:
        if ticket.status != "PENDING":
            raise ValueError(f"该审批单已处理（{ticket.status}）")
        if decision not in ("APPROVE", "REJECT"):
            raise ValueError("决策须为 APPROVE 或 REJECT")
        ticket.status = "APPROVED" if decision == "APPROVE" else "REJECTED"
        ticket.approver = approver
        ticket.decision_note = note
        ticket.decided_at = datetime.now(UTC)
        ref_id = None
        if decision == "APPROVE" and ticket.type in EXECUTABLE:
            ref_id = await self._execute(ticket, approver)
        ticket.ref_id = ref_id
        self.session.add(ticket)
        await self.session.flush()
        await audit_record(
            self.session,
            ticket.tenant_id,
            "approval.decide",
            actor=approver,
            resource_type="approval_ticket",
            resource_id=ticket.id,
            hotel_id=ticket.hotel_id,
            result="success",
            detail={"type": ticket.type, "decision": ticket.status, "note": note},
        )
        await event_bus.publish(
            ApprovalDecided(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                approval_type=ticket.type,
                decision=ticket.status,
                approver=approver,
            )
        )
        return ticket

    async def _execute(self, ticket: ApprovalTicket, approver: str) -> int | None:
        """审批通过后的自动执行。DISCOUNT：向账单落折扣应收（负向冲减）。"""
        if ticket.type == "DISCOUNT":
            bill = await self.session.get(Bill, int(ticket.payload.get("bill_id", 0)))
            if not bill or bill.tenant_id != ticket.tenant_id:
                raise ValueError("审批单指向的账单不存在")
            await CashierService(self.session).add_charge(
                bill,
                "DISCOUNT",
                int(ticket.payload.get("amount", 0)),
                ticket.payload.get("description", f"店长审批折扣 {ticket.id}"),
                operator=approver,
            )
            return bill.id
        return None

    async def list_tickets(
        self, tenant_id: str, status: str | None = None, hotel_id: int | None = None
    ) -> list[ApprovalTicket]:
        stmt = select(ApprovalTicket).where(ApprovalTicket.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(ApprovalTicket.status == status)
        if hotel_id is not None:
            stmt = stmt.where(ApprovalTicket.hotel_id == hotel_id)
        stmt = stmt.order_by(ApprovalTicket.id.desc())
        rows = await self.session.execute(stmt)
        return list(rows.scalars())
