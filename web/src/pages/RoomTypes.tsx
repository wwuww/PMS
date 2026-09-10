import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  Switch,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import { listRoomTypes, createRoomType } from "../api/endpoints";
import type { RoomType, RoomTypeCreate } from "../api/types";
import { fmtCents } from "../utils/format";

const { Title } = Typography;

export default function RoomTypes() {
  const { tenantCode, tenants } = useTenant();
  const [list, setList] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setList(await listRoomTypes(tenantCode));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "房型加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const handleCreate = async () => {
    const tenantId = tenants.find((t) => t.code === tenantCode)?.id;
    if (tenantId == null) {
      message.warning("找不到当前租户 ID");
      return;
    }
    const v = await form.validateFields();
    setSaving(true);
    try {
      const body: RoomTypeCreate = {
        code: v.code,
        name: v.name,
        base_price: Math.round((v.base_price_yuan ?? 0) * 100),
        // 批次② 核心实体字段补全
        bed_number: v.bed_number != null ? Number(v.bed_number) : undefined,
        short_name: v.short_name || null,
        en_name: v.en_name || null,
        descript: v.descript || null,
        is_valid: v.is_valid ?? true,
      };
      await createRoomType(tenantId, body);
      message.success("房型已创建");
      setShow(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    } finally {
      setSaving(false);
    }
  };

  const columns = useMemo(
    () => [
      { title: "代码", dataIndex: "code", width: 120 },
      { title: "名称", dataIndex: "name" },
      {
        title: "基准价",
        dataIndex: "base_price",
        align: "right" as const,
        render: (v: number) => fmtCents(v),
      },
      {
        title: "租户",
        dataIndex: "tenant_id",
        render: (v: string) => <Tag>{v}</Tag>,
      },
      {
        title: "床数",
        dataIndex: "bed_number",
        align: "center" as const,
        render: (v: number | undefined) => (v != null ? v : "—"),
      },
      { title: "简称", dataIndex: "short_name", render: (v: string | null) => v || "—" },
      { title: "英文名", dataIndex: "en_name", render: (v: string | null) => v || "—" },
      { title: "描述", dataIndex: "descript", render: (v: string | null) => v || "—" },
      {
        title: "启用",
        dataIndex: "is_valid",
        align: "center" as const,
        render: (v: boolean | undefined) =>
          v === false ? <Tag color="default">停用</Tag> : <Tag color="green">启用</Tag>,
      },
    ],
    []
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          房型管理
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setShow(true)}>
            新建房型
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
        title="新建房型"
        open={show}
        onOk={handleCreate}
        confirmLoading={saving}
        onCancel={() => {
          setShow(false);
          form.resetFields();
        }}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ base_price_yuan: 300, bed_number: 1, is_valid: true }}>
          <Form.Item
            name="code"
            label="房型代码"
            rules={[{ required: true, message: "请输入代码" }]}
          >
            <Input placeholder="如：DLX" maxLength={32} />
          </Form.Item>
          <Form.Item
            name="name"
            label="房型名称"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="如：豪华大床房" maxLength={64} />
          </Form.Item>
          <Form.Item
            name="base_price_yuan"
            label="基准价（元）"
            rules={[{ required: true, message: "请输入价格" }]}
          >
            <InputNumber style={{ width: "100%" }} min={0} step={10} addonAfter="元" />
          </Form.Item>
          <Form.Item name="bed_number" label="床数">
            <InputNumber style={{ width: "100%" }} min={1} step={1} precision={0} />
          </Form.Item>
          <Form.Item name="short_name" label="简称">
            <Input placeholder="如：豪华大床" maxLength={32} />
          </Form.Item>
          <Form.Item name="en_name" label="英文名">
            <Input placeholder="如：Deluxe King" maxLength={64} />
          </Form.Item>
          <Form.Item name="descript" label="描述">
            <Input.TextArea rows={2} maxLength={255} placeholder="房型描述" />
          </Form.Item>
          <Form.Item name="is_valid" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
