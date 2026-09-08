"""收益管理 M15 服务：需求指数、规则化调价建议、竞品对标。

核心方法：
- demand_index：基于夜审 DailyReport 历史出租率计算需求热度（0–100）。
- recommend：给定基价 + 目标营业日 + 可选竞品价，输出建议价与可解释理由。
- 规则 tenant 级单条启用，支持读写。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyReport, PriceRecommendation, PricingRule
from app.services.notification_service import NotificationService

# 周末（周五/周六）视为高峰日
_PEAK_WEEKDAYS = {4, 5}


class YieldService:
    """收益管理（M15 简版调价建议）服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- 规则 ----

    async def get_rule(self, tenant_id: str) -> PricingRule | None:
        result = await self.session.execute(
            select(PricingRule)
            .where(PricingRule.tenant_id == tenant_id, PricingRule.enabled == 1)
            .order_by(PricingRule.id.desc())
        )
        return result.scalar_one_or_none()

    async def get_or_default_rule(self, tenant_id: str) -> PricingRule:
        rule = await self.get_rule(tenant_id)
        if rule is not None:
            return rule
        rule = PricingRule(tenant_id=tenant_id, name="default", enabled=1)
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def set_rule(self, tenant_id: str, **fields: object) -> PricingRule:
        """upsert 租户级启用规则（禁用旧规则，写入新规则）。"""
        existing = await self.get_rule(tenant_id)
        if existing is not None:
            existing.enabled = 0
            self.session.add(existing)
        rule = PricingRule(tenant_id=tenant_id, enabled=1, name="default")
        for key, value in fields.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    # ---- 需求指数 ----

    async def demand_index(
        self, tenant_id: str, hotel_id: int, window_days: int = 14
    ) -> tuple[int, int]:
        """返回 (需求指数 0–100, 采样天数)。

        需求指数 = 近 window_days 个已封账营业日出租率均值；无数据返回中性值 60。
        """
        cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        result = await self.session.execute(
            select(DailyReport.occ_pct).where(
                DailyReport.tenant_id == tenant_id,
                DailyReport.hotel_id == hotel_id,
                DailyReport.business_date >= cutoff,
            )
        )
        rows = [r for (r,) in result.all() if r is not None]
        if not rows:
            return 60, 0
        return sum(rows) // len(rows), len(rows)

    # ---- 调价建议 ----

    async def recommend(
        self,
        tenant_id: str,
        hotel_id: int,
        business_date: str,
        base_price_cents: int,
        room_type_id: int | None = None,
        competitor_price_cents: int | None = None,
        lead_time_days: int | None = None,
    ) -> PriceRecommendation:
        rule = await self.get_or_default_rule(tenant_id)
        demand_index, sample_days = await self.demand_index(tenant_id, hotel_id)

        rationale: list[str] = []
        adjustment_bps = 0

        # 1) 需求侧：高出租率上调，低出租率下调（按超出阈值比例缩放）
        if demand_index >= rule.high_occ_threshold:
            span = max(rule.high_occ_threshold, 100) - rule.high_occ_threshold
            over = demand_index - rule.high_occ_threshold
            ratio = min(over / span, 1.0) if span > 0 else 1.0
            uplift = int(rule.max_uplift_bps * ratio)
            adjustment_bps += uplift
            rationale.append(
                f"出租率高（{demand_index}%）≥阈值{rule.high_occ_threshold}%，建议上调{uplift / 100:.2f}%"
            )
        elif demand_index <= rule.low_occ_threshold:
            span = rule.low_occ_threshold
            under = rule.low_occ_threshold - demand_index
            ratio = min(under / span, 1.0) if span > 0 else 1.0
            discount = int(rule.max_discount_bps * ratio)
            adjustment_bps -= discount
            rationale.append(
                f"出租率低（{demand_index}%）≤阈值{rule.low_occ_threshold}%，建议下调{discount / 100:.2f}%"
            )
        else:
            rationale.append(f"出租率中性（{demand_index}%），维持基价")

        # 2) 周末高峰因子
        try:
            wd = datetime.strptime(business_date, "%Y-%m-%d").weekday()
        except ValueError:
            wd = 0
        if wd in _PEAK_WEEKDAYS:
            adjustment_bps += rule.weekend_uplift_bps
            rationale.append(f"周末高峰日，叠加{rule.weekend_uplift_bps / 100:.2f}%")

        # 3) 需求侧落价区间钳制
        lo = base_price_cents * (10000 - rule.max_discount_bps) // 10000
        hi = base_price_cents * (10000 + rule.max_uplift_bps) // 10000
        demand_price = base_price_cents * (10000 + adjustment_bps) // 10000
        demand_price = max(lo, min(demand_price, hi))
        recommended = demand_price

        # 4) 竞品对标
        if competitor_price_cents and competitor_price_cents > 0:
            if rule.competitor_strategy == "match":
                if recommended > competitor_price_cents:
                    recommended = competitor_price_cents
                    rationale.append(f"竞品对标(match)：建议不高于竞品价{competitor_price_cents}分")
            elif rule.competitor_strategy == "undercut":
                cap = competitor_price_cents * (10000 - rule.competitor_undercut_bps) // 10000
                if recommended > cap:
                    recommended = cap
                    rationale.append(
                        f"竞品对标(undercut)：建议不高于竞品价{(100 - rule.competitor_undercut_bps / 100):.0f}% = {cap}分"
                    )

        # 重新计算最终相对基价调整
        final_bps = (
            (recommended - base_price_cents) * 10000 // base_price_cents
            if base_price_cents > 0
            else 0
        )

        rec = PriceRecommendation(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            room_type_id=room_type_id,
            business_date=business_date,
            base_price_cents=base_price_cents,
            recommended_price_cents=recommended,
            adjustment_bps=final_bps,
            demand_index=demand_index,
            sample_days=sample_days,
            rule_id=rule.id,
            rationale=json.dumps(rationale, ensure_ascii=False),
            status="suggested",
        )
        self.session.add(rec)
        await self.session.flush()
        await self.session.refresh(rec)
        # ② 通知中心推送点：生成收益建议即提醒店长（点击深链直达建议详情）
        await NotificationService(self.session).push(
            tenant_id,
            f"新收益建议：{business_date}",
            body=(
                f"建议价 {rec.recommended_price_cents} 分"
                f"（基价 {base_price_cents}，调整 {rec.adjustment_bps / 100:.2f}%）"
            ),
            hotel_id=hotel_id,
            ref_type="yield_recommendation",
            ref_id=rec.id,
            level="info",
        )
        return rec

    async def list_recommendations(
        self,
        tenant_id: str,
        hotel_id: int | None = None,
        business_date: str | None = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> list[PriceRecommendation]:
        """调价建议快照列表（M32 性能护栏：Paged limit/offset，默认 5000 兼容既有全量拉取）。

        调方可通过 ``?limit=N&offset=M`` 走标准分页。
        """
        stmt = select(PriceRecommendation).where(PriceRecommendation.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(PriceRecommendation.hotel_id == hotel_id)
        if business_date is not None:
            stmt = stmt.where(PriceRecommendation.business_date == business_date)
        stmt = stmt.order_by(PriceRecommendation.id.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    # ---- 建议落地（M20：建议 → 价格日历闭环） ----

    # 批量应用单次最多天数（防误操作刷爆日历）
    MAX_APPLY_DAYS = 365

    async def apply_recommendation(
        self,
        tenant_id: str,
        rec_id: int,
        start: str | None = None,
        end: str | None = None,
    ) -> tuple[PriceRecommendation, int, list[str]]:
        """将「suggested」建议写入价格日历并置为 applied。

        - 不传 start/end：仅落建议日（rec.business_date）单日；
        - 传 start/end：按建议价落 [start, end] 闭区间（含建议日逻辑上无要求，
          区间内逐日 UPSERT）；上限 MAX_APPLY_DAYS 天。
        - 受集团价策边界校验（越界抛 ValueError，由路由转 403 并记录拦截）；
        - 价格日历按 (tenant, room_type, date) UPSERT；
        - 幂等：非 suggested 状态重复应用抛 ValueError("already_<status>")。

        返回 (建议, updated, dates)；updated=更新已有日历行的天数，dates=实际落价的日期列表。
        异常：ValueError("not_found" | "no_room_type" | "already_*" | "bad_range" | "range_too_long")。
        """
        from datetime import datetime as _dt, timedelta as _td  # noqa: PLC0415

        from app.models import PriceCalendar  # noqa: PLC0415
        from app.services.group_service import GroupService  # noqa: PLC0415

        rec = await self.session.get(PriceRecommendation, rec_id)
        if not rec or rec.tenant_id != tenant_id:
            raise ValueError("not_found")
        if rec.status != "suggested":
            raise ValueError(f"already_{rec.status}")
        if not rec.room_type_id:
            raise ValueError("no_room_type")

        # 计算落价日期集合
        if start or end:
            if not (start and end) or start > end:
                raise ValueError("bad_range")
            try:
                d0 = _dt.strptime(start, "%Y-%m-%d").date()
                d1 = _dt.strptime(end, "%Y-%m-%d").date()
            except ValueError as exc:
                raise ValueError("bad_range") from exc
            if (d1 - d0).days + 1 > self.MAX_APPLY_DAYS:
                raise ValueError("range_too_long")
            dates = [(d0 + _td(days=i)).strftime("%Y-%m-%d") for i in range((d1 - d0).days + 1)]
        else:
            dates = [rec.business_date]

        # 集团价格边界（M17-2 拦截语义与手工改价一致；同价同房型校验一次即可）
        group = GroupService(self.session)
        try:
            await group.assert_price_allowed(tenant_id, rec.room_type_id, rec.recommended_price_cents)
        except ValueError:
            await group.record_price_block(
                tenant_id,
                rec.room_type_id,
                rec.recommended_price_cents,
                f"yield_apply#{rec.id}",
            )
            raise

        updated = 0
        for date in dates:
            existing = await self.session.execute(
                select(PriceCalendar).where(
                    PriceCalendar.tenant_id == tenant_id,
                    PriceCalendar.room_type_id == rec.room_type_id,
                    PriceCalendar.date == date,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.price = rec.recommended_price_cents
                updated += 1
            else:
                self.session.add(
                    PriceCalendar(
                        tenant_id=tenant_id,
                        room_type_id=rec.room_type_id,
                        date=date,
                        price=rec.recommended_price_cents,
                    )
                )
        rec.status = "applied"
        await self.session.flush()
        return rec, updated, dates

    async def reject_recommendation(self, tenant_id: str, rec_id: int) -> PriceRecommendation:
        """拒绝建议（status → rejected）。异常语义同 apply。"""
        rec = await self.session.get(PriceRecommendation, rec_id)
        if not rec or rec.tenant_id != tenant_id:
            raise ValueError("not_found")
        if rec.status != "suggested":
            raise ValueError(f"already_{rec.status}")
        rec.status = "rejected"
        await self.session.flush()
        return rec
