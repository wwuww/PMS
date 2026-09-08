"""夜审自动调度骨架（M4-2，FR-YS-02）。

生产环境由 Celery 按租户分波错峰触发（dev-plan 2.2.3）；本服务封装「跑批」语义，
可被调度器或直接调用：

- 遍历租户下全部酒店；
- 对每个酒店，取出状态为 OPEN / SUSPENDED 且 business_date <= as_of 的营业日；
  若该日无待审营业日：已 CLOSED（当日已夜审）则跳过，不存在才为 as_of 建一条 OPEN（代表「今夜应审」）；
- 逐日调用 NightAuditService.run_night_audit；
- 单日异常被捕获后置为 SUSPENDED 并记录原因，不阻断其余日（异常挂起）。

注意（Sprint 14 修复）：此前「无待审日即插入 as_of」的写法会在当日已 CLOSED 时撞
business_days(hotel_id, business_date) 唯一约束，且该插入在异常隔离块之外，直接导致
auto-run 接口 500。现改为先查重、已审则跳过。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BusinessDay, Hotel
from app.services.night_audit_service import NightAuditService


def _categorize_suspended(exc: Exception) -> str:
    """将夜审异常归因为可读分类，便于前端分组展示与运营干预。

    不依赖具体异常类型（未来新增异常也只会落入「未知异常」），仅按消息关键字匹配，
    保证挂账原因稳定可读。
    """
    msg = str(exc)
    m = msg.lower()
    if "multiple rows were found" in m or "multipleresultsfound" in m:
        return "重复入住脏数据"
    if "room_type" in m and ("不存在" in msg or "none" in m):
        return "房型数据缺失"
    if "非法流转" in msg or "invalidtransition" in m:
        return "房态流转非法"
    if "integrityerror" in m or "约束" in msg or "constraint" in m or "unique" in m:
        return "数据完整性冲突"
    if "timeout" in m or "连接" in msg or "connection" in m:
        return "数据库/连接异常"
    return "未知异常"


class NightAuditScheduler:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def auto_run(
        self, tenant_id: str, as_of: str, operator: str = "scheduler"
    ) -> dict:
        """批量夜审。返回 {ran, suspended, skipped, errors, skips}。"""
        hotels = list(
            (await self.session.execute(select(Hotel).where(Hotel.tenant_id == tenant_id)))
            .scalars()
            .all()
        )
        ran = 0
        suspended = 0
        skipped = 0
        skips: list[dict] = []
        errors: list[dict] = []

        for hotel in hotels:
            hotel_id = hotel.id
            pending = list(
                (
                    await self.session.execute(
                        select(BusinessDay)
                        .where(
                            BusinessDay.hotel_id == hotel_id,
                            BusinessDay.business_date <= as_of,
                            BusinessDay.status.in_(["OPEN", "SUSPENDED"]),
                        )
                        .order_by(BusinessDay.business_date)
                    )
                )
                .scalars()
                .all()
            )
            if not pending:
                # 无待审日：先查重。当日已 CLOSED（已夜审）→ 跳过，不可重复插入；
                # 仅当日不存在任何营业日时，才为 as_of 建一条 OPEN（今夜应审）。
                same_day = (
                    await self.session.execute(
                        select(BusinessDay).where(
                            BusinessDay.hotel_id == hotel_id,
                            BusinessDay.business_date == as_of,
                        )
                    )
                ).scalar_one_or_none()
                if same_day is not None:
                    # 只在 CLOSED（已审）时计数跳过；其它状态（理论不到）也保守跳过
                    skipped += 1
                    skips.append(
                        {
                            "hotel_id": hotel_id,
                            "business_date": as_of,
                            "status": same_day.status,
                            "reason": f"营业日 {as_of} 状态为 {same_day.status}，本次跳过",
                        }
                    )
                    continue
                bd = BusinessDay(
                    tenant_id=tenant_id,
                    hotel_id=hotel_id,
                    business_date=as_of,
                    status="OPEN",
                )
                self.session.add(bd)
                await self.session.flush()
                await self.session.commit()
                pending = [bd]

            for bd in pending:
                bd_id = bd.id
                bd_date = bd.business_date
                try:
                    await NightAuditService(self.session).run_night_audit(
                        tenant_id, hotel_id, bd_date, operator
                    )
                    ran += 1
                except Exception as exc:  # noqa: BLE001 — 单日失败隔离，不阻断整批
                    await self.session.rollback()
                    fresh = await self.session.get(BusinessDay, bd_id)
                    if fresh is not None:
                        fresh.status = "SUSPENDED"
                        fresh.suspended_reason = f"[{_categorize_suspended(exc)}] {str(exc)}"[:255]
                        self.session.add(fresh)
                        await self.session.commit()
                    suspended += 1
                    errors.append(
                        {
                            "hotel_id": hotel_id,
                            "business_date": bd_date,
                            "error": str(exc),
                        }
                    )

        return {
            "ran": ran,
            "suspended": suspended,
            "skipped": skipped,
            "errors": errors,
            "skips": skips,
        }
