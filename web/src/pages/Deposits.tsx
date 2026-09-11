// 押金管理主页面（M32.18 T05）：
// 列表（筛选 + 分页上限）+ 新建 + 详情抽屉 + 行内动作（冲抵/退款/释放/作废）+ 超期预授权批量释放。
// 权限门控：useCan(DEPOSIT_MANAGE/DEPOSIT_REFUND/NIGHT_AUDIT_RUN) 与 meta.canAct 双重叠加。
import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  applyDeposit,
  autoReleaseDeposits,
  listDeposits,
  refundDeposit,
  releaseDeposit,
  voidDeposit,
} from "../api/endpoints";
import type { Deposit } from "../api/types";
import { useTenant } from "../store/tenant";
import { fmtCents, yuanToCents } from "../utils/format";
import { currentOperator, useCan } from "../utils/permission";
import DepositForm from "../components/deposit/DepositForm";
import DepositDetailDrawer from "../components/deposit/DepositDetailDrawer";
import {
  KIND_LABELS,
  METHOD_LABELS,
  STATUS_META,
  canAct,
} from "../components/deposit/meta";

interface Filters {
  status?: string;
  kind?: string;
  room_no?: string;
  booking_id?: number;
  limit: number;
}

const STATUS_OPTIONS = [
  { value: "ALL", label: "全部状态" },
  ...Object.entries(STATUS_META).map(([k, v]) => ({ value: k, label: v.label })),
];
const KIND_OPTIONS = [
  { value: "ALL", label: "全部类型" },
  ...Object.entries(KIND_LABELS).map(([k, v]) => ({ value: k, label: v })),
];

type ActionKind = "apply" | "refund" | "void";

