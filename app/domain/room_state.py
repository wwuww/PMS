"""M1-1 房态状态机引擎（架构决策 DEC-02：房态状态机 + 事件驱动）。

状态（对齐 SRS FR-FT-01）：
    VACANT_CLEAN   空净
    VACANT_DIRTY   空脏
    OCCUPIED       在住
    ARRIVAL_LOCKED 锁房（通用锁房，空净/空脏均可；含原预分配房号场景）
    MAINTENANCE    维修（不可售，联动价格库存中心扣减——S3 接入）
    OUT_OF_SERVICE 停用

规则：状态只能沿合法触发器流转，非法流转抛出 InvalidTransition，
由 API 层转为 422；每次成功流转发布 RoomStateChanged 领域事件。
"""

from __future__ import annotations

from enum import StrEnum


class RoomState(StrEnum):
    VACANT_CLEAN = "vacant_clean"
    VACANT_DIRTY = "vacant_dirty"
    OCCUPIED = "occupied"
    ARRIVAL_LOCKED = "arrival_locked"
    MAINTENANCE = "maintenance"
    OUT_OF_SERVICE = "out_of_service"


class RoomTrigger(StrEnum):
    """状态流转触发器（业务动作）。"""

    CHECK_IN = "check_in"                # 入住
    CHECK_OUT = "check_out"              # 退房（在住→空脏，触发清扫工单——S2 接入）
    CLEAN_DONE = "clean_done"            # 清扫完成
    SET_DIRTY = "set_dirty"              # 置脏（空净 → 空脏，前台手工标记）
    LOCK_FOR_ARRIVAL = "lock_for_arrival"    # 预分配锁房
    RELEASE_ARRIVAL = "release_arrival"      # 取消预订/释放
    START_MAINTENANCE = "start_maintenance"  # 开始维修
    END_MAINTENANCE = "end_maintenance"      # 维修结束（→空脏待清扫）
    SET_OUT_OF_SERVICE = "set_out_of_service"
    RESTORE_SERVICE = "restore_service"
    ROOM_SWAP = "room_swap"  # 换房腾退（在住→空脏，订单仍 CHECKED_IN）


# 触发器 → (允许的源状态集合, 目标状态)
TRANSITIONS: dict[RoomTrigger, tuple[frozenset[RoomState], RoomState]] = {
    RoomTrigger.CHECK_IN: (
        frozenset({RoomState.VACANT_CLEAN, RoomState.ARRIVAL_LOCKED}),
        RoomState.OCCUPIED,
    ),
    RoomTrigger.CHECK_OUT: (frozenset({RoomState.OCCUPIED}), RoomState.VACANT_DIRTY),
    RoomTrigger.CLEAN_DONE: (frozenset({RoomState.VACANT_DIRTY}), RoomState.VACANT_CLEAN),
    RoomTrigger.SET_DIRTY: (frozenset({RoomState.VACANT_CLEAN}), RoomState.VACANT_DIRTY),
    # M32.3：锁房改为通用功能——空净/空脏均可锁定（不只是预抵）
    RoomTrigger.LOCK_FOR_ARRIVAL: (
        frozenset({RoomState.VACANT_CLEAN, RoomState.VACANT_DIRTY}),
        RoomState.ARRIVAL_LOCKED,
    ),
    RoomTrigger.RELEASE_ARRIVAL: (
        frozenset({RoomState.ARRIVAL_LOCKED}),
        RoomState.VACANT_CLEAN,
    ),
    RoomTrigger.START_MAINTENANCE: (
        frozenset({RoomState.VACANT_CLEAN, RoomState.VACANT_DIRTY}),
        RoomState.MAINTENANCE,
    ),
    RoomTrigger.END_MAINTENANCE: (
        frozenset({RoomState.MAINTENANCE}),
        RoomState.VACANT_DIRTY,
    ),
    RoomTrigger.SET_OUT_OF_SERVICE: (
        frozenset({RoomState.VACANT_CLEAN, RoomState.VACANT_DIRTY, RoomState.MAINTENANCE}),
        RoomState.OUT_OF_SERVICE,
    ),
    RoomTrigger.RESTORE_SERVICE: (
        frozenset({RoomState.OUT_OF_SERVICE}),
        RoomState.VACANT_DIRTY,
    ),
    RoomTrigger.ROOM_SWAP: (frozenset({RoomState.OCCUPIED}), RoomState.VACANT_DIRTY),
}


class InvalidTransition(Exception):
    """非法状态流转。"""

    def __init__(self, current: RoomState, trigger: RoomTrigger) -> None:
        self.current = current
        self.trigger = trigger
        super().__init__(
            f"非法流转: 当前状态 {current.value} 不允许触发 {trigger.value}"
        )


def next_state(current: RoomState, trigger: RoomTrigger) -> RoomState:
    """校验并返回目标状态；非法流转抛 InvalidTransition。"""
    sources, target = TRANSITIONS[trigger]
    if current not in sources:
        raise InvalidTransition(current, trigger)
    return target


def sellable(state: RoomState) -> bool:
    """可售状态（价格库存中心扣减口径，FR-JG-02）。"""
    return state in (RoomState.VACANT_CLEAN, RoomState.ARRIVAL_LOCKED)
