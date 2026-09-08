"""M1 基座 · 统一接待办理流状态机（R2，PRD ③）。

办理流把「查档 → 建档/排房 → 入住 → 在住 → 结账 → 退房」收敛为一台
半自动状态机（PRD Q2 默认=每步预填、「继续」确认、可回溯）：

    QUERY → REGISTER → CHECKIN → INHOUSE → FOLIO → CHECKOUT

设计要点（对齐 room_state.py 的 DEC-02 状态机范式）：
- 状态本身**不持久化**，始终由域状态（Booking.status / Room.state）派生，
  避免与既有预订/房态引擎产生第二真相源；
- 仅暴露**有副作用**的 4 个动作（register / check_in / open_folio / check_out），
  由 ReceptionService.advance 校验合法性后委托既有 service 回写各域；
- 非法流转抛 ``InvalidReceptionTransition``，API 层转 409。
"""

from __future__ import annotations

from enum import StrEnum

from app.models import BookingStatus


class ReceptionFlowState(StrEnum):
    QUERY = "query"          # 查档/搜索态，尚未确定客人或预订已取消
    REGISTER = "register"    # 已建客档/预订（待排房在住）
    CHECKIN = "checkin"      # 已办理入住（瞬时态，派生后归并到 INHOUSE）
    INHOUSE = "inhouse"      # 在住（可循环：加账/附加服务/续住/换房）
    FOLIO = "folio"          # 对账/结账中（派生态，存在 OPEN 账单且在住）
    CHECKOUT = "checkout"    # 已退房（终态）


class ReceptionAction(StrEnum):
    """办理流动作（与 PRD 状态机一一对应，仅 5 个有副作用）。"""

    REGISTER = "register"          # 建档/建预订
    CHECK_IN = "check_in"          # 排房 + 入住（复用 unified_check_in）
    OPEN_FOLIO = "open_folio"      # 确认在开账单（幂等）
    CHECK_OUT = "check_out"        # 退房（复用 BookingService.check_out）
    ENROLL_MEMBER = "enroll_member"  # 客档联动会员：现场办会员并关联（① 深度联动）


# 各状态允许的后续动作（状态机守卫）
ALLOWED_ACTIONS: dict[ReceptionFlowState, frozenset[ReceptionAction]] = {
    ReceptionFlowState.QUERY: frozenset(
        {ReceptionAction.REGISTER, ReceptionAction.CHECK_IN, ReceptionAction.ENROLL_MEMBER}
    ),
    ReceptionFlowState.REGISTER: frozenset(
        {ReceptionAction.CHECK_IN, ReceptionAction.ENROLL_MEMBER}
    ),
    ReceptionFlowState.CHECKIN: frozenset(
        {ReceptionAction.REGISTER, ReceptionAction.CHECK_IN, ReceptionAction.CHECK_OUT, ReceptionAction.ENROLL_MEMBER}
    ),
    ReceptionFlowState.INHOUSE: frozenset(
        {ReceptionAction.OPEN_FOLIO, ReceptionAction.CHECK_OUT, ReceptionAction.ENROLL_MEMBER}
    ),
    ReceptionFlowState.FOLIO: frozenset(
        {ReceptionAction.CHECK_OUT, ReceptionAction.ENROLL_MEMBER}
    ),
    ReceptionFlowState.CHECKOUT: frozenset(),
}

# 动作执行后置的预期状态（文档/校验用；实际位置由域派生）
TARGET_STATE: dict[ReceptionAction, ReceptionFlowState] = {
    ReceptionAction.REGISTER: ReceptionFlowState.REGISTER,
    ReceptionAction.CHECK_IN: ReceptionFlowState.INHOUSE,
    ReceptionAction.OPEN_FOLIO: ReceptionFlowState.FOLIO,
    ReceptionAction.CHECK_OUT: ReceptionFlowState.CHECKOUT,
}


class InvalidReceptionTransition(Exception):
    """非法办理流流转（状态机守卫失败）。"""

    def __init__(self, state: ReceptionFlowState, action: ReceptionAction) -> None:
        self.state = state
        self.action = action
        super().__init__(
            f"非法办理流流转: 当前状态 {state.value} 不允许动作 {action.value}"
        )


def derive_flow_state(
    *,
    booking_status: str | None = None,
) -> ReceptionFlowState:
    """由域状态派生办理流当前位置（状态机不持久化，始终由域推导）。

    - 预订已离 → CHECKOUT；在住 → INHOUSE（FOLIO 作为 INHOUSE 内的结账子阶段，
      由 UI 借 ``open_folio`` 动作提示，不单独派生状态，避免与自动开账冲突）；
    - 预订已建未住 → REGISTER；无预订/已取消 → QUERY。
    """
    if booking_status == BookingStatus.CHECKED_OUT.value:
        return ReceptionFlowState.CHECKOUT
    if booking_status == BookingStatus.CHECKED_IN.value:
        return ReceptionFlowState.INHOUSE
    if booking_status == BookingStatus.CREATED.value:
        return ReceptionFlowState.REGISTER
    # CANCELLED / 无预订
    return ReceptionFlowState.QUERY


def can_advance(state: ReceptionFlowState) -> list[str]:
    """返回当前状态下允许的动作（供 UI 单步「继续」按钮渲染）。"""
    return sorted(a.value for a in ALLOWED_ACTIONS.get(state, frozenset()))
