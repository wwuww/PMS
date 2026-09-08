import { useEffect, useMemo, useState } from "react";
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
  Typography,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import { listRooms, listRoomTypes, createRooms } from "../api/endpoints";
import type { Room, RoomType, RoomCreate } from "../api/types";

const { Title, Text } = Typography;

const STATE_LABELS: Record<string, { label: string; color: string }> = {
  vacant_clean: { label: "空净", color: "green" },
  vacant_dirty: { label: "空脏", color: "orange" },
  occupied: { label: "在住", color: "blue" },
  arrival_locked: { label: "锁房", color: "purple" },
  maintenance: { label: "维修", color: "red" },
  out_of_service: { label: "停用", color: "default" },
};

export default function Rooms() {
  const { tenantCode, hotelId } = useTenant();
  const [list, setList] = useState<Room[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);
  const [stateFilter, setStateFilter] = useState<string>("ALL");
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [rs, rts] = await Promise.all([
        listRooms(tenantCode),
        listRoomTypes(tenantCode),
      ]);
      setList(rs);
      setRoomTypes(rts);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "房间加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const rtMap = useMemo(() => {
    const m = new Map<string, string>();
    roomTypes.forEach((r) => m.set(r.id, `${r.name}（${r.code}）`));
    return m;
  }, [roomTypes]);

  const filtered = useMemo(() => {
    if (stateFilter === "ALL") return list;
    return list.filter((r) => r.state === stateFilter);
  }, [list, stateFilter]);

  const handleCreate = async () => {
    if (!hotelId) {
      message.warning("请先在顶部选择门店");
      return;
    }
    const v = await form.validateFields();
    const nos = String(v.room_nos || "")
      .split(/[\n,，]+/)
      .map((s: string) => s.trim())
      .filter(Boolean);
    if (!nos.length) {
      message.warning("请至少填写一个房号");
      return;
    }
    const body: RoomCreate[] = nos.map((room_no: string) => ({
      room_type_id: v.room_type_id,
      room_no,
      floor:
        v.floor ||
        String(room_no).replace(/[^0-9]/g, "").slice(0, 2) ||
        "0",
    }));
    setSaving(true);
    try {
      await createRooms(hotelId, body);
      message.success(`已创建 ${body.length} 间房`);
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
      { title: "房号", dataIndex: "room_no", width: 110 },
      { title: "楼层", dataIndex: "floor", width: 80 },
      {
        title: "房型",
        dataIndex: "room_type_id",
        render: (id: string) =>
          rtMap.get(id) || <Text type="secondary">未关联</Text>,
      },
      {
        title: "状态",
        dataIndex: "state",
        render: (s: string) => {
          const meta = STATE_LABELS[s] || { label: s, color: "default" };
          return <Tag color={meta.color}>{meta.label}</Tag>;
        },
      },
      { title: "门店ID", dataIndex: "hotel_id", width: 90 },
    ],
    [rtMap]
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          房间 / 库存管理
        </Title>
        <Space>
          <Select
            value={stateFilter}
            style={{ width: 140 }}
            onChange={setStateFilter}
            options={[
              { value: "ALL", label: "全部状态" },
              ...Object.entries(STATE_LABELS).map(([k, v]) => ({
                value: k,
                label: v.label,
              })),
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setShow(true)}>
            批量建房
          </Button>
        </Space>
      </div>
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={filtered}
          columns={columns}
          pagination={{ pageSize: 14 }}
        />
      </Card>
      <Modal
        title="批量新建房间"
        open={show}
        onOk={handleCreate}
        confirmLoading={saving}
        onCancel={() => {
          setShow(false);
          form.resetFields();
        }}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ floor: "4" }}>
          <Form.Item
            name="room_type_id"
            label="房型"
            rules={[{ required: true, message: "请选择房型" }]}
          >
            <Select
              placeholder="选择房型"
              options={roomTypes.map((r) => ({
                value: r.id,
                label: `${r.name}（${r.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="room_nos"
            label="房号（每行一个，或用逗号分隔）"
            rules={[{ required: true, message: "请填写房号" }]}
          >
            <Input.TextArea rows={6} placeholder={"401\n402\n403"} />
          </Form.Item>
          <Form.Item name="floor" label="楼层（默认取房号前两位，可覆盖）">
            <Input placeholder="如：4" maxLength={8} />
          </Form.Item>
          <Text type="secondary">目标门店：{hotelId ? `ID ${hotelId}` : "未选择"}</Text>
        </Form>
      </Modal>
    </div>
  );
}
