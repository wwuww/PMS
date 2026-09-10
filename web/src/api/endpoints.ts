import { http } from "./http";
import type {
  Complaint,
  Tenant,
  TenantUpdate,
  Hotel,
  HotelUpdate,
  Room,
  RoomType,
  Dashboard,
  AnalyticsDashboard,
  Booking,
  BookingCreate,
  Bill,
  BillOpen,
  ChargeCreate,
  PaymentCreate,
  DailyReport,
  BusinessDay,
  NightAuditBoard,
  ApprovalTicket,
  ApprovalSubmit,
  ApprovalDecide,
  HousekeepingTask,
  HousekeepingCreate,
  Notification,
  NotificationPreference,
  NotificationSubscription,
  AlertNotification,
  HqDashboard,
  Settlement,
  AnalyticsRanking,
  AnalyticsChannel,
  AnalyticsRoomType,
  AnalyticsPayment,
  Member,
  MemberCreate,
  MemberRecharge,
  Guest,
  GuestVipLevel,
  GuestIdType,
  CommissionRule,
  CommissionRuleCreate,
  CommissionReconciliation,
  Shift,
  ShiftOpen,
  ShiftClose,
  WakeUpCall,
  WakeUpCallCreate,
  PsbTask,
  PsbTaskCreate,
  User,
  UserCreate,
  Role,
  RoleCreate,
  UserRole,
  LoginResult,
  LoginInput,
  RefreshResult,
  AuditLog,
  PayOrder,
  PayReconcileResult,
  RateCode,
  RateCodeCreate,
  PriceCalendar,
  PriceCalendarCreate,
  Availability,
  MpOffer,
  MpOrderPlace,
  MpOrder,
  ChatSession,
  ChatMessage,
  ChatReply,
  OpenApiApp,
  OpenApiAppCreate,
  OpenApiKey,
  OpenApiKeyWithSecret,
  OpenApiWebhook,
  OpenApiWebhookCreate,
  OpenApiWebhookTest,
  PricingRule,
  PricingRuleUpdate,
  PriceRecommend,
  PriceRecommendCreate,
  YieldApplyResult,
  YieldApplyInput,
  GroupPricePolicyOut,
  GroupPricePolicyIn,
  RoomTypeCreate,
  RoomCreate,
  Adjustment,
  ChannelPushIn,
  ChannelResult,
  ReportExport,
  GroupBlock,
  GroupAllocation,
  ReceptionContext,
  ReceptionAction,
  ReceptionCheckIn,
  MenuItem,
  DiningTable,
  PosOrder,
  PosOrderItem,
  FnbReport,
  KitchenTicket,
  ArAccount,
  ArRepayment,
  RoomRecommend,
  OversellWarnings,
  OccupancyForecast,
  CustomReport,
} from "./types";
import type {
  Deposit,
  DepositIn,
  DepositApplyIn,
  DepositRefundIn,
  DepositReleaseIn,
  DepositVoidIn,
  AutoReleaseIn,
  AutoReleaseOut,
  OtaConfig,
  OtaConfigIn,
  ChannelRoomMapping,
  ChannelRoomMappingIn,
  ChannelRatePlan,
  ChannelRatePlanIn,
  ChannelPushLog,
  SearchResult,
  SearchEntityType,
} from "./types";

export async function listTenants(): Promise<Tenant[]> {
  const { data } = await http.get<Tenant[]>("/tenants");
  return data;
}

export async function createTenant(body: {
  code: string;
  name: string;
  is_chain?: boolean;
}): Promise<Tenant> {
  const { data } = await http.post<Tenant>("/tenants", body);
  return data;
}

// M31：更新租户级设置（如 NoShow 自动扣首晚房费）
export async function updateTenantSettings(
  tenantCode: string,
  body: TenantUpdate
): Promise<Tenant> {
  const { data } = await http.patch<Tenant>(
    `/tenants/${tenantCode}/settings`,
    body
  );
  return data;
}

// M31：更新门店级设置（noshow_charge_first_night 可置 null=继承租户默认）
export async function updateHotelSettings(
  tenantCode: string,
  hotelId: string,
  body: HotelUpdate
): Promise<Hotel> {
  const { data } = await http.patch<Hotel>(
    `/tenants/${tenantCode}/hotels/${hotelId}/settings`,
    body
  );
  return data;
}

export async function listHotels(tenantCode: string): Promise<Hotel[]> {
  const { data } = await http.get<Hotel[]>(
    `/tenants/${tenantCode}/hotels`
  );
  return data;
}

export async function listRooms(tenantCode: string): Promise<Room[]> {
  const { data } = await http.get<Room[]>(`/tenants/${tenantCode}/rooms`);
  return data;
}

export async function managerDashboard(
  tenantCode: string,
  hotelId: string
): Promise<Dashboard> {
  const { data } = await http.get<Dashboard>(
    `/tenants/${tenantCode}/manager/dashboard`,
    { params: { hotel_id: hotelId } }
  );
  return data;
}

export async function analyticsDashboard(
  tenantCode: string,
  hotelId: string
): Promise<AnalyticsDashboard> {
  const { data } = await http.get<AnalyticsDashboard>(
    `/tenants/${tenantCode}/analytics/dashboard`,
    { params: { hotel_id: hotelId } }
  );
  return data;
}

export async function transitionRoom(
  tenantCode: string,
  roomNo: string,
  trigger: string,
  operator = "web"
): Promise<Room> {
  const { data } = await http.post<Room>(
    `/tenants/${tenantCode}/rooms/${roomNo}/transition`,
    { trigger, operator }
  );
  return data;
}

export async function listRoomTypes(tenantCode: string): Promise<RoomType[]> {
  const { data } = await http.get<RoomType[]>(
    `/tenants/${tenantCode}/room-types`
  );
  return data;
}

export async function listBookings(
  tenantCode: string,
  status_?: string
): Promise<Booking[]> {
  const { data } = await http.get<Booking[]>(`/tenants/${tenantCode}/bookings`, {
    params: status_ ? { status_ } : {},
  });
  return data;
}

export async function createBooking(
  tenantCode: string,
  body: BookingCreate
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/bookings`,
    body
  );
  return data;
}

export async function checkInBooking(
  tenantCode: string,
  bookingId: string,
  roomNo: string,
  operator = "front_desk"
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/bookings/${bookingId}/check-in`,
    { room_no: roomNo, operator }
  );
  return data;
}

/** 统一接待办理：散客/预订双模式一键入住。 */
export async function receptionCheckIn(
  tenantCode: string,
  body: ReceptionCheckIn
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/reception/check-in`,
    body
  );
  return data;
}

// ---------- 统一接待办理流（M1/M2：单客上下文 + 状态机，R1/R2/R3/R4） ----------

export async function receptionContext(
  tenantCode: string,
  opts: {
    guest_phone?: string | null;
    booking_id?: number | null;
    room_no?: string | null;
    hotel_id?: number | null;
  }
): Promise<ReceptionContext> {
  const params: Record<string, unknown> = {};
  if (opts.guest_phone != null) params.guest_phone = opts.guest_phone;
  if (opts.booking_id != null) params.booking_id = opts.booking_id;
  if (opts.room_no != null) params.room_no = opts.room_no;
  if (opts.hotel_id != null) params.hotel_id = opts.hotel_id;
  const { data } = await http.get<ReceptionContext>(
    `/tenants/${tenantCode}/reception/context`,
    { params }
  );
  return data;
}

export interface ReceptionAdvanceBody {
  action: string; // register | check_in | open_folio | check_out
  guest_phone?: string | null;
  booking_id?: number | null;
  room_no?: string | null;
  hotel_id?: number | null;
  guest_name?: string | null;
  room_type_id?: number | null;
  id_type?: string | null;
  id_no?: string | null;
  check_in_date?: string | null;
  check_out_date?: string | null;
  operator?: string;
}

export async function receptionAdvance(
  tenantCode: string,
  body: ReceptionAdvanceBody
): Promise<ReceptionContext> {
  const { data } = await http.post<ReceptionContext>(
    `/tenants/${tenantCode}/reception/advance`,
    body
  );
  return data;
}

// ---------- 团队 / 会议排房（M15，FR-GROUP） ----------

export interface GroupBlockCreateBody {
  hotel_id: number;
  name: string;
  arrival_date: string;
  departure_date: string;
  notes?: string | null;
}

export interface GroupBlockAssignItem {
  room_no: string;
  room_type_id: number;
  guest_name?: string | null;
  guest_phone?: string | null;
}

export interface GroupBlockAssignBody {
  allocations: GroupBlockAssignItem[];
}

export async function listGroupBlocks(
  tenantCode: string,
  hotelId?: string
): Promise<GroupBlock[]> {
  const params: Record<string, unknown> = {};
  if (hotelId != null) params.hotel_id = hotelId;
  const { data } = await http.get<GroupBlock[]>(
    `/tenants/${tenantCode}/group-blocks`,
    { params }
  );
  return data;
}

export async function getGroupBlock(
  tenantCode: string,
  id: string
): Promise<GroupBlock> {
  const { data } = await http.get<GroupBlock>(
    `/tenants/${tenantCode}/group-blocks/${id}`
  );
  return data;
}

export async function createGroupBlock(
  tenantCode: string,
  body: GroupBlockCreateBody
): Promise<GroupBlock> {
  const { data } = await http.post<GroupBlock>(
    `/tenants/${tenantCode}/group-blocks`,
    body
  );
  return data;
}

export async function assignGroupBlockRooms(
  tenantCode: string,
  id: string,
  body: GroupBlockAssignBody
): Promise<GroupBlock> {
  const { data } = await http.post<GroupBlock>(
    `/tenants/${tenantCode}/group-blocks/${id}/assign`,
    body
  );
  return data;
}

// M32.15：在住联房（账务关联到主房；各单保留自己的来离店日期）
export async function linkBookings(
  tenantCode: string,
  body: { room_nos: string[]; master_room_no: string }
): Promise<Booking[]> {
  const { data } = await http.post<Booking[]>(
    `/tenants/${tenantCode}/bookings/link`,
    body
  );
  return data;
}

export async function unlinkBookings(
  tenantCode: string,
  roomNos: string[]
): Promise<Booking[]> {
  const { data } = await http.post<Booking[]>(
    `/tenants/${tenantCode}/bookings/unlink`,
    { room_nos: roomNos }
  );
  return data;
}

// M32.16：联房结转——从房未结余额整体并入主房账单
export async function settleToMaster(
  tenantCode: string,
  roomNo: string
): Promise<{
  master_room_no: string;
  sub_room_no: string;
  amount: number;
  master_bill_balance: number;
  sub_bill_balance: number;
}> {
  const { data } = await http.post(
    `/tenants/${tenantCode}/bookings/settle-to-master`,
    { room_no: roomNo }
  );
  return data;
}

export async function checkInGroupBlock(
  tenantCode: string,
  id: string,
  operator = "front_desk"
): Promise<GroupBlock> {
  const { data } = await http.post<GroupBlock>(
    `/tenants/${tenantCode}/group-blocks/${id}/check-in`,
    undefined,
    { params: { operator } }
  );
  return data;
}

export async function closeGroupBlock(
  tenantCode: string,
  id: string
): Promise<GroupBlock> {
  const { data } = await http.post<GroupBlock>(
    `/tenants/${tenantCode}/group-blocks/${id}/close`
  );
  return data;
}

export async function checkOutBooking(
  tenantCode: string,
  bookingId: string,
  operator = "front_desk"
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/bookings/${bookingId}/check-out`,
    { operator }
  );
  return data;
}

