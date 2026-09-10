"""会员 CRM 服务（M13，FR-MB）。

连锁场景下会员主数据按 tenant_id 共享（跨店通用），hotel_id 记录归属门店。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Booking, Member


class MemberService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register(
        self,
        tenant_id: str,
        hotel_id: int,
        name: str,
        phone: str,
        *,
        member_no: str | None = None,
        card_type: str | None = None,
        join_date: str | None = None,
    ) -> Member:
        existing = await self.get_by_phone(tenant_id, phone)
        if existing:
            return existing
        member = Member(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            name=name,
            phone=phone,
            level="NORMAL",
            # 批次② 字段补全
            member_no=member_no,
            card_type=card_type,
            join_date=join_date,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def get_by_phone(self, tenant_id: str, phone: str) -> Member | None:
        r = await self.session.execute(
            select(Member).where(Member.tenant_id == tenant_id, Member.phone == phone)
        )
        return r.scalar_one_or_none()

    async def recharge(self, member: Member, amount: int, operator: str = "front_desk") -> Member:
        if amount <= 0:
            raise ValueError("充值金额必须为正")
        member.stored_value += amount
        self.session.add(member)
        self.session.add(
            AuditLog(
                tenant_id=member.tenant_id,
                actor=operator,
                action="member.recharge",
                resource_type="member",
                resource_id=str(member.id),
                detail={"amount": amount},
            )
        )
        await self.session.flush()
        return member

    async def earn_points(
        self, member: Member, spend_cents: int, operator: str = "system"
    ) -> Member:
        """按消费金额累积积分：每 100 分(=1元) 得 1 分。"""
        pts = spend_cents // 100
        if pts <= 0:
            return member
        member.points += pts
        member.total_spend += spend_cents
        self.session.add(member)
        await self.session.flush()
        return member

    async def record_stay(self, member: Member) -> Member:
        """入住次数 +1，并按阈值自动升级。"""
        member.stays += 1
        if member.stays >= 50:
            member.level = "PLATINUM"
        elif member.stays >= 20:
            member.level = "GOLD"
        elif member.stays >= 5:
            member.level = "SILVER"
        self.session.add(member)
        await self.session.flush()
        return member

    async def use_points(self, member: Member, points: int, operator: str = "front_desk") -> Member:
        if member.points < points:
            raise ValueError("积分余额不足")
        member.points -= points
        self.session.add(member)
        await self.session.flush()
        return member

    async def history(self, tenant_id: str, phone: str) -> list[Booking]:
        member = await self.get_by_phone(tenant_id, phone)
        if not member:
            return []
        r = await self.session.execute(
            select(Booking)
            .where(Booking.tenant_id == tenant_id, Booking.guest_phone == phone)
            .order_by(Booking.id.desc())
        )
        return list(r.scalars())
