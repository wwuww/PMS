import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined, EditOutlined, SearchOutlined, PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import {
  listRateCodes,
  createRateCode,
  upsertPriceCalendar,
  roomTypeAvailability,
  listRoomTypes,
} from "../api/endpoints";
import type {
  RateCode,
  RateCodeCreate,
  PriceCalendar,
  Availability,
  RoomType,
} from "../api/types";
import { fmtCents } from "../utils/format";

const { Title, Text } = Typography;

export default function Rates() {
  const { tenantCode, hotelId } = useTenant();
  const [rateCodes, setRateCodes] = useState<RateCode[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);

  // 价格日历编辑
  const [showPrice, setShowPrice] = useState(false);
  const [priceForm] = Form.useForm();
  const [priceLoading, setPriceLoading] = useState(false);

  // 新建费率码（批次② 核心实体字段补全）
  const [showCreateRC, setShowCreateRC] = useState(false);
  const [createRCForm] = Form.useForm();
  const [createRCLoading, setCreateRCLoading] = useState(false);

  // 房量查询
  const [avail, setAvail] = useState<Availability | null>(null);
  const [availLoading, setAvailLoading] = useState(false);

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [rc, rt] = await Promise.all([
        listRateCodes(tenantCode),
        listRoomTypes(tenantCode),
      ]);
      setRateCodes(rc);
      setRoomTypes(rt);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const roomTypeName = useMemo(() => {
    const m = new Map<string, string>();
    roomTypes.forEach((r) => m.set(r.id, `${r.name}（${r.code}）`));
    return m;
  }, [roomTypes]);

  const handlePrice = async () => {
    const v = await priceForm.validateFields();
    setPriceLoading(true);
    try {
      const row: PriceCalendar = await upsertPriceCalendar(tenantCode, {
        room_type_id: v.room_type_id,
        date: dayjs(v.date).format("YYYY-MM-DD"),
        price: Math.round(v.price_yuan * 100),
      });
      message.success(`已设价 ${fmtCents(row.price)}`);
      setShowPrice(false);
      priceForm.resetFields();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "设价失败");
    } finally {
      setPriceLoading(false);
    }
  };

  const handleAvail = async (roomTypeId: string, date: string) => {
    setAvailLoading(true);
    try {
      const a = await roomTypeAvailability(tenantCode, roomTypeId, date);
      setAvail(a);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "查询失败");
    } finally {
      setAvailLoading(false);
    }
  };

  const handleCreateRC = async () => {
    if (!tenantCode) return;
    const v = await createRCForm.validateFields();
    setCreateRCLoading(true);
    try {
      const body: RateCodeCreate = {
        code: v.code,
        name: v.name,
        channel: v.channel || null,
        member_level: v.member_level || null,
        agreement_type: v.agreement_type || null,
        room_type_id: v.room_type_id || null,
        stay_type: v.stay_type || null,
        discount_pct: v.discount_pct != null ? Number(v.discount_pct) : 10000,
        // 批次② 核心实体字段补全
        stay_class: v.stay_class || null,
        rate_type: v.rate_type || null,
        valid_from: v.valid_from ? dayjs(v.valid_from).format("YYYY-MM-DD") : null,
        valid_to: v.valid_to ? dayjs(v.valid_to).format("YYYY-MM-DD") : null,
        is_overlay: v.is_overlay ?? false,
        week: v.week || null,
      };
      await createRateCode(tenantCode, body);
      message.success("费率码已创建");
      setShowCreateRC(false);
      createRCForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    } finally {
      setCreateRCLoading(false);
    }
  };

  const rcColumns = [
    { title: "代码", dataIndex: "code", width: 90 },
    { title: "名称", dataIndex: "name" },
    { title: "渠道", dataIndex: "channel", render: (v: string) => <Tag>{v}</Tag> },
    { title: "会员等级", dataIndex: "member_level", render: (v: string) => v || "—" },
    { title: "协议类型", dataIndex: "agreement_type", render: (v: string) => v || "—" },
    {
      title: "折扣",
      dataIndex: "discount_pct",
      render: (v: number) => (
        <Text type={v < 10000 ? "success" : undefined}>
          {v === 10000 ? "原价" : `${(v / 100).toFixed(0)} 折`}
        </Text>
      ),
    },
    { title: "住期类型", dataIndex: "stay_type", render: (v: string) => v || "—" },
    // 批次② 核心实体字段补全：回显
    {
      title: "住宿类型",
      dataIndex: "stay_class",
      render: (v: string | null) =>
        v === "DR" ? "日租" : v === "HR" ? "时租" : v || "—",
    },
    {
      title: "价格类型",
      dataIndex: "rate_type",
      render: (v: string | null) =>
        v === "FIXED"
          ? "固定价"
          : v === "DELTA"
          ? "加减价"
          : v === "MULTIPLIER"
          ? "倍数"
          : v || "—",
    },
    { title: "有效期起", dataIndex: "valid_from", render: (v: string | null) => v || "—" },
    { title: "有效期至", dataIndex: "valid_to", render: (v: string | null) => v || "—" },
    {
      title: "可叠加",
      dataIndex: "is_overlay",
      align: "center" as const,
      render: (v: boolean | undefined) => (v ? <Tag color="green">是</Tag> : <Tag>否</Tag>),
    },
    { title: "适用星期", dataIndex: "week", render: (v: string | null) => v || "—" },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          价格库存中心
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<EditOutlined />}
            onClick={() => setShowPrice(true)}
            disabled={!roomTypes.length}
          >
            设定价格
          </Button>
          <Button
            icon={<PlusOutlined />}
            onClick={() => {
              createRCForm.resetFields();
              setShowCreateRC(true);
            }}
          >
            新建费率码
          </Button>
        </Space>
      </div>

      <Row gutter={16}>
        <Col span={16}>
          <Card title="费率码（Rate Codes）" size="small">
            <Table
              rowKey="id"
              size="small"
              loading={loading}
              dataSource={rateCodes}
              columns={rcColumns}
              pagination={{ pageSize: 8 }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="房量 / 解析价查询" size="small">
            <Space direction="vertical" style={{ width: "100%" }}>
              <Select
                placeholder="选择房型"
                style={{ width: "100%" }}
                options={roomTypes.map((r) => ({
                  value: r.id,
                  label: `${r.name}（${r.code}）`,
                }))}
                onChange={(id) => handleAvail(id, dayjs().format("YYYY-MM-DD"))}
              />
              {avail && (
                <div style={{ background: "#fafafa", padding: 12, borderRadius: 8 }}>
                  <p>
                    日期：<Text strong>{avail.date}</Text>
                  </p>
                  <p>
                    总房量：{avail.total} ｜ 已订：{avail.booked} ｜ 可售：
                    <Text strong type="success">
                      {avail.available}
                    </Text>
                  </p>
                  <p>
                    解析价：<Text strong>{fmtCents(avail.price)}</Text>
                  </p>
                </div>
              )}
              {availLoading && <Text type="secondary">查询中…</Text>}
            </Space>
          </Card>
        </Col>
      </Row>

      <Modal
        title="设定当日价格（UPSERT）"
        open={showPrice}
        onOk={handlePrice}
        confirmLoading={priceLoading}
        onCancel={() => setShowPrice(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={priceForm} layout="vertical" initialValues={{ price_yuan: 300 }}>
          <Form.Item name="room_type_id" label="房型" rules={[{ required: true }]}>
            <Select
              placeholder="选择房型"
              options={roomTypes.map((r) => ({
                value: r.id,
                label: `${r.name}（${r.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item name="date" label="日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} defaultPickerValue={dayjs()} />
          </Form.Item>
          <Form.Item
            name="price_yuan"
            label="价格（元）"
            rules={[{ required: true, message: "请输入价格" }]}
          >
            <InputNumber style={{ width: "100%" }} min={0} step={10} addonAfter="元" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建费率码"
        open={showCreateRC}
        onOk={handleCreateRC}
        confirmLoading={createRCLoading}
        onCancel={() => setShowCreateRC(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createRCForm} layout="vertical">
          <Form.Item name="code" label="费率码" rules={[{ required: true, message: "请输入费率码" }]}>
            <Input placeholder="如：BAR" maxLength={32} />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="如：门市价" maxLength={64} />
          </Form.Item>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="channel" label="渠道" style={{ flex: 1 }}>
              <Input placeholder="如：OTA" maxLength={32} />
            </Form.Item>
            <Form.Item name="member_level" label="会员等级" style={{ flex: 1 }}>
              <Input placeholder="如：NORMAL" maxLength={32} />
            </Form.Item>
          </Space>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="agreement_type" label="协议类型" style={{ flex: 1 }}>
              <Input placeholder="如：CORP" maxLength={32} />
            </Form.Item>
            <Form.Item name="room_type_id" label="房型" style={{ flex: 1 }}>
              <Select
                allowClear
                placeholder="选择房型（可空）"
                options={roomTypes.map((r) => ({
                  value: r.id,
                  label: `${r.name}（${r.code}）`,
                }))}
              />
            </Form.Item>
          </Space>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="stay_type" label="住期类型" style={{ flex: 1 }}>
              <Input placeholder="如：daily" maxLength={16} />
            </Form.Item>
            <Form.Item name="discount_pct" label="折扣（基点，10000=原价）" style={{ flex: 1 }}>
              <InputNumber style={{ width: "100%" }} min={0} max={10000} step={100} />
            </Form.Item>
          </Space>
          {/* 批次② 核心实体字段补全 */}
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="stay_class" label="住宿类型" style={{ flex: 1 }}>
              <Select
                allowClear
                placeholder="选择"
                options={[
                  { label: "日租 (DR)", value: "DR" },
                  { label: "时租 (HR)", value: "HR" },
                ]}
              />
            </Form.Item>
            <Form.Item name="rate_type" label="价格类型" style={{ flex: 1 }}>
              <Select
                allowClear
                placeholder="选择"
                options={[
                  { label: "固定价 (FIXED)", value: "FIXED" },
                  { label: "加减价 (DELTA)", value: "DELTA" },
                  { label: "倍数 (MULTIPLIER)", value: "MULTIPLIER" },
                ]}
              />
            </Form.Item>
          </Space>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="valid_from" label="有效期起" style={{ flex: 1 }}>
              <DatePicker style={{ width: "100%" }} placeholder="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="valid_to" label="有效期至" style={{ flex: 1 }}>
              <DatePicker style={{ width: "100%" }} placeholder="YYYY-MM-DD" />
            </Form.Item>
          </Space>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="is_overlay" label="可叠加" valuePropName="checked" style={{ flex: 1 }}>
              <Switch />
            </Form.Item>
            <Form.Item name="week" label="适用星期" style={{ flex: 1 }}>
              <Input placeholder="如：1,2,3,4,5" maxLength={32} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