/** 续住（延住）：延长在住房间离店日期。 */
export async function extendStayBooking(
  tenantCode: string,
  bookingId: string,
  newCheckOutDate: string,
  operator = "front_desk"
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/bookings/${bookingId}/extend-stay`,
    { new_check_out_date: newCheckOutDate, operator }
  );
  return data;
}

/** 换房：在住房客换至同房型空净房。 */
export async function changeRoomBooking(
  tenantCode: string,
  bookingId: string,
  newRoomNo: string,
  operator = "front_desk"
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/bookings/${bookingId}/change-room`,
    { new_room_no: newRoomNo, operator }
  );
  return data;
}

export interface BookingExtrasBody {
  extra_bed_count?: number | null;
  companion_names?: string[] | null;
  operator?: string;
}

export async function updateBookingExtras(
  tenantCode: string,
  bookingId: string,
  body: BookingExtrasBody
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/bookings/${bookingId}/extras`,
    body
  );
  return data;
}

export async function cancelBooking(
  tenantCode: string,
  bookingId: string
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/bookings/${bookingId}/cancel`,
    {}
  );
  return data;
}

/** M23 清单#3：前台手动标记 NoShow（留存原因并释放锁房）。 */
export async function markBookingNoshow(
  tenantCode: string,
  bookingId: string | number,
  reason?: string
): Promise<Booking> {
  const { data } = await http.post<Booking>(
    `/tenants/${tenantCode}/bookings/${bookingId}/noshow`,
    { reason: reason || null }
  );
  return data;
}

export interface NightAuditResult {
  ran: number;
  suspended: number;
  skipped: number;
  errors: unknown[];
  skips: { hotel_id: string; business_date: string; status: string; reason: string }[];
}

export async function runNightAudit(
  tenantCode: string,
  asOf: string,
  operator = "web"
): Promise<NightAuditResult> {
  const { data } = await http.post<NightAuditResult>(
    `/tenants/${tenantCode}/night-audit/auto-run`,
    { as_of: asOf, operator }
  );
  return data;
}

// ---------- 前台收银（M3） ----------

export async function listBills(
  tenantCode: string,
  source?: string
): Promise<Bill[]> {
  const { data } = await http.get<Bill[]>(`/tenants/${tenantCode}/bills`, {
    params: source ? { source } : {},
  });
  return data;
}

export async function getBill(
  tenantCode: string,
  billId: string
): Promise<Bill> {
  const { data } = await http.get<Bill>(
    `/tenants/${tenantCode}/bills/${billId}`
  );
  return data;
}

export async function openBill(
  tenantCode: string,
  body: BillOpen
): Promise<Bill> {
  const { data } = await http.post<Bill>(
    `/tenants/${tenantCode}/bills`,
    body
  );
  return data;
}

export async function addCharge(
  tenantCode: string,
  billId: string,
  body: ChargeCreate
): Promise<Bill> {
  const { data } = await http.post<Bill>(
    `/tenants/${tenantCode}/bills/${billId}/charges`,
    body
  );
  return data;
}

export async function takePayment(
  tenantCode: string,
  billId: string,
  body: PaymentCreate
): Promise<Bill> {
  const { data } = await http.post<Bill>(
    `/tenants/${tenantCode}/bills/${billId}/payments`,
    body
  );
  return data;
}

export async function settleBill(
  tenantCode: string,
  billId: string
): Promise<Bill> {
  const { data } = await http.post<Bill>(
    `/tenants/${tenantCode}/bills/${billId}/settle`,
    {}
  );
  return data;
}

export async function refundBill(
  tenantCode: string,
  billId: string,
  body: PaymentCreate
): Promise<Bill> {
  const { data } = await http.post<Bill>(
    `/tenants/${tenantCode}/bills/${billId}/refund`,
    body
  );
  return data;
}

// ---------- 夜审日报（M4） ----------

export async function listDailyReports(
  tenantCode: string,
  hotelId: string | undefined
): Promise<DailyReport[]> {
  const { data } = await http.get<DailyReport[]>(
    `/tenants/${tenantCode}/daily-reports`,
    { params: hotelId ? { hotel_id: hotelId } : {} }
  );
  return data;
}

export async function listBusinessDays(
  tenantCode: string,
  hotelId: string | undefined
): Promise<BusinessDay[]> {
  const { data } = await http.get<BusinessDay[]>(
    `/tenants/${tenantCode}/business-days`,
    { params: hotelId ? { hotel_id: hotelId } : {} }
  );
  return data;
}

export async function nightAuditBoard(
  tenantCode: string
): Promise<NightAuditBoard> {
  const { data } = await http.get<NightAuditBoard>(
    `/tenants/${tenantCode}/night-audit/board`
  );
  return data;
}

// ---------- 审批中心（M10-2） ----------

export async function listApprovals(
  tenantCode: string,
  status_?: string
): Promise<ApprovalTicket[]> {
  const { data } = await http.get<ApprovalTicket[]>(
    `/tenants/${tenantCode}/approvals`,
    { params: status_ ? { status: status_ } : {} }
  );
  return data;
}

export async function submitApproval(
  tenantCode: string,
  body: ApprovalSubmit
): Promise<ApprovalTicket> {
  const { data } = await http.post<ApprovalTicket>(
    `/tenants/${tenantCode}/approvals`,
    body
  );
  return data;
}

export async function decideApproval(
  tenantCode: string,
  ticketId: string,
  body: ApprovalDecide
): Promise<ApprovalTicket> {
  const { data } = await http.post<ApprovalTicket>(
    `/tenants/${tenantCode}/approvals/${ticketId}/decide`,
    body
  );
  return data;
}

// ---------- 清扫工单（M10-3） ----------

/** M26：多维过滤参数（状态 / 类型 / 责任人 / 楼层）。 */
export interface HousekeepingFilters {
  status?: string;
  task_type?: string;
  assignee?: string;
  floor?: string;
  hotel_id?: number | string;
}

export async function listHousekeeping(
  tenantCode: string,
  filters: HousekeepingFilters | string = {}
): Promise<HousekeepingTask[]> {
  const params =
    typeof filters === "string"
      ? filters && filters !== "ALL"
        ? { status: filters }
        : {}
      : { ...filters };
  const { data } = await http.get<HousekeepingTask[]>(
    `/tenants/${tenantCode}/housekeeping-tasks`,
    { params }
  );
  return data;
}

