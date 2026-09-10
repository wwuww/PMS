"""M37-④ 早餐券服务：发放 / 核销 / 作废 / 查询。

对齐维也纳 PMS 数据字典 ``Breakfast``：
- 发券：一次 ``count`` 张，券号 ``BF{snowflake}``（租户内唯一）；
- 核销：幂等——已核销再核返回冲突（路由映射 409）；过期（营业日 > valid_to）拒绝；
- 作废：软删 ``is_valid=False``（WORM），已核销的券不可作废。

服务层只抛 ``ValueError``（业务冲突/参数错误），由路由层统一映射 HTTP 状态码。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.snowflake import next_id
from app.models import BreakfastTicket


class BreakfastService:
    """早餐券领域服务（构造于请求会话）。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def issue(
        self,
        tenant_id: str,
        hotel_id: int,
        booking_id: int | None = None,
        room_no: str | None = None,
        ticket_type: int = 0,
        ticket_type_name: str | None = None,
        count: int = 1,
        valid_from: str | None = None,
        valid_to: str | None = None,
        card_type: int = 0,
        memo: str | None = None,
        operator: str = "front_desk",
    ) -> list[BreakfastTicket]:
        """批量发券（一次 ``count`` 张同规则券）。

        券号由雪花 ID 生成（``BF{id}``），租户内唯一；校验通过后 flush 不 commit，
        由路由层统一提交事务。
        """
        if count < 1:
            raise ValueError("发券张数 count 须 >= 1")
        if count > 100:
            raise ValueError("单次发券张数不可超过 100")
        if valid_from and valid_to and valid_to < valid_from:
            raise ValueError("有效期结束日不可早于起始日")

        tickets: list[BreakfastTicket] = []
        for _ in range(count):
            ticket = BreakfastTicket(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                ticket_no=f"BF{next_id()}",
                booking_id=booking_id,
                room_no=room_no,
                card_type=card_type,
                ticket_type=ticket_type,
                ticket_type_name=ticket_type_name,
                valid_from=valid_from,
                valid_to=valid_to,
                is_used=False,
                is_valid=True,
                operator=operator,
                memo=memo,
            )
            self.session.add(ticket)
            tickets.append(ticket)
        await self.session.flush()
        return tickets

    async def use(
        self,
        tenant_id: str,
        ticket_no: str,
        business_date: str,
        operator: str = "front_desk",
    ) -> BreakfastTicket:
        """核销早餐券（幂等失败而非静默成功）。

        - 券不存在 → ``ValueError("早餐券不存在")``（路由 404→409 由调用方决定）；
        - 已核销 → ``ValueError("早餐券已核销")``（409）；
        - 已作废 → ``ValueError("早餐券已作废")``（409）；
        - 营业日晚于有效期 → ``ValueError("早餐券已过期")``（409）。
        """
        ticket = (
            await self.session.execute(
                select(BreakfastTicket).where(
                    BreakfastTicket.tenant_id == tenant_id,
                    BreakfastTicket.ticket_no == ticket_no,
                )
            )
        ).scalar_one_or_none()
        if ticket is None:
            raise ValueError("早餐券不存在")
        if not ticket.is_valid:
            raise ValueError("早餐券已作废")
        if ticket.is_used:
            raise ValueError("早餐券已核销")
        if ticket.valid_to and business_date > ticket.valid_to:
            raise ValueError("早餐券已过期")

        ticket.is_used = True
        ticket.used_business_date = business_date
        ticket.operator = operator
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def void(self, tenant_id: str, ticket_id: int, operator: str = "front_desk") -> BreakfastTicket:
        """作废早餐券（软删 WORM：仅置 ``is_valid=False``）。"""
        ticket = await self.session.get(BreakfastTicket, ticket_id)
        if ticket is None or ticket.tenant_id != tenant_id:
            raise ValueError("早餐券不存在")
        if ticket.is_used:
            raise ValueError("已核销的券不可作废")
        if not ticket.is_valid:
            return ticket  # 幂等：重复作废直接返回
        ticket.is_valid = False
        ticket.operator = operator
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def list(  # noqa: A003 - 与既有 Service 命名保持一致
        self,
        tenant_id: str,
        booking_id: int | None = None,
        ticket_type: int | None = None,
        is_used: bool | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[BreakfastTicket]:
        """早餐券列表（按 id 倒序，带 MAX_LIST_ROWS 硬上限护栏）。"""
        from app.api.routes import MAX_LIST_ROWS  # noqa: PLC0415 - 延迟导入避免循环依赖

        stmt = select(BreakfastTicket).where(BreakfastTicket.tenant_id == tenant_id)
        if booking_id is not None:
            stmt = stmt.where(BreakfastTicket.booking_id == booking_id)
        if ticket_type is not None:
            stmt = stmt.where(BreakfastTicket.ticket_type == ticket_type)
        if is_used is not None:
            stmt = stmt.where(BreakfastTicket.is_used == is_used)
        if date_from:
            stmt = stmt.where(BreakfastTicket.valid_to.isnot(None))
            stmt = stmt.where(BreakfastTicket.valid_to >= date_from)
        if date_to:
            stmt = stmt.where(BreakfastTicket.valid_from.isnot(None))
            stmt = stmt.where(BreakfastTicket.valid_from <= date_to)
        stmt = stmt.order_by(BreakfastTicket.id.desc())
        stmt = stmt.offset(max(0, offset)).limit(
            MAX_LIST_ROWS if limit is None else max(1, min(limit, MAX_LIST_ROWS))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())


__all__ = ["BreakfastService"]
