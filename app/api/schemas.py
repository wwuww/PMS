"""API Schema（Pydantic v2，兼作接口契约）。"""

import json
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from typing import Annotated, Any

from pydantic import BeforeValidator


def _coerce_str_id(v):
    """id 字段统一字符串化：兼容 int 输入（ORM/测试）与 str 输入（前端）。"""
    if v is None:
        return None
    return str(v)


StrId = Annotated[str, BeforeValidator(_coerce_str_id)]


class TenantCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=128)
    is_chain: bool = False


class TenantOut(BaseModel):
    id: StrId
    code: str
    name: str
    is_chain: bool
    status: str
    noshow_charge_first_night: bool = False  # M31：NoShow 自动扣首晚房费（租户级默认）

    model_config = {"from_attributes": True}


class TenantUpdate(BaseModel):
    """租户设置更新（M31：当前仅暴露 noshow_charge_first_night；后续可扩）。"""

    noshow_charge_first_night: bool | None = None


class HotelCreate(BaseModel):
    code: str
    name: str


class HotelOut(BaseModel):
    id: StrId
    tenant_id: str
    code: str
    name: str
    noshow_charge_first_night: bool | None = None  # M31：NoShow 自动扣首晚房费（None=继承租户默认）

    model_config = {"from_attributes": True}


class HotelUpdate(BaseModel):
    """门店设置更新（M31：当前仅暴露 noshow_charge_first_night；后续可扩）。"""

    noshow_charge_first_night: bool | None = None


class RoomTypeCreate(BaseModel):
    code: str
    name: str
    # D1（M0 多店）：房型归属门店。未传时由路由回退到租户下的默认门店（保持旧调用兼容）。
    hotel_id: int | None = None
    # 批次② 字段补全
    bed_number: int = 1
    short_name: str | None = None
    en_name: str | None = None
    descript: str | None = None
    is_valid: bool = True
    base_price: int = Field(ge=0, description="基准价（分）")
    hourly_rate: int | None = Field(default=None, ge=0, description="时租价（分/小时）")  # M24


class RoomTypeOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId  # D1：房型所属门店
    code: str
    name: str
    base_price: int
    hourly_rate: int | None = None  # M24：时租价（分/小时）

    model_config = {"from_attributes": True}


class RoomCreate(BaseModel):
    room_type_id: int
    room_no: str
    floor: str = ""


class RoomOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    room_type_id: StrId
    room_no: str
    floor: str
    state: str
    dnd: int = 0  # M31：免打扰 0/1
    pre_lock_state: str | None = None  # M32.3：锁房前房态（仅锁房房间返回，前端原色+小锁）

    model_config = {"from_attributes": True}


class RoomTransitionIn(BaseModel):
    trigger: str
    operator: str = "front_desk"


class RateCodeCreate(BaseModel):
    code: str
    name: str
    channel: str = "direct"
    member_level: str = "none"
    agreement_type: str = "none"
    room_type_id: int | None = None
    stay_type: str = "daily"
    discount_pct: int = Field(default=10000, ge=0, le=10000)
    restrictions: dict = Field(default_factory=dict)


class RateCodeOut(BaseModel):
    id: StrId
    tenant_id: str
    code: str
    name: str
    channel: str
    member_level: str
    agreement_type: str
    stay_type: str
    discount_pct: int

    model_config = {"from_attributes": True}


# ---------- 价格库存中心（FR-JG 全量） ----------


class PriceCalendarCreate(BaseModel):
    room_type_id: int
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    price: int = Field(ge=0, description="当日基准价（分）")


class PriceCalendarOut(BaseModel):
    id: StrId
    tenant_id: str
    room_type_id: StrId
    date: str
    price: int

    model_config = {"from_attributes": True}


class AvailabilityOut(BaseModel):
    room_type_id: StrId
    date: str
    total: int
    booked: int
    available: int
    price: int  # 该日解析价（分）


# ---------- 预订引擎（M2） ----------


class BookingCreate(BaseModel):
    hotel_id: int
    room_type_id: int
    guest_name: str = Field(min_length=1, max_length=64)
    check_in_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    check_out_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    channel: str = "direct"
    rate_code_code: str | None = None
    guest_phone: str | None = None
    id_doc_no: str | None = None
    room_no: str | None = None  # 可选预分配房号
    chat_session_id: int | None = None  # AI 会话建单回链
    stay_type: str = Field(default="daily", pattern=r"^(daily|hourly)$")  # M24：时租房
    hourly_hours: int | None = Field(default=None, gt=0, description="时租时长（小时）")


class BookingOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    room_type_id: StrId
    channel: str
    guest_name: str
    guest_phone: str | None = None
    check_in_date: str
    check_out_date: str
    room_no: str | None
    chat_session_id: StrId | None = None
    status: str
    total_price: int | None
    nights: int
    extra_bed_count: int = 0
    companion_names: list[str] = []
    noshow_reason: str | None = None  # M23：NoShow 原因（夜审自动/前台手动）
    stay_type: str = "daily"  # M24：daily|hourly
    hourly_hours: int | None = None  # M24：时租时长（小时）
    # M32.15：联房（在住单之间；各单保留自己的来离店日期）
    link_group_id: str | None = None
    is_link_master: bool = False
    # M32.17b：钟点房到店时刻（HH:MM）
    hourly_start_time: str | None = None
    # 批次② 核心实体字段补全（维也纳数据字典对齐）
    guest_source_type: str | None = None
    member_no: str | None = None
    member_type: str | None = None
    is_vip: bool = False
    is_secret: bool = False
    is_quick_depart: bool = False
    is_print_real_price: bool = True
    is_add_point: bool = True
    is_guarantee: bool = False
    guarantee_hold_until: str | None = None
    guarantor: str | None = None
    sales_id: str | None = None
    activity_code: str | None = None
    upgrade_room_type_id: int | None = None
    group_name: str | None = None
    group_type: str | None = None
    group_leader: str | None = None
    group_tel: str | None = None
    email: str | None = None
    country: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("companion_names", mode="before")
    @classmethod
    def _parse_companions(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            if not v:
                return []
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v


class BookingActionIn(BaseModel):
    room_no: str | None = None
    operator: str = "front_desk"


class BookingLinkIn(BaseModel):
    """在住联房（M32.15）：把多间在住房联为一组，master_room_no 为主房。

    联房只建立账务关联，不改动各单的来离店日期。
    """

    room_nos: list[str] = Field(min_length=2)
    master_room_no: str


class BookingUnlinkIn(BaseModel):
    """取消联房：把若干房号移出其联房组；主房移出时自动移交主房标记。"""

    room_nos: list[str] = Field(min_length=1)


class BookingSettleToMasterIn(BaseModel):
    """联房结转（M32.16）：把从房未结余额整体并入主房账单。"""

    room_no: str
    operator: str = "front_desk"


class BookingNoShowIn(BaseModel):
    """前台手动标记 NoShow（M23 验收清单#3）。"""

    reason: str | None = Field(default=None, max_length=255, description="NoShow 原因；缺省自动生成")
    operator: str = "front_desk"


class BookingExtendIn(BaseModel):
    """续住（延住）：新离店日期 + 操作员。"""

    new_check_out_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    operator: str = "front_desk"


class BookingChangeRoomIn(BaseModel):
    """换房：目标房号 + 换房原因（必填，审计刚需）+ 操作员。"""

    new_room_no: str = Field(min_length=1, max_length=16)
    reason: str = Field(min_length=1, max_length=64)
    operator: str = "front_desk"


# ---------- M37-③ 发票 + 换房记录 + 续住记录 ----------


class InvoiceIn(BaseModel):
    """开票入参：消费/开票额必填（分），专票必填税号，差额>¥10 必填审批人。"""

    invoice_no: str | None = Field(default=None, max_length=32)  # 不传则后端自动生成
    bill_id: int | None = None
    booking_id: int | None = None
    room_no: str | None = Field(default=None, max_length=16)
    guest_name: str | None = Field(default=None, max_length=128)
    agreement_no: str | None = Field(default=None, max_length=32)
    check_in_at: str | None = Field(default=None, max_length=32)
    check_out_at: str = Field(min_length=1, max_length=32)
    check_in_type: str | None = Field(default=None, max_length=16)
    consume_amount_cents: int = Field(default=0, ge=0)
    invoice_amount_cents: int = Field(default=0, ge=0)
    invoice_type: str = Field(default="NORMAL", max_length=16)  # NORMAL|VAT_SPECIAL|ELECTRONIC
    title: str | None = Field(default=None, max_length=128)
    tax_no: str | None = Field(default=None, max_length=64)
    approver: str | None = Field(default=None, max_length=64)
    work_shift: str | None = Field(default=None, max_length=50)
    flag: str = Field(default="1", max_length=1)
    memo: str | None = Field(default=None, max_length=255)
    operator: str = "front_desk"


class InvoiceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: str
    hotel_id: int
    invoice_no: str
    bill_id: int | None = None
    booking_id: int | None = None
    room_no: str | None = None
    guest_name: str | None = None
    agreement_no: str | None = None
    check_in_at: str | None = None
    check_out_at: str
    check_in_type: str | None = None
    consume_amount_cents: int = 0
    invoice_amount_cents: int = 0
    invoice_type: str = "NORMAL"
    title: str | None = None
    tax_no: str | None = None
    approver: str | None = None
    work_shift: str | None = None
    flag: str = "1"
    status: str = "ISSUED"
    operator: str = "front_desk"
    memo: str | None = None
    is_valid: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InvoiceVoidIn(BaseModel):
    """作废发票：WORM，仅置 status=VOID，不改金额。"""

    reason: str | None = Field(default=None, max_length=255)
    operator: str = "front_desk"


class RoomChangeOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: str
    hotel_id: int
    change_no: str
    booking_id: int
    bill_id: int | None = None
    from_room_no: str | None = None
    to_room_no: str | None = None
    from_room_type_id: int | None = None
    to_room_type_id: int | None = None
    from_price_cents: int | None = None
    to_price_cents: int | None = None
    price_diff_cents: int = 0
    reason: str
    business_date: str
    operator: str = "front_desk"
    created_at: datetime | None = None


class StayExtensionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: str
    hotel_id: int
    booking_id: int
    room_no: str | None = None
    bill_id: int | None = None
    business_date: str
    start_date: str
    end_date: str
    nights: int = 0
    added_amount_cents: int = 0
    is_valid: bool = True
    operator: str = "front_desk"
    created_at: datetime | None = None


class BookingExtrasIn(BaseModel):
    """在住附加服务（加床 / 同住人）。"""

    extra_bed_count: int | None = Field(default=None, ge=0)
    companion_names: list[str] | None = None
    operator: str = "front_desk"


class ReceptionCheckInIn(BaseModel):
    """统一接待办理（绿云前台-散客/预订双模式入住）：

    - 预订模式：传 ``booking_id`` + ``room_no``（前台指定物理房），可选证件登记
      （``guest_phone`` / ``id_type`` / ``id_no``），自动累计客史/关联会员。
    - 散客模式：不传 ``booking_id``，传 ``room_no`` + ``room_type_id`` + ``guest_name``
      + ``check_in_date`` + ``check_out_date``，自动建档（关联会员）+ 建预订 + 入住。
    """

    booking_id: int | None = None
    room_no: str = Field(min_length=1, max_length=16)
    room_type_id: int | None = None
    guest_name: str | None = Field(default=None, max_length=64)
    guest_phone: str | None = Field(default=None, max_length=32)
    id_type: str | None = None
    id_no: str | None = Field(default=None, max_length=32)
    check_in_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    check_out_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    # M32.17：钟点房入住（散客模式；同日入住退房，不占过夜可售房量）
    stay_type: str = "daily"
    hourly_hours: int | None = None
    # M32.7：登记页扩展档案字段（入住时一并写入客档）
    gender: str | None = None  # M|F
    birthday: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    email: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=128)
    nationality: str | None = Field(default=None, max_length=32)
    ethnicity: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=256)
    # 批次② 核心实体字段补全：登记页 6 个 checkbox + 客源/会员号/担保 接线
    guest_source_type: str | None = Field(default=None, max_length=20)
    member_no: str | None = Field(default=None, max_length=32)
    is_vip: bool = False
    is_secret: bool = False
    is_quick_depart: bool = False
    is_print_real_price: bool = True
    is_add_point: bool = True
    is_guarantee: bool = False
    guarantee_hold_until: str | None = None
    operator: str = "front_desk"


# ---------- 统一接待办理流：单客上下文 + 编排状态机（M1 基座，R1/R2） ----------


class ReceptionGuestOut(BaseModel):
    """客档视图（含联动会员等级）。"""

    id: int
    name: str
    phone: str | None = None
    id_type: str | None = None
    id_no: str | None = None
    vip_level: str = "NORMAL"
    gender: str | None = None
    email: str | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    stay_count: int = 0
    total_spend: int = 0
    member_id: int | None = None
    member_level: str | None = None


class ReceptionMembershipOut(BaseModel):
    """联动会员视图（CRM 主数据）。"""

    member_id: int
    name: str
    phone: str
    level: str
    stored_value: int = 0
    points: int = 0
    stays: int = 0


class ReceptionBookingOut(BaseModel):
    """预订视图（含间夜数）。"""

    id: int
    guest_name: str
    guest_phone: str | None = None
    room_type_id: int | None = None
    room_no: str | None = None
    channel: str
    status: str
    check_in_date: str
    check_out_date: str
    total_price: int | None = None
    extra_bed_count: int = 0
    companion_names: list[str] = Field(default_factory=list)
    nights: int = 0


class ReceptionFolioOut(BaseModel):
    """在开账单（结账单位）摘要。"""

    bill_id: int
    bill_no: str
    status: str
    balance: int = 0
    item_count: int = 0
    payment_count: int = 0


class ReceptionAuditOut(BaseModel):
    """办理流相关审计轨迹（该预订最近操作）。"""

    id: int
    action: str
    actor: str
    resource_type: str
    resource_id: str | None = None
    created_at: str | None = None


class ReceptionContext(BaseModel):
    """单客上下文（R1）：聚合客档/会员/预订/房态/账单/审计，并标注办理流状态机位置。

    - ``flow_state`` 由域状态派生（QUERY/REGISTER/INHOUSE/FOLIO/CHECKOUT）；
    - ``can_advance`` 为当前状态下允许的动作（供 UI 单步「继续」按钮渲染）。
    """

    flow_state: str
    can_advance: list[str] = Field(default_factory=list)
    guest: ReceptionGuestOut | None = None
    membership: ReceptionMembershipOut | None = None
    booking: ReceptionBookingOut | None = None
    room_no: str | None = None
    room_state: str | None = None
    folio: ReceptionFolioOut | None = None
    audit_log: list[ReceptionAuditOut] = Field(default_factory=list)
    insights: list[str] = Field(
        default_factory=list,
        description="客史洞察（R7）：由客档/会员派生，供前台一键识别常客/VIP/高价值/偏好。",
    )
    degraded: bool = Field(
        default=False,
        description="Q4 断网降级：任一可选聚合（会员/账单/审计）暂不可用时为 True，上下文仍返回 200。",
    )
    degradation_notes: list[str] = Field(
        default_factory=list,
        description="Q4 断网降级：降级原因列表（如「审计轨迹暂不可用」），供前端非阻塞提示。",
    )


