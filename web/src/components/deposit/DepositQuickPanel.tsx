// 入住登记页「押金 / 预授权」快捷面板（M36 接线）：
// 替换 CheckInRegister 原先写死的四个禁用控件，接后端已上线的押金能力。
// 复用既有资产：api/endpoints 的 listDepositsByBooking / createDeposit / releaseDeposit、
// components/deposit/meta.ts 的标签与状态×动作矩阵、DepositDetailDrawer 详情抽屉。
// 复杂动作（冲抵 / 退款 / 作废）不在本面板重复实现，统一跳转押金管理页。
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  App,
  Button,
  InputNumber,
  Input,
  Popconfirm,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { createDeposit, listDepositsByBooking, releaseDeposit } from "../../api/endpoints";
import type { Deposit, DepositIn, DepositKind, DepositMethod } from "../../api/types";
import { useTenant } from "../../store/tenant";
import { yuanToCents } from "../../utils/format";
// 必须带 .tsx 后缀：无后缀会优先解析到 format.ts（纯字符串工具），取不到组件。
import { CellAmount } from "../../utils/format.tsx";
import { currentOperator, useCan } from "../../utils/permission";
import DepositDetailDrawer from "./DepositDetailDrawer";
import { KIND_LABELS, METHOD_LABELS, STATUS_META, canAct } from "./meta";

interface Props {
  /** 当前登记单对应的预订 ID；散客尚未办理入住时为 null（此时只提示、不请求） */
  bookingId: number | null;
  /** 房号（开押时带入，便于收银/夜审按房查询） */
  roomNo?: string | null;
}

const KIND_OPTIONS: { value: DepositKind; label: string }[] = [
  { value: "DEPOSIT", label: "收押金" },
  { value: "PREAUTH", label: "刷预授权" },
];

// 方式选项从 meta.METHOD_LABELS 派生，避免与 DepositForm 各写一份而漂移
const METHOD_OPTIONS: { value: DepositMethod; label: string }[] = (
  Object.entries(METHOD_LABELS) as [DepositMethod, string][]
).map(([value, label]) => ({ value, label }));

/** 汇总口径：已作废（VOID）不计入合计 */
interface Totals {
  depositCents: number;
  preauthCents: number;
  availableCents: number;
  currency: string;
}

const LABEL_STYLE: React.CSSProperties = { marginBottom: 2, fontSize: 12, color: "#8a919c" };

