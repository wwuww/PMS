"""M37-④ 优惠券服务：模板 CRUD + 发券 / 核销 / 作废 / 查询。

用户拍板采用「**券模板 + 券实例**」两表：

- ``CouponTemplate`` 描述券规则（一次生成 N 张同规则券的母版）；
- ``Coupon`` 是可核销的实体券，``template_id`` 可空（兼容无模板散券）。

折扣口径（``discount_type``）：
- ``AMOUNT``：定额抵扣，``discount_value`` 即**分**；
- ``FIXED_PRICE``：定价值，``discount_value`` 即**分**（与 AMOUNT 同口径，保留语义区分）；
- ``PERCENT``：万分比（basis point，1000 = 10%），核销时须传 ``bill_id`` 以账单
  ``balance`` 为基数计算，否则拒绝核销（避免无基数凭空算折扣）。

核销时若 ``is_transfer_to_account=True`` 且传了 ``bill_id``，写一条
``BillItem(type="DISCOUNT", amount=-amount)`` 并等额冲减 ``bill.balance``（转应收）。

服务层只抛 ``ValueError``，由路由层映射 404/409。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.snowflake import next_id
from app.models import Bill, BillItem, Coupon, CouponTemplate

# 券状态机
STATUS_ISSUED = "ISSUED"
STATUS_USED = "USED"
STATUS_VOID = "VOID"
STATUS_EXPIRED = "EXPIRED"

# PERCENT 折扣的分母：discount_value 以万分比存储（1000 = 10%）
PERCENT_BASE = 10000


class CouponService:
    """优惠券领域服务（构造于请求会话）。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- 券模板 ----------------

    async def create_template(
        self,
        tenant_id: str,
        code: str,
        name: str,
        valid_from: str,
        valid_to: str,
        hotel_id: int | None = None,
        ticket_type: str = "VOUCHER",
        discount_type: str = "AMOUNT",
        discount_value: int = 0,
        total_quantity: int = 0,
        operator: str = "front_desk",
    ) -> CouponTemplate:
        """创建券模板（同租户内 ``code`` 唯一）。"""
        if valid_to < valid_from:
            raise ValueError("有效期结束日不可早于起始日")
        if discount_value < 0:
            raise ValueError("折扣值不可为负")
        if discount_type == "PERCENT" and discount_value > PERCENT_BASE:
            raise ValueError(f"折扣率（万分比）不可超过 {PERCENT_BASE}")
        dup = (
            await self.session.execute(
                select(CouponTemplate).where(
                    CouponTemplate.tenant_id == tenant_id,
                    CouponTemplate.code == code,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise ValueError(f"券模板编码 {code} 已存在")

        tpl = CouponTemplate(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            code=code,
            name=name,
            ticket_type=ticket_type,
            discount_type=discount_type,
            discount_value=discount_value,
            valid_from=valid_from,
            valid_to=valid_to,
            total_quantity=total_quantity,
            issued_quantity=0,
            is_valid=True,
            operator=operator,
        )
        self.session.add(tpl)
        await self.session.flush()
        return tpl

    async def list_templates(
        self, tenant_id: str, is_valid: bool | None = None
    ) -> list[CouponTemplate]:
        """券模板列表（默认按 id 倒序）。"""
        stmt = select(CouponTemplate).where(CouponTemplate.tenant_id == tenant_id)
        if is_valid is not None:
            stmt = stmt.where(CouponTemplate.is_valid == is_valid)
        stmt = stmt.order_by(CouponTemplate.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars())

    # ---------------- 发券 / 核销 / 作废 ----------------

    async def issue(
        self,
        tenant_id: str,
        hotel_id: int,
        template_id: int | None = None,
        count: int = 1,
        ticket_type: str | None = None,
        discount_type: str | None = None,
        discount_value: int | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        is_cover_other_discount: bool = False,
        is_transfer_to_account: bool = False,
        operator: str = "front_desk",
    ) -> list[Coupon]:
        """批量发券：可基于模板（继承规则 + 扣减发行量），也可直接给规则（散券）。"""
        if count < 1:
            raise ValueError("发券张数 count 须 >= 1")
        if count > 1000:
            raise ValueError("单次发券张数不可超过 1000")

        if template_id is not None:
            tpl = await self.session.get(CouponTemplate, template_id)
            if tpl is None or tpl.tenant_id != tenant_id:
                raise ValueError("券模板不存在")
            if not tpl.is_valid:
                raise ValueError("券模板已停用")
            if tpl.total_quantity > 0 and tpl.issued_quantity + count > tpl.total_quantity:
                raise ValueError("超出券模板发行总量")
            # 显式参数优先，缺省继承模板规则
            ticket_type = ticket_type or tpl.ticket_type
            discount_type = discount_type or tpl.discount_type
            discount_value = tpl.discount_value if discount_value is None else discount_value
            valid_from = valid_from or tpl.valid_from
            valid_to = valid_to or tpl.valid_to
            if hotel_id is None or hotel_id == 0:
                hotel_id = tpl.hotel_id or hotel_id
            tpl.issued_quantity += count
            self.session.add(tpl)

        if not valid_from or not valid_to:
            raise ValueError("有效期 valid_from / valid_to 必填（无模板发券时须显式传入）")
        if valid_to < valid_from:
            raise ValueError("有效期结束日不可早于起始日")

        coupons: list[Coupon] = []
        for _ in range(count):
            coupon = Coupon(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                template_id=template_id,
                coupon_no=f"CP{next_id()}",
                ticket_type=ticket_type or "VOUCHER",
                discount_type=discount_type or "AMOUNT",
                discount_value=int(discount_value or 0),
                valid_from=valid_from,
                valid_to=valid_to,
                status=STATUS_ISSUED,
                is_cover_other_discount=is_cover_other_discount,
                is_transfer_to_account=is_transfer_to_account,
                operator=operator,
            )
            self.session.add(coupon)
            coupons.append(coupon)
        await self.session.flush()
        return coupons

    async def use(
        self,
        tenant_id: str,
        coupon_no: str,
        booking_id: int | None = None,
        bill_id: int | None = None,
        operator: str = "front_desk",
    ) -> Coupon:
        """核销优惠券（幂等失败；过期券落 EXPIRED 后拒绝）。"""
        coupon = (
            await self.session.execute(
                select(Coupon).where(
                    Coupon.tenant_id == tenant_id,
                    Coupon.coupon_no == coupon_no,
                )
            )
        ).scalar_one_or_none()
        if coupon is None:
            raise ValueError("优惠券不存在")
        if coupon.status == STATUS_USED:
            raise ValueError("优惠券已核销")
        if coupon.status == STATUS_VOID:
            raise ValueError("优惠券已作废")

        today = date.today().isoformat()
        if coupon.valid_to < today or coupon.valid_from > today:
            coupon.status = STATUS_EXPIRED
            self.session.add(coupon)
            await self.session.flush()
            raise ValueError("优惠券已过期")

        amount = await self._resolve_amount(coupon, bill_id)

        # 转应收：写折扣流水并等额冲减账单余额
        if coupon.is_transfer_to_account and bill_id:
            bill = await self.session.get(Bill, bill_id)
            if bill is not None and bill.tenant_id == tenant_id:
                self.session.add(
                    BillItem(
                        tenant_id=tenant_id,
                        bill_id=bill.id,
                        type="DISCOUNT",
                        amount=-amount,
                        description=f"优惠券 {coupon.coupon_no}",
                        created_by=operator,
                    )
                )
                bill.balance = bill.balance - amount
                self.session.add(bill)

        coupon.status = STATUS_USED
        coupon.used_at = datetime.now(UTC).isoformat()
        coupon.booking_id = booking_id
        coupon.bill_id = bill_id
        coupon.operator = operator
        self.session.add(coupon)
        await self.session.flush()
        return coupon

    async def _resolve_amount(self, coupon: Coupon, bill_id: int | None) -> int:
        """按折扣类型计算抵扣金额（分）。

        - ``AMOUNT`` / ``FIXED_PRICE``：直接取 ``discount_value``（分）；
        - ``PERCENT``：以账单 ``balance`` 为基数按万分比折算，无 ``bill_id`` 时拒绝
          （缺少基数无法计算，宁可报错也不猜）。
        """
        if coupon.discount_type in ("AMOUNT", "FIXED_PRICE"):
            return int(coupon.discount_value or 0)
        if coupon.discount_type == "PERCENT":
            if not bill_id:
                raise ValueError("PERCENT 折扣需传入 bill_id 以计算基数")
            bill = await self.session.get(Bill, bill_id)
            if bill is None:
                raise ValueError("账单不存在，无法计算 PERCENT 折扣")
            base = max(0, int(bill.balance or 0))
            return base * int(coupon.discount_value or 0) // PERCENT_BASE
        raise ValueError(f"未知折扣类型：{coupon.discount_type}")

    async def void(self, tenant_id: str, coupon_id: int, operator: str = "front_desk") -> Coupon:
        """作废优惠券（软状态 VOID，WORM：不物理删）。"""
        coupon = await self.session.get(Coupon, coupon_id)
        if coupon is None or coupon.tenant_id != tenant_id:
            raise ValueError("优惠券不存在")
        if coupon.status == STATUS_USED:
            raise ValueError("已核销的券不可作废")
        if coupon.status == STATUS_VOID:
            return coupon  # 幂等：重复作废直接返回
        coupon.status = STATUS_VOID
        coupon.operator = operator
        self.session.add(coupon)
        await self.session.flush()
        return coupon

    async def list(  # noqa: A003 - 与既有 Service 命名保持一致
        self,
        tenant_id: str,
        status: str | None = None,
        booking_id: int | None = None,
        coupon_no: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Coupon]:
        """优惠券列表（按 id 倒序，带 MAX_LIST_ROWS 硬上限护栏）。"""
        from app.api.routes import MAX_LIST_ROWS  # noqa: PLC0415 - 延迟导入避免循环依赖

        stmt = select(Coupon).where(Coupon.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(Coupon.status == status)
        if booking_id is not None:
            stmt = stmt.where(Coupon.booking_id == booking_id)
        if coupon_no:
            stmt = stmt.where(Coupon.coupon_no == coupon_no)
        stmt = stmt.order_by(Coupon.id.desc())
        stmt = stmt.offset(max(0, offset)).limit(
            MAX_LIST_ROWS if limit is None else max(1, min(limit, MAX_LIST_ROWS))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())


__all__ = ["CouponService", "PERCENT_BASE"]
