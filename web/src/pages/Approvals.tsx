import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined, PlusOutlined, CheckOutlined, CloseOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useTenant } from "../store/tenant";
import { listApprovals, submitApproval, decideApproval } from "../api/endpoints";
import type { ApprovalTicket, ApprovalType, ApprovalDecision } from "../api/types";

const { Title, Text } = Typography;

const TYPE_LABELS: Record<ApprovalType, string> = {
  DISCOUNT: "折扣",
  ADJUST: "冲账",
  OVERBOOK: "超额预订",
  REFUND: "退款",
};

function statusTag(s: string) {
  const m: Record<string, { color: string; label: string }> = {
    PENDING: { color: "gold", label: "待审批" },
    APPROVED: { color: "green", label: "已通过" },
    REJECTED: { color: "red", label: "已驳回" },
  };
  const x = m[s] || { color: "default", label: s };
  return <Tag color={x.color}>{x.label}</Tag>;
}

export default function ApprovalsPage() {
  const { tenantCode, hotelId } = useTenant();
  const [list, setList] = useState<ApprovalTicket[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>("ALL");
  const [showCreate, setShowCreate] = useState(false);
  const [form] = Form.useForm();

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setList(await listApprovals(tenantCode, filter === "ALL" ? undefined : filter));
    } catch (e: any) {
      message.error(e?.message || "审批列表加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, filter]);

  const handleCreate = async () => {
    if (!hotelId) {
      message.warning("请先选择门店");
      return;
    }
    const v = await form.validateFields();
    const payload: Record<string, unknown> = {};
    if (v.bill_id) payload.bill_id = v.bill_id;
    // 折扣审批通过后自动落账：后端读 payload.amount（分，负向冲减）
    if (v.amount) payload.amount = -Math.round(v.amount * 100);
    try {
      await submitApproval(tenantCode, {
        hotel_id: hotelId,
        type: v.type,
        reason: v.reason || "",
        applicant: v.applicant || "front_desk",
        payload,
      });
      message.success("已提交审批");
      setShowCreate(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "提交失败");
    }
  };

  const decide = async (id: string, decision: ApprovalDecision) => {
    try {
      await decideApproval(tenantCode, id, {
        decision,
        approver: "manager",
        note: decision === "REJECT" ? "店长驳回" : "店长批准",
      });
      message.success(decision === "APPROVE" ? "已通过" : "已驳回");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    }
  };

  const columns: ColumnsType<ApprovalTicket> = [
    { title: "ID", dataIndex: "id", key: "id", width: 70 },
    {
      title: "类型",
      dataIndex: "type",
      key: "type",
      render: (t: ApprovalType) => <Tag color="blue">{TYPE_LABELS[t]}</Tag>,
    },
    {
      title: "金额/参数",
      key: "amount",
      render: (_, r) => {
        const amt = (r.payload as any)?.amount;
        const bid = (r.payload as any)?.bill_id;
        if (amt) return `¥${(amt / 100).toFixed(2)}`;
        if (bid) return `账单#${bid}`;
        return "—";
      },
    },
    { title: "事由", dataIndex: "reason", key: "reason", render: (v: string) => v || "—" },
    { title: "申请人", dataIndex: "applicant", key: "applicant" },
    { title: "状态", dataIndex: "status", key: "status", render: (s: string) => statusTag(s) },
    { title: "审批人", dataIndex: "approver", key: "approver", render: (v: string | null) => v || "—" },
    {
      title: "操作",
      key: "action",
      render: (_, r) =>
        r.status === "PENDING" ? (
          <Space>
            <Popconfirm title="确认通过并执行？" onConfirm={() => decide(r.id, "APPROVE")}>
              <Button type="link" icon={<CheckOutlined />} style={{ color: "#52c41a" }}>
                通过
              </Button>
            </Popconfirm>
            <Popconfirm title="确认驳回？" onConfirm={() => decide(r.id, "REJECT")}>
              <Button type="link" danger icon={<CloseOutlined />}>
                驳回
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Text type="secondary">已处理</Text>
        ),
    },
  ];

  return (
    <div>
      <Card
        style={{ marginBottom: 16 }}
        styles={{ body: { display: "flex", alignItems: "center", justifyContent: "space-between" } }}
      >
        <Title level={4} style={{ margin: 0 }}>
          审批中心
        </Title>
        <Space>
          <Select
            value={filter}
            style={{ width: 140 }}
            onChange={setFilter}
            options={[
              { value: "ALL", label: "全部" },
              { value: "PENDING", label: "待审批" },
              { value: "APPROVED", label: "已通过" },
              { value: "REJECTED", label: "已驳回" },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowCreate(true)}>
            提交审批
          </Button>
        </Space>
      </Card>

      <Card>
        <Table rowKey="id" loading={loading} columns={columns} dataSource={list} pagination={{ pageSize: 10 }} />
      </Card>

      <Modal
        title="提交审批单"
        open={showCreate}
        onOk={handleCreate}
        onCancel={() => {
          setShowCreate(false);
          form.resetFields();
        }}
        okText="提交"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ type: "DISCOUNT", applicant: "front_desk" }}>
          <Form.Item name="type" label="审批类型" rules={[{ required: true }]}>
            <Select
              options={(Object.keys(TYPE_LABELS) as ApprovalType[]).map((k) => ({
                value: k,
                label: TYPE_LABELS[k],
              }))}
            />
          </Form.Item>
          <Form.Item name="amount" label="折扣金额（元，DISCOUNT 用，正数额）">
            <Input type="number" placeholder="如 30" />
          </Form.Item>
          <Form.Item name="bill_id" label="关联账单 ID（DISCOUNT 必填）">
            <Input type="number" placeholder="如 12" />
          </Form.Item>
          <Form.Item name="reason" label="事由">
            <Input.TextArea rows={2} placeholder="如：老客户协议折扣" />
          </Form.Item>
          <Form.Item name="applicant" label="申请人">
            <Input placeholder="front_desk" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