export default function Deposits() {
  const { tenantCode, hotelId } = useTenant();
  const canManage = useCan("DEPOSIT_MANAGE");
  const canRefund = useCan("DEPOSIT_REFUND");
  const canNight = useCan("NIGHT_AUDIT_RUN");

  const [filters, setFilters] = useState<Filters>({ limit: 50 });
  const [data, setData] = useState<Deposit[]>([]);
  const [loading, setLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [actionRow, setActionRow] = useState<Deposit | null>(null);
  const [actionKind, setActionKind] = useState<ActionKind | null>(null);
  const [actionForm] = Form.useForm();

  const [autoOpen, setAutoOpen] = useState(false);
  const [autoForm] = Form.useForm();

  const fetchList = useCallback(async () => {
    if (!canManage) {
      setData([]);
      return;
    }
    setLoading(true);
    try {
      const list = await listDeposits(tenantCode, {
        hotel_id: hotelId ? Number(hotelId) : undefined,
        status: filters.status && filters.status !== "ALL" ? filters.status : undefined,
        kind: filters.kind && filters.kind !== "ALL" ? filters.kind : undefined,
        room_no: filters.room_no?.trim() || undefined,
        booking_id: filters.booking_id,
        limit: filters.limit,
      });
      setData(list);
    } catch (e: any) {
      message.error(e?.message || "加载押金列表失败");
      setData([]);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    tenantCode,
    hotelId,
    filters.status,
    filters.kind,
    filters.room_no,
    filters.booking_id,
    filters.limit,
    canManage,
  ]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const refresh = () => fetchList();

  const openAction = (row: Deposit, kind: ActionKind) => {
    setActionRow(row);
    setActionKind(kind);
    actionForm.resetFields();
    if (kind === "apply" || kind === "refund") {
      actionForm.setFieldsValue({
        amount: Number((row.available_cents / 100).toFixed(2)),
      });
    } else if (kind === "void") {
      actionForm.setFieldsValue({ reason: "" });
    }
  };
  const closeAction = () => {
    setActionRow(null);
    setActionKind(null);
  };

  const submitAction = async () => {
    if (!actionRow || !actionKind) return;
    const vals = await actionForm.validateFields();
    try {
      if (actionKind === "apply") {
        await applyDeposit(tenantCode, actionRow.id, {
          amount: yuanToCents(vals.amount),
          target_bill_id: null,
          operator: currentOperator(),
          expected_version: actionRow.version,
        });
        message.success("冲抵成功");
      } else if (actionKind === "refund") {
        await refundDeposit(tenantCode, actionRow.id, {
          amount: yuanToCents(vals.amount),
          operator: currentOperator(),
          note: vals.note?.trim(),
          expected_version: actionRow.version,
        });
        message.success("退款成功");
      } else if (actionKind === "void") {
        await voidDeposit(tenantCode, actionRow.id, {
          operator: currentOperator(),
          reason: vals.reason?.trim() || null,
          expected_version: actionRow.version,
        });
        message.success("已作废");
      }
      closeAction();
      refresh();
    } catch (e: any) {
      const msg = e?.message || "操作失败";
      if (/version|冲突|已被/.test(msg)) {
        message.error("数据已被修改，请刷新重试");
      } else {
        message.error(msg);
      }
      refresh();
    }
  };

  const doRelease = async (row: Deposit) => {
    try {
      await releaseDeposit(tenantCode, row.id, {
        operator: currentOperator(),
        cause: "MANUAL",
        expected_version: row.version,
      });
      message.success("已释放预授权");
      refresh();
    } catch (e: any) {
      const msg = e?.message || "释放失败";
      if (/version|冲突|已被/.test(msg)) {
        message.error("数据已被修改，请刷新重试");
      } else {
        message.error(msg);
      }
      refresh();
    }
  };

  const submitAutoRelease = async () => {
    if (!hotelId) {
      message.warning("请先选择门店");
      return;
    }
    const vals = await autoForm.validateFields();
    try {
      const out = await autoReleaseDeposits(tenantCode, {
        hotel_id: Number(hotelId),
        days: vals.days ?? 30,
        operator: "front_desk",
      });
      message.success(`已释放 ${out.released} 笔预授权`);
      setAutoOpen(false);
      autoForm.resetFields();
      refresh();
    } catch (e: any) {
      message.error(e?.message || "批量释放失败");
    }
  };

  const columns: ColumnsType<Deposit> = [
    { title: "押金单号", dataIndex: "deposit_no", width: 160 },
    {
      title: "类型",
      dataIndex: "kind",
      width: 90,
      render: (v) => <Tag>{KIND_LABELS[v as keyof typeof KIND_LABELS] ?? v}</Tag>,
    },
    {
      title: "方式",
      dataIndex: "method",
      width: 80,
      render: (v) => (
        <Tag color="blue">{METHOD_LABELS[v as keyof typeof METHOD_LABELS] ?? v}</Tag>
      ),
    },
    { title: "房号", dataIndex: "room_no", width: 80, render: (v) => v || "—" },
    { title: "预订", dataIndex: "booking_id", width: 80, render: (v) => v || "—" },
    {
      title: "金额 / 已冲抵 / 已退 / 可用",
      width: 280,
      render: (_, r) => (
        <span>
          {fmtCents(r.amount_cents)} / {fmtCents(r.applied_cents)} /{" "}
          {fmtCents(r.refunded_cents)} / <strong>{fmtCents(r.available_cents)}</strong>
        </span>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (v: keyof typeof STATUS_META) => {
        const m = STATUS_META[v];
        return m ? <Tag color={m.color}>{m.label}</Tag> : <Tag>{v}</Tag>;
      },
    },
    { title: "操作员", dataIndex: "operator", width: 100 },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 170,
      render: (v) => (v ? new Date(v).toLocaleString() : "—"),
    },
    {
      title: "操作",
      width: 280,
      fixed: "right",
      render: (_, r) => {
        const cApply = canAct(r, "apply");
        const cRefund = canAct(r, "refund");
        const cRelease = canAct(r, "release");
        const cVoid = canAct(r, "void");
        return (
          <Space size={4} wrap>
            <Button
              size="small"
              onClick={() => {
                setDrawerId(r.id);
                setDrawerOpen(true);
              }}
            >
              查看
            </Button>
            <Button
              size="small"
              disabled={!canManage || !cApply}
              onClick={() => openAction(r, "apply")}
            >
              冲抵
            </Button>
            <Button
              size="small"
              danger
              disabled={!canRefund || !cRefund}
              onClick={() => openAction(r, "refund")}
            >
              退款
            </Button>
            <Popconfirm
              title="确认释放该预授权？"
              onConfirm={() => doRelease(r)}
              disabled={!canManage || !cRelease}
            >
              <Button size="small" disabled={!canManage || !cRelease}>
                释放
              </Button>
            </Popconfirm>
            <Button
              size="small"
              danger
              disabled={!canManage || !cVoid}
              onClick={() => openAction(r, "void")}
            >
              作废
            </Button>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          marginBottom: 12,
          alignItems: "center",
        }}
      >
        <Select
          style={{ width: 140 }}
          value={filters.status ?? "ALL"}
          options={STATUS_OPTIONS}
          onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
        />
        <Select
          style={{ width: 140 }}
          value={filters.kind ?? "ALL"}
          options={KIND_OPTIONS}
          onChange={(v) => setFilters((f) => ({ ...f, kind: v }))}
        />
        <Input
          style={{ width: 120 }}
          placeholder="房号"
          value={filters.room_no ?? ""}
          onChange={(e) => setFilters((f) => ({ ...f, room_no: e.target.value }))}
        />
        <InputNumber
          style={{ width: 140 }}
          placeholder="预订 ID"
          value={filters.booking_id}
          onChange={(v) => setFilters((f) => ({ ...f, booking_id: v ?? undefined }))}
        />
        <Select
          style={{ width: 120 }}
          value={filters.limit}
          options={[
            { value: 50, label: "50 条" },
            { value: 100, label: "100 条" },
            { value: 200, label: "200 条" },
          ]}
          onChange={(v) => setFilters((f) => ({ ...f, limit: v }))}
        />
        <Button onClick={refresh}>刷新</Button>
        <div style={{ flex: 1 }} />
        <Button type="primary" disabled={!canManage} onClick={() => setCreateOpen(true)}>
          收押金 / 冻结预授权
        </Button>
        <Button disabled={!canNight} onClick={() => setAutoOpen(true)}>
          超期预授权批量释放
        </Button>
      </div>

      <Table<Deposit>
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        scroll={{ x: 1400 }}
        pagination={false}
        size="small"
        locale={{ emptyText: <Empty description="暂无押金记录" /> }}
      />

      <DepositForm open={createOpen} onClose={() => setCreateOpen(false)} onCreated={refresh} />

      <DepositDetailDrawer
        open={drawerOpen}
        depositId={drawerId}
        onClose={() => setDrawerOpen(false)}
      />

      {/* 冲抵 / 退款 / 作废 通用弹窗 */}
      <Modal
        title={
          actionKind === "apply"
            ? "冲抵账单"
            : actionKind === "refund"
            ? "原路退款"
            : actionKind === "void"
            ? "作废押金"
            : ""
        }
        open={!!actionKind}
        onOk={submitAction}
        onCancel={closeAction}
        okText="提交"
        cancelText="取消"
        destroyOnClose
      >
        {actionRow && (
          <div style={{ marginBottom: 12, color: "#666" }}>
            押金单号：<strong>{actionRow.deposit_no}</strong> · 可用余额：
            <strong>{fmtCents(actionRow.available_cents)}</strong>
          </div>
        )}
        <Form form={actionForm} layout="vertical" preserve={false}>
          {(actionKind === "apply" || actionKind === "refund") && (
            <Form.Item
              name="amount"
              label="金额（元）"
              rules={[
                { required: true, message: "请输入金额" },
                { type: "number", min: 0.01, message: "金额必须大于 0" },
              ]}
            >
              <InputNumber
                addonBefore="¥"
                min={0.01}
                precision={2}
                style={{ width: "100%" }}
              />
            </Form.Item>
          )}
          {actionKind === "refund" && (
            <Form.Item
              name="note"
              label="退款原因"
              rules={[{ required: true, message: "请填写退款原因（审计必填）" }]}
            >
              <Input.TextArea rows={3} maxLength={255} />
            </Form.Item>
          )}
          {actionKind === "void" && (
            <Form.Item name="reason" label="作废原因（可选）">
              <Input.TextArea rows={3} maxLength={255} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 超期预授权批量释放 */}
      <Modal
        title="超期预授权批量释放"
        open={autoOpen}
        onOk={submitAutoRelease}
        onCancel={() => setAutoOpen(false)}
        okText="执行"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={autoForm} layout="vertical" initialValues={{ days: 30 }} preserve={false}>
          <Form.Item
            name="days"
            label="超过天数（创建 ≥ 该天数 的 AUTHORIZED/CAPTURED 预授权将被释放）"
            rules={[
              { required: true, type: "number", min: 1, max: 365, message: "请输入 1-365 之间的天数" },
            ]}
          >
            <InputNumber min={1} max={365} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}