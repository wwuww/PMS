export interface Tenant {
  id: string;
  code: string;
  name: string;
  is_chain: boolean;
  status: string;
  noshow_charge_first_night: boolean; // M31：NoShow 自动扣首晚房费（租户级默认）
}

export interface Hotel {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  noshow_charge_first_night: boolean | null; // M31：NoShow 自动扣首晚房费（None=继承租户默认）
}

// M31：租户/门店设置更新（仅写入显式提供的字段；酒店置 null=清除覆盖回落租户默认）
export interface TenantUpdate {
  noshow_charge_first_night?: boolean;
}

export interface HotelUpdate {
  noshow_charge_first_night?: boolean | null;
}

export interface RoomType {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  base_price: number;
  hourly_rate: number | null; // M24：时租价（分/小时）
  // 批次② 核心实体字段补全
  bed_number?: number;
  short_name?: string | null;
  en_name?: string | null;
  descript?: string | null;
  is_valid?: boolean;
}

export type RoomState =
  | "vacant_clean"
  | "vacant_dirty"
  | "occupied"
  | "arrival_locked"
  | "maintenance"
  | "out_of_service";

export interface Room {
  id: string;
  tenant_id: string;
  hotel_id: string;
  room_type_id: string;
  room_no: string;
  floor: string;
  state: RoomState;
  dnd: number; // M31：免打扰 0/1
  pre_lock_state?: string | null;  // M32.3 锁房前房态（锁房卡片用原色+小锁）
  // 批次② 核心实体字段补全
  building_id?: string | null;
  telephone?: string | null;
  room_card_no?: string | null;
  room_name?: string | null;
  memo?: string | null;
  is_valid?: boolean;
}

export interface RoomStateCount {
  total: number;
  by_state: Partial<Record<RoomState, number>>;
}

export type BookingStatus =
  | "created"
  | "checked_in"
  | "checked_out"
  | "cancelled"
  | "noshow";

export interface Booking {
  id: string;
  tenant_id: string;
  hotel_id: string;
  room_type_id: string;
  channel: string;
  guest_name: string;
  guest_phone: string | null;
  check_in_date: string;
  check_out_date: string;
  room_no: string | null;
  chat_session_id: string | null;
  status: BookingStatus;
  total_price: number | null;
  nights: number;
  extra_bed_count: number;
  companion_names: string[];
  stay_type: "daily" | "hourly"; // M24
  hourly_hours: number | null; // M24
  link_group_id: string | null; // M32.15：联房组（在住单之间）
  is_link_master: boolean; // M32.15：主房标记
  hourly_start_time: string | null; // M32.17b：钟点房到店时刻 HH:MM
  // 批次② 核心实体字段补全
  guest_source_type?: string | null;
  member_no?: string | null;
  member_type?: string | null;
  is_vip?: boolean;
  is_secret?: boolean;
  is_quick_depart?: boolean;
  is_print_real_price?: boolean;
  is_add_point?: boolean;
  is_guarantee?: boolean;
  guarantee_hold_until?: string | null;
  guarantor?: string | null;
  sales_id?: string | null;
  activity_code?: string | null;
  upgrade_room_type_id?: string | null;
  group_name?: string | null;
  group_type?: string | null;
  group_leader?: string | null;
  group_tel?: string | null;
  email?: string | null;
  country?: string | null;
}

export interface BookingCreate {
  hotel_id: string;
  room_type_id: string;
  guest_name: string;
  check_in_date: string;
  check_out_date: string;
  channel?: string;
  rate_code_code?: string | null;
  guest_phone?: string | null;
  id_doc_no?: string | null;
  room_no?: string | null;
  chat_session_id: string | null;
  stay_type?: "daily" | "hourly"; // M24：时租房
  hourly_hours?: number | null; // M24：时租时长（小时）
  // 批次② 核心实体字段补全
  guest_source_type?: string | null;
  member_no?: string | null;
  member_type?: string | null;
  is_vip?: boolean;
  is_secret?: boolean;
  is_quick_depart?: boolean;
  is_print_real_price?: boolean;
  is_add_point?: boolean;
  is_guarantee?: boolean;
  guarantee_hold_until?: string | null;
  guarantor?: string | null;
  sales_id?: string | null;
  activity_code?: string | null;
  upgrade_room_type_id?: string | null;
  group_name?: string | null;
  group_type?: string | null;
  group_leader?: string | null;
  group_tel?: string | null;
  email?: string | null;
  country?: string | null;
}

/** 统一接待办理（预订/散客双模式入住）。 */
export interface ReceptionCheckIn {
  booking_id?: number | null;
  room_no: string;
  room_type_id?: number | null;
  guest_name?: string | null;
  guest_phone?: string | null;
  id_type?: string | null;
  id_no?: string | null;
  check_in_date?: string | null;
  check_out_date?: string | null;
  operator?: string;
  // 批次② 核心实体字段补全
  guest_source_type?: string | null;
  member_no?: string | null;
  is_vip?: boolean;
  is_secret?: boolean;
  is_quick_depart?: boolean;
  is_print_real_price?: boolean;
  is_add_point?: boolean;
  is_guarantee?: boolean;
  guarantee_hold_until?: string | null;
}

