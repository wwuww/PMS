"""BLK-03 领域事件规范：事件基类与主题命名。

主题命名规范：{domain}.{aggregate}.{action}
    例：room.room.state_changed

事件设计约束：
- 事件为不可变值对象（dataclass/frozen）；
- 必含 tenant_id（多租户隔离，扇出与审计依赖）；
- occurred_at 使用 UTC ISO8601。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """领域事件基类。"""

    tenant_id: str
    occurred_at: str = field(default_factory=lambda: utc_now().isoformat())

    @property
    def topic(self) -> str:
        raise NotImplementedError

    def payload(self) -> dict[str, Any]:
        return {"topic": self.topic, "occurred_at": self.occurred_at, "tenant_id": self.tenant_id}


@dataclass(frozen=True, kw_only=True)
class RoomStateChanged(DomainEvent):
    """M1-1 房态变更事件（验收：房态事件可订阅）。"""

    TOPIC: ClassVar[str] = "room.room.state_changed"

    room_id: int
    room_no: str
    from_state: str
    to_state: str
    trigger: str
    operator: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "room_id": self.room_id,
                "room_no": self.room_no,
                "from_state": self.from_state,
                "to_state": self.to_state,
                "trigger": self.trigger,
                "operator": self.operator,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class BookingStateChanged(DomainEvent):
    """M2 预订状态变更事件（入住/退房/取消时发布，供渠道回推与经营分析订阅）。"""

    TOPIC: ClassVar[str] = "booking.state_changed"

    booking_id: int
    room_type_id: int
    from_status: str
    to_status: str
    channel: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "booking_id": self.booking_id,
                "room_type_id": self.room_type_id,
                "from_status": self.from_status,
                "to_status": self.to_status,
                "channel": self.channel,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class NightAuditCompleted(DomainEvent):
    """M4 夜审完成事件（营业日关闭、日报生成后发布，供经营分析订阅）。"""

    TOPIC: ClassVar[str] = "night_audit.completed"

    hotel_id: int
    business_date: str
    total_revenue: int
    occupied_rooms: int

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "hotel_id": self.hotel_id,
                "business_date": self.business_date,
                "total_revenue": self.total_revenue,
                "occupied_rooms": self.occupied_rooms,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class CommissionReconciled(DomainEvent):
    """M4-4 佣金对账完成事件（夜审计提佣金后发布，供财务对账订阅）。"""

    TOPIC: ClassVar[str] = "commission.reconciled"

    hotel_id: int
    business_date: str
    total_commission: int
    channels: int

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "hotel_id": self.hotel_id,
                "business_date": self.business_date,
                "total_commission": self.total_commission,
                "channels": self.channels,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class ShiftClosed(DomainEvent):
    """M3 交班事件（收银员交班、现金对账后发布，供财务/审计订阅）。"""

    TOPIC: ClassVar[str] = "cashier.shift_closed"

    shift_id: int
    hotel_id: int
    cashier: str
    expected_cash: int
    counted_cash: int
    discrepancy: int

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "shift_id": self.shift_id,
                "hotel_id": self.hotel_id,
                "cashier": self.cashier,
                "expected_cash": self.expected_cash,
                "counted_cash": self.counted_cash,
                "discrepancy": self.discrepancy,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class WakeUpCallScheduled(DomainEvent):
    """M3-7 叫醒登记事件（前台登记叫醒后发布，供前台定时触发订阅）。"""

    TOPIC: ClassVar[str] = "wakeup.scheduled"

    hotel_id: int
    room_no: str
    call_at: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "hotel_id": self.hotel_id,
                "room_no": self.room_no,
                "call_at": self.call_at,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class PsbUploaded(DomainEvent):
    """M3-5 PSB 住客登记上报事件（上报成功后发布，供公安对接/审计订阅）。"""

    TOPIC: ClassVar[str] = "psb.uploaded"

    hotel_id: int
    booking_id: int | None
    task_id: int

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "hotel_id": self.hotel_id,
                "booking_id": self.booking_id,
                "task_id": self.task_id,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class UserLoggedIn(DomainEvent):
    """M8-3 登录事件（成功/失败均发布，供安全监控订阅）。"""

    TOPIC: ClassVar[str] = "auth.user_logged_in"

    user_id: int
    username: str
    ip: str | None
    success: bool

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "user_id": self.user_id,
                "username": self.username,
                "ip": self.ip,
                "success": self.success,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class PermissionDenied(DomainEvent):
    """M8-3 鉴权拒绝事件（越权访问尝试，供安全审计订阅）。"""

    TOPIC: ClassVar[str] = "auth.permission_denied"

    user_id: int | None
    username: str
    permission: str
    resource: str | None

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "user_id": self.user_id,
                "username": self.username,
                "permission": self.permission,
                "resource": self.resource,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class MpOrderCreated(DomainEvent):
    """M7-1 小程序下单事件（下单成功后发布，供营销/消息推送订阅）。"""

    TOPIC: ClassVar[str] = "mp.order_created"

    booking_id: int
    out_trade_no: str
    amount_cents: int

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "booking_id": self.booking_id,
                "out_trade_no": self.out_trade_no,
                "amount_cents": self.amount_cents,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class PayOrderPaid(DomainEvent):
    """M7-2 支付成功事件（回调确认后发布，供订单确认/财务入账订阅）。"""

    TOPIC: ClassVar[str] = "pay.order_paid"

    out_trade_no: str
    booking_id: int | None
    amount_cents: int
    transaction_id: str | None
    posted_to_bill: bool

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "out_trade_no": self.out_trade_no,
                "booking_id": self.booking_id,
                "amount_cents": self.amount_cents,
                "transaction_id": self.transaction_id,
                "posted_to_bill": self.posted_to_bill,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class PayOrderClosed(DomainEvent):
    """M7-2 支付关单事件（用户取消/对账超时关单后发布，供库存释放订阅）。"""

    TOPIC: ClassVar[str] = "pay.order_closed"

    out_trade_no: str
    reason: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update({"out_trade_no": self.out_trade_no, "reason": self.reason})
        return base


@dataclass(frozen=True, kw_only=True)
class GroupPolicyApplied(DomainEvent):
    """M17-2 集团价格策略下发事件（策略中心通知门店价格边界变更，可订阅刷新缓存）。"""

    TOPIC: ClassVar[str] = "group.policy_applied"

    policy_id: int
    room_type_id: int | None
    price_floor_cents: int
    price_ceiling_cents: int | None

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "policy_id": self.policy_id,
                "room_type_id": self.room_type_id,
                "price_floor_cents": self.price_floor_cents,
                "price_ceiling_cents": self.price_ceiling_cents,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class ApprovalDecided(DomainEvent):
    """M10-2 移动审批决策事件（通过/驳回，供执行器与审计订阅）。"""

    TOPIC: ClassVar[str] = "approval.decided"

    ticket_id: int
    approval_type: str
    decision: str  # APPROVED | REJECTED
    approver: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "ticket_id": self.ticket_id,
                "approval_type": self.approval_type,
                "decision": self.decision,
                "approver": self.approver,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class HousekeepingDone(DomainEvent):
    """M10-3 清扫工单完成事件（房态回归可售后发布，供房态盘实时刷新订阅）。"""

    TOPIC: ClassVar[str] = "housekeeping.done"

    task_id: int
    room_no: str
    task_type: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "task_id": self.task_id,
                "room_no": self.room_no,
                "task_type": self.task_type,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class ChatHandoffRequested(DomainEvent):
    """M11 智能客服转人工事件（前台/店长 App 可订阅并接管会话）。"""

    TOPIC: ClassVar[str] = "chat.handoff_requested"

    session_id: int
    channel: str
    reason: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update({"session_id": self.session_id, "channel": self.channel, "reason": self.reason})
        return base


@dataclass(frozen=True, kw_only=True)
class AnomalyDetected(DomainEvent):
    """M12 自动对账异常预警事件（推送至店长/财务）。"""

    TOPIC: ClassVar[str] = "anomaly.detected"

    alert_id: int
    alert_type: str
    severity: str
    hotel_id: int | None

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "alert_id": self.alert_id,
                "alert_type": self.alert_type,
                "severity": self.severity,
                "hotel_id": self.hotel_id,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class BillSettled(DomainEvent):
    """M3 账单结清事件（结账后发布，触发会员积分累积/财务入账）。"""

    TOPIC: ClassVar[str] = "cashier.bill_settled"

    bill_id: int
    hotel_id: int
    guest_name: str
    settle_amount: int
    payment_methods: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "bill_id": self.bill_id,
                "hotel_id": self.hotel_id,
                "guest_name": self.guest_name,
                "settle_amount": self.settle_amount,
                "payment_methods": self.payment_methods,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class NotificationPushed(DomainEvent):
    """⑤ 通知已推送事件（NotificationService.push 落库后发布）。

    供 WebSocket 网关（/ws/notifications）按 recipients 接收角色做实时扇出路由：
    - recipients：本通知的最终接收角色标签（store_manager/front_desk/night_audit）；
    - muted：③ 免打扰静音标记，为 True 时实时网关不应弹出（但通知中心仍可见）；
    - 订阅方将自身角色映射为标签集合，与 recipients 求交集决定下发。
    """

    TOPIC: ClassVar[str] = "notification.pushed"

    notification_id: int
    ref_type: str | None
    ref_id: int | None
    recipients: list[str]
    muted: bool
    level: str
    title: str
    body: str
    link: str | None

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "notification_id": self.notification_id,
                "ref_type": self.ref_type,
                "ref_id": self.ref_id,
                "recipients": self.recipients,
                "muted": self.muted,
                "level": self.level,
                "title": self.title,
                "body": self.body,
                "link": self.link,
            }
        )
        return base


@dataclass(frozen=True, kw_only=True)
class DepositChanged(DomainEvent):
    """M32.18 押金/预授权生命周期事件（用于实时通知与跨域联动）。

    状态变化时由 ``DepositService`` 通过 ``event_bus.publish`` 发出。
    ``action`` 复用 ``DepositAction`` 枚举值（CREATE/APPLY/REFUND/...）。
    """

    TOPIC: ClassVar[str] = "deposit.deposit.changed"

    deposit_id: int
    deposit_no: str
    kind: str  # DEPOSIT | PREAUTH
    action: str  # CREATE|APPLY|REFUND|FORFEIT|VOID|CAPTURE|RELEASE|EXPIRE
    status: str
    amount_cents: int
    available_cents: int
    booking_id: int | None
    room_no: str | None
    bill_id: int | None
    operator: str

    @property
    def topic(self) -> str:
        return self.TOPIC

    def payload(self) -> dict[str, Any]:
        base = super().payload()
        base.update(
            {
                "deposit_id": self.deposit_id,
                "deposit_no": self.deposit_no,
                "kind": self.kind,
                "action": self.action,
                "status": self.status,
                "amount_cents": self.amount_cents,
                "available_cents": self.available_cents,
                "booking_id": self.booking_id,
                "room_no": self.room_no,
                "bill_id": self.bill_id,
                "operator": self.operator,
            }
        )
        return base
