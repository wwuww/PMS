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
import { ReloadOutlined, PlusOutlined, CheckOutlined, TeamOutlined, BarChartOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useTenant } from "../store/tenant";
import {
  listHousekeeping,
  createHousekeeping,
  assignHousekeeping,
  doneHousekeeping,
  inspectHousekeeping,
  batchAssignHousekeeping,
  batchDoneHousekeeping,
  housekeepingPerformance,
  type HousekeepingPerformance,
} from "../api/endpoints";
import type { HousekeepingTask, HousekeepingType } from "../api/types";

const { Title, Text } = Typography;

const TYPE_LABELS: Record<HousekeepingType, string> = {
  CLEANUP: "清扫",
  MAINTENANCE: "维修",
  INSPECT: "查房",
};

function statusTag(s: string) {
  const m: Record<string, { color: string; label: string }> = {
    PENDING: { color: "gold", label: "待派单" },
    ASSIGNED: { color: "blue", label: "已派单" },
    PENDING_INSPECT: { color: "purple", label: "待检查" },
    DONE: { color: "green", label: "已完成" },
  };
  const x = m[s] || { color: "default", label: s };
  return <Tag color={x.color}>{x.label}</Tag>;
}

export default function HousekeepingPage() {
  const { tenantCode, hotelId } = useTenant();
  const [list, setList] = useState<HousekeepingTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>("ALL");
  const [showCreate, setShowCreate] = useState(false);
  const [form] = Form.useForm();
  const [assignId, setAssignId] = useState<string | null>(null);
  const [assignForm] = Form.useForm();

  // ---------- M26：多维过滤 + 批量操作 + 绩效 ----------
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [floorFilter, setFloorFilter] = useState<string>("");
  const [assigneeFilter, setAssigneeFilter] = useState<string>("");
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [showBatchAssign, setShowBatchAssign] = useState(false);
  const [batchForm] = Form.useForm<{ assignee: string }>();
  const [batchBusy, setBatchBusy] = useState(false);
  const [perf, setPerf] = useState<HousekeepingPerformance | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);

  const loadPerf = async () => {
    if (!tenantCode || !hotelId) {
      message.warning("请先选择门店");
      return;
    }
    setPerfLoading(true);
    try {
      setPerf(await housekeepingPerformance(tenantCode, hotelId));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "绩效加载失败");
    } finally {
      setPerfLoading(false);
    }
  };

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setList(
        await listHousekeeping(tenantCode, {
          status: filter === "ALL" ? undefined : filter,
          task_type: typeFilter,
          floor: floorFilter || undefined,
          assignee: assigneeFilter || undefined,
          hotel_id: hotelId ?? undefined,
        })
      );
    } catch (e: any) {
      message.error(e?.message || "工单加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, filter, typeFilter, floorFilter, assigneeFilter]);

  const handleBatchAssign = async () => {
    const v = await batchForm.validateFields();
    setBatchBusy(true);
    try {
      const r = await batchAssignHousekeeping(
        tenantCode,
        selectedKeys.map(Number)
      , v.assignee);
      message.success(`批量派单成功 ${r.assigned.length} 单` + (r.failed.length ? `，失败 ${r.failed.length} 单` : ""));
      setShowBatchAssign(false);
      batchForm.resetFields();
      setSelectedKeys([]);
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "批量派单失败");
    } finally {
      setBatchBusy(false);
    }
  };

  const handleBatchDone = async () => {
    setBatchBusy(true);
    try {
      const r = await batchDoneHousekeeping(tenantCode, selectedKeys.map(Number));
      message.success(`批量完成 ${r.done.length} 单` + (r.failed.length ? `，失败 ${r.failed.length} 单` : ""));
      setSelectedKeys([]);
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "批量完成失败");
    } finally {
      setBatchBusy(false);
    }
  };

  const handleCreate = async () => {
    if (!hotelId) {
      message.warning("请先选择门店");
      return;
    }
    const v = await form.validateFields();
    try {
      await createHousekeeping(tenantCode, {
        hotel_id: hotelId,
        room_no: v.room_no,
        task_type: v.task_type || "CLEANUP",
        assignee: v.assignee || null,
        note: v.note || "",
      });
      message.success("已创建工单");
      setShowCreate(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    }
  };

  const handleAssign = async () => {
    if (assignId == null) return;
    const v = await assignForm.validateFields();
    try {
      await assignHousekeeping(tenantCode, assignId, v.assignee);
      message.success("已派单");
      setAssignId(null);
      assignForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "派单失败");
    }
  };

  const handleDone = async (id: string) => {
    try {
      await doneHousekeeping(tenantCode, id);
      message.success("已完成，等待主管检查");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "完成失败");
    }
  };

  const handleInspect = async (id: string, passed: boolean) => {
    try {
      await inspectHousekeeping(tenantCode, id, { passed, operator: "supervisor" });
      message.success(passed ? "检查通过，房间已放行可售" : "已退回返工");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "检查操作失败");
    }
  };

  const columns: ColumnsType<HousekeepingTask> = [
    { title: "ID", dataIndex: "id", key: "id", width: 70 },
    { title: "房号", dataIndex: "room_no", key: "room_no" },
    {
      title: "类型",
      dataIndex: "task_type",
      key: "task_type",
      render: (t: HousekeepingType) => TYPE_LABELS[t],
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (s: string) => statusTag(s),
    },
    { title: "责任人", dataIndex: "assignee", key: "assignee", render: (v: string | null) => v || "—" },
    { title: "来源", dataIndex: "source", key: "source" },
    { title: "备注", dataIndex: "note", key: "note", render: (v: string) => v || "—" },
    {
      title: "操作",
      key: "action",
      render: (_, r) =>
        r.status === "PENDING" ? (
          <Button
            type="link"
            onClick={() => {
              setAssignId(r.id);
              assignForm.resetFields();
            }}
          >
            派单
          </Button>
        ) : r.status === "ASSIGNED" ? (
          <Popconfirm title="确认完成？（完成后进入待检查）" onConfirm={() => handleDone(r.id)}>
            <Button type="link" icon={<CheckOutlined />} style={{ color: "#52c41a" }}>
              完成
            </Button>
          </Popconfirm>
        ) : r.status === "PENDING_INSPECT" ? (
          <Space size={0}>
            <Popconfirm title="检查通过并放行该房？" onConfirm={() => handleInspect(r.id, true)}>
              <Button type="link" style={{ color: "#52c41a" }}>
                检查通过
              </Button>
            </Popconfirm>
            <Popconfirm title="退回返工？" onConfirm={() => handleInspect(r.id, false)}>
              <Button type="link" danger>
                退回
              </Button>
            </Popconfirm>
          </Space>
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
          清扫工单
        </Title>
        <Space wrap>
          <Select
            value={filter}
            style={{ width: 120 }}
            onChange={setFilter}
            options={[
              { value: "ALL", label: "全部状态" },
              { value: "PENDING", label: "待派单" },
              { value: "ASSIGNED", label: "已派单" },
              { value: "PENDING_INSPECT", label: "待检查" },
              { value: "DONE", label: "已完成" },
            ]}
          />
          <Select
            allowClear
            placeholder="类型"
            style={{ width: 100 }}
            value={typeFilter}
            onChange={(v) => setTypeFilter(v)}
            options={(Object.keys(TYPE_LABELS) as HousekeepingType[]).map((k) => ({
              value: k,
              label: TYPE_LABELS[k],
            }))}
          />
          <Input
            allowClear
            placeholder="楼层"
            style={{ width: 80 }}
            value={floorFilter}
            onChange={(e) => setFloorFilter(e.target.value)}
          />
          <Input
            allowClear
            placeholder="责任人"
            style={{ width: 110 }}
            value={assigneeFilter}
            onChange={(e) => setAssigneeFilter(e.target.value)}
          />
          <Button icon={<BarChartOutlined />} onClick={loadPerf} loading={perfLoading}>
            绩效
          </Button>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowCreate(true)}>
            新建工单
          </Button>
        </Space>
      </Card>

      {selectedKeys.length > 0 && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Space>
            <Text>已选 {selectedKeys.length} 单</Text>
            <Button icon={<TeamOutlined />} onClick={() => { batchForm.resetFields(); setShowBatchAssign(true); }}>
              批量派单
            </Button>
            <Popconfirm title={`确认批量完成 ${selectedKeys.length} 单？（空脏房将联动转空净）`} onConfirm={handleBatchDone}>
              <Button type="primary" ghost icon={<CheckOutlined />} loading={batchBusy}>
                批量完成
              </Button>
            </Popconfirm>
            <Button type="text" onClick={() => setSelectedKeys([])}>
              取消选择
            </Button>
          </Space>
        </Card>
      )}

      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={list}
          pagination={{ pageSize: 10 }}
          rowSelection={{ selectedRowKeys: selectedKeys, onChange: setSelectedKeys }}
        />
      </Card>

      {perf && (
        <Card
          size="small"
          title="员工清扫绩效（M26）"
          style={{ marginTop: 16 }}
          extra={
            <Button type="text" onClick={() => setPerf(null)}>
              收起
            </Button>
          }
        >
          <Table
            rowKey="assignee"
            size="small"
            pagination={false}
            columns={[
              { title: "员工", dataIndex: "assignee" },
              { title: "完成单数", dataIndex: "done_count", align: "center", width: 120 },
              {
                title: "平均耗时（分钟）",
                dataIndex: "avg_minutes",
                align: "right",
                render: (v: number) => (v == null ? "—" : v.toFixed(1)),
              },
            ]}
            dataSource={perf.staff}
            locale={{ emptyText: "统计周期内暂无完成工单" }}
          />
        </Card>
      )}

      <Modal
        title="新建清扫工单"
        open={showCreate}
        onOk={handleCreate}
        onCancel={() => {
          setShowCreate(false);
          form.resetFields();
        }}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ task_type: "CLEANUP" }}>
          <Form.Item name="room_no" label="房号" rules={[{ required: true, message: "请输入房号" }]}>
            <Input placeholder="如 401" />
          </Form.Item>
          <Form.Item name="task_type" label="工单类型" rules={[{ required: true }]}>
            <Select
              options={(Object.keys(TYPE_LABELS) as HousekeepingType[]).map((k) => ({
                value: k,
                label: TYPE_LABELS[k],
              }))}
            />
          </Form.Item>
          <Form.Item name="assignee" label="责任人（可选）">
            <Input placeholder="如 保洁员A" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="批量派单"
        open={showBatchAssign}
        onOk={handleBatchAssign}
        confirmLoading={batchBusy}
        onCancel={() => setShowBatchAssign(false)}
        okText={`派单（${selectedKeys.length} 单）`}
        cancelText="取消"
      >
        <Form form={batchForm} layout="vertical">
          <Form.Item name="assignee" label="统一指派给" rules={[{ required: true, message: "请输入责任人" }]}>
            <Input placeholder="如 保洁员A" maxLength={64} />
          </Form.Item>
          <Typography.Paragraph type="secondary">
            逐单尝试派单：仅「待派单」工单会成功，其余计入失败明细。
          </Typography.Paragraph>
        </Form>
      </Modal>

      <Modal
        title="派单"
        open={assignId !== null}
        onOk={handleAssign}
        onCancel={() => setAssignId(null)}
        okText="派单"
        cancelText="取消"
      >
        <Form form={assignForm} layout="vertical">
          <Form.Item name="assignee" label="责任人" rules={[{ required: true, message: "请输入责任人" }]}>
            <Input placeholder="如 保洁员A" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