class ReceptionAdvanceIn(BaseModel):
    """办理流状态机驱动入参（R2）：指定动作 + 上下文定位 + 动作所需参数。"""

    action: str  # register | check_in | open_folio | check_out
    guest_phone: str | None = Field(default=None, max_length=32)
    booking_id: int | None = None
    room_no: str | None = Field(default=None, min_length=1, max_length=16)
    hotel_id: int | None = None
    guest_name: str | None = Field(default=None, max_length=64)
    room_type_id: int | None = None
    id_type: str | None = None
    id_no: str | None = Field(default=None, max_length=32)
    check_in_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    check_out_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    operator: str = "front_desk"


# ---------- 团队 / 会议排房（M15，FR-GROUP） ----------


class GroupAllocationIn(BaseModel):
    """排房单项：物理房号 + 房型 + 可选住客。"""

    room_no: str = Field(min_length=1, max_length=16)
    room_type_id: int
    guest_name: str | None = None
    guest_phone: str | None = Field(default=None, max_length=32)


class GroupBlockAssignIn(BaseModel):
    """团队排房：若干房间分配。"""

    allocations: list[GroupAllocationIn]


class GroupAllocationOut(BaseModel):
    id: StrId
    room_no: str
    room_type_id: StrId
    guest_name: str | None = None
    guest_phone: str | None = None
    status: str

    model_config = {"from_attributes": True}


class GroupBlockCreate(BaseModel):
    hotel_id: int
    name: str = Field(min_length=1, max_length=128)
    arrival_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    departure_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str | None = None


class GroupBlockOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    name: str
    arrival_date: str
    departure_date: str
    status: str
    notes: str | None = None
    allocations: list[GroupAllocationOut] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------- 渠道（M6-1 骨架） ----------


class ChannelPushIn(BaseModel):
    room_type_id: int
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class ChannelResultOut(BaseModel):
    channel: str
    integrated: bool
    message: str
    payload: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


# ---------- 会员 CRM（M13） ----------


class MemberCreate(BaseModel):
    hotel_id: int
    name: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=6, max_length=32)
    # 批次② 字段补全
    member_no: str | None = None
    card_type: str | None = None
    join_date: str | None = None


class MemberOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    name: str
    phone: str
    level: str
    stored_value: int
    points: int
    stays: int
    total_spend: int
    # 批次② 字段补全
    member_no: str | None = None
    card_type: str | None = None
    join_date: str | None = None

    model_config = {"from_attributes": True}


class MemberRechargeIn(BaseModel):
    amount: int = Field(ge=1, description="充值金额（分）")
    operator: str = "front_desk"


# ---------- 宾客档案 / 客史（M14，FR-GUEST） ----------


class GuestCreate(BaseModel):
    hotel_id: int
    name: str = Field(min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    id_type: str | None = None  # ID|PASSPORT|OFFICER|OTHER
    id_no: str | None = None
    vip_level: str = "NORMAL"  # NORMAL|SILVER|GOLD|PLATINUM|DIAMOND
    gender: str | None = None  # M|F
    birthday: date | None = None
    email: str | None = None
    address: str | None = None
    tags: list[str] | None = None  # 客史标签
    notes: str | None = None  # 偏好/备注
    member_id: int | None = None  # 关联会员（可选）


class GuestUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    id_type: str | None = None
    id_no: str | None = None
    vip_level: str | None = None
    gender: str | None = None
    birthday: date | None = None
    email: str | None = None
    address: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    member_id: int | None = None


class GuestOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    name: str
    phone: str | None = None
    id_type: str | None = None
    id_no: str | None = None
    vip_level: str
    gender: str | None = None
    birthday: date | None = None
    email: str | None = None
    address: str | None = None
    tags: list[str] = []
    notes: str | None = None
    stay_count: int
    total_spend: int
    member_id: StrId | None = None
    member_level: str | None = None  # 关联会员等级（客档联动会员）
    member_points: int | None = None  # 关联会员积分
    member_stored_value: int | None = None  # 关联会员储值（分）
    # 批次② 字段补全
    en_name: str | None = None
    native_place: str | None = None
    nation: str | None = None
    is_valid: bool = True
    come_time: str | None = None
    head_url: str | None = None
    id_doc_sign_org: str | None = None
    id_doc_valid_to: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            if not v:
                return []
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v


# ---------- 前台收银（M3） ----------


class BillOpenIn(BaseModel):
    hotel_id: int
    guest_name: str = Field(min_length=1, max_length=64)
    room_no: str | None = None
    booking_id: int | None = None
    source: str | None = None  # BOOKING|WALK_IN；缺省按 booking_id 自动判定（无预订=散客）


class ChargeIn(BaseModel):
    charge_type: str = Field(pattern=r"^(ROOM_CHARGE|MISC|DISCOUNT|REFUND)$")
    amount: int  # 正应收/负冲减
    description: str = ""
    operator: str = "front_desk"  # 加账操作员（M23 交班应收口径按此聚合）


class PaymentIn(BaseModel):
    method: str = Field(pattern=r"^(CASH|PREAUTH|WECHAT|ALIPAY|UNIONPAY|STORE_VALUE)$")
    amount: int = Field(ge=1, description="收款金额（分）")
    is_deposit: bool = False
    ref_no: str | None = None
    operator: str = "front_desk"  # 收款操作员（交班现金对账按此聚合）


class BillItemOut(BaseModel):
    id: StrId
    type: str
    amount: int
    description: str

    model_config = {"from_attributes": True}


class PaymentOut(BaseModel):
    id: StrId
    method: str
    amount: int
    is_deposit: bool

    model_config = {"from_attributes": True}


class BillOut(BaseModel):
    id: StrId
    tenant_id: str
    bill_no: str
    hotel_id: StrId
    booking_id: StrId | None = None
    guest_name: str
    room_no: str | None
    ar_account_id: StrId | None = None  # M24：挂账协议单位
    source: str
    status: str
    balance: int
    items: list[BillItemOut]
    payments: list[PaymentOut]
    adjustments: list["AdjustmentOut"] = []

    model_config = {"from_attributes": True}


# ---------- M24 协议单位挂账（AR） ----------


class ArAccountCreate(BaseModel):
    hotel_id: int
    name: str = Field(min_length=1, max_length=64)
    contact: str | None = None
    contact_phone: str | None = None
    credit_limit_cents: int = Field(default=0, ge=0, description="分；0=不限额")
    note: str | None = None
    operator: str = "front_desk"


class ArAccountOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    name: str
    contact: str | None = None
    contact_phone: str | None = None
    credit_limit_cents: int
    balance_cents: int
    note: str | None = None
    status: str

    model_config = {"from_attributes": True}


class ArRepaymentIn(BaseModel):
    amount: int = Field(gt=0, description="还款金额（分），不得超过欠款")
    method: str = Field(default="BANK", pattern=r"^(BANK|CASH|WECHAT|ALIPAY|UNIONPAY)$")
    operator: str = "front_desk"
    note: str | None = None


class ArRepaymentOut(BaseModel):
    id: StrId
    tenant_id: str
    ar_account_id: StrId
    amount: int
    method: str
    operator: str
    note: str | None = None

    model_config = {"from_attributes": True}


class ArChargeIn(BaseModel):
    """把某账单余额挂到协议单位（结账方式 COMPANY）。"""

    bill_id: int
    operator: str = "front_desk"


class AdjustmentIn(BaseModel):
    type: str = Field(pattern=r"^(VOID|ADJUST)$", description="VOID 红冲 | ADJUST 调账")
    amount_cents: int = Field(description="有符号余额增量（分），负=冲减应收/退收，正=补收")
    reason: str = ""
    operator: str = "front_desk"


class AdjustmentOut(BaseModel):
    id: StrId
    bill_id: StrId | None
    type: str
    amount_cents: int
    reason: str
    operator: str

    model_config = {"from_attributes": True}


# ---------- 夜审（M4） ----------


class NightAuditIn(BaseModel):
    hotel_id: int
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    operator: str = "night_audit"


class DailyReportOut(BaseModel):
    id: StrId
    hotel_id: StrId
    business_date: str
    arrived_rooms: int
    departed_rooms: int
    occupied_rooms: int
    total_rooms: int
    room_revenue: int
    other_revenue: int
    total_revenue: int
    adr: int
    occ_pct: int
    snapshot: str = "{}"

    model_config = {"from_attributes": True}


class BusinessDayOut(BaseModel):
    id: StrId
    hotel_id: StrId
    business_date: str
    status: str
    audited_by: str | None
    suspended_reason: str | None

    model_config = {"from_attributes": True}


class NightAuditBoardHotelOut(BaseModel):
    hotel_id: int
    name: str
    latest_business_date: str | None = None
    latest_status: str | None = None
    suspended_count: int = 0
    latest_report: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class NightAuditBoardOut(BaseModel):
    hotels: list[NightAuditBoardHotelOut] = Field(default_factory=list)
    hotel_count: int = 0
    total_suspended: int = 0

    model_config = {"from_attributes": True}


class AutoRunIn(BaseModel):
    as_of: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="截至（含）该营业日进行批量夜审")
    operator: str = "scheduler"


