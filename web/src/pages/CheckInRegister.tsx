import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  App,
  Button,
  Checkbox,
  Col,
  DatePicker,
  Descriptions,
  Empty,
  Input,
  InputNumber,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import {
  ArrowsAltOutlined,
  DollarOutlined,
  FileSearchOutlined,
  KeyOutlined,
  LinkOutlined,
  LogoutOutlined,
  PauseOutlined,
  PrinterOutlined,
  ReadOutlined,
  ReloadOutlined,
  SaveOutlined,
  SelectOutlined,
  UserAddOutlined,
} from "@ant-design/icons";
import dayjs, { Dayjs } from "dayjs";
import {
  listRooms,
  listRoomTypes,
  listBookings,
  receptionCheckIn,
  checkOutBooking,
  extendStayBooking,
  changeRoomBooking,
  updateBookingExtras,
  setRoomDnd,
  settleToMaster,
  listRoomStateEvents,
  listBookingLogs,
  listRoomChangesByBooking,
  listStayExtensionsByBooking,
} from "../api/endpoints";
import type { Room, RoomType, Booking, RoomChange, StayExtension } from "../api/types";
import { useTenant } from "../store/tenant";
import { ROOM_STATE_LABELS, TRIGGER_LABELS } from "../domain/roomActions";
import { fmtCents } from "../utils/format";
// 必须带 .tsx 后缀：无后缀会优先解析到 format.ts（纯字符串工具），取不到组件。
import { CellAmount } from "../utils/format.tsx";
import DepositQuickPanel from "../components/deposit/DepositQuickPanel";

const ID_TYPES = [
  { value: "ID", label: "居民身份证" },
  { value: "PASSPORT", label: "护照" },
  { value: "OFFICER", label: "军官证" },
  { value: "OTHER", label: "其他" },
];

const ETHNICITIES = ["汉族", "壮族", "满族", "回族", "苗族", "维吾尔族", "土家族", "彝族", "蒙古族", "藏族", "其他"];

// 批次②：客源类型选项（value 为后端枚举码）
const GUEST_SOURCE_OPTIONS = [
  { value: "WI", label: "上门散客" },
  { value: "IM", label: "个人会员" },
  { value: "CM", label: "公司会员" },
  { value: "LP", label: "长包" },
  { value: "GP", label: "团队" },
  { value: "AM", label: "中介协议" },
];

// 批次③：换房原因选项
const CHANGE_ROOM_REASONS = [
  { value: "客人要求", label: "客人要求" },
  { value: "设施故障", label: "设施故障" },
  { value: "升级", label: "升级" },
  { value: "噪音", label: "噪音" },
  { value: "其他", label: "其他" },
];

/** 分区标题：蓝/红小节标题 */
function SectionTitle({ text, red, extra }: { text: string; red?: boolean; extra?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 8px" }}>
      <span
        style={{
          width: 3,
          height: 14,
          background: red ? "#cf1322" : "#1677ff",
          borderRadius: 2,
          display: "inline-block",
        }}
      />
      <span style={{ fontWeight: 600, fontSize: 13.5, color: red ? "#cf1322" : "#1f2329" }}>{text}</span>
      {extra}
    </div>
  );
}