/** M26：批量派单（逐单尝试，返回成功/失败明细）。 */
export async function batchAssignHousekeeping(
  tenantCode: string,
  taskIds: number[],
  assignee: string
): Promise<{ assigned: number[]; failed: { id: number; reason: string }[] }> {
  const { data } = await http.post(
    `/tenants/${tenantCode}/housekeeping-tasks/batch-assign`,
    { task_ids: taskIds, assignee }
  );
  return data;
}

/** M26：批量完成（联动空脏 → 空净）。 */
export async function batchDoneHousekeeping(
  tenantCode: string,
  taskIds: number[],
  operator = "front_desk"
): Promise<{ done: number[]; failed: { id: number; reason: string }[] }> {
  const { data } = await http.post(
    `/tenants/${tenantCode}/housekeeping-tasks/batch-done`,
    { task_ids: taskIds, operator }
  );
  return data;
}

/** M26：员工清扫绩效（完成单数 / 平均耗时分钟）。 */
export interface HousekeepingPerformance {
  hotel_id: string;
  start_date: string | null;
  end_date: string | null;
  staff: { assignee: string; done_count: number; avg_minutes: number }[];
}

export async function housekeepingPerformance(
  tenantCode: string,
  hotelId: number | string,
  startDate?: string,
  endDate?: string
): Promise<HousekeepingPerformance> {
  const { data } = await http.get<HousekeepingPerformance>(
    `/tenants/${tenantCode}/analytics/housekeeping-performance`,
    { params: { hotel_id: Number(hotelId), start_date: startDate, end_date: endDate } }
  );
  return data;
}

export async function createHousekeeping(
  tenantCode: string,
  body: HousekeepingCreate
): Promise<HousekeepingTask> {
  const { data } = await http.post<HousekeepingTask>(
    `/tenants/${tenantCode}/housekeeping-tasks`,
    body
  );
  return data;
}

export async function assignHousekeeping(
  tenantCode: string,
  taskId: string,
  assignee: string
): Promise<HousekeepingTask> {
  const { data } = await http.post<HousekeepingTask>(
    `/tenants/${tenantCode}/housekeeping-tasks/${taskId}/assign`,
    { assignee }
  );
  return data;
}

export async function doneHousekeeping(
  tenantCode: string,
  taskId: string
): Promise<HousekeepingTask> {
  const { data } = await http.post<HousekeepingTask>(
    `/tenants/${tenantCode}/housekeeping-tasks/${taskId}/done`,
    {}
  );
  return data;
}

// ---------- 通知中心（M10-4） ----------

export async function listNotifications(
  tenantCode: string,
  opts?: {
    unreadOnly?: boolean;
    refType?: string | null;
    level?: string | null;
    hotelId?: number | null;
    limit?: number;
    offset?: number;
  }
): Promise<Notification[]> {
  const params: Record<string, unknown> = {};
  if (opts?.unreadOnly) params.unread_only = true;
  if (opts?.refType) params.ref_type = opts.refType;
  if (opts?.level) params.level = opts.level;
  if (opts?.hotelId != null) params.hotel_id = opts.hotelId;
  if (opts?.limit != null) params.limit = opts.limit;
  if (opts?.offset != null) params.offset = opts.offset;
  const { data } = await http.get<Notification[]>(`/tenants/${tenantCode}/notifications`, { params });
  return data;
}

export async function readNotification(
  tenantCode: string,
  id: string
): Promise<Notification> {
  const { data } = await http.post<Notification>(
    `/tenants/${tenantCode}/notifications/${id}/read`
  );
  return data;
}

export async function readAllNotifications(
  tenantCode: string,
  hotelId?: number | null
): Promise<number> {
  const params: Record<string, unknown> = {};
  if (hotelId != null) params.hotel_id = hotelId;
  const { data } = await http.post<{ updated: number }>(
    `/tenants/${tenantCode}/notifications/read-all`,
    undefined,
    { params }
  );
  return data.updated ?? 0;
}

export async function getUnreadCount(tenantCode: string, hotelId?: number | null): Promise<number> {
  const params: Record<string, unknown> = {};
  if (hotelId != null) params.hotel_id = hotelId;
  const { data } = await http.get<{ unread: number }>(
    `/tenants/${tenantCode}/notifications/unread-count`,
    { params }
  );
  return data.unread ?? 0;
}

// ③ 通知分级 / 免打扰偏好
export async function getNotificationPreferences(
  tenantCode: string
): Promise<NotificationPreference> {
  const { data } = await http.get<NotificationPreference>(
    `/tenants/${tenantCode}/notification-preferences`
  );
  return data;
}

export async function updateNotificationPreferences(
  tenantCode: string,
  body: Partial<NotificationPreference>
): Promise<NotificationPreference> {
  const { data } = await http.put<NotificationPreference>(
    `/tenants/${tenantCode}/notification-preferences`,
    body
  );
  return data;
}

// ④ 角色订阅配置
export async function getNotificationSubscriptions(
  tenantCode: string
): Promise<NotificationSubscription[]> {
  const { data } = await http.get<NotificationSubscription[]>(
    `/tenants/${tenantCode}/notification-subscriptions`
  );
  return data;
}

export async function updateNotificationSubscriptions(
  tenantCode: string,
  items: { ref_type: string; recipients: string[] }[]
): Promise<NotificationSubscription[]> {
  const { data } = await http.put<NotificationSubscription[]>(
    `/tenants/${tenantCode}/notification-subscriptions`,
    { items }
  );
  return data;
}

// ---------- AI 预警（M12） ----------

export async function listAlerts(
  tenantCode: string,
  status_?: string
): Promise<AlertNotification[]> {
  const { data } = await http.get<AlertNotification[]>(
    `/tenants/${tenantCode}/ai/alerts`,
    { params: status_ ? { status: status_ } : {} }
  );
  return data;
}

export async function acknowledgeAlert(
  tenantCode: string,
  id: string
): Promise<AlertNotification> {
  const { data } = await http.post<AlertNotification>(
    `/tenants/${tenantCode}/ai/alerts/${id}/acknowledge`
  );
  return data;
}

export async function resolveAlert(
  tenantCode: string,
  id: string
): Promise<AlertNotification> {
  const { data } = await http.post<AlertNotification>(
    `/tenants/${tenantCode}/ai/alerts/${id}/resolve`
  );
  return data;
}

// ---------- 集团驾驶舱（M17） ----------

export async function groupDashboard(
  tenantCode: string
): Promise<HqDashboard> {
  const { data } = await http.get<HqDashboard>(
    `/tenants/${tenantCode}/group/dashboard`
  );
  return data;
}

export async function groupSettlement(
  tenantCode: string
): Promise<Settlement> {
  const { data } = await http.get<Settlement>(
    `/tenants/${tenantCode}/group/settlement`
  );
  return data;
}

// ---------- 数据中台/经营分析（M16，扩展） ----------

export async function analyticsRanking(
  tenantCode: string
): Promise<AnalyticsRanking> {
  const { data } = await http.get<AnalyticsRanking>(
    `/tenants/${tenantCode}/analytics/hotel-ranking`
  );
  return data;
}

export async function analyticsChannelRevenue(
  tenantCode: string,
  hotelId: string
): Promise<AnalyticsChannel> {
  const { data } = await http.get<AnalyticsChannel>(
    `/tenants/${tenantCode}/analytics/channel-revenue`,
    { params: { hotel_id: hotelId } }
  );
  return data;
}

export async function analyticsRoomTypeRevenue(
  tenantCode: string,
  hotelId: string
): Promise<AnalyticsRoomType> {
  const { data } = await http.get<AnalyticsRoomType>(
    `/tenants/${tenantCode}/analytics/room-type-revenue`,
    { params: { hotel_id: hotelId } }
  );
  return data;
}

export async function analyticsPaymentSummary(
  tenantCode: string,
  hotelId: string
): Promise<AnalyticsPayment> {
  const { data } = await http.get<AnalyticsPayment>(
    `/tenants/${tenantCode}/analytics/payment-summary`,
  { params: { hotel_id: hotelId } }
  );
  return data;
}

// ---------- 会员 CRM（M13） ----------

export async function createMember(
  tenantCode: string,
  body: MemberCreate
): Promise<Member> {
  const { data } = await http.post<Member>(
    `/tenants/${tenantCode}/members`,
    body
  );
  return data;
}

export async function getMember(
  tenantCode: string,
  phone: string
): Promise<Member> {
  const { data } = await http.get<Member>(
    `/tenants/${tenantCode}/members/${encodeURIComponent(phone)}`
  );
  return data;
}

export async function rechargeMember(
  tenantCode: string,
  phone: string,
  body: MemberRecharge
): Promise<Member> {
  const { data } = await http.post<Member>(
    `/tenants/${tenantCode}/members/${encodeURIComponent(phone)}/recharge`,
    body
  );
  return data;
}

// ---------- 宾客档案 / 客史（M14，FR-GUEST） ----------

