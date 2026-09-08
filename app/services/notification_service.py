"""消息推送中心（M10-4，FR-APP-04）：日报推送 / 待办提醒，已读回执 + 点击深链跳转。"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.models import (
    DailyReport,
    Notification,
    NotificationPreference,
    NotificationSubscription,
)
from app.models.rbac import ROLE_LEVEL_ADMIN, ROLE_LEVEL_MANAGER, ROLE_LEVEL_STAFF, Role

# ref_type -> 前端路由模板（{id} 占位 ref_id）；push 未显式传 link 时自动推导
REF_LINK_TEMPLATES: dict[str, str] = {
    "daily_report": "/reports?type=dashboard",
    "chat_session": "/ai-chat?session={id}",
    "booking": "/bookings?booking={id}",
    "bill": "/billing?bill={id}",
    "bill_item": "/billing?bill_item={id}",
    "payment": "/billing?payment={id}",
    "alert": "/alerts?alert={id}",
    "approval": "/approvals?ticket={id}",
    "task": "/housekeeping?task={id}",
    "yield_recommendation": "/yield?rec={id}",
    "commission_reconciliation": "/commission?recon={id}",
}

# ref_type -> 中文标签（通知中心列表展示用）
REF_LABELS: dict[str, str] = {
    "daily_report": "营业日报",
    "chat_session": "AI客服转人工",
    "booking": "预订",
    "bill": "账单",
    "bill_item": "账单明细",
    "payment": "收款",
    "alert": "风险预警",
    "approval": "审批待办",
    "task": "清扫工单",
    "yield_recommendation": "收益建议",
    "commission_reconciliation": "佣金对账",
}

# ③ 通知分级
NOTIF_LEVELS = ("critical", "normal", "info")
# 免打扰时段内仍可突破的级别（风险预警始终触达）
BREAKTHROUGH_LEVELS = frozenset({"critical"})

# ④ 缺订阅配置时的默认接收角色（与历史单 recipient 语义对齐）。
# 键即 REF_LINK_TEMPLATES 中的 ref_type；未列出的 ref_type 回落到 push 的 recipient 形参。
DEFAULT_SUBSCRIBERS: dict[str, list[str]] = {
    "daily_report": ["store_manager"],
    "chat_session": ["front_desk"],
    "approval": ["store_manager"],
    "task": ["front_desk", "store_manager"],
    "yield_recommendation": ["store_manager"],
    "alert": ["store_manager"],
    "booking": ["front_desk"],
    "bill": ["front_desk"],
    "bill_item": ["front_desk"],
    "payment": ["front_desk"],
    "commission_reconciliation": ["store_manager"],
}

# ⑥ RBAC 角色档位 → 通知接收标签（与 ④ recipients 标签对齐：store_manager/front_desk/night_audit）
# ADMIN 全量可见；MANAGER 收店长类；STAFF 收前台类；night_audit 暂无独立角色，仅 ADMIN 覆盖。
# 与 ws.py 共享同一份映射，保证实时推送与列表读取走同一套 recipients 路由。
ROLE_TAG_MAP: dict[str, set[str]] = {
    ROLE_LEVEL_ADMIN: {"store_manager", "front_desk", "night_audit"},
    ROLE_LEVEL_MANAGER: {"store_manager"},
    ROLE_LEVEL_STAFF: {"front_desk"},
}


def recipient_tags_for_roles(levels: Iterable[str]) -> set[str]:
    """将用户角色档位集合映射为通知接收标签集合（⑥ 列表行级可见性用）。"""
    tags: set[str] = set()
    for lvl in levels:
        tags.update(ROLE_TAG_MAP.get(lvl, set()))
    return tags


def notification_visible_to(recipients: list[str], user_tags: set[str]) -> bool:
    """⑥ 读取/已读行级可见性：与本人标签有交集才可见；空 recipients 对任何人不可见。

    与 WS `notification_matches` 同口径但忽略 `muted`——③ 免打扰项在通知中心仍可见，
    故已读标记不应以静音为由拒绝（仅按 recipients 角色路由）。
    """
    return bool(set(recipients or []) & user_tags)


def build_link(ref_type: str | None, ref_id: int | None) -> str | None:
    """按 ref_type 推导前端深链；无法推导返回 None（前端退化为只标记已读）。"""
    if not ref_type:
        return None
    tpl = REF_LINK_TEMPLATES.get(ref_type)
    if not tpl:
        return None
    if "{id}" in tpl:
        if ref_id is None:
            return None
        return tpl.replace("{id}", str(ref_id))
    return tpl


def in_dnd_window(now: datetime, start: str, end: str) -> bool:
    """判断本地时间 now 是否落在 [start, end) 安静时段；支持跨午夜（22:00–08:00）。

    start/end 为 'HH:MM'。start == end 视为不启用。
    """
    try:
        sh, sm = (int(x) for x in start.split(":"))
        eh, em = (int(x) for x in end.split(":"))
    except (ValueError, TypeError):
        return False
    cur = now.hour * 60 + now.minute
    s = sh * 60 + sm
    e = eh * 60 + em
    if s == e:
        return False
    if s < e:
        return s <= cur <= e
    return cur >= s or cur <= e  # 跨午夜


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def push(
        self,
        tenant_id: str,
        title: str,
        body: str = "",
        hotel_id: int | None = None,
        recipient: str = "store_manager",
        channel: str = "APP",
        ref_type: str | None = None,
        ref_id: int | None = None,
        link: str | None = None,
        level: str = "normal",
        recipients: list[str] | None = None,
    ) -> Notification:
        if level not in NOTIF_LEVELS:
            level = "normal"
        # ④ 多接收人解析：显式 recipients 优先；否则按 ref_type 查订阅配置；
        # 均无则回落到历史单 recipient（再无则空列表）。订阅配置让「谁收到」可运营。
        resolved = recipients
        if resolved is None:
            resolved = await self.get_subscribers(tenant_id, ref_type, fallback=recipient)
        n = Notification(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            recipient=recipient,
            channel=channel,
            title=title,
            body=body,
            ref_type=ref_type,
            ref_id=ref_id,
            level=level,
            recipients=resolved or [],
            link=link if link is not None else build_link(ref_type, ref_id),
        )
        self.session.add(n)
        await self.session.flush()
        # ③ 免打扰：处于安静时段且非突破级别 → 静音（不计入未读角标，打开通知中心仍可见）
        pref = await self.get_preference(tenant_id)
        if pref and pref.dnd_enabled and level not in BREAKTHROUGH_LEVELS:
            local_now = datetime.now(UTC).astimezone()
            if in_dnd_window(local_now, pref.dnd_start, pref.dnd_end):
                n.muted = True
                self.session.add(n)
                await self.session.flush()
        # ⑤ 实时推送：落库后发布领域事件，供 WebSocket 网关按 recipients 角色路由扇出。
        # 发布失败不应影响通知落库（解耦：WS/Webhook 均为订阅方，非关键路径）。
        try:
            from app.events.base import NotificationPushed  # noqa: PLC0415
            from app.events.bus import event_bus  # noqa: PLC0415

            await event_bus.publish(
                NotificationPushed(
                    tenant_id=tenant_id,
                    notification_id=n.id,
                    ref_type=ref_type,
                    ref_id=ref_id,
                    recipients=list(n.recipients or []),
                    muted=bool(n.muted),
                    level=level,
                    title=title,
                    body=body,
                    link=n.link,
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("通知实时推送事件发布失败: id=%s tenant=%s", n.id, tenant_id)
        return n

    async def get_preference(self, tenant_id: str) -> NotificationPreference | None:
        """读取租户通知偏好（无记录视为未开启免打扰）。"""
        res = await self.session.execute(
            select(NotificationPreference).where(NotificationPreference.tenant_id == tenant_id)
        )
        return res.scalar_one_or_none()

    # ---------- ④ 角色订阅配置 ----------

    async def get_subscription(
        self, tenant_id: str, ref_type: str
    ) -> NotificationSubscription | None:
        """读取某 ref_type 的订阅配置（无记录返回 None）。"""
        res = await self.session.execute(
            select(NotificationSubscription).where(
                NotificationSubscription.tenant_id == tenant_id,
                NotificationSubscription.ref_type == ref_type,
            )
        )
        return res.scalar_one_or_none()

    async def get_subscribers(
        self, tenant_id: str, ref_type: str | None, fallback: str = "store_manager"
    ) -> list[str]:
        """解析某 ref_type 的最终接收角色列表（供 push 落库）。

        优先级：显式订阅配置（含空列表=不推送）> DEFAULT_SUBSCRIBERS[ref_type] > 历史单 recipient 形参。
        """
        if ref_type:
            sub = await self.get_subscription(tenant_id, ref_type)
            if sub is not None:
                # 已配置即权威：空列表表示该类通知不推送任何人
                return list(sub.recipients or [])
        if ref_type and ref_type in DEFAULT_SUBSCRIBERS:
            return list(DEFAULT_SUBSCRIBERS[ref_type])
        return [fallback] if fallback else []

    async def get_subscriptions(self, tenant_id: str) -> list[NotificationSubscription]:
        """读取租户下全部订阅配置行。"""
        res = await self.session.execute(
            select(NotificationSubscription).where(
                NotificationSubscription.tenant_id == tenant_id
            )
        )
        return list(res.scalars())

    async def set_subscription(
        self, tenant_id: str, ref_type: str, recipients: list[str]
    ) -> NotificationSubscription:
        """upsert 某 ref_type 的接收角色列表（空列表=该类通知不推送）。"""
        sub = await self.get_subscription(tenant_id, ref_type)
        if sub is None:
            sub = NotificationSubscription(tenant_id=tenant_id, ref_type=ref_type)
            self.session.add(sub)
        sub.recipients = list(recipients or [])
        self.session.add(sub)
        await self.session.flush()
        return sub

    async def push_daily_report(self, report: DailyReport) -> Notification:
        """夜审完成自动推送营业日报+摘要（FR-APP-04：06:00 前送达）。"""
        body = (
            f"营业日 {report.business_date}："
            f"总营收 {report.total_revenue} 分（房费 {report.room_revenue} / 杂费 {report.other_revenue}），"
            f"出租率 {report.occ_pct}%，ADR {report.adr} 分，"
            f"到店 {report.arrived_rooms} / 离店 {report.departed_rooms}。"
        )
        return await self.push(
            report.tenant_id,
            f"营业日报 {report.business_date}",
            body,
            hotel_id=report.hotel_id,
            ref_type="daily_report",
            ref_id=report.id,
            level="info",
            link=f"/reports?type=dashboard&date={report.business_date}",
        )

    async def list_notifications(
        self,
        tenant_id: str,
        hotel_id: int | None = None,
        unread_only: bool = False,
        recipient_tags: set[str] | None = None,
        ref_type: str | None = None,
        level: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(Notification.hotel_id == hotel_id)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        if ref_type:
            stmt = stmt.where(Notification.ref_type == ref_type)
        if level:
            stmt = stmt.where(Notification.level == level)
        stmt = stmt.order_by(Notification.id.desc())
        rows = await self.session.execute(stmt)
        items = list(rows.scalars())
        # ⑥ 行级可见性：仅返回 recipients 与本人标签有交集的通知；
        # 空 recipients（④=不推送任何人）对任何人不可见，与 WS 实时路由一致。
        if recipient_tags is not None:
            items = [n for n in items if set(n.recipients or []) & recipient_tags]
        # 分页在可见性过滤之后切片，保证返回页内均为本人可见项（跨库可移植）
        if offset:
            items = items[offset:]
        if limit is not None:
            items = items[:limit]
        return items

    async def mark_read(self, n: Notification) -> Notification:
        if n.read_at is None:
            n.read_at = datetime.now(UTC)
            self.session.add(n)
            await self.session.flush()
        return n

    async def mark_all_read(
        self, tenant_id: str, hotel_id: int | None = None, recipient_tags: set[str] | None = None
    ) -> int:
        """一键全部已读：仅标记本人可见的未读项（⑥ 行级可见性），返回受影响行数。

        ③ 免打扰静音项在通知中心仍可见，故「全部已读」一并清除（与列表口径一致）；
        空 recipients 抑制项对任何人不可见，不计入。
        """
        stmt = select(Notification).where(
            Notification.tenant_id == tenant_id, Notification.read_at.is_(None)
        )
        if hotel_id is not None:
            stmt = stmt.where(Notification.hotel_id == hotel_id)
        rows = await self.session.execute(stmt)
        items = list(rows.scalars())
        # ⑥ 行级可见性：仅清除与本人标签交集的通知（与列表/未读计数同一过滤）
        if recipient_tags is not None:
            items = [n for n in items if set(n.recipients or []) & recipient_tags]
        for n in items:
            n.read_at = datetime.now(UTC)
            self.session.add(n)
        await self.session.flush()
        return len(items)

    async def count_unread(
        self, tenant_id: str, hotel_id: int | None = None, recipient_tags: set[str] | None = None
    ) -> int:
        """未读条数（顶栏角标）。③ 免打扰静音项不计入角标；⑥ 行级可见性过滤。"""
        stmt = select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.read_at.is_(None),
            Notification.muted.is_(False),
        )
        if hotel_id is not None:
            stmt = stmt.where(Notification.hotel_id == hotel_id)
        rows = await self.session.execute(stmt)
        items = list(rows.scalars())
        # ⑥ 行级可见性：计数同样受本人标签约束（与列表一致）
        if recipient_tags is not None:
            items = [n for n in items if set(n.recipients or []) & recipient_tags]
        return len(items)

    async def resolve_user_tags(self, tenant_id: str, user_id: int) -> set[str]:
        """按用户角色档位解析通知接收标签集合（⑥ 列表/未读行级可见性路由）。

        无角色绑定返回空集（仅能看到租户级全员推送，当前无此类通知）。
        """
        from app.services.rbac_service import RbacService  # noqa: PLC0415

        rbac = RbacService(self.session)
        bindings = await rbac.list_user_roles(tenant_id, user_id)
        if not bindings:
            return set()
        role_ids = [b.role_id for b in bindings]
        res = await self.session.execute(
            select(Role.level).where(Role.tenant_id == tenant_id, Role.id.in_(role_ids))
        )
        levels = set(res.scalars())
        return recipient_tags_for_roles(levels)
