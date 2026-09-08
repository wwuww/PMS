"""协议单位挂账/月结服务（M24，验收清单 #10）。

挂账 = 结账时以 COMPANY 方式「收款」，账单转 SETTLED 并回填 ar_account_id，
协议单位 balance_cents（未清欠款）同步增加；还款冲减欠款并落 ArRepayment 流水。
金额统一「分」。信用额度 credit_limit_cents > 0 时挂账后不得超额。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ArAccount, ArRepayment, Bill
from app.services.audit_service import record as audit_record
from app.services.cashier_service import CashierService


class CreditLimitExceeded(ValueError):
    """挂账超出信用额度。"""


class ArService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- 账户管理 ----

    async def list_accounts(
        self, tenant_id: str, hotel_id: int | None = None
    ) -> list[ArAccount]:
        stmt = select(ArAccount).where(
            ArAccount.tenant_id == tenant_id, ArAccount.status == "ACTIVE"
        )
        if hotel_id is not None:
            stmt = stmt.where(ArAccount.hotel_id == hotel_id)
        r = await self.session.execute(stmt.order_by(ArAccount.id.desc()))
        return list(r.scalars())

    async def get_account(self, tenant_id: str, account_id: int) -> ArAccount:
        acct = await self.session.get(ArAccount, account_id)
        if acct is None or acct.tenant_id != tenant_id:
            raise ValueError("协议单位不存在")
        return acct

    async def create_account(
        self,
        tenant_id: str,
        hotel_id: int,
        name: str,
        contact: str | None = None,
        contact_phone: str | None = None,
        credit_limit_cents: int = 0,
        note: str | None = None,
        operator: str = "front_desk",
    ) -> ArAccount:
        if credit_limit_cents < 0:
            raise ValueError("信用额度不能为负")
        acct = ArAccount(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            name=name,
            contact=contact,
            contact_phone=contact_phone,
            credit_limit_cents=credit_limit_cents,
            note=note,
        )
        self.session.add(acct)
        await self.session.flush()
        await audit_record(
            self.session,
            tenant_id,
            "ar.account.create",
            actor=operator,
            resource_type="ar_account",
            resource_id=acct.id,
            hotel_id=hotel_id,
            detail={"name": name, "credit_limit_cents": credit_limit_cents},
        )
        return acct

    # ---- 挂账结账 ----

    async def settle_to_account(
        self,
        tenant_id: str,
        account_id: int,
        bill: Bill,
        operator: str = "front_desk",
    ) -> Bill:
        """把账单余额挂到协议单位（结账方式 COMPANY）。"""
        acct = await self.get_account(tenant_id, account_id)
        if bill.status == "SETTLED":
            raise ValueError("账单已结清")
        if bill.tenant_id != tenant_id:
            raise ValueError("账单不属于该租户")
        outstanding = bill.balance
        if outstanding <= 0:
            raise ValueError("账单无应收余额，无需挂账")
        if (
            acct.credit_limit_cents > 0
            and acct.balance_cents + outstanding > acct.credit_limit_cents
        ):
            raise CreditLimitExceeded(
                f"超出信用额度（欠款 {acct.balance_cents} + 本次 {outstanding}"
                f" > 额度 {acct.credit_limit_cents} 分）"
            )

        cs = CashierService(self.session)
        await cs.take_payment(bill, "COMPANY", outstanding, operator=operator)
        bill.ar_account_id = acct.id
        acct.balance_cents += outstanding
        await cs.settle(bill, operator=operator)  # 平账 → SETTLED + 事件

        await audit_record(
            self.session,
            tenant_id,
            "ar.bill.charge",
            actor=operator,
            resource_type="bill",
            resource_id=bill.id,
            hotel_id=bill.hotel_id,
            detail={
                "account_id": acct.id,
                "amount_cents": outstanding,
            },
        )
        return bill

    async def list_bills(self, tenant_id: str, account_id: int) -> list[Bill]:
        await self.get_account(tenant_id, account_id)
        r = await self.session.execute(
            select(Bill)
            .where(Bill.tenant_id == tenant_id, Bill.ar_account_id == account_id)
            .order_by(Bill.id.desc())
        )
        return list(r.scalars())

    # ---- 还款（月结回款） ----

    async def repay(
        self,
        tenant_id: str,
        account_id: int,
        amount: int,
        method: str = "BANK",
        operator: str = "front_desk",
        note: str | None = None,
    ) -> tuple[ArAccount, ArRepayment]:
        acct = await self.get_account(tenant_id, account_id)
        if amount <= 0:
            raise ValueError("还款金额必须为正")
        if amount > acct.balance_cents:
            raise ValueError(
                f"还款额超过欠款（欠款 {acct.balance_cents} 分）"
            )
        acct.balance_cents -= amount
        rep = ArRepayment(
            tenant_id=tenant_id,
            ar_account_id=acct.id,
            amount=amount,
            method=method,
            operator=operator,
            note=note,
        )
        self.session.add(rep)
        await self.session.flush()
        await audit_record(
            self.session,
            tenant_id,
            "ar.repay",
            actor=operator,
            resource_type="ar_account",
            resource_id=acct.id,
            hotel_id=acct.hotel_id,
            detail={"amount_cents": amount, "method": method},
        )
        return acct, rep
