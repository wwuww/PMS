import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CustomerServiceOutlined,
  SendOutlined,
  SwapOutlined,
  CloseOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  listChatSessions,
  listChatMessages,
  chatSendMessage,
  chatHandoff,
  chatCloseSession,
  createBooking,
  listRoomTypes,
} from "../api/endpoints";
import type { ChatSession, ChatMessage, RoomType } from "../api/types";

const { Title, Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  active: "blue",
  handoff: "orange",
  closed: "default",
};
const STATUS_LABEL: Record<string, string> = {
  active: "进行中",
  handoff: "已转人工",
  closed: "已关闭",
};
const ROLE_COLOR: Record<string, string> = {
  user: "default",
  bot: "green",
  agent: "purple",
};

export default function AIChat() {
  const { tenantCode, hotelId } = useTenant();
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [current, setCurrent] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [input, setInput] = useState("");
  const [satisfaction, setSatisfaction] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  // 来自通知中心的深链：?session=<chat_session_id>（转人工提醒直达会话）
  const [searchParams] = useSearchParams();
  const targetSession = searchParams.get("session");
  const openedSession = useRef<string | null>(null);

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const list = await listChatSessions(tenantCode, statusFilter);
      setSessions(list);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, statusFilter]);

  const openSession = async (s: ChatSession) => {
    setCurrent(s);
    setMsgLoading(true);
    try {
      const msgs = await listChatMessages(tenantCode, s.id);
      setMessages(msgs);
    } finally {
      setMsgLoading(false);
    }
  };

  useEffect(() => {
    // 深链目标会话可能已关闭，直接切「全部」筛选确保能命中
    if (targetSession && statusFilter !== "") setStatusFilter("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetSession]);

  // 列表就绪后自动打开深链会话（每组参数只开一次）
  useEffect(() => {
    if (!targetSession || !sessions.length) return;
    if (openedSession.current === targetSession) return;
    const s = sessions.find((x) => String(x.id) === targetSession);
    if (s) {
      openedSession.current = targetSession;
      openSession(s);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions, targetSession]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMsg = async () => {
    if (!current || !input.trim()) return;
    setMsgLoading(true);
    try {
      const reply = await chatSendMessage(tenantCode, current.id, input.trim(), hotelId);
      setMessages((m) => [...m, reply.bot_message]);
      setInput("");
      if (reply.handoff) {
        message.info("机器人已转人工");
        refresh();
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "发送失败");
    } finally {
      setMsgLoading(false);
    }
  };

  const handoff = async () => {
    if (!current) return;
    try {
      const msg = await chatHandoff(tenantCode, current.id, undefined, hotelId);
      setMessages((m) => [...m, msg]);
      message.success("已转人工");
      refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "转人工失败");
    }
  };

  const closeSession = async () => {
    if (!current) return;
    try {
      const s = await chatCloseSession(tenantCode, current.id, satisfaction);
      setCurrent(s);
      message.success("会话已关闭");
      refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "关闭失败");
    }
  };

  // ----- AI 会话建单：从会话一键创建预订（M11 落地） -----
  const navigate = useNavigate();
  const [bookingOpen, setBookingOpen] = useState(false);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [bookingLoading, setBookingLoading] = useState(false);
  const [lastBookingId, setLastBookingId] = useState<string | null>(null);
  const [bookingForm] = Form.useForm();

  const openBooking = async () => {
    if (!hotelId) {
      message.warning("当前未选择门店，无法创建预订");
      return;
    }
    setBookingOpen(true);
    bookingForm.setFieldsValue({
      guest_name: current?.guest_name || "",
      guest_phone: current?.guest_phone || "",
      channel: "direct",
    });
    try {
      const rt = await listRoomTypes(tenantCode);
      setRoomTypes(rt);
    } catch (e: any) {
      message.error(e?.message || "房型加载失败");
    }
  };

  const submitBooking = async () => {
    if (!hotelId) return;
    const v = await bookingForm.validateFields();
    setBookingLoading(true);
    try {
      const b = await createBooking(tenantCode, {
        hotel_id: hotelId,
        room_type_id: v.room_type_id,
        guest_name: v.guest_name,
        check_in_date: v.check_in_date.format("YYYY-MM-DD"),
        check_out_date: v.check_out_date.format("YYYY-MM-DD"),
        channel: v.channel || "direct",
        guest_phone: v.guest_phone || null,
        room_no: v.room_no || null,
        chat_session_id: current?.id ?? null,
      });
      setLastBookingId(b.id);
      message.success(`预订创建成功 #${b.id} · ${b.guest_name}（已关联本会话）`);
      setBookingOpen(false);
      bookingForm.resetFields();
    } catch (e: any) {
      message.error(e?.message || "创建失败");
    } finally {
      setBookingLoading(false);
    }
  };

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        AI 客服中心
      </Title>
      <Row gutter={16}>
        <Col span={9}>
          <Card
            size="small"
            title="会话列表"
            extra={
              <Segmented
                size="small"
                value={statusFilter}
                onChange={(v) => setStatusFilter(v as string)}
                options={[
                  { label: "进行中", value: "active" },
                  { label: "人工", value: "handoff" },
                  { label: "全部", value: "" },
                ]}
              />
            }
          >
            <List
              loading={loading}
              dataSource={sessions}
              locale={{ emptyText: "暂无会话" }}
              renderItem={(s) => (
                <List.Item
                  onClick={() => openSession(s)}
                  style={{
                    cursor: "pointer",
                    background:
                      current?.id === s.id ? "#e6f4ff" : undefined,
                    padding: "8px 10px",
                    borderRadius: 6,
                  }}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Text strong>{s.guest_name || "匿名客人"}</Text>
                        <Tag color={STATUS_COLOR[s.status]}>
                          {STATUS_LABEL[s.status]}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {s.channel} ｜ 意图：{s.intent || "—"} ｜ #
                        {s.id}
                      </Text>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col span={15}>
          <Card
            size="small"
            title={
              current ? (
                <Space>
                  <CustomerServiceOutlined />
                  会话 #{current.id} · {current.guest_name || "匿名客人"}
                  <Tag color={STATUS_COLOR[current.status]}>
                    {STATUS_LABEL[current.status]}
                  </Tag>
                </Space>
              ) : (
                "会话详情"
              )
            }
            extra={
              current && (
                <Space>
                  <Button
                    icon={<PlusOutlined />}
                    disabled={current.status === "closed" || !hotelId}
                    onClick={openBooking}
                  >
                    创建预订
                  </Button>
                  {lastBookingId != null && (
                    <Button onClick={() => navigate("/bookings")}>
                      查看订单 #{lastBookingId}
                    </Button>
                  )}
                  <Button
                    icon={<SwapOutlined />}
                    disabled={current.status === "closed"}
                    onClick={handoff}
                  >
                    转人工
                  </Button>
                  <Button
                    icon={<CloseOutlined />}
                    disabled={current.status === "closed"}
                    onClick={closeSession}
                  >
                    关闭
                  </Button>
                </Space>
              )
            }
          >
            {!current && (
              <Text type="secondary">从左侧选择一个会话查看对话</Text>
            )}
            {current && (
              <>
                <div
                  style={{
                    height: 360,
                    overflowY: "auto",
                    background: "#fafafa",
                    padding: 12,
                    borderRadius: 8,
                    marginBottom: 12,
                  }}
                >
                  {messages.map((m) => (
                    <div
                      key={m.id}
                      style={{
                        textAlign: m.role === "user" ? "right" : "left",
                        marginBottom: 8,
                      }}
                    >
                      <span
                        style={{
                          display: "inline-block",
                          maxWidth: "70%",
                          padding: "8px 12px",
                          borderRadius: 10,
                          background:
                            m.role === "user"
                              ? "#1677ff"
                              : m.role === "agent"
                              ? "#f9f0ff"
                              : "#f6ffed",
                          color:
                            m.role === "user" ? "#fff" : "#000",
                        }}
                      >
                        {m.content}
                        {m.intent && (
                          <Tag
                            style={{ marginLeft: 6 }}
                            color={ROLE_COLOR[m.role]}
                          >
                            {m.intent}
                          </Tag>
                        )}
                      </span>
                    </div>
                  ))}
                  {msgLoading && (
                    <Text type="secondary">机器人思考中…</Text>
                  )}
                  <div ref={endRef} />
                </div>
                {current.status !== "closed" && (
                  <Space.Compact style={{ width: "100%" }}>
                    <Input
                      placeholder="输入消息，机器人自动应答…"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onPressEnter={sendMsg}
                    />
                    <Button
                      type="primary"
                      icon={<SendOutlined />}
                      loading={msgLoading}
                      onClick={sendMsg}
                    >
                      发送
                    </Button>
                  </Space.Compact>
                )}
                {current.status !== "closed" && (
                  <div style={{ marginTop: 8 }}>
                    <Space>
                      <Text type="secondary">关闭满意度：</Text>
                      <InputNumber
                        min={1}
                        max={5}
                        value={satisfaction}
                        onChange={(v) => setSatisfaction(v)}
                        placeholder="1-5"
                      />
                    </Space>
                  </div>
                )}
              </>
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title={`为会话 #${current?.id ?? ""} 创建预订`}
        open={bookingOpen}
        onCancel={() => setBookingOpen(false)}
        onOk={submitBooking}
        confirmLoading={bookingLoading}
        okText="创建"
        destroyOnClose
      >
        <Form form={bookingForm} layout="vertical">
          <Form.Item
            name="guest_name"
            label="客人姓名"
            rules={[{ required: true, message: "请输入客人姓名" }]}
          >
            <Input placeholder="从会话带入，可修改" />
          </Form.Item>
          <Form.Item
            name="room_type_id"
            label="房型"
            rules={[{ required: true, message: "请选择房型" }]}
          >
            <Select
              placeholder="选择房型"
              options={roomTypes.map((r) => ({
                value: r.id,
                label: `${r.name}（¥${r.base_price / 100}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="check_in_date"
            label="入住日期"
            rules={[{ required: true, message: "请选择入住日期" }]}
          >
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            name="check_out_date"
            label="离店日期"
            rules={[{ required: true, message: "请选择离店日期" }]}
          >
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="channel" label="渠道" initialValue="direct">
            <Select
              options={[
                { value: "direct", label: "直订" },
                { value: "ctrip", label: "携程" },
                { value: "meituan", label: "美团" },
                { value: "wechat_mp", label: "微信小程序" },
              ]}
            />
          </Form.Item>
          <Form.Item name="guest_phone" label="手机号">
            <Input placeholder="选填，从会话带入" />
          </Form.Item>
          <Form.Item name="room_no" label="预排房号">
            <Input placeholder="选填，入住时再分配" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
