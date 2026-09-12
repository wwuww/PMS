"""API 路由：租户开通 / 房型 / 房间 / 房态流转 / RateCode（BLK-01 + M1-1）。"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Security, status
from fastapi.responses import Response, StreamingResponse
from fastapi.security import SecurityScopes
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from app.core.config import get_settings
from app.models.rbac import LoginSession, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


async def _lookup_tenant(tenant_id: str, session: AsyncSession) -> Tenant | None:
    """按租户引用解析：优先按整型 id，否则按 code（兼容雪花 ID 串与字母 code）。"""
    try:
        tid = int(tenant_id)
    except (ValueError, TypeError):
        tid = None
    if tid is not None:
        t = await session.get(Tenant, tid)
        if t:
            return t
    result = await session.execute(select(Tenant).where(Tenant.code == tenant_id))
    return result.scalar_one_or_none()

from app.api.schemas import (
    # M37-④ 早餐券 + 优惠券 + 房间属性 + 黑名单
    RoomAttributeIn,
    RoomAttributeOut,
    BlackGuestIn,
    BlackGuestOut,
    BlacklistHit,
    BreakfastIssueIn,
    BreakfastUseIn,
    BreakfastTicketOut,
    CouponTemplateIn,
    CouponTemplateOut,
    CouponIn,
    CouponUseIn,
    CouponOut,
    AdjustmentIn,
    ArAccountCreate,
    ArAccountOut,
    ArChargeIn,
    ArRepaymentIn,
    AdjustmentOut,
    AlertNotificationOut,
    AnalyticsChannelOut,
    OpenApiAppCreate,
    OpenApiAppOut,
    OpenApiKeyOut,
    OpenApiKeyWithSecret,
    OpenApiVerifyKeyIn,
    OpenApiWebhookIn,
    OpenApiWebhookOut,
    OpenApiWebhookTestOut,
    PriceRecommendationOut,
    PriceRecommendIn,
    PriceRecommendOut,
    YieldApplyIn,
    YieldApplyOut,
    PricingRuleIn,
    PricingRuleOut,
    MenuItemIn,
    MenuItemOut,
    MenuItemPatch,
    DiningTableIn,
    DiningTableOut,
    PosOrderOpenIn,
    PosOrderItemIn,
    PosOrderItemOut,
    PosOrderOut,
    PosSettleRoomIn,
    PosSettleCashIn,
    FnbReportOut,
    KitchenTicketOut,
    FnbSoldOutIn,
    FnbVoidIn,
    FnbDiscountIn,
    AnalyticsDashboardOut,
    AnalyticsExportQuery,
    AnalyticsPaymentOut,
    AnalyticsRankingOut,
    AnalyticsRoomTypeOut,
    ApprovalDecideIn,
    ApprovalSubmitIn,
    ApprovalTicketOut,
    AuditLogOut,
    AutoRunIn,
    AutoRunOut,
    AvailabilityOut,
    BillOpenIn,
    BillOut,
    BookingActionIn,
    BookingLinkIn,
    BookingSettleToMasterIn,
    BookingUnlinkIn,
    BookingNoShowIn,
    BookingChangeRoomIn,
    BookingCreate,
    BookingExtendIn,
    BookingExtrasIn,
    BookingOut,
    InvoiceIn,
    InvoiceOut,
    InvoiceVoidIn,
    RoomChangeOut,
    StayExtensionOut,
    ReceptionCheckInIn,
    ReceptionContext,
    ReceptionAdvanceIn,
    GroupAllocationIn,
    GroupAllocationOut,
    GroupBlockAssignIn,
    GroupBlockCreate,
    GroupBlockOut,
    BusinessDayOut,
    ChatCloseIn,
    ChatHandoffIn,
    ChatMessageIn,
    ChatMessageOut,
    ChatReplyOut,
    ChatSessionCreate,
    ChatSessionOut,
    ChargeIn,
    ChannelPushIn,
    ChannelResultOut,
    CommissionReconciliationOut,
    CommissionRuleIn,
    CommissionRuleOut,
    DailyReportOut,
    DashboardOut,
    NightAuditBoardOut,
    GroupPricePolicyIn,
    GroupPricePolicyOut,
    HqDashboardOut,
    SettlementOut,
    HotelCreate,
    HotelOut,
    HotelUpdate,
    HousekeepingAssignIn,
    ComplaintCreate,
    ComplaintOut,
    ComplaintTransitionIn,
    OtaConfigIn,
    OtaConfigOut,
    OtaOrderInjectIn,
    OtaOrderInjectOut,
    ChannelRoomMappingIn,
    ChannelRoomMappingOut,
    ChannelRatePlanIn,
    ChannelRatePlanOut,
    ChannelPushLogOut,
    PointsPayIn,
    PointsPayOut,
    RoomLookupOut,
    HkInspectIn,
    SnapshotGenerateIn,
    SnapshotOut,
    GroupAllocationSettleIn,
    GroupSettlementOut,
    RoomDndIn,
    HousekeepingBatchAssignIn,
    HousekeepingBatchDoneIn,
    HousekeepingTaskIn,
    HousekeepingTaskOut,
    LoginIn,
    DepositIn,
    DepositOut,
    DepositApplyIn,
    DepositRefundIn,
    DepositVoidIn,
    DepositReleaseIn,
    DepositCaptureIn,
    DepositTransactionOut,
    AutoReleaseIn,
    AutoReleaseOut,
    LoginOut,
    LogoutIn,
    RefreshIn,
    RefreshOut,
    MemberCreate,
    MemberOut,
    MemberRechargeIn,
    GuestCreate,
    GuestOut,
    GuestUpdate,
    MpOfferOut,
    MpOrderOut,
    MpOrderPlaceIn,
    NightAuditIn,
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdateIn,
    NotificationSubscriptionOut,
    NotificationSubscriptionBulkIn,
    PayNotifyIn,
    PayNotifyResultOut,
    PayOrderOut,
    PayReconcileIn,
    PayReconcileOut,
    PaymentIn,
    PermissionCheckIn,
    PermissionCheckOut,
    PriceCalendarCreate,
    PriceCalendarOut,
    RateCodeCreate,
    RateCodeOut,
    RoleCreate,
    RoleOut,
    RoomCreate,
    RoomOut,
    RoomTransitionIn,
    RoomTypeCreate,
    RoomTypeOut,
    ShiftCloseIn,
    ShiftOpenIn,
    ShiftOut,
    PsbTaskIn,
    PsbTaskOut,
    SearchResultItem,
    SearchResultOut,
    TenantCreate,
    TenantOut,
    TenantUpdate,
    UserCreate,
    UserOut,
    UserRoleIn,
    UserRoleOut,
    WakeUpCallIn,
    WakeUpCallOut,
)
from app.channels import get_adapter
from app.db.session import get_session
from app.domain.room_state import InvalidTransition, RoomTrigger
from app.events.base import PermissionDenied, UserLoggedIn, utc_now
from app.events.bus import event_bus
from app.models import (
    AdjustmentVoucher,
    AlertNotification,
    ApprovalTicket,
    AuditLog,
    Bill,
    Booking,
    BusinessDay,
    ChatMessage,
    ChatSession,
    Complaint,
    CommissionReconciliation,
    CommissionRule,
    DailyReport,
    GroupPricePolicy,
    Guest,
    GroupAllocation,
    GroupBlock,
    Hotel,
    HousekeepingTask,
    Invoice,
    Member,
    Notification,
    NotificationPreference,
    NotificationSubscription,
    OtaChannelConfig,
    OpenApiApp,
    ReportSnapshot,
    OpenApiKey,
    ChannelRoomMapping,
    ChannelRatePlan,
    ChannelPushLog,
    PayOrder,
    Payment,
    PosOrder,
    PosOrderItem,
    PriceCalendar,
    PsbUploadTask,
    RateCode,
    Role,
    Room,
    RoomChange,
    RoomType,
    ShiftHandover,
    StayExtension,
    Tenant,
    User,
    UserRole,
    WakeUpCall,
    WebhookDelivery,
    WebhookSubscription,
    RoomStateEvent,)
from app.services.analytics_service import AnalyticsService
from app.services.anomaly_service import AnomalyService
from app.services.approval_service import ApprovalService
from app.services.ar_service import ArService, CreditLimitExceeded
from app.services.audit_service import record as audit_record
from app.services.booking_service import BookingService
from app.services.chatbot_service import ChatbotService
from app.services.cashier_service import CashierService
from app.services.commission_service import CommissionService
from app.services.deposit_service import DepositError, DepositService
from app.services.group_service import GroupService
from app.services.invoice_service import InvoiceError, InvoiceService
from app.services.guest_service import GuestService
from app.services.housekeeping_service import HousekeepingService
from app.services.manager_service import ManagerService
from app.services.member_service import MemberService
from app.services.mp_service import MpService
from app.services.night_audit_service import NightAuditService
from app.services.night_audit_scheduler import NightAuditScheduler
from app.services.notification_service import (
    DEFAULT_SUBSCRIBERS,
    REF_LABELS,
    NotificationService,
    notification_visible_to,
)
from app.services.openapi_service import OpenApiService
from app.services.permissions import (
    AUDIT_VIEW,
    PRICE_EDIT,
    BOOKING_CANCEL,
    BILL_REFUND,
    BILL_ADJUST,
    BILL_DISCOUNT,
    NIGHT_AUDIT_RUN,
    USER_MANAGE,
    ROLE_MANAGE,
    FNB_MANAGE,
    DEPOSIT_MANAGE,
    DEPOSIT_REFUND,
    OTA_MANAGE,
    RATE_EDIT,
    INVOICE_MANAGE,
    BLACKLIST_MANAGE,
    COUPON_MANAGE,
    BREAKFAST_MANAGE,
)
from app.services.pay_service import PayService
from app.services.price_service import PriceService
from app.services.psb_service import PsbService
from app.services.rbac_service import RbacService
from app.services.reception_service import ReceptionService
from app.domain.reception_flow import InvalidReceptionTransition
from app.services.group_block_service import GroupBlockService
from app.services.yield_service import YieldService
from app.services.fnb_service import PosService
from app.services.room_service import RoomService
from app.services.shift_service import ShiftService
from app.services.wakeup_service import WakeUpCallService
from app.services.audit_service import record as audit_service_record
from app.services.audit_service import record as audit_service_record
from app.services.complaint_service import ComplaintService
from app.services.fnb_service import PosService
from app.api.dependencies import MAX_LIST_ROWS, Paged
from app.services.ota_service import OtaError, OtaService, SIGN_HEADER
from app.services.ota_mapping_service import OtaMappingError, OtaMappingService
from app.services.ota_rate_plan_service import OtaRatePlanError, OtaRatePlanService
from app.infra.cache import get_cache

router = APIRouter()


# ---------- 路由级强制会话鉴权（M8-3 落地） ----------


async def resolve_tenant_id(path: str, session: AsyncSession) -> str | None:
    """从请求路径解析租户编码（会话以租户编码为键）。支持三种形态：

    - ``/api/v1/tenants/{code}/...`` —— 主形态，直接取编码；
    - ``/api/v1/tenants/{id}/...`` —— 少数路由（建门店/建房型）用整型租户 id，
      需回查 ``Tenant.code``（Sprint 14 修复：此前这类端点带有效 token 也 401）；
    - ``/api/v1/hotels/{hotel_id}/...`` —— 门店形态（如批量建档房间），
      按门店反查所属租户（Sprint 14 修复：此前恒 401）。
    """
    parts = [p for p in path.split("/") if p]
    raw = parts[3] if len(parts) >= 4 and parts[2] == "tenants" else None
    if not raw and len(parts) >= 4 and parts[2] == "hotels":
        if parts[3].isdigit():
            hotel = await session.get(Hotel, int(parts[3]))
            raw = hotel.tenant_id if hotel is not None else None
        else:
            raw = None
    if not raw:
        return None
    if raw.isdigit():  # 整型租户 id → 回查编码
        tenant = await session.get(Tenant, int(raw))
        return tenant.code if tenant is not None else None
    return raw


async def require_auth(
    request: Request,
    authorization: str = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> LoginSession | None:
    """全部业务路由的强制会话鉴权依赖。

    通过 ``app.include_router(api_router, prefix=..., dependencies=[Depends(require_auth)])``
    挂载到除公开端点外的所有路由。公开白名单（无需会话）：
      - ``POST /tenants`` 租户开通
      - ``GET  /tenants`` 租户目录（登录页租户切换器，未登录可用）
      - ``POST /tenants/{code}/auth/login|logout|check`` 登录/登出/鉴权校验
      - ``/tenants/{code}/openapi/...`` 开放平台（采用 API-Key 独立鉴权）
    其余端点必须携带 ``Authorization: Bearer <token>`` 且会话有效，否则返回 401。
    """
    path = request.url.path
    prefix = get_settings().api_v1_prefix

    # 1) 公开端点白名单
    if any(
        path.endswith(ep)
        for ep in ("/auth/login", "/auth/logout", "/auth/check", "/auth/refresh")
    ):
        return None
    if path.rstrip("/") == f"{prefix}/tenants":
        return None
    if "/openapi/" in path:
        return None
    if "/ota/" in path and "/webhook/" in path:
        return None  # M29：OTA webhook 走 HMAC 签名校验，不走会话鉴权

    # 2) 校验 Bearer token 是否提供
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供有效的登录凭证（缺少 Bearer token）",
        )

    # 3) 提取租户编码（支持租户编码 / 整型租户 id / 门店 id 三种路径形态）
    tenant_id = await resolve_tenant_id(path, session)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法从请求路径识别租户",
        )

    token = authorization.split(" ", 1)[1].strip()
    sess = await RbacService(session).get_session(tenant_id, token)
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录会话无效或已过期，请重新登录",
        )
    return sess


# ---------- 路由级 RBAC 授权（M8-3 授权层） ----------

# M30：列表接口安全护栏——单次返回行数硬上限，防止全表拉取拖垮实例。
# 默认（limit=None）语义仍是「不额外限制」以兼容既有前端全量拉取，但无论如何
# 不会超过此值；需要精确分页的调用方显式传 limit/offset。
# 常量定义已迁出至 ``app.api.dependencies``（M32 抽公共依赖），routes.py 仅保留
# ``from app.api.dependencies import MAX_LIST_ROWS, Paged`` 供既有 6 个端点继续使用。


async def require_perm(
    security_scopes: SecurityScopes,
    session: AsyncSession = Depends(get_session),
    login_session: LoginSession = Depends(require_auth),
) -> User:
    """授权层：在 require_auth（认证）之后按路由声明权限点二次校验，缺权限返 403。

    用法：``dependencies=[Security(require_perm, scopes=["booking.cancel"])]``
    未声明 scopes 的路由仅要求登录态（兼容既有只读接口）。
    """
    if login_session is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该资源")
    user = await session.get(User, login_session.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    for perm in security_scopes.scopes:
        if not await RbacService(session).has_permission(user, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"权限不足：需要 {perm}")
    return user


# ---------- M18 开放 API：第三方 API-Key 鉴权 ----------
async def require_api_key(
    tenant_id: str,
    authorization: str = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> "OpenApiApp":
    """第三方只读开放接口的鉴权依赖（与登录会话鉴权相互独立）。

    ``/openapi/`` 路径已在 ``require_auth`` 白名单中放行（不要求登录会话），
    此处改为校验 ``Authorization: Bearer pms_xxx`` 的 API Key，命中应用后返回
    ``OpenApiApp``；无效/已吊销/格式错误均返回 401。所有查询以 ``app.tenant_id``
    作用域，杜绝借路径篡改越权跨租户。
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="缺少 API Key（Authorization: Bearer pms_xxx）",
        )
    raw = authorization.split(" ", 1)[1].strip()
    app = await OpenApiService(session).verify_key(tenant_id, raw)
    if app is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="API Key 无效或已吊销"
        )
    return app


# ---------- 租户（BLK-01 开通流程） ----------


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate, session: AsyncSession = Depends(get_session)
) -> Tenant:
    exists = await session.execute(select(Tenant).where(Tenant.code == body.code))
    if exists.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "租户编码已存在")
    tenant = Tenant(code=body.code, name=body.name, is_chain=body.is_chain)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    # 租户开通即播种默认三档角色（M8-1 框架先行）
    svc = RbacService(session)
    await svc.seed_default_roles(tenant.code)
    # 播种默认管理员引导账号，使强制鉴权下仍有可用登录凭据（M8-3）
    await svc.seed_default_admin(tenant.code)
    await session.commit()
    return tenant


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(session: AsyncSession = Depends(get_session)) -> list[Tenant]:
    result = await session.execute(select(Tenant))
    return list(result.scalars())


# ---------- 租户设置（M31：NoShow 扣首晚房费等租户级配置） ----------


@router.patch(
    "/tenants/{tenant_id}/settings",
    response_model=TenantOut,
    dependencies=[Security(require_perm, scopes=[NIGHT_AUDIT_RUN])],
)
async def update_tenant_settings(
    tenant_id: str,
    body: TenantUpdate,
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    """M31：更新租户级配置（仅写入显式提供的字段）。

    权限复用 ``night_audit.run`` —— 夜审相关配置（NoShow 扣首晚房费）由夜审负责人掌控，
    不另开系统管理权限。后续扩字段时直接扩 ``TenantUpdate`` 即可。
    """
    tenant = await _lookup_tenant(tenant_id, session)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "租户不存在")
    fields = body.model_dump(exclude_unset=True)
    for k, v in fields.items():
        if v is not None:
            setattr(tenant, k, v)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


# ---------- 门店 ----------


@router.post(
    "/tenants/{tenant_id}/hotels",
    response_model=HotelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_hotel(
    tenant_id: str, body: HotelCreate, session: AsyncSession = Depends(get_session)
) -> Hotel:
    tenant = await _lookup_tenant(tenant_id, session)
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "租户不存在")
    hotel = Hotel(tenant_id=tenant.code, code=body.code, name=body.name)
    session.add(hotel)
    await session.commit()
    await session.refresh(hotel)
    return hotel


@router.get("/tenants/{tenant_id}/hotels", response_model=list[HotelOut])
async def list_hotels(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[Hotel]:
    """列出某租户下的门店（前端酒店选择器）。"""
    stmt = select(Hotel).where(Hotel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return list(result.scalars())


# ---------- 门店设置（M31：NoShow 扣首晚房费等酒店级覆盖） ----------


@router.patch(
    "/tenants/{tenant_id}/hotels/{hotel_id}/settings",
    response_model=HotelOut,
    dependencies=[Security(require_perm, scopes=[NIGHT_AUDIT_RUN])],
)
async def update_hotel_settings(
    tenant_id: str,
    hotel_id: int,
    body: HotelUpdate,
    session: AsyncSession = Depends(get_session),
) -> Hotel:
    """M31：更新门店级配置（仅写入显式提供的字段）。

    支持将 ``noshow_charge_first_night`` 显式置 null（清除酒店级覆盖，回落租户默认）：
    客户端传 ``{"noshow_charge_first_night": null}`` 即落库 ``None``。
    权限复用 ``night_audit.run``。
    """
    hotel = await session.get(Hotel, hotel_id)
    if hotel is None or hotel.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "门店不存在")
    # 区分「字段未提供」与「显式置 None」：model_fields_set 含字段名即认为客户端提供了
    provided = body.model_fields_set
    for k in provided:
        setattr(hotel, k, getattr(body, k))
    session.add(hotel)
    await session.commit()
    await session.refresh(hotel)
    return hotel


# ---------- 房型 ----------


@router.post(
    "/tenants/{tenant_id}/room-types",
    response_model=RoomTypeOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_room_type(
    tenant_id: str, body: RoomTypeCreate, session: AsyncSession = Depends(get_session)
) -> RoomType:
    tenant = await _lookup_tenant(tenant_id, session)
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "租户不存在")
    room_type = RoomType(
        tenant_id=tenant.code,
        code=body.code,
        name=body.name,
        base_price=body.base_price,
        hourly_rate=body.hourly_rate,
        # 批次② 字段补全
        bed_number=body.bed_number,
        short_name=body.short_name,
        en_name=body.en_name,
        descript=body.descript,
        is_valid=body.is_valid,
    )
    session.add(room_type)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"房型代码 {body.code} 已存在"
        ) from exc
    await session.refresh(room_type)
    return room_type


@router.get("/tenants/{tenant_id}/room-types", response_model=list[RoomTypeOut])
async def list_room_types(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[RoomType]:
    """列出某租户下的房型（前端新建预订表单）。"""
    stmt = select(RoomType).where(RoomType.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return list(result.scalars())


# ---------- 房间 ----------


@router.post(
    "/hotels/{hotel_id}/rooms",
    response_model=list[RoomOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_rooms(
    hotel_id: int, body: list[RoomCreate], session: AsyncSession = Depends(get_session)
) -> list[Room]:
    hotel = await session.get(Hotel, hotel_id)
    if not hotel:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "门店不存在")
    rooms: list[Room] = []
    for item in body:
        room_type = await session.get(RoomType, item.room_type_id)
        if not room_type or room_type.tenant_id != hotel.tenant_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "房型不存在或不属于该租户")
        rooms.append(
            Room(
                tenant_id=hotel.tenant_id,
                hotel_id=hotel.id,
                room_type_id=item.room_type_id,
                room_no=item.room_no,
                floor=item.floor,
            )
        )
    session.add_all(rooms)
    await session.commit()
    from app.infra.cache import get_cache  # noqa: PLC0415

    await get_cache().invalidate_prefix(f"rooms:{hotel.tenant_id}")
    return rooms


@router.get("/tenants/{tenant_id}/rooms", response_model=list[RoomOut])
async def list_rooms(
    tenant_id: str,
    state: str | None = None,
    limit: int = Query(MAX_LIST_ROWS, le=MAX_LIST_ROWS, ge=1, description="返回行数上限"),
    offset: int = Query(0, ge=0, description="跳过的行数"),
    session: AsyncSession = Depends(get_session),
) -> list[Room] | list[dict]:
    """房态列表（Sprint 15 热点读缓存 + M30 性能护栏）。

    - 全量列表走缓存（key=rooms:{tenant_id}，TTL 30s 兜底）；
    - 房态写路径（RoomService.transition / create_rooms）显式失效；
    - state 过滤在缓存快照上执行，命中时避免全表扫描；
    - 缓存 miss 时按 ``limit`` / ``offset`` 走 DB 分页，保护后端不被百万级房态一次打满。
    """
    from app.infra.cache import get_cache  # noqa: PLC0415

    cache = get_cache()
    key = f"rooms:{tenant_id}"
    cached = await cache.get(key)
    if cached is not None:
        rows = cached
    else:
        result = await session.execute(
            select(Room)
            .where(Room.tenant_id == tenant_id)
            .order_by(Room.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rooms = list(result.scalars())
        rows = [RoomOut.model_validate(r).model_dump(mode="json") for r in rooms]
        # M32.3：锁房房间附带锁房前房态（最近一次 lock_for_arrival 事件的 from_state），
        # 前端用「原房态底色 + 小锁图标」表达锁房，不再整体变色
        locked_ids = [r["id"] for r in rows if r.get("state") == "arrival_locked"]
        if locked_ids:
            # M30 性能护栏：按锁房房间数 * 5 倍限，防止重复锁房历史无谓扫全表
            # （5× 折中：覆盖极端重复锁房场景，又不至于放飞）
            ev = await session.execute(
                select(RoomStateEvent)
                .where(
                    RoomStateEvent.room_id.in_(locked_ids),
                    RoomStateEvent.trigger == "lock_for_arrival",
                )
                .order_by(RoomStateEvent.id.desc())
                .limit(len(locked_ids) * 5)
            )
            pre_lock: dict[str, str] = {}
            for e in ev.scalars():
                pre_lock.setdefault(str(e.room_id), e.from_state)
            for r in rows:
                if r.get("state") == "arrival_locked":
                    pre = pre_lock.get(r["id"], "vacant_clean")
                    r["pre_lock_state"] = pre if pre in ("vacant_clean", "vacant_dirty") else "vacant_clean"
        await cache.set(key, rows)
    if state:
        rows = [r for r in rows if r.get("state") == state]
    return rows


@router.get("/tenants/{tenant_id}/rooms/{room_no}/state-events")
async def list_room_state_events(
    tenant_id: str,
    room_no: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """房态日志：某房间最近的状态流转流水（M32.6，房态盘菜单用）。"""
    result = await session.execute(
        select(RoomStateEvent)
        .where(RoomStateEvent.tenant_id == tenant_id, RoomStateEvent.room_no == room_no)
        .order_by(RoomStateEvent.id.desc())
        .limit(max(1, min(limit, 200)))
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "room_no": e.room_no,
            "from_state": e.from_state,
            "to_state": e.to_state,
            "trigger": e.trigger,
            "operator": e.operator,
            "occurred_at": e.occurred_at,
        }
        for e in events
    ]


@router.get("/tenants/{tenant_id}/bookings/{booking_id}/logs")
async def list_booking_logs(
    tenant_id: str,
    booking_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """登记单操作日志（M32.13）：该预订单的审计流水（创建/入住/续住/换房/随行人/退房等）。"""
    result = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.resource_type == "booking",
            AuditLog.resource_id == str(booking_id),
        )
        .order_by(AuditLog.id.desc())
        .limit(max(1, min(limit, 200)))
    )
    logs = result.scalars().all()
    return [
        {
            "id": a.id,
            "action": a.action,
            "actor": a.actor,
            "result": a.result,
            "detail": a.detail,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in logs
    ]


@router.post("/tenants/{tenant_id}/rooms/{room_no}/transition", response_model=RoomOut)
async def transition_room(
    tenant_id: str,
    room_no: str,
    body: RoomTransitionIn,
    session: AsyncSession = Depends(get_session),
) -> Room:
    service = RoomService(session)
    room = await service.get_room(tenant_id, room_no)
    if not room:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "房间不存在")
    try:
        trigger = RoomTrigger(body.trigger)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"未知触发器: {body.trigger}"
        ) from None
    try:
        return await service.transition(room, trigger, operator=body.operator)
    except InvalidTransition as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


# ---------- RateCode（FR-JG-06 五维价格码） ----------


@router.post(
    "/tenants/{tenant_id}/rate-codes",
    response_model=RateCodeOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[PRICE_EDIT])],
)
async def create_rate_code(
    tenant_id: str, body: RateCodeCreate, session: AsyncSession = Depends(get_session)
) -> RateCode:
    rate_code = RateCode(
        tenant_id=tenant_id,
        code=body.code,
        name=body.name,
        channel=body.channel,
        member_level=body.member_level,
        agreement_type=body.agreement_type,
        room_type_id=body.room_type_id,
        stay_type=body.stay_type,
        discount_pct=body.discount_pct,
        restrictions=body.restrictions,
    )
    session.add(rate_code)
    await session.commit()
    await session.refresh(rate_code)
    return rate_code