class AutoRunOut(BaseModel):
    ran: int = 0
    suspended: int = 0
    skipped: int = 0
    errors: list[dict] = Field(default_factory=list)
    skips: list[dict] = Field(default_factory=list)


# ---------- 佣金对账（M4-4） ----------


class CommissionRuleIn(BaseModel):
    channel: str
    rate_bps: int = Field(ge=0, le=10000, description="费率（基点），10000=100%")
    note: str = ""


class CommissionRuleOut(BaseModel):
    id: StrId
    tenant_id: str
    channel: str
    rate_bps: int
    note: str

    model_config = {"from_attributes": True}


class CommissionReconciliationOut(BaseModel):
    id: StrId
    hotel_id: StrId
    business_date: str
    channel: str
    room_revenue_cents: int
    commission_rate_bps: int
    commission_cents: int
    status: str
    reconciled_at: str | None

    model_config = {"from_attributes": True}


# ---------- 前台收银交班（M3） ----------


class ShiftOpenIn(BaseModel):
    hotel_id: int
    cashier: str = Field(min_length=1, max_length=64)
    opening_float_cents: int = Field(default=0, ge=0, description="备用金（分）")


class ShiftCloseIn(BaseModel):
    counted_cash_cents: int = Field(ge=0, description="实点现金（分）")
    note: str = ""


class ShiftOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    cashier: str
    status: str
    opening_float_cents: int
    expected_cash_cents: int
    counted_cash_cents: int
    discrepancy_cents: int
    # M23 交班三口径（清单#11）：现金流=备用金+班内现金；实收=班内全方式收款；应收=班内新增应收
    received_cents: int = 0
    receivable_cents: int = 0
    opened_at: str | None
    closed_at: str | None
    note: str

    model_config = {"from_attributes": True}


# ---------- 叫醒服务（M3-7） ----------


class WakeUpCallIn(BaseModel):
    hotel_id: int
    room_no: str = Field(min_length=1, max_length=16)
    call_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$", description="ISO 时刻")
    guest_name: str = ""
    note: str = ""
    operator: str = "front_desk"


class WakeUpCallOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    room_no: str
    guest_name: str
    call_at: datetime
    status: str
    note: str

    model_config = {"from_attributes": True}


# ---------- PSB 上传队列（M3-5） ----------


class PsbTaskIn(BaseModel):
    hotel_id: int
    guest_name: str = Field(min_length=1, max_length=64)
    id_doc_no: str | None = None
    room_no: str | None = None
    operator: str = "front_desk"


class PsbTaskOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    booking_id: StrId | None
    guest_name: str
    id_doc_no_masked: str | None
    room_no: str | None
    status: str
    uploaded_at: datetime | None
    operator: str

    model_config = {"from_attributes": True}


# ---------- 权限审计（M8） ----------


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""
    scope: str = "tenant"  # tenant | hotel


class UserOut(BaseModel):
    id: StrId
    tenant_id: str
    username: str
    display_name: str
    status: str
    scope: str
    failed_attempts: int
    last_login_at: datetime | None
    last_login_ip: str | None

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    level: str = "STAFF"  # ADMIN | MANAGER | STAFF
    permissions: list[str] = Field(default_factory=list)
    hotel_scoped: bool = False


class RoleOut(BaseModel):
    id: StrId
    tenant_id: str
    name: str
    level: str
    is_system: bool
    hotel_scoped: bool
    permissions: list[str]

    model_config = {"from_attributes": True}


class UserRoleIn(BaseModel):
    role_id: int
    hotel_id: int | None = None


class UserRoleOut(BaseModel):
    id: StrId
    tenant_id: str
    user_id: StrId
    role_id: StrId
    hotel_id: StrId | None

    model_config = {"from_attributes": True}


class LoginIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    ip: str | None = None


class LoginOut(BaseModel):
    token: str | None = None
    refresh_token: str | None = None  # M18-2：刷新令牌（一次性旋转）
    username: str
    display_name: str
    status: str  # ok | locked | bad_credentials | disabled | not_found
    permissions: list[str] = Field(default_factory=list)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1)


class RefreshOut(BaseModel):
    token: str
    refresh_token: str
    username: str
    display_name: str
    status: str = "ok"
    permissions: list[str] = Field(default_factory=list)


class LogoutIn(BaseModel):
    token: str = Field(min_length=1)


class PermissionCheckIn(BaseModel):
    token: str = Field(min_length=1)
    permission: str = Field(min_length=1)
    hotel_id: int | None = None


class PermissionCheckOut(BaseModel):
    granted: bool
    permission: str
    username: str | None = None


class AuditLogOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId | None
    actor_id: StrId | None
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    result: str
    ip: str | None
    detail: dict
    created_at: datetime | None

    model_config = {"from_attributes": True}


# ---------- 移动端直订小程序（M7） ----------


class MpOfferNight(BaseModel):
    date: str
    price: int
    available: int


class MpOfferOut(BaseModel):
    room_type_id: StrId
    code: str
    name: str
    nights: int
    price_per_night: list[MpOfferNight]
    total_price: int
    available: int
    bookable: bool
    sold_out_dates: list[str]


class MpOrderPlaceIn(BaseModel):
    hotel_id: int
    room_type_id: int
    guest_name: str = Field(min_length=1, max_length=64)
    check_in_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    check_out_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    guest_phone: str | None = None


class PayOrderOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    out_trade_no: str
    channel: str
    booking_id: StrId | None
    bill_id: StrId | None
    subject: str
    amount_cents: int
    status: str
    prepay_id: str | None
    transaction_id: str | None
    paid_at: datetime | None
    close_reason: str | None = None

    model_config = {"from_attributes": True}


class MpOrderOut(BaseModel):
    booking: BookingOut
    pay_order: PayOrderOut


# ---------- 移动支付（M7-2） ----------


class PayNotifyIn(BaseModel):
    out_trade_no: str = Field(min_length=1)
    amount_cents: int = Field(ge=0)
    transaction_id: str = Field(min_length=1)
    notify_id: str = Field(min_length=1)
    payload: dict = Field(default_factory=dict)


class PayNotifyResultOut(BaseModel):
    result: str  # PROCESSED | DUPLICATE | REJECTED
    posted_to_bill: bool | None = None


class PayReconcileIn(BaseModel):
    before: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$",
        description="仅处理该时刻之前创建的未支付单（ISO 时刻）",
    )