export interface GuestCreateBody {
  hotel_id: number;
  name: string;
  phone?: string | null;
  id_type?: GuestIdType | null;
  id_no?: string | null;
  vip_level?: GuestVipLevel;
  gender?: "M" | "F" | null;
  email?: string | null;
  address?: string | null;
  tags?: string[] | null;
  notes?: string | null;
  member_id?: number | null;
  // 批次② 核心实体字段补全
  en_name?: string | null;
  native_place?: string | null;
  nation?: string | null;
  is_valid?: boolean;
  come_time?: string | null;
  head_url?: string | null;
  id_doc_sign_org?: string | null;
  id_doc_valid_to?: string | null;
}

export interface GuestUpdateBody {
  name?: string | null;
  phone?: string | null;
  id_type?: GuestIdType | null;
  id_no?: string | null;
  vip_level?: GuestVipLevel | null;
  gender?: "M" | "F" | null;
  email?: string | null;
  address?: string | null;
  tags?: string[] | null;
  notes?: string | null;
  member_id?: number | null;
  // 批次② 核心实体字段补全
  en_name?: string | null;
  native_place?: string | null;
  nation?: string | null;
  is_valid?: boolean;
  come_time?: string | null;
  head_url?: string | null;
  id_doc_sign_org?: string | null;
  id_doc_valid_to?: string | null;
}

export async function createGuest(
  tenantCode: string,
  body: GuestCreateBody
): Promise<Guest> {
  const { data } = await http.post<Guest>(`/tenants/${tenantCode}/guests`, body);
  return data;
}

export async function getGuest(
  tenantCode: string,
  id: string
): Promise<Guest> {
  const { data } = await http.get<Guest>(
    `/tenants/${tenantCode}/guests/${id}`
  );
  return data;
}

export async function listGuests(
  tenantCode: string,
  opts?: { hotelId?: number | null; keyword?: string; limit?: number; offset?: number }
): Promise<Guest[]> {
  const params: Record<string, unknown> = {};
  if (opts?.hotelId != null) params.hotel_id = opts.hotelId;
  if (opts?.keyword) params.keyword = opts.keyword;
  if (opts?.limit != null) params.limit = opts.limit;
  if (opts?.offset != null) params.offset = opts.offset;
  const { data } = await http.get<Guest[]>(`/tenants/${tenantCode}/guests`, {
    params,
  });
  return data;
}

export async function searchGuests(
  tenantCode: string,
  opts: { phone?: string; name?: string; id_no?: string; booking_id?: number | string }
): Promise<Guest[]> {
  // M23 清单#4：支持 姓名/手机号/证件号/订单号 四维快速检索
  const params: Record<string, unknown> = {};
  if (opts.phone) params.phone = opts.phone;
  if (opts.name) params.name = opts.name;
  if (opts.id_no) params.id_no = opts.id_no;
  if (opts.booking_id !== undefined && opts.booking_id !== null && `${opts.booking_id}` !== "")
    params.booking_id = Number(opts.booking_id);
  const { data } = await http.get<Guest[]>(
    `/tenants/${tenantCode}/guests/search`,
    { params }
  );
  return data;
}

export async function updateGuest(
  tenantCode: string,
  id: string,
  body: GuestUpdateBody
): Promise<Guest> {
  const { data } = await http.patch<Guest>(
    `/tenants/${tenantCode}/guests/${id}`,
    body
  );
  return data;
}

// ---------- 佣金规则（M9） ----------

export async function listCommissionRules(
  tenantCode: string
): Promise<CommissionRule[]> {
  const { data } = await http.get<CommissionRule[]>(
    `/tenants/${tenantCode}/commission-rules`
  );
  return data;
}

export async function setCommissionRule(
  tenantCode: string,
  body: CommissionRuleCreate
): Promise<CommissionRule> {
  const { data } = await http.post<CommissionRule>(
    `/tenants/${tenantCode}/commission-rules`,
    body
  );
  return data;
}

export async function listCommissionReconciliations(
  tenantCode: string,
  hotelId: string | undefined,
  businessDate?: string
): Promise<CommissionReconciliation[]> {
  const params: Record<string, unknown> = {};
  if (hotelId != null) params.hotel_id = hotelId;
  if (businessDate != null) params.business_date = businessDate;
  const { data } = await http.get<CommissionReconciliation[]>(
    `/tenants/${tenantCode}/commission-reconciliations`,
    { params }
  );
  return data;
}

// ---------- 前台收银交班（M3） ----------

export async function listShifts(
  tenantCode: string,
  hotelId: string | undefined
): Promise<Shift[]> {
  const { data } = await http.get<Shift[]>(`/tenants/${tenantCode}/shifts`, {
    params: hotelId != null ? { hotel_id: hotelId } : {},
  });
  return data;
}

export async function openShift(
  tenantCode: string,
  body: ShiftOpen
): Promise<Shift> {
  const { data } = await http.post<Shift>(
    `/tenants/${tenantCode}/shifts/open`,
    body
  );
  return data;
}

export async function closeShift(
  tenantCode: string,
  shiftId: string,
  body: ShiftClose
): Promise<Shift> {
  const { data } = await http.post<Shift>(
    `/tenants/${tenantCode}/shifts/${shiftId}/close`,
    body
  );
  return data;
}

// ---------- 叫醒服务（M3-7） ----------

export async function listWakeUpCalls(
  tenantCode: string,
  hotelId: string,
  status_?: string
): Promise<WakeUpCall[]> {
  const params: Record<string, unknown> = { hotel_id: hotelId };
  if (status_) params.status_ = status_;
  const { data } = await http.get<WakeUpCall[]>(
    `/tenants/${tenantCode}/wake-up-calls`,
    { params }
  );
  return data;
}

export async function createWakeUpCall(
  tenantCode: string,
  body: WakeUpCallCreate
): Promise<WakeUpCall> {
  const { data } = await http.post<WakeUpCall>(
    `/tenants/${tenantCode}/wake-up-calls`,
    body
  );
  return data;
}

export async function doneWakeUpCall(
  tenantCode: string,
  callId: string
): Promise<WakeUpCall> {
  const { data } = await http.post<WakeUpCall>(
    `/tenants/${tenantCode}/wake-up-calls/${callId}/done`
  );
  return data;
}

export async function cancelWakeUpCall(
  tenantCode: string,
  callId: string
): Promise<WakeUpCall> {
  const { data } = await http.post<WakeUpCall>(
    `/tenants/${tenantCode}/wake-up-calls/${callId}/cancel`
  );
  return data;
}

// ---------- PSB 公安报送（M3-5） ----------

export async function listPsbTasks(
  tenantCode: string,
  hotelId: string | undefined,
  status_?: string
): Promise<PsbTask[]> {
  const params: Record<string, unknown> = {};
  if (hotelId != null) params.hotel_id = hotelId;
  if (status_) params.status_ = status_;
  const { data } = await http.get<PsbTask[]>(
    `/tenants/${tenantCode}/psb-tasks`,
    { params }
  );
  return data;
}

export async function createPsbTask(
  tenantCode: string,
  body: PsbTaskCreate
): Promise<PsbTask> {
  const { data } = await http.post<PsbTask>(
    `/tenants/${tenantCode}/psb-tasks`,
    body
  );
  return data;
}

export async function uploadPsbTask(
  tenantCode: string,
  taskId: string
): Promise<PsbTask> {
  const { data } = await http.post<PsbTask>(
    `/tenants/${tenantCode}/psb-tasks/${taskId}/upload`
  );
  return data;
}

// ---------- 用户与角色 RBAC（M8） ----------

export async function listUsers(tenantCode: string): Promise<User[]> {
  const { data } = await http.get<User[]>(`/tenants/${tenantCode}/users`);
  return data;
}

export async function createUser(
  tenantCode: string,
  body: UserCreate
): Promise<User> {
  const { data } = await http.post<User>(
    `/tenants/${tenantCode}/users`,
    body
  );
  return data;
}

export async function listRoles(tenantCode: string): Promise<Role[]> {
  const { data } = await http.get<Role[]>(`/tenants/${tenantCode}/roles`);
  return data;
}

export async function createRole(
  tenantCode: string,
  body: RoleCreate
): Promise<Role> {
  const { data } = await http.post<Role>(
    `/tenants/${tenantCode}/roles`,
    body
  );
  return data;
}

export async function assignUserRole(
  tenantCode: string,
  userId: string,
  roleId: string,
  hotelId: string | null
): Promise<UserRole> {
  const { data } = await http.post<UserRole>(
    `/tenants/${tenantCode}/users/${userId}/roles`,
    { role_id: roleId, hotel_id: hotelId ?? null }
  );
  return data;
}

// ---------- 登录（M8） ----------

export async function login(
  tenantCode: string,
  body: LoginInput
): Promise<LoginResult> {
  const { data } = await http.post<LoginResult>(
    `/tenants/${tenantCode}/auth/login`,
    body
  );
  return data;
}

// M18-2：刷新令牌换新会话（一次性旋转）
export async function authRefresh(
  tenantCode: string,
  refreshToken: string
): Promise<RefreshResult> {
  const { data } = await http.post<RefreshResult>(
    `/tenants/${tenantCode}/auth/refresh`,
    { refresh_token: refreshToken }
  );
  return data;
}

