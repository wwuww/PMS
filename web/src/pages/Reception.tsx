import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Table,
  Tabs,
  Tag,
  Typography,
  Space,
} from "antd";
import {
  HomeOutlined,
  ReloadOutlined,
  SolutionOutlined,
} from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { listRooms, listBookings, listRoomTypes, receptionCheckIn, listHousekeeping } from "../api/endpoints";
import type { Room, Booking, RoomType, RoomState, ReceptionCheckIn } from "../api/types";
import { useTenant } from "../store/tenant";
import { ROOM_STATE_LABELS } from "../domain/roomActions";
import { fmtCents } from "../utils/format";
// 必须带 .tsx 后缀：无后缀会优先解析到 format.ts（纯字符串工具），取不到组件。
import { CellAmount } from "../utils/format.tsx";
import StatCard from "../components/StatCard";

const STATE_COLOR: Record<RoomState, string> = {
  vacant_clean: "#389e0d",
  vacant_dirty: "#8c8c8c",  // 空脏=灰色
  occupied: "#0958d9",
  arrival_locked: "#08979c",
  maintenance: "#cf1322",
  out_of_service: "#595959",
};

const CHANNEL_LABEL: Record<string, string> = {
  walk_in: "散客",
  direct: "直订",
  ota: "OTA",
  phone: "电话",
  agreement: "协议",
  wechat: "微信",
};

