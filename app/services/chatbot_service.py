"""M11 AI 智能客服服务。

当前为规则+关键词意图识别骨架（便于后续接入 LLM），所有判定逻辑集中，
对外接口稳定。数据脱敏出域（NFR-SE-05）由调用侧保证。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import ChatHandoffRequested
from app.events.bus import event_bus
from app.models import ChatMessage, ChatSession, Hotel, Notification, PriceCalendar, RoomType


@dataclass(frozen=True)
class IntentResult:
    intent: str
    confidence: float
    reply: str
    handoff: bool


INTENTS = {
    "price": {
        "keywords": ["价格", "多少钱", "房价", "一晚", "怎么卖", "贵不贵", "便宜", "优惠", "折扣"],
        "reply": "房价以小程序实时报价为准，入住日期不同价格会有浮动。您可点击下方「预订」选择日期查看可售房型与价格。",
    },
    "refund_policy": {
        "keywords": ["退", "取消", "退款", "改签", "改期", "能退吗", "退订政策"],
        "reply": "入住当日 18:00 前可免费取消；18:00 后或到店当天取消将收取首晚房费。具体以订单确认页展示为准。",
    },
    "facilities": {
        "keywords": ["停车", "早餐", "洗衣", "健身房", "泳池", "wifi", "网络", "空调", "设施"],
        "reply": "本店提供免费 Wi-Fi、24 小时热水、空调；部分房型含早餐，停车/健身房请以门店详情页标签为准。",
    },
    "traffic": {
        "keywords": ["地铁", "公交", "机场", "高铁", "怎么走", "地址", "位置", "附近", "周边"],
        "reply": "门店地址可在订单确认页导航；如需查询具体公共交通路线，请告诉我您从哪个站点/机场出发。",
    },
    "human": {
        "keywords": ["人工", "客服", "找前台", "打电话", "热线", "投诉", "经理", "店长"],
        "reply": "已为您转接人工客服，请稍等，前台将尽快接入。",
        "handoff": True,
    },
    "greeting": {
        "keywords": ["你好", "您好", "在吗", "hello", "hi", "咨询"],
        "reply": "您好！我是酒店智能客服，可为您解答房价、退订政策、设施、交通等问题，输入「人工」可转接前台。",
    },
    "unknown": {
        "keywords": [],
        "reply": "抱歉，我可能没理解您的问题。您可以输入「房价」「退订」「设施」「交通」或「人工」。",
    },
}


class ChatbotService:
    """M11 智能客服服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        tenant_id: str,
        channel: str = "wechat_mp",
        guest_name: str | None = None,
        guest_phone: str | None = None,
    ) -> ChatSession:
        sess = ChatSession(
            tenant_id=tenant_id,
            channel=channel,
            guest_name=guest_name,
            guest_phone=guest_phone,
        )
        self.session.add(sess)
        await self.session.flush()
        return sess

    async def classify(self, text: str) -> IntentResult:
        """意图识别：关键词匹配 + 置信度（后续可替换为 LLM）。"""
        text_norm = text.lower().strip()
        best_intent = "unknown"
        best_score = 0.0
        for intent, cfg in INTENTS.items():
            if intent == "unknown":
                continue
            score = 0.0
            for kw in cfg["keywords"]:
                if kw in text_norm:
                    score += 1.0
            # 整句匹配加分
            if score:
                score = min(1.0, 0.6 + 0.1 * score)
            if score > best_score:
                best_score = score
                best_intent = intent

        cfg = INTENTS.get(best_intent, INTENTS["unknown"])
        reply = cfg["reply"]
        handoff = cfg.get("handoff", False)
        # 连续 unknown 两次也建议转人工
        if best_intent == "unknown" and best_score == 0:
            best_score = 0.3
        return IntentResult(best_intent, round(best_score, 2), reply, handoff)

    async def reply(
        self,
        session: ChatSession,
        user_text: str,
        hotel_id: int | None = None,
    ) -> ChatMessage:
        """处理用户消息并返回机器人回复。"""
        # 记录用户消息
        user_msg = ChatMessage(
            session_id=session.id,
            role="user",
            content=user_text,
        )
        self.session.add(user_msg)

        result = await self.classify(user_text)

        # 如果是房价意图且指定了酒店+房型，可返回实时价格（ richer answer ）
        if result.intent == "price" and hotel_id:
            enriched = await self._enrich_price_reply(tenant_id=session.tenant_id, hotel_id=hotel_id)
            if enriched:
                result = IntentResult(
                    intent=result.intent,
                    confidence=result.confidence,
                    reply=enriched,
                    handoff=result.handoff,
                )

        bot_msg = ChatMessage(
            session_id=session.id,
            role="bot",
            content=result.reply,
            intent=result.intent,
            confidence=result.confidence,
        )
        self.session.add(bot_msg)

        session.intent = result.intent
        if result.handoff:
            session.status = "handoff"
            await self._create_handoff_notification(session, hotel_id)
            await event_bus.publish(
                ChatHandoffRequested(
                    tenant_id=session.tenant_id,
                    session_id=session.id,
                    channel=session.channel,
                    reason="用户关键词触发转人工",
                )
            )

        await self.session.flush()
        return bot_msg

    async def handoff(
        self,
        session: ChatSession,
        reason: str,
        hotel_id: int | None = None,
    ) -> ChatMessage:
        """显式转人工。"""
        session.status = "handoff"
        session.handoff_reason = reason
        reply = INTENTS["human"]["reply"]
        msg = ChatMessage(
            session_id=session.id,
            role="system",
            content=reply,
            intent="human",
            confidence=1.0,
        )
        self.session.add(msg)
        await self._create_handoff_notification(session, hotel_id)
        await event_bus.publish(
            ChatHandoffRequested(
                tenant_id=session.tenant_id,
                session_id=session.id,
                channel=session.channel,
                reason=reason,
            )
        )
        await self.session.flush()
        return msg

    async def close_session(
        self, session: ChatSession, satisfaction: int | None = None
    ) -> ChatSession:
        """关闭会话并记录满意度。"""
        session.status = "closed"
        if satisfaction is not None:
            session.satisfaction = max(1, min(5, satisfaction))
        self.session.add(session)
        await self.session.flush()
        return session

    async def human_reply(
        self, session: ChatSession, content: str
    ) -> ChatMessage:
        """人工客服回复。"""
        msg = ChatMessage(
            session_id=session.id,
            role="human",
            content=content,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def _create_handoff_notification(
        self, session: ChatSession, hotel_id: int | None
    ) -> None:
        """转人工时给前台推送通知。"""
        from app.services.notification_service import NotificationService

        title = "AI客服转人工"
        body = f"客人{session.guest_name or '（匿名）'}请求人工接入，原因为：{session.handoff_reason or '用户主动转人工'}。"
        await NotificationService(self.session).push(
            tenant_id=session.tenant_id,
            hotel_id=hotel_id,
            recipient="front_desk",
            channel="APP",
            title=title,
            body=body,
            ref_type="chat_session",
            ref_id=session.id,
        )

    async def _enrich_price_reply(
        self, tenant_id: str, hotel_id: int
    ) -> str | None:
        """若酒店存在，返回最便宜房型起价。"""
        hotel = await self.session.get(Hotel, hotel_id)
        if not hotel:
            return None
        # 查找该酒店下所有房型起价
        rows = await self.session.execute(
            select(RoomType).where(RoomType.tenant_id == tenant_id, RoomType.id == RoomType.id)
        )
        room_types = list(rows.scalars())
        if not room_types:
            return None
        # 取未来 7 天最低日历价
        future_prices: list[int] = []
        for rt in room_types:
            prices = await self.session.execute(
                select(PriceCalendar.price)
                .where(
                    PriceCalendar.tenant_id == tenant_id,
                    PriceCalendar.room_type_id == rt.id,
                )
                .order_by(PriceCalendar.price)
                .limit(1)
            )
            p = prices.scalar_one_or_none()
            if p is not None:
                future_prices.append(p)
        if not future_prices:
            return None
        min_price = min(future_prices)
        return f"本店当前可订房型起价 {min_price} 分/晚（以小程序选择日期后的实时报价为准）。"

    async def list_sessions(
        self, tenant_id: str, status: str | None = None, limit: int = 100
    ) -> list[ChatSession]:
        stmt = select(ChatSession).where(ChatSession.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(ChatSession.status == status)
        stmt = stmt.order_by(ChatSession.id.desc()).limit(limit)
        rows = await self.session.execute(stmt)
        return list(rows.scalars())

    async def list_messages(
        self, session_id: int
    ) -> list[ChatMessage]:
        rows = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
        )
        return list(rows.scalars())
