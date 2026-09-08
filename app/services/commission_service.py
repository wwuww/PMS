"""佣金对账服务（M4-4）。

夜审时由 NightAuditService 调用 reconcile()，按租户佣金规则对当日各渠道
佣金性房费收入计提佣金，沉淀不可变 CommissionReconciliation 行。
无对应渠道规则的（直订/微信）不计提。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import CommissionReconciled, utc_now
from app.events.bus import event_bus
from app.models import CommissionReconciliation, CommissionRule


class CommissionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def set_rule(self, tenant_id: str, channel: str, rate_bps: int, note: str = "") -> CommissionRule:
        """设定/更新某渠道佣金率（basis points）。"""
        if rate_bps < 0 or rate_bps > 10000:
            raise ValueError("费率须在 0~10000 基点之间")
        r = await self.session.execute(
            select(CommissionRule).where(
                CommissionRule.tenant_id == tenant_id, CommissionRule.channel == channel
            )
        )
        rule = r.scalar_one_or_none()
        if rule:
            rule.rate_bps = rate_bps
            rule.note = note
        else:
            rule = CommissionRule(
                tenant_id=tenant_id, channel=channel, rate_bps=rate_bps, note=note
            )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def list_rules(self, tenant_id: str) -> list[CommissionRule]:
        r = await self.session.execute(
            select(CommissionRule).where(CommissionRule.tenant_id == tenant_id)
        )
        return list(r.scalars())

    async def reconcile(
        self,
        tenant_id: str,
        hotel_id: int,
        business_date: str,
        revenue_by_channel: dict[str, int],
    ) -> list[CommissionReconciliation]:
        """按规则对 revenue_by_channel 计提佣金，生成对账行（已存在则幂等覆盖）。"""
        rules = await self.list_rules(tenant_id)
        rule_map = {rl.channel: rl.rate_bps for rl in rules}

        produced: list[CommissionReconciliation] = []
        for channel, revenue in revenue_by_channel.items():
            rate_bps = rule_map.get(channel, 0)
            if rate_bps <= 0 or revenue <= 0:
                continue  # 无规则或零收入不计提
            commission = revenue * rate_bps // 10000

            # 幂等：同 酒店×营业日×渠道 覆盖
            r = await self.session.execute(
                select(CommissionReconciliation).where(
                    CommissionReconciliation.hotel_id == hotel_id,
                    CommissionReconciliation.business_date == business_date,
                    CommissionReconciliation.channel == channel,
                )
            )
            rec = r.scalar_one_or_none()
            if not rec:
                rec = CommissionReconciliation(
                    tenant_id=tenant_id,
                    hotel_id=hotel_id,
                    business_date=business_date,
                    channel=channel,
                )
                self.session.add(rec)
            rec.room_revenue_cents = revenue
            rec.commission_rate_bps = rate_bps
            rec.commission_cents = commission
            rec.status = "PENDING"
            rec.reconciled_at = None
            await self.session.flush()
            produced.append(rec)

        if produced:
            await event_bus.publish(
                CommissionReconciled(
                    tenant_id=tenant_id,
                    hotel_id=hotel_id,
                    business_date=business_date,
                    total_commission=sum(p.commission_cents for p in produced),
                    channels=len(produced),
                )
            )
        return produced