class PayReconcileOut(BaseModel):
    scanned: int
    closed: int
    recovered: int
    details: list[dict] = Field(default_factory=list)


# ---------- 店长 App（M10） ----------


class ApprovalSubmitIn(BaseModel):
    hotel_id: int
    type: str = Field(pattern=r"^(DISCOUNT|ADJUST|OVERBOOK|REFUND)$")
    payload: dict = Field(default_factory=dict, description="审批通过后的执行参数")
    reason: str = ""
    applicant: str = "front_desk"


class ApprovalDecideIn(BaseModel):
    decision: str = Field(pattern=r"^(APPROVE|REJECT)$")
    approver: str = Field(min_length=1)
    note: str = ""


class ApprovalTicketOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    type: str
    payload: dict
    reason: str
    applicant: str
    status: str
    approver: str | None
    decision_note: str | None
    decided_at: datetime | None
    ref_id: StrId | None

    model_config = {"from_attributes": True}


class HousekeepingTaskIn(BaseModel):
    hotel_id: int
    room_no: str = Field(min_length=1, max_length=16)
    task_type: str = Field(default="CLEANUP", pattern=r"^(CLEANUP|MAINTENANCE|INSPECT)$")
    assignee: str | None = None
    note: str = ""
    due_at: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$"
    )


class HousekeepingAssignIn(BaseModel):
    assignee: str = Field(min_length=1, max_length=64)


class HousekeepingBatchAssignIn(BaseModel):
    """M26 批量派单。"""

    task_ids: list[int] = Field(min_length=1)
    assignee: str = Field(min_length=1, max_length=64)


class HousekeepingBatchDoneIn(BaseModel):
    """M26 批量完成。"""

    task_ids: list[int] = Field(min_length=1)
    operator: str = "front_desk"


class HousekeepingTaskOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    room_no: str
    task_type: str
    status: str
    assignee: str | None
    source: str
    note: str
    due_at: datetime | None
    done_at: datetime | None

    model_config = {"from_attributes": True}


class NotificationOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId | None
    recipient: str
    channel: str
    title: str
    body: str
    ref_type: str | None
    ref_id: StrId | None
    # ③ 通知分级与免打扰
    level: str = "normal"
    muted: bool = False
    # ④ 多接收人：本通知最终接收角色列表
    recipients: list[str] = Field(default_factory=list)
    link: str | None
    read_at: datetime | None
    created_at: datetime | None

    model_config = {"from_attributes": True}

    @field_validator("recipients", mode="before")
    @classmethod
    def _coerce_recipients(cls, v: object) -> list[str]:
        # 历史行未存 recipients 时 ORM 取到 None，统一兜底为空列表
        return v or []


class NotificationSubscriptionOut(BaseModel):
    tenant_id: str
    ref_type: str
    label: str = ""  # REF_LABELS 中文标签（前端展示用）
    recipients: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class NotificationSubscriptionItemIn(BaseModel):
    """单条订阅配置（批量 upsert 的元素）。"""

    ref_type: str = Field(min_length=1, max_length=32)
    recipients: list[str] = Field(default_factory=list)


class NotificationSubscriptionBulkIn(BaseModel):
    """批量更新订阅配置：传入的每一项按 (tenant_id, ref_type) upsert。"""

    items: list[NotificationSubscriptionItemIn] = Field(default_factory=list)


class NotificationPreferenceOut(BaseModel):
    tenant_id: str
    dnd_enabled: bool
    dnd_start: str
    dnd_end: str

    model_config = {"from_attributes": True}


class NotificationPreferenceUpdateIn(BaseModel):
    dnd_enabled: bool | None = None
    dnd_start: str | None = None
    dnd_end: str | None = None


class DashboardOut(BaseModel):
    hotel_id: StrId
    business_date: str
    rooms: dict
    occupancy_pct: int
    in_house: int
    arrivals: list[BookingOut]
    departures: list[BookingOut]
    latest_report: DailyReportOut | None
    alerts: dict


# ---------- 集团多店管控（M17） ----------


class GroupPricePolicyIn(BaseModel):
    price_floor_cents: int = Field(ge=0)
    price_ceiling_cents: int | None = Field(default=None, ge=0)
    hotel_id: int | None = None
    room_type_id: int | None = None
    note: str = ""


class GroupPricePolicyOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId | None
    room_type_id: StrId | None
    price_floor_cents: int
    price_ceiling_cents: int | None
    status: str
    issued_by: str
    note: str
    created_at: datetime | None

    model_config = {"from_attributes": True}


class HqDashboardOut(BaseModel):
    hotels: list[dict]
    hotel_count: int
    total_revenue: int
    total_room_revenue: int


class SettlementRowOut(BaseModel):
    hotel_id: StrId
    name: str
    pay_now_cents: int
    prepaid_cents: int
    total_cents: int


class SettlementOut(BaseModel):
    hotels: list[SettlementRowOut]
    group: dict


# ---------- AI 服务（M11/M12） ----------


class ChatSessionCreate(BaseModel):
    channel: str = Field(default="wechat_mp", pattern=r"^(wechat_mp|mini_app|web)$")
    guest_name: str | None = Field(default=None, max_length=64)
    guest_phone: str | None = Field(default=None, max_length=32)


class ChatMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=512)
    hotel_id: int | None = None


class ChatMessageOut(BaseModel):
    id: StrId
    session_id: StrId
    role: str
    content: str
    intent: str | None
    confidence: float | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class ChatSessionOut(BaseModel):
    id: StrId
    tenant_id: str
    channel: str
    guest_name: str | None
    guest_phone: str | None
    status: str
    intent: str | None
    satisfaction: int | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class ChatHandoffIn(BaseModel):
    reason: str = Field(default="用户请求人工", max_length=128)
    hotel_id: int | None = None


class ChatCloseIn(BaseModel):
    satisfaction: int | None = Field(default=None, ge=1, le=5)


class ChatReplyOut(BaseModel):
    bot_message: ChatMessageOut
    handoff: bool
    intent: str | None
    confidence: float | None


class AlertNotificationOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId | None
    alert_type: str
    severity: str
    title: str
    description: str
    ref_type: str | None
    ref_id: str | None
    status: str
    suggested_action: str | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


# ---------- 数据中台/经营分析（M16） ----------


class AnalyticsDashboardOut(BaseModel):
    hotel_id: StrId
    hotel_name: str
    start_date: str | None
    end_date: str | None
    days: int
    total_rooms: int
    occupied_room_nights: int
    room_revenue_cents: int
    other_revenue_cents: int
    total_revenue_cents: int
    revpar_cents: int
    adr_cents: int
    occ_pct_bps: int
    daily_series: list[dict]


class HotelRankingOut(BaseModel):
    hotel_id: StrId
    name: str
    days: int
    room_revenue_cents: int
    total_revenue_cents: int
    revpar_cents: int
    adr_cents: int
    occ_pct_bps: int


class AnalyticsRankingOut(BaseModel):
    hotels: list[HotelRankingOut]
    hotel_count: int
    total_room_revenue_cents: int
    total_revenue_cents: int


class ChannelRevenueRowOut(BaseModel):
    channel: str
    booking_count: int
    room_revenue_cents: int


class AnalyticsChannelOut(BaseModel):
    hotel_id: StrId
    hotel_name: str
    start_date: str | None
    end_date: str | None
    channels: list[ChannelRevenueRowOut]
    total_bookings: int
    total_room_revenue_cents: int


class RoomTypeRevenueRowOut(BaseModel):
    room_type_id: StrId
    room_type_name: str
    booking_count: int
    room_revenue_cents: int


