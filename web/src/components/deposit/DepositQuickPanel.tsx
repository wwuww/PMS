// 入住登记页「押金 / 预授权」快捷面板（M36 接线）：
// 替换 CheckInRegister 原先写死的四个禁用控件，接后端已上线的押金能力。
// 复用既有资产：api/endpoints 的 listDepositsByBooking / createDeposit / releaseDeposit /
// applyDeposit / refundDeposit / voidDeposit、components/deposit/meta.ts 的标签与状态×动作矩阵、
// DepositDetailDrawer 详情抽屉。
// 查看 / 请款 / 释放 / 冲抵 / 退款 / 作废六个动作均在本面板内完成（含金额与原因采集弹窗），
// 仅批量操作、超期清理等后台维护场景才需跳转押金管理页。
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  App,
  Button,
  InputNumber,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  applyDeposit,
  captureDeposit,
  createDeposit,
  listDepositsByBooking,
  refundDeposit,
  releaseDeposit,
  voidDeposit,
} from "../../api/endpoints";
import type {
  Deposit,
  DepositApplyIn,
  DepositCaptureIn,
  DepositIn,
  DepositKind,
  DepositMethod,
  DepositRefundIn,
  DepositVoidIn,
} from "../../api/types";
import { useTenant } from "../../store/tenant";
import { yuanToCents } from "../../utils/format";
// 必须带 .tsx 后缀：无后缀会优先解析到 format.ts（纯字符串工具），取不到组件。
import { CellAmount } from "../../utils/format.tsx";
import { PERM, currentOperator, useCan } from "../../utils/permission";
import DepositDetailDrawer from "./DepositDetailDrawer";
import type { DepositActionType } from "./meta";
import { KIND_LABELS, METHOD_LABELS, STATUS_META, canAct } from "./meta";

