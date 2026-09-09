import { useCallback, useEffect, useMemo, useState } from "react";
import {
  App,
  Button,
  Alert,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Steps,
  Tag,
  Timeline,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  CreditCardOutlined,
  DollarOutlined,
  IdcardOutlined,
  ReloadOutlined,
  SwapOutlined,
  TrophyOutlined,
  WalletOutlined,
} from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import {
  receptionContext,
  receptionAdvance,
  listHotels,
  listRooms,
  listRoomTypes,
  extendStayBooking,
  changeRoomBooking,
  type ReceptionAdvanceBody,
} from "../api/endpoints";
import type {
  Hotel,
  Room,
  RoomType,
  ReceptionContext,
  ReceptionAction,
} from "../api/types";
import { useTenant } from "../store/tenant";
import { ROOM_STATE_LABELS } from "../domain/roomActions";
import { fmtCents, fmtInt } from "../utils/format";
// 必须带 .tsx 后缀：无后缀会优先解析到 format.ts（纯字符串工具），取不到组件。
import { CellAmount } from "../utils/format.tsx";
import StatCard from "../components/StatCard";

/** 办理流阶段（对齐 PRD 状态机流水线）。 */
const FLOW_STAGES: { key: string; label: string }[] = [
  { key: "query", label: "查档" },
  { key: "register", label: "建档" },
  { key: "checkin", label: "入住" },
  { key: "inhouse", label: "在住" },
  { key: "folio", label: "结账" },
  { key: "checkout", label: "退房" },
];

const ACTION_LABEL: Record<ReceptionAction, string> = {
  register: "建档 / 建预订",
  check_in: "办理入住",
  open_folio: "确认在开账单",
  check_out: "退房结账",
  enroll_member: "办理会员",
};

const CHANNEL_LABEL: Record<string, string> = {
  walk_in: "散客",
  direct: "直订",
  ota: "OTA",
  phone: "电话",
  agreement: "协议",
  wechat: "微信",
};

