import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  listGroupPricePolicies,
  createGroupPricePolicy,
  listHotels,
  listRoomTypes,
} from "../api/endpoints";
import type {
  GroupPricePolicyOut,
  GroupPricePolicyIn,
  Hotel,
  RoomType,
} from "../api/types";
import { fmtCents } from "../utils/format";

const { Title } = Typography;

export default function PricePolicy() {
  const { tenantCode } = useTenant();
  const [list, setList] = useState<GroupPricePolicyOut[]>([]);
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [p, h, rt] = await Promise.all([
        listGroupPricePolicies(tenantCode),
        listHotels(tenantCode),
        listRoomTypes(tenantCode),
      ]);
      setList(p);
      setHotels(h);
      setRoomTypes(rt);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "价策加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const handleCreate = async () => {
    if (!tenantCode) return;
    const v = await form.validateFields();
    setSaving(true);
    try {
      const body: GroupPricePolicyIn = {
        price_floor_cents: Math.round((v.price_floor_yuan ?? 0) * 100),
        price_ceiling_cents:
          v.price_ceiling_yuan != null ? Math.round(v.price_ceiling_yuan * 100) : null,
        hotel_id: v.hotel_id || null,
        room_type_id: v.room_type_id || null,
        note: v.note || "",
      };
      await createGroupPricePolicy(tenantCode, body);
      message.success("价策已下发");
      setShow(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "下发失败");
    } finally {
      setSaving(false);
    }
  };

  const scopeOf = (r: GroupPricePolicyOut) => {
    if (r.hotel_id) return <Tag color="blue">门店 {r.hotel_id}</Tag>;
    if (r.room_type_id) return <Tag color="cyan">房型 {r.room_type_id}</Tag>;
    return <Tag color="gold">集团全局</Tag>;
  };

  const columns = useMemo(
    () => [
      { title: "ID", dataIndex: "id", width: 70 },
      {
        title: "适用范围",
        key: "scope",
        render: (_: unknown, r: GroupPricePolicyOut) => scopeOf(r),
      },
      {
        title: "限价下限",
        dataIndex: "price_floor_cents",
        align: "right" as const,
        render: (v: number) => fmtCents(v),
      },
      {
        title: "限价上限",
        dataIndex: "price_ceiling_cents",
        align: "right" as const,
        render: (v: number | null) => (v == null ? "—" : fmtCents(v)),
      },
      {
        title: "状态",
        dataIndex: "status",
        render: (s: string) => (
          <Tag color={s === "active" ? "green" : "default"}>{s}</Tag>
        ),
      },
      { title: "下发人", dataIndex: "issued_by", width: 110 },
      { title: "备注", dataIndex: "note", render: (v: string) => v || "—" },
      {
        title: "创建时间",
        dataIndex: "created_at",
        render: (v: string | null) => v || "—",
      },
    ],
    []
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          集团价策下发
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setShow(true)}>
            下发票策
          </Button>
        </Space>
      </div>
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={list}
          columns={columns}
          pagination={{ pageSize: 12 }}
        />
      </Card>
      <Modal
        title="下发集团限价策略"
        open={show}
        onOk={handleCreate}
        confirmLoading={saving}
        onCancel={() => {
          setShow(false);
          form.resetFields();
        }}
        okText="下发"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ price_floor_yuan: 200 }}>
          <Form.Item
            name="price_floor_yuan"
            label="限价下限（元）"
            rules={[{ required: true, message: "请输入下限" }]}
          >
            <InputNumber style={{ width: "100%" }} min={0} step={10} addonAfter="元" />
          </Form.Item>
          <Form.Item name="price_ceiling_yuan" label="限价上限（元，选填）">
            <InputNumber style={{ width: "100%" }} min={0} step={10} addonAfter="元" />
          </Form.Item>
          <Form.Item name="hotel_id" label="限定门店（选填）">
            <Select
              allowClear
              placeholder="不填 = 集团全局"
              options={hotels.map((h) => ({
                value: h.id,
                label: `${h.name}（${h.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item name="room_type_id" label="限定房型（选填）">
            <Select
              allowClear
              placeholder="不填 = 全部房型"
              options={roomTypes.map((r) => ({
                value: r.id,
                label: `${r.name}（${r.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
