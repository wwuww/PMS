import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Card,
  Dropdown,
  Tag,
  Empty,
  Badge,
  App,
  Space,
  Typography,
  Modal,
  Radio,
  Button,
  Row,
  Col,
  Popconfirm,
  Divider,
  Switch,
  Form,
  Input,
  Select,
  InputNumber,
  DatePicker,
  Descriptions,
  Spin,
  Table,
} from "antd";
import { ReloadOutlined, ClearOutlined, LoginOutlined, LogoutOutlined, AudioMutedOutlined, ClockCircleOutlined, LinkOutlined, LockOutlined, SolutionOutlined, PayCircleOutlined, UserAddOutlined, SwapOutlined, UnlockOutlined, ToolOutlined, StopOutlined, CheckCircleOutlined, FileSearchOutlined, CheckSquareOutlined, TeamOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  listRooms,
  transitionRoom,
  listBookings,
  createBooking,
  checkInBooking,
  checkOutBooking,
  extendStayBooking,
  changeRoomBooking,
  updateBookingExtras,
  listRoomTypes,
  setRoomDnd,
  listHousekeeping,
  listRoomStateEvents,
  linkBookings,
  unlinkBookings,
} from "../api/endpoints";
import type { MenuProps } from "antd";
import { getToken, wsBase } from "../api/http";
import type { Room, RoomState, Booking, RoomType } from "../api/types";
import { useTenant } from "../store/tenant";
import {
  ROOM_STATE_LABELS,
  TRIGGER_LABELS,
  ALLOWED_TRIGGERS,
  type RoomTrigger,
} from "../domain/roomActions";

const STATE_META: Record<RoomState, { color: string; bg: string }> = {
  vacant_clean: { color: "#389e0d", bg: "#f6ffed" },
  vacant_dirty: { color: "#8c8c8c", bg: "#fafafa" },  // 空脏=灰色
  occupied: { color: "#0958d9", bg: "#e6f4ff" },
  arrival_locked: { color: "#08979c", bg: "#e6fffb" },
  maintenance: { color: "#cf1322", bg: "#fff1f0" },
  out_of_service: { color: "#595959", bg: "#fafafa" },
};

const isVacant = (s: RoomState) => s === "vacant_clean" || s === "vacant_dirty";

