import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import {
  App,
  Button,
  Card,
  DatePicker,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { PlusOutlined, ReloadOutlined, TeamOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import {
  listGroupBlocks,
  createGroupBlock,
  assignGroupBlockRooms,
  checkInGroupBlock,
  closeGroupBlock,
  listRooms,
  listRoomTypes,
} from "../api/endpoints";
import type {
  GroupBlock as GB,
  GroupAllocation,
  Room,
  RoomType,
} from "../api/types";
import { useTenant } from "../store/tenant";
import { ROOM_STATE_LABELS } from "../domain/roomActions";

const BLOCK_STATUS_LABEL: Record<string, { text: string; color: string }> = {
  active: { text: "生效中", color: "green" },
  closed: { text: "已关闭", color: "default" },
  draft: { text: "草稿", color: "gold" },
};

const ALLOC_STATUS_LABEL: Record<string, { text: string; color: string }> = {
  assigned: { text: "已排房", color: "cyan" },
  checked_in: { text: "已入住", color: "blue" },
  checked_out: { text: "已退房", color: "default" },
};

export default function GroupBlockPage() {
  const { tenantCode, hotelId, hotels } = useTenant();
  const { message } = App.useApp();
  const [blocks, setBlocks] = useState<GB[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [drawerBlock, setDrawerBlock] = useState<GB | null>(null);
  const [assignVisible, setAssignVisible] = useState(false);
  const [assignForm] = Form.useForm();
  const [assignSubmitting, setAssignSubmitting] = useState(false);

  const hotelName = (id: string) =>
    hotels.find((h) => h.id === id)?.name ?? `#${id}`;
  const rtName = (id: string) =>
    roomTypes.find((x) => x.id === id)?.name ?? `#${id}`;

  const load = useCallback(async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [bk, rm, rt] = await Promise.all([
        listGroupBlocks(tenantCode, hotelId ?? undefined),
        listRooms(tenantCode),
        listRoomTypes(tenantCode),
      ]);
      setBlocks(bk);
      setRooms(rm);
      setRoomTypes(rt);
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId, message]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, hotelId]);

  // 当前 block 已占用的房号（避免重复排同一房）
  const usedRoomNos = useMemo(
    () => new Set((drawerBlock?.allocations ?? []).map((a) => a.room_no)),
    [drawerBlock]
  );
  // 可排房：空净且未被本 block 占用
  const assignableRooms = useMemo(
    () =>
      rooms.filter(
        (r) => r.state === "vacant_clean" && !usedRoomNos.has(r.room_no)
      ),
    [rooms, usedRoomNos]
  );

  const openCreate = () => setCreateOpen(true);

  // 用 ref 持有创建表单实例
  const createFormRef = useCreateFormRef();

  const handleCreate = async () => {
    try {
      if (!hotelId) {
        message.error("请先在右上角选择门店");
        return;
      }
      const f = await (createFormRef.current?.validateFields() ?? Promise.reject());
      const body = {
        hotel_id: hotelId,
        name: f.name as string,
        arrival_date: (f.arrival_date as Dayjs).format("YYYY-MM-DD"),
        departure_date: (f.departure_date as Dayjs).format("YYYY-MM-DD"),
        notes: f.notes ?? null,
      };
      setSubmitting(true);
      await createGroupBlock(tenantCode, body);
      message.success("团队排房已创建");
      setCreateOpen(false);
      createFormRef.current?.resetFields();
      await load();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const openDrawer = (b: GB) => setDrawerBlock(b);

  const reloadBlock = async (id: string) => {
    const fresh = await listGroupBlocks(tenantCode, hotelId ?? undefined);
    setBlocks(fresh);
    const found = fresh.find((x) => x.id === id) ?? null;
    setDrawerBlock(found);
    const rm = await listRooms(tenantCode);
    setRooms(rm);
  };

  const handleAssign = async () => {
    if (!drawerBlock) return;
    try {
      const rows = await assignForm.validateFields();
      const allocations = (rows.allocations as {
        room_no: string;
        room_type_id: number;
        guest_name?: string;
        guest_phone?: string;
      }[]).map((a) => ({
        room_no: a.room_no,
        room_type_id: a.room_type_id,
        guest_name: a.guest_name || null,
        guest_phone: a.guest_phone || null,
      }));
      if (!allocations.length) {
        message.warning("请至少添加一间房");
        return;
      }
      setAssignSubmitting(true);
      await assignGroupBlockRooms(tenantCode, drawerBlock.id, { allocations });
      message.success("排房成功（已锁房预留）");
      setAssignVisible(false);
      assignForm.resetFields();
      await reloadBlock(drawerBlock.id);
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message);
    } finally {
      setAssignSubmitting(false);
    }
  };

  const handleCheckIn = async () => {
    if (!drawerBlock) return;
    try {
      await checkInGroupBlock(tenantCode, drawerBlock.id);
      message.success("团队批量入住成功");
      await reloadBlock(drawerBlock.id);
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  };

  const handleClose = async () => {
    if (!drawerBlock) return;
    try {
      await closeGroupBlock(tenantCode, drawerBlock.id);
      message.success("团队排房已关闭");
      await reloadBlock(drawerBlock.id);
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  };

  const blockCols = [
    { title: "团队名称", dataIndex: "name", key: "name" },
    {
      title: "门店",
      dataIndex: "hotel_id",
      key: "hotel_id",
      render: (v: string) => hotelName(v),
    },
    {
      title: "抵店 ~ 离店",
      key: "range",
      render: (_: unknown, b: GB) => `${b.arrival_date} ~ ${b.departure_date}`,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (v: string) => {
        const s = BLOCK_STATUS_LABEL[v] ?? { text: v, color: "default" };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
    {
      title: "排房数",
      key: "cnt",
      render: (_: unknown, b: GB) => b.allocations.length,
    },
    {
      title: "操作",
      key: "op",
      render: (_: unknown, b: GB) => (
        <Button size="small" type="link" onClick={() => openDrawer(b)}>
          排房 / 入住
        </Button>
      ),
    },
  ];

  const allocCols = [
    { title: "房号", dataIndex: "room_no", key: "room_no" },
    {
      title: "房型",
      dataIndex: "room_type_id",
      key: "room_type_id",
      render: (v: string) => rtName(v),
    },
    {
      title: "住客",
      dataIndex: "guest_name",
      key: "guest_name",
      render: (v: string | null) => v || "—",
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (v: string) => {
        const s = ALLOC_STATUS_LABEL[v] ?? { text: v, color: "default" };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12, width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          团队 / 会议排房
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<TeamOutlined />}
            onClick={openCreate}
            disabled={!hotelId}
          >
            新建团队排房
          </Button>
        </Space>
      </Space>

      <Card size="small" loading={loading && blocks.length === 0}>
        {blocks.length ? (
          <Table
            rowKey="id"
            size="small"
            pagination={false}
            columns={blockCols}
            dataSource={blocks}
          />
        ) : (
          <Empty description="暂无团队排房" />
        )}
      </Card>

      {/* 新建团队 */}
      <Modal
        title="新建团队排房"
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false);
          createFormRef.current?.resetFields();
        }}
        onOk={handleCreate}
        confirmLoading={submitting}
        okText="创建"
        destroyOnClose
      >
        <CreateBlockForm ref={createFormRef} />
      </Modal>

      {/* 排房 / 入住抽屉 */}
      <Drawer
        title={drawerBlock ? `团队排房：${drawerBlock.name}` : "团队排房"}
        width={640}
        open={drawerBlock !== null}
        onClose={() => setDrawerBlock(null)}
        extra={
          drawerBlock?.status === "active" ? (
            <Space>
              <Button
                icon={<PlusOutlined />}
                onClick={() => setAssignVisible((v) => !v)}
              >
                添加房间
              </Button>
              <Button type="primary" onClick={handleCheckIn}>
                批量入住
              </Button>
              <Popconfirm title="确认关闭该团队排房？" onConfirm={handleClose}>
                <Button danger>关闭</Button>
              </Popconfirm>
            </Space>
          ) : null
        }
      >
        {drawerBlock && (
          <>
            <Typography.Paragraph type="secondary">
              门店：{hotelName(drawerBlock.hotel_id)}　|　抵店：
              {drawerBlock.arrival_date}　|　离店：{drawerBlock.departure_date}
            </Typography.Paragraph>
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              columns={allocCols}
              dataSource={drawerBlock.allocations}
            />

            {assignVisible && drawerBlock.status === "active" && (
              <Card
                size="small"
                title="添加排房"
                style={{ marginTop: 16 }}
                extra={
                  <Button
                    type="primary"
                    loading={assignSubmitting}
                    onClick={handleAssign}
                  >
                    确认排房
                  </Button>
                }
              >
                <Form form={assignForm} layout="vertical">
                  <Form.List name="allocations">
                    {(fields, { add, remove }) => (
                      <>
                        {fields.map((field) => (
                          <Space
                            key={field.key}
                            align="baseline"
                            style={{ display: "flex", marginBottom: 8 }}
                          >
                            <Form.Item
                              {...field}
                              name={[field.name, "room_no"]}
                              rules={[{ required: true, message: "选房" }]}
                            >
                              <Select
                                showSearch
                                placeholder="空净房"
                                style={{ width: 130 }}
                                options={assignableRooms.map((r) => ({
                                  value: r.room_no,
                                  label: `${r.room_no} · ${ROOM_STATE_LABELS[r.state]}`,
                                }))}
                                onChange={(rn: string) => {
                                  const r = rooms.find((x) => x.room_no === rn);
                                  if (r)
                                    assignForm.setFieldValue(
                                      ["allocations", field.name, "room_type_id"],
                                      r.room_type_id
                                    );
                                }}
                              />
                            </Form.Item>
                            <Form.Item
                              {...field}
                              name={[field.name, "room_type_id"]}
                              rules={[{ required: true, message: "房型" }]}
                            >
                              <Select
                                placeholder="房型"
                                style={{ width: 120 }}
                                options={roomTypes.map((rt) => ({
                                  value: rt.id,
                                  label: rt.name,
                                }))}
                              />
                            </Form.Item>
                            <Form.Item {...field} name={[field.name, "guest_name"]}>
                              <Input placeholder="住客姓名" style={{ width: 120 }} />
                            </Form.Item>
                            <Form.Item {...field} name={[field.name, "guest_phone"]}>
                              <Input placeholder="手机号" style={{ width: 130 }} />
                            </Form.Item>
                            <Button
                              type="text"
                              danger
                              onClick={() => remove(field.name)}
                            >
                              删
                            </Button>
                          </Space>
                        ))}
                        <Button
                          type="dashed"
                          onClick={() => add()}
                          block
                          icon={<PlusOutlined />}
                        >
                          添加一行
                        </Button>
                      </>
                    )}
                  </Form.List>
                </Form>
              </Card>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
}

// 创建表单（独立组件，便于用 ref 校验）
interface CreateFormHandle {
  validateFields: () => Promise<{
    name: string;
    arrival_date: Dayjs;
    departure_date: Dayjs;
    notes?: string;
  }>;
  resetFields: () => void;
}

const CreateBlockForm = forwardRef<CreateFormHandle>((_props, ref) => {
  const [form] = Form.useForm();
  useImperativeHandle(ref, () => ({
    validateFields: () => form.validateFields(),
    resetFields: () => form.resetFields(),
  }));
  return (
    <Form form={form} layout="vertical">
      <Form.Item
        name="name"
        label="团队名称"
        rules={[{ required: true, message: "请输入团队名称" }]}
      >
        <Input placeholder="如：旅行团A / 公司年会" />
      </Form.Item>
      <Space size="large">
        <Form.Item
          name="arrival_date"
          label="抵店日期"
          rules={[{ required: true, message: "请选择抵店日" }]}
        >
          <DatePicker />
        </Form.Item>
        <Form.Item
          name="departure_date"
          label="离店日期"
          rules={[{ required: true, message: "请选择离店日" }]}
        >
          <DatePicker />
        </Form.Item>
      </Space>
      <Form.Item name="notes" label="备注">
        <Input.TextArea rows={2} placeholder="选填" />
      </Form.Item>
    </Form>
  );
});
CreateBlockForm.displayName = "CreateBlockForm";

// 简易 ref hook（避免重复声明）
function useCreateFormRef() {
  return useRef<CreateFormHandle>(null);
}
