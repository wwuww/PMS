import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Col,
  DatePicker,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CloudUploadOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import { yuanToCents } from "../utils/format";
import {
  listChannelRoomMappings,
  upsertChannelRoomMapping,
  deleteChannelRoomMapping,
  listChannelRatePlans,
  upsertChannelRatePlan,
  deleteChannelRatePlan,
  pushChannelInventory,
  pushChannelRates,
  listChannelPushLogs,
  listRoomTypes,
  listOtaConfigs,
  upsertOtaConfig,
} from "../api/endpoints";
import type {
  ChannelRoomMapping,
  ChannelRatePlan,
  ChannelPushLog,
  RoomType,
  OtaConfig,
} from "../api/types";

const { Title, Text } = Typography;

const CHANNELS = [
  { value: "ota_ctrip", label: "携程 Ctrip" },
  { value: "ota_meituan", label: "美团 Meituan" },
  { value: "ota_fliggy", label: "飞猪 Fliggy" },
  { value: "sandbox", label: "沙箱（自测）" },
];

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  SUCCESS: { color: "green", label: "成功" },
  DRY_RUN: { color: "blue", label: "演练" },
  FAILED: { color: "red", label: "失败" },
};

export default function ChannelCenter() {
  const { tenantCode } = useTenant();
  const [tab, setTab] = useState("configs");

  if (!tenantCode) return <Empty description="缺少租户" />;

  return (
    <div>
      <Title level={4} style={{ marginTop: 0 }}>OTA 渠道中心</Title>
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          { key: "configs", label: "渠道配置", children: <ConfigsTab /> },
          { key: "mappings", label: "房型映射", children: <MappingsTab /> },
          { key: "rates", label: "渠道价", children: <RatesTab /> },
          { key: "logs", label: "推送日志", children: <LogsTab /> },
          { key: "push", label: "推送", children: <PushTab /> },
        ]}
      />
    </div>
  );
}

// ========== 渠道配置 ==========