// ---------- 审计日志（M8） ----------

export async function listAuditLogs(tenantCode: string): Promise<AuditLog[]> {
  const { data } = await http.get<AuditLog[]>(
    `/tenants/${tenantCode}/audit-logs`
  );
  return data;
}

// ---------- 支付对账（M7-2） ----------

export async function listPayOrders(
  tenantCode: string,
  status_?: string
): Promise<PayOrder[]> {
  const { data } = await http.get<PayOrder[]>(
    `/tenants/${tenantCode}/pay-orders`,
    { params: status_ ? { status_: status_ } : {} }
  );
  return data;
}

export async function closePayOrder(
  tenantCode: string,
  outTradeNo: string
): Promise<PayOrder> {
  const { data } = await http.post<PayOrder>(
    `/tenants/${tenantCode}/pay-orders/${encodeURIComponent(outTradeNo)}/close`
  );
  return data;
}

export async function reconcilePay(
  tenantCode: string,
  before: string
): Promise<PayReconcileResult> {
  const { data } = await http.post<PayReconcileResult>(
    `/tenants/${tenantCode}/pay/reconcile`,
    { before }
  );
  return data;
}

// ---------- 价格库存中心（FR-JG） ----------

export async function listRateCodes(tenantCode: string): Promise<RateCode[]> {
  const { data } = await http.get<RateCode[]>(
    `/tenants/${tenantCode}/rate-codes`
  );
  return data;
}

export async function createRateCode(
  tenantCode: string,
  body: RateCodeCreate
): Promise<RateCode> {
  const { data } = await http.post<RateCode>(
    `/tenants/${tenantCode}/rate-codes`,
    body
  );
  return data;
}

export async function upsertPriceCalendar(
  tenantCode: string,
  body: PriceCalendarCreate
): Promise<PriceCalendar> {
  const { data } = await http.post<PriceCalendar>(
    `/tenants/${tenantCode}/price-calendar`,
    body
  );
  return data;
}

export async function listPriceCalendar(
  tenantCode: string,
  params: { room_type_id: string; start?: string; end?: string }
): Promise<PriceCalendar[]> {
  const { data } = await http.get<PriceCalendar[]>(
    `/tenants/${tenantCode}/price-calendar`,
    { params }
  );
  return data;
}

export interface BatchPriceResult {
  updated: number;
  blocked: string[];
  total: number;
}

export async function batchUpsertPriceCalendar(
  tenantCode: string,
  body: PriceCalendarCreate[]
): Promise<BatchPriceResult> {
  const { data } = await http.post<BatchPriceResult>(
    `/tenants/${tenantCode}/price-calendar/batch`,
    body
  );
  return data;
}

export async function roomTypeAvailability(
  tenantCode: string,
  roomTypeId: string,
  date: string,
  channel = "direct",
  rateCodeCode?: string | null
): Promise<Availability> {
  const { data } = await http.get<Availability>(
    `/tenants/${tenantCode}/room-types/${roomTypeId}/availability`,
    { params: { date, channel, rate_code_code: rateCodeCode } }
  );
  return data;
}

// ---------- 移动端直订小程序（M7） ----------

export async function mpOffers(
  tenantCode: string,
  hotelId: string,
  checkIn: string,
  checkOut: string
): Promise<MpOffer[]> {
  const { data } = await http.get<MpOffer[]>(`/tenants/${tenantCode}/mp/offers`, {
    params: { hotel_id: hotelId, check_in: checkIn, check_out: checkOut },
  });
  return data;
}

export async function mpPlaceOrder(
  tenantCode: string,
  body: MpOrderPlace
): Promise<MpOrder> {
  const { data } = await http.post<MpOrder>(
    `/tenants/${tenantCode}/mp/orders`,
    body
  );
  return data;
}

export async function mpOrderDetail(
  tenantCode: string,
  outTradeNo: string
): Promise<MpOrder> {
  const { data } = await http.get<MpOrder>(
    `/tenants/${tenantCode}/mp/orders/${encodeURIComponent(outTradeNo)}`
  );
  return data;
}

// ---------- AI 客服（M11） ----------

export async function listChatSessions(
  tenantCode: string,
  status?: string
): Promise<ChatSession[]> {
  const { data } = await http.get<ChatSession[]>(
    `/tenants/${tenantCode}/ai/chat-sessions`,
    { params: status ? { status } : {} }
  );
  return data;
}

export async function listChatMessages(
  tenantCode: string,
  sessionId: string
): Promise<ChatMessage[]> {
  const { data } = await http.get<ChatMessage[]>(
    `/tenants/${tenantCode}/ai/chat-sessions/${sessionId}/messages`
  );
  return data;
}

export async function chatSendMessage(
  tenantCode: string,
  sessionId: string,
  content: string,
  hotelId: string | null
): Promise<ChatReply> {
  const { data } = await http.post<ChatReply>(
    `/tenants/${tenantCode}/ai/chat-sessions/${sessionId}/messages`,
    { content, hotel_id: hotelId }
  );
  return data;
}

export async function chatHandoff(
  tenantCode: string,
  sessionId: string,
  reason = "用户请求人工",
  hotelId: string | null
): Promise<ChatMessage> {
  const { data } = await http.post<ChatMessage>(
    `/tenants/${tenantCode}/ai/chat-sessions/${sessionId}/handoff`,
    { reason, hotel_id: hotelId }
  );
  return data;
}

export async function chatCloseSession(
  tenantCode: string,
  sessionId: string,
  satisfaction?: number | null
): Promise<ChatSession> {
  const { data } = await http.post<ChatSession>(
    `/tenants/${tenantCode}/ai/chat-sessions/${sessionId}/close`,
    { satisfaction }
  );
  return data;
}

// ---------- 开放平台（M18） ----------

export async function listOpenApiApps(tenantCode: string): Promise<OpenApiApp[]> {
  const { data } = await http.get<OpenApiApp[]>(
    `/tenants/${tenantCode}/openapi/apps`
  );
  return data;
}

export async function registerOpenApiApp(
  tenantCode: string,
  body: OpenApiAppCreate
): Promise<OpenApiApp> {
  const { data } = await http.post<OpenApiApp>(
    `/tenants/${tenantCode}/openapi/apps`,
    body
  );
  return data;
}

export async function listOpenApiKeys(
  tenantCode: string,
  appId: string
): Promise<OpenApiKey[]> {
  const { data } = await http.get<OpenApiKey[]>(
    `/tenants/${tenantCode}/openapi/apps/${appId}/keys`
  );
  return data;
}

export async function createOpenApiKey(
  tenantCode: string,
  appId: string
): Promise<OpenApiKeyWithSecret> {
  const { data } = await http.post<OpenApiKeyWithSecret>(
    `/tenants/${tenantCode}/openapi/apps/${appId}/keys`
  );
  return data;
}

export async function revokeOpenApiKey(
  tenantCode: string,
  appId: string,
  keyId: string
): Promise<OpenApiKey> {
  const { data } = await http.post<OpenApiKey>(
    `/tenants/${tenantCode}/openapi/apps/${appId}/keys/${keyId}/revoke`
  );
  return data;
}

export async function listOpenApiWebhooks(
  tenantCode: string,
  appId: string | null
): Promise<OpenApiWebhook[]> {
  const { data } = await http.get<OpenApiWebhook[]>(
    `/tenants/${tenantCode}/openapi/webhooks`,
    { params: appId ? { app_id: appId } : {} }
  );
  return data;
}

export async function createOpenApiWebhook(
  tenantCode: string,
  body: OpenApiWebhookCreate
): Promise<OpenApiWebhook> {
  const { data } = await http.post<OpenApiWebhook>(
    `/tenants/${tenantCode}/openapi/webhooks`,
    body
  );
  return data;
}

export async function testOpenApiWebhook(
  tenantCode: string,
  subscriptionId: string
): Promise<OpenApiWebhookTest> {
  const { data } = await http.post<OpenApiWebhookTest>(
    `/tenants/${tenantCode}/openapi/webhooks/${subscriptionId}/test`
  );
  return data;
}

// ---------- 收益管理（M15） ----------

export async function getYieldRule(tenantCode: string): Promise<PricingRule> {
  const { data } = await http.get<PricingRule>(
    `/tenants/${tenantCode}/yield/rules`
  );
  return data;
}

export async function updateYieldRule(
  tenantCode: string,
  body: PricingRuleUpdate
): Promise<PricingRule> {
  const { data } = await http.put<PricingRule>(
    `/tenants/${tenantCode}/yield/rules`,
    body
  );
  return data;
}

export async function recommendPrice(
  tenantCode: string,
  body: PriceRecommendCreate
): Promise<PriceRecommend> {
  const { data } = await http.post<PriceRecommend>(
    `/tenants/${tenantCode}/yield/pricing/recommend`,
    body
  );
  return data;
}

