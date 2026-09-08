import { useEffect, useState } from "react";
import {
  Button,
  Card,
  DatePicker,
  Descriptions,
  Form,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { CloudUploadOutlined, ReloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import { pushChannelAvailability, listRoomTypes } from "../api/endpoints";
import type { ChannelResult, RoomType } from "../api/types";

const { Title, Text, Paragraph } = Typography;

const CHANNELS = [
  { value: "ctrip", label: "携程 Ctrip" },
  { value: "meituan", label: "美团 Meituan" },
  { value: "fliggy", label: "飞猪 Fliggy" },
  { value: "booking", label: "Booking.com" },
  { value: "agoda", label: "Agoda" },
];

export default function Channel() {
  const { tenantCode } = useTenant();
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [result, setResult] = useState<ChannelResult | null>(null);
  const [pushing, setPushing] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    if (!tenantCode) return;
    try {
      setRoomTypes(await listRoomTypes(tenantCode));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const handlePush = async () => {
    if (!tenantCode) return;
    const v = await form.validateFields();
    setPushing(true);
    try {
      const r = await pushChannelAvailability(tenantCode, v.channel, {
        room_type_id: v.room_type_id,
        date: dayjs(v.date).format("YYYY-MM-DD"),
      });
      setResult(r);
      message.success(`已推送至 ${r.channel}`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "推送失败");
    } finally {
      setPushing(false);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          OTA 渠道推送
        </Title>
        <Button icon={<ReloadOutlined />} onClick={load}>
          刷新房型
        </Button>
      </div>
      <Card style={{ marginBottom: 16 }} title="房量 / 价格推送">
        <Form form={form} layout="inline" initialValues={{ date: dayjs() }}>
          <Form.Item name="channel" label="渠道" rules={[{ required: true }]}>
            <Select
              style={{ width: 180 }}
              options={CHANNELS}
              placeholder="选择渠道"
            />
          </Form.Item>
          <Form.Item name="room_type_id" label="房型" rules={[{ required: true }]}>
            <Select
              style={{ width: 200 }}
              options={roomTypes.map((r) => ({
                value: r.id,
                label: `${r.name}（${r.code}）`,
              }))}
              placeholder="选择房型"
            />
          </Form.Item>
          <Form.Item name="date" label="日期" rules={[{ required: true }]}>
            <DatePicker />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={pushing}
              onClick={handlePush}
            >
              推送可用房
            </Button>
          </Form.Item>
        </Form>
      </Card>
      {result && (
        <Card title={`推送结果 · ${result.channel}`}>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="渠道">{result.channel}</Descriptions.Item>
            <Descriptions.Item label="集成状态">
              {result.integrated ? (
                <Tag color="green">已对接</Tag>
              ) : (
                <Tag color="orange">模拟</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="消息">{result.message}</Descriptions.Item>
            <Descriptions.Item label="回传载荷">
              <Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {JSON.stringify(result.payload, null, 2)}
              </Paragraph>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}
      {!result && (
        <Text type="secondary">选择渠道、房型与日期后点击「推送可用房」查看回传结果。</Text>
      )}
    </div>
  );
}
