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
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined, EditOutlined, SearchOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import {
  listRateCodes,
  upsertPriceCalendar,
  roomTypeAvailability,
  listRoomTypes,
} from "../api/endpoints";
import type { RateCode, PriceCalendar, Availability, RoomType } from "../api/types";
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
    </div>
  );
}