@router.get("/tenants/{tenant_id}/rate-codes", response_model=list[RateCodeOut])
async def list_rate_codes(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[RateCode]:
    result = await session.execute(
        select(RateCode).where(RateCode.tenant_id == tenant_id)
    )
    return list(result.scalars())


# ---------- 价格库存中心（FR-JG 全量） ----------


@router.post(
    "/tenants/{tenant_id}/price-calendar",
    response_model=PriceCalendarOut,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_price_calendar(
    tenant_id: str, body: PriceCalendarCreate, session: AsyncSession = Depends(get_session)
) -> PriceCalendar:
    # M17-2 集团价格策略拦截（FR-JG-05）：改价前校验总部下发的价格边界
    try:
        await GroupService(session).assert_price_allowed(
            tenant_id, body.room_type_id, body.price
        )
    except ValueError as exc:
        await GroupService(session).record_price_block(
            tenant_id, body.room_type_id, body.price, str(exc)
        )
        await session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    existing = await session.execute(
        select(PriceCalendar).where(
            PriceCalendar.tenant_id == tenant_id,
            PriceCalendar.room_type_id == body.room_type_id,
            PriceCalendar.date == body.date,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        row.price = body.price
    else:
        row = PriceCalendar(
            tenant_id=tenant_id,
            room_type_id=body.room_type_id,
            date=body.date,
            price=body.price,
        )
        session.add(row)
    await session.commit()
    await session.refresh(row)
    # M8-2 审计埋点：改价
    await audit_record(
        session,
        tenant_id,
        "price.edit",
        actor="front_desk",
        resource_type="price_calendar",
        resource_id=row.id,
        detail={"room_type_id": body.room_type_id, "date": body.date, "price": body.price},
    )
    await session.commit()
    return row


@router.get(
    "/tenants/{tenant_id}/price-calendar",
    response_model=list[PriceCalendarOut],
)
async def list_price_calendar(
    tenant_id: str,
    room_type_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    paging: tuple[int, int] = Depends(Paged),
    session: AsyncSession = Depends(get_session),
) -> list[PriceCalendar]:
    """按租户/房型/日期范围查询价格日历（日历视图数据源 + M32 性能护栏）。

    - 默认按 (room_type_id, date) 升序输出（日历视图需要稳定顺序）；
    - Paged 默认 limit=5000 兼容既有按月全量拉取；
    - 显式传 ``?limit=N&offset=M`` 走标准分页。
    """
    limit, offset = paging
    q = select(PriceCalendar).where(PriceCalendar.tenant_id == tenant_id)
    if room_type_id is not None:
        q = q.where(PriceCalendar.room_type_id == room_type_id)
    if start:
        q = q.where(PriceCalendar.date >= start)
    if end:
        q = q.where(PriceCalendar.date <= end)
    q = q.order_by(
        PriceCalendar.date.asc(), PriceCalendar.room_type_id.asc()
    ).limit(limit).offset(offset)
    rows = (await session.execute(q)).scalars().all()
    return list(rows)


@router.post(
    "/tenants/{tenant_id}/price-calendar/batch",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def batch_upsert_price_calendar(
    tenant_id: str,
    body: list[PriceCalendarCreate],
    session: AsyncSession = Depends(get_session),
) -> dict:
    """批量改价（UPSERT）。逐条校验集团价格边界，越界项计入 blocked 并跳过。"""
    updated = 0
    blocked: list[str] = []
    for item in body:
        try:
            await GroupService(session).assert_price_allowed(
                tenant_id, item.room_type_id, item.price
            )
        except ValueError as exc:
            await GroupService(session).record_price_block(
                tenant_id, item.room_type_id, item.price, str(exc)
            )
            blocked.append(f"{item.room_type_id}/{item.date}: {exc}")
            continue
        existing = await session.execute(
            select(PriceCalendar).where(
                PriceCalendar.tenant_id == tenant_id,
                PriceCalendar.room_type_id == item.room_type_id,
                PriceCalendar.date == item.date,
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.price = item.price
        else:
            row = PriceCalendar(
                tenant_id=tenant_id,
                room_type_id=item.room_type_id,
                date=item.date,
                price=item.price,
            )
            session.add(row)
        updated += 1
    await session.commit()
    return {"updated": updated, "blocked": blocked, "total": len(body)}


@router.get(
    "/tenants/{tenant_id}/room-types/{room_type_id}/availability",
    response_model=AvailabilityOut,
)
async def room_type_availability(
    tenant_id: str,
    room_type_id: int,
    date: str,
    channel: str = "direct",
    rate_code_code: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> AvailabilityOut:
    ps = PriceService(session)
    avail = await ps.availability(tenant_id, room_type_id, date)
    price = await ps.resolve(
        room_type_id, date, channel=channel, rate_code_code=rate_code_code
    )
    return AvailabilityOut(
        room_type_id=room_type_id,
        date=date,
        total=avail["total"],
        booked=avail["booked"],
        available=avail["available"],
        price=price,
    )


# ---------- 预订引擎（M2） ----------


@router.post(
    "/tenants/{tenant_id}/bookings",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking(
    tenant_id: str, body: BookingCreate, session: AsyncSession = Depends(get_session)
) -> Booking:
    svc = BookingService(session)
    try:
        booking = await svc.create(
            tenant_id=tenant_id,
            hotel_id=body.hotel_id,
            room_type_id=body.room_type_id,
            guest_name=body.guest_name,
            check_in_date=body.check_in_date,
            check_out_date=body.check_out_date,
            channel=body.channel,
            rate_code_code=body.rate_code_code,
            guest_phone=body.guest_phone,
            id_doc_no=body.id_doc_no,
            room_no=body.room_no,
            chat_session_id=body.chat_session_id,
            stay_type=body.stay_type,
            hourly_hours=body.hourly_hours,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return booking


@router.get("/tenants/{tenant_id}/bookings", response_model=list[BookingOut])
async def list_bookings(
    tenant_id: str,
    status_: str | None = None,
    guest_source_type: str | None = None,
    member_no: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[Booking]:
    """预订列表（M30 性能护栏）。

    - ``limit=None``（默认）语义为「不额外限制」，兼容既有前端全量拉取；
    - 但仍受 ``MAX_LIST_ROWS`` 硬上限保护，避免百万级预订一次打满内存；
    - 需要精确分页的调用方显式传 ``limit`` / ``offset``。
    """
    stmt = select(Booking).where(Booking.tenant_id == tenant_id)
    if status_:
        stmt = stmt.where(Booking.status == status_)
    if guest_source_type:
        stmt = stmt.where(Booking.guest_source_type == guest_source_type)
    if member_no:
        stmt = stmt.where(Booking.member_no == member_no)
    stmt = stmt.offset(max(0, offset)).limit(
        MAX_LIST_ROWS if limit is None else max(1, min(limit, MAX_LIST_ROWS))
    )
    result = await session.execute(stmt)
    return list(result.scalars())


@router.post("/tenants/{tenant_id}/bookings/link", response_model=list[BookingOut])
async def link_bookings(
    tenant_id: str,
    body: BookingLinkIn,
    session: AsyncSession = Depends(get_session),
) -> list[Booking]:
    """在住联房（M32.15）：多间在住房联为一组，主房 master_room_no；各单保留自己的来离店日期。"""
    svc = ReceptionService(session)
    try:
        out = await svc.link_rooms(tenant_id, body.room_nos, body.master_room_no)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return out


@router.post("/tenants/{tenant_id}/bookings/unlink", response_model=list[BookingOut])
async def unlink_bookings(
    tenant_id: str,
    body: BookingUnlinkIn,
    session: AsyncSession = Depends(get_session),
) -> list[Booking]:
    """取消联房（M32.15）：把房号移出联房组；主房移出时自动移交主房标记。"""
    svc = ReceptionService(session)
    try:
        out = await svc.unlink_rooms(tenant_id, body.room_nos)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return out


@router.post("/tenants/{tenant_id}/bookings/settle-to-master")
async def settle_booking_to_master(
    tenant_id: str,
    body: BookingSettleToMasterIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """联房结转（M32.16）：从房未结余额整体并入主房账单，从房余额归零后可正常退房。"""
    svc = CashierService(session)
    try:
        out = await svc.transfer_to_master(tenant_id, body.room_no, operator=body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return out


@router.post("/tenants/{tenant_id}/bookings/{booking_id}/check-in", response_model=BookingOut)
async def booking_check_in(
    tenant_id: str,
    booking_id: int,
    body: BookingActionIn,
    session: AsyncSession = Depends(get_session),
) -> Booking:
    if not body.room_no:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "入住需指定房号")
    booking = await session.get(Booking, booking_id)
    if not booking or booking.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预订不存在")
    svc = BookingService(session)
    try:
        return await svc.check_in(booking, body.room_no, operator=body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidTransition as exc:
        # 房态与订单状态不一致（如房间已被占用/非干净房）应返回 409，而非 500
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/tenants/{tenant_id}/bookings/{booking_id}/check-out", response_model=BookingOut)
async def booking_check_out(
    tenant_id: str,
    booking_id: int,
    body: BookingActionIn,
    session: AsyncSession = Depends(get_session),
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if not booking or booking.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预订不存在")
    svc = BookingService(session)
    try:
        return await svc.check_out(booking, operator=body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidTransition as exc:
        # 房间非在住态（换房腾退/手工房态流转等）：属业务冲突（409），不应暴露为 500
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/tenants/{tenant_id}/bookings/{booking_id}/extend-stay", response_model=BookingOut)
async def booking_extend_stay(
    tenant_id: str,
    booking_id: int,
    body: BookingExtendIn,
    session: AsyncSession = Depends(get_session),
) -> Booking:
    """续住（延住）：延长在住房间离店日期，按增量晚重算房费。"""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预订不存在")
    svc = BookingService(session)
    try:
        return await svc.extend_stay(booking, body.new_check_out_date, operator=body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/tenants/{tenant_id}/bookings/{booking_id}/change-room", response_model=BookingOut)
async def booking_change_room(
    tenant_id: str,
    booking_id: int,
    body: BookingChangeRoomIn,
    session: AsyncSession = Depends(get_session),
) -> Booking:
    """换房：在住房客换至同房型空净房，原房转空脏待清扫。"""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预订不存在")
    svc = BookingService(session)
    try:
        return await svc.change_room(
            booking, body.new_room_no, operator=body.operator, reason=body.reason
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/bookings/{booking_id}/extras",
    response_model=BookingOut,
)
async def booking_update_extras(
    tenant_id: str,
    booking_id: int,
    body: BookingExtrasIn,
    session: AsyncSession = Depends(get_session),
) -> Booking:
    """在住附加服务：加床数 / 同住人（绿云前台操作台-附加服务）。"""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预订不存在")
    svc = BookingService(session)
    try:
        return await svc.update_stay_extras(
            booking,
            extra_bed_count=body.extra_bed_count,
            companion_names=body.companion_names,
            operator=body.operator,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/reception/check-in",
    response_model=BookingOut,
)
async def reception_check_in(
    tenant_id: str,
    body: ReceptionCheckInIn,
    session: AsyncSession = Depends(get_session),
) -> Booking:
    """统一接待办理（绿云前台-散客/预订双模式入住）。

    预订模式（``booking_id``）→ 确认预订 +（可选）证件登记 + 入住；
    散客模式（无 ``booking_id``）→ 建档（关联会员）+ 建预订（锁房）+ 入住。
    hotel_id 取自预订（预订模式）或房间（散客模式），调用方无需显式传。
    """
    tenant = await session.execute(select(Tenant).where(Tenant.code == tenant_id))
    tenant = tenant.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "租户不存在")

    if body.booking_id is not None:
        booking = await session.get(Booking, body.booking_id)
        if booking is None or booking.tenant_id != tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "预订不存在")
        hotel_id = booking.hotel_id
    else:
        # 散客模式：从指定房号反查归属门店
        room = await session.execute(
            select(Room).where(Room.tenant_id == tenant_id, Room.room_no == body.room_no)
        )
        room = room.scalar_one_or_none()
        if room is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "房间不存在")
        hotel_id = room.hotel_id

    svc = ReceptionService(session)
    try:
        booking = await svc.unified_check_in(
            tenant_id,
            hotel_id,
            body.operator,
            booking_id=body.booking_id,
            room_no=body.room_no,
            room_type_id=body.room_type_id,
            guest_name=body.guest_name,
            guest_phone=body.guest_phone,
            id_type=body.id_type,
            id_no=body.id_no,
            check_in_date=body.check_in_date,
            check_out_date=body.check_out_date,
            stay_type=body.stay_type,
            hourly_hours=body.hourly_hours,
            gender=body.gender,
            birthday=body.birthday,
            email=body.email,
            address=body.address,
            nationality=body.nationality,
            ethnicity=body.ethnicity,
            note=body.note,
            guest_source_type=body.guest_source_type,
            member_no=body.member_no,
            is_vip=body.is_vip,
            is_secret=body.is_secret,
            is_quick_depart=body.is_quick_depart,
            is_print_real_price=body.is_print_real_price,
            is_add_point=body.is_add_point,
            is_guarantee=body.is_guarantee,
            guarantee_hold_until=body.guarantee_hold_until,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return booking


@router.get(
    "/tenants/{tenant_id}/reception/context",
    response_model=ReceptionContext,
)
async def reception_context(
    tenant_id: str,
    guest_phone: str | None = None,
    booking_id: int | None = None,
    room_no: str | None = None,
    hotel_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """统一接待办理流 · 单客上下文只读聚合（M1，R1）。

    定位优先级：booking_id → room_no（在住预订）→ guest_phone（最新预订）。
    返回结构即 ``ReceptionContext``：客档/会员/预订/房态/账单/审计 + 办理流状态机位置。
    """
    return await ReceptionService(session).get_context(
        tenant_id,
        guest_phone=guest_phone,
        booking_id=booking_id,
        room_no=room_no,
        hotel_id=hotel_id,
    )


@router.post(
    "/tenants/{tenant_id}/reception/advance",
    response_model=ReceptionContext,
)
async def reception_advance(
    tenant_id: str,
    body: ReceptionAdvanceIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """统一接待办理流 · 状态机驱动（M1，R2）。

    半自动单步推进（PRD Q2）：每步预填、「继续」确认、可回溯。动作：
    register（建档）/ check_in（排房+入住）/ open_folio（确认在开账单）/ check_out（退房）。
    非法流转或参数缺失 → 409。
    """
    svc = ReceptionService(session)
    try:
        result = await svc.advance(
            tenant_id,
            body.action,
            guest_phone=body.guest_phone,
            booking_id=body.booking_id,
            room_no=body.room_no,
            hotel_id=body.hotel_id,
            guest_name=body.guest_name,
            room_type_id=body.room_type_id,
            id_type=body.id_type,
            id_no=body.id_no,
            check_in_date=body.check_in_date,
            check_out_date=body.check_out_date,
            operator=body.operator,
        )
    except InvalidReceptionTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    # 提交本请求内编排产生的全部写操作（建档/办会员/开账/退房等）。
    # get_session 退出仅关闭会话、不自动提交，故须显式提交；check_in 路径
    # 因复用 BookingService.check_in 内部已提交，此处统一补提交保持行为一致。
    await session.commit()
    return result


# ---------- 团队 / 会议排房（M15，FR-GROUP） ----------


async def _group_block_out(session: AsyncSession, block: GroupBlock) -> GroupBlockOut:
    svc = GroupBlockService(session)
    allocs = await svc.list_allocations(block.id)
    return GroupBlockOut.model_validate(
        {
            **block.__dict__,
            "allocations": [GroupAllocationOut.model_validate(a) for a in allocs],
        }
    )


@router.post(
    "/tenants/{tenant_id}/group-blocks",
    response_model=GroupBlockOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_group_block(
    tenant_id: str, body: GroupBlockCreate, session: AsyncSession = Depends(get_session)
) -> GroupBlock:
    tenant = await session.execute(select(Tenant).where(Tenant.code == tenant_id))
    if tenant.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "租户不存在")
    svc = GroupBlockService(session)
    try:
        block = await svc.create_block(
            tenant_id, body.hotel_id, body.name, body.arrival_date, body.departure_date, notes=body.notes
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(block)
    return await _group_block_out(session, block)


@router.get("/tenants/{tenant_id}/group-blocks", response_model=list[GroupBlockOut])
async def list_group_blocks(
    tenant_id: str,
    hotel_id: int | None = None,
    paging: tuple[int, int] = Depends(Paged),
    session: AsyncSession = Depends(get_session),
) -> list[GroupBlock]:
    """团队排房列表（M32 性能护栏：Paged limit/offset 透传 GroupBlockService.list_blocks）。"""
    limit, offset = paging
    svc = GroupBlockService(session)
    blocks = await svc.list_blocks(tenant_id, hotel_id=hotel_id, limit=limit, offset=offset)
    return [await _group_block_out(session, b) for b in blocks]


@router.get("/tenants/{tenant_id}/group-blocks/{block_id}", response_model=GroupBlockOut)
async def get_group_block(
    tenant_id: str, block_id: int, session: AsyncSession = Depends(get_session)
) -> GroupBlockOut:
    svc = GroupBlockService(session)
    block = await svc.get_block(tenant_id, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队排房不存在")
    return await _group_block_out(session, block)


@router.post("/tenants/{tenant_id}/group-blocks/{block_id}/assign", response_model=GroupBlockOut)
async def assign_group_block_rooms(
    tenant_id: str,
    block_id: int,
    body: GroupBlockAssignIn,
    session: AsyncSession = Depends(get_session),
) -> GroupBlockOut:
    svc = GroupBlockService(session)
    block = await svc.get_block(tenant_id, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队排房不存在")
    try:
        await svc.assign_rooms(block, [a.model_dump() for a in body.allocations])
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(block)
    return await _group_block_out(session, block)


@router.post("/tenants/{tenant_id}/group-blocks/{block_id}/check-in", response_model=GroupBlockOut)
async def check_in_group_block(
    tenant_id: str,
    block_id: int,
    operator: str = "front_desk",
    session: AsyncSession = Depends(get_session),
) -> GroupBlockOut:
    svc = GroupBlockService(session)
    block = await svc.get_block(tenant_id, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队排房不存在")
    try:
        await svc.check_in_block(block, operator=operator)
    except (ValueError, InvalidTransition) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(block)
    return await _group_block_out(session, block)


@router.post("/tenants/{tenant_id}/group-blocks/{block_id}/close", response_model=GroupBlockOut)
async def close_group_block(
    tenant_id: str, block_id: int, session: AsyncSession = Depends(get_session)
) -> GroupBlockOut:
    """关闭团队排房（入住完毕或取消）。关闭后不可再排房 / 入住。"""
    svc = GroupBlockService(session)
    block = await svc.get_block(tenant_id, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队排房不存在")
    block = await svc.close_block(block)
    await session.commit()
    await session.refresh(block)
    return await _group_block_out(session, block)


@router.post("/tenants/{tenant_id}/bookings/{booking_id}/cancel", response_model=BookingOut, dependencies=[Security(require_perm, scopes=[BOOKING_CANCEL])])
async def booking_cancel(
    tenant_id: str,
    booking_id: int,
    body: BookingActionIn,
    session: AsyncSession = Depends(get_session),
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if not booking or booking.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预订不存在")
    svc = BookingService(session)
    try:
        result = await svc.cancel(booking, operator=body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    # M8-2 审计埋点：取消单
    await audit_record(
        session,
        tenant_id,
        "booking.cancel",
        actor=body.operator,
        resource_type="booking",
        resource_id=booking.id,
        hotel_id=booking.hotel_id,
        detail={"guest_name": booking.guest_name, "check_in_date": booking.check_in_date},
    )
    await session.commit()
    return result


@router.post("/tenants/{tenant_id}/bookings/{booking_id}/noshow", response_model=BookingOut, dependencies=[Security(require_perm, scopes=[BOOKING_CANCEL])])
async def booking_mark_noshow(
    tenant_id: str,
    booking_id: int,
    body: BookingNoShowIn,
    session: AsyncSession = Depends(get_session),
) -> Booking:
    """前台手动标记 NoShow（M23 验收清单#3）：仅 CREATED 可标记，留存原因并释放锁房。"""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预订不存在")
    svc = BookingService(session)
    try:
        result = await svc.mark_noshow(booking, reason=body.reason, operator=body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await audit_record(
        session,
        tenant_id,
        "booking.noshow",
        actor=body.operator,
        resource_type="booking",
        resource_id=booking.id,
        hotel_id=booking.hotel_id,
        detail={
            "guest_name": booking.guest_name,
            "check_in_date": booking.check_in_date,
            "reason": result.noshow_reason,
        },
    )
    await session.commit()
    return result


# ---------- 渠道直连（M6-1 骨架） ----------


@router.post(
    "/tenants/{tenant_id}/channels/{channel}/availability-push",
    response_model=ChannelResultOut,
)
async def channel_availability_push(
    tenant_id: str,
    channel: str,
    body: ChannelPushIn,
    session: AsyncSession = Depends(get_session),
) -> ChannelResultOut:
    ps = PriceService(session)
    avail = await ps.availability(tenant_id, body.room_type_id, body.date)
    adapter = get_adapter(channel, tenant_id)
    result = await adapter.push_availability(body.room_type_id, body.date, avail["available"])
    return ChannelResultOut(
        channel=result.channel,
        integrated=result.integrated,
        message=result.message,
        payload=result.payload,
    )


# ---------- 会员 CRM（M13） ----------


@router.post(
    "/tenants/{tenant_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_member(
    tenant_id: str, body: MemberCreate, session: AsyncSession = Depends(get_session)
) -> Member:
    tenant = await session.execute(select(Tenant).where(Tenant.code == tenant_id))
    tenant = tenant.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "租户不存在")
    svc = MemberService(session)
    member = await svc.register(
        tenant_id, body.hotel_id, body.name, body.phone,
        member_no=body.member_no,
        card_type=body.card_type,
        join_date=body.join_date,
    )
    await session.commit()
    await session.refresh(member)
    return member


@router.get("/tenants/{tenant_id}/members/{phone}", response_model=MemberOut)
async def get_member(
    tenant_id: str, phone: str, session: AsyncSession = Depends(get_session)
) -> Member:
    svc = MemberService(session)
    member = await svc.get_by_phone(tenant_id, phone)
    if not member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会员不存在")
    return member


@router.post("/tenants/{tenant_id}/members/{phone}/recharge", response_model=MemberOut)
async def recharge_member(
    tenant_id: str, phone: str, body: MemberRechargeIn, session: AsyncSession = Depends(get_session)
) -> Member:
    svc = MemberService(session)
    member = await svc.get_by_phone(tenant_id, phone)
    if not member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会员不存在")
    try:
        member = await svc.recharge(member, body.amount, operator=body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(member)
    return member


# ---------- 宾客档案 / 客史（M14，FR-GUEST） ----------


async def _enrich_guests_with_member(
    session: AsyncSession, guests: list[Guest]
) -> list[GuestOut]:
    """客档联动会员：批量回填关联会员的等级/积分/储值（只读，避免 N+1）。"""
    ids = [g.member_id for g in guests if g.member_id]
    member_map: dict[int, Member] = {}
    if ids:
        rows = await session.execute(select(Member).where(Member.id.in_(ids)))
        for m in rows.scalars():
            member_map[m.id] = m
    out: list[GuestOut] = []
    for g in guests:
        o = GuestOut.model_validate(g)
        m = member_map.get(g.member_id) if g.member_id else None  # type: ignore[arg-type]
        if m is not None:
            o.member_level = m.level
            o.member_points = m.points
            o.member_stored_value = m.stored_value
        out.append(o)
    return out


@router.post(
    "/tenants/{tenant_id}/guests",
    response_model=GuestOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_guest(
    tenant_id: str, body: GuestCreate, session: AsyncSession = Depends(get_session)
) -> Guest:
    tenant = await session.execute(select(Tenant).where(Tenant.code == tenant_id))
    tenant = tenant.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "租户不存在")
    svc = GuestService(session)
    guest = await svc.create(
        tenant_id,
        body.hotel_id,
        body.name,
        body.phone,
        id_type=body.id_type,
        id_no=body.id_no,
        vip_level=body.vip_level,
        gender=body.gender,
        email=body.email,
        address=body.address,
        tags=body.tags,
        notes=body.notes,
        member_id=body.member_id,
    )
    await session.commit()
    await session.refresh(guest)
    # 建档后立即回填关联会员的等级/积分/储值（客档联动会员）
    enriched = await _enrich_guests_with_member(session, [guest])
    return enriched[0]


@router.get("/tenants/{tenant_id}/guests/search", response_model=list[GuestOut])
async def search_guests(
    tenant_id: str,
    phone: str | None = None,
    name: str | None = None,
    id_no: str | None = None,
    booking_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[Guest]:
    """多维度快速检索（M23 清单#4）：姓名 / 手机号 / 证件号 / 订单号。"""
    if not (phone or name or id_no or booking_id is not None):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "至少提供 phone / name / id_no / booking_id 之一"
        )
    svc = GuestService(session)
    guests = await svc.search(
        tenant_id, phone=phone, name=name, id_no=id_no, booking_id=booking_id
    )
    return await _enrich_guests_with_member(session, guests)


@router.get("/tenants/{tenant_id}/guests/{guest_id}", response_model=GuestOut)
async def get_guest(
    tenant_id: str, guest_id: int, session: AsyncSession = Depends(get_session)
) -> GuestOut:
    svc = GuestService(session)
    guest = await svc.get(tenant_id, guest_id)
    if not guest:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "宾客档案不存在")
    enriched = await _enrich_guests_with_member(session, [guest])
    return enriched[0]


@router.get("/tenants/{tenant_id}/guests", response_model=list[GuestOut])
async def list_guests(
    tenant_id: str,
    hotel_id: int | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[Guest]:
    svc = GuestService(session)
    guests = await svc.list(
        tenant_id,
        hotel_id=hotel_id,
        keyword=keyword,
        limit=max(1, min(limit, 200)),
        offset=max(0, offset),
    )
    return await _enrich_guests_with_member(session, guests)


@router.patch("/tenants/{tenant_id}/guests/{guest_id}", response_model=GuestOut)
async def update_guest(
    tenant_id: str,
    guest_id: int,
    body: GuestUpdate,
    session: AsyncSession = Depends(get_session),
) -> Guest:
    svc = GuestService(session)
    guest = await svc.get(tenant_id, guest_id)
    if not guest:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "宾客档案不存在")
    changed = body.model_dump(exclude_unset=True)
    guest = await svc.update(guest, **changed)
    # 编辑时若手机号变更，重新尝试关联会员
    if "phone" in changed:
        await svc._link_member_by_phone(guest, guest.phone)  # type: ignore[attr-defined]
    await session.commit()
    await session.refresh(guest)
    enriched = await _enrich_guests_with_member(session, [guest])
    return enriched[0]


# ---------- 前台收银（M3） ----------


@router.post("/tenants/{tenant_id}/bills", response_model=BillOut, status_code=status.HTTP_201_CREATED)
async def open_bill(
    tenant_id: str, body: BillOpenIn, session: AsyncSession = Depends(get_session)
) -> Bill:
    svc = CashierService(session)
    bill = await svc.open_bill(
        tenant_id, body.hotel_id, body.guest_name, body.room_no, body.booking_id, body.source
    )
    await session.commit()
    await session.refresh(bill)
    return await _bill_with_items(bill, session)


@router.get("/tenants/{tenant_id}/bills", response_model=list[BillOut])
async def list_bills(
    tenant_id: str,
    source: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[Bill]:
    """账单列表（可按来源过滤：BOOKING 预订账 / WALK_IN 街客账）。

    M30 性能护栏：``limit=None`` 兼容既有全量语义，但受 ``MAX_LIST_ROWS`` 硬上限保护。
    """
    stmt = select(Bill).where(Bill.tenant_id == tenant_id)
    if source:
        stmt = stmt.where(Bill.source == source)
    stmt = stmt.offset(max(0, offset)).limit(
        MAX_LIST_ROWS if limit is None else max(1, min(limit, MAX_LIST_ROWS))
    )
    result = await session.execute(stmt)
    return list(result.scalars())


@router.post("/tenants/{tenant_id}/bills/{bill_id}/charges", response_model=BillOut)
async def add_charge(
    tenant_id: str,
    bill_id: int,
    body: ChargeIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm),
) -> Bill:
    bill = await _get_bill(tenant_id, bill_id, session)
    # M8-3 授权层：折扣操作需 billing.discount 权限（普通加账不受限），加账前拦截
    if body.charge_type == "DISCOUNT" and not await RbacService(session).has_permission(
        user, BILL_DISCOUNT
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足：需要 billing.discount")
    svc = CashierService(session)
    try:
        await svc.add_charge(bill, body.charge_type, body.amount, body.description, body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    # M8-2 审计埋点：折扣（charge_type=DISCOUNT）
    if body.charge_type == "DISCOUNT":
        await audit_record(
            session,
            tenant_id,
            "billing.discount",
            actor="front_desk",
            resource_type="bill",
            resource_id=bill.id,
            hotel_id=bill.hotel_id,
            detail={"amount": body.amount, "description": body.description},
        )
        await session.commit()
    await session.refresh(bill)
    return await _bill_with_items(bill, session)


@router.post("/tenants/{tenant_id}/bills/{bill_id}/payments", response_model=BillOut)
async def take_payment(
    tenant_id: str, bill_id: int, body: PaymentIn, session: AsyncSession = Depends(get_session)
) -> Bill:
    bill = await _get_bill(tenant_id, bill_id, session)
    svc = CashierService(session)
    await svc.take_payment(
        bill,
        body.method,
        body.amount,
        operator=body.operator,
        ref_no=body.ref_no,
        is_deposit=body.is_deposit,
    )
    await session.commit()
    await session.refresh(bill)
    return await _bill_with_items(bill, session)


@router.post("/tenants/{tenant_id}/bills/{bill_id}/settle", response_model=BillOut)
async def settle_bill(
    tenant_id: str, bill_id: int, session: AsyncSession = Depends(get_session)
) -> Bill:
    bill = await _get_bill(tenant_id, bill_id, session)
    svc = CashierService(session)
    try:
        settled = await svc.settle(bill)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except DepositError as exc:
        raise _to_deposit_http_error(exc) from exc
    await session.refresh(settled)
    return await _bill_with_items(settled, session)


@router.post("/tenants/{tenant_id}/bills/{bill_id}/refund", response_model=BillOut, dependencies=[Security(require_perm, scopes=[BILL_REFUND])])
async def refund_bill(
    tenant_id: str,
    bill_id: int,
    body: PaymentIn,
    session: AsyncSession = Depends(get_session),
) -> Bill:
    bill = await _get_bill(tenant_id, bill_id, session)
    svc = CashierService(session)
    await svc.refund(bill, body.amount, method=body.method)
    await session.commit()
    await session.refresh(bill)
    return await _bill_with_items(bill, session)


@router.get("/tenants/{tenant_id}/bills/{bill_id}", response_model=BillOut)
async def get_bill(
    tenant_id: str, bill_id: int, session: AsyncSession = Depends(get_session)
) -> Bill:
    bill = await _get_bill(tenant_id, bill_id, session)
    return await _bill_with_items(bill, session)


# ---------- M24 协议单位挂账 / 月结（AR，验收 #10） ----------


@router.get("/tenants/{tenant_id}/ar-accounts", response_model=list[ArAccountOut])
async def list_ar_accounts(
    tenant_id: str,
    hotel_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ArAccount]:
    return await ArService(session).list_accounts(tenant_id, hotel_id)


@router.post(
    "/tenants/{tenant_id}/ar-accounts",
    response_model=ArAccountOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_ar_account(
    tenant_id: str, body: ArAccountCreate, session: AsyncSession = Depends(get_session)
) -> ArAccount:
    try:
        acct = await ArService(session).create_account(
            tenant_id,
            body.hotel_id,
            body.name,
            contact=body.contact,
            contact_phone=body.contact_phone,
            credit_limit_cents=body.credit_limit_cents,
            note=body.note,
            operator=body.operator,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return acct


@router.get(
    "/tenants/{tenant_id}/ar-accounts/{account_id}/bills",
    response_model=list[BillOut],
)
async def list_ar_bills(
    tenant_id: str, account_id: int, session: AsyncSession = Depends(get_session)
) -> list[Bill]:
    try:
        bills = await ArService(session).list_bills(tenant_id, account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [await _bill_with_items(b, session) for b in bills]


@router.post(
    "/tenants/{tenant_id}/ar-accounts/{account_id}/charge",
    response_model=BillOut,
)
async def charge_bill_to_ar_account(
    tenant_id: str,
    account_id: int,
    body: ArChargeIn,
    session: AsyncSession = Depends(get_session),
) -> Bill:
    bill = await _get_bill(tenant_id, body.bill_id, session)
    svc = ArService(session)
    try:
        bill = await svc.settle_to_account(tenant_id, account_id, bill, body.operator)
    except CreditLimitExceeded as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return await _bill_with_items(bill, session)


@router.post(
    "/tenants/{tenant_id}/ar-accounts/{account_id}/repayments",
    response_model=ArAccountOut,
)
async def repay_ar_account(
    tenant_id: str,
    account_id: int,
    body: ArRepaymentIn,
    session: AsyncSession = Depends(get_session),
) -> ArAccount:
    svc = ArService(session)
    try:
        acct, _ = await svc.repay(
            tenant_id,
            account_id,
            body.amount,
            method=body.method,
            operator=body.operator,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return acct


# ---------- M24 智能排房推荐（验收 #5） ----------


@router.get("/tenants/{tenant_id}/rooms/recommend")
async def recommend_rooms(
    tenant_id: str,
    hotel_id: int,
    room_type_id: int | None = None,
    guest_phone: str | None = None,
    id_doc_no: str | None = None,
    limit: int = 5,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await RoomService(session).recommend_rooms(
        tenant_id,
        hotel_id,
        room_type_id=room_type_id,
        guest_phone=guest_phone,
        id_doc_no=id_doc_no,
        limit=limit,
    )


# ---------- 夜审（M4） ----------


@router.post(
    "/tenants/{tenant_id}/night-audit",
    response_model=DailyReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def run_night_audit(
    tenant_id: str, body: NightAuditIn, session: AsyncSession = Depends(get_session)
) -> DailyReport:
    svc = NightAuditService(session)
    try:
        return await svc.run_night_audit(tenant_id, body.hotel_id, body.business_date, body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/tenants/{tenant_id}/business-days", response_model=list[BusinessDayOut])
async def list_business_days(
    tenant_id: str,
    hotel_id: int | None = None,
    paging: tuple[int, int] = Depends(Paged),
    session: AsyncSession = Depends(get_session),
) -> list[BusinessDay]:
    """营业日列表（M32 性能护栏：Paged limit/offset + 稳定排序）。"""
    limit, offset = paging
    stmt = select(BusinessDay).where(BusinessDay.tenant_id == tenant_id)
    if hotel_id is not None:
        stmt = stmt.where(BusinessDay.hotel_id == hotel_id)
    # 稳定排序：分页场景下无 order_by 会出现重复/漏行
    stmt = stmt.order_by(BusinessDay.id.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars())


@router.get("/tenants/{tenant_id}/daily-reports", response_model=list[DailyReportOut])
async def list_daily_reports(
    tenant_id: str,
    hotel_id: int | None = None,
    paging: tuple[int, int] = Depends(Paged),
    session: AsyncSession = Depends(get_session),
) -> list[DailyReport]:
    """夜审日报列表（M32 性能护栏：Paged limit/offset + 稳定排序）。"""
    limit, offset = paging
    stmt = select(DailyReport).where(DailyReport.tenant_id == tenant_id)
    if hotel_id is not None:
        stmt = stmt.where(DailyReport.hotel_id == hotel_id)
    # 稳定排序：分页场景下无 order_by 会出现重复/漏行
    stmt = stmt.order_by(DailyReport.id.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars())


@router.post("/tenants/{tenant_id}/night-audit/auto-run", response_model=AutoRunOut, dependencies=[Security(require_perm, scopes=[NIGHT_AUDIT_RUN])])
async def auto_run_night_audit(
    tenant_id: str, body: AutoRunIn, session: AsyncSession = Depends(get_session)
) -> AutoRunOut:
    """夜审自动调度（M4-2）：对租户下全部酒店批量跑批，单日异常挂起不阻断整批。"""
    svc = NightAuditScheduler(session)
    return AutoRunOut(**await svc.auto_run(tenant_id, body.as_of, body.operator))


@router.get("/tenants/{tenant_id}/night-audit/board", response_model=NightAuditBoardOut)
async def night_audit_board(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """集团跨店夜审监控（M17-lite）：各店最新营业日状态 + 挂账数 + 最新日报摘要。"""
    return await NightAuditService(session).night_audit_board(tenant_id)


# ---------- 佣金对账（M4-4） ----------


@router.post("/tenants/{tenant_id}/commission-rules", response_model=CommissionRuleOut)
async def set_commission_rule(
    tenant_id: str, body: CommissionRuleIn, session: AsyncSession = Depends(get_session)
) -> CommissionRule:
    svc = CommissionService(session)
    try:
        rule = await svc.set_rule(tenant_id, body.channel, body.rate_bps, body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(rule)
    return rule


@router.get("/tenants/{tenant_id}/commission-rules", response_model=list[CommissionRuleOut])
async def list_commission_rules(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[CommissionRule]:
    svc = CommissionService(session)
    return await svc.list_rules(tenant_id)


@router.get(
    "/tenants/{tenant_id}/commission-reconciliations",
    response_model=list[CommissionReconciliationOut],
)
async def list_commission_reconciliations(
    tenant_id: str,
    hotel_id: int | None = None,
    business_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[CommissionReconciliation]:
    stmt = select(CommissionReconciliation).where(
        CommissionReconciliation.tenant_id == tenant_id
    )
    if hotel_id is not None:
        stmt = stmt.where(CommissionReconciliation.hotel_id == hotel_id)
    if business_date is not None:
        stmt = stmt.where(CommissionReconciliation.business_date == business_date)
    result = await session.execute(stmt)
    return list(result.scalars())


# ---------- 冲调账（M4-5） ----------


@router.post("/tenants/{tenant_id}/bills/{bill_id}/adjustments", response_model=BillOut, dependencies=[Security(require_perm, scopes=[BILL_ADJUST])])
async def issue_adjustment(
    tenant_id: str,
    bill_id: int,
    body: AdjustmentIn,
    session: AsyncSession = Depends(get_session),
) -> Bill:
    bill = await _get_bill(tenant_id, bill_id, session)
    svc = CashierService(session)
    try:
        bill = await svc.issue_adjustment(
            bill, body.type, body.amount_cents, body.reason, body.operator
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    # M8-2 审计埋点：冲账/调账
    await audit_record(
        session,
        tenant_id,
        "billing.adjust",
        actor=body.operator,
        resource_type="bill",
        resource_id=bill.id,
        hotel_id=bill.hotel_id,
        detail={"type": body.type, "amount_cents": body.amount_cents, "reason": body.reason},
    )
    await session.commit()
    await session.refresh(bill)
    return await _bill_with_items(bill, session)


@router.get("/tenants/{tenant_id}/adjustments", response_model=list[AdjustmentOut])
async def list_adjustments(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[AdjustmentVoucher]:
    result = await session.execute(
        select(AdjustmentVoucher).where(AdjustmentVoucher.tenant_id == tenant_id)
    )
    return list(result.scalars())


# ---------- 前台收银交班（M3） ----------


@router.post("/tenants/{tenant_id}/shifts/open", response_model=ShiftOut)
async def open_shift(
    tenant_id: str, body: ShiftOpenIn, session: AsyncSession = Depends(get_session)
) -> ShiftHandover:
    svc = ShiftService(session)
    try:
        return await svc.open_shift(tenant_id, body.hotel_id, body.cashier, body.opening_float_cents)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/tenants/{tenant_id}/shifts/{shift_id}/close", response_model=ShiftOut)
async def close_shift(
    tenant_id: str,
    shift_id: int,
    body: ShiftCloseIn,
    session: AsyncSession = Depends(get_session),
) -> ShiftHandover:
    shift = await session.get(ShiftHandover, shift_id)
    if not shift or shift.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "交班记录不存在")
    svc = ShiftService(session)
    return await svc.close_shift(shift, body.counted_cash_cents, body.note)


@router.get("/tenants/{tenant_id}/shifts", response_model=list[ShiftOut])
async def list_shifts(
    tenant_id: str,
    hotel_id: int | None = None,
    paging: tuple[int, int] = Depends(Paged),
    session: AsyncSession = Depends(get_session),
) -> list[ShiftHandover]:
    """交班记录列表（M32 性能护栏：Paged limit/offset 透传 ShiftService.list_shifts）。"""
    limit, offset = paging
    svc = ShiftService(session)
    return await svc.list_shifts(tenant_id, hotel_id, limit=limit, offset=offset)


# ---------- 叫醒服务（M3-7） ----------


@router.post(
    "/tenants/{tenant_id}/wake-up-calls",
    response_model=WakeUpCallOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_wake_up_call(
    tenant_id: str, body: WakeUpCallIn, session: AsyncSession = Depends(get_session)
) -> WakeUpCall:
    svc = WakeUpCallService(session)
    try:
        return await svc.create(
            tenant_id,
            body.hotel_id,
            body.room_no,
            _parse_dt(body.call_at),
            guest_name=body.guest_name,
            note=body.note,
            operator=body.operator,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/tenants/{tenant_id}/wake-up-calls", response_model=list[WakeUpCallOut])
async def list_wake_up_calls(
    tenant_id: str,
    hotel_id: int,
    status_: str | None = None,
    due_before: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[WakeUpCall]:
    svc = WakeUpCallService(session)
    if due_before:
        return await svc.due_calls(tenant_id, hotel_id, _parse_dt(due_before))
    stmt = select(WakeUpCall).where(
        WakeUpCall.tenant_id == tenant_id, WakeUpCall.hotel_id == hotel_id
    )
    if status_:
        stmt = stmt.where(WakeUpCall.status == status_)
    result = await session.execute(stmt)
    return list(result.scalars())


@router.post("/tenants/{tenant_id}/wake-up-calls/{call_id}/done", response_model=WakeUpCallOut)
async def done_wake_up_call(
    tenant_id: str, call_id: int, session: AsyncSession = Depends(get_session)
) -> WakeUpCall:
    call = await session.get(WakeUpCall, call_id)
    if not call or call.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "叫醒任务不存在")
    return await WakeUpCallService(session).mark_done(call)


@router.post("/tenants/{tenant_id}/wake-up-calls/{call_id}/cancel", response_model=WakeUpCallOut)
async def cancel_wake_up_call(
    tenant_id: str, call_id: int, session: AsyncSession = Depends(get_session)
) -> WakeUpCall:
    call = await session.get(WakeUpCall, call_id)
    if not call or call.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "叫醒任务不存在")
    return await WakeUpCallService(session).cancel(call)


# ---------- PSB 上传队列（M3-5） ----------


@router.post("/tenants/{tenant_id}/psb-tasks", response_model=PsbTaskOut, status_code=status.HTTP_201_CREATED)
async def enqueue_psb(
    tenant_id: str, body: PsbTaskIn, session: AsyncSession = Depends(get_session)
) -> PsbUploadTask:
    """散客（无预订）现场登记上报任务。预订入住由 check-in 自动建，无需调用。"""
    svc = PsbService(session)
    return await svc.enqueue(
        tenant_id,
        body.hotel_id,
        body.guest_name,
        id_doc_no=body.id_doc_no,
        room_no=body.room_no,
        operator=body.operator,
    )


@router.get("/tenants/{tenant_id}/psb-tasks", response_model=list[PsbTaskOut])
async def list_psb_tasks(
    tenant_id: str,
    hotel_id: int | None = None,
    status_: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[PsbUploadTask]:
    return await PsbService(session).list_tasks(tenant_id, hotel_id, status_)


@router.post("/tenants/{tenant_id}/psb-tasks/{task_id}/upload", response_model=PsbTaskOut)
async def upload_psb(
    tenant_id: str, task_id: int, session: AsyncSession = Depends(get_session)
) -> PsbUploadTask:
    task = await session.get(PsbUploadTask, task_id)
    if not task or task.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "上报任务不存在")
    return await PsbService(session).upload(task)


# ---------- 权限审计（M8） ----------


@router.post(
    "/tenants/{tenant_id}/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[USER_MANAGE])],
)
async def create_user(
    tenant_id: str, body: UserCreate, session: AsyncSession = Depends(get_session)
) -> User:
    svc = RbacService(session)
    try:
        user = await svc.create_user(
            tenant_id, body.username, body.password, body.display_name, body.scope
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/tenants/{tenant_id}/users", response_model=list[UserOut])
async def list_users(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[User]:
    svc = RbacService(session)
    return await svc.list_users(tenant_id)


@router.post(
    "/tenants/{tenant_id}/roles",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[ROLE_MANAGE])],
)
async def create_role(
    tenant_id: str, body: RoleCreate, session: AsyncSession = Depends(get_session)
) -> Role:
    svc = RbacService(session)
    try:
        role = await svc.create_role(
            tenant_id, body.name, body.level, body.permissions, body.hotel_scoped
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(role)
    return role


@router.get("/tenants/{tenant_id}/roles", response_model=list[RoleOut])
async def list_roles(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[Role]:
    svc = RbacService(session)
    return await svc.list_roles(tenant_id)


@router.post(
    "/tenants/{tenant_id}/users/{user_id}/roles",
    response_model=UserRoleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[ROLE_MANAGE])],
)
async def assign_user_role(
    tenant_id: str,
    user_id: int,
    body: UserRoleIn,
    session: AsyncSession = Depends(get_session),
) -> UserRole:
    svc = RbacService(session)
    try:
        binding = await svc.assign_role(tenant_id, user_id, body.role_id, body.hotel_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(binding)
    return binding


@router.get(
    "/tenants/{tenant_id}/users/{user_id}/roles",
    response_model=list[UserRoleOut],
)
async def list_user_roles(
    tenant_id: str,
    user_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[UserRole]:
    svc = RbacService(session)
    return await svc.list_user_roles(tenant_id, user_id)


# 进程内「已同步默认角色」的租户缓存：每个进程生命周期内对每个租户只真正对账一次，
# 部署/重启后自然重新对账——存量租户因此能拿到 DEFAULT_ROLES 新增的权限点，
# 而无需手工跑回填脚本（M37 实测漂移的根治）。
_DEFAULT_ROLE_SYNCED: set[str] = set()


async def _ensure_default_roles_synced(tenant_id: str, session: AsyncSession) -> None:
    """登录成功后惰性同步默认角色定义（幂等、只增不减、不碰自定义角色）。"""
    if tenant_id in _DEFAULT_ROLE_SYNCED:
        return
    await RbacService(session).sync_default_roles(tenant_id)
    _DEFAULT_ROLE_SYNCED.add(tenant_id)


@router.post("/tenants/{tenant_id}/auth/login", response_model=LoginOut)
async def login(
    tenant_id: str, body: LoginIn, session: AsyncSession = Depends(get_session)
) -> LoginOut:
    """登录（M8-3）：密码校验 + 失败锁定；成功返回会话 token 与权限集。"""
    svc = RbacService(session)
    status_ = "ok"
    user: User | None = None
    try:
        user = await svc.authenticate(tenant_id, body.username, body.password, body.ip)
    except ValueError as exc:
        status_ = {
            "not_found": "not_found",
            "disabled": "disabled",
            "locked": "locked",
            "bad_credentials": "bad_credentials",
        }.get(str(exc), "bad_credentials")
    if user is None:
        # 失败：记录审计 + 发布登录事件（用户可能不存在）
        rec = await svc.get_user(tenant_id, body.username)
        actor_id = rec.id if rec else None
        await audit_record(
            session,
            tenant_id,
            "auth.login",
            actor=body.username,
            actor_id=actor_id,
            ip=body.ip,
            result="failure",
            detail={"reason": status_},
        )
        await event_bus.publish(
            UserLoggedIn(
                tenant_id=tenant_id,
                user_id=actor_id or 0,
                username=body.username,
                ip=body.ip,
                success=False,
            )
        )
        await session.commit()
        return LoginOut(token=None, username=body.username, display_name="", status=status_, permissions=[])

    # 成功：建会话 + 签发刷新令牌（M18-2）
    # 先对账默认角色（幂等），保证本次返回的 permissions 已包含 DEFAULT_ROLES 新增点
    await _ensure_default_roles_synced(tenant_id, session)
    sess = await svc.create_session(user, body.ip)
    rt = await svc.create_refresh_token(user)
    perms = await svc.effective_permissions(user)
    await audit_record(
        session,
        tenant_id,
        "auth.login",
        actor=user.username,
        actor_id=user.id,
        ip=body.ip,
        result="success",
        detail={"session_id": sess.id},
    )
    await event_bus.publish(
        UserLoggedIn(
            tenant_id=tenant_id,
            user_id=user.id,
            username=user.username,
            ip=body.ip,
            success=True,
        )
    )
    await session.commit()
    return LoginOut(
        token=sess.token,
        refresh_token=rt.token,
        username=user.username,
        display_name=user.display_name,
        status="ok",
        permissions=sorted(perms),
    )


@router.post(
    "/tenants/{tenant_id}/auth/refresh", response_model=RefreshOut
)
async def refresh_token(
    tenant_id: str, body: RefreshIn, session: AsyncSession = Depends(get_session)
) -> RefreshOut:
    """刷新令牌换新会话（M18-2）：一次性旋转——旧 refresh 立即作废，返回新 token+refresh。"""
    svc = RbacService(session)
    result = await svc.rotate_refresh_token(tenant_id, body.refresh_token)
    if result is None:
        await session.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "刷新令牌无效或已过期，请重新登录"
        )
    user, new_rt = result
    perms = await svc.effective_permissions(user)
    new_sess = await svc.create_session(user, ip=None)
    await session.commit()
    return RefreshOut(
        token=new_sess.token,
        refresh_token=new_rt.token,
        username=user.username,
        display_name=user.display_name,
        permissions=sorted(perms),
    )


@router.post("/tenants/{tenant_id}/auth/logout")
async def logout(
    tenant_id: str, body: LogoutIn, session: AsyncSession = Depends(get_session)
) -> dict:
    svc = RbacService(session)
    ok = await svc.revoke_session(tenant_id, body.token)
    # 同步吊销该用户全部刷新令牌（M18-2：登出即全端下线）
    sess = await session.execute(
        select(LoginSession).where(
            LoginSession.tenant_id == tenant_id, LoginSession.token == body.token
        )
    )
    login_row = sess.scalar_one_or_none()
    revoked_rt = (
        await svc.revoke_user_refresh_tokens(tenant_id, login_row.user_id)
        if login_row
        else 0
    )
    await session.commit()
    return {"revoked": ok, "refresh_tokens_revoked": revoked_rt}


@router.post("/tenants/{tenant_id}/auth/check", response_model=PermissionCheckOut)
async def check_permission(
    tenant_id: str, body: PermissionCheckIn, session: AsyncSession = Depends(get_session)
) -> PermissionCheckOut:
    """鉴权校验（M8-3）：按会话 token 解析用户并判断权限（含门店级作用域）。"""
    svc = RbacService(session)
    sess = await svc.get_session(tenant_id, body.token)
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "会话无效或已过期")
    user = await session.get(User, sess.user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    granted = await svc.has_permission(user, body.permission, body.hotel_id)
    if not granted:
        await audit_record(
            session,
            tenant_id,
            "auth.permission_denied",
            actor=user.username,
            actor_id=user.id,
            result="failure",
            detail={"permission": body.permission, "hotel_id": body.hotel_id},
        )
        await event_bus.publish(
            PermissionDenied(
                tenant_id=tenant_id,
                user_id=user.id,
                username=user.username,
                permission=body.permission,
                resource=str(body.hotel_id) if body.hotel_id else None,
            )
        )
        await session.commit()
    return PermissionCheckOut(
        granted=granted, permission=body.permission, username=user.username
    )


@router.get("/tenants/{tenant_id}/audit-logs", response_model=list[AuditLogOut], dependencies=[Security(require_perm, scopes=[AUDIT_VIEW])])
async def query_audit_logs(
    tenant_id: str,
    action: str | None = None,
    resource_type: str | None = None,
    hotel_id: int | None = None,
    actor: str | None = None,
    result_: str | None = None,
    token: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> list[AuditLog]:
    """审计查询/导出（M8-2，需 audit.view 权限）。"""
    # 若携带 token 则校验审计查看权限
    if token:
        svc = RbacService(session)
        sess = await svc.get_session(tenant_id, token)
        if sess is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "会话无效或已过期")
        user = await session.get(User, sess.user_id)
        if not user or not await svc.has_tenant_scope_permission(user, AUDIT_VIEW):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无审计查看权限")
        actor_name = user.username
    else:
        actor_name = "system"
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if hotel_id is not None:
        stmt = stmt.where(AuditLog.hotel_id == hotel_id)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if result_:
        stmt = stmt.where(AuditLog.result == result_)
    stmt = stmt.order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500)))
    result = await session.execute(stmt)
    logs = list(result.scalars())
    # 导出本身留痕（M8-2：导出全覆盖）
    await audit_record(
        session,
        tenant_id,
        "audit.view",
        actor=actor_name,
        resource_type="audit_logs",
        detail={"filters": {"action": action, "resource_type": resource_type, "hotel_id": hotel_id}},
    )
    await session.commit()
    return logs


# ---------- 移动端直订小程序（M7-1） ----------


@router.get("/tenants/{tenant_id}/mp/offers", response_model=list[MpOfferOut])
async def mp_offers(
    tenant_id: str,
    hotel_id: int,
    check_in: str,
    check_out: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """小程序房型报价：逐晚价格 + 可售量（任一晚无房即不可订）。"""
    svc = MpService(session)
    return await svc.room_type_offers(tenant_id, hotel_id, check_in, check_out)


@router.post(
    "/tenants/{tenant_id}/mp/orders",
    response_model=MpOrderOut,
    status_code=status.HTTP_201_CREATED,
)
async def mp_place_order(
    tenant_id: str, body: MpOrderPlaceIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """小程序一键下单：建预订(channel=wechat_mp) + 生成待支付订单。"""
    svc = MpService(session)
    try:
        return await svc.place_order(
            tenant_id,
            body.hotel_id,
            body.room_type_id,
            body.guest_name,
            body.check_in_date,
            body.check_out_date,
            guest_phone=body.guest_phone,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/tenants/{tenant_id}/mp/orders/{out_trade_no}", response_model=MpOrderOut)
async def mp_order_detail(
    tenant_id: str, out_trade_no: str, session: AsyncSession = Depends(get_session)
) -> dict:
    order = await session.execute(
        select(PayOrder).where(
            PayOrder.tenant_id == tenant_id, PayOrder.out_trade_no == out_trade_no
        )
    )
    order = order.scalar_one_or_none()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "支付单不存在")
    booking = await session.get(Booking, order.booking_id) if order.booking_id else None
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "关联预订不存在")
    return {"booking": booking, "pay_order": order}


# ---------- 移动支付（M7-2） ----------


@router.post("/tenants/{tenant_id}/pay/notify", response_model=PayNotifyResultOut)
async def pay_notify(
    tenant_id: str, body: PayNotifyIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """支付回调（mock 微信通知）：幂等去重 + 金额校验 + 支付成功落账。"""
    svc = PayService(session)
    result = await svc.handle_notify(
        tenant_id,
        body.out_trade_no,
        body.amount_cents,
        body.transaction_id,
        body.notify_id,
        payload=body.payload,
    )
    await session.commit()
    return result


@router.get("/tenants/{tenant_id}/pay-orders", response_model=list[PayOrderOut])
async def list_pay_orders(
    tenant_id: str,
    status_: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[PayOrder]:
    return await PayService(session).list_orders(tenant_id, status_)


@router.post("/tenants/{tenant_id}/pay-orders/{out_trade_no}/close", response_model=PayOrderOut)
async def close_pay_order(
    tenant_id: str, out_trade_no: str, session: AsyncSession = Depends(get_session)
) -> PayOrder:
    svc = PayService(session)
    row = await session.execute(
        select(PayOrder).where(
            PayOrder.tenant_id == tenant_id, PayOrder.out_trade_no == out_trade_no
        )
    )
    order = row.scalar_one_or_none()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "支付单不存在")
    try:
        closed = await svc.close_order(order)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(closed)
    return closed


@router.post("/tenants/{tenant_id}/pay/reconcile", response_model=PayReconcileOut)
async def pay_reconcile(
    tenant_id: str, body: PayReconcileIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """掉单对账（M7-2）：对 before 之前创建的未支付单渠道查单 → 补单或关单。"""
    svc = PayService(session)
    result = await svc.reconcile(tenant_id, _parse_dt(body.before))
    await session.commit()
    return result


@router.post("/tenants/{tenant_id}/bills/{bill_id}/apply-prepay", response_model=BillOut)
async def apply_prepay(
    tenant_id: str, bill_id: int, session: AsyncSession = Depends(get_session)
) -> Bill:
    """预付抵扣：将已支付未落账的小程序预付单落为账单收款（开单晚于回调时）。"""
    bill = await _get_bill(tenant_id, bill_id, session)
    applied = await PayService(session).apply_prepay(bill)
    await session.commit()
    await session.refresh(bill)
    return await _bill_with_items(bill, session)


# ---------- 店长 App（M10） ----------


@router.get("/tenants/{tenant_id}/manager/dashboard", response_model=DashboardOut)
async def manager_dashboard(
    tenant_id: str,
    hotel_id: int,
    business_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """经营看板（M10-1，FR-APP-01）：房态盘汇总 + 在住/预抵/预离 + 指标 + 待办提醒。"""
    svc = ManagerService(session)
    return await svc.dashboard(tenant_id, hotel_id, business_date)


@router.post(
    "/tenants/{tenant_id}/approvals",
    response_model=ApprovalTicketOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_approval(
    tenant_id: str, body: ApprovalSubmitIn, session: AsyncSession = Depends(get_session)
) -> ApprovalTicket:
    """提交审批（M10-2，FR-APP-02）：折扣/冲账/超额预订/退款，审批≤2步。"""
    svc = ApprovalService(session)
    try:
        ticket = await svc.submit(
            tenant_id,
            body.hotel_id,
            body.type,
            body.payload,
            body.reason,
            body.applicant,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(ticket)
    return ticket


@router.get("/tenants/{tenant_id}/approvals", response_model=list[ApprovalTicketOut])
async def list_approvals(
    tenant_id: str,
    status_: str | None = None,
    hotel_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ApprovalTicket]:
    return await ApprovalService(session).list_tickets(tenant_id, status_, hotel_id)


@router.post("/tenants/{tenant_id}/approvals/{ticket_id}/decide", response_model=ApprovalTicketOut)
async def decide_approval(
    tenant_id: str,
    ticket_id: int,
    body: ApprovalDecideIn,
    session: AsyncSession = Depends(get_session),
) -> ApprovalTicket:
    """一键审批（M10-2）：通过即自动执行（折扣落账），驳回即终止；全程留痕。"""
    ticket = await session.get(ApprovalTicket, ticket_id)
    if not ticket or ticket.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "审批单不存在")
    svc = ApprovalService(session)
    try:
        decided = await svc.decide(ticket, body.decision, body.approver, body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(decided)
    return decided


@router.post(
    "/tenants/{tenant_id}/housekeeping-tasks",
    response_model=HousekeepingTaskOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_housekeeping_task(
    tenant_id: str, body: HousekeepingTaskIn, session: AsyncSession = Depends(get_session)
) -> HousekeepingTask:
    svc = HousekeepingService(session)
    try:
        task = await svc.create_task(
            tenant_id,
            body.hotel_id,
            body.room_no,
            task_type=body.task_type,
            assignee=body.assignee,
            note=body.note,
            due_at=_parse_dt(body.due_at) if body.due_at else None,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(task)
    return task


@router.get("/tenants/{tenant_id}/housekeeping-tasks", response_model=list[HousekeepingTaskOut])
async def list_housekeeping_tasks(
    tenant_id: str,
    hotel_id: int | None = None,
    status_: str | None = None,
    task_type: str | None = None,
    assignee: str | None = None,
    floor: str | None = None,
    limit: int = Query(MAX_LIST_ROWS, le=MAX_LIST_ROWS, ge=1, description="返回行数上限"),
    offset: int = Query(0, ge=0, description="跳过的行数"),
    session: AsyncSession = Depends(get_session),
) -> list[HousekeepingTask]:
    """M26：多维过滤（状态 / 类型 / 员工 / 楼层）+ M30 性能护栏（limit/offset）。"""
    return await HousekeepingService(session).list_tasks(
        tenant_id,
        hotel_id,
        status_,
        task_type=task_type,
        assignee=assignee,
        floor=floor,
        limit=limit,
        offset=offset,
    )


# ---------- M26 客房深度：批量操作 + 员工绩效 ----------


@router.post("/tenants/{tenant_id}/housekeeping-tasks/batch-assign")
async def batch_assign_housekeeping_tasks(
    tenant_id: str,
    body: HousekeepingBatchAssignIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """批量派单（M26）：逐单尝试，返回成功/失败明细。"""
    result = await HousekeepingService(session).batch_assign(
        tenant_id, body.task_ids, body.assignee
    )
    await session.commit()
    return result


@router.post("/tenants/{tenant_id}/housekeeping-tasks/batch-done")
async def batch_done_housekeeping_tasks(
    tenant_id: str,
    body: HousekeepingBatchDoneIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """批量完成（M26）：清扫单逐单联动空脏→空净。"""
    result = await HousekeepingService(session).batch_done(
        tenant_id, body.task_ids, body.operator
    )
    await session.commit()
    return result


@router.get("/tenants/{tenant_id}/analytics/housekeeping-performance")
async def housekeeping_performance(
    tenant_id: str,
    hotel_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """员工清扫绩效（M26，验收 #28）：完成单数 / 平均耗时分钟。"""
    return await HousekeepingService(session).staff_performance(
        tenant_id, hotel_id, start_date, end_date
    )


@router.post(
    "/tenants/{tenant_id}/housekeeping-tasks/{task_id}/assign",
    response_model=HousekeepingTaskOut,
)
async def assign_housekeeping_task(
    tenant_id: str,
    task_id: int,
    body: HousekeepingAssignIn,
    session: AsyncSession = Depends(get_session),
) -> HousekeepingTask:
    task = await session.get(HousekeepingTask, task_id)
    if not task or task.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "工单不存在")
    svc = HousekeepingService(session)
    try:
        task = await svc.assign(task, body.assignee)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(task)
    return task


@router.post(
    "/tenants/{tenant_id}/housekeeping-tasks/{task_id}/done",
    response_model=HousekeepingTaskOut,
)
async def done_housekeeping_task(
    tenant_id: str, task_id: int, session: AsyncSession = Depends(get_session)
) -> HousekeepingTask:
    """完成工单（M10-3）：清扫单完成联动房态 空脏→空净 回归可售。"""
    task = await session.get(HousekeepingTask, task_id)
    if not task or task.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "工单不存在")
    svc = HousekeepingService(session)
    try:
        task = await svc.done(task)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(task)
    return task


@router.get("/tenants/{tenant_id}/notifications", response_model=list[NotificationOut])
async def list_notifications(
    tenant_id: str,
    hotel_id: int | None = None,
    unread_only: bool = False,
    ref_type: str | None = None,
    level: str | None = None,
    limit: int = 50,
    offset: int = 0,
    login_session: LoginSession = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> list[Notification]:
    """消息推送（M10-4，FR-APP-04）：日报/待办提醒，unread_only 过滤未读。

    ⑥ 按登录用户 RBAC 角色做 recipients 行级可见性过滤；新增 ref_type/level 筛选 + 分页。
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    svc = NotificationService(session)
    tags = await svc.resolve_user_tags(tenant_id, login_session.user_id)
    return await svc.list_notifications(
        tenant_id,
        hotel_id,
        unread_only,
        recipient_tags=tags,
        ref_type=ref_type,
        level=level,
        limit=limit,
        offset=offset,
    )


@router.get("/tenants/{tenant_id}/notifications/unread-count")
async def count_unread_notifications(
    tenant_id: str,
    hotel_id: int | None = None,
    login_session: LoginSession = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """未读消息数（顶栏角标）；⑥ 按角色过滤可见项。"""
    svc = NotificationService(session)
    tags = await svc.resolve_user_tags(tenant_id, login_session.user_id)
    return {"unread": await svc.count_unread(tenant_id, hotel_id, recipient_tags=tags)}


@router.post("/tenants/{tenant_id}/notifications/read-all")
async def read_all_notifications(
    tenant_id: str,
    hotel_id: int | None = None,
    login_session: LoginSession = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """一键全部已读（幂等）：仅标记本人可见的未读项（⑥ 行级可见性），返回受影响行数。
    可选 hotel_id 时仅清该门店未读（UX 增强：按门店维度筛选的配套写操作）。"""
    svc = NotificationService(session)
    tags = await svc.resolve_user_tags(tenant_id, login_session.user_id)
    updated = await svc.mark_all_read(tenant_id, hotel_id, recipient_tags=tags)
    await session.commit()
    return {"updated": updated}


@router.post("/tenants/{tenant_id}/notifications/{notification_id}/read", response_model=NotificationOut)
async def read_notification(
    tenant_id: str,
    notification_id: int,
    login_session: LoginSession = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> Notification:
    """点击消息跳转前调用：标记已读并返回该消息（含 link 深链），幂等。⑥ 不可见通知返回 404。"""
    n = await session.get(Notification, notification_id)
    if not n or n.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "消息不存在")
    svc = NotificationService(session)
    tags = await svc.resolve_user_tags(tenant_id, login_session.user_id)
    if not notification_visible_to(n.recipients, tags):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "消息不存在或无权访问")
    n = await svc.mark_read(n)
    await session.commit()
    await session.refresh(n)
    return n


# ---------- ③ 通知分级 / 免打扰偏好 ----------


@router.get(
    "/tenants/{tenant_id}/notification-preferences",
    response_model=NotificationPreferenceOut,
)
async def get_notification_preferences(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> NotificationPreferenceOut:
    """读取租户通知偏好（免打扰开关与安静时段），无记录返回默认值。"""
    pref = await NotificationService(session).get_preference(tenant_id)
    if not pref:
        return NotificationPreferenceOut(
            tenant_id=tenant_id, dnd_enabled=False, dnd_start="22:00", dnd_end="08:00"
        )
    return pref


@router.put(
    "/tenants/{tenant_id}/notification-preferences",
    response_model=NotificationPreferenceOut,
)
async def update_notification_preferences(
    tenant_id: str,
    body: NotificationPreferenceUpdateIn,
    session: AsyncSession = Depends(get_session),
) -> NotificationPreferenceOut:
    """更新租户通知偏好（免打扰开关 / 安静时段起止，HH:MM）。"""
    pref = await NotificationService(session).get_preference(tenant_id)
    if not pref:
        pref = NotificationPreference(tenant_id=tenant_id)
        session.add(pref)
    if body.dnd_enabled is not None:
        pref.dnd_enabled = body.dnd_enabled
    if body.dnd_start is not None:
        pref.dnd_start = body.dnd_start
    if body.dnd_end is not None:
        pref.dnd_end = body.dnd_end
    # 落库前暂存字段，避免 commit 后实例过期无法读取
    dnd_enabled, dnd_start, dnd_end = pref.dnd_enabled, pref.dnd_start, pref.dnd_end
    session.add(pref)
    await session.flush()
    await session.commit()
    return NotificationPreferenceOut(
        tenant_id=tenant_id, dnd_enabled=dnd_enabled, dnd_start=dnd_start, dnd_end=dnd_end
    )


# ---------- ④ 多接收人 / 角色订阅 ----------


@router.get(
    "/tenants/{tenant_id}/notification-subscriptions",
    response_model=list[NotificationSubscriptionOut],
)
async def list_notification_subscriptions(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[NotificationSubscriptionOut]:
    """读取全部 ref_type 的接收角色配置矩阵。

    返回覆盖 REF_LINK_TEMPLATES 中的所有 ref_type（含未单独配置的），
    未配置项回落到 DEFAULT_SUBSCRIBERS，便于前端一次性渲染可编辑表格。
    """
    svc = NotificationService(session)
    configured = {s.ref_type: s.recipients for s in await svc.get_subscriptions(tenant_id)}
    rows: list[NotificationSubscriptionOut] = []
    for ref_type in REF_LABELS:  # 仅暴露通知中心实际有标签的 ref_type
        rows.append(
            NotificationSubscriptionOut(
                tenant_id=tenant_id,
                ref_type=ref_type,
                label=REF_LABELS[ref_type],
                recipients=configured.get(
                    ref_type, DEFAULT_SUBSCRIBERS.get(ref_type, ["store_manager"])
                ),
            )
        )
    return rows


@router.put(
    "/tenants/{tenant_id}/notification-subscriptions",
    response_model=list[NotificationSubscriptionOut],
)
async def update_notification_subscriptions(
    tenant_id: str,
    body: NotificationSubscriptionBulkIn,
    session: AsyncSession = Depends(get_session),
) -> list[NotificationSubscriptionOut]:
    """批量 upsert 订阅配置：每条按 (tenant_id, ref_type) 写入接收角色列表。"""
    svc = NotificationService(session)
    for item in body.items:
        await svc.set_subscription(tenant_id, item.ref_type, item.recipients)
    await session.commit()
    # 回读完整矩阵（与 GET 一致），前端保存后直接刷新
    configured = {s.ref_type: s.recipients for s in await svc.get_subscriptions(tenant_id)}
    return [
        NotificationSubscriptionOut(
            tenant_id=tenant_id,
            ref_type=ref_type,
            label=REF_LABELS[ref_type],
            recipients=configured.get(
                ref_type, DEFAULT_SUBSCRIBERS.get(ref_type, ["store_manager"])
            ),
        )
        for ref_type in REF_LABELS
    ]


# ---------- 集团多店管控（M17） ----------


@router.post(
    "/tenants/{tenant_id}/group/price-policies",
    response_model=GroupPricePolicyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_group_price_policy(
    tenant_id: str, body: GroupPricePolicyIn, session: AsyncSession = Depends(get_session)
) -> GroupPricePolicy:
    """M17-2 中央房价下发：总部为租户/门店/房型设置价格上下界。"""
    svc = GroupService(session)
    policy = await svc.set_price_policy(
        tenant_id,
        body.price_floor_cents,
        body.price_ceiling_cents,
        hotel_id=body.hotel_id,
        room_type_id=body.room_type_id,
        note=body.note,
    )
    await session.commit()
    await session.refresh(policy)
    return policy


@router.get("/tenants/{tenant_id}/group/price-policies", response_model=list[GroupPricePolicyOut])
async def list_group_price_policies(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[GroupPricePolicy]:
    return await GroupService(session).list_policies(tenant_id)


@router.get("/tenants/{tenant_id}/group/dashboard", response_model=HqDashboardOut)
async def hq_dashboard(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """M17-1 总部驾驶舱：各店最新日报聚合，按 RevPAR 横向排名。"""
    return await GroupService(session).hq_dashboard(tenant_id)


@router.get("/tenants/{tenant_id}/group/settlement", response_model=SettlementOut)
async def group_settlement(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """M17-3 两级分账汇总：集团/分店现付预付分账口径。"""
    return await GroupService(session).settlement(tenant_id)


# ---------- AI 服务（M11/M12） ----------


@router.post(
    "/tenants/{tenant_id}/ai/chat-sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    tenant_id: str, body: ChatSessionCreate, session: AsyncSession = Depends(get_session)
) -> ChatSession:
    """M11：创建智能客服会话。"""
    svc = ChatbotService(session)
    sess = await svc.create_session(
        tenant_id,
        channel=body.channel,
        guest_name=body.guest_name,
        guest_phone=body.guest_phone,
    )
    await session.commit()
    await session.refresh(sess)
    return sess


@router.get("/tenants/{tenant_id}/ai/chat-sessions/{session_id}", response_model=ChatSessionOut)
async def get_chat_session(
    tenant_id: str, session_id: int, session: AsyncSession = Depends(get_session)
) -> ChatSession:
    sess = await session.get(ChatSession, session_id)
    if not sess or sess.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    return sess


@router.get("/tenants/{tenant_id}/ai/chat-sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(
    tenant_id: str,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ChatSession]:
    return await ChatbotService(session).list_sessions(tenant_id, status=status)


@router.post(
    "/tenants/{tenant_id}/ai/chat-sessions/{session_id}/messages",
    response_model=ChatReplyOut,
    status_code=status.HTTP_201_CREATED,
)
async def chat_reply(
    tenant_id: str,
    session_id: int,
    body: ChatMessageIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """M11：用户发送消息，机器人自动应答并返回意图/置信度/是否转人工。"""
    svc = ChatbotService(session)
    sess = await session.get(ChatSession, session_id)
    if not sess or sess.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if sess.status == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, "会话已关闭")
    msg = await svc.reply(sess, body.content, hotel_id=body.hotel_id)
    await session.commit()
    await session.refresh(msg)
    return {
        "bot_message": msg,
        "handoff": sess.status == "handoff",
        "intent": msg.intent,
        "confidence": msg.confidence,
    }


@router.post("/tenants/{tenant_id}/ai/chat-sessions/{session_id}/handoff", response_model=ChatMessageOut)
async def chat_handoff(
    tenant_id: str,
    session_id: int,
    body: ChatHandoffIn,
    session: AsyncSession = Depends(get_session),
) -> ChatMessage:
    """M11：显式转人工。"""
    svc = ChatbotService(session)
    sess = await session.get(ChatSession, session_id)
    if not sess or sess.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    msg = await svc.handoff(sess, body.reason, hotel_id=body.hotel_id)
    await session.commit()
    await session.refresh(msg)
    return msg


@router.post("/tenants/{tenant_id}/ai/chat-sessions/{session_id}/close", response_model=ChatSessionOut)
async def close_chat_session(
    tenant_id: str,
    session_id: int,
    body: ChatCloseIn,
    session: AsyncSession = Depends(get_session),
) -> ChatSession:
    """M11：关闭会话并记录满意度。"""
    svc = ChatbotService(session)
    sess = await session.get(ChatSession, session_id)
    if not sess or sess.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    sess = await svc.close_session(sess, satisfaction=body.satisfaction)
    await session.commit()
    await session.refresh(sess)
    return sess


@router.get(
    "/tenants/{tenant_id}/ai/chat-sessions/{session_id}/messages",
    response_model=list[ChatMessageOut],
)
async def list_chat_messages(
    tenant_id: str, session_id: int, session: AsyncSession = Depends(get_session)
) -> list[ChatMessage]:
    sess = await session.get(ChatSession, session_id)
    if not sess or sess.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    return await ChatbotService(session).list_messages(session_id)


@router.get("/tenants/{tenant_id}/ai/alerts", response_model=list[AlertNotificationOut])
async def list_alerts(
    tenant_id: str,
    hotel_id: int | None = None,
    status: str | None = None,
    paging: tuple[int, int] = Depends(Paged),
    session: AsyncSession = Depends(get_session),
) -> list[AlertNotification]:
    """M12：AI 自动对账预警列表（M32 性能护栏：Paged limit/offset 透传 AnomalyService.list_alerts）。"""
    limit, offset = paging
    return await AnomalyService(session).list_alerts(
        tenant_id, hotel_id=hotel_id, status=status, limit=limit, offset=offset
    )


@router.post("/tenants/{tenant_id}/ai/alerts/{alert_id}/acknowledge", response_model=AlertNotificationOut)
async def acknowledge_alert(
    tenant_id: str, alert_id: int, session: AsyncSession = Depends(get_session)
) -> AlertNotification:
    alert = await session.get(AlertNotification, alert_id)
    if not alert or alert.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预警不存在")
    alert = await AnomalyService(session).acknowledge(alert)
    await session.commit()
    await session.refresh(alert)
    return alert


@router.post("/tenants/{tenant_id}/ai/alerts/{alert_id}/resolve", response_model=AlertNotificationOut)
async def resolve_alert(
    tenant_id: str, alert_id: int, session: AsyncSession = Depends(get_session)
) -> AlertNotification:
    alert = await session.get(AlertNotification, alert_id)
    if not alert or alert.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "预警不存在")
    alert = await AnomalyService(session).resolve(alert)
    await session.commit()
    await session.refresh(alert)
    return alert


# ---------- 数据中台/经营分析（M16） ----------


@router.get("/tenants/{tenant_id}/analytics/dashboard", response_model=AnalyticsDashboardOut)
async def analytics_dashboard(
    tenant_id: str,
    hotel_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """单店经营看板：KPI 聚合与日序列（M30：热点读缓存，写路径显式失效 + TTL 兜底）。"""
    cache_key = f"dashboard:{tenant_id}:{hotel_id}:{start_date or ''}:{end_date or ''}"
    cached = await get_cache().get(cache_key)
    if cached is not None:
        return cached
    svc = AnalyticsService(session)
    try:
        result = await svc.dashboard(tenant_id, hotel_id, start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await get_cache().set(cache_key, result, ttl=60)  # M30 C4：60s TTL（夜审后当天数据才变）
    return result


@router.get("/tenants/{tenant_id}/analytics/hotel-ranking", response_model=AnalyticsRankingOut)
async def analytics_hotel_ranking(
    tenant_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """集团门店横向排名：按 RevPAR 降序。"""
    return await AnalyticsService(session).hotel_ranking(tenant_id, start_date, end_date)


@router.get("/tenants/{tenant_id}/analytics/channel-revenue", response_model=AnalyticsChannelOut)
async def analytics_channel_revenue(
    tenant_id: str,
    hotel_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """渠道收入分析：按预订渠道聚合间夜与收入。"""
    return await AnalyticsService(session).channel_revenue(tenant_id, hotel_id, start_date, end_date)


# ---------- M25 店总 BI：超卖预警 / 在手预测 / 自定义报表 ----------


@router.get("/tenants/{tenant_id}/analytics/oversell-warnings")
async def analytics_oversell_warnings(
    tenant_id: str,
    hotel_id: int,
    start_date: str,
    end_date: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """超卖预警（验收 #19）：逐日在手预订量 vs 可售房量。"""
    return await AnalyticsService(session).oversell_warnings(
        tenant_id, hotel_id, start_date, end_date
    )


@router.get("/tenants/{tenant_id}/analytics/forecast")
async def analytics_forecast(
    tenant_id: str,
    hotel_id: int,
    days: int = 14,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """远期在手入住率 + 预订增速（验收 #16，OTB 口径）。"""
    return await AnalyticsService(session).occupancy_forecast(tenant_id, hotel_id, days)


@router.get("/tenants/{tenant_id}/analytics/custom-report")
async def analytics_custom_report(
    tenant_id: str,
    hotel_id: int,
    group_by: str = "day",
    start_date: str | None = None,
    end_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """自定义报表（验收 #15）：按房型/渠道/入住日聚合。"""
    try:
        return await AnalyticsService(session).custom_report(
            tenant_id, hotel_id, group_by, start_date, end_date
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/tenants/{tenant_id}/analytics/room-type-revenue", response_model=AnalyticsRoomTypeOut)
async def analytics_room_type_revenue(
    tenant_id: str,
    hotel_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """房型收入分析：按房型聚合间夜与收入。"""
    return await AnalyticsService(session).room_type_revenue(tenant_id, hotel_id, start_date, end_date)


@router.get("/tenants/{tenant_id}/analytics/payment-summary", response_model=AnalyticsPaymentOut)
async def analytics_payment_summary(
    tenant_id: str,
    hotel_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """支付方式汇总：按实收方式统计金额。"""
    return await AnalyticsService(session).payment_summary(tenant_id, hotel_id, start_date, end_date)


@router.get("/tenants/{tenant_id}/analytics/export")
async def analytics_export(
    tenant_id: str,
    report_type: str,
    hotel_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    format: str = "json",
    session: AsyncSession = Depends(get_session),
) -> Any:
    """报表导出（M16）：支持 json/csv，由 API 层序列化。"""
    svc = AnalyticsService(session)
    try:
        data = await svc.export_data(report_type, tenant_id, hotel_id, start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if format == "csv":
        return _analytics_csv_response(report_type, data)
    return data


def _analytics_csv_response(report_type: str, data: dict) -> dict:
    """CSV 语义：返回表头与行数组（前端可下载）。"""
    rows: list[list[str]] = []
    if report_type == "hotel_ranking":
        header = ["hotel_id", "name", "room_revenue_cents", "total_revenue_cents", "revpar_cents", "adr_cents", "occ_pct_bps"]
        rows = [[str(r.get(c, "")) for c in header] for r in data.get("hotels", [])]
    elif report_type == "channel_revenue":
        header = ["channel", "booking_count", "room_revenue_cents"]
        rows = [[str(r.get(c, "")) for c in header] for r in data.get("channels", [])]
    elif report_type == "room_type_revenue":
        header = ["room_type_id", "room_type_name", "booking_count", "room_revenue_cents"]
        rows = [[str(r.get(c, "")) for c in header] for r in data.get("room_types", [])]
    elif report_type == "dashboard":
        header = ["business_date", "occupied_rooms", "room_revenue_cents", "total_revenue_cents", "adr_cents", "occ_pct_bps"]
        rows = [[str(r.get(c, "")) for c in header] for r in data.get("daily_series", [])]
    return {"format": "csv", "header": header, "rows": rows, "meta": {k: v for k, v in data.items() if k not in ("hotels", "channels", "room_types", "daily_series")}}


# ---------- 开放 API 平台（M18） ----------


@router.post(
    "/tenants/{tenant_id}/openapi/apps",
    response_model=OpenApiAppOut,
    status_code=status.HTTP_201_CREATED,
)
async def register_openapi_app(
    tenant_id: str, body: OpenApiAppCreate, session: AsyncSession = Depends(get_session)
) -> OpenApiApp:
    """M18：注册第三方应用。"""
    svc = OpenApiService(session)
    try:
        app = await svc.register_app(
            tenant_id,
            body.app_code,
            body.name,
            callback_url=body.callback_url,
            events_subscribed=body.events_subscribed,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(app)
    return app


@router.get("/tenants/{tenant_id}/openapi/apps", response_model=list[OpenApiAppOut])
async def list_openapi_apps(
    tenant_id: str, session: AsyncSession = Depends(get_session)
) -> list[OpenApiApp]:
    return await OpenApiService(session).list_apps(tenant_id)


@router.post(
    "/tenants/{tenant_id}/openapi/apps/{app_id}/keys",
    response_model=OpenApiKeyWithSecret,
    status_code=status.HTTP_201_CREATED,
)
async def create_openapi_key(
    tenant_id: str,
    app_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """M18：为应用创建 API Key，明文仅返回一次。"""
    svc = OpenApiService(session)
    app = await svc.get_app(tenant_id, app_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "应用不存在")
    key, plaintext = await svc.create_key(app)
    await session.commit()
    await session.refresh(key)
    return {"key": key, "secret": plaintext}


@router.get("/tenants/{tenant_id}/openapi/apps/{app_id}/keys", response_model=list[OpenApiKeyOut])
async def list_openapi_keys(
    tenant_id: str, app_id: int, session: AsyncSession = Depends(get_session)
) -> list[OpenApiKey]:
    svc = OpenApiService(session)
    app = await svc.get_app(tenant_id, app_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "应用不存在")
    return await svc.list_keys(app)


@router.post(
    "/tenants/{tenant_id}/openapi/apps/{app_id}/keys/{key_id}/revoke",
    response_model=OpenApiKeyOut,
)
async def revoke_openapi_key(
    tenant_id: str,
    app_id: int,
    key_id: int,
    session: AsyncSession = Depends(get_session),
) -> OpenApiKey:
    """M18：吊销 API Key。"""
    svc = OpenApiService(session)
    app = await svc.get_app(tenant_id, app_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "应用不存在")
    try:
        key = await svc.revoke_key(key_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await session.commit()
    await session.refresh(key)
    return key


@router.post(
    "/tenants/{tenant_id}/openapi/verify-key",
    response_model=OpenApiAppOut,
)
async def verify_openapi_key(
    tenant_id: str, body: OpenApiVerifyKeyIn, session: AsyncSession = Depends(get_session)
) -> OpenApiApp:
    """M18：校验 API Key 并返回应用信息。"""
    app = await OpenApiService(session).verify_key(tenant_id, body.api_key)
    if app is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API Key 无效或已吊销")
    return app


@router.post(
    "/tenants/{tenant_id}/openapi/webhooks",
    response_model=OpenApiWebhookOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_openapi_webhook(
    tenant_id: str, body: OpenApiWebhookIn, session: AsyncSession = Depends(get_session)
) -> WebhookSubscription:
    """M18：为应用订阅 Webhook 事件（topic 精确匹配或用 * 订阅全部）。"""
    svc = OpenApiService(session)
    try:
        sub = await svc.subscribe(
            tenant_id,
            body.app_id,
            body.topic,
            body.endpoint_url,
            secret=body.secret,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(sub)
    return sub


@router.get(
    "/tenants/{tenant_id}/openapi/webhooks",
    response_model=list[OpenApiWebhookOut],
)
async def list_openapi_webhooks(
    tenant_id: str,
    app_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[WebhookSubscription]:
    return await OpenApiService(session).list_subscriptions(tenant_id, app_id=app_id)


@router.post(
    "/tenants/{tenant_id}/openapi/webhooks/{subscription_id}/test",
    response_model=OpenApiWebhookTestOut,
)
async def test_openapi_webhook(
    tenant_id: str,
    subscription_id: int,
    session: AsyncSession = Depends(get_session),
) -> WebhookDelivery:
    """M18：手动触发测试事件，验证 Webhook 可达性与签名。"""
    svc = OpenApiService(session)
    try:
        delivery = await svc.test_webhook(tenant_id, subscription_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await session.commit()
    await session.refresh(delivery)
    return delivery


# ---------- M18 第三方只读开放接口（API-Key 鉴权） ----------
# 路径含 /openapi/，已在 require_auth 白名单放行；本组路由改由 require_api_key
# 校验 Bearer pms_xxx。所有查询以 app.tenant_id 作用域，杜绝跨租户越权。


@router.get(
    "/tenants/{tenant_id}/openapi/v1/hotels",
    response_model=list[HotelOut],
    tags=["openapi-read"],
)
async def openapi_read_hotels(
    app: OpenApiApp = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> list[Hotel]:
    """M18：第三方读取门店列表。"""
    result = await session.execute(select(Hotel).where(Hotel.tenant_id == app.tenant_id))
    return list(result.scalars())


@router.get(
    "/tenants/{tenant_id}/openapi/v1/hotels/{hotel_id}/rooms",
    response_model=list[RoomOut],
    tags=["openapi-read"],
)
async def openapi_read_rooms(
    hotel_id: int,
    paging: tuple[int, int] = Depends(Paged),
    app: OpenApiApp = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> list[Room]:
    """M18：第三方读取某门店房间与房态（M32 性能护栏：Paged limit/offset）。"""
    limit, offset = paging
    hotel = await session.get(Hotel, hotel_id)
    if not hotel or hotel.tenant_id != app.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "门店不存在")
    result = await session.execute(
        select(Room)
        .where(Room.hotel_id == hotel_id)
        .order_by(Room.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())


@router.get(
    "/tenants/{tenant_id}/openapi/v1/availability",
    tags=["openapi-read"],
)
async def openapi_read_availability(
    room_type_id: int,
    date: str = "2026-09-20",
    app: OpenApiApp = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """M18：第三方读取房型某日可售房量（复用 PriceService.availability）。"""
    rt = await session.get(RoomType, room_type_id)
    if not rt or rt.tenant_id != app.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "房型不存在")
    ps = PriceService(session)
    try:
        return await ps.availability(app.tenant_id, room_type_id, date)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get(
    "/tenants/{tenant_id}/openapi/v1/bookings",
    response_model=list[BookingOut],
    tags=["openapi-read"],
)
async def openapi_read_bookings(
    status_: str | None = None,
    paging: tuple[int, int] = Depends(Paged),
    app: OpenApiApp = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> list[Booking]:
    """M18：第三方读取预订列表（可按状态过滤 + M32 性能护栏：Paged limit/offset）。"""
    limit, offset = paging
    stmt = select(Booking).where(Booking.tenant_id == app.tenant_id)
    if status_:
        stmt = stmt.where(Booking.status == status_)
    stmt = stmt.order_by(Booking.id.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars())


@router.get(
    "/tenants/{tenant_id}/openapi/v1/night-audit/board",
    response_model=NightAuditBoardOut,
    tags=["openapi-read"],
)
async def openapi_read_night_audit_board(
    app: OpenApiApp = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """M18：第三方读取跨店夜审看板（只读聚合）。"""
    return await NightAuditService(session).night_audit_board(app.tenant_id)


# ---------- M15 收益管理：简版调价建议 ----------


@router.get(
    "/tenants/{tenant_id}/yield/rules",
    response_model=PricingRuleOut,
)
async def get_yield_rule(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
) -> PricingRule:
    """M15：获取租户当前启用的调价规则（无则返回默认规则）。"""
    svc = YieldService(session)
    rule = await svc.get_or_default_rule(tenant_id)
    await session.commit()
    return rule


@router.put(
    "/tenants/{tenant_id}/yield/rules",
    response_model=PricingRuleOut,
)
async def update_yield_rule(
    tenant_id: str,
    payload: PricingRuleIn,
    session: AsyncSession = Depends(get_session),
) -> PricingRule:
    """M15：更新调价规则（禁用旧规则、写入新规则）。"""
    fields = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    svc = YieldService(session)
    rule = await svc.set_rule(tenant_id, **fields)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.post(
    "/tenants/{tenant_id}/yield/pricing/recommend",
    response_model=PriceRecommendOut,
    status_code=status.HTTP_201_CREATED,
)
async def recommend_price(
    tenant_id: str,
    payload: PriceRecommendIn,
    session: AsyncSession = Depends(get_session),
) -> PriceRecommendation:
    """M15：生成调价建议并落库（需求指数 + 周末因子 + 竞品对标）。"""
    svc = YieldService(session)
    rec = await svc.recommend(
        tenant_id=tenant_id,
        hotel_id=payload.hotel_id,
        business_date=payload.business_date,
        base_price_cents=payload.base_price_cents,
        room_type_id=payload.room_type_id,
        competitor_price_cents=payload.competitor_price_cents,
        lead_time_days=payload.lead_time_days,
    )
    await session.commit()
    await session.refresh(rec)
    return rec


@router.get(
    "/tenants/{tenant_id}/yield/pricing/recommendations",
    response_model=list[PriceRecommendationOut],
)
async def list_yield_recommendations(
    tenant_id: str,
    hotel_id: int | None = None,
    business_date: str | None = None,
    paging: tuple[int, int] = Depends(Paged),
    session: AsyncSession = Depends(get_session),
) -> list[PriceRecommendation]:
    """M15：查询调价建议快照（按门店/营业日过滤 + M32 性能护栏：Paged limit/offset）。"""
    limit, offset = paging
    svc = YieldService(session)
    return await svc.list_recommendations(
        tenant_id, hotel_id, business_date, limit=limit, offset=offset
    )


@router.post(
    "/tenants/{tenant_id}/yield/pricing/recommendations/{rec_id}/apply",
    response_model=YieldApplyOut,
    dependencies=[Security(require_perm, scopes=[PRICE_EDIT])],
)
async def apply_yield_recommendation(
    tenant_id: str,
    rec_id: int,
    body: YieldApplyIn | None = None,
    session: AsyncSession = Depends(get_session),
) -> YieldApplyOut:
    """M20：建议一键应用到价格日历（受集团价策约束，改价留痕）。

    body 可选：传 ``{"start": "...", "end": "..."}`` 则区间逐日落价，否则仅建议日单日。
    """
    svc = YieldService(session)
    try:
        rec, updated, dates = await svc.apply_recommendation(
            tenant_id, rec_id, start=body.start if body else None, end=body.end if body else None
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "not_found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "建议不存在") from exc
        if msg == "no_room_type":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "建议未指定房型，无法落到价格日历"
            ) from exc
        if msg in ("bad_range", "range_too_long"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "日期区间无效：需 start<=end 且格式为 YYYY-MM-DD"
                if msg == "bad_range"
                else f"区间过长：单次最多 {YieldService.MAX_APPLY_DAYS} 天",
            ) from exc
        if msg.startswith("already_"):
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"建议已被处理（{msg.removeprefix('already_')}）"
            ) from exc
        # 其余为集团价策越界
        await session.commit()  # 落拦截记录
        raise HTTPException(status.HTTP_403_FORBIDDEN, msg) from exc

    await audit_record(
        session,
        tenant_id,
        "price.edit",
        actor="yield_apply",
        resource_type="price_calendar",
        resource_id=rec.id,
        detail={
            "source": "yield_recommendation",
            "rec_id": rec.id,
            "room_type_id": rec.room_type_id,
            "dates": dates,
            "price": rec.recommended_price_cents,
            "updated": updated,
            "created": len(dates) - updated,
        },
    )
    await session.commit()
    return YieldApplyOut(
        rec_id=rec.id,
        status=rec.status,
        room_type_id=rec.room_type_id,
        business_date=rec.business_date,
        price=rec.recommended_price_cents,
        dates=dates,
        updated=updated,
        created=len(dates) - updated,
    )


@router.post(
    "/tenants/{tenant_id}/yield/pricing/recommendations/{rec_id}/reject",
    response_model=PriceRecommendOut,
    dependencies=[Security(require_perm, scopes=[PRICE_EDIT])],
)
async def reject_yield_recommendation(
    tenant_id: str,
    rec_id: int,
    session: AsyncSession = Depends(get_session),
) -> PriceRecommendation:
    """M20：拒绝建议（审核语义：suggested → rejected）。"""
    svc = YieldService(session)
    try:
        rec = await svc.reject_recommendation(tenant_id, rec_id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "not_found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "建议不存在") from exc
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"建议已被处理（{msg.removeprefix('already_')}）"
        ) from exc
    await session.commit()
    await session.refresh(rec)
    return rec


# ---------- M21 餐饮 POS（F&B） ----------
@router.post(
    "/tenants/{tenant_id}/fnb/menu-items",
    response_model=MenuItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def create_menu_item(
    tenant_id: str,
    body: MenuItemIn,
    session: AsyncSession = Depends(get_session),
) -> MenuItem:
    """新增菜品。"""
    svc = PosService(session)
    item = await svc.create_menu_item(
        tenant_id,
        body.hotel_id,
        body.name,
        body.category,
        body.price_cents,
        body.is_active,
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.get(
    "/tenants/{tenant_id}/fnb/menu-items",
    response_model=list[MenuItemOut],
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def list_menu_items(
    tenant_id: str,
    hotel_id: int,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
) -> list[MenuItem]:
    """菜品列表（默认仅上架）。"""
    return await PosService(session).list_menu_items(
        tenant_id, hotel_id, active_only=active_only
    )


@router.patch(
    "/tenants/{tenant_id}/fnb/menu-items/{item_id}",
    response_model=MenuItemOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def update_menu_item(
    tenant_id: str,
    item_id: int,
    body: MenuItemPatch,
    session: AsyncSession = Depends(get_session),
) -> MenuItem:
    """更新菜品（含上下架），仅写入显式提供的字段。"""
    svc = PosService(session)
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    item = await svc.update_menu_item(item_id, **fields)
    await session.commit()
    await session.refresh(item)
    return item


# ---------- M27 餐饮运营：沽清 / 退菜 / 整单折扣 ----------


@router.post(
    "/tenants/{tenant_id}/fnb/menu-items/{item_id}/sold-out",
    response_model=MenuItemOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def set_menu_item_sold_out(
    tenant_id: str,
    item_id: int,
    body: FnbSoldOutIn,
    session: AsyncSession = Depends(get_session),
) -> MenuItem:
    """沽清 / 恢复供应（M27）：当日售罄标记，拒点但不影响上架状态。"""
    try:
        item = await PosService(session).set_menu_sold_out(
            tenant_id, item_id, body.sold_out, body.operator
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return item


@router.post(
    "/tenants/{tenant_id}/fnb/orders/{order_id}/items/{item_id}/void",
    response_model=PosOrderOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def void_pos_order_item(
    tenant_id: str,
    order_id: int,
    item_id: int,
    body: FnbVoidIn,
    session: AsyncSession = Depends(get_session),
) -> PosOrder:
    """退菜（M27）：仅未结算账单，明细置 voided 并扣减总额。"""
    try:
        await PosService(session).void_order_item(
            order_id, item_id, reason=body.reason, operator=body.operator
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    order = await session.get(PosOrder, order_id)
    items = await _load_order_items(session, order_id)
    return _order_out(order, items)


@router.post(
    "/tenants/{tenant_id}/fnb/orders/{order_id}/discount",
    response_model=PosOrderOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def apply_pos_order_discount(
    tenant_id: str,
    order_id: int,
    body: FnbDiscountIn,
    session: AsyncSession = Depends(get_session),
) -> PosOrder:
    """整单折扣（M27）：按金额（分）或百分比（1-99）二选一。"""
    try:
        await PosService(session).apply_order_discount(
            order_id,
            discount_cents=body.discount_cents,
            percent=body.percent,
            operator=body.operator,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    order = await session.get(PosOrder, order_id)
    items = await _load_order_items(session, order_id)
    return _order_out(order, items)


@router.post(
    "/tenants/{tenant_id}/fnb/tables",
    response_model=DiningTableOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def create_table(
    tenant_id: str,
    body: DiningTableIn,
    session: AsyncSession = Depends(get_session),
) -> DiningTable:
    """新增餐桌。"""
    svc = PosService(session)
    table = await svc.create_table(
        tenant_id, body.hotel_id, body.table_no, body.seats, body.zone
    )
    await session.commit()
    await session.refresh(table)
    return table


@router.get(
    "/tenants/{tenant_id}/fnb/tables",
    response_model=list[DiningTableOut],
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def list_tables(
    tenant_id: str,
    hotel_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[DiningTable]:
    """餐桌列表。"""
    return await PosService(session).list_tables(tenant_id, hotel_id)


@router.patch(
    "/tenants/{tenant_id}/fnb/tables/{table_id}/state",
    response_model=DiningTableOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def set_table_state(
    tenant_id: str,
    table_id: int,
    state: str,
    session: AsyncSession = Depends(get_session),
) -> DiningTable:
    """更新餐桌状态（free|occupied|cleaning）。"""
    svc = PosService(session)
    try:
        table = await svc.set_table_state(table_id, state)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(table)
    return table


@router.post(
    "/tenants/{tenant_id}/fnb/orders",
    response_model=PosOrderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def open_pos_order(
    tenant_id: str,
    body: PosOrderOpenIn,
    session: AsyncSession = Depends(get_session),
) -> PosOrder:
    """开餐饮账单（可选关联餐桌/客房）。"""
    svc = PosService(session)
    order = await svc.open_order(
        tenant_id,
        body.hotel_id,
        table_id=body.table_id,
        room_no=body.room_no,
        guest_name=body.guest_name,
        booking_id=body.booking_id,
    )
    await session.commit()
    await session.refresh(order)
    return _order_out(order, [])


@router.post(
    "/tenants/{tenant_id}/fnb/orders/{order_id}/items",
    response_model=PosOrderItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def add_pos_order_item(
    tenant_id: str,
    order_id: int,
    body: PosOrderItemIn,
    session: AsyncSession = Depends(get_session),
) -> PosOrderItem:
    """餐饮账单加菜。"""
    svc = PosService(session)
    try:
        line = await svc.add_order_item(
            order_id,
            name=body.name,
            qty=body.qty,
            unit_price_cents=body.unit_price_cents,
            item_id=body.item_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(line)
    return line


@router.post(
    "/tenants/{tenant_id}/fnb/orders/{order_id}/settle-room",
    response_model=PosOrderOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def settle_pos_room(
    tenant_id: str,
    order_id: int,
    body: PosSettleRoomIn,
    session: AsyncSession = Depends(get_session),
) -> PosOrder:
    """挂房账结账（消费计入客房在开账单）。"""
    svc = PosService(session)
    try:
        order = await svc.settle_room(order_id, body.room_no, body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(order)
    items = await _load_order_items(session, order.id)
    return _order_out(order, items)


@router.post(
    "/tenants/{tenant_id}/fnb/orders/{order_id}/settle-cash",
    response_model=PosOrderOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def settle_pos_cash(
    tenant_id: str,
    order_id: int,
    body: PosSettleCashIn,
    session: AsyncSession = Depends(get_session),
) -> PosOrder:
    """现金结账。"""
    svc = PosService(session)
    try:
        order = await svc.settle_cash(order_id, body.amount_paid, body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(order)
    items = await _load_order_items(session, order.id)
    return _order_out(order, items)


@router.get(
    "/tenants/{tenant_id}/fnb/orders",
    response_model=list[PosOrderOut],
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def list_pos_orders(
    tenant_id: str,
    hotel_id: int,
    status: str | None = None,
    limit: int = Query(MAX_LIST_ROWS, le=MAX_LIST_ROWS, ge=1, description="返回行数上限"),
    offset: int = Query(0, ge=0, description="跳过的行数"),
    session: AsyncSession = Depends(get_session),
) -> list[PosOrder]:
    """餐饮账单列表（M30 性能护栏：limit/offset）。"""
    orders = await PosService(session).list_orders(
        tenant_id, hotel_id, status, limit=limit, offset=offset
    )
    out = []
    for o in orders:
        items = await _load_order_items(session, o.id)
        out.append(_order_out(o, items))
    return out


# ---------- M22 餐饮报表 ----------
@router.get(
    "/tenants/{tenant_id}/fnb/reports/sales",
    response_model=FnbReportOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def fnb_report_sales(
    tenant_id: str,
    hotel_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """餐饮销售报表：总营收 / 单数 / 品类销售 / 桌均消费（仅已结账账单）。"""
    return await PosService(session).report_sales(tenant_id, hotel_id, start, end)


# ---------- M22 厨房出单 KDS ----------
@router.get(
    "/tenants/{tenant_id}/fnb/kitchen/tickets",
    response_model=list[KitchenTicketOut],
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def list_kitchen_tickets(
    tenant_id: str,
    hotel_id: int,
    states: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """厨房出单屏：取待做出餐的菜品行（默认 pending|ready）。states 逗号分隔。"""
    state_tuple = tuple(states.split(",")) if states else ("pending", "ready")
    return await PosService(session).list_kitchen_tickets(tenant_id, hotel_id, state_tuple)


@router.post(
    "/tenants/{tenant_id}/fnb/orders/{order_id}/items/{item_id}/ready",
    response_model=PosOrderItemOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def kds_item_ready(
    tenant_id: str,
    order_id: int,
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> PosOrderItem:
    """标记出餐（待做 → 已出餐）。"""
    try:
        item = await PosService(session).mark_item_ready(item_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return item


@router.post(
    "/tenants/{tenant_id}/fnb/orders/{order_id}/items/{item_id}/served",
    response_model=PosOrderItemOut,
    dependencies=[Security(require_perm, scopes=[FNB_MANAGE])],
)
async def kds_item_served(
    tenant_id: str,
    order_id: int,
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> PosOrderItem:
    """标记上菜（已出餐 → 已上菜）。"""
    try:
        item = await PosService(session).mark_item_served(item_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return item


# ---------- M21 餐饮 POS 内部辅助 ----------
async def _load_order_items(session: AsyncSession, order_id: int) -> list:
    from app.models import PosOrderItem

    res = await session.execute(
        select(PosOrderItem).where(PosOrderItem.order_id == order_id)
    )
    return list(res.scalars().all())


def _order_out(order: "PosOrder", items: list) -> PosOrderOut:
    return PosOrderOut(
        id=order.id,
        tenant_id=order.tenant_id,
        hotel_id=order.hotel_id,
        table_id=order.table_id,
        status=order.status,
        settle_type=order.settle_type,
        room_no=order.room_no,
        booking_id=order.booking_id,
        guest_name=order.guest_name,
        total_cents=order.total_cents,
        discount_cents=order.discount_cents or 0,
        items=[
            PosOrderItemOut(
                id=i.id,
                order_id=i.order_id,
                item_id=i.item_id,
                name=i.name,
                category=i.category,
                qty=i.qty,
                unit_price_cents=i.unit_price_cents,
                subtotal_cents=i.subtotal_cents,
                kds_status=i.kds_status,
                voided=i.voided,
                void_reason=i.void_reason,
            )
            for i in items
        ],
    )


# ---------- 内部辅助 ----------


async def _get_bill(tenant_id: str, bill_id: int, session: AsyncSession) -> Bill:
    bill = await session.get(Bill, bill_id)
    if not bill or bill.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账单不存在")
    return bill


async def _bill_with_items(bill: Bill, session: AsyncSession) -> Bill:  # noqa: ARG001
    """账单关联关系加载（M30 性能）。

    原实现无条件 ``session.refresh(bill, ["items", "payments", "adjustments"])``，
    对**每个**账单产生 3 次 SELECT（列表页 N 个账单 = 3N 次，即典型 N+1）。

    M30 优化：会话已配置 ``expire_on_commit=False``，写路径 commit 后属性与
    已加载关系均不失效，无需再次 refresh；调用点（建账/入账/结账/冲销等）
    在本函数前均已完成写入或查询，关系由 ``BillOut`` 序列化时按需读取。
    保留函数签名以兼容 11 处调用点。

    实测：移除后账单相关全量测试通过，且每账单省 3 次 SELECT。
    """
    return bill


def _parse_dt(value: str) -> datetime:
    """解析 ISO 时刻（形如 2026-11-01T07:30 或带秒），统一转 UTC 时区感知。"""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


# ---------- M28：投诉工单（A2 收尾） ----------


@router.post("/tenants/{tenant_id}/complaints", response_model=ComplaintOut, status_code=status.HTTP_201_CREATED)
async def create_complaint(
    tenant_id: str,
    body: ComplaintCreate,
    session: AsyncSession = Depends(get_session),
) -> Complaint:
    """创建投诉工单：可关联预订自动回填住客/房号/手机号。"""
    svc = ComplaintService(session)
    try:
        c = await svc.create(
            tenant_id,
            hotel_id=body.hotel_id,
            guest_name=body.guest_name,
            description=body.description,
            booking_id=body.booking_id,
            guest_phone=body.guest_phone,
            room_no=body.room_no,
            source=body.source,
            category=body.category,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(c)
    return c


@router.get("/tenants/{tenant_id}/complaints", response_model=list[ComplaintOut])
async def list_complaints(
    tenant_id: str,
    hotel_id: int | None = None,
    status_: str | None = None,
    booking_id: int | None = None,
    guest_phone: str | None = None,
    guest_name: str | None = None,
    limit: int = Query(MAX_LIST_ROWS, le=MAX_LIST_ROWS, ge=1, description="返回行数上限"),
    offset: int = Query(0, ge=0, description="跳过的行数"),
    session: AsyncSession = Depends(get_session),
) -> list[Complaint]:
    """投诉列表：按状态 / 门店 / 预订 / 住客手机号 / 姓名模糊过滤 + M30 性能护栏（limit/offset）。"""
    return await ComplaintService(session).list(
        tenant_id,
        hotel_id=hotel_id,
        status=status_,
        booking_id=booking_id,
        guest_phone=guest_phone,
        guest_name=guest_name,
        limit=limit,
        offset=offset,
    )


@router.post("/tenants/{tenant_id}/complaints/{complaint_id}/transition", response_model=ComplaintOut)
async def transition_complaint(
    tenant_id: str,
    complaint_id: int,
    body: ComplaintTransitionIn,
    session: AsyncSession = Depends(get_session),
) -> Complaint:
    """投诉流转：OPEN→HANDLING（受理）→RESOLVED（办结）/ CANCELLED。"""
    svc = ComplaintService(session)
    try:
        c = await svc.transition(
            complaint_id,
            to_status=body.to_status,
            operator=body.operator,
            handler=body.handler,
            resolution=body.resolution,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(c)
    return c


# ---------- M28：历史数据留存导出（A2 收尾） ----------


@router.get("/tenants/{tenant_id}/analytics/data-export")
async def analytics_data_export(
    tenant_id: str,
    entity: str,
    start_date: str | None = None,
    end_date: str | None = None,
    login_session: LoginSession = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """留存导出（CSV，UTF-8 BOM 兼容 Excel）：entity=bookings|bills|fnb_orders。

    逐批（500 行/批）流式输出，内存占用与批量大小一致；导出动作写审计。
    """
    svc = AnalyticsService(session)
    if entity not in svc.EXPORT_HEADERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的导出实体：{entity}")

    async def _rows():
        headers = svc.EXPORT_HEADERS[entity]
        yield "\ufeff" + ",".join(headers) + "\r\n"
        import csv as _csv
        import io as _io

        async for headers_, row in svc.export_rows(tenant_id, entity, start_date, end_date):
            buf = _io.StringIO()
            writer = _csv.writer(buf)
            writer.writerow([v if v is not None else "" for v in row])
            yield buf.getvalue()

    await audit_service_record(
        session,
        tenant_id,
        "data.export",
        actor="admin" if login_session is None else f"user:{login_session.user_id}",
        resource_type=f"export:{entity}",
        detail={"start_date": start_date, "end_date": end_date},
    )
    await session.commit()
    filename = f"{tenant_id}_{entity}_{start_date or 'all'}_{end_date or 'all'}.csv"
    return StreamingResponse(
        _rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- M29：OTA 渠道直连（A5） ----------


@router.get("/tenants/{tenant_id}/ota/configs", response_model=list[OtaConfigOut])
async def list_ota_configs(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[OtaChannelConfig]:
    """OTA 渠道配置列表（secret 不回显）。"""
    return await OtaService(session).list_configs(tenant_id)


@router.put("/tenants/{tenant_id}/ota/configs", response_model=OtaConfigOut)
async def upsert_ota_config(
    tenant_id: str,
    body: OtaConfigIn,
    session: AsyncSession = Depends(get_session),
) -> OtaChannelConfig:
    """新增/更新渠道接入配置（每租户每渠道一条，覆盖式）。"""
    svc = OtaService(session)
    try:
        cfg = await svc.upsert_config(
            tenant_id,
            hotel_id=body.hotel_id,
            channel=body.channel,
            secret=body.secret,
            app_key=body.app_key,
            push_enabled=body.push_enabled,
            push_inventory_url=body.push_inventory_url,
        )
    except OtaError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(cfg)
    return cfg


@router.post("/tenants/{tenant_id}/ota/{channel}/webhook/orders", response_model=OtaOrderInjectOut)
async def ota_webhook_order(
    tenant_id: str,
    channel: str,
    request: Request,
    x_ota_sign: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """OTA 订单 webhook（公网端点，HMAC 签名鉴权）。

    三级防重：签名校验 → external_ref 幂等 → 预订引擎房量守卫。
    """
    raw = await request.body()
    svc = OtaService(session)
    try:
        booking, created = await svc.inject_order(
            tenant_id,
            channel,
            json.loads(raw) if raw else {},
            raw_body=raw,
            signature=x_ota_sign,
        )
    except OtaError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return {
        "booking_id": booking.id,
        "external_ref": booking.external_ref,
        "channel": channel,
        "status": booking.status,
        "created": created,
    }


@router.post("/tenants/{tenant_id}/ota/{channel}/inventory/push")
async def ota_push_inventory(
    tenant_id: str,
    channel: str,
    days: int = 7,
    dry_run: bool = False,
    session: AsyncSession = Depends(get_session),
    _user: User = Security(require_perm, scopes=[OTA_MANAGE]),
) -> dict:
    """按房型×日期推送未来 N 天剩余房量（沙箱渠道返回确定性回执）。

    - dry_run=True 时不写审计、仅组装 payload 并落 DRY_RUN 状态日志；
    - 启用 ChannelRoomMapping 后，items 改用外部房型码。
    """
    svc = OtaService(session)
    try:
        ack = await svc.push_inventory(
            tenant_id, channel, days=days, dry_run=dry_run
        )
    except OtaError as exc:
        # 即便业务失败也保留推送日志（status=FAILED）以便前台排查
        try:
            await session.commit()
        except Exception:
            pass
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return ack


@router.post(
    "/tenants/{tenant_id}/ota/{channel}/rates/push",
    dependencies=[Security(require_perm, scopes=[OTA_MANAGE, RATE_EDIT])],
)
async def ota_push_rates(
    tenant_id: str,
    channel: str,
    dry_run: bool = False,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """按房型推送渠道价（M29，A6）。

    价格解析优先级：当日渠道价 → 永久默认渠道价 → None（前端可回退展示 PMS base_price）。
    """
    svc = OtaService(session)
    try:
        ack = await svc.push_rates(tenant_id, channel, dry_run=dry_run)
    except OtaError as exc:
        try:
            await session.commit()
        except Exception:
            pass
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return ack


# ---------- M29：房型映射 / 渠道价 / 推送日志（A6） ----------


@router.get(
    "/tenants/{tenant_id}/ota/mappings",
    response_model=list[ChannelRoomMappingOut],
)
async def list_channel_mappings(
    tenant_id: str,
    hotel_id: int | None = None,
    channel: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ChannelRoomMapping]:
    """OTA 房型映射列表（按渠道/酒店过滤）。"""
    return await OtaMappingService(session).list_mappings(
        tenant_id, hotel_id=hotel_id, channel=channel
    )


@router.post(
    "/tenants/{tenant_id}/ota/mappings",
    response_model=ChannelRoomMappingOut,
    dependencies=[Security(require_perm, scopes=[OTA_MANAGE])],
)
async def upsert_channel_mapping(
    tenant_id: str,
    body: ChannelRoomMappingIn,
    session: AsyncSession = Depends(get_session),
) -> ChannelRoomMapping:
    """新增/更新房型映射（每渠道每酒店每 PMS 房型唯一）。"""
    svc = OtaMappingService(session)
    try:
        row = await svc.upsert(
            tenant_id,
            hotel_id=body.hotel_id,
            channel=body.channel,
            pms_room_type_id=body.pms_room_type_id,
            external_room_type_code=body.external_room_type_code,
            enabled=body.enabled,
        )
    except OtaMappingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(row)
    return row


@router.delete(
    "/tenants/{tenant_id}/ota/mappings/{mapping_id}",
    dependencies=[Security(require_perm, scopes=[OTA_MANAGE])],
)
async def delete_channel_mapping(
    tenant_id: str,
    mapping_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除房型映射。"""
    ok = await OtaMappingService(session).delete(tenant_id, mapping_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "房型映射不存在")
    await session.commit()
    return {"deleted": True, "id": mapping_id}


@router.get(
    "/tenants/{tenant_id}/ota/rate-plans",
    response_model=list[ChannelRatePlanOut],
)
async def list_channel_rate_plans(
    tenant_id: str,
    hotel_id: int | None = None,
    channel: str | None = None,
    pms_room_type_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ChannelRatePlan]:
    """渠道价列表（按渠道/酒店/房型过滤）。"""
    return await OtaRatePlanService(session).list_plans(
        tenant_id,
        hotel_id=hotel_id,
        channel=channel,
        pms_room_type_id=pms_room_type_id,
    )


@router.post(
    "/tenants/{tenant_id}/ota/rate-plans",
    response_model=ChannelRatePlanOut,
    dependencies=[Security(require_perm, scopes=[RATE_EDIT])],
)
async def upsert_channel_rate_plan(
    tenant_id: str,
    body: ChannelRatePlanIn,
    session: AsyncSession = Depends(get_session),
) -> ChannelRatePlan:
    """新增/更新渠道价（每渠道每酒店每房型每生效日唯一）。"""
    from datetime import date as _date

    eff = _date.fromisoformat(body.effective_date) if body.effective_date else None
    svc = OtaRatePlanService(session)
    try:
        row = await svc.upsert(
            tenant_id,
            hotel_id=body.hotel_id,
            channel=body.channel,
            pms_room_type_id=body.pms_room_type_id,
            effective_date=eff,
            price_cents=body.price_cents,
            enabled=body.enabled,
        )
    except OtaRatePlanError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(row)
    return row


@router.delete(
    "/tenants/{tenant_id}/ota/rate-plans/{plan_id}",
    dependencies=[Security(require_perm, scopes=[RATE_EDIT])],
)
async def delete_channel_rate_plan(
    tenant_id: str,
    plan_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除渠道价。"""
    ok = await OtaRatePlanService(session).delete(tenant_id, plan_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "渠道价不存在")
    await session.commit()
    return {"deleted": True, "id": plan_id}


@router.get(
    "/tenants/{tenant_id}/ota/push-logs",
    response_model=list[ChannelPushLogOut],
)
async def list_push_logs(
    tenant_id: str,
    hotel_id: int | None = None,
    channel: str | None = None,
    status: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[ChannelPushLog]:
    """推送日志列表（按创建时间倒序，limit 上限 200）。"""
    return await OtaService(session).list_push_logs(
        tenant_id,
        hotel_id=hotel_id,
        channel=channel,
        status=status,
        limit=limit,
    )


# ---------- M31：核心缺口关闭（验收 #9 / #10 / #34） ----------


@router.post("/tenants/{tenant_id}/bills/{bill_id}/pay-points")
async def pay_bill_with_points(
    tenant_id: str,
    bill_id: str,
    body: PointsPayIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """会员积分抵扣支付（1 积分 = 1 分）：扣减积分 + 落 POINTS 收款流水。"""
    bill = await session.get(Bill, int(bill_id))
    if not bill or bill.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账单不存在")
    cs = CashierService(session)
    try:
        pay, member = await cs.pay_with_points(
            bill, body.member_phone, body.points, operator=body.operator
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return {
        "payment_id": pay.id,
        "amount_cents": pay.amount,
        "points_used": body.points,
        "member_points_left": member.points,
        "bill_balance": bill.balance,
    }


@router.post(
    "/tenants/{tenant_id}/group-blocks/{block_id}/allocations/{alloc_id}/settle"
)
async def settle_group_allocation(
    tenant_id: str,
    block_id: int,
    alloc_id: int,
    body: GroupAllocationSettleIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """团队逐间分批结账：结清该间账单（余额自动现金补收）并退房释放。"""
    svc = GroupBlockService(session)
    block = await svc.get_block(tenant_id, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队排房不存在")
    try:
        row = await svc.settle_allocation(block, alloc_id, operator=body.operator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return row


@router.get("/tenants/{tenant_id}/group-blocks/{block_id}/settlement")
async def group_block_settlement(
    tenant_id: str,
    block_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """团主结算汇总：逐间账单状态与整团进度（已结/未结/金额）。"""
    svc = GroupBlockService(session)
    block = await svc.get_block(tenant_id, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队排房不存在")
    return await svc.settlement(block)


@router.post("/tenants/{tenant_id}/rooms/{room_no}/dnd", response_model=RoomOut)
async def set_room_dnd(
    tenant_id: str,
    room_no: str,
    body: RoomDndIn,
    session: AsyncSession = Depends(get_session),
) -> Room:
    """免打扰开关（M31，验收 #34）：不影响可售状态，清扫派单守卫使用。"""
    room = (
        await session.execute(
            select(Room).where(Room.tenant_id == tenant_id, Room.room_no == room_no)
        )
    ).scalars().first()
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "房间不存在")
    # M32.1：免打扰仅限在住状态设置（关闭随时可操作）
    if body.dnd and room.state != "occupied":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"免打扰仅限在住房间设置，当前房态：{room.state}",
        )
    room.dnd = 1 if body.dnd else 0
    session.add(room)
    # DND 展示在房态图上，必须失效房态热点缓存（与房态变更同口径）
    try:
        from app.infra.cache import get_cache  # noqa: PLC0415

        await get_cache().invalidate_prefix(f"rooms:{tenant_id}")
    except Exception:  # noqa: BLE001
        pass
    await audit_service_record(
        session,
        tenant_id,
        "room.dnd",
        actor=body.operator,
        resource_type="room",
        resource_id=room.id,
        hotel_id=room.hotel_id,
        detail={"room_no": room_no, "dnd": bool(room.dnd)},
    )
    await session.commit()
    await session.refresh(room)
    return room


# ---------- M32：P1 四项 ----------


@router.get("/tenants/{tenant_id}/fnb/room-lookup", response_model=RoomLookupOut)
async def fnb_room_lookup(
    tenant_id: str,
    room_no: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """挂账前房号查询（验收 #48）：展示在住客人姓名/脱敏手机号/离店日期与账单余额，防挂错。"""
    return await PosService(session).room_lookup(tenant_id, room_no)


@router.post("/tenants/{tenant_id}/housekeeping-tasks/{task_id}/inspect")
async def inspect_housekeeping_task(
    tenant_id: str,
    task_id: int,
    body: HkInspectIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """主管检查（验收 #38/#39）：通过 → 净房可售并记录完成时间；不通过 → 退回返工。"""
    task = await session.get(HousekeepingTask, task_id)
    if task is None or task.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "工单不存在")
    svc = HousekeepingService(session)
    try:
        task = await svc.inspect(task, body.passed, operator=body.operator, note=body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(task)
    return {
        "id": task.id,
        "room_no": task.room_no,
        "status": task.status,
        "done_at": task.done_at.isoformat() if task.done_at else None,
        "note": task.note,
    }


@router.post("/tenants/{tenant_id}/analytics/snapshots/generate", response_model=SnapshotOut)
async def generate_report_snapshot(
    tenant_id: str,
    body: SnapshotGenerateIn,
    login_session: LoginSession = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> ReportSnapshot:
    """手动生成周报/月报快照（复用 dashboard 聚合，同周期幂等覆盖）。"""
    try:
        snap = await AnalyticsService(session).generate_snapshot(
            tenant_id, body.hotel_id, body.period_type, body.start_date, body.end_date, source="MANUAL"
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return snap


@router.get("/tenants/{tenant_id}/analytics/snapshots", response_model=list[SnapshotOut])
async def list_report_snapshots(
    tenant_id: str,
    hotel_id: int,
    period_type: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[ReportSnapshot]:
    """周报/月报快照列表（夜审周期切换自动生成 + 手动）。"""
    return await AnalyticsService(session).list_snapshots(tenant_id, hotel_id, period_type, limit)


# =================================================================== M32.18 押金 8 API


def _deposit_to_out(d: "Deposit", txns: list | None = None) -> DepositOut:
    """ORM → Pydantic 转换（含 transactions 列表）。"""
    return DepositOut(
        id=str(d.id),
        tenant_id=d.tenant_id,
        hotel_id=str(d.hotel_id),
        deposit_no=d.deposit_no,
        booking_id=str(d.booking_id) if d.booking_id is not None else None,
        room_no=d.room_no,
        bill_id=str(d.bill_id) if d.bill_id is not None else None,
        kind=d.kind,
        method=d.method,
        amount_cents=d.amount_cents,
        applied_cents=d.applied_cents or 0,
        refunded_cents=d.refunded_cents or 0,
        forfeited_cents=d.forfeited_cents or 0,
        available_cents=d.available_cents or 0,
        status=d.status,
        release_cause=d.release_cause,
        currency=d.currency or "CNY",
        ref_no=d.ref_no,
        operator=d.operator or "front_desk",
        expires_at=d.expires_at,
        released_at=d.released_at,
        captured_at=d.captured_at,
        voided_at=d.voided_at,
        version=d.version or 0,
        note=d.note,
        created_at=d.created_at,
        transactions=[DepositTransactionOut.model_validate(t) for t in (txns or [])],
    )


def _to_deposit_http_error(exc: DepositError) -> HTTPException:
    """DepositError → HTTP 409 业务错误（保持与既有 409 风格一致）。"""
    return HTTPException(status.HTTP_409_CONFLICT, f"{exc.code}: {exc.message}")


@router.post(
    "/tenants/{tenant_id}/deposits",
    response_model=DepositOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[DEPOSIT_MANAGE])],
)
async def deposit_create(
    tenant_id: str,
    body: DepositIn,
    session: AsyncSession = Depends(get_session),
) -> DepositOut:
    """收实收押金 / 冻结预授权。**不**触碰 Bill.balance，**不**写 Payment。"""
    svc = DepositService(session)
    try:
        d = await svc.create(
            tenant_id=tenant_id,
            hotel_id=body.hotel_id,
            kind=body.kind,
            method=body.method,
            amount_cents=body.amount,
            booking_id=body.booking_id,
            room_no=body.room_no,
            bill_id=body.bill_id,
            ref_no=body.ref_no,
            currency=body.currency,
            operator=body.operator,
            note=body.note,
        )
    except DepositError as exc:
        raise _to_deposit_http_error(exc)
    await session.commit()
    await session.refresh(d)
    return _deposit_to_out(d)


@router.get(
    "/tenants/{tenant_id}/deposits",
    response_model=list[DepositOut],
    dependencies=[Security(require_perm, scopes=[DEPOSIT_MANAGE])],
)
async def deposit_list(
    tenant_id: str,
    hotel_id: int | None = None,
    booking_id: int | None = None,
    room_no: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[DepositOut]:
    """列表。limit 默认 50、上限 200（service 内部限）。

    查询参数名 ``status`` 与其余列表端点（订单/账单/预授权等）保持一致；
    前端 ``listDeposits()`` 亦以 ``params.status`` 传参，改名会静默失效。
    """
    svc = DepositService(session)
    rows = await svc.list(
        tenant_id=tenant_id,
        hotel_id=hotel_id,
        booking_id=booking_id,
        room_no=room_no,
        status=status,
        kind=kind,
        limit=limit,
    )
    return [_deposit_to_out(d) for d in rows]


@router.get(
    "/tenants/{tenant_id}/deposits/{deposit_id}",
    response_model=DepositOut,
    dependencies=[Security(require_perm, scopes=[DEPOSIT_MANAGE])],
)
async def deposit_get(
    tenant_id: str,
    deposit_id: int,
    session: AsyncSession = Depends(get_session),
) -> DepositOut:
    """详情 + 流水。"""
    svc = DepositService(session)
    try:
        d, txns = await svc.get_with_transactions(tenant_id, deposit_id)
    except DepositError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.message)
    return _deposit_to_out(d, txns)


@router.post(
    "/tenants/{tenant_id}/deposits/{deposit_id}/apply",
    response_model=DepositOut,
    dependencies=[Security(require_perm, scopes=[DEPOSIT_MANAGE])],
)
async def deposit_apply(
    tenant_id: str,
    deposit_id: int,
    body: DepositApplyIn,
    session: AsyncSession = Depends(get_session),
) -> DepositOut:
    """冲抵：写 Payment(method=DEPOSIT) + Bill.balance -= amount。**不**写 BillItem。"""
    svc = DepositService(session)
    try:
        d = await svc.apply(
            tenant_id=tenant_id,
            deposit_id=deposit_id,
            amount_cents=body.amount,
            target_bill_id=body.target_bill_id,
            operator=body.operator,
            expected_version=body.expected_version,
        )
    except DepositError as exc:
        raise _to_deposit_http_error(exc)
    await session.commit()
    await session.refresh(d)
    # 重新拉取带关联（如需要）
    return _deposit_to_out(d)


@router.post(
    "/tenants/{tenant_id}/deposits/{deposit_id}/refund",
    response_model=DepositOut,
    dependencies=[Security(require_perm, scopes=[DEPOSIT_REFUND])],
)
async def deposit_refund(
    tenant_id: str,
    deposit_id: int,
    body: DepositRefundIn,
    session: AsyncSession = Depends(get_session),
) -> DepositOut:
    """原路退还。**不**写 Payment、**不**动 Bill.balance。强制审计留痕。"""
    svc = DepositService(session)
    try:
        d = await svc.refund(
            tenant_id=tenant_id,
            deposit_id=deposit_id,
            amount_cents=body.amount,
            operator=body.operator,
            note=body.note,
            expected_version=body.expected_version,
        )
    except DepositError as exc:
        raise _to_deposit_http_error(exc)
    await session.commit()
    await session.refresh(d)
    return _deposit_to_out(d)


@router.post(
    "/tenants/{tenant_id}/deposits/{deposit_id}/release",
    response_model=DepositOut,
    dependencies=[Security(require_perm, scopes=[DEPOSIT_MANAGE])],
)
async def deposit_release(
    tenant_id: str,
    deposit_id: int,
    body: DepositReleaseIn,
    session: AsyncSession = Depends(get_session),
) -> DepositOut:
    """预授权释放。仅 PREAUTH + applied==0。"""
    svc = DepositService(session)
    try:
        d = await svc.release(
            tenant_id=tenant_id,
            deposit_id=deposit_id,
            operator=body.operator,
            cause=body.cause,
            expected_version=body.expected_version,
        )
    except DepositError as exc:
        raise _to_deposit_http_error(exc)
    await session.commit()
    await session.refresh(d)
    return _deposit_to_out(d)


@router.post(
    "/tenants/{tenant_id}/deposits/{deposit_id}/capture",
    response_model=DepositOut,
    dependencies=[Security(require_perm, scopes=[DEPOSIT_MANAGE])],
)
async def deposit_capture(
    tenant_id: str,
    deposit_id: int,
    body: DepositCaptureIn,
    session: AsyncSession = Depends(get_session),
) -> DepositOut:
    """预授权请款（AUTHORIZED → CAPTURED）。仅转实收额度，**不**写 Payment / 不动 Bill.balance。

    请款后该笔预授权等同 HELD，可再调 ``/apply`` 冲抵账单（那一步才计营收）。
    ``amount`` 缺省表示全额请款；部分请款时未请款部分放弃冻结。
    """
    svc = DepositService(session)
    try:
        d = await svc.capture(
            tenant_id=tenant_id,
            deposit_id=deposit_id,
            amount_cents=body.amount,
            operator=body.operator,
            expected_version=body.expected_version,
        )
    except DepositError as exc:
        raise _to_deposit_http_error(exc)
    await session.commit()
    await session.refresh(d)
    return _deposit_to_out(d)


@router.post(
    "/tenants/{tenant_id}/deposits/{deposit_id}/void",
    response_model=DepositOut,
    dependencies=[Security(require_perm, scopes=[DEPOSIT_MANAGE])],
)
async def deposit_void(
    tenant_id: str,
    deposit_id: int,
    body: DepositVoidIn,
    session: AsyncSession = Depends(get_session),
) -> DepositOut:
    """作废（24h 内、applied==0）。仅 DEPOSIT。"""
    svc = DepositService(session)
    try:
        d = await svc.void(
            tenant_id=tenant_id,
            deposit_id=deposit_id,
            operator=body.operator,
            reason=body.reason,
            expected_version=body.expected_version,
        )
    except DepositError as exc:
        raise _to_deposit_http_error(exc)
    await session.commit()
    await session.refresh(d)
    return _deposit_to_out(d)


@router.post(
    "/tenants/{tenant_id}/deposits/auto-release",
    response_model=AutoReleaseOut,
    dependencies=[Security(require_perm, scopes=[NIGHT_AUDIT_RUN])],
)
async def deposit_auto_release(
    tenant_id: str,
    body: AutoReleaseIn,
    session: AsyncSession = Depends(get_session),
) -> AutoReleaseOut:
    """超期预授权批量释放。供夜审钩子与外部 cron 共用。"""
    svc = DepositService(session)
    result = await svc.auto_release_expired(
        tenant_id=tenant_id,
        hotel_id=body.hotel_id,
        days=body.days,
        operator=body.operator,
    )
    await session.commit()
    return AutoReleaseOut(**result)


@router.get(
    "/tenants/{tenant_id}/bookings/{booking_id}/deposits",
    response_model=list[DepositOut],
    dependencies=[Security(require_perm, scopes=[DEPOSIT_MANAGE])],
)
async def deposit_list_by_booking(
    tenant_id: str,
    booking_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[DepositOut]:
    """某预订的押金（登记页用）。"""
    svc = DepositService(session)
    rows = await svc.list(tenant_id=tenant_id, booking_id=booking_id, limit=200)
    return [_deposit_to_out(d) for d in rows]


# ---------- M34d 全局搜索 ----------


# 实体状态 → antd Tag color 映射（徽章着色）
_STATUS_COLOR = {
    # Booking
    "created": "blue",
    "checked_in": "green",
    "checked_out": "default",
    "cancelled": "red",
    "noshow": "red",
    # Bill
    "OPEN": "blue",
    "SETTLED": "green",
    # Room state（M1）
    "vacant_clean": "green",
    "vacant_dirty": "orange",
    "occupied_clean": "blue",
    "occupied_dirty": "red",
    "out_of_order": "red",
    "inspected": "cyan",
    # Member level
    "NORMAL": "default",
    "SILVER": "blue",
    "GOLD": "gold",
    "PLATINUM": "purple",
    # Group block
    "draft": "default",
    "active": "green",
    "closed": "default",
    # Notification
    "critical": "red",
    "normal": "blue",
    "info": "default",
}


def _status_color(status: str | None) -> str | None:
    """统一状态→颜色 helper：未知状态返回 None（前端走 default 灰）。"""
    if not status:
        return None
    return _STATUS_COLOR.get(status.lower())


@router.get("/tenants/{tenant_id}/search", response_model=SearchResultOut)
async def search_global(
    tenant_id: str,
    q: str = Query(..., min_length=1, max_length=64, description="搜索关键词"),
    types: str | None = Query(
        None, description="逗号分隔的实体类型过滤（guest,booking,room,bill,member,group,notification）"
    ),
    limit: int = Query(20, ge=1, le=50, description="单类型上限（防止大查询拖垮）"),
    login_session: LoginSession = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> SearchResultOut:
    """M34d 全局搜索：跨 7 实体聚合查询（Guest / Booking / Room / Bill / Member / Group / Notification）。

    实现要点：
    - 每个实体类最多 limit 条；items 是所有类型的并集，total = len(items)。
    - by_type 字段统计各类型命中数（如 {"guest": 3, "booking": 2}），前端按 by_type 排序展示。
    - 单实体查询 try/except 隔离：失败时仅跳过该实体，不影响其他实体的结果（默认空值 0）。
    - 权限：与既有单实体搜索端点一致（依赖 require_auth 全局鉴权 + tenant_id 路径参数隔离）。
    - types 支持逗号分隔字符串（如 "guest,booking"），未传则聚合 7 实体。
    """
    q_strip = q.strip()
    if not q_strip:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "搜索关键词不能为空")

    type_filter: set[str] | None = None
    if types:
        type_filter = {t.strip().lower() for t in types.split(",") if t.strip()}

    items: list[SearchResultItem] = []
    by_type: dict[str, int] = {}

    # 1) Guest —— 模糊搜索（姓名 LIKE / 手机号 LIKE）
    if not type_filter or "guest" in type_filter:
        try:
            like = f"%{q_strip}%"
            stmt = (
                select(Guest)
                .where(
                    Guest.tenant_id == tenant_id,
                    or_(Guest.name.ilike(like), Guest.phone.ilike(like), Guest.id_no.ilike(like)),
                )
                .order_by(Guest.id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            guests = list(result.scalars().all())
            for g in guests:
                items.append(
                    SearchResultItem(
                        type="guest",
                        id=g.id,
                        title=g.name or "—",
                        subtitle=g.phone or g.id_no or "—",
                        href=f"/guests/{g.id}",
                    )
                )
            by_type["guest"] = len(guests)
        except Exception:
            by_type["guest"] = 0

    # 2) Booking —— 按 guest_name / guest_phone 模糊匹配（无 booking_no 字段）
    if not type_filter or "booking" in type_filter:
        try:
            like = f"%{q_strip}%"
            stmt = (
                select(Booking)
                .where(
                    Booking.tenant_id == tenant_id,
                    or_(
                        Booking.guest_name.ilike(like),
                        Booking.guest_phone.ilike(like),
                        Booking.room_no.ilike(like),
                        Booking.id_doc_no.ilike(like),
                    ),
                )
                .order_by(Booking.id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            bookings = list(result.scalars().all())
            for b in bookings:
                items.append(
                    SearchResultItem(
                        type="booking",
                        id=b.id,
                        title=f"订单 #{b.id} · {b.guest_name or '—'}",
                        subtitle=f"{b.check_in_date} ~ {b.check_out_date} · 房号 {b.room_no or '—'}",
                        href=f"/bookings?id={b.id}",
                        badge=b.status,
                        badge_color=_status_color(b.status),
                    )
                )
            by_type["booking"] = len(bookings)
        except Exception:
            by_type["booking"] = 0

    # 3) Room —— 按 room_no 模糊 + 房型 code
    if not type_filter or "room" in type_filter:
        try:
            like = f"%{q_strip}%"
            stmt = (
                select(Room, RoomType.code)
                .outerjoin(RoomType, Room.room_type_id == RoomType.id)
                .where(
                    Room.tenant_id == tenant_id,
                    or_(Room.room_no.ilike(like), RoomType.code.ilike(like)),
                )
                .order_by(Room.room_no.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.all()
            for r, rt_code in rows:
                items.append(
                    SearchResultItem(
                        type="room",
                        id=r.id,
                        title=f"房号 {r.room_no}",
                        subtitle=f"{rt_code or '—'} · {r.state}",
                        href=f"/rooms?focus={r.id}",
                        badge=r.state,
                        badge_color=_status_color(r.state),
                    )
                )
            by_type["room"] = len(rows)
        except Exception:
            by_type["room"] = 0

    # 4) Bill —— 按 bill_no / guest_name 模糊
    if not type_filter or "bill" in type_filter:
        try:
            like = f"%{q_strip}%"
            stmt = (
                select(Bill)
                .where(
                    Bill.tenant_id == tenant_id,
                    or_(Bill.bill_no.ilike(like), Bill.guest_name.ilike(like), Bill.room_no.ilike(like)),
                )
                .order_by(Bill.id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            bills = list(result.scalars().all())
            for b in bills:
                balance_yuan = (b.balance or 0) / 100
                items.append(
                    SearchResultItem(
                        type="bill",
                        id=b.id,
                        title=f"账单 {b.bill_no}",
                        subtitle=f"{b.guest_name or '—'} · 房号 {b.room_no or '—'} · 余额 ¥{balance_yuan:.2f}",
                        href=f"/billing?id={b.id}",
                        badge=b.status,
                        badge_color=_status_color(b.status),
                    )
                )
            by_type["bill"] = len(bills)
        except Exception:
            by_type["bill"] = 0

    # 5) Member —— 按 phone / name 模糊匹配
    if not type_filter or "member" in type_filter:
        try:
            like = f"%{q_strip}%"
            stmt = (
                select(Member)
                .where(
                    Member.tenant_id == tenant_id,
                    or_(Member.phone.ilike(like), Member.name.ilike(like)),
                )
                .order_by(Member.id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            members = list(result.scalars().all())
            for m in members:
                items.append(
                    SearchResultItem(
                        type="member",
                        id=m.id,
                        title=m.name or "—",
                        subtitle=f"{m.phone} · {m.level}",
                        href=f"/members?id={m.id}",
                        badge=m.level,
                        badge_color=_status_color(m.level),
                    )
                )
            by_type["member"] = len(members)
        except Exception:
            by_type["member"] = 0

    # 6) Group —— 按 name / notes 模糊匹配
    if not type_filter or "group" in type_filter:
        try:
            like = f"%{q_strip}%"
            stmt = (
                select(GroupBlock)
                .where(
                    GroupBlock.tenant_id == tenant_id,
                    or_(GroupBlock.name.ilike(like), GroupBlock.notes.ilike(like)),
                )
                .order_by(GroupBlock.id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            groups = list(result.scalars().all())
            for g in groups:
                items.append(
                    SearchResultItem(
                        type="group",
                        id=g.id,
                        title=g.name,
                        subtitle=f"{g.arrival_date} ~ {g.departure_date}",
                        href=f"/group-blocks?id={g.id}",
                        badge=g.status,
                        badge_color=_status_color(g.status),
                    )
                )
            by_type["group"] = len(groups)
        except Exception:
            by_type["group"] = 0

    # 7) Notification —— 按 title / body 模糊匹配
    if not type_filter or "notification" in type_filter:
        try:
            like = f"%{q_strip}%"
            stmt = (
                select(Notification)
                .where(
                    Notification.tenant_id == tenant_id,
                    or_(Notification.title.ilike(like), Notification.body.ilike(like)),
                )
                .order_by(Notification.id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            notifs = list(result.scalars().all())
            for n in notifs:
                items.append(
                    SearchResultItem(
                        type="notification",
                        id=n.id,
                        title=n.title,
                        subtitle=n.body or "—",
                        href=n.link or f"/notifications?id={n.id}",
                        badge="已读" if n.read_at else "未读",
                        badge_color="default" if n.read_at else "blue",
                    )
                )
            by_type["notification"] = len(notifs)
        except Exception:
            by_type["notification"] = 0

    return SearchResultOut(items=items, total=len(items), by_type=by_type, query=q_strip)


# ---------- M37-③ 发票 + 换房记录 + 续住记录 ----------


@router.post(
    "/tenants/{tenant_id}/invoices",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[INVOICE_MANAGE])],
)
async def create_invoice(
    tenant_id: str,
    body: InvoiceIn,
    session: AsyncSession = Depends(get_session),
) -> InvoiceOut:
    """开票（201）。规则：开票额>消费额且差额>¥10 必填审批人；专票必填税号。"""
    hotel_id = await _resolve_hotel_id_from_invoice(session, tenant_id, body)
    svc = InvoiceService(session)
    try:
        inv = await svc.create(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            invoice_no=body.invoice_no,
            bill_id=body.bill_id,
            booking_id=body.booking_id,
            room_no=body.room_no,
            guest_name=body.guest_name,
            agreement_no=body.agreement_no,
            check_in_at=body.check_in_at,
            check_out_at=body.check_out_at,
            check_in_type=body.check_in_type,
            consume_amount_cents=body.consume_amount_cents,
            invoice_amount_cents=body.invoice_amount_cents,
            invoice_type=body.invoice_type,
            title=body.title,
            tax_no=body.tax_no,
            approver=body.approver,
            work_shift=body.work_shift,
            flag=body.flag,
            memo=body.memo,
            operator=body.operator,
        )
    except InvoiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    await session.refresh(inv)
    return InvoiceOut.model_validate(inv)


@router.get(
    "/tenants/{tenant_id}/invoices",
    response_model=list[InvoiceOut],
    dependencies=[Security(require_perm, scopes=[INVOICE_MANAGE])],
)
async def list_invoices(
    tenant_id: str,
    bill_id: int | None = None,
    booking_id: int | None = None,
    status: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[InvoiceOut]:
    """发票列表（带 MAX_LIST_ROWS 护栏）。"""
    svc = InvoiceService(session)
    rows = await svc.list(
        tenant_id=tenant_id,
        bill_id=bill_id,
        booking_id=booking_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [InvoiceOut.model_validate(r) for r in rows]


@router.get(
    "/tenants/{tenant_id}/invoices/{invoice_id}",
    response_model=InvoiceOut,
    dependencies=[Security(require_perm, scopes=[INVOICE_MANAGE])],
)
async def get_invoice(
    tenant_id: str,
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
) -> InvoiceOut:
    """发票详情。"""
    inv = await session.get(Invoice, invoice_id)
    if inv is None or inv.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "发票不存在")
    return InvoiceOut.model_validate(inv)


@router.post(
    "/tenants/{tenant_id}/invoices/{invoice_id}/void",
    response_model=InvoiceOut,
    dependencies=[Security(require_perm, scopes=[INVOICE_MANAGE, BILL_ADJUST])],
)
async def void_invoice(
    tenant_id: str,
    invoice_id: int,
    body: InvoiceVoidIn,
    session: AsyncSession = Depends(get_session),
) -> InvoiceOut:
    """作废发票（WORM，仅置 status=VOID，不改金额）。需要 invoice.manage + billing.adjust。"""
    svc = InvoiceService(session)
    try:
        inv = await svc.void(tenant_id, invoice_id, operator=body.operator)
    except InvoiceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    await session.refresh(inv)
    return InvoiceOut.model_validate(inv)


@router.get(
    "/tenants/{tenant_id}/bills/{bill_id}/invoices",
    response_model=list[InvoiceOut],
    dependencies=[Security(require_perm, scopes=[INVOICE_MANAGE])],
)
async def list_invoices_by_bill(
    tenant_id: str,
    bill_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[InvoiceOut]:
    """按账单查发票。"""
    bill = await session.get(Bill, bill_id)
    if bill is None or bill.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账单不存在")
    svc = InvoiceService(session)
    rows = await svc.list_by_bill(tenant_id, bill_id)
    return [InvoiceOut.model_validate(r) for r in rows]


@router.get(
    "/tenants/{tenant_id}/room-changes",
    response_model=list[RoomChangeOut],
)
async def list_room_changes(
    tenant_id: str,
    booking_id: int | None = None,
    room_no: str | None = None,
    business_date: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[RoomChangeOut]:
    """换房记录列表（登录态，筛选 booking_id/room_no/business_date，带 MAX_LIST_ROWS）。"""
    stmt = select(RoomChange).where(RoomChange.tenant_id == tenant_id)
    if booking_id is not None:
        stmt = stmt.where(RoomChange.booking_id == booking_id)
    if room_no:
        stmt = stmt.where(RoomChange.from_room_no == room_no)
    if business_date:
        stmt = stmt.where(RoomChange.business_date == business_date)
    stmt = stmt.order_by(RoomChange.id.desc())
    stmt = stmt.offset(max(0, offset)).limit(
        MAX_LIST_ROWS if limit is None else max(1, min(limit, MAX_LIST_ROWS))
    )
    result = await session.execute(stmt)
    return [RoomChangeOut.model_validate(r) for r in result.scalars()]


@router.get(
    "/tenants/{tenant_id}/bookings/{booking_id}/room-changes",
    response_model=list[RoomChangeOut],
)
async def list_room_changes_by_booking(
    tenant_id: str,
    booking_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[RoomChangeOut]:
    """某单换房历史。"""
    stmt = (
        select(RoomChange)
        .where(
            RoomChange.tenant_id == tenant_id,
            RoomChange.booking_id == booking_id,
        )
        .order_by(RoomChange.id.desc())
    )
    result = await session.execute(stmt)
    return [RoomChangeOut.model_validate(r) for r in result.scalars()]


@router.get(
    "/tenants/{tenant_id}/stay-extensions",
    response_model=list[StayExtensionOut],
)
async def list_stay_extensions(
    tenant_id: str,
    booking_id: int | None = None,
    business_date: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[StayExtensionOut]:
    """续住记录列表（登录态，带 MAX_LIST_ROWS）。"""
    stmt = select(StayExtension).where(StayExtension.tenant_id == tenant_id)
    if booking_id is not None:
        stmt = stmt.where(StayExtension.booking_id == booking_id)
    if business_date:
        stmt = stmt.where(StayExtension.business_date == business_date)
    stmt = stmt.order_by(StayExtension.id.desc())
    stmt = stmt.offset(max(0, offset)).limit(
        MAX_LIST_ROWS if limit is None else max(1, min(limit, MAX_LIST_ROWS))
    )
    result = await session.execute(stmt)
    return [StayExtensionOut.model_validate(r) for r in result.scalars()]


@router.get(
    "/tenants/{tenant_id}/bookings/{booking_id}/stay-extensions",
    response_model=list[StayExtensionOut],
)
async def list_stay_extensions_by_booking(
    tenant_id: str,
    booking_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[StayExtensionOut]:
    """某单续住历史。"""
    stmt = (
        select(StayExtension)
        .where(
            StayExtension.tenant_id == tenant_id,
            StayExtension.booking_id == booking_id,
        )
        .order_by(StayExtension.id.desc())
    )
    result = await session.execute(stmt)
    return [StayExtensionOut.model_validate(r) for r in result.scalars()]


async def _resolve_hotel_id_from_invoice(
    session: AsyncSession, tenant_id: str, body: InvoiceIn
) -> int:
    """从账单/订单/客房反查 hotel_id（开票需酒店归属）。"""
    if body.bill_id is not None:
        bill = await session.get(Bill, body.bill_id)
        if bill is not None and bill.tenant_id == tenant_id and bill.hotel_id:
            return bill.hotel_id
    if body.booking_id is not None:
        bk = await session.get(Booking, body.booking_id)
        if bk is not None and bk.tenant_id == tenant_id and bk.hotel_id:
            return bk.hotel_id
    # fallback：租户下任意酒店（多门店场景下应显式传 bill/booking）
    from sqlalchemy import select as _sel

    h = (
        await session.execute(
            _sel(Hotel).where(Hotel.tenant_id == tenant_id).limit(1)
        )
    ).scalar_one_or_none()
    if h is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法确定发票归属门店")
    return h.id


# ---- M37-④ 依赖集中声明（置于本分区之前，避免多人协作下顶部 import 块互相覆盖） ----
from app.models import (  # noqa: E402, F811
    BlackGuest,
    BreakfastTicket,
    Coupon,
    CouponTemplate,
    RoomAttribute,
)
from app.api.schemas import (  # noqa: E402, F811
    BlackGuestIn,
    BlackGuestOut,
    BlacklistHit,
    BreakfastIssueIn,
    BreakfastTicketOut,
    BreakfastUseIn,
    CouponIn,
    CouponOut,
    CouponTemplateIn,
    CouponTemplateOut,
    CouponUseIn,
    RoomAttributeIn,
    RoomAttributeOut,
)
from app.services.breakfast_service import BreakfastService  # noqa: E402
from app.services.coupon_service import CouponService  # noqa: E402


# ============================ M37-④ 早餐券 + 优惠券 + 房间属性 + 黑名单 ============================
#
# 设计要点：
# - 服务层只抛 ``ValueError``，路由统一映射：参数类 400 / 不存在 404 / 状态冲突 409；
# - 黑名单遵循 D1「仅提醒不硬阻断」——本分区只提供查询/维护，不拦截任何业务写路径；
# - 券/早餐券的 ``hotel_id`` 非空，未显式传入时按 订单 → 房间 → 租户首店 反查。

# 参数校验类错误提示词（用于区分 400 与 409）
_VALIDATION_HINTS = (
    "必填",
    "须为",
    "须 >",
    "不可超过",
    "不可为负",
    "未知折扣类型",
    "无法确定",
)


def _map_value_error(exc: ValueError) -> HTTPException:
    """服务层 ``ValueError`` → HTTP：参数类 400 / 不存在 404 / 其余状态冲突 409。"""
    msg = str(exc)
    if any(hint in msg for hint in _VALIDATION_HINTS):
        return HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    if "不存在" in msg:
        return HTTPException(status.HTTP_404_NOT_FOUND, msg)
    return HTTPException(status.HTTP_409_CONFLICT, msg)


async def _resolve_hotel_id_mini(
    session: AsyncSession,
    tenant_id: str,
    booking_id: int | None = None,
    room_id: int | None = None,
) -> int:
    """反查归属门店（早餐券/优惠券 hotel_id 非空）：订单 → 房间 → 租户首个门店。"""
    if booking_id is not None:
        bk = await session.get(Booking, booking_id)
        if bk is not None and bk.tenant_id == tenant_id and bk.hotel_id:
            return bk.hotel_id
    if room_id is not None:
        room = await session.get(Room, room_id)
        if room is not None and room.tenant_id == tenant_id and room.hotel_id:
            return room.hotel_id
    h = (
        await session.execute(select(Hotel).where(Hotel.tenant_id == tenant_id).limit(1))
    ).scalar_one_or_none()
    if h is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法确定归属门店")
    return h.id


# ---------- 房间属性 ----------


@router.get(
    "/tenants/{tenant_id}/rooms/{room_id}/attributes",
    response_model=list[RoomAttributeOut],
)
async def list_room_attributes(
    tenant_id: str,
    room_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[RoomAttributeOut]:
    """房间属性列表（登录态即可读，排房页与房态盘共用）。"""
    rows = await RoomService(session).list_room_attributes(tenant_id, room_id)
    return [RoomAttributeOut.model_validate(r) for r in rows]


@router.put(
    "/tenants/{tenant_id}/rooms/{room_id}/attributes",
    response_model=list[RoomAttributeOut],
)
async def replace_room_attributes(
    tenant_id: str,
    room_id: int,
    body: RoomAttributeIn,
    session: AsyncSession = Depends(get_session),
) -> list[RoomAttributeOut]:
    """房间属性全量覆盖（幂等：先软删再重建，一次 PUT 即最终态）。"""
    svc = RoomService(session)
    try:
        rows = await svc.set_room_attributes(
            tenant_id=tenant_id,
            hotel_id=0,  # 0 → 服务层回退到房间所属门店
            room_id=room_id,
            codes=body.codes,
            memo=body.memo,
            operator=body.operator,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return [RoomAttributeOut.model_validate(r) for r in rows]


@router.get("/tenants/{tenant_id}/room-attributes", response_model=list[str])
async def query_rooms_by_attributes(
    tenant_id: str,
    code: list[str] = Query(default_factory=list, description="属性编码，可重复传（AND 语义）"),
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """按属性过滤房号（排房用）：返回同时具备全部 ``code`` 的房号。"""
    return await RoomService(session).list_rooms_by_attributes(tenant_id, list(code))


# ---------- 黑名单 ----------


@router.get(
    "/tenants/{tenant_id}/blacklist",
    response_model=list[BlackGuestOut],
    dependencies=[Security(require_perm, scopes=[BLACKLIST_MANAGE])],
)
async def list_blacklist(
    tenant_id: str,
    name: str | None = None,
    id_no: str | None = None,
    level: int | None = None,
    is_valid: bool | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[BlackGuestOut]:
    """黑名单列表（敏感数据，需 blacklist.manage）。"""
    rows = await GuestService(session).list_blacklist(
        tenant_id,
        name=name,
        id_no=id_no,
        level=level,
        is_valid=is_valid,
        limit=limit,
        offset=offset,
    )
    return [BlackGuestOut.model_validate(r) for r in rows]


@router.post(
    "/tenants/{tenant_id}/blacklist",
    response_model=BlackGuestOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[BLACKLIST_MANAGE])],
)
async def add_blacklist(
    tenant_id: str,
    body: BlackGuestIn,
    session: AsyncSession = Depends(get_session),
) -> BlackGuestOut:
    """加入黑名单（hotel_id 为空 = 全集团生效）。"""
    svc = GuestService(session)
    try:
        row = await svc.add_blacklist(
            tenant_id=tenant_id,
            name=body.name,
            reason=body.reason,
            hotel_id=body.hotel_id,
            id_no=body.id_no,
            phone=body.phone,
            level=body.level,
            operator=body.operator,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    await session.refresh(row)
    return BlackGuestOut.model_validate(row)


@router.get("/tenants/{tenant_id}/blacklist/check", response_model=dict)
async def check_blacklist(
    tenant_id: str,
    name: str | None = None,
    id_no: str | None = None,
    phone: str | None = None,
    hotel_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """黑名单命中检查（**仅提醒不硬阻断**，返回 ``{hits: [...]}``）。

    匹配优先级 id_no > phone > name；id_no/phone 命中为强命中（``strong=True``）。
    """
    hits = await GuestService(session).check_blacklist(
        tenant_id, name=name, id_no=id_no, phone=phone, hotel_id=hotel_id
    )
    return {"hits": [BlacklistHit(**h).model_dump() for h in hits]}


@router.delete(
    "/tenants/{tenant_id}/blacklist/{black_id}",
    response_model=BlackGuestOut,
    dependencies=[Security(require_perm, scopes=[BLACKLIST_MANAGE])],
)
async def remove_blacklist(
    tenant_id: str,
    black_id: int,
    operator: str = "front_desk",
    session: AsyncSession = Depends(get_session),
) -> BlackGuestOut:
    """移出黑名单（WORM 软删，仅置 is_valid=False）。"""
    svc = GuestService(session)
    try:
        row = await svc.remove_blacklist(tenant_id, black_id, operator=operator)
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    await session.refresh(row)
    return BlackGuestOut.model_validate(row)


# ---------- 早餐券 ----------


@router.post(
    "/tenants/{tenant_id}/breakfast-tickets/issue",
    response_model=list[BreakfastTicketOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[BREAKFAST_MANAGE])],
)
async def issue_breakfast_tickets(
    tenant_id: str,
    body: BreakfastIssueIn,
    session: AsyncSession = Depends(get_session),
) -> list[BreakfastTicketOut]:
    """发早餐券（一次 count 张，券号 BF{snowflake}）。"""
    hotel_id = await _resolve_hotel_id_mini(session, tenant_id, booking_id=body.booking_id)
    svc = BreakfastService(session)
    try:
        rows = await svc.issue(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            booking_id=body.booking_id,
            room_no=body.room_no,
            ticket_type=body.ticket_type,
            ticket_type_name=body.ticket_type_name,
            count=body.count,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            card_type=body.card_type,
            memo=body.memo,
            operator=body.operator,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return [BreakfastTicketOut.model_validate(r) for r in rows]


@router.post(
    "/tenants/{tenant_id}/breakfast-tickets/use",
    response_model=BreakfastTicketOut,
    dependencies=[Security(require_perm, scopes=[BREAKFAST_MANAGE])],
)
async def use_breakfast_ticket(
    tenant_id: str,
    body: BreakfastUseIn,
    session: AsyncSession = Depends(get_session),
) -> BreakfastTicketOut:
    """核销早餐券（已核销再核 → 409）。"""
    svc = BreakfastService(session)
    try:
        row = await svc.use(
            tenant_id=tenant_id,
            ticket_no=body.ticket_no,
            business_date=body.business_date,
            operator=body.operator,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    await session.refresh(row)
    return BreakfastTicketOut.model_validate(row)


@router.post(
    "/tenants/{tenant_id}/breakfast-tickets/{ticket_id}/void",
    response_model=BreakfastTicketOut,
    dependencies=[Security(require_perm, scopes=[BREAKFAST_MANAGE])],
)
async def void_breakfast_ticket(
    tenant_id: str,
    ticket_id: int,
    operator: str = "front_desk",
    session: AsyncSession = Depends(get_session),
) -> BreakfastTicketOut:
    """作废早餐券（已核销不可作废 → 409）。"""
    svc = BreakfastService(session)
    try:
        row = await svc.void(tenant_id, ticket_id, operator=operator)
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    await session.refresh(row)
    return BreakfastTicketOut.model_validate(row)


@router.get(
    "/tenants/{tenant_id}/breakfast-tickets",
    response_model=list[BreakfastTicketOut],
    dependencies=[Security(require_perm, scopes=[BREAKFAST_MANAGE])],
)
async def list_breakfast_tickets(
    tenant_id: str,
    booking_id: int | None = None,
    ticket_type: int | None = None,
    is_used: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[BreakfastTicketOut]:
    """早餐券列表（带 MAX_LIST_ROWS 护栏）。"""
    rows = await BreakfastService(session).list(
        tenant_id,
        booking_id=booking_id,
        ticket_type=ticket_type,
        is_used=is_used,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [BreakfastTicketOut.model_validate(r) for r in rows]


# ---------- 优惠券 ----------


@router.get(
    "/tenants/{tenant_id}/coupon-templates",
    response_model=list[CouponTemplateOut],
    dependencies=[Security(require_perm, scopes=[COUPON_MANAGE])],
)
async def list_coupon_templates(
    tenant_id: str,
    is_valid: bool | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[CouponTemplateOut]:
    """券模板列表。"""
    rows = await CouponService(session).list_templates(tenant_id, is_valid=is_valid)
    return [CouponTemplateOut.model_validate(r) for r in rows]


@router.post(
    "/tenants/{tenant_id}/coupon-templates",
    response_model=CouponTemplateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[COUPON_MANAGE])],
)
async def create_coupon_template(
    tenant_id: str,
    body: CouponTemplateIn,
    session: AsyncSession = Depends(get_session),
) -> CouponTemplateOut:
    """创建券模板（同租户内 code 唯一）。"""
    svc = CouponService(session)
    try:
        row = await svc.create_template(
            tenant_id=tenant_id,
            code=body.code,
            name=body.name,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            hotel_id=body.hotel_id,
            ticket_type=body.ticket_type,
            discount_type=body.discount_type,
            discount_value=body.discount_value,
            total_quantity=body.total_quantity,
            operator=body.operator,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    await session.refresh(row)
    return CouponTemplateOut.model_validate(row)


@router.post(
    "/tenants/{tenant_id}/coupons",
    response_model=list[CouponOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_perm, scopes=[COUPON_MANAGE])],
)
async def issue_coupons(
    tenant_id: str,
    body: CouponIn,
    session: AsyncSession = Depends(get_session),
) -> list[CouponOut]:
    """发券：按模板批量（扣减发行量）或散券直给规则。"""
    hotel_id = body.hotel_id or await _resolve_hotel_id_mini(session, tenant_id)
    svc = CouponService(session)
    try:
        rows = await svc.issue(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            template_id=body.template_id,
            count=body.count,
            ticket_type=body.ticket_type,
            discount_type=body.discount_type,
            discount_value=body.discount_value,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            is_cover_other_discount=body.is_cover_other_discount,
            is_transfer_to_account=body.is_transfer_to_account,
            operator=body.operator,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return [CouponOut.model_validate(r) for r in rows]


@router.post(
    "/tenants/{tenant_id}/coupons/use",
    response_model=CouponOut,
    dependencies=[Security(require_perm, scopes=[COUPON_MANAGE])],
)
async def use_coupon(
    tenant_id: str,
    body: CouponUseIn,
    session: AsyncSession = Depends(get_session),
) -> CouponOut:
    """核销优惠券（转应收时写 BillItem(DISCOUNT) 并冲减账单余额）。"""
    svc = CouponService(session)
    try:
        row = await svc.use(
            tenant_id=tenant_id,
            coupon_no=body.coupon_no,
            booking_id=body.booking_id,
            bill_id=body.bill_id,
            operator=body.operator,
        )
    except ValueError as exc:
        # 过期判定是一次有效状态迁移（ISSUED → EXPIRED），即使拒绝核销也要落库
        await session.commit()
        raise _map_value_error(exc) from exc
    await session.commit()
    await session.refresh(row)
    return CouponOut.model_validate(row)


@router.post(
    "/tenants/{tenant_id}/coupons/{coupon_id}/void",
    response_model=CouponOut,
    dependencies=[Security(require_perm, scopes=[COUPON_MANAGE])],
)
async def void_coupon(
    tenant_id: str,
    coupon_id: int,
    operator: str = "front_desk",
    session: AsyncSession = Depends(get_session),
) -> CouponOut:
    """作废优惠券（已核销不可作废 → 409）。"""
    svc = CouponService(session)
    try:
        row = await svc.void(tenant_id, coupon_id, operator=operator)
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    await session.commit()
    await session.refresh(row)
    return CouponOut.model_validate(row)


@router.get(
    "/tenants/{tenant_id}/coupons",
    response_model=list[CouponOut],
    dependencies=[Security(require_perm, scopes=[COUPON_MANAGE])],
)
async def list_coupons(
    tenant_id: str,
    status: str | None = None,
    booking_id: int | None = None,
    coupon_no: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[CouponOut]:
    """优惠券列表（带 MAX_LIST_ROWS 护栏）。"""
    rows = await CouponService(session).list(
        tenant_id,
        status=status,
        booking_id=booking_id,
        coupon_no=coupon_no,
        limit=limit,
        offset=offset,
    )
    return [CouponOut.model_validate(r) for r in rows]