export async function listYieldRecommendations(
  tenantCode: string,
  hotelId: string | null,
  businessDate?: string | null
): Promise<PriceRecommend[]> {
  const { data } = await http.get<PriceRecommend[]>(
    `/tenants/${tenantCode}/yield/pricing/recommendations`,
    { params: { hotel_id: hotelId, business_date: businessDate } }
  );
  return data;
}

// M20：建议一键应用到价格日历（可选区间批量落价）
export async function applyYieldRecommendation(
  tenantCode: string,
  recId: string,
  range?: YieldApplyInput
): Promise<YieldApplyResult> {
  const { data } = await http.post<YieldApplyResult>(
    `/tenants/${tenantCode}/yield/pricing/recommendations/${recId}/apply`,
    range ?? null
  );
  return data;
}

// M20：拒绝建议
export async function rejectYieldRecommendation(
  tenantCode: string,
  recId: string
): Promise<PriceRecommend> {
  const { data } = await http.post<PriceRecommend>(
    `/tenants/${tenantCode}/yield/pricing/recommendations/${recId}/reject`
  );
  return data;
}


// ---------- Wave 4：基础数据 / 财务 / 集团 / 渠道 / 报表 ----------

export async function createRoomType(
  tenantId: string,
  body: RoomTypeCreate
): Promise<RoomType> {
  const { data } = await http.post<RoomType>(
    `/tenants/${tenantId}/room-types`,
    body
  );
  return data;
}

export async function createRooms(
  hotelId: string,
  body: RoomCreate[]
): Promise<Room[]> {
  const { data } = await http.post<Room[]>(`/hotels/${hotelId}/rooms`, body);
  return data;
}

export async function listAdjustments(
  tenantCode: string
): Promise<Adjustment[]> {
  const { data } = await http.get<Adjustment[]>(
    `/tenants/${tenantCode}/adjustments`
  );
  return data;
}

export async function applyAdjustment(
  tenantCode: string,
  billId: string,
  body: { type: "VOID" | "ADJUST"; amount_cents: number; reason?: string; operator?: string }
): Promise<Bill> {
  const { data } = await http.post<Bill>(
    `/tenants/${tenantCode}/bills/${billId}/adjustments`,
    body
  );
  return data;
}

export async function createGroupPricePolicy(
  tenantCode: string,
  body: GroupPricePolicyIn
): Promise<GroupPricePolicyOut> {
  const { data } = await http.post<GroupPricePolicyOut>(
    `/tenants/${tenantCode}/group/price-policies`,
    body
  );
  return data;
}

export async function listGroupPricePolicies(
  tenantCode: string
): Promise<GroupPricePolicyOut[]> {
  const { data } = await http.get<GroupPricePolicyOut[]>(
    `/tenants/${tenantCode}/group/price-policies`
  );
  return data;
}

export async function pushChannelAvailability(
  tenantCode: string,
  channel: string,
  body: ChannelPushIn
): Promise<ChannelResult> {
  const { data } = await http.post<ChannelResult>(
    `/tenants/${tenantCode}/channels/${channel}/availability-push`,
    body
  );
  return data;
}

// ---------- M29 OTA 直连：渠道配置 / 房型映射 / 渠道价 / 推送日志 ----------

export async function listOtaConfigs(tenantCode: string): Promise<OtaConfig[]> {
  const { data } = await http.get<OtaConfig[]>(`/tenants/${tenantCode}/ota/configs`);
  return data;
}

export async function upsertOtaConfig(
  tenantCode: string,
  body: OtaConfigIn
): Promise<OtaConfig> {
  const { data } = await http.put<OtaConfig>(
    `/tenants/${tenantCode}/ota/configs`,
    body
  );
  return data;
}

export async function listChannelRoomMappings(
  tenantCode: string,
  opts?: { hotel_id?: number; channel?: string }
): Promise<ChannelRoomMapping[]> {
  const params: Record<string, unknown> = {};
  if (opts?.hotel_id != null) params.hotel_id = opts.hotel_id;
  if (opts?.channel) params.channel = opts.channel;
  const { data } = await http.get<ChannelRoomMapping[]>(
    `/tenants/${tenantCode}/ota/mappings`,
    { params }
  );
  return data;
}

export async function upsertChannelRoomMapping(
  tenantCode: string,
  body: ChannelRoomMappingIn
): Promise<ChannelRoomMapping> {
  const { data } = await http.post<ChannelRoomMapping>(
    `/tenants/${tenantCode}/ota/mappings`,
    body
  );
  return data;
}

export async function deleteChannelRoomMapping(
  tenantCode: string,
  mappingId: number
): Promise<void> {
  await http.delete(`/tenants/${tenantCode}/ota/mappings/${mappingId}`);
}

export async function listChannelRatePlans(
  tenantCode: string,
  opts?: { hotel_id?: number; channel?: string; pms_room_type_id?: number }
): Promise<ChannelRatePlan[]> {
  const params: Record<string, unknown> = {};
  if (opts?.hotel_id != null) params.hotel_id = opts.hotel_id;
  if (opts?.channel) params.channel = opts.channel;
  if (opts?.pms_room_type_id != null) params.pms_room_type_id = opts.pms_room_type_id;
  const { data } = await http.get<ChannelRatePlan[]>(
    `/tenants/${tenantCode}/ota/rate-plans`,
    { params }
  );
  return data;
}

export async function upsertChannelRatePlan(
  tenantCode: string,
  body: ChannelRatePlanIn
): Promise<ChannelRatePlan> {
  const { data } = await http.post<ChannelRatePlan>(
    `/tenants/${tenantCode}/ota/rate-plans`,
    body
  );
  return data;
}

export async function deleteChannelRatePlan(
  tenantCode: string,
  planId: number
): Promise<void> {
  await http.delete(`/tenants/${tenantCode}/ota/rate-plans/${planId}`);
}

export async function pushChannelInventory(
  tenantCode: string,
  channel: string,
  opts?: { days?: number; dry_run?: boolean }
): Promise<ChannelResult> {
  const params: Record<string, unknown> = {};
  if (opts?.days != null) params.days = opts.days;
  if (opts?.dry_run) params.dry_run = "true";
  const { data } = await http.post<ChannelResult>(
    `/tenants/${tenantCode}/ota/${channel}/inventory/push`,
    null,
    { params }
  );
  return data;
}

export async function pushChannelRates(
  tenantCode: string,
  channel: string,
  opts?: { dry_run?: boolean }
): Promise<ChannelResult> {
  const params: Record<string, unknown> = {};
  if (opts?.dry_run) params.dry_run = "true";
  const { data } = await http.post<ChannelResult>(
    `/tenants/${tenantCode}/ota/${channel}/rates/push`,
    null,
    { params }
  );
  return data;
}

export async function listChannelPushLogs(
  tenantCode: string,
  opts?: { hotel_id?: number; channel?: string; status?: string; limit?: number }
): Promise<ChannelPushLog[]> {
  const params: Record<string, unknown> = {};
  if (opts?.hotel_id != null) params.hotel_id = opts.hotel_id;
  if (opts?.channel) params.channel = opts.channel;
  if (opts?.status) params.status = opts.status;
  if (opts?.limit != null) params.limit = opts.limit;
  const { data } = await http.get<ChannelPushLog[]>(
    `/tenants/${tenantCode}/ota/push-logs`,
    { params }
  );
  return data;
}

export async function exportReport(
  tenantCode: string,
  params: {
    report_type: string;
    hotel_id: string | null;
    start_date?: string | null;
    end_date?: string | null;
    format?: string;
  }
): Promise<ReportExport> {
  const { data } = await http.get<ReportExport>(`/tenants/${tenantCode}/analytics/export`, {
    params,
  });
  return data;
}

export async function applyPrepay(
  tenantCode: string,
  billId: string
): Promise<Bill> {
  const { data } = await http.post<Bill>(
    `/tenants/${tenantCode}/bills/${billId}/apply-prepay`
  );
  return data;
}

// ---------- 餐饮 POS（F&B，M21） ----------

/** 菜品列表（默认仅上架；传 activeOnly=false 显示全部含停售）。 */
export async function listMenuItems(
  tenantCode: string,
  hotelId: number | string,
  activeOnly = true
): Promise<MenuItem[]> {
  const { data } = await http.get<MenuItem[]>(
    `/tenants/${tenantCode}/fnb/menu-items`,
    { params: { hotel_id: Number(hotelId), active_only: activeOnly } }
  );
  return data;
}

export interface MenuItemCreateBody {
  hotel_id: number | string;
  name: string;
  category?: string;
  price_cents: number;
  is_active?: number;
}

export async function createMenuItem(
  tenantCode: string,
  body: MenuItemCreateBody
): Promise<MenuItem> {
  const { data } = await http.post<MenuItem>(
    `/tenants/${tenantCode}/fnb/menu-items`,
    { ...body, hotel_id: Number(body.hotel_id) }
  );
  return data;
}

export interface MenuItemPatchBody {
  hotel_id?: number;
  name?: string;
  category?: string;
  price_cents?: number;
  is_active?: number;
}

