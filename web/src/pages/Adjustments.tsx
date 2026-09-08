import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import { listAdjustments, applyAdjustment } from "../api/endpoints";
import type { Adjustment } from "../api/types";
import { fmtCents } from "../utils/format";

const { Title, Text } = Typography;

export default function Adjustments() {
  const { tenantCode } = useTenant();
  const [list, setList] = useState<Adjustment[]>([]);
  const [loading, setLoading] = useState(false);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setList(await listAdjustments(tenantCode));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "调账记录加载失败");
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
      await applyAdjustment(tenantCode, v.bill_id, {
        type: v.type,
        amount_cents: Math.round(v.amount_yuan * 100),
        reason: v.reason || "",
        operator: v.operator || "frontdesk",
      });
      message.success("调账已提交");
      setShow(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "提交失败");
    } finally {
      setSaving(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        title: "类型",
        dataIndex: "type",
        width: 90,
        render: (t: string) => (
          <Tag color={t === "VOID" ? "red" : "orange"}>
            {t === "VOID" ? "红冲" : "调账"}
          </Tag>
        ),
      },
      {
        title: "金额",
        dataIndex: "amount_cents",
        align: "right" as const,
        render: (v: number) => (
          <Text type={v < 0 ? "success" : v > 0 ? "danger" : undefined}>
            {fmtCents(v)}
          </Text>
        ),
      },
      { title: "原因", dataIndex: "reason", render: (v: string) => v || "—" },
      { title: "操作员", dataIndex: "operator", width: 110 },
      {
        title: "账单ID",
        dataIndex: "bill_id",
        width: 90,
        render: (v: number | null) => v ?? "—",
      },
    ],
    []
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          调账中心
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setShow(true)}>
            发起调账
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
        title="发起调账 / 红冲"
        open={show}
        onOk={handleCreate}
        confirmLoading={saving}
        onCancel={() => {
          setShow(false);
          form.resetFields();
        }}
        okText="提交"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ type: "ADJUST", amount_yuan: 0, operator: "frontdesk" }}
        >
          <Form.Item
            name="bill_id"
            label="账单 ID"
            rules={[{ required: true, message: "请输入账单 ID" }]}
          >
            <InputNumber style={{ width: "100%" }} min={1} />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Radio.Group
              options={[
                { label: "调账（ADJUST）", value: "ADJUST" },
                { label: "红冲（VOID）", value: "VOID" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="amount_yuan"
            label="金额（元，正为加收 / 负为冲减）"
            rules={[{ required: true, message: "请输入金额" }]}
          >
            <InputNumber style={{ width: "100%" }} step={10} addonAfter="元" />
          </Form.Item>
          <Form.Item name="reason" label="原因">
            <Input.TextArea rows={3} placeholder="如：系统误差补偿" />
          </Form.Item>
          <Form.Item name="operator" label="操作员">
            <Input maxLength={32} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