class AnalyticsRoomTypeOut(BaseModel):
    hotel_id: StrId
    hotel_name: str
    start_date: str | None
    end_date: str | None
    room_types: list[RoomTypeRevenueRowOut]
    total_bookings: int
    total_room_revenue_cents: int


class PaymentSummaryRowOut(BaseModel):
    method: str
    amount_cents: int


class AnalyticsPaymentOut(BaseModel):
    hotel_id: StrId
    hotel_name: str
    start_date: str | None
    end_date: str | None
    methods: list[PaymentSummaryRowOut]
    total_cents: int


class AnalyticsExportQuery(BaseModel):
    report_type: str = Field(pattern=r"^(dashboard|hotel_ranking|channel_revenue|room_type_revenue)$")
    hotel_id: int | None = None
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    format: str = Field(default="json", pattern=r"^(json|csv)$")


# ---------- 开放 API 平台（M18） ----------


class OpenApiAppCreate(BaseModel):
    app_code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    callback_url: str | None = Field(default=None, max_length=512)
    events_subscribed: list[str] = Field(default_factory=list)


class OpenApiAppOut(BaseModel):
    id: StrId
    tenant_id: str
    app_code: str
    name: str
    status: str
    callback_url: str | None
    events_subscribed: list[str]
    created_at: datetime | None

    model_config = {"from_attributes": True}


class OpenApiKeyOut(BaseModel):
    id: StrId
    app_id: StrId
    key_mask: str
    status: str
    created_at: datetime | None
    revoked_at: str | None

    model_config = {"from_attributes": True}


class OpenApiKeyWithSecret(BaseModel):
    key: OpenApiKeyOut
    secret: str


class OpenApiWebhookIn(BaseModel):
    app_id: int
    topic: str = Field(min_length=1, max_length=128)
    endpoint_url: str = Field(min_length=1, max_length=512)
    secret: str | None = Field(default=None, max_length=128)


class OpenApiWebhookOut(BaseModel):
    id: StrId
    tenant_id: str
    app_id: StrId
    topic: str
    endpoint_url: str
    status: str
    created_at: datetime | None

    model_config = {"from_attributes": True}


class OpenApiWebhookTestOut(BaseModel):
    id: StrId
    event_topic: str
    status: str
    http_status: int | None
    error_message: str | None

    model_config = {"from_attributes": True}


class OpenApiVerifyKeyIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=128)


# ---------- M15 收益管理：简版调价建议 ----------


class PricingRuleOut(BaseModel):
    id: StrId
    tenant_id: str
    name: str
    enabled: int
    high_occ_threshold: int
    low_occ_threshold: int
    max_uplift_bps: int
    max_discount_bps: int
    weekend_uplift_bps: int
    competitor_strategy: str
    competitor_undercut_bps: int

    model_config = {"from_attributes": True}


class PricingRuleIn(BaseModel):
    """更新调价规则（全部可选；未传字段保持默认/当前值）。"""

    name: str | None = None
    enabled: int | None = Field(default=None, ge=0, le=1)
    high_occ_threshold: int | None = Field(default=None, ge=0, le=100)
    low_occ_threshold: int | None = Field(default=None, ge=0, le=100)
    max_uplift_bps: int | None = Field(default=None, ge=0, le=10000)
    max_discount_bps: int | None = Field(default=None, ge=0, le=10000)
    weekend_uplift_bps: int | None = Field(default=None, ge=0, le=10000)
    competitor_strategy: str | None = Field(default=None, pattern=r"^(none|match|undercut)$")
    competitor_undercut_bps: int | None = Field(default=None, ge=0, le=10000)


class PriceRecommendIn(BaseModel):
    hotel_id: int = Field(gt=0)
    room_type_id: int | None = None
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    base_price_cents: int = Field(gt=0, description="基价（分）")
    competitor_price_cents: int | None = Field(default=None, gt=0)
    lead_time_days: int | None = Field(default=None, ge=0, le=365)


class PriceRecommendOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    room_type_id: StrId | None
    business_date: str
    base_price_cents: int
    recommended_price_cents: int
    adjustment_bps: int
    demand_index: int
    sample_days: int
    status: str
    rationale: list[str] = []

    model_config = {"from_attributes": True}

    @field_validator("rationale", mode="before")
    @classmethod
    def _parse_rationale(cls, v: object) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []


class PriceRecommendationOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    room_type_id: StrId | None
    business_date: str
    base_price_cents: int
    recommended_price_cents: int
    adjustment_bps: int
    demand_index: int
    sample_days: int
    status: str
    rationale: list[str] = []

    model_config = {"from_attributes": True}

    @field_validator("rationale", mode="before")
    @classmethod
    def _parse_rationale_rec(cls, v: object) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []


class YieldApplyIn(BaseModel):
    """M20 批量应用可选参数：传 start/end 则按区间落价，否则仅建议日单日。"""

    start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class YieldApplyOut(BaseModel):
    """M20：调价建议一键应用到价格日历的结果。"""

    rec_id: StrId
    status: str  # applied
    room_type_id: StrId
    business_date: str
    price: int  # 落库价（分）
    dates: list[str] = Field(default_factory=list)  # 实际落价日期
    updated: int  # 更新已有日历行数
    created: int  # 新建日历行数


# ---------- M21 餐饮 POS（F&B） ----------
class MenuItemIn(BaseModel):
    hotel_id: int
    name: str
    category: str = "其他"
    price_cents: int = Field(ge=0, description="分")
    is_active: int = Field(default=1, ge=0, le=1)


class MenuItemOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    name: str
    category: str
    price_cents: int
    is_active: int
    sold_out: int = 0  # M27：沽清 0/1


class MenuItemPatch(BaseModel):
    """菜品部分更新（上下架 / 改价），字段均可选。"""

    hotel_id: int | None = None
    name: str | None = None
    category: str | None = None
    price_cents: int | None = Field(default=None, ge=0, description="分")
    is_active: int | None = Field(default=None, ge=0, le=1)


class DiningTableIn(BaseModel):
    hotel_id: int
    table_no: str
    seats: int = 2
    zone: str | None = None


class DiningTableOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    table_no: str
    seats: int
    zone: str | None = None
    state: str


class PosOrderOpenIn(BaseModel):
    hotel_id: int
    table_id: int | None = None
    room_no: str | None = None
    guest_name: str | None = None
    booking_id: int | None = None


class PosOrderItemIn(BaseModel):
    name: str
    qty: int = Field(default=1, ge=1)
    unit_price_cents: int = Field(default=0, ge=0)
    item_id: int | None = None


class PosOrderItemOut(BaseModel):
    id: int
    order_id: int
    item_id: int | None = None
    name: str
    category: str | None = None
    qty: int
    unit_price_cents: int
    subtotal_cents: int
    kds_status: str = "pending"
    voided: int = 0  # M27：退菜 0/1
    void_reason: str | None = None  # M27：退菜原因


class PosOrderOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    table_id: int | None = None
    status: str
    settle_type: str | None = None
    room_no: str | None = None
    booking_id: int | None = None
    guest_name: str | None = None
    total_cents: int
    discount_cents: int = 0  # M27：整单折扣（分）
    items: list[PosOrderItemOut] = Field(default_factory=list)


class FnbSoldOutIn(BaseModel):
    """M27 沽清 / 恢复供应。"""

    sold_out: bool
    operator: str = "fnb"


class FnbVoidIn(BaseModel):
    """M27 退菜。"""

    reason: str = ""
    operator: str = "fnb"


class FnbDiscountIn(BaseModel):
    """M27 整单折扣：discount_cents（分）或 percent（1-99）二选一。"""

    discount_cents: int | None = Field(default=None, ge=0)
    percent: int | None = Field(default=None, ge=1, le=99)
    operator: str = "fnb"


class PosSettleRoomIn(BaseModel):
    room_no: str
    operator: str = "fnb"