interface Props {
  /** 当前登记单对应的预订 ID；散客尚未办理入住时为 null（此时只提示、不请求）
   *  ⚠️ 必须是 string：18 位雪花 ID 经 JS number 中转再拼 URL/JSON 会被截断成 17 位有效数字。 */
  bookingId: string | null;
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

/** 需要二次采集（金额 / 原因）的动作，统一走一个弹窗 */
type QuickActionKind = Extract<DepositActionType, "apply" | "refund" | "void" | "capture">;

/** 走金额采集的动作（作废只采集原因） */
const NEEDS_AMOUNT: ReadonlySet<QuickActionKind> = new Set<QuickActionKind>([
  "apply",
  "refund",
  "capture",
]);

const ACT_TITLE: Record<QuickActionKind, string> = {
  apply: "冲抵押金到账单",
  refund: "押金原路退款",
  void: "作废押金单",
  capture: "预授权请款",
};

const ACT_CONFIRM_TIP: Record<QuickActionKind, string> = {
  apply: "冲抵后押金可用余额将相应减少，账单余额同步冲减，请核对金额。",
  refund: "退款一经提交不可撤销，金额将按原支付方式退回，请核对金额。",
  void: "作废后该押金单不可再用于冲抵 / 退款，且 24 小时后不再允许作废。",
  capture:
    "请款后将真正收取该笔款项，不可再释放，如需退回请走退款；请款成功后方可冲抵到账单。",
};

export default function DepositQuickPanel({ bookingId, roomNo = null }: Props) {
  const { tenantCode, hotelId } = useTenant();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const canManage = useCan(PERM.DEPOSIT_MANAGE);

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

  // 请款 / 冲抵 / 退款 / 作废的采集态（单个弹窗按 kind 切换展示字段）
  const [actRow, setActRow] = useState<Deposit | null>(null);
  const [actKind, setActKind] = useState<QuickActionKind | null>(null);
  const [actAmount, setActAmount] = useState<number | null>(null);
  const [actNote, setActNote] = useState<string>("");
  const [actReason, setActReason] = useState<string>("");
  const [actSubmitting, setActSubmitting] = useState(false);

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
        hotel_id: hotelId,
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

  /**
   * 打开金额/原因采集弹窗。
   * 冲抵 / 退款：金额默认值取「全额可用余额」，与押金管理页 Deposits.tsx 的 openAction 保持一致，
   *   收银场景中「把剩下的押金一次性结掉」是绝大多数操作，只需改数、无需清空调输入框。
   * 请款（capture）：金额上界与默认值取「全额授权额度」而非可用余额——请款针对的是被冻结的
   *   授权额度本身（AUTHORIZED 状态下二者通常相等），且请款的常见场景就是全额收取。
   */
  const openAct = (row: Deposit, kind: QuickActionKind) => {
    setActRow(row);
    setActKind(kind);
    setActAmount(
      Number(
        ((kind === "capture" ? row.amount_cents : row.available_cents) / 100).toFixed(2)
      )
    );
    setActNote("");
    setActReason("");
  };

  const closeAct = () => {
    setActKind(null);
    setActRow(null);
    setActAmount(null);
    setActNote("");
    setActReason("");
  };

  /** 提交冲抵 / 退款 / 作废；错误与刷新处理严格沿用 doRelease 的模式 */
  const submitAct = async () => {
    if (!actRow || !actKind) return;
    if (!canAct(actRow, actKind)) {
      message.warning("该押金单当前状态不允许此操作，请刷新后重试");
      closeAct();
      await fetchRows();
      return;
    }
    const row = actRow;
    const needsAmount = NEEDS_AMOUNT.has(actKind);

    let amountCents = 0;
    if (needsAmount) {
      amountCents = actAmount == null ? 0 : yuanToCents(actAmount);
      if (amountCents < 1) {
        message.warning("请输入大于 0 的金额");
        return;
      }
      // 冲抵 / 退款的上界是可用余额；请款的上界是授权额度（见 openAct 注释）
      const capCents = actKind === "capture" ? row.amount_cents : row.available_cents;
      if (amountCents > capCents) {
        message.warning(`金额不能超过${actKind === "capture" ? "授权额度" : "可用余额"} ${(capCents / 100).toFixed(2)} 元`);
        return;
      }
    }
    // 退款必须留痕：后端 DepositService.refund 强校验 note，缺值会返回 DEPOSIT_REASON_REQUIRED
    if (actKind === "refund" && !actNote.trim()) {
      message.warning("请填写退款原因（退款为资金动作，强制审计留痕）");
      return;
    }

    setActSubmitting(true);
    try {
      if (actKind === "apply") {
        const body: DepositApplyIn = {
          amount: amountCents,
          target_bill_id: null,
          operator: currentOperator(),
          expected_version: row.version,
        };
        await applyDeposit(tenantCode, row.id, body);
        message.success(`已冲抵押金 ${row.deposit_no}`);
      } else if (actKind === "refund") {
        const body: DepositRefundIn = {
          amount: amountCents,
          operator: currentOperator(),
          note: actNote.trim(),
          expected_version: row.version,
        };
        await refundDeposit(tenantCode, row.id, body);
        message.success(`已退款 ${row.deposit_no}`);
      } else if (actKind === "capture") {
        const body: DepositCaptureIn = {
          amount: amountCents,
          operator: currentOperator(),
          expected_version: row.version,
        };
        await captureDeposit(tenantCode, row.id, body);
        message.success(`已请款 ${row.deposit_no}`);
      } else {
        const body: DepositVoidIn = {
          operator: currentOperator(),
          reason: actReason.trim() || null,
          expected_version: row.version,
        };
        await voidDeposit(tenantCode, row.id, body);
        message.success(`已作废押金单 ${row.deposit_no}`);
      }
      closeAct();
      await fetchRows();
    } catch (e: unknown) {
      const msg = (e as Error).message || "操作失败";
      message.error(/version|冲突|已被/.test(msg) ? "数据已被修改，请刷新重试" : msg);
      await fetchRows();
    } finally {
      setActSubmitting(false);
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
      width: 332,
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
          <Button
            size="small"
            disabled={!canManage || !canAct(r, "capture")}
            onClick={() => openAct(r, "capture")}
          >
            请款
          </Button>
          <Button
            size="small"
            disabled={!canManage || !canAct(r, "apply")}
            onClick={() => openAct(r, "apply")}
          >
            冲抵
          </Button>
          <Button
            size="small"
            disabled={!canManage || !canAct(r, "refund")}
            onClick={() => openAct(r, "refund")}
          >
            退款
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
          <Button
            size="small"
            danger
            disabled={!canManage || !canAct(r, "void")}
            onClick={() => openAct(r, "void")}
          >
            作废
          </Button>
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
          scroll={{ x: 1046 }}
          locale={{ emptyText: "该登记单暂无押金 / 预授权记录" }}
        />
      )}

      {/* 请款 / 冲抵 / 退款 / 作废 采集弹窗（相当于二次确认，提交前需核对金额与原因） */}
      <Modal
        title={actKind ? ACT_TITLE[actKind] : ""}
        open={!!actKind && !!actRow}
        onOk={submitAct}
        onCancel={closeAct}
        okText={actKind === "void" ? "确认作废" : "提交"}
        cancelText="取消"
        maskClosable={!actSubmitting}
        okButtonProps={{ loading: actSubmitting, danger: actKind === "void" }}
        cancelButtonProps={{ disabled: actSubmitting }}
      >
        {actRow && (actKind === "apply" || actKind === "refund") && (
          <div style={{ marginBottom: 10, fontSize: 13, color: "#5a626c" }}>
            押金单号：<strong>{actRow.deposit_no}</strong> · 可用余额：
            <Typography.Text strong>
              <CellAmount value={actRow.available_cents} />
            </Typography.Text>
          </div>
        )}
        {actRow && actKind === "capture" && (
          <div style={{ marginBottom: 10, fontSize: 13, color: "#5a626c" }}>
            押金单号：<strong>{actRow.deposit_no}</strong> · 授权额度：
            <Typography.Text strong>
              <CellAmount value={actRow.amount_cents} />
            </Typography.Text>
          </div>
        )}
        <div style={{ marginBottom: 12, fontSize: 12.5, color: "#8a919c" }}>
          {actKind ? ACT_CONFIRM_TIP[actKind] : null}
        </div>
        {(actKind === "apply" || actKind === "refund") && (
          <div style={{ marginBottom: 4, fontSize: 12, color: "#8a919c" }}>金额（元）</div>
        )}
        {(actKind === "apply" || actKind === "refund") && (
          <InputNumber
            size="small"
            style={{ width: "100%" }}
            addonBefore="¥"
            min={0.01}
            max={actRow ? Number((actRow.available_cents / 100).toFixed(2)) : undefined}
            precision={2}
            placeholder="0.00"
            value={actAmount}
            disabled={actSubmitting}
            onChange={(v) => setActAmount(v)}
            onPressEnter={submitAct}
          />
        )}
        {actRow && actKind === "capture" && (
          <div style={{ marginBottom: 4, fontSize: 12, color: "#8a919c" }}>
            请款金额（元，默认全额授权额度）
          </div>
        )}
        {actRow && actKind === "capture" && (
          <InputNumber
            size="small"
            style={{ width: "100%" }}
            addonBefore="¥"
            min={0.01}
            max={Number((actRow.amount_cents / 100).toFixed(2))}
            precision={2}
            placeholder="0.00"
            value={actAmount}
            disabled={actSubmitting}
            onChange={(v) => setActAmount(v)}
            onPressEnter={submitAct}
          />
        )}
        {actKind === "refund" && (
          <>
            <div style={{ margin: "10px 0 4px", fontSize: 12, color: "#8a919c" }}>
              退款原因（必填，写入审计流水）
            </div>
            <Input.TextArea
              rows={3}
              maxLength={255}
              placeholder="如：客人提前离店，押金原路退回"
              value={actNote}
              disabled={actSubmitting}
              onChange={(e) => setActNote(e.target.value)}
            />
          </>
        )}
        {actKind === "void" && (
          <>
            <div style={{ marginBottom: 4, fontSize: 12, color: "#8a919c" }}>作废原因（可选）</div>
            <Input.TextArea
              rows={3}
              maxLength={255}
              placeholder="如：录入金额有误，重新开押"
              value={actReason}
              disabled={actSubmitting}
              onChange={(e) => setActReason(e.target.value)}
            />
          </>
        )}
      </Modal>

      <DepositDetailDrawer
        open={drawerOpen}
        depositId={drawerId}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
