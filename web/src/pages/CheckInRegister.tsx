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
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import {
  ArrowsAltOutlined,
  CalendarOutlined,
  DollarOutlined,
  FileSearchOutlined,
  HomeOutlined,
  KeyOutlined,
  LinkOutlined,
  LoginOutlined,
  LogoutOutlined,
  PauseOutlined,
  PrinterOutlined,
  ReadOutlined,
  ReloadOutlined,
  SaveOutlined,
  SelectOutlined,
  TeamOutlined,
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
} from "../api/endpoints";
import type { Room, RoomType, Booking } from "../api/types";
import { useTenant } from "../store/tenant";
import { ROOM_STATE_LABELS, TRIGGER_LABELS } from "../domain/roomActions";
import { fmtCents } from "../utils/format";
// 必须带 .tsx 后缀：无后缀会优先解析到 format.ts（纯字符串工具），取不到组件。
import { CellAmount } from "../utils/format.tsx";
import StatCard from "../components/StatCard";

const ID_TYPES = [
  { value: "ID", label: "居民身份证" },
  { value: "PASSPORT", label: "护照" },
  { value: "OFFICER", label: "军官证" },
  { value: "OTHER", label: "其他" },
];

const ETHNICITIES = ["汉族", "壮族", "满族", "回族", "苗族", "维吾尔族", "土家族", "彝族", "蒙古族", "藏族", "其他"];

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
  const [bookingId, setBookingId] = useState<number | null>(bookingIdParam ? Number(bookingIdParam) : null);

  // 顶部页签
  const [topTab, setTopTab] = useState("info");
  const [logData, setLogData] = useState<any[]>([]);
  const [logLoading, setLogLoading] = useState(false);

  // 弹窗：续住 / 换房 / 随行人
  const [extendOpen, setExtendOpen] = useState(false);
  const [newCheckOut, setNewCheckOut] = useState<Dayjs | null>(null);
  const [changeOpen, setChangeOpen] = useState(false);
  const [newRoomNo, setNewRoomNo] = useState<string | null>(null);
  const [compOpen, setCompOpen] = useState(false);
  const [compInput, setCompInput] = useState("");
  const [acting, setActing] = useState(false);

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
          setBookingId(Number(matched.id));
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
  // 在住模式：把登记单客人信息回填表单（只读展示）
  useEffect(() => {
    if (!isStay || !stayBooking) return;
    setForm((f) => ({
      ...f,
      guest_name: stayBooking.guest_name || f.guest_name,
      guest_phone: stayBooking.guest_phone || f.guest_phone,
      room_type_id: stayBooking.room_type_id ? String(stayBooking.room_type_id) : f.room_type_id,
      check_out_date: stayBooking.check_out_date ? dayjs(stayBooking.check_out_date) : f.check_out_date,
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

  // 顶部概览（数据全部来自本页已加载的 rooms / bookings，不新增接口）
  const today = dayjs().format("YYYY-MM-DD");
  const todayArrivals = useMemo(
    () => bookings.filter((b) => b.status === "created" && b.check_in_date === today),
    [bookings, today]
  );
  const todayDepartures = useMemo(
    () => bookings.filter((b) => b.status === "checked_in" && b.check_out_date === today),
    [bookings, today]
  );
  const inHouseCount = useMemo(() => bookings.filter((b) => b.status === "checked_in").length, [bookings]);
  const pendingAssignCount = useMemo(
    () => bookings.filter((b) => b.status === "created" && !b.room_no).length,
    [bookings]
  );
  const todayArrivalRevenue = useMemo(
    () => todayArrivals.reduce((s, b) => s + (b.total_price ?? 0), 0),
    [todayArrivals]
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
      };
      if (booking) {
        payload.booking_id = Number(booking.id);
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
      reload();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  };

  const doChangeRoom = async () => {
    if (!stayBooking || !newRoomNo) return;
    setActing(true);
    try {
      await changeRoomBooking(tenantCode, String(stayBooking.id), newRoomNo);
      message.success(`换房成功：${stayBooking.room_no} → ${newRoomNo}`);
      setChangeOpen(false);
      setRoomNo(newRoomNo);
      window.history.replaceState(null, "", `/check-in-register?room_no=${newRoomNo}`);
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
        {sideBtn(<DollarOutlined />, "补交押金(O)", () => navigate("/billing"), !isStay)}
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
            onChange={(v) => v && setBookingId(Number(v))}
            options={createdBookings.map((b) => ({
              value: Number(b.id),
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

        {/* 押金行 */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px 10px", marginTop: 8 }}>
          <div>
            <div style={{ marginBottom: 2 }}>本人押金</div>
            <Input size="small" value="0" disabled />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}>授权金额</div>
            <Input size="small" value="0" disabled />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}>币种</div>
            <Select size="small" style={{ width: "100%" }} value="CNY" disabled options={[{ value: "CNY", label: "人民币" }]} />
          </div>
          <div>
            <div style={{ marginBottom: 2 }}>金额</div>
            <Input size="small" value="0.00" disabled />
          </div>
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
          {["兑点", "当日起早", "VIP客人", "信息保密", "价格保密", "匿名单"].map((t) => (
            <Checkbox key={t} disabled>
              {t}
            </Checkbox>
          ))}
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
        <Typography.Text type="secondary">办理入住后此处显示账务概要；押金/退款请在收银结账页操作。</Typography.Text>
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

      {/* 顶部概览：全部取自本页已加载的 rooms / bookings，未新增接口 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={12} md={4}>
          <StatCard
            label="今日预抵"
            value={todayArrivals.length}
            sub="预订待入住"
            accent="#fa8c16"
            icon={<LoginOutlined />}
          />
        </Col>
        <Col xs={12} sm={12} md={4}>
          <StatCard
            label="今日预离"
            value={todayDepartures.length}
            sub="需结账退房"
            accent="#2f54eb"
            icon={<LogoutOutlined />}
          />
        </Col>
        <Col xs={12} sm={12} md={4}>
          <StatCard
            label="在住"
            value={inHouseCount}
            sub="当前在住订单"
            accent="#13c2c2"
            icon={<TeamOutlined />}
          />
        </Col>
        <Col xs={12} sm={12} md={4}>
          <StatCard
            label="待排房"
            value={pendingAssignCount}
            sub="预订未分配房号"
            accent="#722ed1"
            icon={<CalendarOutlined />}
          />
        </Col>
        <Col xs={12} sm={12} md={4}>
          <StatCard
            label="可排房"
            value={assignableRooms.length}
            sub="空净 / 空脏 / 锁房"
            accent="#389e0d"
            icon={<HomeOutlined />}
          />
        </Col>
        <Col xs={12} sm={12} md={4}>
          <StatCard
            label="今日预抵房费"
            value={fmtCents(todayArrivalRevenue)}
            sub="预抵订单房费合计"
            accent="#1677ff"
            icon={<DollarOutlined />}
          />
        </Col>
      </Row>

      <Tabs
        activeKey={topTab}
        onChange={setTopTab}
        size="small"
        items={[
          { key: "info", label: "基本信息(1)", children: infoTab },
          { key: "folio", label: "账务信息(2)", children: folioTab },
          { key: "log", label: "操作日志(3)", children: logTab },
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
        onCancel={() => setChangeOpen(false)}
        confirmLoading={acting}
        okText="确认换房"
        width={380}
      >
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
