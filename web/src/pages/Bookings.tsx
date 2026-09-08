import { useEffect, useMemo, useState, useCallback } from "react";
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  DatePicker,
  Tag,
  App,
  Popconfirm,
  Space,
  Empty,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  listBookings,
  createBooking,
  checkInBooking,
  checkOutBooking,
  cancelBooking,
  markBookingNoshow,
  listRoomTypes,
  listRooms,
  recommendRooms,
} from "../api/endpoints";
import type {
  Booking,
  BookingStatus,
  RoomType,
  Room,
  RoomRecommend,
} from "../api/types";
import { useTenant } from "../store/tenant";

const STATUS_META: Record<BookingStatus, { label: string; color: string }> = {
  created: { label: "待入住", color: "blue" },
  checked_in: { label: "在住", color: "green" },
  checked_out: { label: "已离店", color: "default" },
  cancelled: { label: "已取消", color: "red" },
  noshow: { label: "未到店", color: "orange" },
};

export default function BookingsPage() {
  const { tenantCode, hotelId } = useTenant();
  const { message } = App.useApp();
  const [rows, setRows] = useState<Booking[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [checkIn, setCheckIn] = useState<Booking | null>(null);
  const [checkInRoom, setCheckInRoom] = useState<string | undefined>();
  const [acting, setActing] = useState(false);
  const [form] = Form.useForm();
  // M24 智能排房
  const [recommendFor, setRecommendFor] = useState<Booking | null>(null);
  const [recommendList, setRecommendList] = useState<RoomRecommend[]>([]);
  const [recommendLoading, setRecommendLoading] = useState(false);
  const formStayType = Form.useWatch("stay_type", form);

  const load = useCallback(async () => {
    if (!hotelId) return;
    setLoading(true);
    try {
      const [b, rt, rm] = await Promise.all([
        listBookings(tenantCode),
        listRoomTypes(tenantCode),
        listRooms(tenantCode),
      ]);
      setRows(b);
      setRoomTypes(rt);
      setRooms(rm);
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId, message]);

  useEffect(() => {
    load();
  }, [load]);

  const rtName = useMemo(() => {
    const m = new Map(roomTypes.map((r) => [r.id, r.name]));
    return (id: string) => m.get(id) || `#${id}`;
  }, [roomTypes]);

  const filtered = useMemo(
    () =>
      statusFilter === "all"
        ? rows
        : rows.filter((r) => r.status === statusFilter),
    [rows, statusFilter]
  );

  async function submitCreate() {
    const v = await form.validateFields();
    try {
      await createBooking(tenantCode, {
        hotel_id: hotelId!,
        room_type_id: v.room_type_id,
        guest_name: v.guest_name,
        chat_session_id: null,
        check_in_date: v.check_in_date.format("YYYY-MM-DD"),
        check_out_date: v.check_out_date.format("YYYY-MM-DD"),
        channel: v.channel || "direct",
        guest_phone: v.guest_phone || null,
        room_no: v.room_no || null,
        stay_type: v.stay_type || "daily",
        hourly_hours:
          v.stay_type === "hourly" ? Number(v.hourly_hours) || null : null,
      });
      message.success("预订创建成功");
      setCreateOpen(false);
      form.resetFields();
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  function openCheckIn(b: Booking) {
    setCheckIn(b);
    setCheckInRoom(b.room_no || undefined);
  }

  async function doCheckIn() {
    if (!checkIn || !checkInRoom) {
      message.warning("请选择入住房号");
      return;
    }
    setActing(true);
    try {
      await checkInBooking(tenantCode, checkIn.id, checkInRoom);
      message.success(`预订 #${checkIn.id} 已办理入住（${checkInRoom}）`);
      setCheckIn(null);
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  }

  async function doCheckOut(b: Booking) {
    setActing(true);
    try {
      await checkOutBooking(tenantCode, b.id);
      message.success(`预订 #${b.id} 已退房`);
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  }

  async function doCancel(b: Booking) {
    try {
      await cancelBooking(tenantCode, b.id);
      message.success(`预订 #${b.id} 已取消`);
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  // M23 清单#3：手动标记 NoShow（留存原因并释放锁房）
  async function doNoshow(b: Booking) {
    let reason: string | undefined;
    try {
      reason = window.prompt("NoShow 原因（可留空）：") ?? undefined;
    } catch {
      reason = undefined;
    }
    try {
      await markBookingNoshow(tenantCode, b.id, reason);
      message.success(`预订 #${b.id} 已标记未到店（NoShow）`);
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  // M24 清单#5：智能排房推荐（历史偏好 + 房态）
  async function openRecommend(b: Booking) {
    setRecommendFor(b);
    setRecommendList([]);
    setRecommendLoading(true);
    try {
      const list = await recommendRooms(tenantCode, {
        hotelId: hotelId!,
        roomTypeId: b.room_type_id,
        guestPhone: b.guest_phone ?? null,
        limit: 5,
      });
      setRecommendList(list);
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setRecommendLoading(false);
    }
  }

  async function doRecommendCheckIn(roomNo: string) {
    if (!recommendFor) return;
    setActing(true);
    try {
      await checkInBooking(tenantCode, recommendFor.id, roomNo);
      message.success(`已按推荐为 #${recommendFor.id} 办理入住（${roomNo}）`);
      setRecommendFor(null);
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  }

  const availableRooms = checkIn
    ? rooms.filter(
        (r) =>
          r.room_type_id === checkIn.room_type_id &&
          (r.state === "vacant_clean" || r.room_no === checkIn.room_no)
      )
    : [];

  const columns = [
    { title: "ID", dataIndex: "id", key: "id", width: 64 },
    { title: "客人", dataIndex: "guest_name", key: "guest_name" },
    {
      title: "房型",
      dataIndex: "room_type_id",
      key: "room_type_id",
      render: (id: string) => rtName(id),
    },
    { title: "房号", dataIndex: "room_no", key: "room_no", render: (v: string | null) => v || "—" },
    { title: "入住", dataIndex: "check_in_date", key: "check_in_date" },
    { title: "离店", dataIndex: "check_out_date", key: "check_out_date" },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (s: BookingStatus) => (
        <Tag color={STATUS_META[s].color}>{STATUS_META[s].label}</Tag>
      ),
    },
    {
      title: "操作",
      key: "act",
      render: (_: unknown, r: Booking) => (
        <Space>
          {r.status === "created" && (
            <Button type="link" onClick={() => openCheckIn(r)}>
              办理入住
            </Button>
          )}
          {r.status === "created" && (
            <Button type="link" onClick={() => openRecommend(r)}>
              智能排房
            </Button>
          )}
          {r.status === "created" && (
            <Popconfirm title="确认取消该预订？" onConfirm={() => doCancel(r)}>
              <Button type="link" danger>
                取消
              </Button>
            </Popconfirm>
          )}
          {r.status === "created" && (
            <Popconfirm
              title="确认标记为未到店（NoShow）？"
              onConfirm={() => doNoshow(r)}
            >
              <Button type="link">未到店</Button>
            </Popconfirm>
          )}
          {r.status === "checked_in" && (
            <Button type="link" loading={acting} onClick={() => doCheckOut(r)}>
              退房
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="预订 / 入住管理"
      extra={
        <Space>
          <Select
            value={statusFilter}
            style={{ width: 130 }}
            onChange={setStatusFilter}
            options={[
              { value: "all", label: "全部" },
              { value: "created", label: "待入住" },
              { value: "checked_in", label: "在住" },
              { value: "checked_out", label: "已离店" },
              { value: "cancelled", label: "已取消" },
            ]}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!hotelId}
            onClick={() => setCreateOpen(true)}
          >
            新建预订
          </Button>
        </Space>
      }
    >
      {!hotelId ? (
        <Empty description="请先在顶栏选择门店" />
      ) : (
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={filtered}
          pagination={{ pageSize: 10 }}
        />
      )}

      <Modal
        title="新建预订"
        open={createOpen}
        onOk={submitCreate}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ channel: "direct" }}>
          <Form.Item name="guest_name" label="客人姓名" rules={[{ required: true }]}>
            <Input placeholder="如 张三" />
          </Form.Item>
          <Form.Item name="room_type_id" label="房型" rules={[{ required: true }]}>
            <Select
              placeholder="选择房型"
              options={roomTypes.map((t) => ({
                value: t.id,
                label: `${t.name}（${t.code}）`,
              }))}
            />
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
                { value: "direct", label: "直订" },
                { value: "ota", label: "OTA" },
                { value: "phone", label: "电话" },
                { value: "walk_in", label: "散客" },
              ]}
            />
          </Form.Item>
          <Form.Item name="stay_type" label="住宿类型" initialValue="daily">
            <Select
              options={[
                { value: "daily", label: "全天（按晚）" },
                { value: "hourly", label: "时租（按小时）" },
              ]}
            />
          </Form.Item>
          {formStayType === "hourly" && (
            <Form.Item
              name="hourly_hours"
              label="时租时长（小时）"
              rules={[{ required: true, message: "请输入时租小时数" }]}
            >
              <Input type="number" min={1} placeholder="如 4" />
            </Form.Item>
          )}
          <Form.Item name="room_no" label="预分配房号（可选）">
            <Input placeholder="如 301" />
          </Form.Item>
          <Form.Item name="guest_phone" label="客人手机（可选）">
            <Input placeholder="如 13800000000" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`办理入住 · 预订 #${checkIn?.id ?? ""}`}
        open={!!checkIn}
        onOk={doCheckIn}
        confirmLoading={acting}
        onCancel={() => setCheckIn(null)}
        okText="确认入住"
        cancelText="取消"
      >
        <p>
          客人：{checkIn?.guest_name} ｜ 房型：
          {checkIn ? rtName(checkIn.room_type_id) : ""}
        </p>
        <Form layout="vertical">
          <Form.Item label="入住房号" required>
            <Select
              value={checkInRoom}
              onChange={setCheckInRoom}
              showSearch
              placeholder="选择可住房间"
              options={availableRooms.map((r) => ({
                value: r.room_no,
                label: `${r.room_no}（${r.floor}层 · ${r.state === "vacant_clean" ? "空净" : r.state}）`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`智能排房 · ${recommendFor?.guest_name ?? ""}`}
        open={!!recommendFor}
        onCancel={() => setRecommendFor(null)}
        footer={null}
      >
        <p style={{ color: "#888" }}>
          基于房态（空净优先）与客人历史偏好（曾住房间 / 楼层）推荐：
        </p>
        {recommendLoading ? (
          <p>加载中…</p>
        ) : recommendList.length === 0 ? (
          <p>暂无可推荐房间（可先完成清扫或检查房态）</p>
        ) : (
          recommendList.map((x) => (
            <div
              key={x.room_no}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 0",
                borderBottom: "1px solid #f0f0f0",
              }}
            >
              <div>
                <b>{x.room_no}</b>
                <span style={{ color: "#888" }}>
                  {" "}
                  · {x.floor}层 ·{" "}
                  {x.state === "vacant_clean" ? "空净" : "空脏"} · 匹配度{" "}
                  {x.score}
                </span>
                <div style={{ fontSize: 12, color: "#52c41a" }}>
                  {x.reasons.join("；")}
                </div>
              </div>
              <Button
                type="link"
                loading={acting}
                onClick={() => doRecommendCheckIn(x.room_no)}
              >
                入住此房
              </Button>
            </div>
          ))
        )}
      </Modal>
    </Card>
  );
}