export async function updateMenuItem(
  tenantCode: string,
  itemId: number,
  body: MenuItemPatchBody
): Promise<MenuItem> {
  const { data } = await http.patch<MenuItem>(
    `/tenants/${tenantCode}/fnb/menu-items/${itemId}`,
    body
  );
  return data;
}

/** 餐桌列表。 */
export async function listTables(
  tenantCode: string,
  hotelId: number | string
): Promise<DiningTable[]> {
  const { data } = await http.get<DiningTable[]>(
    `/tenants/${tenantCode}/fnb/tables`,
    { params: { hotel_id: Number(hotelId) } }
  );
  return data;
}

export interface DiningTableCreateBody {
  hotel_id: number | string;
  table_no: string;
  seats?: number;
  zone?: string | null;
}

export async function createTable(
  tenantCode: string,
  body: DiningTableCreateBody
): Promise<DiningTable> {
  const { data } = await http.post<DiningTable>(
    `/tenants/${tenantCode}/fnb/tables`,
    { ...body, hotel_id: Number(body.hotel_id) }
  );
  return data;
}

/** 切换餐桌状态：free|occupied|cleaning。 */
export async function setTableState(
  tenantCode: string,
  tableId: number,
  state: string
): Promise<DiningTable> {
  const { data } = await http.patch<DiningTable>(
    `/tenants/${tenantCode}/fnb/tables/${tableId}/state`,
    undefined,
    { params: { state } }
  );
  return data;
}

export interface PosOrderOpenBody {
  hotel_id: number | string;
  table_id?: number | null;
  room_no?: string | null;
  guest_name?: string | null;
  booking_id?: number | null;
}

/** 开餐饮账单（开台）。 */
export async function openPosOrder(
  tenantCode: string,
  body: PosOrderOpenBody
): Promise<PosOrder> {
  const { data } = await http.post<PosOrder>(
    `/tenants/${tenantCode}/fnb/orders`,
    { ...body, hotel_id: Number(body.hotel_id) }
  );
  return data;
}

export interface PosOrderItemBody {
  name: string;
  qty?: number;
  unit_price_cents: number;
  item_id?: number | null;
}

/** 餐饮账单加菜。 */
export async function addPosOrderItem(
  tenantCode: string,
  orderId: number,
  body: PosOrderItemBody
): Promise<PosOrderItem> {
  const { data } = await http.post<PosOrderItem>(
    `/tenants/${tenantCode}/fnb/orders/${orderId}/items`,
    body
  );
  return data;
}

/** M27：沽清 / 恢复供应。 */
export async function setMenuSoldOut(
  tenantCode: string,
  itemId: number,
  soldOut: boolean
): Promise<MenuItem> {
  const { data } = await http.post<MenuItem>(
    `/tenants/${tenantCode}/fnb/menu-items/${itemId}/sold-out`,
    { sold_out: soldOut }
  );
  return data;
}

/** M27：退菜（voided + 重算 total，仅未结算账单）。 */
export async function voidPosOrderItem(
  tenantCode: string,
  orderId: number,
  itemId: number,
  reason?: string
): Promise<PosOrder> {
  const { data } = await http.post<PosOrder>(
    `/tenants/${tenantCode}/fnb/orders/${orderId}/items/${itemId}/void`,
    { reason: reason || undefined }
  );
  return data;
}

/** M27：整单折扣（金额分或百分比 1-99，二选一）。 */
export async function applyPosOrderDiscount(
  tenantCode: string,
  orderId: number,
  body: { discount_cents?: number; percent?: number; operator?: string }
): Promise<PosOrder> {
  const { data } = await http.post<PosOrder>(
    `/tenants/${tenantCode}/fnb/orders/${orderId}/discount`,
    body
  );
  return data;
}

/** 挂房账结账（消费计入客房在开账单）。 */
export async function settlePosRoom(
  tenantCode: string,
  orderId: number,
  body: { room_no: string; operator?: string }
): Promise<PosOrder> {
  const { data } = await http.post<PosOrder>(
    `/tenants/${tenantCode}/fnb/orders/${orderId}/settle-room`,
    body
  );
  return data;
}

/** 现金结账（amount_paid 缺省按账单总额）。 */
export async function settlePosCash(
  tenantCode: string,
  orderId: number,
  body: { amount_paid?: number | null; operator?: string }
): Promise<PosOrder> {
  const { data } = await http.post<PosOrder>(
    `/tenants/${tenantCode}/fnb/orders/${orderId}/settle-cash`,
    body
  );
  return data;
}

/** 餐饮账单列表（status 可选 open|settled）。 */
export async function listPosOrders(
  tenantCode: string,
  hotelId: number | string,
  status?: string
): Promise<PosOrder[]> {
  const params: Record<string, unknown> = { hotel_id: Number(hotelId) };
  if (status) params.status = status;
  const { data } = await http.get<PosOrder[]>(
    `/tenants/${tenantCode}/fnb/orders`,
    { params }
  );
  return data;
}

// ---------- 餐饮报表（M22） ----------
export async function fnbReport(
  tenantCode: string,
  hotelId: number | string,
  start?: string,
  end?: string
): Promise<FnbReport> {
  const params: Record<string, unknown> = { hotel_id: Number(hotelId) };
  if (start) params.start = start;
  if (end) params.end = end;
  const { data } = await http.get<FnbReport>(
    `/tenants/${tenantCode}/fnb/reports/sales`,
    { params }
  );
  return data;
}

// ---------- 厨房出单 KDS（M22） ----------
export async function listKitchenTickets(
  tenantCode: string,
  hotelId: number | string,
  states?: string
): Promise<KitchenTicket[]> {
  const params: Record<string, unknown> = { hotel_id: Number(hotelId) };
  if (states) params.states = states;
  const { data } = await http.get<KitchenTicket[]>(
    `/tenants/${tenantCode}/fnb/kitchen/tickets`,
    { params }
  );
  return data;
}

export async function markItemReady(
  tenantCode: string,
  orderId: number,
  itemId: number
): Promise<PosOrderItem> {
  const { data } = await http.post<PosOrderItem>(
    `/tenants/${tenantCode}/fnb/orders/${orderId}/items/${itemId}/ready`
  );
  return data;
}

export async function markItemServed(
  tenantCode: string,
  orderId: number,
  itemId: number
): Promise<PosOrderItem> {
  const { data } = await http.post<PosOrderItem>(
    `/tenants/${tenantCode}/fnb/orders/${orderId}/items/${itemId}/served`
  );
  return data;
}


// ---------- M24 智能排房 + 协议单位挂账 ----------

export async function recommendRooms(
  tenantCode: string,
  opts: {
    hotelId: string;
    roomTypeId?: string | null;
    guestPhone?: string | null;
    idDocNo?: string | null;
    limit?: number;
  }
): Promise<RoomRecommend[]> {
  const params: Record<string, unknown> = { hotel_id: opts.hotelId };
  if (opts.roomTypeId) params.room_type_id = opts.roomTypeId;
  if (opts.guestPhone) params.guest_phone = opts.guestPhone;
  if (opts.idDocNo) params.id_doc_no = opts.idDocNo;
  if (opts.limit) params.limit = opts.limit;
  const { data } = await http.get<RoomRecommend[]>(
    `/tenants/${tenantCode}/rooms/recommend`,
    { params }
  );
  return data;
}

export async function listArAccounts(
  tenantCode: string,
  hotelId?: string | null
): Promise<ArAccount[]> {
  const params: Record<string, unknown> = {};
  if (hotelId) params.hotel_id = hotelId;
  const { data } = await http.get<ArAccount[]>(
    `/tenants/${tenantCode}/ar-accounts`,
    { params }
  );
  return data;
}

export async function createArAccount(
  tenantCode: string,
  body: {
    hotel_id: string;
    name: string;
    contact?: string | null;
    contact_phone?: string | null;
    credit_limit_cents?: number;
    note?: string | null;
  }
): Promise<ArAccount> {
  const { data } = await http.post<ArAccount>(
    `/tenants/${tenantCode}/ar-accounts`,
    body
  );
  return data;
}

export async function listArBills(
  tenantCode: string,
  accountId: string
): Promise<Bill[]> {
  const { data } = await http.get<Bill[]>(
    `/tenants/${tenantCode}/ar-accounts/${accountId}/bills`
  );
  return data;
}

export async function chargeBillToAr(
  tenantCode: string,
  accountId: string,
  billId: string
): Promise<Bill> {
  const { data } = await http.post<Bill>(
    `/tenants/${tenantCode}/ar-accounts/${accountId}/charge`,
    { bill_id: billId }
  );
  return data;
}

export async function repayArAccount(
  tenantCode: string,
  accountId: string,
  body: { amount: number; method?: string; note?: string | null }
): Promise<ArAccount> {
  const { data } = await http.post<ArAccount>(
    `/tenants/${tenantCode}/ar-accounts/${accountId}/repayments`,
    body
  );
  return data;
}