export default function DepositQuickPanel({ bookingId, roomNo = null }: Props) {
  const { tenantCode, hotelId } = useTenant();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const canManage = useCan("DEPOSIT_MANAGE");

  const [rows, setRows] = useState<Deposit[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // 快捷开押表单（轻量内联，无需 antd Form 的校验编排）
  const [kind, setKind] = useState<DepositKind>("DEPOSIT");
  const [method, setMethod] = useState<DepositMethod>("CASH");
  const [amount, setAmount] = useState<number | null>(null);
  const [refNo, setRefNo] = useState<string>("");

  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const fetchRows = useCallback(async () => {
    if (!bookingId || !canManage) {
      setRows([]);
      return;
    }
    setLoading(true);
    try {
      const list = await listDepositsByBooking(tenantCode, bookingId);
      setRows(list);
    } catch (e: unknown) {
      message.error((e as Error).message || "加载押金列表失败");
      setRows([]);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, bookingId, canManage]);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  const totals = useMemo<Totals>(() => {
    const t: Totals = { depositCents: 0, preauthCents: 0, availableCents: 0, currency: "CNY" };
    for (const d of rows) {
      if (d.status === "VOID") continue;
      if (d.kind === "DEPOSIT") t.depositCents += d.amount_cents;
      else t.preauthCents += d.amount_cents;
      t.availableCents += d.available_cents;
      if (d.currency) t.currency = d.currency;
    }
    return t;
  }, [rows]);

  const submit = async () => {
    if (!bookingId) {
      message.warning("该登记单尚未生成，请先办理入住后再收押金");
      return;
    }
    if (!hotelId) {
      message.warning("请先在右上角选择门店");
      return;
    }
    if (amount == null || amount <= 0) {
      message.warning("请输入大于 0 的金额");
      return;
    }
    setSubmitting(true);
    try {
      const body: DepositIn = {
        hotel_id: Number(hotelId),
        kind,
        method,
        amount: yuanToCents(amount),
        booking_id: bookingId,
        room_no: roomNo?.trim() || null,
        ref_no: refNo.trim() || null,
        operator: currentOperator(),
        note: null,
      };
      const d = await createDeposit(tenantCode, body);
      message.success(`已开${KIND_LABELS[kind]}单 ${d.deposit_no}`);
      setAmount(null);
      setRefNo("");
      await fetchRows();
    } catch (e: unknown) {
      message.error((e as Error).message || "开押失败");
    } finally {
      setSubmitting(false);
    }
  };

  const doRelease = async (row: Deposit) => {
    try {
      await releaseDeposit(tenantCode, row.id, {
        operator: currentOperator(),
        cause: "MANUAL",
        expected_version: row.version,
      });
      message.success(`已释放预授权 ${row.deposit_no}`);
      await fetchRows();
    } catch (e: unknown) {
      const msg = (e as Error).message || "释放失败";
      message.error(/version|冲突|已被/.test(msg) ? "数据已被修改，请刷新重试" : msg);
      await fetchRows();
    }
  };

  const columns: ColumnsType<Deposit> = [
    { title: "押金单号", dataIndex: "deposit_no", width: 150 },
    {
      title: "类型",
      dataIndex: "kind",
      width: 78,
      render: (v: DepositKind) => <Tag>{KIND_LABELS[v] ?? v}</Tag>,
    },
    {
      title: "方式",
      dataIndex: "method",
      width: 74,
      render: (v: DepositMethod) => <Tag color="blue">{METHOD_LABELS[v] ?? v}</Tag>,
    },
    {
      title: "金额",
      dataIndex: "amount_cents",
      width: 100,
      className: "text-right",
      render: (v: number) => <CellAmount value={v} />,
    },
    {
      title: "已冲抵",
      dataIndex: "applied_cents",
      width: 100,
      className: "text-right",
      render: (v: number) => <CellAmount value={v} />,
    },
    {
      title: "可用余额",
      dataIndex: "available_cents",
      width: 100,
      className: "text-right",
      render: (v: number) => (
        <Typography.Text strong>
          <CellAmount value={v} />
        </Typography.Text>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 88,
      render: (v: Deposit["status"]) => {
        const m = STATUS_META[v];
        return m ? <Tag color={m.color}>{m.label}</Tag> : <Tag>{v}</Tag>;
      },
    },
    {
      title: "操作",
      key: "action",
      width: 128,
      fixed: "right",
      render: (_: unknown, r: Deposit) => (
        <Space size={4}>
          <Button
            size="small"
            onClick={() => {
              setDrawerId(r.id);
              setDrawerOpen(true);
            }}
          >
            查看
          </Button>
          <Popconfirm
            title={`确认释放预授权 ${r.deposit_no}？`}
            okText="释放"
            cancelText="取消"
            onConfirm={() => doRelease(r)}
            disabled={!canManage || !canAct(r, "release")}
          >
            <Button size="small" disabled={!canManage || !canAct(r, "release")}>
              释放
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const disabledAdd = !canManage || !bookingId || submitting;

  return (
    <div className="pms-panel" style={{ marginTop: 8, padding: "10px 12px" }}>
      {/* 标题行：合计概要 + 入口 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span
          style={{ width: 3, height: 14, background: "#1677ff", borderRadius: 2, display: "inline-block" }}
        />
        <span style={{ fontWeight: 600, fontSize: 13.5, color: "#1f2329" }}>押金 / 预授权</span>
        <div style={{ flex: 1 }} />
        <Button size="small" onClick={fetchRows} loading={loading} disabled={!bookingId || !canManage}>
          刷新
        </Button>
        <Button size="small" onClick={() => navigate("/deposits")}>
          押金管理
        </Button>
      </div>

      {/* 合计四联（沿用原押金行的四列视觉位置） */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px 10px" }}>
        {/* CellAmount 自带 .cell-amount（等宽数字 + 正负配色）；
            .text-right / .is-numeric 仅对表格单元格生效，此处不重复挂无效类名 */}
        <div>
          <div style={LABEL_STYLE}>本人押金</div>
          <div>
            <CellAmount value={totals.depositCents} />
          </div>
        </div>
        <div>
          <div style={LABEL_STYLE}>授权金额</div>
          <div>
            <CellAmount value={totals.preauthCents} />
          </div>
        </div>
        <div>
          <div style={LABEL_STYLE}>币种</div>
          <div>{totals.currency}</div>
        </div>
        <div>
          <div style={LABEL_STYLE}>可用余额</div>
          <div>
            <Typography.Text strong>
              <CellAmount value={totals.availableCents} />
            </Typography.Text>
          </div>
        </div>
      </div>

      {/* 快捷开押行 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 8,
          flexWrap: "wrap",
        }}
      >
        <Radio.Group
          size="small"
          optionType="button"
          buttonStyle="solid"
          options={KIND_OPTIONS}
          value={kind}
          disabled={disabledAdd}
          onChange={(e) => setKind(e.target.value as DepositKind)}
        />
        <Select<DepositMethod>
          size="small"
          style={{ width: 96 }}
          value={method}
          disabled={disabledAdd}
          onChange={(v) => setMethod(v)}
          options={METHOD_OPTIONS}
        />
        <InputNumber
          size="small"
          style={{ width: 132 }}
          addonBefore="¥"
          min={0.01}
          precision={2}
          placeholder="0.00"
          value={amount}
          disabled={disabledAdd}
          onChange={(v) => setAmount(v)}
          onPressEnter={submit}
        />
        {kind === "PREAUTH" && (
          <Input
            size="small"
            style={{ width: 150 }}
            placeholder="预授权号（可选）"
            maxLength={64}
            value={refNo}
            disabled={disabledAdd}
            onChange={(e) => setRefNo(e.target.value)}
            onPressEnter={submit}
          />
        )}
        <Button size="small" type="primary" loading={submitting} disabled={disabledAdd} onClick={submit}>
          {kind === "DEPOSIT" ? "收押金" : "冻结预授权"}
        </Button>
        {!bookingId && (
          <Typography.Text type="warning" style={{ fontSize: 12 }}>
            该登记单尚未生成，请先办理入住后再收押金 / 刷预授权
          </Typography.Text>
        )}
        {bookingId && !canManage && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            当前账号无押金管理权限（DEPOSIT_MANAGE）
          </Typography.Text>
        )}
      </div>

      {/* 该单押金明细 */}
      {bookingId && canManage && (
        <Table<Deposit>
          style={{ marginTop: 8 }}
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={rows}
          columns={columns}
          pagination={false}
          scroll={{ x: 840 }}
          locale={{ emptyText: "该登记单暂无押金 / 预授权记录" }}
        />
      )}

      <DepositDetailDrawer
        open={drawerOpen}
        depositId={drawerId}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
