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
        <Form form={form} layout="vertical" initialValues={{ base_price_yuan: 300 }}>
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
        </Form>
      </Modal>
    </div>
  );
}
