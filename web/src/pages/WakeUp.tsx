import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  DatePicker,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import {
  cancelWakeUpCall,
  createWakeUpCall,
  doneWakeUpCall,
  listWakeUpCalls,
} from "../api/endpoints";
import type { WakeUpCall, WakeUpCallCreate } from "../api/types";

const STATUS_COLOR: Record<string, string> = {
  PENDING: "orange",
  DONE: "green",
  CANCELLED: "default",
};

export default function WakeUp() {
  const { tenantCode, hotelId } = useTenant();
  const [rows, setRows] = useState<WakeUpCall[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [showCreate, setShowCreate] = useState(false);
  const [form] = Form.useForm();

  const refresh = useCallback(async () => {
    if (!hotelId) return;
    setLoading(true);
    try {
      setRows(await listWakeUpCalls(tenantCode, hotelId, statusFilter));
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
    const body: WakeUpCallCreate = {
      hotel_id: hotelId,
      room_no: v.room_no,
      call_at: (v.call_at as dayjs.Dayjs).format("YYYY-MM-DDTHH:mm:ss"),
      guest_name: v.guest_name || "",
      note: v.note || "",
      operator: "front_desk",
    };
    try {
      await createWakeUpCall(tenantCode, body);
      message.success("叫醒已登记");
      setShowCreate(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "登记失败");
    }
  };

  const act = async (id: string, fn: (t: string, i: string) => Promise<WakeUpCall>, label: string) => {
    try {
      await fn(tenantCode, id);
      message.success(label);
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "操作失败");
    }
  };

  if (!hotelId) {
    return (
      <div style={{ padding: 24 }}>
        <Card>请先在顶部选择门店后查看叫醒服务。</Card>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="叫醒服务（M3-7）"
        extra={
          <Space>
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 120 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { value: "PENDING", label: "待叫" },
                { value: "DONE", label: "已完成" },
                { value: "CANCELLED", label: "已取消" },
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
              登记叫醒
            </Button>
          </Space>
        }
      >
        <Table<WakeUpCall>
          rowKey="id"
          dataSource={rows}
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
          columns={[
            { title: "ID", dataIndex: "id" },
            { title: "房号", dataIndex: "room_no" },
            { title: "客人", dataIndex: "guest_name", render: (v) => v || "—" },
            { title: "叫醒时间", dataIndex: "call_at" },
            {
              title: "状态",
              dataIndex: "status",
              render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag>,
            },
            { title: "备注", dataIndex: "note", render: (v) => v || "—" },
            {
              title: "操作",
              key: "op",
              render: (_, r) =>
                r.status === "PENDING" ? (
                  <Space>
                    <Button
                      size="small"
                      type="primary"
                      onClick={() => act(r.id, doneWakeUpCall, "已标记完成")}
                    >
                      完成
                    </Button>
                    <Button
                      size="small"
                      danger
                      onClick={() => act(r.id, cancelWakeUpCall, "已取消")}
                    >
                      取消
                    </Button>
                  </Space>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </Card>

      <Modal
        title="登记叫醒"
        open={showCreate}
        onOk={handleCreate}
        onCancel={() => setShowCreate(false)}
        okText="登记"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="room_no"
            label="房号"
            rules={[{ required: true, message: "请输入房号" }]}
          >
            <Input placeholder="如 402" />
          </Form.Item>
          <Form.Item name="guest_name" label="客人姓名">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item
            name="call_at"
            label="叫醒时间"
            rules={[{ required: true, message: "请选择时间" }]}
          >
            <DatePicker showTime style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
