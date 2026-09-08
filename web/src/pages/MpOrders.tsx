import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined, ShoppingCartOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import { mpOffers, mpPlaceOrder, mpOrderDetail, listRoomTypes } from "../api/endpoints";
import type { MpOffer, MpOrder, RoomType } from "../api/types";
import { fmtCents } from "../utils/format";

const { Title, Text } = Typography;

export default function MpOrders() {
  const { tenantCode, hotelId } = useTenant();
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [offers, setOffers] = useState<MpOffer[]>([]);
  const [loading, setLoading] = useState(false);
  const [queryForm] = Form.useForm();

  const [showOrder, setShowOrder] = useState(false);
  const [orderLoading, setOrderLoading] = useState(false);
  const [order, setOrder] = useState<MpOrder | null>(null);
  const [tradeNo, setTradeNo] = useState("");
  const [tradeLoading, setTradeLoading] = useState(false);

  const refreshRoomTypes = async () => {
    if (!tenantCode) return;
    setRoomTypes(await listRoomTypes(tenantCode));
  };

  useEffect(() => {
    refreshRoomTypes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const handleQuery = async () => {
    const v = await queryForm.validateFields();
    const cid = hotelId ?? v.hotel_id;
    if (!cid) {
      message.warning("请先选择门店");
      return;
    }
    setLoading(true);
    try {
      const list = await mpOffers(
        tenantCode,
        cid,
        dayjs(v.check_in).format("YYYY-MM-DD"),
        dayjs(v.check_out).format("YYYY-MM-DD")
      );
      setOffers(list);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "查询报价失败");
    } finally {
      setLoading(false);
    }
  };

  const handlePlace = async (offer: MpOffer) => {
    const v = await queryForm.validateFields();
    const cid = hotelId ?? v.hotel_id;
    setOrderLoading(true);
    try {
      const o: MpOrder = await mpPlaceOrder(tenantCode, {
        hotel_id: cid,
        room_type_id: offer.room_type_id,
        guest_name: v.guest_name || "小程序客人",
        check_in_date: dayjs(v.check_in).format("YYYY-MM-DD"),
        check_out_date: dayjs(v.check_out).format("YYYY-MM-DD"),
        guest_phone: v.guest_phone || null,
      });
      setOrder(o);
      setShowOrder(true);
      setTradeNo(o.pay_order.out_trade_no);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "下单失败");
    } finally {
      setOrderLoading(false);
    }
  };

  const handleTradeQuery = async () => {
    if (!tradeNo) {
      message.warning("请输入订单号");
      return;
    }
    setTradeLoading(true);
    try {
      const o = await mpOrderDetail(tenantCode, tradeNo);
      setOrder(o);
      setShowOrder(true);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "查单失败");
    } finally {
      setTradeLoading(false);
    }
  };

  const columns = [
    { title: "房型", dataIndex: "name" },
    { title: "代码", dataIndex: "code", width: 80 },
    {
      title: "晚数",
      dataIndex: "nights",
      width: 70,
      render: (v: number) => `${v} 晚`,
    },
    {
      title: "总价",
      dataIndex: "total_price",
      render: (v: number) => <Text strong>{fmtCents(v)}</Text>,
    },
    {
      title: "可售",
      dataIndex: "available",
      width: 70,
      render: (v: number) => (
        <Tag color={v > 0 ? "green" : "red"}>{v}</Tag>
      ),
    },
    {
      title: "可订",
      dataIndex: "bookable",
      width: 70,
      render: (v: boolean) => (
        <Tag color={v ? "blue" : "default"}>{v ? "可订" : "不可订"}</Tag>
      ),
    },
    {
      title: "操作",
      width: 90,
      render: (_: unknown, r: MpOffer) => (
        <Button
          type="link"
          icon={<ShoppingCartOutlined />}
          disabled={!r.bookable}
          loading={orderLoading}
          onClick={() => handlePlace(r)}
        >
          下单
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          移动端直订（小程序）
        </Title>
        <Space>
          <Input.Search
            placeholder="凭订单号查单"
            style={{ width: 240 }}
            value={tradeNo}
            onChange={(e) => setTradeNo(e.target.value)}
            onSearch={handleTradeQuery}
            loading={tradeLoading}
            enterButton="查单"
          />
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Form
          form={queryForm}
          layout="inline"
          initialValues={{
            check_in: dayjs(),
            check_out: dayjs().add(1, "day"),
            guest_name: "小程序客人",
          }}
        >
          <Form.Item name="hotel_id" label="门店 ID" hidden>
            <InputNumber />
          </Form.Item>
          <Form.Item name="check_in" label="入住" rules={[{ required: true }]}>
            <DatePicker />
          </Form.Item>
          <Form.Item name="check_out" label="离店" rules={[{ required: true }]}>
            <DatePicker />
          </Form.Item>
          <Form.Item name="guest_name" label="客人姓名">
            <Input placeholder="小程序客人" />
          </Form.Item>
          <Form.Item name="guest_phone" label="手机号">
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={handleQuery}
              loading={loading}
            >
              查询报价
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="房型报价（逐晚价格 + 可售量）" size="small">
        <Table
          rowKey="room_type_id"
          size="small"
          loading={loading}
          dataSource={offers}
          columns={columns}
          pagination={false}
        />
      </Card>

      <Drawer
        title="小程序订单详情"
        width={460}
        open={showOrder}
        onClose={() => setShowOrder(false)}
      >
        {order && (
          <Space direction="vertical" style={{ width: "100%" }} size="large">
            <Descriptions title="预订信息" column={1} size="small" bordered>
              <Descriptions.Item label="客人">
                {order.booking.guest_name}
              </Descriptions.Item>
              <Descriptions.Item label="房型 ID">
                {order.booking.room_type_id}
              </Descriptions.Item>
              <Descriptions.Item label="入住">
                {order.booking.check_in_date}
              </Descriptions.Item>
              <Descriptions.Item label="离店">
                {order.booking.check_out_date}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color="blue">{order.booking.status}</Tag>
              </Descriptions.Item>
            </Descriptions>
            <Descriptions title="支付单" column={1} size="small" bordered>
              <Descriptions.Item label="订单号">
                <Text copyable>{order.pay_order.out_trade_no}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="金额">
                <Text strong>{fmtCents(order.pay_order.amount_cents)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={order.pay_order.status === "PAID" ? "green" : "gold"}>
                  {order.pay_order.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="渠道">
                {order.pay_order.channel}
              </Descriptions.Item>
            </Descriptions>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