export default function ReceptionPage() {
  const { tenantCode } = useTenant();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [rooms, setRooms] = useState<Room[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);
  const [receptionOpen, setReceptionOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("resv");
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  // 住脏：在住但有未完成清扫工单（CLEANUP, PENDING/ASSIGNED）的房间
  const [occDirtyRooms, setOccDirtyRooms] = useState<Set<string>>(new Set());

  // 可排房（空净 / 锁房）
  const assignableRooms = useMemo(
    () => rooms.filter((r) => r.state === "vacant_clean" || r.state === "arrival_locked"),
    [rooms]
  );
  // 可办理入住的预订（CREATED）
  const resvBookings = useMemo(
    () => bookings.filter((b) => b.status === "created"),
    [bookings]
  );

  const handleReception = async () => {
    try {
      const v = await form.validateFields();
      if (!v.room_no) {
        message.error("请选择入住房号");
        return;
      }
      const payload: ReceptionCheckIn = { room_no: v.room_no, operator: "front_desk" };
      if (activeTab === "resv") {
        if (!v.booking_id) {
          message.error("请选择预订");
          return;
        }
        payload.booking_id = v.booking_id;
        payload.guest_phone = v.guest_phone ?? null;
        payload.id_type = v.id_type ?? null;
        payload.id_no = v.id_no ?? null;
      } else {
        if (!v.room_type_id || !v.guest_name || !v.check_in_date || !v.check_out_date) {
          message.error("散客需填写房型 / 姓名 / 入住日 / 离店日");
          return;
        }
        payload.room_type_id = v.room_type_id;
        payload.guest_name = v.guest_name;
        payload.guest_phone = v.guest_phone ?? null;
        payload.id_type = v.id_type ?? null;
        payload.id_no = v.id_no ?? null;
        payload.check_in_date = (v.check_in_date as Dayjs).format("YYYY-MM-DD");
        payload.check_out_date = (v.check_out_date as Dayjs).format("YYYY-MM-DD");
      }
      setSubmitting(true);
      const b = await receptionCheckIn(tenantCode, payload);
      message.success(`入住办理成功：${b.guest_name} · ${b.room_no}`);
      setReceptionOpen(false);
      form.resetFields();
      await load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const today = dayjs().format("YYYY-MM-DD");

  const load = useCallback(async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [rm, bk, rt] = await Promise.all([
        listRooms(tenantCode),
        listBookings(tenantCode),
        listRoomTypes(tenantCode),
      ]);
      setRooms(rm);
      setBookings(bk);
      setRoomTypes(rt);
      try {
        const tasks = await listHousekeeping(tenantCode);
        setOccDirtyRooms(
          new Set(
            tasks
              .filter((t: any) => t.task_type === "CLEANUP" && (t.status === "PENDING" || t.status === "ASSIGNED"))
              .map((t: any) => t.room_no)
          )
        );
      } catch {
        /* 工单拉取失败不阻断页面 */
      }
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tenantCode, message]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const rtName = (id: string) =>
    roomTypes.find((x) => x.id === id)?.name ?? `#${id}`;

  // 房态概览
  const stateCounts = useMemo(() => {
    const c: Partial<Record<RoomState, number>> = {};
    for (const r of rooms) c[r.state] = (c[r.state] || 0) + 1;
    return c;
  }, [rooms]);

  // 今日预抵：created 且入住日=今天
  const arrivals = useMemo(
    () =>
      bookings.filter(
        (b) => b.status === "created" && b.check_in_date === today
      ),
    [bookings, today]
  );
  // 今日预离：checked_in 且离店日=今天
  const departures = useMemo(
    () =>
      bookings.filter(
        (b) => b.status === "checked_in" && b.check_out_date === today
      ),
    [bookings, today]
  );
  // 在住：全部 checked_in
  const inHouse = useMemo(
    () => bookings.filter((b) => b.status === "checked_in"),
    [bookings]
  );
  // 待清扫：空脏房
  const dirtyRooms = useMemo(
    () => rooms.filter((r) => r.state === "vacant_dirty"),
    [rooms]
  );
  // 房费列（统一右对齐 + 金额单元格）。
  const priceCol = {
    title: "房费",
    dataIndex: "total_price",
    key: "total_price",
    width: 108,
    align: "right" as const,
    className: "text-right",
    render: (v: number | null) => <CellAmount value={v ?? 0} />,
  };

  const bookingCols = [
    { title: "客人", dataIndex: "guest_name", key: "guest_name", render: (v: string) => v || "—" },
    {
      title: "房型",
      dataIndex: "room_type_id",
      key: "room_type_id",
      render: (v: string) => rtName(v),
    },
    {
      title: "房号",
      dataIndex: "room_no",
      key: "room_no",
      render: (v: string | null) => v ?? <Tag color="orange">未排房</Tag>,
    },
    {
      title: "渠道",
      dataIndex: "channel",
      key: "channel",
      render: (v: string) => CHANNEL_LABEL[v] ?? v,
    },
  ];

  const roomCols = [
    { title: "房号", dataIndex: "room_no", key: "room_no" },
    { title: "楼层", dataIndex: "floor", key: "floor", render: (v: string) => v || "—" },
    {
      title: "状态",
      dataIndex: "state",
      key: "state",
      render: (v: RoomState, record: Room) => {
        // 住脏：蓝灰渐变（在住 + 未完成清扫工单）
        if (v === "occupied" && occDirtyRooms.has(record.room_no)) {
          return (
            <Tag
              style={{
                background: "linear-gradient(135deg, #1677ff 0%, #8c8c8c 100%)",
                color: "#fff",
                border: "none",
              }}
              title="住脏：待清扫"
            >
              住脏
            </Tag>
          );
        }
        return <Tag color={STATE_COLOR[v]}>{ROOM_STATE_LABELS[v]}</Tag>;
      },
    },
  ];

  return (
    <div>
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
            前台接待看板
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            今日预抵 / 预离 · 在住 · 待清扫 · 房态概览
          </Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<SolutionOutlined />}
            onClick={() => setReceptionOpen(true)}
          >
            接待办理
          </Button>
        </Space>
      </div>

      {/* 房态概览 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {(["vacant_clean", "vacant_dirty", "occupied", "arrival_locked", "maintenance", "out_of_service"] as RoomState[]).map((s) => (
          <Col xs={12} sm={8} md={4} key={s}>
            <StatCard
              label={ROOM_STATE_LABELS[s]}
              value={stateCounts[s] || 0}
              suffix="间"
              accent={STATE_COLOR[s]}
              icon={<HomeOutlined />}
            />
          </Col>
        ))}
      </Row>

      {/* 今日预抵 / 今日预离 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card
            title={`今日预抵（${arrivals.length}）`}
            size="small"
            extra={
              <Button size="small" type="link" onClick={() => navigate("/bookings")}>
                预订管理
              </Button>
            }
            loading={loading && bookings.length === 0}
          >
            {arrivals.length ? (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  ...bookingCols,
                  priceCol,
                  {
                    title: "操作",
                    key: "op",
                    render: (_: unknown, b: Booking) => (
                      <Button
                        size="small"
                        type="primary"
                        onClick={() => navigate("/rooms")}
                      >
                        排房/入住
                      </Button>
                    ),
                  },
                ]}
                dataSource={arrivals}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="今日无预抵" />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card
            title={`今日预离（${departures.length}）`}
            size="small"
            extra={
              <Button size="small" type="link" onClick={() => navigate("/rooms")}>
                房态盘
              </Button>
            }
            loading={loading && bookings.length === 0}
          >
            {departures.length ? (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  ...bookingCols,
                  priceCol,
                  {
                    title: "操作",
                    key: "op",
                    render: (_: unknown, b: Booking) => (
                      <Button
                        size="small"
                        danger
                        onClick={() => navigate("/rooms")}
                      >
                        退房/结账
                      </Button>
                    ),
                  },
                ]}
                dataSource={departures}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="今日无预离" />
            )}
          </Card>
        </Col>
      </Row>

      {/* 在住 / 待清扫 */}
      <Row gutter={16}>
        <Col span={12}>
          <Card
            title={`在住（${inHouse.length}）`}
            size="small"
            extra={
              <Button size="small" type="link" onClick={() => navigate("/rooms")}>
                房态盘
              </Button>
            }
            loading={loading && bookings.length === 0}
          >
            {inHouse.length ? (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  { title: "客人", dataIndex: "guest_name", key: "guest_name", render: (v: string) => v || "—" },
                  { title: "房号", dataIndex: "room_no", key: "room_no", render: (v: string | null) => v ?? "—" },
                  { title: "离店", dataIndex: "check_out_date", key: "check_out_date" },
                  priceCol,
                  {
                    title: "操作",
                    key: "op",
                    render: (_: unknown, b: Booking) => (
                      <Button
                        size="small"
                        onClick={() =>
                          navigate(
                            `/billing?booking=${b.id}${b.room_no ? `&room=${b.room_no}` : ""}`
                          )
                        }
                      >
                        账单
                      </Button>
                    ),
                  },
                ]}
                dataSource={inHouse}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前无在住" />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card
            title={`待清扫（${dirtyRooms.length}）`}
            size="small"
            extra={
              <Button size="small" type="link" onClick={() => navigate("/housekeeping")}>
                清扫工单
              </Button>
            }
            loading={loading && rooms.length === 0}
          >
            {dirtyRooms.length ? (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  ...roomCols,
                  {
                    title: "操作",
                    key: "op",
                    render: (_: unknown, r: Room) => (
                      <Button
                        size="small"
                        onClick={() => navigate("/housekeeping")}
                      >
                        派单
                      </Button>
                    ),
                  },
                ]}
                dataSource={dirtyRooms}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无待清扫房间" />
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title="统一接待办理"
        open={receptionOpen}
        onCancel={() => {
          setReceptionOpen(false);
          form.resetFields();
        }}
        onOk={handleReception}
        confirmLoading={submitting}
        okText="办理入住"
        width={580}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="room_no" label="入住房号">
            <Select
              showSearch
              placeholder="选择可排房（空净 / 锁房）"
              options={assignableRooms.map((r) => ({
                value: r.room_no,
                label: `${r.room_no} · ${ROOM_STATE_LABELS[r.state]}`,
              }))}
            />
          </Form.Item>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: "resv",
                label: "预订入住",
                children: (
                  <>
                    <Form.Item name="booking_id" label="预订">
                      <Select
                        showSearch
                        placeholder="选择 CREATED 预订"
                        options={resvBookings.map((b) => ({
                          // ⚠️ 雪花 ID 不要 Number()：JSON 序列化会截成 17 位有效数字
                          value: String(b.id),
                          label: `${b.guest_name} · ${rtName(b.room_type_id)} · ${b.check_in_date} · ${b.room_no ?? "未排房"}`,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name="guest_phone" label="手机号（证件登记）">
                      <Input placeholder="选填，用于客史 / 会员关联" />
                    </Form.Item>
                    <Form.Item name="id_type" label="证件类型">
                      <Select
                        allowClear
                        placeholder="选填"
                        options={[
                          { value: "ID", label: "身份证" },
                          { value: "PASSPORT", label: "护照" },
                          { value: "OFFICER", label: "军官证" },
                          { value: "OTHER", label: "其他" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item name="id_no" label="证件号">
                      <Input placeholder="选填" />
                    </Form.Item>
                  </>
                ),
              },
              {
                key: "walk",
                label: "散客登记",
                children: (
                  <>
                    <Form.Item name="room_type_id" label="房型">
                      <Select
                        showSearch
                        placeholder="选择房型"
                        options={roomTypes.map((rt) => ({ value: rt.id, label: rt.name }))}
                      />
                    </Form.Item>
                    <Form.Item name="guest_name" label="客人姓名">
                      <Input placeholder="必填" />
                    </Form.Item>
                    <Form.Item name="guest_phone" label="手机号">
                      <Input placeholder="选填，用于客史 / 会员关联" />
                    </Form.Item>
                    <Form.Item name="id_type" label="证件类型">
                      <Select
                        allowClear
                        placeholder="选填"
                        options={[
                          { value: "ID", label: "身份证" },
                          { value: "PASSPORT", label: "护照" },
                          { value: "OFFICER", label: "军官证" },
                          { value: "OTHER", label: "其他" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item name="id_no" label="证件号">
                      <Input placeholder="选填" />
                    </Form.Item>
                    <Space size="large">
                      <Form.Item name="check_in_date" label="入住日" initialValue={dayjs()}>
                        <DatePicker />
                      </Form.Item>
                      <Form.Item
                        name="check_out_date"
                        label="离店日"
                        initialValue={dayjs().add(1, "day")}
                      >
                        <DatePicker />
                      </Form.Item>
                    </Space>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Modal>
    </div>
  );
}