export default function RoomStatusPage() {
  const { tenantCode, hotelId } = useTenant();
  const navigate = useNavigate();
  const { message, modal } = App.useApp();
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState<Room | null>(null);
  const [acting, setActing] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const clickTimer = useRef<number | null>(null);

  // 双击办理入住（空房）
  const [ciRoom, setCiRoom] = useState<Room | null>(null);
  const [ciBookings, setCiBookings] = useState<Booking[]>([]);
  const [ciBookingId, setCiBookingId] = useState<string | null>(null);
  const [ciActing, setCiActing] = useState(false);
  const [ciForm] = Form.useForm();

  // 双击查看订单（在住）
  const [dtRoom, setDtRoom] = useState<Room | null>(null);
  const [dtBooking, setDtBooking] = useState<Booking | null>(null);
  const [dtLoading, setDtLoading] = useState(false);
  const [dtBusy, setDtBusy] = useState(false);

  // 在住房间：续住 / 换房
  const [extOpen, setExtOpen] = useState(false);
  const [extDate, setExtDate] = useState<dayjs.Dayjs | null>(null);
  const [extActing, setExtActing] = useState(false);
  const [swapOpen, setSwapOpen] = useState(false);
  const [swapRoomNo, setSwapRoomNo] = useState<string | null>(null);
  const [swapActing, setSwapActing] = useState(false);

  // 经典房态盘（参考维也纳 PMS 5.0）：状态过滤 / 房型 Tab / 视图模式 / 在住客映射
  const [stateFilter, setStateFilter] = useState<RoomState | "dnd" | "due_in" | "due_out" | null>(null);
  const [typeTab, setTypeTab] = useState<string>("all");
  const [viewMode, setViewMode] = useState<"dense" | "floor">("dense");
  const [guestMap, setGuestMap] = useState<Record<string, { guest_name: string; check_in_date: string; check_out_date: string; total_price: number; linked: boolean; is_master: boolean; bid: string; hourly_start_time: string | null; hourly_hours: number | null }>>({});
  // 住脏：在住但有未完成清扫工单（PENDING/ASSIGNED）的房间
  const [dirtyRooms, setDirtyRooms] = useState<Set<string>>(new Set());
  // 预抵：今日入住且已分房的未入住订单房间
  const [dueInRooms, setDueInRooms] = useState<Set<string>>(new Set());
  // 单击紧凑菜单（参考维也纳 PMS：小菜单代替大弹窗）
  const [menuState, setMenuState] = useState<{ r: Room; x: number; y: number } | null>(null);
  // 批量操作模式（M32.14）：批量置脏/打扫/锁房/联房
  const [batchMode, setBatchMode] = useState(false);
  const [selectedRooms, setSelectedRooms] = useState<Set<string>>(new Set());
  const [batchBusy, setBatchBusy] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);
  const [masterPick, setMasterPick] = useState("");
  // 房态日志弹窗
  const [logRoom, setLogRoom] = useState<string | null>(null);
  const [logData, setLogData] = useState<any[]>([]);
  const [logLoading, setLogLoading] = useState(false);

  // 在住房间：附加服务（加床 / 同住人）
  const [extrasOpen, setExtrasOpen] = useState(false);
  const [bedCount, setBedCount] = useState<number>(0);
  const [companions, setCompanions] = useState<string[]>([]);
  const [extrasActing, setExtrasActing] = useState(false);

  const fetchRooms = useCallback(async () => {
    setLoading(true);
    try {
      const [rm, rt] = await Promise.all([
        listRooms(tenantCode),
        listRoomTypes(tenantCode),
      ]);
      setRooms(rm);
      setRoomTypes(rt);
      // 在住客映射：房态卡片直接显示住客姓名（经典房态盘样式）
      try {
        const bks = await listBookings(tenantCode);
        const today = dayjs().format("YYYY-MM-DD");
        const gmap: Record<string, { guest_name: string; check_in_date: string; check_out_date: string; total_price: number; linked: boolean; is_master: boolean; bid: string; hourly_start_time: string | null; hourly_hours: number | null }> = {};
        const dueIn = new Set<string>();
        for (const b of bks) {
          if (!b.room_no) continue;
          if (b.status === "checked_in") {
            const cur = gmap[b.room_no];
            // 一房多笔在住单（脏数据）时取最近入住的一笔，避免住客/预离显示错乱
            const newer = !cur || b.check_in_date > cur.check_in_date || (b.check_in_date === cur.check_in_date && String(b.id) > cur.bid);
            if (newer) {
              gmap[b.room_no] = { guest_name: b.guest_name, check_in_date: b.check_in_date, check_out_date: b.check_out_date, total_price: b.total_price || 0, linked: !!b.link_group_id, is_master: !!b.is_link_master, bid: String(b.id), hourly_start_time: b.hourly_start_time ?? null, hourly_hours: b.hourly_hours ?? null };
            }
          } else if (b.status === "created" && b.check_in_date === today) {
            // 预抵：今日入住、已分房、未办理入住
            dueIn.add(b.room_no);
          }
        }
        setGuestMap(gmap);
        setDueInRooms(dueIn);
      } catch {
        /* 在住客映射失败不阻断房态盘 */
      }
      // 住脏集合：有未完成清扫工单（CLEANUP, PENDING/ASSIGNED）的房间
      try {
        const tasks = await listHousekeeping(tenantCode);
        setDirtyRooms(
          new Set(
            tasks
              .filter((t: any) => t.task_type === "CLEANUP" && (t.status === "PENDING" || t.status === "ASSIGNED"))
              .map((t: any) => t.room_no)
          )
        );
      } catch {
        /* 工单拉取失败不阻断房态盘 */
      }
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tenantCode, message]);

  useEffect(() => {
    fetchRooms();
  }, [fetchRooms]);

  useEffect(
    () => () => {
      if (clickTimer.current) window.clearTimeout(clickTimer.current);
    },
    []
  );

  // WebSocket 房态实时刷新（M18-3：订阅需 token；断线指数退避自动重连）
  useEffect(() => {
    let ws: WebSocket | null = null;
    let disposed = false;
    let retries = 0;
    let timer: number | undefined;

    const connect = () => {
      const token = getToken() ?? "";
      ws = new WebSocket(
        `${wsBase()}/ws/rooms?tenant_id=${tenantCode}&token=${token}`
      );
      wsRef.current = ws;
      ws.onopen = () => {
        retries = 0;
        setLive(true);
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "event") fetchRooms();
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        setLive(false);
        if (disposed) return;
        // 指数退避重连：3s 起，封顶 15s；重连时重新读取 token（自动续期后可恢复）
        retries += 1;
        const delay = Math.min(3000 * 1.5 ** (retries - 1), 15000);
        timer = window.setTimeout(connect, delay);
      };
      ws.onerror = () => setLive(false);
    };

    connect();
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
      ws?.close();
    };
  }, [tenantCode, fetchRooms]);

  async function doTransition(trigger: RoomTrigger) {
    if (!active) return;
    setActing(true);
    try {
      await transitionRoom(tenantCode, active.room_no, trigger);
      message.success(`${active.room_no} · ${TRIGGER_LABELS[trigger]} 成功`);
      setActive(null);
      fetchRooms(); // 即时刷新（WebSocket 也会再推一次）
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  }

  // 快捷流转（紧凑菜单用，不依赖 active 弹窗）
  async function quickTransition(r: Room, trigger: RoomTrigger) {
    try {
      await transitionRoom(tenantCode, r.room_no, trigger);
      message.success(`${r.room_no} · ${TRIGGER_LABELS[trigger]} 成功`);
      fetchRooms();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  async function toggleDnd(r: Room) {
    try {
      const updated = await setRoomDnd(tenantCode, r.room_no, !r.dnd);
      setRooms((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      message.success(!r.dnd ? `房间 ${r.room_no} 已设为免打扰` : `房间 ${r.room_no} 已取消免打扰`);
      fetchRooms();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "免打扰设置失败");
    }
  }

  // 紧凑菜单内容（按房态出菜单；全部操作直达，无二级弹窗）
  function buildRoomMenu(r: Room): MenuProps["items"] {
    const items: MenuProps["items"] = [];
    if (r.state === "occupied") {
      items.push(
        { key: "detail", icon: <SolutionOutlined />, label: "客人详情" },
        { key: "billing", icon: <PayCircleOutlined />, label: "收银结账" },
        { key: "dnd", icon: <AudioMutedOutlined />, label: r.dnd ? "取消免打扰" : "免打扰" }
      );
    } else {
      if (["vacant_clean", "vacant_dirty", "arrival_locked"].includes(r.state)) {
        items.push({ key: "checkin", icon: <UserAddOutlined />, label: "办理入住" });
      }
      if (r.state === "vacant_clean") {
        items.push({ key: "set_dirty", icon: <SwapOutlined />, label: "置脏" });
      }
      if (r.state === "vacant_dirty") {
        items.push({ key: "clean_done", icon: <ClearOutlined />, label: "清扫完成" });
      }
      if (r.state === "arrival_locked") {
        items.push({ key: "release_arrival", icon: <UnlockOutlined />, label: "解锁" });
      }
      if (r.state === "vacant_clean" || r.state === "vacant_dirty") {
        items.push(
          { key: "lock_for_arrival", icon: <LockOutlined />, label: "锁房" },
          { key: "start_maintenance", icon: <ToolOutlined />, label: "维修" },
          { key: "set_out_of_service", icon: <StopOutlined />, label: "停用", danger: true }
        );
      }
      if (r.state === "maintenance") {
        items.push({ key: "end_maintenance", icon: <ToolOutlined />, label: "结束维修" });
      }
      if (r.state === "out_of_service") {
        items.push({ key: "restore_service", icon: <CheckCircleOutlined />, label: "恢复使用" });
      }
    }
    items.push({ type: "divider" });
    items.push({ key: "log", icon: <FileSearchOutlined />, label: "房态日志" });
    return items;
  }

  const MENU_TRIGGERS: RoomTrigger[] = [
    "set_dirty",
    "clean_done",
    "lock_for_arrival",
    "release_arrival",
    "start_maintenance",
    "end_maintenance",
    "restore_service",
  ];

  function handleMenuAction(key: string, r: Room) {
    setMenuState(null);
    if (key === "detail") navigate(`/check-in-register?room_no=${r.room_no}`);
    else if (key === "billing") navigate("/billing");
    else if (key === "dnd") toggleDnd(r);
    else if (key === "checkin") navigate(`/check-in-register?room_no=${r.room_no}`);
    else if (key === "log") openRoomLog(r);
    else if (key === "set_out_of_service") {
      modal.confirm({
        title: `确认停用房间 ${r.room_no}？`,
        content: "停用后该房不可售，需恢复使用后才能重新上线。",
        okButtonProps: { danger: true },
        onOk: () => quickTransition(r, "set_out_of_service"),
      });
    } else if (MENU_TRIGGERS.includes(key as RoomTrigger)) {
      quickTransition(r, key as RoomTrigger);
    }
  }

  async function openRoomLog(r: Room) {
    setLogRoom(r.room_no);
    setLogLoading(true);
    setLogData([]);
    try {
      setLogData(await listRoomStateEvents(tenantCode, r.room_no));
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLogLoading(false);
    }
  }

  // M32.17d：Esc 清空多选
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && selectedRooms.size) setSelectedRooms(new Set());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedRooms]);

  // ---------- 批量操作（M32.14） ----------
  function toggleBatchMode() {
    setBatchMode((v) => !v);
    setSelectedRooms(new Set());
  }

  function toggleSelect(roomNo: string) {
    setSelectedRooms((prev) => {
      const next = new Set(prev);
      if (next.has(roomNo)) next.delete(roomNo);
      else next.add(roomNo);
      return next;
    });
  }

  async function runBatchTransition(trigger: RoomTrigger, label: string) {
    const eligible = rooms.filter(
      (r) => selectedRooms.has(r.room_no) && (ALLOWED_TRIGGERS[r.state as RoomState] || []).includes(trigger)
    );
    if (!eligible.length) {
      message.warning(`所选房间中没有房态可执行「${label}」`);
      return;
    }
    setBatchBusy(true);
    let ok = 0;
    const fails: string[] = [];
    for (const r of eligible) {
      try {
        await transitionRoom(tenantCode, r.room_no, trigger);
        ok++;
      } catch (e: unknown) {
        fails.push(`${r.room_no}：${(e as Error).message}`);
      }
    }
    setBatchBusy(false);
    if (fails.length) {
      message.warning(`「${label}」成功 ${ok} 间、失败 ${fails.length} 间：${fails[0]}${fails.length > 1 ? " 等" : ""}`);
    } else {
      message.success(`「${label}」批量完成：${ok} 间`);
    }
    fetchRooms();
  }

  // 在住房联房（M32.15）：把选中的在住单联为一组，账务关联到主房；各单保留自己的来离店日期
  function openLinkModal() {
    const target = rooms.filter((r) => selectedRooms.has(r.room_no) && guestMap[r.room_no]);
    if (target.length < 2) {
      message.warning("联房是在住房之间的业务：请至少选中两间在住房");
      return;
    }
    setMasterPick(target[0].room_no);
    setGroupOpen(true);
  }

  async function doLinkGroup() {
    const target = rooms.filter((r) => selectedRooms.has(r.room_no) && guestMap[r.room_no]);
    if (target.length < 2) {
      message.warning("联房至少需要两间在住房");
      return;
    }
    setBatchBusy(true);
    try {
      await linkBookings(tenantCode, {
        room_nos: target.map((r) => r.room_no),
        master_room_no: masterPick,
      });
      message.success(`联房成功：${target.length} 间已关联，主房 ${masterPick}（各单保留原来离店日期）`);
      setGroupOpen(false);
      setSelectedRooms(new Set());
      fetchRooms();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setBatchBusy(false);
    }
  }

  async function doUnlinkGroup() {
    const target = rooms.filter((r) => selectedRooms.has(r.room_no) && guestMap[r.room_no]?.linked);
    if (!target.length) {
      message.warning("所选房间中没有已联房的在住房");
      return;
    }
    setBatchBusy(true);
    try {
      await unlinkBookings(tenantCode, target.map((r) => r.room_no));
      message.success(`已取消联房：${target.map((r) => r.room_no).join("、")}`);
      setSelectedRooms(new Set());
      fetchRooms();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setBatchBusy(false);
    }
  }

  // 单击：弹出紧凑菜单（与双击区分，避免冲突）
  function handleClick(r: Room, e: React.MouseEvent) {
    if (clickTimer.current) window.clearTimeout(clickTimer.current);
    clickTimer.current = window.setTimeout(() => {
      setMenuState({ r, x: e.clientX, y: e.clientY });
      clickTimer.current = null;
    }, 220);
  }

  // 双击：空房办理入住 / 在住查看订单
  function handleDblClick(r: Room) {
    if (clickTimer.current) {
      window.clearTimeout(clickTimer.current);
      clickTimer.current = null;
    }
    setMenuState(null);
    setActive(null);
    if (isVacant(r.state) || r.state === "arrival_locked") {
      navigate(`/check-in-register?room_no=${r.room_no}`);
    } else if (r.state === "occupied") {
      // M32.11：在住房双击 → 登记页在住登记单（含续住/换房/结账等业务按钮）
      navigate(`/check-in-register?room_no=${r.room_no}`);
    } else {
      message.info(
        `房态「${ROOM_STATE_LABELS[r.state]}」暂不支持双击快捷操作，请单击选择房态操作`
      );
    }
  }

  async function openCheckIn(room: Room) {
    setCiRoom(room);
    setCiBookingId(null);
    setCiBookings([]);
    setCiActing(false);
    ciForm.resetFields();
    ciForm.setFieldsValue({
      channel: "walk_in",
      check_in_date: dayjs(),
      check_out_date: dayjs().add(1, "day"),
    });
    try {
      const all = await listBookings(tenantCode);
      const cands = all.filter(
        (b) =>
          b.status === "created" &&
          (b.room_no === room.room_no ||
            (b.room_no == null && b.room_type_id === room.room_type_id))
      );
      setCiBookings(cands);
      if (cands.length === 1) setCiBookingId(cands[0].id);
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  async function doCheckInExisting() {
    if (!ciRoom) return;
    if (ciBookingId == null) {
      message.warning("请选择要入住的预订");
      return;
    }
    setCiActing(true);
    try {
      await checkInBooking(tenantCode, ciBookingId, ciRoom.room_no);
      message.success(`预订 #${ciBookingId} 已办理入住（${ciRoom.room_no}）`);
      setCiRoom(null);
      fetchRooms();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setCiActing(false);
    }
  }

  async function doWalkIn() {
    if (!ciRoom) return;
    const v = await ciForm.validateFields();
    setCiActing(true);
    try {
      const b = await createBooking(tenantCode, {
        hotel_id: ciRoom.hotel_id,
        room_type_id: ciRoom.room_type_id,
        guest_name: v.guest_name,
        chat_session_id: null,
        check_in_date: v.check_in_date.format("YYYY-MM-DD"),
        check_out_date: v.check_out_date.format("YYYY-MM-DD"),
        channel: v.channel || "walk_in",
        room_no: ciRoom.room_no,
      });
      await checkInBooking(tenantCode, b.id, ciRoom.room_no);
      message.success(`散客 ${v.guest_name} 已登记入住（${ciRoom.room_no}）`);
      setCiRoom(null);
      ciForm.resetFields();
      fetchRooms();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setCiActing(false);
    }
  }

  async function openDetail(room: Room) {
    setDtRoom(room);
    setDtBooking(null);
    setDtLoading(true);
    try {
      const all = await listBookings(tenantCode);
      const match = all
        .filter((b) => b.status === "checked_in" && b.room_no === room.room_no)
        .sort((a, b) => b.id.localeCompare(a.id));
      setDtBooking(match[0] || null);
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setDtLoading(false);
    }
  }

  const rtName = (id: string) => {
    const t = roomTypes.find((x) => x.id === id);
    return t ? t.name : `#${id}`;
  };

  async function doCheckOut() {
    if (!dtBooking) return;
    setDtBusy(true);
    try {
      await checkOutBooking(tenantCode, dtBooking.id);
      message.success(`预订 #${dtBooking.id} 已办理退房（${dtBooking.room_no}）`);
      // 退房后通常需结清账单：直接跳转到收银页定位该账单，便于前台立即结账
      navigate(
        `/billing?booking=${dtBooking.id}${
          dtBooking.room_no ? `&room=${dtBooking.room_no}` : ""
        }`
      );
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setDtBusy(false);
    }
  }

  async function doExtend() {
    if (!dtBooking || !extDate) return;
    const nd = extDate.format("YYYY-MM-DD");
    if (nd <= dtBooking.check_out_date) {
      message.warning("续住离店日期须晚于当前离店日期");
      return;
    }
    setExtActing(true);
    try {
      await extendStayBooking(tenantCode, dtBooking.id, nd);
      message.success(`预订 #${dtBooking.id} 已续住至 ${nd}`);
      setExtOpen(false);
      setDtRoom(null);
      fetchRooms();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setExtActing(false);
    }
  }

  async function doSwap() {
    if (!dtBooking || !swapRoomNo) return;
    setSwapActing(true);
    try {
      await changeRoomBooking(tenantCode, dtBooking.id, swapRoomNo);
      message.success(`预订 #${dtBooking.id} 已换房至 ${swapRoomNo}`);
      setSwapOpen(false);
      setDtRoom(null);
      fetchRooms();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setSwapActing(false);
    }
  }

  function openExtras() {
    if (!dtBooking) return;
    setBedCount(dtBooking.extra_bed_count || 0);
    setCompanions(dtBooking.companion_names || []);
    setExtrasOpen(true);
  }

  async function doSaveExtras() {
    if (!dtBooking) return;
    setExtrasActing(true);
    try {
      const updated = await updateBookingExtras(tenantCode, dtBooking.id, {
        extra_bed_count: bedCount,
        companion_names: companions,
      });
      message.success("附加服务已保存");
      setDtBooking(updated);
      setExtrasOpen(false);
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setExtrasActing(false);
    }
  }

  const typeNameOf = (r: Room) =>
    roomTypes.find((rt) => String(rt.id) === String(r.room_type_id))?.name || "";

  // M32.17b：钟点房离店时刻（HH:mm，跨日进位）
  const hourlyEndOf = (start: string, hours: number) => {
    const [hh, mm] = start.split(":").map(Number);
    const total = hh * 60 + mm + hours * 60;
    const d = Math.floor(total / 1440);
    const t = `${String(Math.floor((total % 1440) / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
    return d > 0 ? `次日 ${t}` : t;
  };

  // 经典卡片：实色底 + 白字（房号大字 + 住客/房型小字），单击房态操作、双击入住/订单
  const renderCard = (r: Room) => {
    const m = STATE_META[r.state];
    const guest = guestMap[r.room_no];
    // M32.3：锁房不变底色——按锁房前房态着色，第一行加小锁图标
    const locked = r.state === "arrival_locked";
    const displayColor = locked
      ? STATE_META[r.pre_lock_state === "vacant_dirty" ? "vacant_dirty" : "vacant_clean"].color
      : m.color;
    const occDirty = r.state === "occupied" && dirtyRooms.has(r.room_no);
    const typeName = typeNameOf(r);
    const guestName = r.state === "occupied" ? guest?.guest_name || "在住" : "";
    // M32.17c：房型上移第一行右侧；状态文字与图标重新归位
    const stateLabel = locked
      ? r.pre_lock_state === "vacant_dirty"
        ? "空脏"
        : "空净"
      : occDirty
      ? "住脏"
      : ROOM_STATE_LABELS[r.state];

    const batchSelected = selectedRooms.has(r.room_no);
    return (
      <div
        key={r.id}
        onClick={(e) => {
          // M32.17d：Ctrl/⌘ + 左键 = 多选（自动进入批量条，再点一次取消选择）
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            e.stopPropagation();
            setBatchMode(true);
            toggleSelect(r.room_no);
            return;
          }
          if (batchMode) {
            e.stopPropagation();
            toggleSelect(r.room_no);
          } else {
            handleClick(r, e);
          }
        }}
        onDoubleClick={(e) => {
          e.preventDefault();
          if (!batchMode) handleDblClick(r);
        }}
        style={{
          width: 112,
          height: 78,
          borderRadius: 6,
          background: displayColor,
          color: "#fff",
          padding: "6px 8px",
          cursor: "pointer",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          transition: "transform .12s, box-shadow .12s",
          position: "relative",
          outline: batchSelected ? "3px solid #1677ff" : undefined,
          outlineOffset: 1,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "translateY(-2px)";
          e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,.25)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "none";
          e.currentTarget.style.boxShadow = "none";
        }}
        title={
          (isVacant(r.state)
            ? "单击：房态操作 ｜ 双击：办理登记入住"
            : r.state === "occupied"
            ? "单击：房态操作 ｜ 双击：在住登记单"
            : "单击：房态操作") + " ｜ Ctrl+左键：多选"
        }
      >
        {batchSelected && (
          <div
            style={{
              position: "absolute",
              top: -6,
              right: -6,
              width: 18,
              height: 18,
              borderRadius: "50%",
              background: "#1677ff",
              color: "#fff",
              fontSize: 12,
              lineHeight: "18px",
              textAlign: "center",
              boxShadow: "0 1px 4px rgba(0,0,0,.3)",
            }}
          >
            ✓
          </div>
        )}
        {/* 第一行：房号 ｜ 房型名称（右） */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 4 }}>
          <Typography.Text strong style={{ color: "#fff", fontSize: 15, lineHeight: "18px", flexShrink: 0 }}>
            {r.room_no}
          </Typography.Text>
          <span
            title={typeName}
            style={{
              fontSize: 11,
              lineHeight: "14px",
              color: "rgba(255,255,255,.82)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              minWidth: 0,
            }}
          >
            {typeName || "—"}
          </span>
        </div>
        {/* 第二行：客人姓名（在住）/ 状态文字（空房），整行居中显示 */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span
            style={{
              fontSize: 12,
              lineHeight: "16px",
              textAlign: "center",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: "100%",
            }}
          >
            {guestName || stateLabel}
          </span>
        </div>
        {/* 第三行：小图标组（右）：预抵/预离 → 锁房 → 免打扰 → 住脏 → 联房 → 钟点（在住房不再显示住净/住脏文字） */}
        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center" }}>
          <span style={{ display: "flex", alignItems: "center", gap: 3, flexShrink: 0 }}>
            {dueInRooms.has(r.room_no) && (
              <LoginOutlined style={{ fontSize: 12, color: "#ffe58f" }} title="预抵：今日入住" />
            )}
            {r.state === "occupied" && guest && guest.check_out_date === dayjs().format("YYYY-MM-DD") && (
              <LogoutOutlined style={{ fontSize: 12, color: "#ffd666" }} title="预离：今日离店" />
            )}
            {locked && <LockOutlined style={{ fontSize: 12, color: "#fff" }} title="锁房" />}
            {!!r.dnd && <AudioMutedOutlined style={{ fontSize: 12, color: "#fff" }} title="免打扰（DND）" />}
            {occDirty && <ClearOutlined style={{ fontSize: 12, color: "#d9d9d9" }} title="住脏：待清扫" />}
            {guest?.linked && (
              <LinkOutlined
                style={{ fontSize: 12, color: "#fff" }}
                title={guest.is_master ? "联房 · 主房" : "联房 · 从房"}
              />
            )}
            {guest?.hourly_start_time && (
              <ClockCircleOutlined
                style={{ fontSize: 12, color: "#fff" }}
                title={`钟点房 ${guest.hourly_start_time}-${hourlyEndOf(guest.hourly_start_time, guest.hourly_hours ?? 0)}（${guest.hourly_hours ?? 0} 小时）`}
              />
            )}
          </span>
        </div>
      </div>
    );
  };

  if (!rooms.length && !loading)
    return <Empty description="该租户下暂无房间，请先在后端创建门店与房间" />;

  const floors = Array.from(new Set(rooms.map((r) => r.floor))).sort();
  const counts = rooms.reduce<Partial<Record<RoomState, number>>>((acc, r) => {
    acc[r.state] = (acc[r.state] || 0) + 1;
    return acc;
  }, {});
  const dndCount = rooms.filter((r) => !!r.dnd).length;

  // 房型 Tab 计数（参考图顶部：全部[n] 豪双[88] 高单[65] ...）
  const typeTabCounts = rooms.reduce<Record<string, number>>((acc, r) => {
    const name = roomTypes.find((rt) => String(rt.id) === String(r.room_type_id))?.name || "未知";
    acc[name] = (acc[name] || 0) + 1;
    return acc;
  }, {});

  // 过滤链：状态/免打扰 → 房型 Tab
  const todayStr = dayjs().format("YYYY-MM-DD");
  const isDueIn = (r: Room) => dueInRooms.has(r.room_no);
  const isDueOut = (r: Room) => r.state === "occupied" && guestMap[r.room_no]?.check_out_date === todayStr;
  const dueOutCount = rooms.filter(isDueOut).length;
  const visibleRooms = rooms.filter((r) => {
    if (stateFilter === "dnd" && !r.dnd) return false;
    if (stateFilter === "due_in") return isDueIn(r);
    if (stateFilter === "due_out") return isDueOut(r);
    if (stateFilter && stateFilter !== "dnd" && r.state !== stateFilter) return false;
    if (typeTab !== "all") {
      const name = roomTypes.find((rt) => String(rt.id) === String(r.room_type_id))?.name || "未知";
      if (name !== typeTab) return false;
    }
    return true;
  });

  // 经营统计条（参考图底部：总数/在住/…/平均房价/出租率）
  const occupiedCount = counts.occupied || 0;
  const occRate = rooms.length ? ((occupiedCount / rooms.length) * 100).toFixed(1) : "0.0";
  const occupiedBookingsList = Object.values(guestMap);
  const avgPrice = occupiedBookingsList.length
    ? Math.round(occupiedBookingsList.reduce((sum, g) => sum + (g.total_price || 0), 0) / occupiedBookingsList.length)
    : 0;

  const actions = active ? ALLOWED_TRIGGERS[active.state] : [];

  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start", paddingBottom: 52 }}>
      {/* 左侧：房态过滤面板（参考维也纳 PMS 5.0 左栏，带计数可点选） */}
      <Card size="small" title="房态" style={{ width: 196, flexShrink: 0 }} styles={{ body: { padding: "8px 8px" } }}>
        {([
          ...(Object.entries(ROOM_STATE_LABELS) as [RoomState, string][]).map(([st, label]) => ({
            key: st,
            label,
            count: counts[st] || 0,
            color: STATE_META[st].color,
          })),
          { key: "due_in", label: "预抵", count: dueInRooms.size, color: "#fa8c16" },
          { key: "due_out", label: "预离", count: dueOutCount, color: "#2f54eb" },
          { key: "dnd", label: "免打扰", count: dndCount, color: "#722ed1" },
        ] as { key: RoomState | "dnd" | "due_in" | "due_out"; label: string; count: number; color: string }[]).map((it) => {
          const sel = stateFilter === it.key;
          return (
            <div
              key={it.key}
              onClick={() => setStateFilter(sel ? null : it.key)}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "5px 8px",
                marginBottom: 2,
                borderRadius: 6,
                cursor: "pointer",
                background: sel ? "#e6f4ff" : "transparent",
                border: sel ? "1px solid #91caff" : "1px solid transparent",
              }}
            >
              <span>
                <span
                  style={{
                    display: "inline-block",
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    background: it.color,
                    marginRight: 8,
                  }}
                />
                {it.label}
              </span>
              <Typography.Text type="secondary">[{it.count}]</Typography.Text>
            </div>
          );
        })}
        <Divider style={{ margin: "8px 0" }} />
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Button size="small" type={viewMode === "dense" ? "primary" : "default"} onClick={() => setViewMode("dense")}>
            大图标（平铺）
          </Button>
          <Button size="small" type={viewMode === "floor" ? "primary" : "default"} onClick={() => setViewMode("floor")}>
            按楼层分组
          </Button>
        </div>
      </Card>

      {/* 右侧主区 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* 房型 Tab（带计数） */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10, alignItems: "center" }}>
          <Button size="small" type={typeTab === "all" ? "primary" : "default"} onClick={() => setTypeTab("all")}>
            全部 [{rooms.length}]
          </Button>
          {Object.entries(typeTabCounts).map(([name, n]) => (
            <Button
              key={name}
              size="small"
              type={typeTab === name ? "primary" : "default"}
              onClick={() => setTypeTab(typeTab === name ? "all" : name)}
            >
              {name} [{n}]
            </Button>
          ))}
          <span style={{ flex: 1 }} />
          <Badge status={live ? "processing" : "default"} text={live ? "实时连接中" : "未连接"} />
          <Button
            size="small"
            type={batchMode ? "primary" : "default"}
            icon={<CheckSquareOutlined />}
            onClick={toggleBatchMode}
          >
            {batchMode ? "退出批量" : "批量操作（Ctrl+左键）"}
          </Button>
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchRooms} loading={loading}>
            刷新
          </Button>
        </div>

        {/* 卡片墙 */}
        {viewMode === "floor" ? (
          floors.map((floor) => (
            <Card key={floor} size="small" style={{ marginBottom: 10 }} title={`${floor} 层`}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {visibleRooms.filter((r) => r.floor === floor).map(renderCard)}
              </div>
            </Card>
          ))
        ) : (
          <Card size="small" loading={loading && rooms.length === 0}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{visibleRooms.map(renderCard)}</div>
          </Card>
        )}

        {/* 批量操作条 */}
        {(batchMode || selectedRooms.size > 0) && (
          <div
            style={{
              position: "fixed",
              bottom: 52,
              left: 224,
              right: 24,
              zIndex: 90,
              background: "#fff",
              border: "1px solid #e3e6eb",
              borderRadius: 10,
              padding: "8px 14px",
              display: "flex",
              gap: 8,
              alignItems: "center",
              boxShadow: "0 4px 16px rgba(31,35,41,.14)",
              flexWrap: "wrap",
            }}
          >
            <Typography.Text strong>已选 {selectedRooms.size} 间</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              （Ctrl/⌘ + 左键 加选或取消，Esc 清空；自动跳过房态不匹配的房间）
            </Typography.Text>
            <Button size="small" loading={batchBusy} onClick={() => runBatchTransition("set_dirty", "置脏")}>
              置脏
            </Button>
            <Button size="small" icon={<ClearOutlined />} loading={batchBusy} onClick={() => runBatchTransition("clean_done", "打扫")}>
              打扫
            </Button>
            <Button size="small" icon={<LockOutlined />} loading={batchBusy} onClick={() => runBatchTransition("lock_for_arrival", "锁房")}>
              锁房
            </Button>
            <Button size="small" loading={batchBusy} onClick={() => runBatchTransition("release_arrival", "解锁")}>
              解锁
            </Button>
            <Button size="small" icon={<TeamOutlined />} loading={batchBusy} onClick={openLinkModal}>
              联房
            </Button>
            <Button size="small" loading={batchBusy} onClick={doUnlinkGroup}>
              取消联房
            </Button>
            <span style={{ flex: 1 }} />
            <Button size="small" onClick={() => setSelectedRooms(new Set())}>
              清空选择
            </Button>
          </div>
        )}

        {/* 经营统计条：fixed 钉在屏幕底部（避开左侧 208px 导航栏），与房间多少/滚动无关 */}
        <div
          style={{
            padding: "8px 16px",
            background: "#fffbe6",
            borderTop: "1px solid #ffe58f",
            display: "flex",
            flexWrap: "wrap",
            gap: 16,
            fontSize: 13,
            position: "fixed",
            left: 208,
            right: 0,
            bottom: 0,
            zIndex: 20,
            boxShadow: "0 -2px 8px rgba(0,0,0,.08)",
          }}
        >
          <span>经营统计：</span>
          <span>
            总数 <b>{rooms.length}</b>
          </span>
          <span>
            在住 <b>{occupiedCount}</b>
          </span>
          <span>
            空净 <b>{counts.vacant_clean || 0}</b>
          </span>
          <span>
            空脏 <b>{counts.vacant_dirty || 0}</b>
          </span>
          <span>
            锁房 <b>{counts.arrival_locked || 0}</b>
          </span>
          <span>
            维修 <b>{counts.maintenance || 0}</b>
          </span>
          <span>
            停用 <b>{counts.out_of_service || 0}</b>
          </span>
          <span>
            免打扰 <b>{dndCount}</b>
          </span>
          <span>
            平均房价 <b>¥{(avgPrice / 100).toFixed(2)}</b>
          </span>
          <span>
            出租率 <b>{occRate}%</b>
          </span>
        </div>
      </div>

      {/* 单击：房态操作 */}
      <Modal
        title={active ? `房间 ${active.room_no} · 当前 ${ROOM_STATE_LABELS[active.state]}` : ""}
        open={!!active}
        onCancel={() => setActive(null)}
        footer={null}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <Typography.Text>
            免打扰（DND）
            <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
              仅在住房间可开启；退房后自动取消
            </Typography.Text>
          </Typography.Text>
          <Switch
            checked={!!active?.dnd}
            disabled={!active?.dnd && active?.state !== "occupied"}
            onChange={async (v) => {
              if (!active) return;
              try {
                const updated = await setRoomDnd(tenantCode, active.room_no, v);
                setRooms((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
                setActive(updated);
                message.success(v ? `房间 ${updated.room_no} 已设为免打扰` : `房间 ${updated.room_no} 已取消免打扰`);
              } catch (e: any) {
                message.error(e?.response?.data?.detail || "免打扰设置失败");
              }
            }}
          />
        </div>
        <Typography.Paragraph type="secondary">
          选择要执行的房态操作（操作后将即时刷新并同步至其他终端）：
        </Typography.Paragraph>
        <Row gutter={[8, 8]}>
          {actions.map((t) => (
            <Col span={12} key={t}>
              <Button
                block
                loading={acting}
                onClick={() => doTransition(t)}
                danger={t === "set_out_of_service"}
              >
                {TRIGGER_LABELS[t]}
              </Button>
            </Col>
          ))}
          {actions.length === 0 && <Col span={24}>该房态无可执行操作</Col>}
        </Row>
      </Modal>

      {/* 双击空房：办理登记入住 */}
      <Modal
        title={ciRoom ? `办理登记入住 · ${ciRoom.room_no}（${ROOM_STATE_LABELS[ciRoom.state]}）` : ""}
        open={!!ciRoom}
        onCancel={() => setCiRoom(null)}
        footer={null}
      >
        <Typography.Paragraph type="secondary">
          为该空房办理入住：可选择已有预订直接入住，或登记散客（无预订）创建订单并入住。
        </Typography.Paragraph>

        <Divider orientation="left">已有预订</Divider>
        {ciBookings.length > 0 ? (
          <>
            <Form layout="vertical">
              <Form.Item label="选择预订" required>
                <Select
                  value={ciBookingId ?? undefined}
                  onChange={setCiBookingId}
                  placeholder="选择匹配该房间的预订"
                  options={ciBookings.map((b) => ({
                    value: b.id,
                    label:
                      `#${b.id} ${b.guest_name}（${b.check_in_date}~${b.check_out_date}` +
                      (b.room_no ? ` · 房${b.room_no}` : " · 未排房") +
                      "）",
                  }))}
                />
              </Form.Item>
            </Form>
            <Button type="primary" block loading={ciActing} onClick={doCheckInExisting}>
              办理入住（已有预订）
            </Button>
          </>
        ) : (
          <Typography.Text type="secondary">该房间暂无匹配的待入住预订，可走下方散客登记。</Typography.Text>
        )}

        <Divider orientation="left">散客登记（无预订直接入住）</Divider>
        <Form form={ciForm} layout="vertical">
          <Form.Item name="guest_name" label="客人姓名" rules={[{ required: true, message: "请输入客人姓名" }]}>
            <Input placeholder="如 张三" />
          </Form.Item>
          <Form.Item name="check_in_date" label="入住日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="check_out_date" label="离店日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="channel" label="渠道">
            <Select
              options={[
                { value: "walk_in", label: "散客" },
                { value: "direct", label: "直订" },
                { value: "ota", label: "OTA" },
                { value: "phone", label: "电话" },
              ]}
            />
          </Form.Item>
          <Button block loading={ciActing} onClick={doWalkIn}>
            创建并入住
          </Button>
        </Form>
      </Modal>

      {/* 双击在住：查看订单详情 */}
      <Modal
        title={dtRoom ? `订单详情 · ${dtRoom.room_no}（在住）` : ""}
        open={!!dtRoom}
        onCancel={() => setDtRoom(null)}
        footer={null}
      >
        {dtLoading ? (
          <div style={{ textAlign: "center", padding: 24 }}>
            <Spin />
          </div>
        ) : dtBooking ? (
          <>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="订单号">#{dtBooking.id}</Descriptions.Item>
              <Descriptions.Item label="客人">{dtBooking.guest_name}</Descriptions.Item>
              <Descriptions.Item label="房型">{rtName(dtBooking.room_type_id)}</Descriptions.Item>
              <Descriptions.Item label="房号">{dtBooking.room_no || "—"}</Descriptions.Item>
              <Descriptions.Item label="渠道">{dtBooking.channel}</Descriptions.Item>
              <Descriptions.Item label="入住">{dtBooking.check_in_date}</Descriptions.Item>
              <Descriptions.Item label="离店">{dtBooking.check_out_date}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color="green">在住</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="间夜">{dtBooking.nights}</Descriptions.Item>
              <Descriptions.Item label="房价总额">
                ¥{((dtBooking.total_price ?? 0) / 100).toFixed(2)}
              </Descriptions.Item>
              <Descriptions.Item label="加床">
                {dtBooking.extra_bed_count > 0 ? `${dtBooking.extra_bed_count} 张` : "无"}
              </Descriptions.Item>
              <Descriptions.Item label="同住人">
                {dtBooking.companion_names && dtBooking.companion_names.length
                  ? dtBooking.companion_names.join("、")
                  : "—"}
              </Descriptions.Item>
              {dtBooking.chat_session_id != null && (
                <Descriptions.Item label="关联会话">#{dtBooking.chat_session_id}</Descriptions.Item>
              )}
            </Descriptions>
            <div style={{ textAlign: "right", marginTop: 12 }}>
              <Space wrap>
                <Button onClick={() => setDtRoom(null)}>关闭</Button>
                <Button
                  onClick={() => {
                    setExtDate(dayjs(dtBooking!.check_out_date).add(1, "day"));
                    setExtOpen(true);
                  }}
                >
                  续住
                </Button>
                <Button
                  onClick={() => {
                    setSwapRoomNo(null);
                    setSwapOpen(true);
                  }}
                >
                  换房
                </Button>
                <Button onClick={openExtras}>附加服务</Button>
                <Button
                  onClick={() =>
                    navigate(
                      `/billing?booking=${dtBooking!.id}${
                        dtBooking!.room_no ? `&room=${dtBooking!.room_no}` : ""
                      }`
                    )
                  }
                >
                  查看账单
                </Button>
                <Popconfirm
                  title="确认办理退房？"
                  description="退房后房间将转为待清扫，账单需另行结清。"
                  onConfirm={doCheckOut}
                >
                  <Button type="primary" danger loading={dtBusy}>
                    办理退房
                  </Button>
                </Popconfirm>
              </Space>
            </div>
          </>
        ) : (
          <Empty description="该房间当前无关联预订订单（可能为散客/历史账单）" />
        )}
      </Modal>

      {/* 在住房间：续住 */}
      <Modal
        title={dtBooking ? `续住 · ${dtBooking.room_no}` : ""}
        open={extOpen}
        onCancel={() => setExtOpen(false)}
        onOk={doExtend}
        confirmLoading={extActing}
        okText="确认续住"
        cancelText="取消"
      >
        <Typography.Paragraph type="secondary">
          当前离店：{dtBooking?.check_out_date}。请选择新的离店日期（须晚于当前离店日，系统将按增量晚重算房费）。
        </Typography.Paragraph>
        <DatePicker
          style={{ width: "100%" }}
          value={extDate}
          onChange={setExtDate}
          disabledDate={(d) =>
            !d.isAfter(dayjs(dtBooking!.check_out_date), "day")
          }
        />
      </Modal>

      {/* 在住房间：换房 */}
      <Modal
        title={dtBooking ? `换房 · ${dtBooking.room_no}（${rtName(dtBooking.room_type_id)}）` : ""}
        open={swapOpen}
        onCancel={() => setSwapOpen(false)}
        onOk={doSwap}
        confirmLoading={swapActing}
        okText="确认换房"
        cancelText="取消"
        okButtonProps={{ disabled: !swapRoomNo }}
      >
        <Typography.Paragraph type="secondary">
          仅可换至同房型「空净」房。原房将自动转「空脏」待清扫，在开账单房号同步更新。
        </Typography.Paragraph>
        <Select
          style={{ width: "100%" }}
          placeholder="选择目标房号"
          value={swapRoomNo ?? undefined}
          onChange={setSwapRoomNo}
          options={rooms
            .filter(
              (r) =>
                r.room_type_id === dtBooking?.room_type_id &&
                r.state === "vacant_clean" &&
                r.room_no !== dtBooking?.room_no
            )
            .map((r) => ({ value: r.room_no, label: `${r.room_no}（空净）` }))}
        />
      </Modal>

      {/* 在住房间：附加服务（加床 / 同住人） */}
      <Modal
        title={dtBooking ? `附加服务 · ${dtBooking.room_no}` : ""}
        open={extrasOpen}
        onCancel={() => setExtrasOpen(false)}
        onOk={doSaveExtras}
        confirmLoading={extrasActing}
        okText="保存"
        cancelText="取消"
      >
        <Form layout="vertical">
          <Form.Item label="加床数量">
            <InputNumber
              min={0}
              max={5}
              style={{ width: "100%" }}
              value={bedCount}
              onChange={(v) => setBedCount(v ?? 0)}
            />
          </Form.Item>
          <Form.Item label="同住人姓名" tooltip="输入姓名后回车添加，可多人">
            <Select
              mode="tags"
              style={{ width: "100%" }}
              placeholder="如：李四、王五"
              value={companions}
              onChange={setCompanions}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 联房弹窗（在住房之间；各单保留自己的来离店日期） */}
      <Modal
        title={`联房 · 已选 ${rooms.filter((r) => selectedRooms.has(r.room_no) && guestMap[r.room_no]).length} 间在住房`}
        open={groupOpen}
        onOk={doLinkGroup}
        onCancel={() => setGroupOpen(false)}
        confirmLoading={batchBusy}
        okText="确认联房"
        width={440}
      >
        <div style={{ marginBottom: 8 }}>
          <div style={{ marginBottom: 4 }}>* 选择主房（联房账务结算的主账房）</div>
          <Radio.Group
            value={masterPick}
            onChange={(e) => setMasterPick(e.target.value)}
            style={{ display: "flex", flexDirection: "column", gap: 6 }}
          >
            {rooms
              .filter((r) => selectedRooms.has(r.room_no) && guestMap[r.room_no])
              .map((r) => (
                <Radio key={r.room_no} value={r.room_no}>
                  <b>{r.room_no}</b>
                  <span style={{ marginLeft: 8 }}>
                    {guestMap[r.room_no].guest_name}（{guestMap[r.room_no].check_in_date} → {guestMap[r.room_no].check_out_date}）
                  </span>
                </Radio>
              ))}
          </Radio.Group>
        </div>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          联房只在在住房之间建立账务关联，各房间保留自己的来离店日期与房价；退房时从房账单可并入主房结算。可在批量操作条「取消联房」解除。
        </Typography.Text>
      </Modal>

      {/* 房态日志弹窗 */}
      <Modal
        title={logRoom ? `房间 ${logRoom} · 房态日志` : "房态日志"}
        open={!!logRoom}
        onCancel={() => setLogRoom(null)}
        footer={null}
        width={600}
      >
        <Table
          size="small"
          loading={logLoading}
          rowKey="id"
          pagination={{ pageSize: 8, showSizeChanger: false }}
          dataSource={logData}
          columns={[
            {
              title: "时间",
              dataIndex: "occurred_at",
              key: "occurred_at",
              width: 150,
              render: (v: string) => (v ? v.replace("T", " ").slice(0, 19) : "—"),
            },
            {
              title: "操作",
              dataIndex: "trigger",
              key: "trigger",
              width: 110,
              render: (v: string) => TRIGGER_LABELS[v as RoomTrigger] ?? v,
            },
            {
              title: "状态流转",
              key: "flow",
              render: (_: unknown, rec: any) => (
                <span>
                  {ROOM_STATE_LABELS[rec.from_state as RoomState] ?? rec.from_state} →{" "}
                  {ROOM_STATE_LABELS[rec.to_state as RoomState] ?? rec.to_state}
                </span>
              ),
            },
            { title: "操作人", dataIndex: "operator", key: "operator", width: 100 },
          ]}
        />
      </Modal>

      {/* 房态卡片紧凑菜单（单击弹出，参考维也纳 PMS 样式） */}
      {menuState && (
        <Dropdown
          open
          trigger={["contextMenu"]}
          menu={{
            items: buildRoomMenu(menuState.r),
            onClick: ({ key, domEvent }) => {
              domEvent.stopPropagation();
              handleMenuAction(key, menuState.r);
            },
          }}
          onOpenChange={(o) => {
            if (!o) setMenuState(null);
          }}
        >
          <span
            style={{ position: "fixed", left: menuState.x, top: menuState.y, width: 1, height: 1, display: "block" }}
          />
        </Dropdown>
      )}
    </div>
  );
}
