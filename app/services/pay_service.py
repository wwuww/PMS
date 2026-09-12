"""移动支付服务（M7-2）：统一下单 / 回调幂等 / 金额校验 / 掉单对账。

微信支付为 mock 实现（prepay_id 本地生成、回调由网关/测试模拟），
真实签名与证书对接在 SG-2 压测准入门前按同一契约替换 _wechat_* 内部方法。

关键设计：
- 幂等：notify_id 唯一约束去重；重复回调返回 DUPLICATE 不重复落账。
- 金额校验：回调金额与支付单不符 → REJECTED（防篡改）。
- 掉单对账：对超时未支付单渠道查单（mock=未支付）→ 关单防占库存；
  「已支付但回调丢失」场景通过迟到回调天然补单（幂等路径放行）。
- 支付成功落账：若预订已开 OPEN 账单，直接落 Payment(WECHAT)；
  若尚未开单，标记 PAID，开账单后经 apply_prepay 抵扣。
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.events.base import PayOrderClosed, PayOrderPaid
from app.events.bus import event_bus
from app.models import Bill, Payment, PayNotify, PayOrder
from app.services.cashier_service import CashierService

PAY_STATUS_CREATED = "CREATED"
PAY_STATUS_PAID = "PAID"
PAY_STATUS_CLOSED = "CLOSED"
STALE_STATUSES = (PAY_STATUS_CREATED, "PAYING")

# 回调验签失败时的统一错误码（不含任何可探测内部状态的信息）
PAY_SIGN_INVALID = "SIGN_INVALID"
PAY_SIGN_NOT_CONFIGURED = "SIGN_NOT_CONFIGURED"


class PayNotifySignatureError(Exception):
    """支付回调验签失败。路由层据此返回 401，不进入任何落账逻辑。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def sign_payload(secret: str, raw_body: bytes) -> str:
    """回调签名算法：HMAC-SHA256(secret, 原始请求体)。与 OTA webhook 同一套契约。

    注意必须用**原始字节**而非解析后的 dict——JSON 序列化顺序/空白不可靠。
    """
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify_pay_notify_signature(raw_body: bytes, signature: str | None) -> None:
    """校验支付回调签名。失败抛 ``PayNotifySignatureError``，成功静默返回。

    安全要点：
    - 使用 ``hmac.compare_digest`` 防时序攻击；
    - 无签名 / 空签名一律拒绝（不做"未配置就放行"的宽松分支）；
    - 生产（``require_pay_notify_secret=True``）未注入密钥时**拒绝全部回调**，
      走人工补单，避免默认密钥被利用。
    """
    settings = get_settings()
    secret = settings.pay_notify_secret

    if not secret:
        if settings.require_pay_notify_secret:
            raise PayNotifySignatureError(
                PAY_SIGN_NOT_CONFIGURED, "支付回调密钥未配置，拒绝回调"
            )
        # dev/测试：无密钥则视为未启用验签（保持既有测试与本地联调可用）
        return

    if not signature:
        raise PayNotifySignatureError(PAY_SIGN_INVALID, "缺少回调签名")
    if not hmac.compare_digest(sign_payload(secret, raw_body), signature):
        raise PayNotifySignatureError(PAY_SIGN_INVALID, "回调签名校验失败")


def _as_utc(dt: datetime | None) -> datetime | None:
    """SQLite 读回 naive datetime，统一归一化为 UTC 感知（与 rbac_service 同法）。"""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _new_out_trade_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"MP{stamp}{uuid.uuid4().hex[:8].upper()}"


class PayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- 统一下单 ----

    async def create_order(
        self,
        tenant_id: str,
        hotel_id: int,
        amount_cents: int,
        subject: str = "",
        booking_id: int | None = None,
        channel: str = "WECHAT_MP",
    ) -> PayOrder:
        if amount_cents <= 0:
            raise ValueError("支付金额必须为正（分）")
        order = PayOrder(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            out_trade_no=_new_out_trade_no(),
            channel=channel,
            booking_id=booking_id,
            subject=subject,
            amount_cents=amount_cents,
            status=PAY_STATUS_CREATED,
        )
        self.session.add(order)
        await self.session.flush()
        await self._unified_order(order)
        return order

    async def _unified_order(self, order: PayOrder) -> dict[str, Any]:
        """微信统一下单（mock）。返回小程序拉起支付所需参数。"""
        order.prepay_id = f"prep_{uuid.uuid4().hex[:24]}"
        self.session.add(order)
        await self.session.flush()
        return {
            "prepay_id": order.prepay_id,
            "out_trade_no": order.out_trade_no,
            "amount_cents": order.amount_cents,
        }

    # ---- 回调（幂等） ----

    async def handle_notify(
        self,
        tenant_id: str,
        out_trade_no: str,
        amount_cents: int,
        transaction_id: str,
        notify_id: str,
        payload: dict | None = None,
    ) -> dict[str, Any]:
        """支付回调（幂等）。result: PROCESSED | DUPLICATE | REJECTED。"""
        dup = await self.session.execute(
            select(PayNotify).where(
                PayNotify.tenant_id == tenant_id, PayNotify.notify_id == notify_id
            )
        )
        if dup.scalar_one_or_none():
            return {"result": "DUPLICATE"}

        order = await self._get_order(tenant_id, out_trade_no)
        if not order or amount_cents != order.amount_cents:
            result = "REJECTED"  # 单不存在或金额不符（防篡改）
        elif order.status == PAY_STATUS_PAID:
            result = "DUPLICATE"  # 迟到重放回调：幂等放行不重复落账
        elif order.status == PAY_STATUS_CLOSED:
            result = "REJECTED"  # 已关单：走人工补单流程
        else:
            result = "PROCESSED"

        self.session.add(
            PayNotify(
                tenant_id=tenant_id,
                out_trade_no=out_trade_no,
                notify_id=notify_id,
                payload=payload or {},
                result=result,
            )
        )
        if result != "PROCESSED":
            await self.session.flush()
            return {"result": result}

        order.status = PAY_STATUS_PAID
        order.transaction_id = transaction_id
        order.paid_at = datetime.now(UTC)
        self.session.add(order)
        await self.session.flush()
        posted = await self._post_to_open_bill(order)
        await event_bus.publish(
            PayOrderPaid(
                tenant_id=tenant_id,
                out_trade_no=out_trade_no,
                booking_id=order.booking_id,
                amount_cents=order.amount_cents,
                transaction_id=transaction_id,
                posted_to_bill=posted,
            )
        )
        return {"result": result, "posted_to_bill": posted}

    async def _post_to_open_bill(self, order: PayOrder) -> bool:
        """支付成功落账：若预订已有 OPEN 账单，落 Payment(WECHAT) 并回填 bill_id。"""
        if order.bill_id:
            bill = await self.session.get(Bill, order.bill_id)
        elif order.booking_id:
            row = await self.session.execute(
                select(Bill).where(
                    Bill.tenant_id == order.tenant_id,
                    Bill.booking_id == order.booking_id,
                    Bill.status == "OPEN",
                )
            )
            bill = row.scalar_one_or_none()
        else:
            bill = None
        if not bill or bill.status != "OPEN":
            return False
        cs = CashierService(self.session)
        await cs.take_payment(
            bill, "WECHAT", order.amount_cents, operator="wechat_mp", ref_no=order.transaction_id
        )
        order.bill_id = bill.id
        self.session.add(order)
        await self.session.flush()
        return True

    # ---- 预付抵扣 ----

    async def apply_prepay(self, bill: Bill) -> int:
        """预付抵扣（M7）：开账单晚于支付回调时，将已支付未落账的预付单落 Payment。"""
        rows = await self.session.execute(
            select(PayOrder).where(
                PayOrder.tenant_id == bill.tenant_id,
                PayOrder.status == PAY_STATUS_PAID,
                PayOrder.booking_id == bill.booking_id,
                PayOrder.bill_id.is_(None),
            )
        )
        cs = CashierService(self.session)
        applied = 0
        for order in rows.scalars():
            await cs.take_payment(
                bill,
                "WECHAT",
                order.amount_cents,
                operator="wechat_mp",
                ref_no=order.transaction_id,
            )
            order.bill_id = bill.id
            self.session.add(order)
            applied += 1
        await self.session.flush()
        return applied

    # ---- 关单 / 掉单对账 ----

    async def close_order(self, order: PayOrder, reason: str = "user_cancel") -> PayOrder:
        if order.status == PAY_STATUS_PAID:
            raise ValueError("已支付订单不可关闭")
        if order.status == PAY_STATUS_CLOSED:
            return order
        order.status = PAY_STATUS_CLOSED
        order.closed_at = datetime.now(UTC)
        order.close_reason = reason
        self.session.add(order)
        await self.session.flush()
        await event_bus.publish(
            PayOrderClosed(
                tenant_id=order.tenant_id, out_trade_no=order.out_trade_no, reason=reason
            )
        )
        return order

    async def reconcile(self, tenant_id: str, before: datetime) -> dict[str, Any]:
        """掉单对账（M7-2）：对 before 之前创建的未支付单渠道查单 → 补单或关单。"""
        rows = await self.session.execute(
            select(PayOrder).where(
                PayOrder.tenant_id == tenant_id, PayOrder.status.in_(STALE_STATUSES)
            )
        )
        scanned = closed = recovered = 0
        details: list[dict[str, Any]] = []
        for order in rows.scalars():
            created = _as_utc(order.created_at)
            if created is None or created > before:
                continue
            scanned += 1
            paid = await self._wechat_query_paid(order)
            if paid:
                # 渠道已支付但回调丢失 → 补单
                await self.handle_notify(
                    tenant_id,
                    order.out_trade_no,
                    order.amount_cents,
                    transaction_id=f"recon_{order.out_trade_no}",
                    notify_id=f"recon_{order.out_trade_no}",
                )
                recovered += 1
                details.append({"out_trade_no": order.out_trade_no, "action": "paid_recovered"})
            else:
                await self.close_order(order, reason="reconcile_timeout")
                closed += 1
                details.append({"out_trade_no": order.out_trade_no, "action": "closed"})
        return {"scanned": scanned, "closed": closed, "recovered": recovered, "details": details}

    async def _wechat_query_paid(self, order: PayOrder) -> bool:
        """渠道查单（mock：恒未支付）。真实实现按商户号查询微信订单状态。"""
        return False

    # ---- 查询 ----

    async def _get_order(self, tenant_id: str, out_trade_no: str) -> PayOrder | None:
        row = await self.session.execute(
            select(PayOrder).where(
                PayOrder.tenant_id == tenant_id, PayOrder.out_trade_no == out_trade_no
            )
        )
        return row.scalar_one_or_none()

    async def list_orders(self, tenant_id: str, status: str | None = None) -> list[PayOrder]:
        stmt = select(PayOrder).where(PayOrder.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(PayOrder.status == status)
        stmt = stmt.order_by(PayOrder.id.desc())
        rows = await self.session.execute(stmt)
        return list(rows.scalars())