// ---------- M25 店总 BI ----------

export async function analyticsOversellWarnings(
  tenantCode: string,
  hotelId: string,
  startDate: string,
  endDate: string
): Promise<OversellWarnings> {
  const { data } = await http.get<OversellWarnings>(
    `/tenants/${tenantCode}/analytics/oversell-warnings`,
    { params: { hotel_id: hotelId, start_date: startDate, end_date: endDate } }
  );
  return data;
}

export async function analyticsForecast(
  tenantCode: string,
  hotelId: string,
  days = 14
): Promise<OccupancyForecast> {
  const { data } = await http.get<OccupancyForecast>(
    `/tenants/${tenantCode}/analytics/forecast`,
    { params: { hotel_id: hotelId, days } }
  );
  return data;
}

export async function analyticsCustomReport(
  tenantCode: string,
  hotelId: string,
  groupBy: "room_type" | "channel" | "day",
  startDate?: string | null,
  endDate?: string | null
): Promise<CustomReport> {
  const params: Record<string, unknown> = { hotel_id: hotelId, group_by: groupBy };
  if (startDate) params.start_date = startDate;
  if (endDate) params.end_date = endDate;
  const { data } = await http.get<CustomReport>(
    `/tenants/${tenantCode}/analytics/custom-report`,
    { params }
  );
  return data;
}


// ---------- M28：投诉工单 ----------

export async function listComplaints(
  tenantCode: string,
  filters: { hotel_id?: number | string; status?: string; booking_id?: number; guest_phone?: string; guest_name?: string } = {}
): Promise<Complaint[]> {
  const { data } = await http.get<Complaint[]>(`/tenants/${tenantCode}/complaints`, { params: filters });
  return data;
}

export async function createComplaint(
  tenantCode: string,
  body: {
    hotel_id: number | string;
    guest_name: string;
    description?: string;
    booking_id?: number | null;
    guest_phone?: string | null;
    room_no?: string | null;
    source?: string;
    category?: string;
  }
): Promise<Complaint> {
  const { data } = await http.post<Complaint>(`/tenants/${tenantCode}/complaints`, body);
  return data;
}

export async function transitionComplaint(
  tenantCode: string,
  complaintId: number,
  body: { to_status: string; handler?: string; resolution?: string; operator?: string }
): Promise<Complaint> {
  const { data } = await http.post<Complaint>(
    `/tenants/${tenantCode}/complaints/${complaintId}/transition`,
    body
  );
  return data;
}


// ---------- M31：免打扰 / 积分支付 / 团队分批结账 ----------

export async function setRoomDnd(
  tenantCode: string,
  roomNo: string,
  dnd: boolean
): Promise<Room> {
  const { data } = await http.post<Room>(
    `/tenants/${tenantCode}/rooms/${roomNo}/dnd`,
    { dnd, operator: "front_desk" }
  );
  return data;
}

/** M32.6：房态日志（某房间最近的状态流转流水）。 */
/** 登记单操作日志：该预订单的审计流水（创建/入住/续住/换房/随行人/退房等）。 */
export async function listBookingLogs(
  tenantCode: string,
  bookingId: string | number,
  limit = 50
): Promise<
  { id: number; action: string; actor: string; result: string; detail: Record<string, unknown>; created_at: string | null }[]
> {
  const { data } = await http.get(`/tenants/${tenantCode}/bookings/${bookingId}/logs`, {
    params: { limit },
  });
  return data;
}

export async function listRoomStateEvents(
  tenantCode: string,
  roomNo: string,
  limit = 50
): Promise<
  {
    id: number;
    room_no: string;
    from_state: string;
    to_state: string;
    trigger: string;
    operator: string;
    occurred_at: string;
  }[]
> {
  const { data } = await http.get(`/tenants/${tenantCode}/rooms/${roomNo}/state-events`, {
    params: { limit },
  });
  return data;
}

export async function groupBlockSettlement(
  tenantCode: string,
  blockId: number
): Promise<{
  block_id: number;
  status: string;
  total_allocations: number;
  settled_allocations: number;
  total_cents: number;
  settled_cents: number;
  rows: {
    allocation_id: number;
    room_no: string;
    guest_name: string | null;
    booking_id: string | null;
    bill_id: string | null;
    total_cents: number;
    settled: boolean;
  }[];
}> {
  const { data } = await http.get(
    `/tenants/${tenantCode}/group-blocks/${blockId}/settlement`
  );
  return data;
}

export async function settleGroupAllocation(
  tenantCode: string,
  blockId: number,
  allocId: number
): Promise<{ allocation_id: number; room_no: string; settled: boolean; block_settled_count?: number }> {
  const { data } = await http.post(
    `/tenants/${tenantCode}/group-blocks/${blockId}/allocations/${allocId}/settle`,
    { operator: "front_desk" }
  );
  return data;
}


// ---------- M32：P1 四项 ----------

export async function inspectHousekeeping(
  tenantCode: string,
  taskId: string,
  body: { passed: boolean; operator?: string; note?: string }
): Promise<{ id: string; room_no: string; status: string; done_at: string | null; note: string }> {
  const { data } = await http.post(`/tenants/${tenantCode}/housekeeping-tasks/${taskId}/inspect`, body);
  return data;
}

export async function fnbRoomLookup(
  tenantCode: string,
  roomNo: string
): Promise<{
  room_no: string;
  occupied: boolean;
  guest_name?: string | null;
  guest_phone_masked?: string | null;
  check_out_date?: string | null;
  bill_id?: string | null;
  bill_balance?: number | null;
  warning?: string | null;
}> {
  const { data } = await http.get(`/tenants/${tenantCode}/fnb/room-lookup`, { params: { room_no: roomNo } });
  return data;
}

// ---------- 押金与预授权（M32.18 T05） ----------

export async function createDeposit(
  tenantCode: string,
  body: DepositIn
): Promise<Deposit> {
  const { data } = await http.post<Deposit>(`/tenants/${tenantCode}/deposits`, body);
  return data;
}

export async function listDeposits(
  tenantCode: string,
  opts?: {
    hotel_id?: number;
    booking_id?: number;
    room_no?: string;
    status?: string;
    kind?: string;
    limit?: number;
  }
): Promise<Deposit[]> {
  const params: Record<string, unknown> = {};
  if (opts?.hotel_id != null) params.hotel_id = opts.hotel_id;
  if (opts?.booking_id != null) params.booking_id = opts.booking_id;
  if (opts?.room_no != null) params.room_no = opts.room_no;
  if (opts?.status != null) params.status = opts.status;
  if (opts?.kind != null) params.kind = opts.kind;
  if (opts?.limit != null) params.limit = opts.limit;
  const { data } = await http.get<Deposit[]>(`/tenants/${tenantCode}/deposits`, { params });
  return data;
}

export async function getDeposit(
  tenantCode: string,
  depositId: string
): Promise<Deposit> {
  const { data } = await http.get<Deposit>(`/tenants/${tenantCode}/deposits/${depositId}`);
  return data;
}

export async function applyDeposit(
  tenantCode: string,
  depositId: string,
  body: DepositApplyIn
): Promise<Deposit> {
  const { data } = await http.post<Deposit>(`/tenants/${tenantCode}/deposits/${depositId}/apply`, body);
  return data;
}

export async function refundDeposit(
  tenantCode: string,
  depositId: string,
  body: DepositRefundIn
): Promise<Deposit> {
  const { data } = await http.post<Deposit>(`/tenants/${tenantCode}/deposits/${depositId}/refund`, body);
  return data;
}

export async function releaseDeposit(
  tenantCode: string,
  depositId: string,
  body: DepositReleaseIn
): Promise<Deposit> {
  const { data } = await http.post<Deposit>(`/tenants/${tenantCode}/deposits/${depositId}/release`, body);
  return data;
}

export async function voidDeposit(
  tenantCode: string,
  depositId: string,
  body: DepositVoidIn
): Promise<Deposit> {
  const { data } = await http.post<Deposit>(`/tenants/${tenantCode}/deposits/${depositId}/void`, body);
  return data;
}

export async function autoReleaseDeposits(
  tenantCode: string,
  body: AutoReleaseIn
): Promise<AutoReleaseOut> {
  const { data } = await http.post<AutoReleaseOut>(`/tenants/${tenantCode}/deposits/auto-release`, body);
  return data;
}

export async function listDepositsByBooking(
  tenantCode: string,
  bookingId: number
): Promise<Deposit[]> {
  const { data } = await http.get<Deposit[]>(`/tenants/${tenantCode}/bookings/${bookingId}/deposits`);
  return data;
}

// ---------- M34d 全局搜索 ----------

export async function globalSearch(
  tenantCode: string,
  q: string,
  types?: SearchEntityType[],
  limit = 20,
): Promise<SearchResult> {
  const params: Record<string, string | number> = { q, limit };
  if (types && types.length) params.types = types.join(",");
  const { data } = await http.get<SearchResult>(
    `/tenants/${tenantCode}/search`,
    { params },
  );
  return data;
}
