"""BLK-03 事件总线：进程内实现 + 外部 MQ 适配器接口。

演进路径（对齐 dev-plan 2.1/2.2 节）：
- Sprint 1: InProcessEventBus（本文件），满足「房态事件可订阅」验收；
- Sprint 7+: KafkaPublisher 适配器（aiokafka，按 tenant_id 分区保序），
  替换 publish 通道即可，订阅方（WebSocket 网关/渠道同步）零改动。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.events.base import DomainEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventPublisher(Protocol):
    """事件发布通道抽象（未来 Kafka 适配器实现同一协议）。"""

    async def publish(self, event: DomainEvent) -> None: ...


class InProcessEventBus(EventPublisher):
    """进程内异步事件总线（主题订阅/发布）。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: EventHandler) -> Callable[[], None]:
        self._subscribers[topic].append(handler)

        def unsubscribe() -> None:
            self._subscribers[topic].remove(handler)

        return unsubscribe

    async def publish(self, event: DomainEvent) -> None:
        handlers = list(self._subscribers.get(event.topic, ()))
        # M18 开放 API 平台：支持 "#" 通配符订阅全部事件
        handlers += list(self._subscribers.get("#", ()))
        if not handlers:
            logger.debug("事件无订阅者: %s", event.topic)
            return
        # 重试策略：指数退避（BLK-03 规范），进程内先做 2 次重试
        for handler in handlers:
            await self._dispatch_with_retry(handler, event)

    async def _dispatch_with_retry(
        self, handler: EventHandler, event: DomainEvent, retries: int = 2
    ) -> None:
        for attempt in range(retries + 1):
            try:
                await handler(event)
                return
            except Exception:  # noqa: BLE001
                logger.exception(
                    "事件处理失败(第%d次): topic=%s", attempt + 1, event.topic
                )
                if attempt < retries:
                    await asyncio.sleep(0.1 * (2**attempt))
                else:
                    # 最终失败：落库事件表由补偿任务重放（S2 引入死信队列）
                    logger.error("事件处理最终失败，等待补偿: topic=%s", event.topic)


class QueuedSubscriber:
    """队列化订阅者：WebSocket 推送网关使用（解耦发布方与连接写入）。"""

    def __init__(self, maxsize: int = 100) -> None:
        self.queue: asyncio.Queue[DomainEvent] = asyncio.Queue(maxsize=maxsize)

    async def __call__(self, event: DomainEvent) -> None:
        self.queue.put_nowait(event)


# 全局总线实例（Kafka 适配器上线后替换此对象的 publish 通道）
event_bus = InProcessEventBus()
