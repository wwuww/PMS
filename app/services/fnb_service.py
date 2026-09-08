"""餐饮 POS 服务（F&B，M21）。

职责：菜品/餐桌管理、开单点菜、两种结账（挂房账 / 现金），
餐饮消费统一经 CashierService 入账到 Bill，复用既有财务口径。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Bill,
    Booking,
    BookingStatus,
    DiningTable,
    MenuItem,
    PosOrder,
    PosOrderItem,
)
from app.services.cashier_service import CashierService


class PosService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- 菜品 ----------
    async def create_menu_item(
        self,
        tenant_id: str,
        hotel_id: int,
        name: str,
        category: str,
        price_cents: int,
        is_active: int = 1,
    ) -> MenuItem:
        item = MenuItem(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            name=name,
            category=category,
            price_cents=price_cents,
            is_active=is_active,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_menu_items(
        self, tenant_id: str, hotel_id: int, active_only: bool = True
    ) -> list[MenuItem]:
        stmt = select(MenuItem).where(
            MenuItem.tenant_id == tenant_id, MenuItem.hotel_id == hotel_id
        )
        if active_only:
            stmt = stmt.where(MenuItem.is_active == 1)
        stmt = stmt.order_by(MenuItem.category, MenuItem.name)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_menu_item(
        self, item_id: int, **fields: object
    ) -> MenuItem:
        item = await self.session.get(MenuItem, item_id)
        if item is None:
            raise ValueError(f"菜品不存在：{item_id}")
        for k, v in fields.items():
            if v is not None:
                setattr(item, k, v)
        self.session.add(item)
        await self.session.flush()
        return item

    # ---------- 餐桌 ----------
    async def create_table(
        self,
        tenant_id: str,
        hotel_id: int,
        table_no: str,
        seats: int = 2,
        zone: str | None = None,
    ) -> DiningTable:
        table = DiningTable(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            table_no=table_no,
            seats=seats,
            zone=zone,
            state="free",
        )
        self.session.add(table)
        await self.session.flush()
        return table

    async def list_tables(self, tenant_id: str, hotel_id: int) -> list[DiningTable]:
        res = await self.session.execute(
            select(DiningTable).where(
                DiningTable.tenant_id == tenant_id, DiningTable.hotel_id == hotel_id
            )
        )
        return list(res.scalars().all())

    async def set_table_state(self, table_id: int, state: str) -> DiningTable:
        table = await self.session.get(DiningTable, table_id)
        if table is None:
            raise ValueError(f"餐桌不存在：{table_id}")
        if state not in ("free", "occupied", "cleaning"):
            raise ValueError("餐桌状态须为 free|occupied|cleaning")
        table.state = state
        self.session.add(table)
        await self.session.flush()
        return table

    # ---------- 开单 / 点菜 ----------
    async def open_order(
        self,
        tenant_id: str,
        hotel_id: int,
        *,
        table_id: int | None = None,
        room_no: str | None = None,
        guest_name: str | None = None,
        booking_id: int | None = None,
    ) -> PosOrder:
        if table_id is not None:
            table = await self.session.get(DiningTable, table_id)
            if table is None:
                raise ValueError(f"餐桌不存在：{table_id}")
            # 占用餐桌
            table.state = "occupied"
            self.session.add(table)
        order = PosOrder(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            table_id=table_id,
            room_no=room_no,
            guest_name=guest_name,
            booking_id=booking_id,
            status="open",
            total_cents=0,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def add_order_item(
        self,
        order_id: int,
        *,
        name: str,
        qty: int = 1,
        unit_price_cents: int = 0,
        item_id: int | None = None,
    ) -> PosOrderItem:
        order = await self.session.get(PosOrder, order_id)
        if order is None:
            raise ValueError(f"餐饮账单不存在：{order_id}")
        if order.status == "settled":
            raise ValueError("已结账账单不可再加菜")
        if qty <= 0:
            raise ValueError("数量须为正")
        # 冗余品类：取自 MenuItem（便于品类销售报表免 join），手动加菜兜底"其他"
        category = "其他"
        if item_id is not None:
            mi = await self.session.get(MenuItem, item_id)
            if mi is not None:
                if getattr(mi, "sold_out", 0):
                    raise ValueError(f"菜品「{mi.name}」已沽清，今日不可点")
                category = mi.category
        line = PosOrderItem(
            tenant_id=order.tenant_id,
            order_id=order_id,
            item_id=item_id,
            name=name,
            category=category,
            qty=qty,
            unit_price_cents=unit_price_cents,
            subtotal_cents=unit_price_cents * qty,
        )
        self.session.add(line)
        order.total_cents += line.subtotal_cents
        self.session.add(order)
        await self.session.flush()
        return line

    async def list_orders(
        self,
        tenant_id: str,
        hotel_id: int,
        status: str | None = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> list[PosOrder]:
        stmt = select(PosOrder).where(
            PosOrder.tenant_id == tenant_id, PosOrder.hotel_id == hotel_id
        )
        if status:
            stmt = stmt.where(PosOrder.status == status)
        # M30 性能护栏：时序数据按 limit/offset 分页，避免拉全表
        stmt = stmt.order_by(PosOrder.id.desc()).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    # ---------- 沽清 / 退菜 / 折扣（M27） ----------

    async def set_menu_sold_out(
        self, tenant_id: str, item_id: int, sold_out: bool, operator: str = "fnb"
    ) -> MenuItem:
        """沽清 / 恢复供应（当日售罄标记，拒点但不影响在售状态 is_active）。"""
        mi = await self.session.get(MenuItem, item_id)
        if mi is None or mi.tenant_id != tenant_id:
            raise ValueError("菜品不存在")
        mi.sold_out = 1 if sold_out else 0
        self.session.add(mi)
        await self.session.flush()
        return mi

    async def void_order_item(
        self,
        order_id: int,
        item_id: int,
        reason: str = "",
        operator: str = "fnb",
    ) -> PosOrderItem:
        """退菜（M27）：仅未结算账单；明细置 voided 并从总额扣减。"""
        order = await self.session.get(PosOrder, order_id)
        if order is None:
            raise ValueError(f"餐饮账单不存在：{order_id}")
        if order.status == "settled":
            raise ValueError("已结账账单不可退菜，请走冲减调账")
        line = await self.session.get(PosOrderItem, item_id)
        if line is None or line.order_id != order_id or line.tenant_id != order.tenant_id:
            raise ValueError("点菜明细不存在")
        if line.voided:
            raise ValueError("该明细已退过")
        line.voided = 1
        line.void_reason = reason[:128] or None
        order.total_cents -= line.subtotal_cents
        if order.total_cents < 0:
            order.total_cents = 0
        # 折扣不得超过新总额
        if (order.discount_cents or 0) > order.total_cents:
            order.discount_cents = order.total_cents
        self.session.add(line)
        self.session.add(order)
        await self.session.flush()
        return line

    async def apply_order_discount(
        self,
        order_id: int,
        *,
        discount_cents: int | None = None,
        percent: int | None = None,
        operator: str = "fnb",
    ) -> PosOrder:
        """整单折扣（M27）：按金额（分）或百分比（1-99）二选一。"""
        order = await self.session.get(PosOrder, order_id)
        if order is None:
            raise ValueError(f"餐饮账单不存在：{order_id}")
        if order.status == "settled":
            raise ValueError("已结账账单不可再折扣")
        if discount_cents is None and percent is None:
            raise ValueError("须提供 discount_cents 或 percent 之一")
        if discount_cents is not None:
            if discount_cents < 0:
                raise ValueError("折扣不能为负")
        else:
            if not 1 <= int(percent) <= 99:
                raise ValueError("折扣百分比须在 1-99 之间")
            discount_cents = order.total_cents * int(percent) // 100
        if discount_cents > order.total_cents:
            raise ValueError("折扣不能超过账单总额")
        order.discount_cents = discount_cents
        self.session.add(order)
        await self.session.flush()
        return order

    # ---------- 结账 ----------
    async def settle_room(
        self, order_id: int, room_no: str, operator: str = "fnb"
    ) -> PosOrder:
        """挂房账：消费计入客房在开账单（无在住预订则开街客账）。"""
        order = await self.session.get(PosOrder, order_id)
        if order is None:
            raise ValueError(f"餐饮账单不存在：{order_id}")
        if order.status == "settled":
            raise ValueError("账单已结账")
        if order.total_cents <= 0:
            raise ValueError("账单金额为 0，无法结账")

        booking_id = await self._resolve_booking_id(order.tenant_id, room_no)
        payable = order.total_cents - (order.discount_cents or 0)
        if payable <= 0:
            raise ValueError("折后金额为 0，无法结账（请核对折扣）")
        cs = CashierService(self.session)
        bill = await cs.open_bill(
            order.tenant_id,
            order.hotel_id,
            guest_name=order.guest_name or f"客房{room_no}",
            room_no=room_no,
            booking_id=booking_id,
            source="FNB",
        )
        await cs.add_charge(
            bill,
            "FNB",
            payable,
            description=f"餐饮消费（单#{order.id}）",
            operator=operator,
        )
        # 餐饮挂账通常随房账在退房时结，这里保持 OPEN（不立即 settle）
        order.settle_type = "room"
        order.room_no = room_no
        order.booking_id = booking_id
        order.status = "settled"
        self.session.add(order)
        await self._release_table(order)
        await self.session.flush()
        return order

    async def settle_cash(
        self, order_id: int, amount_paid: int | None = None, operator: str = "fnb"
    ) -> PosOrder:
        """现金结账：开单→加应收→收款→平账。"""
        order = await self.session.get(PosOrder, order_id)
        if order is None:
            raise ValueError(f"餐饮账单不存在：{order_id}")
        if order.status == "settled":
            raise ValueError("账单已结账")
        if order.total_cents <= (order.discount_cents or 0):
            raise ValueError("账单金额为 0，无法结账")

        payable = order.total_cents - (order.discount_cents or 0)
        cs = CashierService(self.session)
        bill = await cs.open_bill(
            order.tenant_id,
            order.hotel_id,
            guest_name=order.guest_name or "餐饮散客",
            source="FNB",
        )
        await cs.add_charge(
            bill,
            "FNB",
            payable,
            description=f"餐饮消费（单#{order.id}）",
            operator=operator,
        )
        paid = amount_paid if amount_paid and amount_paid > 0 else payable
        if paid < payable:
            raise ValueError("收款不足，无法现金结账")
        await cs.take_payment(bill, "CASH", paid, operator=operator)
        # settle 内部 commit
        await cs.settle(bill, operator=operator)

        order.settle_type = "cash"
        order.status = "settled"
        self.session.add(order)
        await self._release_table(order)
        await self.session.flush()
        return order

    # ---------- 报表（餐饮销售分析，M22） ----------
    async def report_sales(
        self,
        tenant_id: str,
        hotel_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        """聚合餐饮销售：总营收 / 单数 / 品类销售 / 桌均消费。

        仅统计已结账(settled)餐饮账单；时间范围按 ``PosOrder.created_at`` 过滤。
        """
        # 已结账餐饮账单（带桌号）
        ord_stmt = select(PosOrder).where(
            PosOrder.tenant_id == tenant_id,
            PosOrder.hotel_id == hotel_id,
            PosOrder.status == "settled",
        )
        if start is not None:
            ord_stmt = ord_stmt.where(PosOrder.created_at >= start)
        if end is not None:
            ord_stmt = ord_stmt.where(PosOrder.created_at <= end)
        orders = list((await self.session.execute(ord_stmt)).scalars().all())

        # 关联点菜明细
        item_stmt = (
            select(PosOrderItem)
            .join(PosOrder, PosOrderItem.order_id == PosOrder.id)
            .where(
                PosOrder.tenant_id == tenant_id,
                PosOrder.hotel_id == hotel_id,
                PosOrder.status == "settled",
            )
        )
        if start is not None:
            item_stmt = item_stmt.where(PosOrder.created_at >= start)
        if end is not None:
            item_stmt = item_stmt.where(PosOrder.created_at <= end)
        items = list((await self.session.execute(item_stmt)).scalars().all())

        total_revenue_cents = sum(
            o.total_cents - (o.discount_cents or 0) for o in orders
        )  # M27：折后净额
        order_count = len(orders)
        item_count = sum(i.qty for i in items)

        # 品类销售
        cat: dict[str, dict[str, int]] = defaultdict(lambda: {"qty": 0, "revenue_cents": 0})
        for i in items:
            key = i.category or "其他"
            cat[key]["qty"] += i.qty
            if getattr(i, "voided", 0):
                continue  # M27：退菜行不计品类销售
            cat[key]["revenue_cents"] += i.subtotal_cents
        by_category = [
            {"category": k, "qty": v["qty"], "revenue_cents": v["revenue_cents"]}
            for k, v in sorted(cat.items(), key=lambda kv: -kv[1]["revenue_cents"])
        ]

        # 桌均消费（仅统计关联餐桌的账单）
        table_rows = (
            await self.session.execute(
                select(DiningTable).where(
                    DiningTable.tenant_id == tenant_id,
                    DiningTable.hotel_id == hotel_id,
                )
            )
        ).scalars().all()
        table_map = {t.id: t.table_no for t in table_rows}
        table_rev: dict[str, dict[str, int]] = defaultdict(
            lambda: {"order_count": 0, "revenue_cents": 0}
        )
        for o in orders:
            if not o.table_id:
                continue
            table_no = table_map.get(o.table_id, f"#{o.table_id}")
            table_rev[table_no]["order_count"] += 1
            table_rev[table_no]["revenue_cents"] += o.total_cents - (
                o.discount_cents or 0
            )
        by_table = [
            {
                "table_no": k,
                "order_count": v["order_count"],
                "revenue_cents": v["revenue_cents"],
            }
            for k, v in sorted(table_rev.items())
        ]
        table_order_total = sum(v["revenue_cents"] for v in table_rev.values())
        table_count = len(table_rev)
        avg_per_table_cents = (
            table_order_total // table_count if table_count else 0
        )

        return {
            "total_revenue_cents": total_revenue_cents,
            "order_count": order_count,
            "item_count": item_count,
            "avg_per_table_cents": avg_per_table_cents,
            "by_category": by_category,
            "by_table": by_table,
        }

    # ---------- 厨房出单（KDS，M22 + M30 性能优化 #4 审计 B2） ----------
    async def list_kitchen_tickets(
        self,
        tenant_id: str,
        hotel_id: int,
        states: tuple[str, ...] = ("pending", "ready"),
        limit: int = 200,
    ) -> list[dict]:
        """厨房出单屏：单次 JOIN 取齐 item + 订单上下文（房号/客人/桌号），消除 N+1。

        原逐房版本：1 + 2N 查询（50 个菜 ≈ 101 次），改为固定 1 次。
        ORDER BY id asc 保持按下单顺序；limit 默认 200 防失控（D1 列表护栏）。
        """
        stmt = (
            select(
                PosOrderItem.id.label("item_id"),
                PosOrderItem.order_id,
                PosOrder.room_no,
                PosOrder.guest_name,
                PosOrder.table_id,
                DiningTable.table_no,
                PosOrderItem.name,
                PosOrderItem.category,
                PosOrderItem.qty,
                PosOrderItem.kds_status,
            )
            .join(PosOrder, PosOrderItem.order_id == PosOrder.id)
            .outerjoin(DiningTable, PosOrder.table_id == DiningTable.id)
            .where(
                PosOrder.tenant_id == tenant_id,
                PosOrder.hotel_id == hotel_id,
                PosOrderItem.kds_status.in_(states),
                PosOrderItem.voided == 0,  # M27：退菜行不出现在厨房屏
            )
            .order_by(PosOrderItem.id.asc())
            .limit(limit)
        )
        tickets = []
        for row in (await self.session.execute(stmt)).all():
            tickets.append(
                {
                    "item_id": row.item_id,
                    "order_id": row.order_id,
                    "table_no": row.table_no,       # outer join → 无桌号为 None
                    "room_no": row.room_no,
                    "guest_name": row.guest_name,
                    "name": row.name,
                    "category": row.category,
                    "qty": row.qty,
                    "kds_status": row.kds_status,
                }
            )
        return tickets

    async def _set_kds_status(self, item_id: int, status: str) -> PosOrderItem:
        item = await self.session.get(PosOrderItem, item_id)
        if item is None:
            raise ValueError(f"点菜明细不存在：{item_id}")
        item.kds_status = status
        self.session.add(item)
        await self.session.flush()
        return item

    async def mark_item_ready(self, item_id: int) -> PosOrderItem:
        """标记出餐（待做 → 已出餐）。"""
        return await self._set_kds_status(item_id, "ready")

    async def mark_item_served(self, item_id: int) -> PosOrderItem:
        """标记上菜（已出餐 → 已上菜）。"""
        return await self._set_kds_status(item_id, "served")

    # ---- 内部辅助 ----
    async def _resolve_booking_id(
        self, tenant_id: str, room_no: str
    ) -> int | None:
        """按房号解析在住预订（用于挂房账）。无在住则返回 None（开街客账）。"""
        res = await self.session.execute(
            select(Booking).where(
                Booking.tenant_id == tenant_id,
                Booking.room_no == room_no,
                Booking.status == BookingStatus.CHECKED_IN.value,
            )
        )
        bk = res.scalars().first()
        return bk.id if bk else None

    async def room_lookup(self, tenant_id: str, room_no: str) -> dict:
        """M32（验收 #48）：挂账前按房号查询在住客人信息，防挂错。

        返回在住预订的客人姓名/手机号（脱敏）/离店日期 + 在开账单余额；
        无在住客人时 occupied=False（前台确认后可开街客账）。
        """
        res = await self.session.execute(
            select(Booking)
            .where(
                Booking.tenant_id == tenant_id,
                Booking.room_no == room_no,
                Booking.status == BookingStatus.CHECKED_IN.value,
            )
            .order_by(Booking.id.desc())
        )
        bk = res.scalars().first()
        if bk is None:
            return {"room_no": room_no, "occupied": False, "warning": "该房无在住客人，挂账将开街客账"}
        bill = (
            await self.session.execute(
                select(Bill).where(
                    Bill.tenant_id == tenant_id,
                    Bill.booking_id == bk.id,
                    Bill.status == "OPEN",
                )
            )
        ).scalars().first()
        phone = bk.guest_phone or ""
        masked = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else (phone or None)
        return {
            "room_no": room_no,
            "occupied": True,
            "guest_name": bk.guest_name,
            "guest_phone_masked": masked,
            "check_out_date": bk.check_out_date.isoformat()
            if bk.check_out_date and hasattr(bk.check_out_date, "isoformat")
            else bk.check_out_date,
            "bill_id": bill.id if bill else None,
            "bill_balance": bill.balance if bill else None,
        }

    async def _release_table(self, order: PosOrder) -> None:
        if not order.table_id:
            return
        table = await self.session.get(DiningTable, order.table_id)
        if table is not None:
            table.state = "cleaning"
            self.session.add(table)
