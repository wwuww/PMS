"""M37-③ 发票服务（开票 / 作废 / 查 / 按账单查）。

规则（对齐维也纳数据字典）：
- 开票额 > 消费额 且 差额 > 1000 分（¥10）→ 必填审批人 ``approver``
- 专票 ``invoice_type == "VAT_SPECIAL"`` → 必填纳税人识别号 ``tax_no``
- 作废 WORM：仅置 ``status=VOID``，不改金额不物理删
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.snowflake import next_id
from app.models import Invoice


# 审批阈值：开票额超出消费额超过此分值时强制审批（对齐维也纳 ¥10）
APPROVER_THRESHOLD_CENTS = 1000


class InvoiceError(Exception):
    """开票业务错误（参数/规则）。"""


class InvoiceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        tenant_id: str,
        hotel_id: int,
        invoice_no: str | None,
        bill_id: int | None,
        booking_id: int | None,
        room_no: str | None,
        guest_name: str | None,
        agreement_no: str | None,
        check_in_at: str | None,
        check_out_at: str,
        check_in_type: str | None,
        consume_amount_cents: int,
        invoice_amount_cents: int,
        invoice_type: str,
        title: str | None,
        tax_no: str | None,
        approver: str | None,
        work_shift: str | None,
        flag: str,
        memo: str | None,
        operator: str = "front_desk",
    ) -> Invoice:
        # 校验：开票额超出消费额超过阈值 → 强制审批人
        over_issue = invoice_amount_cents - consume_amount_cents
        if over_issue > APPROVER_THRESHOLD_CENTS and not (approver and approver.strip()):
            raise InvoiceError(
                f"开票额超出消费额 {over_issue} 分（> {APPROVER_THRESHOLD_CENTS} 分阈值），"
                "需填写审批人 approver"
            )
        # 校验：专票必填税号
        if invoice_type == "VAT_SPECIAL" and not (tax_no and tax_no.strip()):
            raise InvoiceError("专票（VAT_SPECIAL）必须填写纳税人识别号 tax_no")
        # 校验：开票额非负
        if invoice_amount_cents < 0:
            raise InvoiceError("开票额不能为负")
        # 生成发票号（不传则自动生成，租户内唯一）
        if not invoice_no:
            invoice_no = f"INV{next_id()}"
        inv = Invoice(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            invoice_no=invoice_no,
            bill_id=bill_id,
            booking_id=booking_id,
            room_no=room_no,
            guest_name=guest_name,
            agreement_no=agreement_no,
            check_in_at=check_in_at,
            check_out_at=check_out_at,
            check_in_type=check_in_type,
            consume_amount_cents=consume_amount_cents,
            invoice_amount_cents=invoice_amount_cents,
            invoice_type=invoice_type,
            title=title,
            tax_no=tax_no,
            approver=approver,
            work_shift=work_shift,
            flag=flag,
            status="ISSUED",
            operator=operator,
            memo=memo,
            is_valid=True,
        )
        self.session.add(inv)
        await self.session.flush()
        return inv

    async def void(
        self, tenant_id: str, invoice_id: int, operator: str = "front_desk"
    ) -> Invoice:
        inv = await self.session.get(Invoice, invoice_id)
        if inv is None or inv.tenant_id != tenant_id:
            raise InvoiceError("发票不存在")
        if inv.status == "VOID":
            raise InvoiceError("发票已作废，不可重复作废")
        inv.status = "VOID"
        inv.operator = operator
        self.session.add(inv)
        await self.session.flush()
        return inv

    async def list(
        self,
        tenant_id: str,
        bill_id: int | None = None,
        booking_id: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Invoice]:
        """列表（带 MAX_LIST_ROWS 护栏，调用方按需传 limit/offset）。"""
        from app.api.routes import MAX_LIST_ROWS  # noqa: PLC0415 - 复用路由护栏常量

        stmt = select(Invoice).where(Invoice.tenant_id == tenant_id)
        if bill_id is not None:
            stmt = stmt.where(Invoice.bill_id == bill_id)
        if booking_id is not None:
            stmt = stmt.where(Invoice.booking_id == booking_id)
        if status:
            stmt = stmt.where(Invoice.status == status)
        stmt = stmt.order_by(Invoice.id.desc())
        stmt = stmt.offset(max(0, offset)).limit(
            MAX_LIST_ROWS if limit is None else max(1, min(limit, MAX_LIST_ROWS))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def list_by_bill(self, tenant_id: str, bill_id: int) -> list[Invoice]:
        stmt = (
            select(Invoice)
            .where(Invoice.tenant_id == tenant_id, Invoice.bill_id == bill_id)
            .order_by(Invoice.id.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())
