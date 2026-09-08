import { useEffect, useState } from "react";
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Switch,
  App,
  Tag,
  Space,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { listTenants, createTenant } from "../api/endpoints";
import type { Tenant } from "../api/types";
import { useTenant } from "../store/tenant";

export default function TenantsPage() {
  const { message } = App.useApp();
  const { refresh } = useTenant();
  const [rows, setRows] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  async function load() {
    setLoading(true);
    try {
      setRows(await listTenants());
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function submit() {
    const v = await form.validateFields();
    try {
      await createTenant(v);
      message.success("门店/租户创建成功");
      setOpen(false);
      form.resetFields();
      await load();
      await refresh();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  const columns = [
    { title: "ID", dataIndex: "id", key: "id", width: 70 },
    { title: "编码", dataIndex: "code", key: "code" },
    { title: "名称", dataIndex: "name", key: "name" },
    {
      title: "类型",
      dataIndex: "is_chain",
      key: "is_chain",
      render: (v: boolean) => (v ? <Tag color="blue">连锁</Tag> : <Tag>单体</Tag>),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (v: string) => <Tag color="green">{v}</Tag>,
    },
  ];

  return (
    <Card
      title="门店 / 租户管理"
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setOpen(true)}
        >
          新建门店
        </Button>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title="新建门店 / 租户"
        open={open}
        onOk={submit}
        onCancel={() => setOpen(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ is_chain: false }}>
          <Form.Item
            name="code"
            label="编码"
            rules={[{ required: true, message: "请输入编码" }]}
          >
            <Input placeholder="如 DEMO2026" />
          </Form.Item>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="如 深圳湾示范店" />
          </Form.Item>
          <Form.Item name="is_chain" label="是否连锁" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
