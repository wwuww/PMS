"""M12 AI 自动对账预警服务。

夜审后扫描异常交易：金额异常、重复入账、漏收、渠道佣金差异。
当前为规则基线（准确率目标≥90%），后续可叠加统计/LLM 模型。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AlertNotification,
    Bill,
    BillItem,
    Booking,
    CommissionReconciliation,
    DailyReport,
    Payment,
    PayOrder,
)
from app.services.notification_service import NotificationService


class AnomalyService:
    """M12 自动对账与异常预警。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def scan_after_night_audit(
        self,
        tenant_id: str,
        hotel_id: int,
        business_date: str,
    ) -> list[AlertNotification]:
        """夜审后扫描，返回生成的预警列表。"""
        alerts: list[AlertNotification] = []
        alerts.extend(await self._check_amount_anomalies(tenant_id, hotel_id, business_date))
        alerts.extend(await self._check_duplicate_payments(tenant_id, hotel_id, business_date))
        alerts.extend(await self._check_missed_revenue(tenant_id, hotel_id, business_date))
        alerts.extend(await self._check_commission_diff(tenant_id, hotel_id, business_date))
        self.session.add_all(alerts)
        await self.session.flush()
        # ② 通知中心推送点：每生成一条预警同步推送到通知中心（点击深链直达预警详情）
        notif = NotificationService(self.session)
        for a in alerts:
            await notif.push(
                a.tenant_id,
                a.title,
                body=a.description,
                hotel_id=a.hotel_id,
                ref_type="alert",
                ref_id=a.id,
                level="critical",  # 风险预警：免打扰时段仍突破触达
            )
        return alerts

    async def _check_amount_anomalies(
        self, tenant_id: str, hotel_id: int, business_date: str
    ) -> list[AlertNotification]:
        """金额异常：房费为 0 或负数（折扣除外）、单笔支付金额异常大。"""
        alerts: list[AlertNotification] = []
        # 房费账单项为 0 或负数但类型不是 DISCOUNT/ADJUST
        rows = await self.session.execute(
            select(BillItem, Bill)
            .join(Bill, Bill.id == BillItem.bill_id)
            .where(
                Bill.tenant_id == tenant_id,
                Bill.hotel_id == hotel_id,
                BillItem.type.notin_(["DISCOUNT", "ADJUSTMENT"]),
                BillItem.amount <= 0,
            )
        )
        for item, bill in rows.all():
            alerts.append(
                AlertNotification(
                    tenant_id=tenant_id,
                    hotel_id=hotel_id,
                    alert_type="amount_anomaly",
                    severity="critical",
                    title="金额异常：非折扣账单项≤0",
                    description=f"账单 {bill.id} 的 {item.type} 金额为 {item.amount} 分，请复核。",
                    ref_type="bill_item",
                    ref_id=str(item.id),
                    suggested_action="核对订单来源与价格日历，确认是否误操作。",
                )
            )

        # 单笔现金支付超过 100000 分（1000 元）提示大额
        big = await self.session.execute(
            select(Payment, Bill)
            .join(Bill, Bill.id == Payment.bill_id)
            .where(
                Bill.tenant_id == tenant_id,
                Bill.hotel_id == hotel_id,
                Payment.method == "CASH",
                Payment.amount >= 100000,
            )
        )
        for pay, bill in big.all():
            alerts.append(
                AlertNotification(
                    tenant_id=tenant_id,
                    hotel_id=hotel_id,
                    alert_type="amount_anomaly",
                    severity="warning",
                    title="大额现金收款预警",
                    description=f"账单 {bill.id} 现金收款 {pay.amount} 分，建议复核。",
                    ref_type="payment",
                    ref_id=str(pay.id),
                    suggested_action="核对交班记录与实点现金。",
                )
            )
        return alerts

    async def _check_duplicate_payments(
        self, tenant_id: str, hotel_id: int, business_date: str
    ) -> list[AlertNotification]:
        """重复入账：同一账单短时间内多笔同金额同渠道支付。"""
        alerts: list[AlertNotification] = []
        rows = await self.session.execute(
            select(Payment.bill_id, Payment.method, Payment.amount, func.count())
            .join(Bill, Bill.id == Payment.bill_id)
            .where(
                Bill.tenant_id == tenant_id,
                Bill.hotel_id == hotel_id,
            )
            .group_by(Payment.bill_id, Payment.method, Payment.amount)
            .having(func.count() > 1)
        )
        for bill_id, method, amount, cnt in rows.all():
            alerts.append(
                AlertNotification(
                    tenant_id=tenant_id,
                    hotel_id=hotel_id,
                    alert_type="duplicate_payment",
                    severity="critical",
                    title="重复入账疑似",
                    description=f"账单 {bill_id} 存在 {cnt} 笔 {method} {amount} 分支付记录。",
                    ref_type="bill",
                    ref_id=str(bill_id),
                    suggested_action="核对支付流水，确认是否重复扣款或重复落账。",
                )
            )
        return alerts

    async def _check_missed_revenue(
        self, tenant_id: str, hotel_id: int, business_date: str
    ) -> list[AlertNotification]:
        """漏收：已入住订单无对应应收账单。"""
        alerts: list[AlertNotification] = []
        rows = await self.session.execute(
            select(Booking).where(
                Booking.tenant_id == tenant_id,
                Booking.hotel_id == hotel_id,
                Booking.status == "checked_in",
            )
        )
        for booking in rows.scalars():
            # 检查是否有指向该 booking 的账单
            count = await self.session.execute(
                select(func.count())
                .select_from(Bill)
                .where(
                    Bill.tenant_id == tenant_id,
                    Bill.hotel_id == hotel_id,
                    Bill.booking_id == booking.id,
                )
            )
            if not count.scalar():
                alerts.append(
                    AlertNotification(
                        tenant_id=tenant_id,
                        hotel_id=hotel_id,
                        alert_type="missed_revenue",
                        severity="warning",
                        title="漏收疑似：入住订单未建账单",
                        description=f"订单 {booking.id}（{booking.guest_name}）已入住但无关联账单。",
                        ref_type="booking",
                        ref_id=str(booking.id),
                        suggested_action="为住客开立账单并过房费。",
                    )
                )
        return alerts

    async def _check_commission_diff(
        self, tenant_id: str, hotel_id: int, business_date: str
    ) -> list[AlertNotification]:
        """渠道佣金差异：夜审佣金对账行状态 PENDING 或金额与规则不符。"""
        alerts: list[AlertNotification] = []
        rows = await self.session.execute(
            select(CommissionReconciliation).where(
                CommissionReconciliation.tenant_id == tenant_id,
                CommissionReconciliation.hotel_id == hotel_id,
                CommissionReconciliation.status == "PENDING",
            )
        )
        for rec in rows.scalars():
            expected = rec.room_revenue_cents * rec.commission_rate_bps // 10000
            diff = abs(rec.commission_cents - expected)
            if diff > 0:
                alerts.append(
                    AlertNotification(
                        tenant_id=tenant_id,
                        hotel_id=hotel_id,
                        alert_type="commission_diff",
                        severity="warning",
                        title="渠道佣金差异",
                        description=(
                            f"渠道 {rec.channel} 佣金 {rec.commission_cents} 分，"
                            f"按规则 {rec.commission_rate_bps}bps 应为 {expected} 分，差额 {diff} 分。"
                        ),
                        ref_type="commission_reconciliation",
                        ref_id=str(rec.id),
                        suggested_action="核对渠道账单与佣金规则。",
                    )
                )
        return alerts

    async def list_alerts(
        self,
        tenant_id: str,
        hotel_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AlertNotification]:
        stmt = select(AlertNotification).where(AlertNotification.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(AlertNotification.hotel_id == hotel_id)
        if status:
            stmt = stmt.where(AlertNotification.status == status)
        stmt = stmt.order_by(AlertNotification.id.desc()).limit(limit)
        rows = await self.session.execute(stmt)
        return list(rows.scalars())

    async def acknowledge(self, alert: AlertNotification) -> AlertNotification:
        alert.status = "acknowledged"
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def resolve(self, alert: AlertNotification) -> AlertNotification:
        alert.status = "resolved"
        self.session.add(alert)
        await self.session.flush()
        return alert