class PosSettleCashIn(BaseModel):
    amount_paid: int | None = Field(default=None, ge=1, description="分；缺省按账单总额")
    operator: str = "fnb"


# ---------- 餐饮报表（M22） ----------
class FnbCategorySales(BaseModel):
    category: str
    qty: int
    revenue_cents: int


class FnbTableSales(BaseModel):
    table_no: str
    order_count: int
    revenue_cents: int


class FnbReportOut(BaseModel):
    total_revenue_cents: int
    order_count: int
    item_count: int
    avg_per_table_cents: int
    by_category: list[FnbCategorySales] = Field(default_factory=list)
    by_table: list[FnbTableSales] = Field(default_factory=list)


# ---------- 厨房出单 KDS（M22） ----------
class KitchenTicketOut(BaseModel):
    item_id: int
    order_id: int
    table_no: str | None = None
    room_no: str | None = None
    guest_name: str | None = None
    name: str
    category: str | None = None
    qty: int
    kds_status: str


# ---------- M28：投诉工单 ----------

class ComplaintCreate(BaseModel):
    hotel_id: int
    guest_name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)
    booking_id: int | None = None
    guest_phone: str | None = Field(default=None, max_length=32)
    room_no: str | None = Field(default=None, max_length=16)
    source: str = Field(default="FRONT_DESK", max_length=16)
    category: str = Field(default="SERVICE", max_length=32)


class ComplaintOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    booking_id: int | None = None
    guest_name: str
    guest_phone: str | None = None
    room_no: str | None = None
    source: str
    category: str
    status: str
    description: str
    handler: str | None = None
    resolution: str | None = None
    handled_at: datetime | None = None
    created_at: datetime | None = None


class ComplaintTransitionIn(BaseModel):
    to_status: str = Field(pattern="^(HANDLING|RESOLVED|CANCELLED)$")
    handler: str | None = Field(default=None, max_length=64)
    resolution: str | None = Field(default=None, max_length=512)
    operator: str = Field(default="front_desk", max_length=64)


# ---------- M29：OTA 直连 ----------

class OtaConfigIn(BaseModel):
    hotel_id: int
    channel: str = Field(min_length=1, max_length=32)
    secret: str = Field(min_length=8, max_length=128)
    app_key: str = Field(default="", max_length=64)
    push_enabled: bool = True
    push_inventory_url: str | None = Field(default=None, max_length=256)


class OtaConfigOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    channel: str
    app_key: str
    push_enabled: int
    push_inventory_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OtaOrderInjectIn(BaseModel):
    """OTA webhook 订单体（签名覆盖原始字节，此模型仅解析）。"""

    external_ref: str = Field(min_length=1, max_length=64)
    room_type_code: str = Field(min_length=1, max_length=32)
    guest_name: str = Field(default="OTA客", max_length=64)
    guest_phone: str | None = Field(default=None, max_length=32)
    check_in_date: str = Field(min_length=10, max_length=10)
    check_out_date: str = Field(min_length=10, max_length=10)
    hotel_id: int | None = None
    total_price_cents: int | None = None


class OtaOrderInjectOut(BaseModel):
    booking_id: int
    external_ref: str
    channel: str
    status: str
    created: bool


# ---------- M29：OTA 房型映射 / 渠道价 / 推送日志 ----------


class ChannelRoomMappingIn(BaseModel):
    hotel_id: int
    channel: str = Field(min_length=1, max_length=32)
    pms_room_type_id: int
    external_room_type_code: str = Field(min_length=1, max_length=64)
    enabled: bool = True


class ChannelRoomMappingOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    channel: str
    pms_room_type_id: int
    external_room_type_code: str
    enabled: int

    model_config = ConfigDict(from_attributes=True)


class ChannelRatePlanIn(BaseModel):
    hotel_id: int
    channel: str = Field(min_length=1, max_length=32)
    pms_room_type_id: int
    effective_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    price_cents: int = Field(gt=0)
    enabled: bool = True


class ChannelRatePlanOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    channel: str
    pms_room_type_id: int
    effective_date: str | None = None
    price_cents: int
    enabled: int

    model_config = ConfigDict(from_attributes=True)


class ChannelPushLogOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    channel: str
    days: int
    status: str
    trace_id: str
    item_count: int
    duration_ms: int
    error_message: str | None = None
    operator: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------- M31：核心缺口关闭 ----------

class PointsPayIn(BaseModel):
    """积分抵扣支付（M31，验收 #9）：1 积分 = 1 分。"""

    member_phone: str = Field(min_length=1, max_length=32)
    points: int = Field(gt=0, le=100_000_000)
    operator: str = Field(default="front_desk", max_length=64)


class PointsPayOut(BaseModel):
    payment_id: int
    amount_cents: int
    points_used: int
    member_points_left: int


class GroupAllocationSettleIn(BaseModel):
    """团队逐间分批结账（M31，验收 #10）。"""

    operator: str = Field(default="front_desk", max_length=64)


class GroupAllocationSettleOut(BaseModel):
    allocation_id: int
    room_no: str
    guest_name: str | None = None
    bill_id: str | None = None
    total_cents: int
    settled: bool
    block_settled_count: int
    block_total_count: int


class GroupSettlementOut(BaseModel):
    block_id: int
    status: str
    total_allocations: int
    settled_allocations: int
    total_cents: int
    settled_cents: int
    rows: list[GroupAllocationSettleOut]


class RoomDndIn(BaseModel):
    dnd: bool
    operator: str = Field(default="front_desk", max_length=64)


# ---------- M32：P1 四项 ----------

class RoomLookupOut(BaseModel):
    """挂账前房号查询（验收 #48）：展示客人姓名/离店日期，防挂错。"""

    room_no: str
    occupied: bool
    guest_name: str | None = None
    guest_phone_masked: str | None = None
    check_out_date: str | None = None
    bill_id: int | str | None = None
    bill_balance: int | None = None
    warning: str | None = None


class HkInspectIn(BaseModel):
    passed: bool
    operator: str = Field(default="supervisor", max_length=64)
    note: str = Field(default="", max_length=256)


class SnapshotGenerateIn(BaseModel):
    hotel_id: int
    period_type: str = Field(pattern="^(WEEKLY|MONTHLY)$")
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)