export default function ReceptionWorkbenchPage() {
  const { tenantCode } = useTenant();
  const { message } = App.useApp();

  const [ctx, setCtx] = useState<ReceptionContext | null>(null);
  const [query, setQuery] = useState({ guest_phone: "", booking_id: "", room_no: "" });
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [pendingAction, setPendingAction] = useState<ReceptionAction | null>(null);
  const [r4Type, setR4Type] = useState<"extend" | "change" | null>(null);
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [form] = Form.useForm();

  const loadSelectors = useCallback(async () => {
    if (!tenantCode) return;
    const [h, r, rt] = await Promise.all([
      listHotels(tenantCode),
      listRooms(tenantCode),
      listRoomTypes(tenantCode),
    ]);
    setHotels(h);
    setRooms(r);
    setRoomTypes(rt);
  }, [tenantCode]);

  useEffect(() => {
    loadSelectors();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const runQuery = useCallback(async () => {
    if (!tenantCode) return;
    const body = {
      guest_phone: query.guest_phone.trim() || null,
      booking_id: query.booking_id.trim() ? Number(query.booking_id.trim()) : null,
      room_no: query.room_no.trim() || null,
    };
    if (!body.guest_phone && !body.booking_id && !body.room_no) {
      message.warning("请填写手机号 / 预订号 / 房号任一查询条件");
      return;
    }
    setLoading(true);
    try {
      const c = await receptionContext(tenantCode, body);
      setCtx(c);
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tenantCode, query, message]);

  const refresh = useCallback(async () => {
    if (!tenantCode) return;
    const body = {
      guest_phone: query.guest_phone.trim() || null,
      booking_id: query.booking_id.trim() ? Number(query.booking_id.trim()) : null,
      room_no: query.room_no.trim() || null,
    };
    const c = await receptionContext(tenantCode, body);
    setCtx(c);
  }, [tenantCode, query]);

  // 可排房（空净 / 锁房）
  const assignableRooms = useMemo(
    () => rooms.filter((r) => r.state === "vacant_clean" || r.state === "arrival_locked"),
    [rooms]
  );
  const rtName = (id: number | string | null | undefined) =>
    id == null ? "—" : roomTypes.find((x) => x.id === String(id))?.name ?? `#${id}`;

  
  const currentStep = ctx ? FLOW_STAGES.findIndex((s) => s.key === ctx.flow_state) : -1;

  const openAction = (a: ReceptionAction) => {
    form.resetFields();
    if (a === "register" || a === "enroll_member") {
      form.setFieldsValue({ guest_phone: query.guest_phone || ctx?.guest?.phone || "" });
    }
    if (a === "check_in" && ctx?.booking) {
      form.setFieldsValue({ booking_id: ctx.booking.id });
    }
    setPendingAction(a);
  };

  const submitAction = async () => {
    if (!tenantCode || !pendingAction || !ctx) return;
    try {
      const v = await form.validateFields();
      const body: ReceptionAdvanceBody = {
        action: pendingAction,
        guest_phone: query.guest_phone.trim() || ctx.guest?.phone || null,
        booking_id: ctx.booking?.id ?? null,
        room_no: ctx.room_no || query.room_no.trim() || null,
        operator: "front_desk",
      };
      if (pendingAction === "register") {
        if (!v.hotel_id || !v.guest_name) {
          message.error("建档需选择门店并填写姓名");
          return;
        }
        body.hotel_id = v.hotel_id;
        body.guest_name = v.guest_name;
        body.id_type = v.id_type ?? null;
        body.id_no = v.id_no ?? null;
      } else if (pendingAction === "enroll_member") {
        if (!v.hotel_id) {
          message.error("办会员需选择归属门店");
          return;
        }
        body.hotel_id = v.hotel_id;
      } else if (pendingAction === "check_in") {
        if (ctx.booking) {
          // 预订模式：复用既有预订
          body.booking_id = ctx.booking.id;
        } else {
          // 散客模式：需要房号 + 房型 + 姓名 + 日期
          const room = rooms.find((r) => r.room_no === v.room_no);
          if (!room || !v.guest_name || !v.check_in_date || !v.check_out_date) {
            message.error("散客入住需选择房号、填写姓名与入住/离店日期");
            return;
          }
          body.room_no = room.room_no;
          body.room_type_id = Number(room.room_type_id);
          body.guest_name = v.guest_name;
          body.check_in_date = (v.check_in_date as Dayjs).format("YYYY-MM-DD");
          body.check_out_date = (v.check_out_date as Dayjs).format("YYYY-MM-DD");
        }
      }
      setActing(true);
      const next = await receptionAdvance(tenantCode, body);
      setCtx(next);
      setPendingAction(null);
      message.success(`已执行：${ACTION_LABEL[pendingAction]}`);
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  };

  const submitR4 = async () => {
    if (!tenantCode || !ctx?.booking || !r4Type) return;
    try {
      const v = await form.validateFields();
      setActing(true);
      if (r4Type === "extend") {
        await extendStayBooking(
          tenantCode,
          String(ctx.booking.id),
          (v.new_check_out_date as Dayjs).format("YYYY-MM-DD")
        );
        message.success("续住已生效");
      } else {
        await changeRoomBooking(tenantCode, String(ctx.booking.id), v.new_room_no);
        message.success("换房已生效");
      }
      setR4Type(null);
      await refresh();
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setActing(false);
    }
  };

  const isInhouse = ctx?.flow_state === "inhouse";

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
            统一接待办理工作台
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            查档 → 建档 → 入住 → 在住 → 结账 → 退房
          </Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={runQuery} loading={loading}>
            重新查询
          </Button>
        </Space>
      </div>

      {/* 查询栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="手机号"
            value={query.guest_phone}
            onChange={(e) => setQuery((q) => ({ ...q, guest_phone: e.target.value }))}
            allowClear
            style={{ width: 160 }}
          />
          <Input
            placeholder="预订号"
            value={query.booking_id}
            onChange={(e) => setQuery((q) => ({ ...q, booking_id: e.target.value }))}
            allowClear
            style={{ width: 140 }}
          />
          <Input
            placeholder="房号"
            value={query.room_no}
            onChange={(e) => setQuery((q) => ({ ...q, room_no: e.target.value }))}
            allowClear
            style={{ width: 120 }}
          />
          <Button type="primary" onClick={runQuery} loading={loading}>
            查询
          </Button>
        </Space>
      </Card>

      {loading && !ctx ? (
        <Card>
          <Spin />
        </Card>
      ) : !ctx ? (
        <Card>
          <Empty description="输入手机号 / 预订号 / 房号，查询单客全貌（客档·会员·预订·房态·账单·审计）" />
        </Card>
      ) : (
        <>
          {/* 办理流进度 */}
          <Card size="small" style={{ marginBottom: 16 }}>
            <Steps
              size="small"
              current={currentStep < 0 ? 0 : currentStep}
              items={FLOW_STAGES.map((s) => ({ title: s.label }))}
            />
          </Card>

          {/* 单客关键数字（StatCard 基线，数据取自 ctx，未新增接口） */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={12} md={6}>
              <StatCard
                label="累计消费"
                value={ctx.guest ? fmtCents(ctx.guest.total_spend) : "—"}
                sub={ctx.guest ? `入住 ${ctx.guest.stay_count} 次 · VIP ${ctx.guest.vip_level}` : "尚无客档"}
                accent="#1677ff"
                icon={<DollarOutlined />}
              />
            </Col>
            <Col xs={12} sm={12} md={6}>
              <StatCard
                label="会员储值"
                value={ctx.membership ? fmtCents(ctx.membership.stored_value) : "—"}
                sub={ctx.membership ? `等级 ${ctx.membership.level}` : "未关联会员"}
                accent="#13c2c2"
                icon={<WalletOutlined />}
              />
            </Col>
            <Col xs={12} sm={12} md={6}>
              <StatCard
                label="会员积分"
                value={ctx.membership ? fmtInt(ctx.membership.points) : "—"}
                sub={ctx.membership ? `历史入住 ${ctx.membership.stays} 次` : "未关联会员"}
                accent="#fa8c16"
                icon={<TrophyOutlined />}
              />
            </Col>
            <Col xs={12} sm={12} md={6}>
              <StatCard
                label="在开账单余额"
                value={ctx.folio ? fmtCents(ctx.folio.balance) : "—"}
                sub={ctx.folio ? `${ctx.folio.bill_no} · ${ctx.folio.item_count} 项` : "暂无在开账单"}
                accent="#722ed1"
                icon={<CreditCardOutlined />}
              />
            </Col>
          </Row>

          {/* 客史洞察（R7） */}
          {ctx.insights.length > 0 && (
            <Card size="small" style={{ marginBottom: 16, background: "#f6ffed", borderColor: "#b7eb8f" }}>
              <Space wrap>
                <Typography.Text strong>
                  <IdcardOutlined /> 客史洞察：
                </Typography.Text>
                {ctx.insights.map((s, i) => (
                  <Tag key={i} color="green">
                    {s}
                  </Tag>
                ))}
              </Space>
            </Card>
          )}

          {/* 断网/降级提示（Q4 容错）：部分聚合暂不可用时降级而非整页报错 */}
          {ctx.degraded && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message="部分信息降级展示"
              description={
                <span>
                  以下数据暂不可用，其余功能正常：
                  {ctx.degradation_notes && ctx.degradation_notes.length > 0
                    ? ctx.degradation_notes.map((n, i) => (
                        <Tag key={i} color="orange" style={{ marginLeft: 4 }}>
                          {n}
                        </Tag>
                      ))
                    : "（未知原因）"}
                </span>
              }
            />
          )}

          {/* 动作区：状态机可继续动作 + 在住附加（R4） */}
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space wrap>
              <Typography.Text type="secondary">可继续：</Typography.Text>
              {ctx.can_advance.length === 0 && (
                <Tag color="default">无（已至终态或可回溯结束）</Tag>
              )}
              {ctx.can_advance.map((a) => (
                <Button
                  key={a}
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  onClick={() => openAction(a)}
                >
                  {ACTION_LABEL[a]}
                </Button>
              ))}
              {isInhouse && (
                <>
                  <Typography.Text type="secondary" style={{ marginLeft: 12 }}>
                    在住附加：
                  </Typography.Text>
                  <Button icon={<ReloadOutlined />} onClick={() => { form.resetFields(); setR4Type("extend"); }}>
                    续住
                  </Button>
                  <Button icon={<SwapOutlined />} onClick={() => { form.resetFields(); setR4Type("change"); }}>
                    换房
                  </Button>
                </>
              )}
            </Space>
          </Card>

          {/* 单客全貌 */}
          <Row gutter={16}>
            {/* 客档 */}
            <Col span={8}>
              <Card size="small" title="客档" style={{ marginBottom: 16 }}>
                {ctx.guest ? (
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="姓名">{ctx.guest.name}</Descriptions.Item>
                    <Descriptions.Item label="手机号">{ctx.guest.phone ?? "—"}</Descriptions.Item>
                    <Descriptions.Item label="VIP">{ctx.guest.vip_level}</Descriptions.Item>
                    <Descriptions.Item label="入住次数">{ctx.guest.stay_count}</Descriptions.Item>
                    <Descriptions.Item label="累计消费">
                      <CellAmount value={ctx.guest.total_spend} />
                    </Descriptions.Item>
                    {ctx.guest.member_level && (
                      <Descriptions.Item label="关联会员等级">{ctx.guest.member_level}</Descriptions.Item>
                    )}
                  </Descriptions>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无客档" />
                )}
              </Card>
            </Col>

            {/* 会员 + 房态 */}
            <Col span={8}>
              <Card size="small" title="会员（CRM）" style={{ marginBottom: 16 }}>
                {ctx.membership ? (
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="等级">{ctx.membership.level}</Descriptions.Item>
                    <Descriptions.Item label="储值">
                      <CellAmount value={ctx.membership.stored_value} />
                    </Descriptions.Item>
                    <Descriptions.Item label="积分">{ctx.membership.points}</Descriptions.Item>
                    <Descriptions.Item label="入住次数">{ctx.membership.stays}</Descriptions.Item>
                  </Descriptions>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未关联会员" />
                )}
              </Card>
              <Card size="small" title="房态">
                {ctx.room_no ? (
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="房号">{ctx.room_no}</Descriptions.Item>
                    <Descriptions.Item label="状态">
                      {ctx.room_state ? (
                        <Tag color="blue">{ROOM_STATE_LABELS[ctx.room_state as keyof typeof ROOM_STATE_LABELS] ?? ctx.room_state}</Tag>
                      ) : (
                        "—"
                      )}
                    </Descriptions.Item>
                  </Descriptions>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未排房" />
                )}
              </Card>
            </Col>

            {/* 预订 + 账单 */}
            <Col span={8}>
              <Card size="small" title="预订" style={{ marginBottom: 16 }}>
                {ctx.booking ? (
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="客人">{ctx.booking.guest_name}</Descriptions.Item>
                    <Descriptions.Item label="渠道">{CHANNEL_LABEL[ctx.booking.channel] ?? ctx.booking.channel}</Descriptions.Item>
                    <Descriptions.Item label="房型">{rtName(ctx.booking.room_type_id)}</Descriptions.Item>
                    <Descriptions.Item label="房号">{ctx.booking.room_no ?? "未排房"}</Descriptions.Item>
                    <Descriptions.Item label="入住">{ctx.booking.check_in_date}</Descriptions.Item>
                    <Descriptions.Item label="离店">{ctx.booking.check_out_date}</Descriptions.Item>
                    <Descriptions.Item label="状态">
                      <Tag color={ctx.booking.status === "checked_in" ? "green" : "gold"}>{ctx.booking.status}</Tag>
                    </Descriptions.Item>
                  </Descriptions>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无预订" />
                )}
              </Card>
              <Card size="small" title="在开账单">
                {ctx.folio ? (
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="账单号">{ctx.folio.bill_no}</Descriptions.Item>
                    <Descriptions.Item label="余额">
                      <CellAmount value={ctx.folio.balance} />
                    </Descriptions.Item>
                    <Descriptions.Item label="笔数">{ctx.folio.item_count} 项 / {ctx.folio.payment_count} 笔</Descriptions.Item>
                  </Descriptions>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无在开账单" />
                )}
              </Card>
            </Col>
          </Row>

          {/* 审计轨迹 */}
          {ctx.audit_log.length > 0 && (
            <Card size="small" title="办理流审计轨迹" style={{ marginTop: 16 }}>
              <Timeline
                items={ctx.audit_log.map((a) => ({
                  children: (
                    <span>
                      <Tag>{a.action}</Tag> {a.resource_type}
                      {a.resource_id ? ` #${a.resource_id}` : ""} · {a.actor}
                      {a.created_at ? ` · ${a.created_at}` : ""}
                    </span>
                  ),
                }))}
              />
            </Card>
          )}
        </>
      )}

      {/* 状态机动作 Modal */}
      <Modal
        title={pendingAction ? `办理流 · ${ACTION_LABEL[pendingAction]}` : ""}
        open={pendingAction !== null}
        onCancel={() => setPendingAction(null)}
        onOk={submitAction}
        confirmLoading={acting}
        okText="继续"
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          {pendingAction === "register" && (
            <>
              <Form.Item name="hotel_id" label="门店" rules={[{ required: true, message: "请选择门店" }]}>
                <Select
                  placeholder="选择门店"
                  options={hotels.map((h) => ({ value: Number(h.id), label: h.name }))}
                />
              </Form.Item>
              <Form.Item name="guest_name" label="客人姓名" rules={[{ required: true, message: "请填写姓名" }]}>
                <Input placeholder="必填" />
              </Form.Item>
              <Form.Item name="guest_phone" label="手机号">
                <Input placeholder="选填" />
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
          )}

          {pendingAction === "enroll_member" && (
            <>
              <Form.Item name="hotel_id" label="归属门店" rules={[{ required: true, message: "请选择归属门店" }]}>
                <Select
                  placeholder="选择门店"
                  options={hotels.map((h) => ({ value: Number(h.id), label: h.name }))}
                />
              </Form.Item>
              <Typography.Paragraph type="secondary">
                将为客档
                {ctx?.guest ? `（${ctx.guest.name} · ${ctx.guest.phone ?? "—"}）` : ""}
                现场办理会员（{ctx?.membership ? "该手机号已存在会员，将直接关联" : "新建 NORMAL 等级会员并关联客档"}）。
              </Typography.Paragraph>
            </>
          )}

          {pendingAction === "check_in" && (
            <>
              {ctx?.booking ? (
                <Typography.Paragraph type="secondary">
                  将使用预订 #{ctx.booking.id}（{ctx.booking.guest_name} · {ctx.booking.room_no ?? "未排房"}）办理入住。
                </Typography.Paragraph>
              ) : (
                <>
                  <Form.Item name="room_no" label="入住房号" rules={[{ required: true, message: "请选择房号" }]}>
                    <Select
                      showSearch
                      placeholder="选择可排房（空净 / 锁房）"
                      options={assignableRooms.map((r) => ({
                        value: r.room_no,
                        label: `${r.room_no} · ${ROOM_STATE_LABELS[r.state]}`,
                      }))}
                    />
                  </Form.Item>
                  <Form.Item name="guest_name" label="客人姓名" rules={[{ required: true, message: "请填写姓名" }]}>
                    <Input placeholder="必填" />
                  </Form.Item>
                  <Space size="large">
                    <Form.Item name="check_in_date" label="入住日" initialValue={dayjs()}>
                      <DatePicker />
                    </Form.Item>
                    <Form.Item name="check_out_date" label="离店日" initialValue={dayjs().add(1, "day")}>
                      <DatePicker />
                    </Form.Item>
                  </Space>
                </>
              )}
            </>
          )}

          {pendingAction === "open_folio" && (
            <Typography.Paragraph type="secondary">
              将确认当前在开账单（{ctx?.folio ? ctx.folio.bill_no : "自动开账"}），随后进入结账阶段。
            </Typography.Paragraph>
          )}

          {pendingAction === "check_out" && (
            <Typography.Paragraph type="secondary">
              将为{ctx?.booking ? `预订 #${ctx.booking.id}` : ""}{ctx?.room_no ? ` 房号 ${ctx.room_no}` : ""}办理退房结账。
            </Typography.Paragraph>
          )}
        </Form>
      </Modal>

      {/* R4 续住 / 换房 Modal */}
      <Modal
        title={r4Type === "extend" ? "续住（延住）" : "换房"}
        open={r4Type !== null}
        onCancel={() => setR4Type(null)}
        onOk={submitR4}
        confirmLoading={acting}
        okText="确认"
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          {r4Type === "extend" && (
            <Form.Item
              name="new_check_out_date"
              label="新离店日"
              initialValue={dayjs().add(1, "day")}
              rules={[{ required: true, message: "请选择新离店日" }]}
            >
              <DatePicker />
            </Form.Item>
          )}
          {r4Type === "change" && (
            <Form.Item name="new_room_no" label="目标房号" rules={[{ required: true, message: "请选择目标房号" }]}>
              <Select
                showSearch
                placeholder="选择可排房（空净 / 锁房）"
                options={assignableRooms
                  .filter((r) => r.room_no !== ctx?.room_no)
                  .map((r) => ({
                    value: r.room_no,
                    label: `${r.room_no} · ${ROOM_STATE_LABELS[r.state]}`,
                  }))}
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}
