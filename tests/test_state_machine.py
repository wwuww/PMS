"""M1-1 房态状态机单元测试。"""

import pytest

from app.domain.room_state import (
    InvalidTransition,
    RoomState,
    RoomTrigger,
    next_state,
    sellable,
)


class TestRoomStateMachine:
    def test_check_in_from_vacant_clean(self) -> None:
        assert (
            next_state(RoomState.VACANT_CLEAN, RoomTrigger.CHECK_IN) is RoomState.OCCUPIED
        )

    def test_check_in_from_arrival_locked(self) -> None:
        assert (
            next_state(RoomState.ARRIVAL_LOCKED, RoomTrigger.CHECK_IN) is RoomState.OCCUPIED
        )

    def test_check_out_creates_dirty_room(self) -> None:
        assert (
            next_state(RoomState.OCCUPIED, RoomTrigger.CHECK_OUT) is RoomState.VACANT_DIRTY
        )

    def test_clean_done_restores_clean(self) -> None:
        assert (
            next_state(RoomState.VACANT_DIRTY, RoomTrigger.CLEAN_DONE) is RoomState.VACANT_CLEAN
        )

    def test_full_lifecycle(self) -> None:
        """完整生命周期：空净→锁房→在住→空脏→空净。"""
        state = RoomState.VACANT_CLEAN
        for trigger, expected in [
            (RoomTrigger.LOCK_FOR_ARRIVAL, RoomState.ARRIVAL_LOCKED),
            (RoomTrigger.CHECK_IN, RoomState.OCCUPIED),
            (RoomTrigger.CHECK_OUT, RoomState.VACANT_DIRTY),
            (RoomTrigger.CLEAN_DONE, RoomState.VACANT_CLEAN),
        ]:
            state = next_state(state, trigger)
            assert state is expected

    def test_maintenance_roundtrip(self) -> None:
        state = next_state(RoomState.VACANT_CLEAN, RoomTrigger.START_MAINTENANCE)
        assert state is RoomState.MAINTENANCE
        assert next_state(state, RoomTrigger.END_MAINTENANCE) is RoomState.VACANT_DIRTY

    def test_illegal_check_in_from_dirty(self) -> None:
        with pytest.raises(InvalidTransition):
            next_state(RoomState.VACANT_DIRTY, RoomTrigger.CHECK_IN)

    def test_illegal_check_out_from_clean(self) -> None:
        with pytest.raises(InvalidTransition):
            next_state(RoomState.VACANT_CLEAN, RoomTrigger.CHECK_OUT)

    def test_illegal_clean_occupied(self) -> None:
        with pytest.raises(InvalidTransition):
            next_state(RoomState.OCCUPIED, RoomTrigger.CLEAN_DONE)

    def test_sellable_states(self) -> None:
        assert sellable(RoomState.VACANT_CLEAN)
        assert sellable(RoomState.ARRIVAL_LOCKED)
        assert not sellable(RoomState.OCCUPIED)
        assert not sellable(RoomState.MAINTENANCE)
        assert not sellable(RoomState.VACANT_DIRTY)
        assert not sellable(RoomState.OUT_OF_SERVICE)
