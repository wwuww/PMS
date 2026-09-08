"""BLK-03 事件总线单元测试。"""

import pytest

from app.events.base import DomainEvent, RoomStateChanged
from app.events.bus import InProcessEventBus, QueuedSubscriber


class TestEventBus:
    async def test_publish_subscribe_roundtrip(self) -> None:
        bus = InProcessEventBus()
        received: list[DomainEvent] = []

        async def handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe(RoomStateChanged.TOPIC, handler)  # type: ignore[arg-type]
        event = RoomStateChanged(
            tenant_id="t001",
            room_id=1,
            room_no="0101",
            from_state="vacant_clean",
            to_state="occupied",
            trigger="check_in",
            operator="front_desk",
        )
        await bus.publish(event)
        assert received == [event]

    async def test_unsubscribe(self) -> None:
        bus = InProcessEventBus()
        received: list[DomainEvent] = []

        async def handler(event: DomainEvent) -> None:
            received.append(event)

        unsubscribe = bus.subscribe(RoomStateChanged.TOPIC, handler)  # type: ignore[arg-type]
        unsubscribe()
        await bus.publish(
            RoomStateChanged(
                tenant_id="t001",
                room_id=1,
                room_no="0101",
                from_state="vacant_clean",
                to_state="occupied",
                trigger="check_in",
                operator="front_desk",
            )
        )
        assert received == []

    async def test_no_subscriber_is_noop(self) -> None:
        bus = InProcessEventBus()
        await bus.publish(
            RoomStateChanged(
                tenant_id="t001",
                room_id=1,
                room_no="0101",
                from_state="vacant_clean",
                to_state="occupied",
                trigger="check_in",
                operator="front_desk",
            )
        )  # 不应抛异常

    async def test_queued_subscriber(self) -> None:
        bus = InProcessEventBus()
        queued = QueuedSubscriber()
        bus.subscribe(RoomStateChanged.TOPIC, queued)  # type: ignore[arg-type]
        await bus.publish(
            RoomStateChanged(
                tenant_id="t001",
                room_id=1,
                room_no="0101",
                from_state="vacant_clean",
                to_state="occupied",
                trigger="check_in",
                operator="front_desk",
            )
        )
        event = queued.queue.get_nowait()
        payload = event.payload()
        assert payload["topic"] == "room.room.state_changed"
        assert payload["to_state"] == "occupied"

    async def test_failed_handler_retried_then_survives(self) -> None:
        """指数退避重试后仍失败不中断总线（等待补偿）。"""
        bus = InProcessEventBus()
        calls = 0

        async def flaky(event: DomainEvent) -> None:
            nonlocal calls
            calls += 1
            raise RuntimeError("boom")

        bus.subscribe(RoomStateChanged.TOPIC, flaky)  # type: ignore[arg-type]
        await bus.publish(
            RoomStateChanged(
                tenant_id="t001",
                room_id=1,
                room_no="0101",
                from_state="vacant_clean",
                to_state="occupied",
                trigger="check_in",
                operator="front_desk",
            )
        )
        assert calls == 3  # 1次 + 2次重试

    def test_event_topic_naming(self) -> None:
        event = RoomStateChanged(
            tenant_id="t001",
            room_id=1,
            room_no="0101",
            from_state="a",
            to_state="b",
            trigger="t",
            operator="o",
        )
        assert event.topic == "room.room.state_changed"


if __name__ == "__main__":
    pytest.main([__file__])