// ---------- 统一接待办理流：单客上下文 + 编排状态机（M1/M2，R1/R2/R3/R4） ----------

/** 办理流状态机位置（由域状态派生，不持久化）。 */
export type ReceptionFlowState =
  | "query"
  | "register"
  | "checkin"
  | "inhouse"
  | "folio"
  | "checkout";

/** 有副作用的办理流动作（与状态机守卫一一对应）。 */
export type ReceptionAction =
  | "register"
  | "check_in"
  | "open_folio"
  | "check_out"
  | "enroll_member";

export interface ReceptionGuest {
  id: number;
  name: string;
  phone: string | null;
  id_type: string | null;
  id_no: string | null;
  vip_level: string;
  gender: string | null;
  email: string | null;
  tags: string[];
  notes: string | null;
  stay_count: number;
  total_spend: number; // 分
  member_id: number | null;
  member_level: string | null;
}

export interface ReceptionMembership {
  member_id: number;
  name: string;
  phone: string;
  level: string;
  stored_value: number; // 分
  points: number;
  stays: number;
}

export interface ReceptionBooking {
  id: number;
  guest_name: string;
  guest_phone: string | null;
  room_type_id: number | null;
  room_no: string | null;
  channel: string;
  status: string;
  check_in_date: string;
  check_out_date: string;
  total_price: number | null;
  extra_bed_count: number;
  companion_names: string[];
  nights: number;
}

export interface ReceptionFolio {
  bill_id: number;
  bill_no: string;
  status: string;
  balance: number; // 分
  item_count: number;
  payment_count: number;
}

export interface ReceptionAudit {
  id: number;
  action: string;
  actor: string;
  resource_type: string;
  resource_id: string | null;
  created_at: string | null;
}

export interface ReceptionContext {
  flow_state: ReceptionFlowState;
  can_advance: ReceptionAction[];
  guest: ReceptionGuest | null;
  membership: ReceptionMembership | null;
  booking: ReceptionBooking | null;
  room_no: string | null;
  room_state: string | null;
  folio: ReceptionFolio | null;
  audit_log: ReceptionAudit[];
  insights: string[];
  degraded: boolean;
  degradation_notes: string[];
}

/** 团队 / 会议排房：单房分配。 */
export interface GroupAllocation {
  id: string;
  room_no: string;
  room_type_id: string;
  guest_name?: string | null;
  guest_phone?: string | null;
  status: string;
}