class SnapshotOut(BaseModel):
    id: int
    tenant_id: str
    hotel_id: int
    period_type: str
    period_start: date
    period_end: date
    metrics: dict[str, Any] = Field(default_factory=dict)
    source: str

    model_config = ConfigDict(from_attributes=True)

    @field_validator("metrics", mode="before")
    @classmethod
    def _parse_metrics(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v


# ============================================================ M32.18 押金 ===


class DepositIn(BaseModel):
    """收押金 / 冻结预授权入参。"""

    hotel_id: int
    booking_id: int | None = None
    room_no: str | None = None
    bill_id: int | None = None
    kind: str = Field(pattern="^(DEPOSIT|PREAUTH)$")
    method: str = Field(pattern="^(CASH|WECHAT|ALIPAY|UNIONPAY|STORE_VALUE)$")
    amount: int = Field(ge=1, le=99_999_999, description="押金金额（分），1 ~ 99999999")
    ref_no: str | None = None
    currency: str = "CNY"
    operator: str = "front_desk"
    note: str | None = None


class DepositApplyIn(BaseModel):
    amount: int = Field(ge=1, description="冲抵金额（分）")
    target_bill_id: int | None = None
    operator: str = "front_desk"
    expected_version: int | None = None


class DepositRefundIn(BaseModel):
    amount: int = Field(ge=1, description="退还金额（分）")
    operator: str = "front_desk"
    note: str | None = None  # 退款原因（审计必留）
    expected_version: int | None = None


class DepositVoidIn(BaseModel):
    operator: str = "front_desk"
    reason: str | None = None
    expected_version: int | None = None


class DepositReleaseIn(BaseModel):
    operator: str = "front_desk"
    cause: str = "MANUAL"  # MANUAL | SETTLED | EXPIRED
    expected_version: int | None = None


class DepositCaptureIn(BaseModel):
    """预授权请款入参。``amount=None`` 表示全额请款（按授权额度）。"""

    amount: int | None = Field(default=None, ge=1, description="请款金额（分）；缺省=全额请款")
    operator: str = "front_desk"
    expected_version: int | None = None


class DepositTransactionOut(BaseModel):
    id: int
    action: str
    amount_cents: int
    method: str
    ref_no: str | None
    bill_id: int | None
    operator: str
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DepositOut(BaseModel):
    id: StrId
    tenant_id: str
    hotel_id: StrId
    deposit_no: str
    booking_id: StrId | None
    room_no: str | None
    bill_id: StrId | None
    kind: str
    method: str
    amount_cents: int
    applied_cents: int
    refunded_cents: int
    forfeited_cents: int
    available_cents: int
    status: str
    release_cause: str | None
    currency: str
    ref_no: str | None
    operator: str
    expires_at: str | None
    released_at: str | None
    captured_at: str | None
    voided_at: str | None
    version: int
    note: str | None
    created_at: datetime
    transactions: list[DepositTransactionOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AutoReleaseIn(BaseModel):
    hotel_id: int | None = None
    days: int = 30
    operator: str = "system"


class AutoReleaseOut(BaseModel):
    released: int
    ids: list[int]


# ---------- M34d 全局搜索 ----------


class SearchResultItem(BaseModel):
    """M34d 全局搜索单条结果：跨 7 实体的统一结果条目。"""

    type: str  # guest / booking / room / bill / member / group / notification
    id: int | str  # 实体主键（int 主键为主，notification 也是 BigInt）
    title: str  # 主标（宾客姓名 / 订单号 / 房号 / 账单号 / 会员姓名 / 团队名 / 通知标题）
    subtitle: str  # 副标（手机号 / 入住日期 / 房型 / 金额 / 会员等级 / 入住人 / 通知摘要）
    href: str  # 前端跳转路径
    badge: str | None = None  # 状态徽章文本
    badge_color: str | None = None  # 徽章颜色（antd Tag color：red/green/blue/...）


class SearchResultOut(BaseModel):
    """M34d 全局搜索响应：聚合跨实体结果 + 各类型命中计数。"""

    items: list[SearchResultItem]
    total: int
    by_type: dict[str, int]  # {"guest": 3, "booking": 2, ...} 各类型命中数
    query: str


# ---------- M37-④ 早餐券 + 优惠券 + 房间属性 + 黑名单 ----------


class RoomAttributeOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: str
    hotel_id: int
    room_id: int
    room_no: str
    attribute_code: str
    attribute_name: str
    is_valid: bool = True
    operator: str = "front_desk"
    memo: str | None = None
    created_at: datetime | None = None


class RoomAttributeIn(BaseModel):
    """房间属性全量覆盖（幂等：先软删再插）。"""

    codes: list[str] = Field(default_factory=list)
    memo: str | None = Field(default=None, max_length=128)
    operator: str = "front_desk"


class BlackGuestIn(BaseModel):
    """加入黑名单：姓名必填，证件号/手机号至少填一个（提高匹配精度）。"""

    hotel_id: int | None = None  # 空 = 全集团生效
    name: str = Field(min_length=1, max_length=64)
    id_no: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    reason: str = Field(min_length=1, max_length=255)
    level: int = Field(default=0, ge=0, le=3)
    operator: str = "front_desk"


class BlackGuestOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: str
    hotel_id: int | None = None
    name: str
    id_no: str | None = None
    phone: str | None = None
    reason: str
    level: int = 0
    is_valid: bool = True
    operator: str = "front_desk"
    created_at: datetime | None = None


class BlacklistHit(BaseModel):
    """黑名单命中项（仅提醒，不硬阻断）。"""

    id: int
    name: str
    reason: str
    level: int = 0
    matched_by: str  # id_no|phone|name
    strong: bool  # id_no/phone 命中才算强命中


class BreakfastIssueIn(BaseModel):
    """发早餐券（一次 count 张）。"""

    booking_id: int | None = None
    room_no: str | None = Field(default=None, max_length=16)
    ticket_type: int = 0  # 0 送早 / 5 兑早 / 9 购早
    ticket_type_name: str | None = Field(default=None, max_length=64)
    count: int = Field(default=1, ge=1, le=100)
    valid_from: str | None = Field(default=None, max_length=10)
    valid_to: str | None = Field(default=None, max_length=10)
    card_type: int = 0
    memo: str | None = Field(default=None, max_length=255)
    operator: str = "front_desk"


class BreakfastUseIn(BaseModel):
    """核销早餐券（幂等：已核销再核返回 409）。"""

    ticket_no: str = Field(min_length=1, max_length=32)
    business_date: str = Field(min_length=1, max_length=10)
    operator: str = "front_desk"


class BreakfastTicketOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: str
    hotel_id: int
    ticket_no: str
    booking_id: int | None = None
    room_no: str | None = None
    card_type: int = 0
    ticket_type: int = 0
    ticket_type_name: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    used_business_date: str | None = None
    is_used: bool = False
    is_valid: bool = True
    shift_id: int | None = None
    operator: str = "front_desk"
    memo: str | None = None
    created_at: datetime | None = None


class CouponTemplateIn(BaseModel):
    """券模板（规则）。"""

    hotel_id: int | None = None
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    ticket_type: str = Field(default="VOUCHER", max_length=8)
    discount_type: str = Field(default="AMOUNT", max_length=16)
    discount_value: int = Field(default=0, ge=0)
    valid_from: str = Field(min_length=1, max_length=10)
    valid_to: str = Field(min_length=1, max_length=10)
    total_quantity: int = Field(default=0, ge=0)
    operator: str = "front_desk"


class CouponTemplateOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: str
    hotel_id: int | None = None
    code: str
    name: str
    ticket_type: str = "VOUCHER"
    discount_type: str = "AMOUNT"
    discount_value: int = 0
    valid_from: str
    valid_to: str
    total_quantity: int = 0
    issued_quantity: int = 0
    is_valid: bool = True
    operator: str = "front_desk"
    created_at: datetime | None = None


class CouponIn(BaseModel):
    """发券（可指定模板批量，或散券直接给规则）。"""

    hotel_id: int | None = None
    template_id: int | None = None
    count: int = Field(default=1, ge=1, le=1000)
    ticket_type: str | None = Field(default=None, max_length=8)
    discount_type: str | None = Field(default=None, max_length=16)
    discount_value: int | None = Field(default=None, ge=0)
    valid_from: str | None = Field(default=None, max_length=10)
    valid_to: str | None = Field(default=None, max_length=10)
    is_cover_other_discount: bool = False
    is_transfer_to_account: bool = False
    operator: str = "front_desk"


class CouponUseIn(BaseModel):
    """核销券。"""

    coupon_no: str = Field(min_length=1, max_length=32)
    booking_id: int | None = None
    bill_id: int | None = None
    operator: str = "front_desk"


class CouponOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: str
    hotel_id: int
    template_id: int | None = None
    coupon_no: str
    ticket_type: str = "VOUCHER"
    discount_type: str = "AMOUNT"
    discount_value: int = 0
    valid_from: str
    valid_to: str
    status: str = "ISSUED"
    booking_id: int | None = None
    bill_id: int | None = None
    used_at: str | None = None
    is_cover_other_discount: bool = False
    is_transfer_to_account: bool = False
    operator: str = "front_desk"
    created_at: datetime | None = None
