import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined, UploadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  createPsbTask,
  listPsbTasks,
  uploadPsbTask,
} from "../api/endpoints";
import type { PsbTask, PsbTaskCreate } from "../api/types";

const STATUS_COLOR: Record<string, string> = {
  PENDING: "orange",
  UPLOADED: "green",
};

export default function PSB() {
  const { tenantCode, hotelId } = useTenant();
  const [rows, setRows] = useState<PsbTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [showCreate, setShowCreate] = useState(false);
  const [form] = Form.useForm();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listPsbTasks(tenantCode, hotelId ?? undefined, statusFilter));
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId, statusFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreate = async () => {
    if (!hotelId) {
      message.warning("请先选择门店");
      return;
    }
    const v = await form.validateFields();
    const body: PsbTaskCreate = {
      hotel_id: hotelId,
      guest_name: v.guest_name,
      id_doc_no: v.id_doc_no || null,
      room_no: v.room_no || null,
      operator: "front_desk",
    };
    try {
      await createPsbTask(tenantCode, body);
      message.success("已录入报送任务");
      setShowCreate(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "录入失败");
    }
  };

  const upload = async (id: string) => {
    try {
      await uploadPsbTask(tenantCode, id);
      message.success("已上报公安");
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "上报失败");
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="PSB 公安报送（M3-5）"
        extra={
          <Space>
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 120 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { value: "PENDING", label: "待报送" },
                { value: "UPLOADED", label: "已报送" },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setShowCreate(true);
                form.resetFields();
              }}
            >
              录入散客
            </Button>
          </Space>
        }
      >
        <Table<PsbTask>
          rowKey="id"
          dataSource={rows}
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
          columns={[
            { title: "ID", dataIndex: "id" },
            { title: "姓名", dataIndex: "guest_name" },
            {
              title: "证件号",
              dataIndex: "id_doc_no_masked",
              render: (v) => v || "—",
            },
            { title: "房号", dataIndex: "room_no", render: (v) => v || "—" },
            {
              title: "状态",
              dataIndex: "status",
              render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag>,
            },
            {
              title: "上报时间",
              dataIndex: "uploaded_at",
              render: (v) => v || "—",
            },
            {
              title: "操作",
              key: "op",
              render: (_, r) =>
                r.status === "PENDING" ? (
                  <Button
                    size="small"
                    type="primary"
                    icon={<UploadOutlined />}
                    onClick={() => upload(r.id)}
                  >
                    上报
                  </Button>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </Card>

      <Modal
        title="录入散客报送（无预订现场登记）"
        open={showCreate}
        onOk={handleCreate}
        onCancel={() => setShowCreate(false)}
        okText="录入"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="guest_name"
            label="客人姓名"
            rules={[{ required: true, message: "请输入姓名" }]}
          >
            <Input placeholder="入住人姓名" />
          </Form.Item>
          <Form.Item name="id_doc_no" label="证件号">
            <Input placeholder="身份证/护照号" />
          </Form.Item>
          <Form.Item name="room_no" label="房号">
            <Input placeholder="如 402" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
