import { useCallback, useEffect, useState } from "react";
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
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useTenant } from "../store/tenant";
import {
  listComplaints,
  createComplaint,
  transitionComplaint,
} from "../api/endpoints";
import type { Complaint, ComplaintCategory } from "../api/types";

const { Title, Text } = Typography;

const CATEGORY_LABELS: Record<ComplaintCategory, string> = {
  SERVICE: "服务",
  FACILITY: "设施",
  HYGIENE: "卫生",
  NOISE: "噪音",
  BILLING: "账务",
  OTHER: "其他",
};

function statusTag(s: string) {
  const m: Record<string, { color: string; label: string }> = {
    OPEN: { color: "red", label: "待受理" },
    HANDLING: { color: "processing", label: "处理中" },
    RESOLVED: { color: "green", label: "已办结" },
    CANCELLED: { color: "default", label: "已取消" },
  };
  const x = m[s] || { color: "default", label: s };
  return <Tag color={x.color}>{x.label}</Tag>;
}

export default function ComplaintsPage() {
  const { tenantCode, hotelId } = useTenant();
  const [list, setList] = useState<Complaint[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm] = Form.useForm<{
    guest_name: string;
    guest_phone?: string;
    room_no?: string;
    booking_id?: string;
    category: ComplaintCategory;
    description?: string;
  }>();
  const [createBusy, setCreateBusy] = useState(false);
  const [resolveTarget, setResolveTarget] = useState<Complaint | null>(null);
  const [resolveForm] = Form.useForm<{ handler: string; resolution: string }>();
  const [resolveBusy, setResolveBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setList(
        await listComplaints(tenantCode, {
          hotel_id: hotelId ?? undefined,
          status: statusFilter === "ALL" ? undefined : statusFilter,
        })
      );
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "投诉加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId, statusFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreate = async () => {
    const v = await createForm.validateFields();
    setCreateBusy(true);
    try {
      await createComplaint(tenantCode, {
        hotel_id: hotelId!,
        guest_name: v.guest_name,
        guest_phone: v.guest_phone || null,
        room_no: v.room_no || null,
        booking_id: v.booking_id || null,
        category: v.category,
        description: v.description || "",
        source: "FRONT_DESK",
      });
      message.success("投诉已登记");
      setShowCreate(false);
      createForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "登记失败");
    } finally {
      setCreateBusy(false);
    }
  };

  const handleResolve = async () => {
    if (!resolveTarget) return;
    const v = await resolveForm.validateFields();
    setResolveBusy(true);
    try {
      await transitionComplaint(tenantCode, resolveTarget.id, {
        to_status: "RESOLVED",
        handler: v.handler,
        resolution: v.resolution,
      });
      message.success("投诉已办结");
      setResolveTarget(null);
      resolveForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "办结失败");
    } finally {
      setResolveBusy(false);
    }
  };

  const handleAccept = async (c: Complaint) => {
    try {
      await transitionComplaint(tenantCode, c.id, {
        to_status: "HANDLING",
        handler: "前台",
      });
      message.success("已受理");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "受理失败");
    }
  };

  const columns: ColumnsType<Complaint> = [
    { title: "ID", dataIndex: "id", width: 70 },
    { title: "住客", dataIndex: "guest_name", width: 100 },
    {
      title: "房号",
      dataIndex: "room_no",
      width: 80,
      render: (v: string | null) => v || "—",
    },
    {
      title: "分类",
      dataIndex: "category",
      width: 90,
      render: (c: ComplaintCategory) => <Tag>{CATEGORY_LABELS[c] ?? c}</Tag>,
    },
    { title: "描述", dataIndex: "description", ellipsis: true },
    { title: "状态", dataIndex: "status", width: 100, render: statusTag },
    {
      title: "处理人",
      dataIndex: "handler",
      width: 90,
      render: (v: string | null) => v || "—",
    },
    {
      title: "结果",
      dataIndex: "resolution",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
    {
      title: "操作",
      key: "action",
      width: 140,
      render: (_, r) =>
        r.status === "OPEN" ? (
          <Popconfirm title="受理该投诉（指定前台处理）？" onConfirm={() => handleAccept(r)}>
            <Button type="link" size="small">
              受理
            </Button>
          </Popconfirm>
        ) : r.status === "HANDLING" ? (
          <Button
            type="link"
            size="small"
            onClick={() => {
              resolveForm.resetFields();
              resolveForm.setFieldsValue({ handler: r.handler || "前台" });
              setResolveTarget(r);
            }}
          >
            办结
          </Button>
        ) : (
          <Text type="secondary">—</Text>
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
          投诉管理
        </Title>
        <Space>
          <Select
            value={statusFilter}
            style={{ width: 120 }}
            onChange={setStatusFilter}
            options={[
              { value: "ALL", label: "全部" },
              { value: "OPEN", label: "待受理" },
              { value: "HANDLING", label: "处理中" },
              { value: "RESOLVED", label: "已办结" },
              { value: "CANCELLED", label: "已取消" },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowCreate(true)}>
            登记投诉
          </Button>
        </Space>
      </Card>

      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={list}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title="登记投诉"
        open={showCreate}
        onOk={handleCreate}
        confirmLoading={createBusy}
        onCancel={() => setShowCreate(false)}
        okText="登记"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" initialValues={{ category: "SERVICE" }}>
          <Form.Item name="guest_name" label="住客姓名" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input placeholder="如 张三" maxLength={64} />
          </Form.Item>
          <Form.Item name="guest_phone" label="手机号（可选，便于住客关联查询）">
            <Input placeholder="如 13900000000" maxLength={32} />
          </Form.Item>
          <Form.Item name="booking_id" label="关联预订号（可选，自动回填房号）">
            <Input type="number" placeholder="如 123" />
          </Form.Item>
          <Form.Item name="room_no" label="房号（可选）">
            <Input placeholder="如 401" maxLength={16} />
          </Form.Item>
          <Form.Item name="category" label="投诉分类" rules={[{ required: true }]}>
            <Select
              options={(Object.keys(CATEGORY_LABELS) as ComplaintCategory[]).map((k) => ({
                value: k,
                label: CATEGORY_LABELS[k],
              }))}
            />
          </Form.Item>
          <Form.Item name="description" label="投诉描述">
            <Input.TextArea rows={3} maxLength={512} placeholder="如 空调噪音大，影响休息" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`办结投诉 #${resolveTarget?.id ?? ""}`}
        open={resolveTarget != null}
        onOk={handleResolve}
        confirmLoading={resolveBusy}
        onCancel={() => setResolveTarget(null)}
        okText="办结"
        cancelText="取消"
      >
        <Form form={resolveForm} layout="vertical">
          <Form.Item name="handler" label="处理人" rules={[{ required: true, message: "请输入处理人" }]}>
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="resolution" label="处理结果" rules={[{ required: true, message: "请填写处理结果" }]}>
            <Input.TextArea rows={3} maxLength={512} placeholder="如 已更换房间并补偿果盘" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