/** C/S 版登记单（复刻绿云布局）：顶部页签 + 左侧操作栏 + 右侧表单 + 底部随行人表格 */
export default function CheckInRegister() {
  const { tenantCode } = useTenant();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { message, modal } = App.useApp();

  const roomNoParam = params.get("room_no") || "";
  const bookingIdParam = params.get("booking_id");

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);

  const [roomNo, setRoomNo] = useState<string>(roomNoParam);
  // ⚠️ 雪花 ID 必须全程以字符串传递，绝对不要 Number() 化。
  // 订单 ID 是 18 位（如 354986244532338688），远超 Number.MAX_SAFE_INTEGER。
  // 虽然 double 本身能精确存下它（BigInt(Number(s)) 与原值相等），但 JS 把 number
  // 转回字符串时按「最短往返」只打印 17 位有效数字 → ...338688 会变成 ...338700。
  // 拼进 URL 后后端拿到的是不存在的 ID，且只静默返回空列表（不报错），极难发现。
  // 后端 JSON 里 ID 本来就是字符串（{"id":"354986244532338688"}），照原样传即可。
  const [bookingId, setBookingId] = useState<string | null>(bookingIdParam || null);

  // 顶部页签
  const [topTab, setTopTab] = useState("info");
  const [logData, setLogData] = useState<any[]>([]);
  const [logLoading, setLogLoading] = useState(false);

  // 弹窗：续住 / 换房 / 随行人
  const [extendOpen, setExtendOpen] = useState(false);
  const [newCheckOut, setNewCheckOut] = useState<Dayjs | null>(null);
  const [changeOpen, setChangeOpen] = useState(false);
  const [newRoomNo, setNewRoomNo] = useState<string | null>(null);
  const [changeReason, setChangeReason] = useState<string | undefined>(undefined);
  const [compOpen, setCompOpen] = useState(false);
  const [compInput, setCompInput] = useState("");
  const [acting, setActing] = useState(false);

  // 批次③：在住单换房/续住记录
  const [roomChanges, setRoomChanges] = useState<RoomChange[]>([]);
  const [roomChangesLoading, setRoomChangesLoading] = useState(false);
  const [stayExtensions, setStayExtensions] = useState<StayExtension[]>([]);
  const [stayExtensionsLoading, setStayExtensionsLoading] = useState(false);
  // 最新一次续住回显（续住成功后即时提示用户）
  const [latestExtension, setLatestExtension] = useState<StayExtension | null>(null);
  const [latestChange, setLatestChange] = useState<RoomChange | null>(null);

  // 客人登记信息
  const [form, setForm] = useState({
    guest_name: "",
    gender: "M",
    nationality: "中国",
    ethnicity: "汉族",
    id_type: "ID",
    id_no: "",
    birthday: "",
    guest_phone: "",
    address: "",
    email: "",
    note: "",
    check_out_date: dayjs().add(1, "day"),
    room_type_id: null as string | null,
    hourly: false as boolean,
    hourlyHours: 4 as number,
    // 批次② 核心实体字段补全
    guest_source_type: null as string | null,
    member_no: "",
    is_vip: false as boolean,
    is_secret: false as boolean,
    is_print_real_price: true as boolean, // 默认打印真实价；勾选“价格保密”时置 false
    is_add_point: true as boolean,
    is_quick_depart: false as boolean,
    is_guarantee: false as boolean,
    guarantee_hold_until: "",
  });

  const load = useCallback(async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [rm, rt, bk] = await Promise.all([listRooms(tenantCode), listRoomTypes(tenantCode), listBookings(tenantCode)]);
      setRooms(rm);
      setRoomTypes(rt);
      setBookings(bk);
      // 排房预抵自动带入
      if (!bookingId && roomNoParam) {
        const matched = bk
          .filter((b) => b.room_no === roomNoParam && b.status === "created")
          .sort((a, b) => (a.check_in_date || "").localeCompare(b.check_in_date || ""))[0];
        if (matched) {
          setBookingId(matched.id);
          setForm((f) => ({
            ...f,
            guest_name: matched.guest_name || f.guest_name,
            guest_phone: matched.guest_phone || f.guest_phone,
            room_type_id: matched.room_type_id ? String(matched.room_type_id) : f.room_type_id,
            check_out_date: matched.check_out_date ? dayjs(matched.check_out_date) : f.check_out_date,
          }));
          message.info(`房间 ${roomNoParam} 已有排房预抵订单 #${matched.id}，已自动带入`);
        }
      }
      // 预订模式预填
      if (bookingId) {
        const b = bk.find((x) => String(x.id) === String(bookingId));
        if (b) {
          setForm((f) => ({
            ...f,
            guest_name: b.guest_name || "",
            guest_phone: b.guest_phone || "",
            room_type_id: b.room_type_id ? String(b.room_type_id) : null,
            check_out_date: dayjs(b.check_out_date),
            // 批次② 核心实体字段补全：从预订回显
            guest_source_type: b.guest_source_type ?? f.guest_source_type,
            member_no: b.member_no ?? "",
            is_vip: b.is_vip ?? false,
            is_secret: b.is_secret ?? false,
            is_print_real_price: b.is_print_real_price ?? true,
            is_add_point: b.is_add_point ?? true,
            is_quick_depart: b.is_quick_depart ?? false,
            is_guarantee: b.is_guarantee ?? false,
            guarantee_hold_until: b.guarantee_hold_until ?? "",
          }));
          if (!roomNo && b.room_no) setRoomNo(b.room_no);
        }
      }
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, bookingId, roomNoParam]);

  useEffect(() => {
    load();
  }, [load]);

  // 同 Tab 二次跳转：房号参数变化即重置
  const lastRoomRef = useRef<string>("");
  // 「补交押金(O)」按钮定位锚点：滚动到内联押金面板，不再错跳无押金能力的收银页
  const depositPanelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!roomNoParam || roomNoParam === lastRoomRef.current) return;
    lastRoomRef.current = roomNoParam;
    setRoomNo(roomNoParam);
    setBookingId(null);
    setForm((f) => ({ ...f, room_type_id: null }));
  }, [roomNoParam]);

  const room = useMemo(() => rooms.find((r) => r.room_no === roomNo), [rooms, roomNo]);
  const roomType = useMemo(
    () => roomTypes.find((rt) => String(rt.id) === String(room?.room_type_id ?? form.room_type_id)),
    [roomTypes, room, form.room_type_id]
  );
  const booking = useMemo(() => bookings.find((b) => String(b.id) === String(bookingId)), [bookings, bookingId]);
  const stayBooking = useMemo(
    () => bookings.find((b) => b.room_no === roomNo && b.status === "checked_in") || null,
    [bookings, roomNo]
  );
  const isStay = room?.state === "occupied" && !!stayBooking;
  // 押金面板绑定的登记单：在住单优先，其次预订单，再退回 URL 带入的 booking_id；散客新建时为 null
  const depositBookingId = useMemo<string | null>(() => {
    const id = stayBooking?.id ?? booking?.id ?? bookingId;
    return id != null ? String(id) : null;
  }, [stayBooking, booking, bookingId]);
  // 在住模式：把登记单客人信息回填表单（只读展示）
  useEffect(() => {
    if (!isStay || !stayBooking) return;
    setForm((f) => ({
      ...f,
      guest_name: stayBooking.guest_name || f.guest_name,
      guest_phone: stayBooking.guest_phone || f.guest_phone,
      room_type_id: stayBooking.room_type_id ? String(stayBooking.room_type_id) : f.room_type_id,
      check_out_date: stayBooking.check_out_date ? dayjs(stayBooking.check_out_date) : f.check_out_date,
      // 批次② 核心实体字段补全：从在住单回显
      guest_source_type: stayBooking.guest_source_type ?? f.guest_source_type,
      member_no: stayBooking.member_no ?? "",
      is_vip: stayBooking.is_vip ?? false,
      is_secret: stayBooking.is_secret ?? false,
      is_print_real_price: stayBooking.is_print_real_price ?? true,
      is_add_point: stayBooking.is_add_point ?? true,
      is_quick_depart: stayBooking.is_quick_depart ?? false,
      is_guarantee: stayBooking.is_guarantee ?? false,
      guarantee_hold_until: stayBooking.guarantee_hold_until ?? "",
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStay, stayBooking?.id]);
  const createdBookings = useMemo(() => bookings.filter((b) => b.status === "created"), [bookings]);
  const assignableRooms = useMemo(
    () => rooms.filter((r) => ["vacant_clean", "vacant_dirty", "arrival_locked"].includes(r.state)),
    [rooms]
  );
  const changeTargets = useMemo(
    () => rooms.filter((r) => r.state === "vacant_clean" && r.room_no !== roomNo),
    [rooms, roomNo]
  );

  // 实际到店时间：房态事件 check_in 的发生时刻
  const [arrivalAt, setArrivalAt] = useState<string | null>(null);
  useEffect(() => {
    if (!roomNo) {
      setArrivalAt(null);
      return;
    }
    listRoomStateEvents(tenantCode, roomNo, 30)
      .then((evs) => {
        const ev = [...evs].reverse().find((e) => e.trigger === "check_in");
        setArrivalAt(ev ? ev.occurred_at.replace("T", " ").slice(0, 16) : null);
      })
      .catch(() => setArrivalAt(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomNo, tenantCode]);

  // 操作日志（切到该页签时加载）：登记单审计流水优先，无单则退房态流转
  const logBooking = stayBooking ?? booking;
  useEffect(() => {
    if (topTab !== "log") return;
    setLogLoading(true);
    if (logBooking) {
      listBookingLogs(tenantCode, String(logBooking.id), 50)
        .then(setLogData)
        .catch((e: unknown) => message.error((e as Error).message))
        .finally(() => setLogLoading(false));
    } else if (roomNo) {
      listRoomStateEvents(tenantCode, roomNo, 50)
        .then(setLogData)
        .catch((e: unknown) => message.error((e as Error).message))
        .finally(() => setLogLoading(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topTab, roomNo, logBooking?.id]);

  // 批次③：加载该登记单的换房记录 + 续住记录（在住模式下）
  const loadRoomChangeLog = useCallback(
    async (bookingIdVal: number | string) => {
      if (!tenantCode) return;
      setRoomChangesLoading(true);
      try {
        const list = await listRoomChangesByBooking(tenantCode, String(bookingIdVal));
        setRoomChanges(list);
      } catch (e: unknown) {
        message.error((e as Error).message || "加载换房记录失败");
        setRoomChanges([]);
      } finally {
        setRoomChangesLoading(false);
      }
    },
    [tenantCode]
  );

  const loadStayExtensionLog = useCallback(
    async (bookingIdVal: number | string) => {
      if (!tenantCode) return;
      setStayExtensionsLoading(true);
      try {
        const list = await listStayExtensionsByBooking(tenantCode, String(bookingIdVal));
        setStayExtensions(list);
      } catch (e: unknown) {
        message.error((e as Error).message || "加载续住记录失败");
        setStayExtensions([]);
      } finally {
        setStayExtensionsLoading(false);
      }
    },
    [tenantCode]
  );

  // 在住单变化时刷新换房/续住记录
  useEffect(() => {
    if (!stayBooking) {
      setRoomChanges([]);
      setStayExtensions([]);
      return;
    }
    loadRoomChangeLog(stayBooking.id);
    loadStayExtensionLog(stayBooking.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stayBooking?.id]);

  const nights = useMemo(() => {
    const diff = form.check_out_date.diff(dayjs().startOf("day"), "day");
    return diff > 0 ? diff : 1;
  }, [form.check_out_date]);

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const reload = () => {
    setBookingId(null);
    load();
  };

  const onSave = async () => {
    if (!roomNo) return message.error("请选择房号");
    if (!form.guest_name.trim()) return message.error("请填写客人姓名");
    if (!form.id_no.trim()) return message.error("请填写证件号码");
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = {
        room_no: roomNo,
        operator: "front_desk",
        guest_name: form.guest_name.trim(),
        guest_phone: form.guest_phone.trim() || null,
        id_type: form.id_type,
        id_no: form.id_no.trim(),
        gender: form.gender,
        birthday: form.birthday || null,
        nationality: form.nationality || null,
        ethnicity: form.ethnicity || null,
        email: form.email.trim() || null,
        address: form.address.trim() || null,
        note: form.note.trim() || null,
        // 批次② 核心实体字段补全
        guest_source_type: form.guest_source_type || null,
        member_no: form.member_no.trim() || null,
        is_vip: form.is_vip,
        is_secret: form.is_secret,
        is_quick_depart: form.is_quick_depart,
        is_print_real_price: form.is_print_real_price,
        is_add_point: form.is_add_point,
        is_guarantee: form.is_guarantee,
        guarantee_hold_until: form.guarantee_hold_until.trim() || null,
      };
      if (booking) {
        // ⚠️ 不要 Number()：JSON 序列化会把它打成 17 位有效数字（...338700），后端静默查不到
        payload.booking_id = String(booking.id);
      } else if (form.hourly) {
        // M32.17：钟点房——同日入住退房，按小时计价，不占过夜可售房量
        payload.room_type_id = form.room_type_id ?? room?.room_type_id;
        payload.check_in_date = dayjs().format("YYYY-MM-DD");
        payload.check_out_date = dayjs().format("YYYY-MM-DD");
        payload.stay_type = "hourly";
        payload.hourly_hours = form.hourlyHours;
      } else {
        payload.room_type_id = form.room_type_id ?? room?.room_type_id;
        payload.check_in_date = dayjs().format("YYYY-MM-DD");
        payload.check_out_date = form.check_out_date.format("YYYY-MM-DD");
      }
      const b = await receptionCheckIn(tenantCode, payload as never);
      message.success(`登记入住成功：${b.guest_name} · ${b.room_no}`);
      navigate("/rooms");
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  // ---------- 在住业务动作 ----------
  const doExtend = async () => {
    if (!stayBooking || !newCheckOut) return;
    setActing(true);
    try {
      await extendStayBooking(tenantCode, String(stayBooking.id), newCheckOut.format("YYYY-MM-DD"));
      message.success(`续住成功，预离延至 ${newCheckOut.format("YYYY-MM-DD")}`);
      setExtendOpen(false);
      // 批次③：刷新续住记录，并把最新一条置顶
      await loadStayExtensionLog(stayBooking.id);
      try {
        const list = await listStayExtensionsByBooking(tenantCode, String(stayBooking.id));
        if (list.length) setLatestExtension(list[0]);
      } catch {
        /* noop */
      }
      reload();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  };

  const doChangeRoom = async () => {
    if (!stayBooking || !newRoomNo) return;
    if (!changeReason) {
      message.error("请选择换房原因");
      return;
    }
    setActing(true);
    try {
      await changeRoomBooking(
        tenantCode,
        String(stayBooking.id),
        newRoomNo,
        changeReason
      );
      message.success(`换房成功：${stayBooking.room_no} → ${newRoomNo}`);
      setChangeOpen(false);
      setNewRoomNo(null);
      setChangeReason(undefined);
      setRoomNo(newRoomNo);
      window.history.replaceState(null, "", `/check-in-register?room_no=${newRoomNo}`);
      // 批次③：刷新换房记录，最新一条置顶
      await loadRoomChangeLog(stayBooking.id);
      try {
        const list = await listRoomChangesByBooking(tenantCode, String(stayBooking.id));
        if (list.length) setLatestChange(list[0]);
      } catch {
        /* noop */
      }
      reload();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  };

  const doAddCompanion = async () => {
    if (!stayBooking) return;
    const names = compInput
      .split(/[、,，\s]+/)
      .map((x) => x.trim())
      .filter(Boolean);
    if (!names.length) return message.error("请输入同住人姓名");
    setActing(true);
    try {
      const merged = [...new Set([...(stayBooking.companion_names || []), ...names])];
      await updateBookingExtras(tenantCode, String(stayBooking.id), { companion_names: merged });
      message.success(`已添加同住人：${names.join("、")}`);
      setCompOpen(false);
      setCompInput("");
      reload();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  };

  const doCheckout = () => {
    if (!stayBooking) return;
    modal.confirm({
      title: `确认为 ${stayBooking.guest_name}（${stayBooking.room_no}）办理结账退房？`,
      content: "将结清房费并释放房间；如有账目请先在账务信息页处理。",
      okText: "结账退房",
      onOk: async () => {
        try {
          await checkOutBooking(tenantCode, String(stayBooking.id));
          message.success(`退房成功：${stayBooking.room_no}`);
          navigate("/rooms");
        } catch (e: unknown) {
          message.error((e as Error).message);
        }
      },
    });
  };

  if (loading) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: 300 }}>
        <Spin tip="加载中…" />
      </div>
    );
  }

  // 左侧操作按钮
  const sideBtn = (icon: React.ReactNode, label: string, onClick?: () => void, disabled = false, danger = false) => (
    <Button
      block
      size="small"
      icon={icon}
      disabled={disabled}
      danger={danger}
      onClick={onClick}
      style={{ textAlign: "left", marginBottom: 4, paddingLeft: 10 }}
    >
      {label}
    </Button>
  );

  const stateLabel = room ? (ROOM_STATE_LABELS[room.state as keyof typeof ROOM_STATE_LABELS] ?? room.state) : "—";
  // M32.17b：钟点房显示真实到离店时刻（离店=到店时刻+时长，跨日自动进位）
  const hourlyDepart = (() => {
    if (!stayBooking || stayBooking.stay_type !== "hourly" || !stayBooking.hourly_start_time) return null;
    const [hh, mm] = stayBooking.hourly_start_time.split(":").map(Number);
    const d = dayjs(`${stayBooking.check_in_date} 00:00`).add(hh * 60 + mm + (stayBooking.hourly_hours ?? 0) * 60, "minute");
    return d.format("YYYY-MM-DD HH:mm");
  })();
  const arrivalDisplay = isStay
    ? stayBooking?.stay_type === "hourly"
      ? `${stayBooking.check_in_date} ${stayBooking.hourly_start_time ?? "—"}`
      : arrivalAt ?? `${stayBooking?.check_in_date} —`
    : dayjs().format("YYYY-MM-DD HH:mm");
  const departDisplay = isStay && stayBooking
    ? stayBooking.stay_type === "hourly"
      ? hourlyDepart ?? `${stayBooking.check_out_date} —`
      : `${stayBooking.check_out_date} 12:00`
    : undefined;
  const companions: { key: string; name: string }[] = (stayBooking?.companion_names || []).map((n, i) => ({
    key: String(i),
    name: n,
  }));

  const infoTab = (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
      {/* ===== 左侧：房间信息 + 操作栏 ===== */}
      <div style={{ width: 168, flexShrink: 0 }}>
        <div
          style={{
            border: "1px solid #e3e6eb",
            borderRadius: 8,
            padding: "10px 12px",
            marginBottom: 10,
            background: isStay ? "#f6fbff" : "#fafbfc",
          }}
        >
          <div style={{ fontSize: 12, color: "#8a919c", marginBottom: 2 }}>房间信息</div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {roomNo || "未选房"}
          </Typography.Title>
          <div style={{ fontSize: 12.5, color: "#1f2329", marginTop: 2 }}>{roomType?.name || "—"}</div>
          <div style={{ fontSize: 12.5, color: "#1f2329" }}>
            房价 {roomType ? fmtCents(roomType.base_price ?? 0) : "—"}
          </div>
          <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <Tag color={isStay ? "processing" : room?.state === "vacant_clean" ? "success" : "default"}>
              {isStay ? "在住" : stateLabel}
            </Tag>
            {room?.dnd ? <Tag color="orange">免打扰</Tag> : null}
            {stayBooking?.link_group_id ? (
              <Tag color="purple">{stayBooking.is_link_master ? "联房·主房" : "联房·从房"}</Tag>
            ) : null}
            {stayBooking?.stay_type === "hourly" ? (
              <Tag color="cyan">钟点房·{stayBooking.hourly_hours ?? "—"}小时</Tag>
            ) : null}
          </div>

        </div>

        <div style={{ fontSize: 12, color: "#8a919c", margin: "2px 0 4px" }}>基本操作</div>
        {sideBtn(<SaveOutlined />, "保存(S)", onSave, isStay)}
        {sideBtn(<PrinterOutlined />, "打印(P)", () => window.print())}
        {sideBtn(<DollarOutlined />, "补交押金(O)", () => {
          if (!depositBookingId) {
            message.warning("该登记单尚未生成，请先办理入住后再收押金");
            return;
          }
          depositPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, !isStay)}
        {sideBtn(
          <SelectOutlined />,
          "续住/延住(Y)",
          () => {
            if (!stayBooking) return;
            setNewCheckOut(dayjs(stayBooking.check_out_date).add(1, "day"));
            setExtendOpen(true);
          },
          !isStay
        )}
        {sideBtn(<LogoutOutlined />, "结账退房(T)", doCheckout, !isStay, true)}

        <div style={{ fontSize: 12, color: "#8a919c", margin: "8px 0 4px" }}>扩展操作</div>
        {sideBtn(<UserAddOutlined />, "增加随行人(A)", () => setCompOpen(true), !isStay)}
        {sideBtn(
          <ArrowsAltOutlined />,
          "换房/升级(H)",
          () => {
            setNewRoomNo(null);
            setChangeReason(undefined);
            setChangeOpen(true);
          },
          !isStay
        )}
        {sideBtn(
          <PauseOutlined />,
          room?.dnd ? "取消免打扰(D)" : "设为免打扰(D)",
          async () => {
            if (!room) return;
            try {
              await setRoomDnd(tenantCode, room.room_no, !room.dnd);
              message.success(!room.dnd ? "已设为免打扰" : "已取消免打扰");
              load();
            } catch (e: unknown) {
              message.error((e as Error).message);
            }
          }
        )}
        {sideBtn(<LinkOutlined />, "团队/关联(L)", undefined, true)}
        {sideBtn(
          <DollarOutlined />,
          "并入主房(M)",
          async () => {
            if (!stayBooking?.link_group_id || stayBooking.is_link_master || !room) return;
            try {
              const out = await settleToMaster(tenantCode, room.room_no);
              message.success(
                `已并入主房 ${out.master_room_no}：¥${(out.amount / 100).toFixed(2)}（从房余额归零，可正常退房）`
              );
              load();
            } catch (e: unknown) {
              message.error((e as Error).message);
            }
          },
          !isStay || !stayBooking?.link_group_id || !!stayBooking?.is_link_master
        )}
        {sideBtn(<KeyOutlined />, "制房卡(K)", () => message.info("暂未接入写卡硬件，请到前台制卡机操作"), true)}
        {sideBtn(<FileSearchOutlined />, "查看订单(I)", () => navigate("/bookings"))}
      </div>

      {/* ===== 右侧：表单区 ===== */}
      <div className="pms-panel" style={{ flex: 1, minWidth: 0, padding: "12px 16px" }}>
        {/* 基本信息 */}
        <SectionTitle text="基本信息" />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px 10px" }}>
          <div>
            <div style={{ marginBottom: 2 }}><Typography.Text type="danger">* </Typography.Text>客源门店</div>
            <Select size="small" style={{ width: "100%" }} value="hotel" disabled options={[{ value: "hotel", label: "本店" }]} />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}><Typography.Text type="danger">* </Typography.Text>客源</div>
            <Select
              size="small"
              style={{ width: "100%" }}
              value={bookingId ? "resv" : "walk_in"}
              disabled
              options={[
                { value: "walk_in", label: "上门客" },
                { value: "resv", label: "预订" },
              ]}
            />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}><Typography.Text type="danger">* </Typography.Text>房号</div>
            <Select
              size="small"
              style={{ width: "100%" }}
              placeholder="选择可排房"
              value={roomNo || undefined}
              disabled={isStay}
              onChange={(v) => setRoomNo(v)}
              options={assignableRooms.map((r) => ({
                value: r.room_no,
                label: `${r.room_no} · ${ROOM_STATE_LABELS[r.state as keyof typeof ROOM_STATE_LABELS] ?? r.state}`,
              }))}
            />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}><Typography.Text type="danger">* </Typography.Text>房型</div>
            <Select
              size="small"
              style={{ width: "100%" }}
              placeholder="选择房型"
              value={
                form.room_type_id != null
                  ? String(form.room_type_id)
                  : room?.room_type_id != null
                  ? String(room.room_type_id)
                  : undefined
              }
              disabled={isStay}
              onChange={(v) => set({ room_type_id: String(v) })}
              options={roomTypes.map((rt) => ({ value: String(rt.id), label: rt.name }))}
            />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}>市场活动</div>
            <Input size="small" disabled placeholder="—" />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}><Typography.Text type="danger">* </Typography.Text>到店</div>
            <DatePicker
              size="small"
              style={{ width: "100%" }}
              showTime={{ format: "HH:mm" }}
              format="YYYY-MM-DD HH:mm"
              value={dayjs(isStay ? arrivalDisplay : dayjs().format("YYYY-MM-DD HH:mm"))}
              disabled={isStay}
              onChange={() => undefined}
            />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}>
              <Checkbox
                checked={form.hourly}
                disabled={isStay}
                onChange={(e) => set({ hourly: e.target.checked })}
                style={{ fontSize: 12 }}
              >
                钟点房
              </Checkbox>
            </div>
            {form.hourly ? (
              <Select
                size="small"
                style={{ width: "100%" }}
                value={form.hourlyHours}
                disabled={isStay}
                onChange={(v) => set({ hourlyHours: v })}
                options={[1, 2, 3, 4, 5, 6, 8, 10, 12].map((h) => ({ value: h, label: `${h} 小时` }))}
              />
            ) : (
              <DatePicker
                size="small"
                style={{ width: "100%" }}
                showTime={{ format: "HH:mm", defaultValue: dayjs("12:00", "HH:mm") }}
                format="YYYY-MM-DD HH:mm"
                value={isStay && stayBooking ? dayjs(departDisplay) : form.check_out_date}
                disabled={isStay}
                onChange={(d: Dayjs | null) => d && set({ check_out_date: d })}
              />
            )}
          </div>
          <div>
            <div style={{ marginBottom: 2 }}>天数</div>
            <InputNumber size="small" style={{ width: "100%" }} value={nights} disabled />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}>房价</div>
            <Input size="small" value={roomType ? fmtCents(roomType.base_price ?? 0) : "—"} disabled />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <Button size="small" onClick={() => message.info("已按门市价刷新房价")}>
              刷新房价
            </Button>
          </div>
        </div>

        {!bookingId && !booking && !isStay && createdBookings.length > 0 && (
          <Select
            style={{ width: 380, marginTop: 8 }}
            size="small"
            placeholder="选择已有预订转预订入住（可清空保持散客）"
            allowClear
            value={undefined}
            onChange={(v) => v && setBookingId(String(v))}
            options={createdBookings.map((b) => ({
              value: String(b.id),
              label: `#${b.id} ${b.guest_name} · ${b.check_in_date}~${b.check_out_date}`,
            }))}
          />
        )}

        <div style={{ height: 1, background: "#f2f4f7", margin: "12px 0" }} />

        {/* 客人信息 */}
        <SectionTitle
          red
          text="客人信息"
          extra={
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              （可通过身份证读卡器读取，也可手动输入）
            </Typography.Text>
          }
        />
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px 10px" }}>
            <div>
              <div style={{ marginBottom: 2 }}><Typography.Text type="danger">* </Typography.Text>姓名</div>
              <Input size="small" value={form.guest_name} onChange={(e) => set({ guest_name: e.target.value })} placeholder="客人姓名" disabled={isStay} />
            </div>
            <div>
              <div style={{ marginBottom: 2 }}>性别</div>
              <Radio.Group
                size="small"
                value={form.gender}
                disabled={isStay}
                onChange={(e) => set({ gender: e.target.value })}
                options={[
                  { value: "F", label: "女" },
                  { value: "M", label: "男" },
                ]}
              />
            </div>
            <div>
              <div style={{ marginBottom: 2 }}>国籍</div>
              <Input size="small" value={form.nationality} onChange={(e) => set({ nationality: e.target.value })} disabled={isStay} />
            </div>
            <div>
              <div style={{ marginBottom: 2 }}>民族</div>
              <Select
                size="small"
                style={{ width: "100%" }}
                value={form.ethnicity}
                disabled={isStay}
                onChange={(v) => set({ ethnicity: v })}
                options={ETHNICITIES.map((x) => ({ value: x, label: x }))}
              />
            </div>
            <div>
              <div style={{ marginBottom: 2 }}>生日</div>
              <Input size="small" value={form.birthday} onChange={(e) => set({ birthday: e.target.value })} placeholder="YYYY-MM-DD" disabled={isStay} />
            </div>
            <div>
              <div style={{ marginBottom: 2 }}><Typography.Text type="danger">* </Typography.Text>证件类型</div>
              <Select size="small" style={{ width: "100%" }} value={form.id_type} disabled={isStay} onChange={(v) => set({ id_type: v })} options={ID_TYPES} />
            </div>
            <div>
              <div style={{ marginBottom: 2 }}><Typography.Text type="danger">* </Typography.Text>证件号码</div>
              <Input size="small" value={form.id_no} onChange={(e) => set({ id_no: e.target.value })} placeholder="证件号码" disabled={isStay} />
            </div>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <Button size="small" icon={<ReadOutlined />} onClick={() => message.info("未检测到身份证读卡器，请手动输入")}>
                读卡
              </Button>
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <div style={{ marginBottom: 2 }}>地址</div>
              <Input size="small" value={form.address} onChange={(e) => set({ address: e.target.value })} disabled={isStay} />
            </div>
            <div>
              <div style={{ marginBottom: 2 }}>联系电话</div>
              <Input size="small" value={form.guest_phone} onChange={(e) => set({ guest_phone: e.target.value })} placeholder="手机号" disabled={isStay} />
            </div>
            <div>
              <div style={{ marginBottom: 2 }}>邮箱</div>
              <Input size="small" value={form.email} onChange={(e) => set({ email: e.target.value })} disabled={isStay} />
            </div>
          </div>
          {/* 证件照占位 */}
          <div
            style={{
              width: 110,
              flexShrink: 0,
              border: "1px dashed #d9dce1",
              borderRadius: 8,
              display: "grid",
              placeItems: "center",
              color: "#b3bac2",
              fontSize: 12,
            }}
          >
            没有图像数据
          </div>
        </div>

        {/* 押金行：接后端押金/预授权能力（M36 接线，取代原写死的四个禁用控件） */}
        <div ref={depositPanelRef}>
          <DepositQuickPanel bookingId={depositBookingId} roomNo={roomNo || null} />
        </div>
        {/* 批次② 核心实体字段补全：登记选项（原为 6 个禁用占位 Checkbox，现改为实时绑定 form 状态） */}
        <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
          <Checkbox
            checked={form.is_vip}
            disabled={isStay}
            onChange={(e) => set({ is_vip: e.target.checked })}
          >
            VIP客人
          </Checkbox>
          <Checkbox
            checked={form.is_secret}
            disabled={isStay}
            onChange={(e) => set({ is_secret: e.target.checked })}
          >
            信息保密
          </Checkbox>
          {/* 价格保密：勾选 = 不打印真实价 → is_print_real_price=false；默认不勾选（打印真实价） */}
          <Checkbox
            checked={!form.is_print_real_price}
            disabled={isStay}
            onChange={(e) => set({ is_print_real_price: !e.target.checked })}
          >
            价格保密(不打印真实价)
          </Checkbox>
          <Checkbox
            checked={form.is_add_point}
            disabled={isStay}
            onChange={(e) => set({ is_add_point: e.target.checked })}
          >
            计积分
          </Checkbox>
          <Checkbox
            checked={form.is_quick_depart}
            disabled={isStay}
            onChange={(e) => set({ is_quick_depart: e.target.checked })}
          >
            无停留离店
          </Checkbox>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12 }}>担保</span>
            <Switch
              size="small"
              checked={form.is_guarantee}
              disabled={isStay}
              onChange={(v) => set({ is_guarantee: v })}
            />
          </span>
        </div>
        <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
          <div style={{ width: 200 }}>
            <div style={{ fontSize: 12, marginBottom: 2, color: "#8a919c" }}>客源类型</div>
            <Select
              size="small"
              style={{ width: "100%" }}
              allowClear
              placeholder="选择客源类型"
              disabled={isStay}
              value={form.guest_source_type ?? undefined}
              onChange={(v) => set({ guest_source_type: v ?? null })}
              options={GUEST_SOURCE_OPTIONS}
            />
          </div>
          <div style={{ width: 200 }}>
            <div style={{ fontSize: 12, marginBottom: 2, color: "#8a919c" }}>会员号</div>
            <Input
              size="small"
              placeholder="会员卡号 / 会员号"
              disabled={isStay}
              value={form.member_no}
              onChange={(e) => set({ member_no: e.target.value })}
            />
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 12, marginBottom: 2, color: "#8a919c" }}>担保保留至（ISO8601，可空）</div>
            <Input
              size="small"
              placeholder="如 2024-01-15T18:00:00"
              disabled={isStay}
              value={form.guarantee_hold_until}
              onChange={(e) => set({ guarantee_hold_until: e.target.value })}
            />
          </div>
        </div>

        <div style={{ height: 1, background: "#f2f4f7", margin: "12px 0" }} />

        {/* 备注 / 习性 / 黑名单 */}
        <div style={{ display: "grid", gridTemplateColumns: "56px 1fr", gap: "6px 8px", alignItems: "start" }}>
          <div style={{ fontSize: 13, color: "#1f2329", paddingTop: 4 }}>备注</div>
          <Input.TextArea
            rows={1}
            value={form.note}
            onChange={(e) => set({ note: e.target.value })}
            placeholder="客人习性 / 特殊要求等（将存入客档备注）"
            disabled={isStay}
          />
          <div style={{ fontSize: 13, color: "#8a919c", paddingTop: 4 }}>习性</div>
          <Input.TextArea rows={1} disabled placeholder="—" />
          <div style={{ fontSize: 13, color: "#8a919c", paddingTop: 4 }}>黑名单</div>
          <Input.TextArea rows={1} disabled placeholder="—" />
        </div>

        {/* 底部：随行人表格 */}
        <div style={{ height: 1, background: "#f2f4f7", margin: "12px 0" }} />
        <Table
          size="small"
          pagination={false}
          rowKey="key"
          dataSource={companions}
          columns={[
            { title: "主单", render: () => (stayBooking ? `#${stayBooking.id}` : "—"), width: 90 },
            { title: "房号", render: () => roomNo, width: 80 },
            { title: "姓名", dataIndex: "name", key: "name" },
            { title: "状态", render: () => <Tag color="processing">随行</Tag>, width: 80 },
            { title: "客源", render: () => (stayBooking?.channel === "walk_in" ? "上门客" : stayBooking?.channel || "—"), width: 90 },
            { title: "房型", render: () => roomType?.name || "—", width: 110 },
            { title: "入住时间", render: () => arrivalDisplay, width: 150 },
            { title: "离店时间", render: () => departDisplay || form.check_out_date.format("YYYY-MM-DD 12:00"), width: 150 },
          ]}
          locale={{ emptyText: "无随行人" }}
        />

        {/* 保存按钮（散客/预订模式） */}
        {!isStay && (
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}>
            <Button type="primary" loading={submitting} onClick={onSave}>
              保存并办理入住(S)
            </Button>
            <Button onClick={() => navigate("/rooms")}>取消</Button>
            {!roomNo && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择房号" style={{ margin: 0 }} />}
          </div>
        )}
      </div>
    </div>
  );

  const folioTab = (
    <div className="pms-panel" style={{ padding: "12px 16px" }}>
      <SectionTitle text="账务信息" />
      {stayBooking ? (
        <>
          <Descriptions column={3} size="small">
            <Descriptions.Item label="房费总额">
              <CellAmount value={stayBooking.total_price ?? 0} />
            </Descriptions.Item>
            <Descriptions.Item label="入住日">{stayBooking.check_in_date}</Descriptions.Item>
            <Descriptions.Item label="预离">{stayBooking.check_out_date} 12:00</Descriptions.Item>
          </Descriptions>
          <Button type="primary" size="small" icon={<DollarOutlined />} onClick={() => navigate("/billing")} style={{ marginTop: 8 }}>
            前往收银结账
          </Button>
        </>
      ) : (
        <Typography.Text type="secondary">
          办理入住后此处显示账务概要；押金请在左侧「押金 / 预授权」面板操作，结账请前往收银页。
        </Typography.Text>
      )}
    </div>
  );

  const BOOKING_ACTION_LABELS: Record<string, string> = {
    "booking.extend_stay": "续住/延住",
    "booking.change_room": "换房/升级",
    "booking.update_stay_extras": "随行人/加床",
    "booking.check_in": "登记入住",
    "booking.checked_in": "登记入住",
    "booking.check_out": "结账退房",
    "booking.checked_out": "结账退房",
    "booking.cancel": "取消预订",
    "booking.cancelled": "取消预订",
    "booking.noshow": "未到标记",
  };

  // 批次③：换房/续住记录 tab
  const stayRecordsTab = (
    <div className="pms-panel" style={{ padding: "12px 16px" }}>
      <SectionTitle text="换房记录" extra={
        latestChange ? <Tag color="blue">最新：{latestChange.from_room_no} → {latestChange.to_room_no}</Tag> : null
      } />
      <Table<RoomChange>
        size="small"
        loading={roomChangesLoading}
        rowKey="id"
        pagination={{ pageSize: 5, showSizeChanger: false }}
        dataSource={roomChanges}
        locale={{ emptyText: "该登记单暂无换房记录" }}
        columns={[
          {
            title: "时间",
            dataIndex: "created_at",
            width: 160,
            render: (v: string) => (v ? v.replace("T", " ").slice(0, 19) : "—"),
          },
          {
            title: "原房号 → 新房号",
            width: 200,
            render: (_, r) => (
              <span>
                <Tag>{r.from_room_no ?? "—"}</Tag>
                <span style={{ margin: "0 4px" }}>→</span>
                <Tag color="blue">{r.to_room_no ?? "—"}</Tag>
              </span>
            ),
          },
          {
            title: "差价（元）",
            dataIndex: "price_diff_cents",
            width: 110,
            render: (v: number) => fmtCents(v ?? 0),
          },
          { title: "原因", dataIndex: "reason", render: (v: string) => v || "—" },
          { title: "操作人", dataIndex: "operator", width: 110 },
        ]}
      />

      <div style={{ height: 1, background: "#f2f4f7", margin: "16px 0" }} />

      <SectionTitle text="续住记录" extra={
        latestExtension ? <Tag color="blue">最新延长至 {latestExtension.end_date}（+{latestExtension.nights ?? 0} 晚）</Tag> : null
      } />
      <Table<StayExtension>
        size="small"
        loading={stayExtensionsLoading}
        rowKey="id"
        pagination={{ pageSize: 5, showSizeChanger: false }}
        dataSource={stayExtensions}
        locale={{ emptyText: "该登记单暂无续住记录" }}
        columns={[
          {
            title: "时间",
            dataIndex: "created_at",
            width: 160,
            render: (v: string) => (v ? v.replace("T", " ").slice(0, 19) : "—"),
          },
          {
            title: "起始日 → 截止日",
            width: 230,
            render: (_, r) => (
              <span>
                <Tag>{r.start_date ?? "—"}</Tag>
                <span style={{ margin: "0 4px" }}>→</span>
                <Tag color="blue">{r.end_date ?? "—"}</Tag>
              </span>
            ),
          },
          {
            title: "新增间夜",
            dataIndex: "nights",
            width: 90,
            render: (v: number) => v ?? 0,
          },
          {
            title: "新增金额（元）",
            dataIndex: "added_amount_cents",
            width: 130,
            render: (v: number) => fmtCents(v ?? 0),
          },
          { title: "操作人", dataIndex: "operator", width: 110 },
        ]}
      />
    </div>
  );

  const logTab = (
    <div className="pms-panel" style={{ padding: "12px 16px" }}>
      <SectionTitle
        text={logBooking ? `登记单操作日志 · #${logBooking.id} ${logBooking.guest_name || ""}` : "操作日志（房态流转参考）"}
      />
      <Table
        size="small"
        loading={logLoading}
        rowKey="id"
        pagination={{ pageSize: 8, showSizeChanger: false }}
        dataSource={logData}
        locale={{ emptyText: logBooking ? "该登记单暂无操作记录" : "尚未生成登记单；办理入住后此处显示该单的操作日志" }}
        columns={
          logBooking
            ? [
                { title: "时间", dataIndex: "created_at", width: 160, render: (v: string) => (v ? v.replace("T", " ").slice(0, 19) : "—") },
                {
                  title: "操作",
                  dataIndex: "action",
                  width: 130,
                  render: (v: string) => BOOKING_ACTION_LABELS[v] ?? v,
                },
                { title: "操作人", dataIndex: "actor", width: 110 },
                {
                  title: "结果",
                  dataIndex: "result",
                  width: 80,
                  render: (v: string) =>
                    v === "failure" ? <Tag color="error">失败</Tag> : <Tag color="success">成功</Tag>,
                },
                {
                  title: "详情",
                  dataIndex: "detail",
                  render: (v: Record<string, unknown>) =>
                    v && Object.keys(v).length ? (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {JSON.stringify(v)}
                      </Typography.Text>
                    ) : (
                      "—"
                    ),
                },
              ]
            : [
                { title: "时间", dataIndex: "occurred_at", width: 150, render: (v: string) => (v ? v.replace("T", " ").slice(0, 19) : "—") },
                {
                  title: "操作",
                  dataIndex: "trigger",
                  width: 110,
                  render: (v: string) => TRIGGER_LABELS[v as keyof typeof TRIGGER_LABELS] ?? v,
                },
                {
                  title: "状态流转",
                  key: "flow",
                  render: (_: unknown, rec: any) => (
                    <span>
                      {ROOM_STATE_LABELS[rec.from_state as keyof typeof ROOM_STATE_LABELS] ?? rec.from_state} →{" "}
                      {ROOM_STATE_LABELS[rec.to_state as keyof typeof ROOM_STATE_LABELS] ?? rec.to_state}
                    </span>
                  ),
                },
                { title: "操作人", dataIndex: "operator", width: 100 },
              ]
        }
      />
    </div>
  );

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto" }}>
      {/* 页头：对齐 Dashboard / Reports（标题 + 副标题 + 工具条） */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: 16,
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <Typography.Title level={4} style={{ margin: 0, marginBottom: 4 }}>
            入住登记
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            散客 / 预订办理 · 分配房 · 随行人 · 账务与日志
          </Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      <Tabs
        activeKey={topTab}
        onChange={setTopTab}
        size="small"
        items={[
          { key: "info", label: "基本信息(1)", children: infoTab },
          { key: "folio", label: "账务信息(2)", children: folioTab },
          { key: "log", label: "操作日志(3)", children: logTab },
          { key: "stay-records", label: "换房/续住(4)", children: stayRecordsTab },
        ]}
      />

      {/* 续住弹窗 */}
      <Modal
        title={`续住 · ${stayBooking?.room_no || ""} ${stayBooking?.guest_name || ""}`}
        open={extendOpen}
        onOk={doExtend}
        onCancel={() => setExtendOpen(false)}
        confirmLoading={acting}
        okText="确认续住"
        width={380}
      >
        <div style={{ marginBottom: 6 }}>当前预离：{stayBooking?.check_out_date}</div>
        <DatePicker style={{ width: "100%" }} value={newCheckOut} onChange={(d: Dayjs | null) => d && setNewCheckOut(d)} format="YYYY-MM-DD" />
      </Modal>

      {/* 换房弹窗 */}
      <Modal
        title={`换房 · ${stayBooking?.room_no || ""} ${stayBooking?.guest_name || ""}`}
        open={changeOpen}
        onOk={doChangeRoom}
        onCancel={() => {
          setChangeOpen(false);
          setNewRoomNo(null);
          setChangeReason(undefined);
        }}
        confirmLoading={acting}
        okText="确认换房"
        width={420}
      >
        <div style={{ marginBottom: 8 }}>
          <div style={{ marginBottom: 4 }}>目标房号</div>
          <Select
            style={{ width: "100%" }}
            placeholder="选择目标空净房"
            value={newRoomNo ?? undefined}
            onChange={(v) => setNewRoomNo(v)}
            options={changeTargets.map((r) => ({
              value: r.room_no,
              label: `${r.room_no} · ${roomTypes.find((rt) => String(rt.id) === String(r.room_type_id))?.name ?? ""}`,
            }))}
          />
        </div>
        <div>
          <div style={{ marginBottom: 4 }}>
            <Typography.Text type="danger">* </Typography.Text>换房原因（必填）
          </div>
          <Select
            style={{ width: "100%" }}
            placeholder="选择换房原因"
            value={changeReason}
            onChange={(v) => setChangeReason(v)}
            options={CHANGE_ROOM_REASONS}
          />
        </div>
      </Modal>

      {/* 增加随行人弹窗 */}
      <Modal
        title={`增加随行人 · ${stayBooking?.room_no || ""} ${stayBooking?.guest_name || ""}`}
        open={compOpen}
        onOk={doAddCompanion}
        onCancel={() => setCompOpen(false)}
        confirmLoading={acting}
        okText="确认添加"
        width={380}
      >
        <div style={{ marginBottom: 6 }}>已有随行人：{(stayBooking?.companion_names || []).join("、") || "无"}</div>
        <Input
          value={compInput}
          onChange={(e) => setCompInput(e.target.value)}
          placeholder="输入姓名，多人用顿号/逗号分隔"
          onPressEnter={doAddCompanion}
        />
      </Modal>
    </div>
  );
}