function ConfigsTab() {
  const { tenantCode } = useTenant();
  const [list, setList] = useState<OtaConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<OtaConfig | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setList(await listOtaConfigs(tenantCode));
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const onUpsert = async () => {
    const v = await form.validateFields();
    try {
      await upsertOtaConfig(tenantCode!, {
        hotel_id: Number(v.hotel_id),
        channel: v.channel,
        secret: v.secret,
        push_enabled: v.push_enabled ?? true,
      });
      message.success("已保存");
      setEditing(null);
      form.resetFields();
      load();
    } catch (e: any) {
      message.error(e?.message || "保存失败");
    }
  };

  return (
    <Card
      title="渠道接入配置（每租户每渠道一条）"
      extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
    >
      <Table
        loading={loading}
        dataSource={list}
        rowKey="id"
        size="small"
        pagination={false}
        columns={[
          { title: "渠道", dataIndex: "channel", render: (v) => CHANNELS.find((c) => c.value === v)?.label ?? v },
          { title: "酒店 ID", dataIndex: "hotel_id" },
          { title: "推送", dataIndex: "push_enabled", render: (v) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>) },
          {
            title: "操作",
            render: (_, r) => (
              <Button size="small" onClick={() => {
                setEditing(r);
                form.setFieldsValue({
                  hotel_id: r.hotel_id,
                  channel: r.channel,
                  secret: "",
                  push_enabled: !!r.push_enabled,
                });
              }}>编辑</Button>
            ),
          },
        ]}
      />
      <Button
        type="primary"
        icon={<PlusOutlined />}
        style={{ marginTop: 12 }}
        onClick={() => {
          setEditing({} as any);
          form.resetFields();
          form.setFieldsValue({ push_enabled: true });
        }}
      >
        新增渠道配置
      </Button>

      <Modal
        open={!!editing}
        title={editing?.id ? "编辑渠道配置" : "新增渠道配置"}
        onCancel={() => setEditing(null)}
        onOk={onUpsert}
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="channel" label="渠道" rules={[{ required: true }]}>
            <Select options={CHANNELS} disabled={!!editing?.id} />
          </Form.Item>
          <Form.Item name="hotel_id" label="酒店 ID" rules={[{ required: true }]}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="secret" label="签名密钥（≥8 位）" rules={[{ required: true, min: 8 }]}>
            <Input.Password placeholder="HMAC-SHA256 共享密钥" />
          </Form.Item>
          <Form.Item name="push_enabled" label="启用推送" valuePropName="checked">
            <Checkbox />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

// ========== 房型映射 ==========

function MappingsTab() {
  const { tenantCode } = useTenant();
  const [list, setList] = useState<ChannelRoomMapping[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<Partial<ChannelRoomMapping> | null>(null);
  const [form] = Form.useForm();
  const [channel, setChannel] = useState<string | undefined>();

  const load = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [maps, rts] = await Promise.all([
        listChannelRoomMappings(tenantCode, channel ? { channel } : {}),
        listRoomTypes(tenantCode),
      ]);
      setList(maps);
      setRoomTypes(rts);
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, channel]);

  const onUpsert = async () => {
    const v = await form.validateFields();
    try {
      await upsertChannelRoomMapping(tenantCode!, {
        hotel_id: Number(v.hotel_id),
        channel: v.channel,
        pms_room_type_id: Number(v.pms_room_type_id),
        external_room_type_code: v.external_room_type_code,
        enabled: v.enabled ?? true,
      });
      message.success("已保存");
      setEditing(null);
      form.resetFields();
      load();
    } catch (e: any) {
      message.error(e?.message || "保存失败");
    }
  };

  const onDelete = async (id: string | number) => {
    try {
      await deleteChannelRoomMapping(tenantCode!, Number(id));
      message.success("已删除");
      load();
    } catch (e: any) {
      message.error(e?.message || "删除失败");
    }
  };

  return (
    <Card
      title="OTA 房型映射（PMS 房型 ↔ 渠道房型码）"
      extra={
        <Space>
          <Select
            placeholder="按渠道筛选"
            allowClear
            style={{ width: 180 }}
            options={CHANNELS}
            value={channel}
            onChange={(v) => setChannel(v)}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      }
    >
      <Table
        loading={loading}
        dataSource={list}
        rowKey="id"
        size="small"
        columns={[
          { title: "渠道", dataIndex: "channel", render: (v) => CHANNELS.find((c) => c.value === v)?.label ?? v },
          { title: "酒店 ID", dataIndex: "hotel_id" },
          {
            title: "PMS 房型",
            dataIndex: "pms_room_type_id",
            render: (v) => {
              const rt = roomTypes.find((r) => String(r.id) === String(v));
              return rt ? `${rt.name}（${rt.code}）` : `#${v}`;
            },
          },
          { title: "外部房型码", dataIndex: "external_room_type_code" },
          {
            title: "启用",
            dataIndex: "enabled",
            render: (v) => (v ? <Tag color="green">✓</Tag> : <Tag>—</Tag>),
          },
          {
            title: "操作",
            render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => {
                  setEditing(r);
                  form.setFieldsValue({
                    hotel_id: r.hotel_id,
                    channel: r.channel,
                    pms_room_type_id: Number(r.pms_room_type_id),
                    external_room_type_code: r.external_room_type_code,
                    enabled: !!r.enabled,
                  });
                }}>编辑</Button>
                <Popconfirm title="确认删除？" onConfirm={() => onDelete(r.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Button
        type="primary"
        icon={<PlusOutlined />}
        style={{ marginTop: 12 }}
        onClick={() => {
          setEditing({});
          form.resetFields();
          form.setFieldsValue({ enabled: true });
        }}
      >
        新增映射
      </Button>

      <Modal
        open={!!editing}
        title={editing?.id ? "编辑房型映射" : "新增房型映射"}
        onCancel={() => setEditing(null)}
        onOk={onUpsert}
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="channel" label="渠道" rules={[{ required: true }]}>
            <Select options={CHANNELS} disabled={!!editing?.id} />
          </Form.Item>
          <Form.Item name="hotel_id" label="酒店 ID" rules={[{ required: true }]}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="pms_room_type_id" label="PMS 房型" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={roomTypes.map((r) => ({
                value: Number(r.id),
                label: `${r.name}（${r.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item name="external_room_type_code" label="外部房型码" rules={[{ required: true }]}>
            <Input placeholder="如 STD-X / DELUXE-A" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Checkbox />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

// ========== 渠道价 ==========

function RatesTab() {
  const { tenantCode } = useTenant();
  const [list, setList] = useState<ChannelRatePlan[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<Partial<ChannelRatePlan> | null>(null);
  const [form] = Form.useForm();
  const [channel, setChannel] = useState<string | undefined>();

  const load = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [plans, rts] = await Promise.all([
        listChannelRatePlans(tenantCode, channel ? { channel } : {}),
        listRoomTypes(tenantCode),
      ]);
      setList(plans);
      setRoomTypes(rts);
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, channel]);

  const onUpsert = async () => {
    const v = await form.validateFields();
    try {
      await upsertChannelRatePlan(tenantCode!, {
        hotel_id: Number(v.hotel_id),
        channel: v.channel,
        pms_room_type_id: Number(v.pms_room_type_id),
        effective_date: v.effective_date ? v.effective_date.format("YYYY-MM-DD") : null,
        price_cents: yuanToCents(Number(v.price_yuan)),
        enabled: v.enabled ?? true,
      });
      message.success("已保存");
      setEditing(null);
      form.resetFields();
      load();
    } catch (e: any) {
      message.error(e?.message || "保存失败");
    }
  };

  const onDelete = async (id: string | number) => {
    try {
      await deleteChannelRatePlan(tenantCode!, Number(id));
      message.success("已删除");
      load();
    } catch (e: any) {
      message.error(e?.message || "删除失败");
    }
  };

  return (
    <Card
      title="OTA 渠道价（按房型覆盖 PMS base_price）"
      extra={
        <Space>
          <Select
            placeholder="按渠道筛选"
            allowClear
            style={{ width: 180 }}
            options={CHANNELS}
            value={channel}
            onChange={(v) => setChannel(v)}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      }
    >
      <Table
        loading={loading}
        dataSource={list}
        rowKey="id"
        size="small"
        columns={[
          { title: "渠道", dataIndex: "channel", render: (v) => CHANNELS.find((c) => c.value === v)?.label ?? v },
          { title: "酒店 ID", dataIndex: "hotel_id" },
          {
            title: "PMS 房型",
            dataIndex: "pms_room_type_id",
            render: (v) => {
              const rt = roomTypes.find((r) => String(r.id) === String(v));
              return rt ? `${rt.name}（${rt.code}）` : `#${v}`;
            },
          },
          {
            title: "生效日",
            dataIndex: "effective_date",
            render: (v) => (v ? v : <Text type="secondary">永久默认</Text>),
          },
          {
            title: "渠道价（元）",
            dataIndex: "price_cents",
            render: (v) => `¥${(v / 100).toFixed(2)}`,
          },
          {
            title: "启用",
            dataIndex: "enabled",
            render: (v) => (v ? <Tag color="green">✓</Tag> : <Tag>—</Tag>),
          },
          {
            title: "操作",
            render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => {
                  setEditing(r);
                  form.setFieldsValue({
                    hotel_id: r.hotel_id,
                    channel: r.channel,
                    pms_room_type_id: Number(r.pms_room_type_id),
                    effective_date: r.effective_date ? dayjs(r.effective_date) : null,
                    price_yuan: r.price_cents / 100,
                    enabled: !!r.enabled,
                  });
                }}>编辑</Button>
                <Popconfirm title="确认删除？" onConfirm={() => onDelete(r.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Button
        type="primary"
        icon={<PlusOutlined />}
        style={{ marginTop: 12 }}
        onClick={() => {
          setEditing({});
          form.resetFields();
          form.setFieldsValue({ enabled: true });
        }}
      >
        新增渠道价
      </Button>

      <Modal
        open={!!editing}
        title={editing?.id ? "编辑渠道价" : "新增渠道价"}
        onCancel={() => setEditing(null)}
        onOk={onUpsert}
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="channel" label="渠道" rules={[{ required: true }]}>
            <Select options={CHANNELS} disabled={!!editing?.id} />
          </Form.Item>
          <Form.Item name="hotel_id" label="酒店 ID" rules={[{ required: true }]}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="pms_room_type_id" label="PMS 房型" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={roomTypes.map((r) => ({
                value: Number(r.id),
                label: `${r.name}（${r.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item name="effective_date" label="生效日（留空 = 永久默认）">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="price_yuan" label="渠道价（元）" rules={[{ required: true, type: "number", min: 0.01 }]}>
            <InputNumber addonBefore="¥" min={0.01} step={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Checkbox />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

// ========== 推送日志 ==========

function LogsTab() {
  const { tenantCode } = useTenant();
  const [list, setList] = useState<ChannelPushLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<{ channel?: string; status?: string }>({});

  const load = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setList(await listChannelPushLogs(tenantCode, { ...filter, limit: 100 }));
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, filter.channel, filter.status]);

  return (
    <Card
      title="推送日志（最新 100 条）"
      extra={
        <Space>
          <Select
            placeholder="渠道"
            allowClear
            style={{ width: 160 }}
            options={CHANNELS}
            value={filter.channel}
            onChange={(v) => setFilter((f) => ({ ...f, channel: v }))}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 140 }}
            options={[
              { value: "SUCCESS", label: "成功" },
              { value: "DRY_RUN", label: "演练" },
              { value: "FAILED", label: "失败" },
            ]}
            value={filter.status}
            onChange={(v) => setFilter((f) => ({ ...f, status: v }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      }
    >
      <Table
        loading={loading}
        dataSource={list}
        rowKey="id"
        size="small"
        pagination={{ pageSize: 20 }}
        columns={[
          {
            title: "时间",
            dataIndex: "created_at",
            render: (v) => (v ? new Date(v).toLocaleString("zh-CN") : "—"),
          },
          { title: "渠道", dataIndex: "channel", render: (v) => CHANNELS.find((c) => c.value === v)?.label ?? v },
          {
            title: "状态",
            dataIndex: "status",
            render: (v) => (
              <Tag color={STATUS_TAG[v]?.color || "default"}>{STATUS_TAG[v]?.label || v}</Tag>
            ),
          },
          { title: "trace_id", dataIndex: "trace_id" },
          { title: "条数", dataIndex: "item_count" },
          { title: "耗时(ms)", dataIndex: "duration_ms" },
          { title: "操作员", dataIndex: "operator" },
          {
            title: "错误",
            dataIndex: "error_message",
            render: (v) => (v ? <Text type="danger">{v}</Text> : "—"),
          },
        ]}
      />
    </Card>
  );
}

// ========== 推送 ==========

function PushTab() {
  const { tenantCode } = useTenant();
  const [channel, setChannel] = useState("sandbox");
  const [days, setDays] = useState<number>(7);
  const [dryRun, setDryRun] = useState(true);
  const [last, setLast] = useState<any>(null);

  const pushInventory = async () => {
    try {
      const r = await pushChannelInventory(tenantCode!, channel, { days, dry_run: dryRun });
      setLast(r);
      message.success(`已${dryRun ? "演练" : "推送"}房量（${r.items?.length ?? 0} 项）`);
    } catch (e: any) {
      message.error(e?.message || "推送失败");
    }
  };

  const pushRates = async () => {
    try {
      const r = await pushChannelRates(tenantCode!, channel, { dry_run: dryRun });
      setLast(r);
      message.success(`已${dryRun ? "演练" : "推送"}渠道价（${r.items?.length ?? 0} 项）`);
    } catch (e: any) {
      message.error(e?.message || "推送失败");
    }
  };

  return (
    <Row gutter={16}>
      <Col span={10}>
        <Card title="推送参数">
          <Form layout="vertical">
            <Form.Item label="渠道">
              <Select value={channel} onChange={setChannel} options={CHANNELS} />
            </Form.Item>
            <Form.Item label="房量推送范围（天）">
              <InputNumber min={1} max={90} value={days} onChange={(v) => setDays(v ?? 7)} />
            </Form.Item>
            <Form.Item>
              <Checkbox checked={dryRun} onChange={(e) => setDryRun(e.target.checked)}>
                演练模式（不实际推送，仅落 DRY_RUN 日志）
              </Checkbox>
            </Form.Item>
            <Space>
              <Button type="primary" icon={<CloudUploadOutlined />} onClick={pushInventory}>
                推送可用房
              </Button>
              <Button onClick={pushRates}>推送渠道价</Button>
            </Space>
          </Form>
        </Card>
      </Col>
      <Col span={14}>
        <Card title="最近结果">
          {last ? (
            <pre style={{ maxHeight: 360, overflow: "auto", background: "#fafafa", padding: 12 }}>
              {JSON.stringify(last, null, 2)}
            </pre>
          ) : (
            <Empty description="暂无结果" />
          )}
        </Card>
      </Col>
    </Row>
  );
}