/** 团队 / 会议排房：block 及分配明细。 */
export interface GroupBlock {
  id: string;
  tenant_id: string;
  hotel_id: string;
  name: string;
  arrival_date: string;
  departure_date: string;
  status: string;
  notes?: string | null;
  allocations: GroupAllocation[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Dashboard {
  hotel_id: string;
  business_date: string;
  rooms: RoomStateCount;
  occupancy_pct: number;
  in_house: number;
  arrivals: Booking[];
  departures: Booking[];
  latest_report: unknown | null;
  alerts: Record<string, unknown>;
}

// ---------- 前台收银（M3） ----------

export type BillSource = "BOOKING" | "WALK_IN";
export type ChargeType = "ROOM_CHARGE" | "MISC" | "DISCOUNT" | "REFUND";
export type PaymentMethod =
  | "CASH"
  | "PREAUTH"
  | "WECHAT"
  | "ALIPAY"
  | "UNIONPAY"
  | "STORE_VALUE";

export interface BillItem {
  id: string;
  type: ChargeType;
  amount: number; // 分（正应收 / 负冲减）
  description: string;
}

export interface Payment {
  id: string;
  method: PaymentMethod;
  amount: number; // 分
  is_deposit: boolean;
}

export interface Adjustment {
  id: string;
  bill_id: string | null;
  type: "VOID" | "ADJUST";
  amount_cents: number; // 分（有符号）
  reason: string;
  operator: string;
}

export interface Bill {
  id: string;
  tenant_id: string;
  bill_no: string;
  hotel_id: string;
  booking_id: string | null;
  guest_name: string;
  room_no: string | null;
  source: BillSource | null;
  status: string;
  balance: number; // 分（应收 − 实收 + 调整）
  items: BillItem[];
  payments: Payment[];
  adjustments: Adjustment[];
}

export interface BillOpen {
  hotel_id: string;
  guest_name: string;
  room_no?: string | null;
  booking_id: string | null;
  source?: BillSource | null;
}

export interface ChargeCreate {
  charge_type: ChargeType;
  amount: number; // 分（正应收 / 负冲减）
  description?: string;
}

export interface PaymentCreate {
  method: PaymentMethod;
  amount: number; // 分（≥1）
  is_deposit?: boolean;
  ref_no?: string | null;
  operator?: string;
}

// ---------- 夜审日报（M4） ----------

export interface DailyReport {
  id: string;
  hotel_id: string;
  business_date: string;
  arrived_rooms: number;
  departed_rooms: number;
  occupied_rooms: number;
  total_rooms: number;
  room_revenue: number; // 分
  other_revenue: number; // 分
  total_revenue: number; // 分
  adr: number; // 分
  occ_pct: number; // 百分比整数（如 33 表示 33%）
  snapshot?: string; // 夜审前后房态/账务快照（JSON 字符串）
}

export interface BusinessDay {
  id: string;
  hotel_id: string;
  business_date: string;
  status: string;
  audited_by: string | null;
  suspended_reason: string | null;
}

export interface NightAuditBoardHotel {
  hotel_id: number;
  name: string;
  latest_business_date: string | null;
  latest_status: string | null;
  suspended_count: number;
  latest_report: {
    business_date: string | null;
    occ_pct: number | null;
    room_revenue: number;
    total_revenue: number;
  };
}

export interface NightAuditBoard {
  hotels: NightAuditBoardHotel[];
  hotel_count: number;
  total_suspended: number;
}

// ---------- 审批中心（M10-2） ----------

export type ApprovalType = "DISCOUNT" | "ADJUST" | "OVERBOOK" | "REFUND";
export type ApprovalDecision = "APPROVE" | "REJECT";

export interface ApprovalTicket {
  id: string;
  tenant_id: string;
  hotel_id: string;
  type: ApprovalType;
  payload: Record<string, unknown>;
  reason: string;
  applicant: string;
  status: string; // PENDING | APPROVED | REJECTED
  approver: string | null;
  decision_note: string | null;
  decided_at: string | null;
  ref_id: string | null;
}

export interface ApprovalSubmit {
  hotel_id: string;
  type: ApprovalType;
  payload?: Record<string, unknown>;
  reason?: string;
  applicant?: string;
}

export interface ApprovalDecide {
  decision: ApprovalDecision;
  approver: string;
  note?: string;
}

// ---------- 清扫工单（M10-3） ----------

export type HousekeepingType = "CLEANUP" | "MAINTENANCE" | "INSPECT";

export interface HousekeepingTask {
  id: string;
  tenant_id: string;
  hotel_id: string;
  room_no: string;
  task_type: HousekeepingType;
  status: string; // PENDING | ASSIGNED | DONE
  assignee: string | null;
  source: string;
  note: string;
  due_at: string | null;
  done_at: string | null;
}

export interface HousekeepingCreate {
  hotel_id: string;
  room_no: string;
  task_type?: HousekeepingType;
  assignee?: string | null;
  note?: string;
  due_at?: string | null;
}

// ---------- 通知中心（M10-4） ----------

export interface Notification {
  id: string;
  tenant_id: string;
  hotel_id: string | null;
  recipient: string;
  channel: string;
  title: string;
  body: string;
  ref_type: string | null;
  ref_id: string | null;
  // ③ 通知分级与免打扰
  level: string;
  muted: boolean;
  // ④ 多接收人：本通知最终接收角色列表
  recipients: string[];
  link: string | null;
  read_at: string | null;
  created_at: string | null;
}

// ③ 免打扰偏好（每租户）
export interface NotificationPreference {
  tenant_id: string;
  dnd_enabled: boolean;
  dnd_start: string;
  dnd_end: string;
}

// ④ 角色订阅配置（每租户每个 ref_type 一行）
export interface NotificationSubscription {
  tenant_id: string;
  ref_type: string;
  label: string;
  recipients: string[];
}

// ---------- AI 预警（M12） ----------

export interface AlertNotification {
  id: string;
  tenant_id: string;
  hotel_id: string | null;
  alert_type: string;
  severity: string;
  title: string;
  description: string;
  ref_type: string | null;
  ref_id: string | null;
  status: string; // OPEN | ACKNOWLEDGED | RESOLVED
  suggested_action: string | null;
  created_at: string | null;
}

// ---------- 集团驾驶舱（M17） ----------

export interface HqDashboard {
  hotels: Array<Record<string, unknown>>;
  hotel_count: number;
  total_revenue: number; // 分
  total_room_revenue: number; // 分
}

export interface SettlementRow {
  hotel_id: string;
  name: string;
  pay_now_cents: number;
  prepaid_cents: number;
  total_cents: number;
}

export interface Settlement {
  hotels: SettlementRow[];
  group: Record<string, unknown>;
}

// ---------- 数据中台/经营分析（M16） ----------

export interface DailyPoint {
  business_date?: string;
  room_revenue_cents?: number;
  occ_pct_bps?: number;
  [k: string]: unknown;
}

export interface AnalyticsDashboard {
  hotel_id: string;
  hotel_name: string;
  start_date: string | null;
  end_date: string | null;
  days: number;
  total_rooms: number;
  occupied_room_nights: number;
  room_revenue_cents: number;
  other_revenue_cents: number;
  total_revenue_cents: number;
  revpar_cents: number;
  adr_cents: number;
  occ_pct_bps: number;
  daily_series: DailyPoint[];
}

export interface HotelRanking {
  hotel_id: string;
  name: string;
  days: number;
  room_revenue_cents: number;
  total_revenue_cents: number;
  revpar_cents: number;
  adr_cents: number;
  occ_pct_bps: number;
}

export interface AnalyticsRanking {
  hotels: HotelRanking[];
  hotel_count: number;
  total_room_revenue_cents: number;
  total_revenue_cents: number;
}

export interface ChannelRevenueRow {
  channel: string;
  booking_count: number;
  room_revenue_cents: number;
}

export interface AnalyticsChannel {
  hotel_id: string;
  hotel_name: string;
  start_date: string | null;
  end_date: string | null;
  channels: ChannelRevenueRow[];
  total_bookings: number;
  total_room_revenue_cents: number;
}

export interface RoomTypeRevenueRow {
  room_type_id: string;
  room_type_name: string;
  booking_count: number;
  room_revenue_cents: number;
}

export interface AnalyticsRoomType {
  hotel_id: string;
  hotel_name: string;
  start_date: string | null;
  end_date: string | null;
  room_types: RoomTypeRevenueRow[];
  total_bookings: number;
  total_room_revenue_cents: number;
}

export interface PaymentSummaryRow {
  method: string;
  amount_cents: number;
}

export interface AnalyticsPayment {
  hotel_id: string;
  hotel_name: string;
  start_date: string | null;
  end_date: string | null;
  methods: PaymentSummaryRow[];
  total_cents: number;
}

// ---------- 会员 CRM（M13） ----------

export interface Member {
  id: string;
  tenant_id: string;
  hotel_id: string;
  name: string;
  phone: string;
  level: string;
  stored_value: number; // 储值（分）
  points: number;
  stays: number;
  total_spend: number; // 分
  // 批次② 核心实体字段补全
  member_no?: string | null;
  card_type?: string | null;
  join_date?: string | null;
}

export interface MemberCreate {
  hotel_id: string;
  name: string;
  phone: string;
  // 批次② 核心实体字段补全
  member_no?: string | null;
  card_type?: string | null;
  join_date?: string | null;
}

export interface MemberRecharge {
  amount: number; // 分（≥1）
  operator?: string;
}

// ---------- 佣金规则（M9） ----------

export interface CommissionRule {
  id: string;
  tenant_id: string;
  channel: string;
  rate_bps: number; // 基点，10000=100%
  note: string;
}

export interface CommissionRuleCreate {
  channel: string;
  rate_bps: number;
  note?: string;
}

export interface CommissionReconciliation {
  id: string;
  hotel_id: string;
  business_date: string;
  channel: string;
  room_revenue_cents: number;
  commission_rate_bps: number;
  commission_cents: number;
  status: string;
  reconciled_at: string | null;
}

// ---------- 前台收银交班（M3） ----------

export interface Shift {
  id: string;
  tenant_id: string;
  hotel_id: string;
  cashier: string;
  status: string; // OPEN | CLOSED
  opening_float_cents: number;
  expected_cash_cents: number;
  counted_cash_cents: number;
  discrepancy_cents: number;
  /** M23 交班三口径：班内实收（全支付方式）/ 班内应收（新增正向条目） */
  received_cents: number;
  receivable_cents: number;
  opened_at: string | null;
  closed_at: string | null;
  note: string;
}

export interface ShiftOpen {
  hotel_id: string;
  cashier: string;
  opening_float_cents?: number; // 分
}

export interface ShiftClose {
  counted_cash_cents: number; // 分
  note?: string;
}

// ---------- 叫醒服务（M3-7） ----------

export interface WakeUpCall {
  id: string;
  tenant_id: string;
  hotel_id: string;
  room_no: string;
  guest_name: string;
  call_at: string; // ISO
  status: string; // PENDING | DONE | CANCELLED
  note: string;
}

export interface WakeUpCallCreate {
  hotel_id: string;
  room_no: string;
  call_at: string; // ISO
  guest_name?: string;
  note?: string;
  operator?: string;
}

// ---------- PSB 公安报送（M3-5） ----------

export interface PsbTask {
  id: string;
  tenant_id: string;
  hotel_id: string;
  booking_id: string | null;
  guest_name: string;
  id_doc_no_masked: string | null;
  room_no: string | null;
  status: string; // PENDING | UPLOADED
  uploaded_at: string | null;
  operator: string;
}

export interface PsbTaskCreate {
  hotel_id: string;
  guest_name: string;
  id_doc_no?: string | null;
  room_no?: string | null;
  operator?: string;
}

// ---------- 用户与角色 RBAC（M8） ----------

export type UserScope = "tenant" | "hotel";
export type RoleLevel = "ADMIN" | "MANAGER" | "STAFF";

export interface User {
  id: string;
  tenant_id: string;
  username: string;
  display_name: string;
  status: string; // active | disabled | locked
  scope: UserScope;
  failed_attempts: number;
  last_login_at: string | null;
  last_login_ip: string | null;
}

export interface UserCreate {
  username: string;
  password: string;
  display_name?: string;
  scope?: UserScope;
}

export interface Role {
  id: string;
  tenant_id: string;
  name: string;
  level: RoleLevel;
  is_system: boolean;
  hotel_scoped: boolean;
  permissions: string[];
}

export interface RoleCreate {
  name: string;
  level?: RoleLevel;
  permissions?: string[];
  hotel_scoped?: boolean;
}

export interface UserRole {
  id: string;
  tenant_id: string;
  user_id: string;
  role_id: string;
  hotel_id: string | null;
}

export interface LoginResult {
  token: string | null;
  refresh_token: string | null; // M18-2：一次性刷新令牌
  username: string;
  display_name: string;
  status: string; // ok | locked | bad_credentials | disabled | not_found
  permissions: string[];
}

export interface RefreshResult {
  token: string;
  refresh_token: string;
  username: string;
  display_name: string;
  status: string;
  permissions: string[];
}

export interface LoginInput {
  username: string;
  password: string;
  ip?: string | null;
}

// ---------- 审计日志（M8） ----------

export interface AuditLog {
  id: string;
  tenant_id: string;
  hotel_id: string | null;
  actor_id: string | null;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  result: string;
  ip: string | null;
  detail: Record<string, unknown>;
  created_at: string | null;
}

// ---------- 支付对账（M7-2） ----------

export interface PayOrder {
  id: string;
  tenant_id: string;
  hotel_id: string;
  out_trade_no: string;
  channel: string;
  booking_id: string | null;
  bill_id: string | null;
  subject: string;
  amount_cents: number;
  status: string; // CREATED | PAID | CLOSED | ...
  prepay_id: string | null;
  transaction_id: string | null;
  paid_at: string | null;
  close_reason: string | null;
}

export interface PayReconcileResult {
  scanned: number;
  closed: number;
  recovered: number;
  details: Array<Record<string, unknown>>;
}

// ---------- 价格库存中心（FR-JG） ----------

export interface RateCode {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  channel: string;
  member_level: string;
  agreement_type: string;
  stay_type: string;
  discount_pct: number; // 基点（0-10000，10000=原价）
  // 批次② 核心实体字段补全
  stay_class?: string | null;
  rate_type?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  is_overlay?: boolean;
  week?: string | null;
}

export interface RateCodeCreate {
  code: string;
  name: string;
  channel?: string;
  member_level?: string;
  agreement_type?: string;
  room_type_id: string | null;
  stay_type?: string;
  discount_pct?: number;
  // 批次② 核心实体字段补全
  stay_class?: string | null;
  rate_type?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  is_overlay?: boolean;
  week?: string | null;
}

export interface PriceCalendar {
  id: string;
  tenant_id: string;
  room_type_id: string;
  date: string;
  price: number; // 分
}

export interface PriceCalendarCreate {
  room_type_id: string;
  date: string;
  price: number; // 分
}

export interface Availability {
  room_type_id: string;
  date: string;
  total: number;
  booked: number;
  available: number;
  price: number; // 分
}

// ---------- 移动端直订小程序（M7） ----------

export interface MpOfferNight {
  date: string;
  price: number; // 分
  available: number;
}

export interface MpOffer {
  room_type_id: string;
  code: string;
  name: string;
  nights: number;
  price_per_night: MpOfferNight[];
  total_price: number; // 分
  available: number;
  bookable: boolean;
  sold_out_dates: string[];
}

export interface MpOrderPlace {
  hotel_id: string;
  room_type_id: string;
  guest_name: string;
  check_in_date: string;
  check_out_date: string;
  guest_phone?: string | null;
}

export interface MpOrder {
  booking: Booking;
  pay_order: PayOrder;
}

// ---------- AI 客服（M11） ----------

export interface ChatSession {
  id: string;
  tenant_id: string;
  channel: string;
  guest_name: string | null;
  guest_phone: string | null;
  status: string; // active | handoff | closed
  intent: string | null;
  satisfaction: number | null;
  created_at: string | null;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: string; // user | bot | agent
  content: string;
  intent: string | null;
  confidence: number | null;
  created_at: string | null;
}

export interface ChatReply {
  bot_message: ChatMessage;
  handoff: boolean;
  intent: string | null;
  confidence: number | null;
}

// ---------- 开放平台（M18） ----------

export interface OpenApiApp {
  id: string;
  tenant_id: string;
  app_code: string;
  name: string;
  status: string; // active | suspended
  callback_url: string | null;
  events_subscribed: string[];
  created_at: string | null;
}

export interface OpenApiAppCreate {
  app_code: string;
  name: string;
  callback_url?: string | null;
  events_subscribed?: string[];
}

export interface OpenApiKey {
  id: string;
  app_id: string;
  key_mask: string;
  status: string;
  created_at: string | null;
  revoked_at: string | null;
}

export interface OpenApiKeyWithSecret {
  key: OpenApiKey;
  secret: string;
}

export interface OpenApiWebhook {
  id: string;
  tenant_id: string;
  app_id: string;
  topic: string;
  endpoint_url: string;
  status: string;
  created_at: string | null;
}

export interface OpenApiWebhookCreate {
  app_id: string;
  topic: string;
  endpoint_url: string;
  secret?: string | null;
}

export interface OpenApiWebhookTest {
  id: string;
  event_topic: string;
  status: string;
  http_status: number | null;
  error_message: string | null;
}

// ---------- 收益管理（M15） ----------

export interface PricingRule {
  id: string;
  tenant_id: string;
  name: string;
  enabled: number; // 0/1
  high_occ_threshold: number; // %
  low_occ_threshold: number; // %
  max_uplift_bps: number;
  max_discount_bps: number;
  weekend_uplift_bps: number;
  competitor_strategy: string; // none | match | undercut
  competitor_undercut_bps: number;
}

export interface PricingRuleUpdate {
  name?: string;
  enabled?: number;
  high_occ_threshold?: number;
  low_occ_threshold?: number;
  max_uplift_bps?: number;
  max_discount_bps?: number;
  weekend_uplift_bps?: number;
  competitor_strategy?: string;
  competitor_undercut_bps?: number;
}

export interface PriceRecommend {
  id: string;
  tenant_id: string;
  hotel_id: string;
  room_type_id: string | null;
  business_date: string;
  base_price_cents: number;
  recommended_price_cents: number;
  adjustment_bps: number;
  demand_index: number;
  sample_days: number;
  status: string;
  rationale: string[];
}

export interface PriceRecommendCreate {
  hotel_id: string;
  room_type_id: string | null;
  business_date: string;
  base_price_cents: number;
  competitor_price_cents?: number | null;
  lead_time_days?: number | null;
}

export interface YieldApplyResult {
  rec_id: string;
  status: string;
  room_type_id: string;
  business_date: string;
  price: number;
  dates: string[];
  updated: number;
  created: number;
}

export interface YieldApplyInput {
  start?: string;
  end?: string;
}


// ---------- Wave 4：基础数据 / 财务 / 集团 / 渠道 / 报表 ----------

export interface RoomTypeCreate {
  code: string;
  name: string;
  base_price: number; // 分
  // 批次② 核心实体字段补全
  bed_number?: number;
  short_name?: string | null;
  en_name?: string | null;
  descript?: string | null;
  is_valid?: boolean;
}

export interface RoomCreate {
  room_type_id: string;
  room_no: string;
  floor: string;
  // 批次② 核心实体字段补全
  building_id?: string | null;
  telephone?: string | null;
  room_card_no?: string | null;
  room_name?: string | null;
  memo?: string | null;
  is_valid?: boolean;
}

export interface GroupPricePolicyIn {
  price_floor_cents: number;
  price_ceiling_cents?: number | null;
  hotel_id: string | null;
  room_type_id: string | null;
  note?: string;
}

export interface GroupPricePolicyOut {
  id: string;
  tenant_id: string;
  hotel_id: string | null;
  room_type_id: string | null;
  price_floor_cents: number;
  price_ceiling_cents: number | null;
  status: string;
  issued_by: string;
  note: string;
  created_at: string | null;
}

export interface ChannelPushIn {
  room_type_id: string;
  date: string; // YYYY-MM-DD
}

export interface ChannelResult {
  channel: string;
  integrated: boolean;
  message: string;
  payload: Record<string, unknown>;
  // M29 OTA 推送回执：后端 ota_service.push_inventory / push_rates 实际返回
  items?: unknown[]; // 推送明细（房量 / 渠道价）
  accepted?: boolean; // 是否被渠道接受
  trace_id?: string; // 链路追踪 ID
  hotel_id?: number | null;
  dry_run?: boolean;
  total_rooms?: number; // 仅 inventory push 返回
}

export type ReportType =
  | "dashboard"
  | "hotel_ranking"
  | "channel_revenue"
  | "room_type_revenue";

// ---------- M29 OTA 直连 ----------

export interface OtaConfig {
  id: string;
  tenant_id: string;
  hotel_id: string;
  channel: string;
  app_key: string;
  push_enabled: number;
  push_inventory_url: string | null;
}

export interface OtaConfigIn {
  hotel_id: number;
  channel: string;
  secret: string;
  app_key?: string;
  push_enabled?: boolean;
  push_inventory_url?: string | null;
}

export interface ChannelRoomMapping {
  id: string;
  tenant_id: string;
  hotel_id: string;
  channel: string;
  pms_room_type_id: string;
  external_room_type_code: string;
  enabled: number;
}

export interface ChannelRoomMappingIn {
  hotel_id: number;
  channel: string;
  pms_room_type_id: number;
  external_room_type_code: string;
  enabled?: boolean;
}

export interface ChannelRatePlan {
  id: string;
  tenant_id: string;
  hotel_id: string;
  channel: string;
  pms_room_type_id: string;
  effective_date: string | null;
  price_cents: number;
  enabled: number;
}

export interface ChannelRatePlanIn {
  hotel_id: number;
  channel: string;
  pms_room_type_id: number;
  effective_date: string | null;
  price_cents: number;
  enabled?: boolean;
}

export interface ChannelPushLog {
  id: string;
  tenant_id: string;
  hotel_id: string;
  channel: string;
  days: number;
  status: string;
  trace_id: string;
  item_count: number;
  duration_ms: number;
  error_message: string | null;
  operator: string;
  created_at: string | null;
}
export interface ReportExport {
  report_type?: string;
  data?: Array<Record<string, unknown>>;
  meta?: Record<string, unknown>;
  hotels?: Array<Record<string, unknown>>;
  channels?: Array<Record<string, unknown>>;
  room_types?: Array<Record<string, unknown>>;
  daily_series?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

// ---------- 宾客档案 / 客史（M14，FR-GUEST） ----------

export type GuestVipLevel =
  | "NORMAL"
  | "SILVER"
  | "GOLD"
  | "PLATINUM"
  | "DIAMOND";

export type GuestIdType = "ID" | "PASSPORT" | "OFFICER" | "OTHER";

export interface Guest {
  id: string;
  tenant_id: string;
  hotel_id: string;
  name: string;
  phone: string | null;
  id_type: GuestIdType | null;
  id_no: string | null;
  vip_level: GuestVipLevel;
  gender: "M" | "F" | null;
  birthday: string | null;
  email: string | null;
  address: string | null;
  tags: string[];
  notes: string | null;
  stay_count: number;
  total_spend: number; // 分
  member_id: string | null;
  member_level: GuestVipLevel | null;
  member_points: number | null;
  member_stored_value: number | null; // 分
  created_at: string | null;
  updated_at: string | null;
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

// ---------- 餐饮 POS（F&B，M21） ----------

/** 菜品（租户级，可按门店下架）。 */
export interface MenuItem {
  id: number;
  tenant_id: string;
  hotel_id: number;
  name: string;
  category: string; // 热菜/凉菜/酒水/主食/其他
  price_cents: number; // 分
  is_active: number; // 0/1
  sold_out: number; // M27：0/1 当日沽清（拒点但不影响上架）
}

/** 餐桌 / 桌台，state: free|occupied|cleaning。 */
export interface DiningTable {
  id: number;
  tenant_id: string;
  hotel_id: number;
  table_no: string;
  seats: number;
  zone: string | null; // 大厅/包厢
  state: string;
}

/** 餐饮账单明细（点菜行）。 */
export interface PosOrderItem {
  id: number;
  order_id: number;
  item_id: number | null;
  name: string;
  category: string | null; // 热菜/凉菜/酒水/主食/其他
  qty: number;
  unit_price_cents: number; // 分
  subtotal_cents: number; // 分
  kds_status: string; // pending|ready|served
  voided: number; // M27：0/1 已退菜
  void_reason: string | null; // M27：退菜原因
}

/** 餐饮账单（开单 → 点菜 → 结账）。 */
export interface PosOrder {
  id: number;
  tenant_id: string;
  hotel_id: number;
  table_id: number | null;
  status: string; // open|settled
  settle_type: string | null; // room|cash
  room_no: string | null;
  booking_id: number | null;
  guest_name: string | null;
  total_cents: number; // 分
  discount_cents: number; // M27：整单折扣（分）
  items: PosOrderItem[];
}

// ---------- 餐饮报表（M22） ----------
export interface FnbCategorySales {
  category: string;
  qty: number;
  revenue_cents: number; // 分
}

export interface FnbTableSales {
  table_no: string;
  order_count: number;
  revenue_cents: number; // 分
}

export interface FnbReport {
  total_revenue_cents: number; // 分
  order_count: number;
  item_count: number;
  avg_per_table_cents: number; // 分
  by_category: FnbCategorySales[];
  by_table: FnbTableSales[];
}

// ---------- 厨房出单 KDS（M22） ----------
export interface KitchenTicket {
  item_id: number;
  order_id: number;
  table_no: string | null;
  room_no: string | null;
  guest_name: string | null;
  name: string;
  category: string | null;
  qty: number;
  kds_status: string; // pending|ready|served
}


// ---------- M24 协议单位挂账 / 智能排房 ----------

/** 协议单位挂账账户（月结）。 */
export interface ArAccount {
  id: string;
  tenant_id: string;
  hotel_id: string;
  name: string;
  contact: string | null;
  contact_phone: string | null;
  credit_limit_cents: number; // 0 = 不限额
  balance_cents: number; // 未清欠款（分）
  note: string | null;
  status: string;
}

/** 协议单位还款流水。 */
export interface ArRepayment {
  id: string;
  tenant_id: string;
  ar_account_id: string;
  amount: number;
  method: string;
  operator: string;
  note: string | null;
}

/** 智能排房推荐项。 */
export interface RoomRecommend {
  room_id: string;
  room_no: string;
  floor: string;
  room_type_id: string;
  state: RoomState;
  score: number;
  reasons: string[];
}

/** M25 超卖预警响应。 */
export interface OversellWarnings {
  hotel_id: string;
  hotel_name: string;
  start_date: string;
  end_date: string;
  sellable_rooms: number;
  warnings: {
    date: string;
    on_hand_bookings: number;
    sellable_rooms: number;
    gap: number;
    level: "OVERSELL" | "CRITICAL";
  }[];
  warning_count: number;
}

/** M25 在手入住率预测响应。 */
export interface OccupancyForecast {
  hotel_id: string;
  hotel_name: string;
  days: number;
  sellable_rooms: number;
  forecast: {
    date: string;
    on_hand_bookings: number;
    sellable_rooms: number;
    occupancy_rate: number;
  }[];
  booking_pace: { date: string; bookings: number }[];
}

/** M25 自定义报表响应。 */
export interface CustomReport {
  hotel_id: string;
  hotel_name: string;
  group_by: "room_type" | "channel" | "day";
  start_date: string | null;
  end_date: string | null;
  rows: {
    group: string;
    label?: string;
    booking_count: number;
    room_revenue_cents: number;
  }[];
  total_bookings: number;
  total_room_revenue_cents: number;
}


// ---------- M28：投诉工单 ----------

export type ComplaintCategory = "SERVICE" | "FACILITY" | "HYGIENE" | "NOISE" | "BILLING" | "OTHER";

/** 投诉工单：与住客/预订关联，OPEN → HANDLING → RESOLVED/CANCELLED。 */
export interface Complaint {
  id: number;
  tenant_id: string;
  hotel_id: number;
  booking_id: number | null;
  guest_name: string;
  guest_phone: string | null;
  room_no: string | null;
  source: string;
  category: ComplaintCategory;
  status: string; // OPEN | HANDLING | RESOLVED | CANCELLED
  description: string;
  handler: string | null;
  resolution: string | null;
  handled_at: string | null;
  created_at: string | null;
}

// ---------- 押金与预授权（M32.18 T05） ----------

export type DepositKind = "DEPOSIT" | "PREAUTH";
export type DepositMethod = "CASH" | "WECHAT" | "ALIPAY" | "UNIONPAY" | "STORE_VALUE";
export type DepositStatus =
  | "HELD"
  | "APPLIED"
  | "PARTIALLY_APPLIED"
  | "REFUNDED"
  | "PARTIALLY_REFUNDED"
  | "RELEASED"
  | "VOID"
  | "FORFEITED"
  | "EXPIRED";
export type ReleaseCause = "MANUAL" | "SETTLED" | "EXPIRED";

export interface DepositTransaction {
  id: number;
  action: string;
  amount_cents: number;
  method: string;
  ref_no?: string | null;
  bill_id?: number | null;
  operator: string;
  note?: string | null;
  created_at: string;
}

export interface Deposit {
  id: string;
  tenant_id: string;
  hotel_id: string;
  deposit_no: string;
  booking_id?: string | null;
  room_no?: string | null;
  bill_id?: string | null;
  kind: DepositKind;
  method: DepositMethod;
  amount_cents: number;
  applied_cents: number;
  refunded_cents: number;
  forfeited_cents: number;
  available_cents: number;
  status: DepositStatus;
  release_cause?: ReleaseCause | null;
  currency: string;
  ref_no?: string | null;
  operator: string;
  expires_at?: string | null;
  released_at?: string | null;
  captured_at?: string | null;
  voided_at?: string | null;
  version: number;
  note?: string | null;
  created_at: string;
  transactions: DepositTransaction[];
}

export interface DepositIn {
  hotel_id: number;
  booking_id?: number | null;
  room_no?: string | null;
  bill_id?: number | null;
  kind: DepositKind;
  method: DepositMethod;
  amount: number;
  ref_no?: string | null;
  currency?: string;
  operator?: string;
  note?: string | null;
}

export interface DepositApplyIn {
  amount: number;
  target_bill_id?: number | null;
  operator?: string;
  expected_version?: number;
}

export interface DepositRefundIn {
  amount: number;
  operator?: string;
  note?: string | null;
  expected_version?: number;
}

export interface DepositReleaseIn {
  operator?: string;
  cause: ReleaseCause;
  expected_version?: number;
}

export interface DepositVoidIn {
  operator?: string;
  reason?: string | null;
  expected_version?: number;
}

export interface AutoReleaseIn {
  hotel_id?: number;
  days?: number;
  operator?: string;
}

export interface AutoReleaseOut {
  released: number;
  ids: number[];
}

// ---------- M34d 全局搜索 ----------

export type SearchEntityType =
  | "guest"
  | "booking"
  | "room"
  | "bill"
  | "member"
  | "group"
  | "notification";

export interface SearchResultItem {
  type: SearchEntityType;
  id: number | string;
  title: string;
  subtitle: string;
  href: string;
  badge?: string | null;
  badge_color?: string | null;
}

export interface SearchResult {
  items: SearchResultItem[];
  total: number;
  by_type: Record<string, number>;
  query: string;
}
