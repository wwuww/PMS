// 押金模块共享元数据：中文标签、状态配色、流水动作映射、状态×动作可用性矩阵
// （与后端 DepositService 不变式 I1–I7 对齐）。页面与子组件均从此处导入，避免重复定义。
import type { Deposit, DepositKind, DepositMethod, DepositStatus } from "../../api/types";

export const KIND_LABELS: Record<DepositKind, string> = {
  DEPOSIT: "押金",
  PREAUTH: "预授权",
};

export const METHOD_LABELS: Record<DepositMethod, string> = {
  CASH: "现金",
  WECHAT: "微信",
  ALIPAY: "支付宝",
  UNIONPAY: "银联",
  STORE_VALUE: "储值",
};

export const STATUS_META: Record<DepositStatus, { label: string; color: string }> = {
  HELD: { label: "冻结中", color: "processing" },
  APPLIED: { label: "已冲抵", color: "green" },
  PARTIALLY_APPLIED: { label: "部分冲抵", color: "cyan" },
  REFUNDED: { label: "已退款", color: "default" },
  RELEASED: { label: "已释放", color: "default" },
  VOID: { label: "已作废", color: "red" },
  FORFEITED: { label: "已没收", color: "volcano" },
  AUTHORIZED: { label: "已授权", color: "gold" },
  CAPTURED: { label: "已转实收", color: "cyan" },
};

export const ACTION_LABELS: Record<string, string> = {
  CREATE: "创建",
  HOLD: "冻结",
  APPLY: "冲抵",
  REFUND: "退款",
  RELEASE: "释放",
  VOID: "作废",
  EXPIRE: "过期",
  FORFEIT: "没收",
  CAPTURE: "预授权转实收",
};

export type DepositActionType = "apply" | "refund" | "release" | "void";

/**
 * 可退状态集合：后端 refund（deposit_service.py 第 356 行）的守卫是
 * `if d.status in _TERMINAL: raise`，而 `_TERMINAL`（第 45-51 行）=
 * {APPLIED, REFUNDED, FORFEITED, VOID, RELEASED}。
 * 故可退状态 = 全部 9 个状态 − _TERMINAL = HELD / PARTIALLY_APPLIED / AUTHORIZED / CAPTURED。
 * 这里显式枚举报备未知状态（宁可禁用按钮，也不放行后端会拒绝的操作）。
 */
const REFUNDABLE_STATUSES: ReadonlySet<DepositStatus> = new Set<DepositStatus>([
  "HELD",
  "PARTIALLY_APPLIED",
  "AUTHORIZED",
  "CAPTURED",
]);

/**
 * 可释放状态集合：后端 release（deposit_service.py 第 476-487 行）只拒绝
 * `RELEASED` 与 `APPLIED` 两种状态；这里收敛为「非终态」——比后端更严格
 * （不释放已退款/已没收/已作废的单据），只会禁用按钮、不会放行后端会拒绝的操作。
 * 关键：必须包含 AUTHORIZED —— 新建预授权的初态（deposit_service.py 第 137-142 行），
 * 缺失它会导致刚刷的预授权永远点不了「释放」。
 */
const RELEASABLE_STATUSES: ReadonlySet<DepositStatus> = new Set<DepositStatus>([
  "AUTHORIZED",
  "HELD",
  "CAPTURED",
  "PARTIALLY_APPLIED",
]);

/**
 * 可冲抵「类型 × 状态」池：后端 deposit_service.py 第 53-58 行 `_APPLICABLE_POOL`，
 * apply（第 261 行）要求 (kind, status) 精确命中。押金与预授权规则不同：
 * 实收押金 HELD/PARTIALLY_APPLIED 可冲抵；预授权必须先 CAPTURED 才可冲抵。
 */
const APPLICABLE_POOL: ReadonlySet<string> = new Set<string>([
  "DEPOSIT:HELD",
  "DEPOSIT:PARTIALLY_APPLIED",
  "PREAUTH:CAPTURED",
]);

/**
 * 单一真值来源：某押金在某状态下某动作是否可用。
 * 权限在调用处另行与 useCan 叠加（如 apply 需要 DEPOSIT_MANAGE）。
 * 规则逐条对应后端 DepositService 守卫：
 * - apply   可用余额 > 0 + (kind,status) ∈ _APPLICABLE_POOL（deposit_service.py:53-58, 261）
 * - refund  可用余额 > 0 + status ∉ _TERMINAL（deposit_service.py:45-51, 356）
 * - release 仅 PREAUTH + applied==0 + status ∈ 非终态（deposit_service.py:476-487）
 * - void    仅 DEPOSIT + applied==0 + HELD + 24h 内（deposit_service.py:424-435）
 */
export function canAct(d: Deposit, action: DepositActionType): boolean {
  const avail = d.available_cents > 0;
  const appliedZero = d.applied_cents === 0;
  const isPreauth = d.kind === "PREAUTH";
  const isDeposit = d.kind === "DEPOSIT";
  const within24h =
    !!d.created_at && Date.now() - new Date(d.created_at).getTime() <= 24 * 3600 * 1000;

  switch (action) {
    case "apply":
      return avail && APPLICABLE_POOL.has(`${d.kind}:${d.status}`);
    case "refund":
      return avail && REFUNDABLE_STATUSES.has(d.status);
    case "release":
      return isPreauth && appliedZero && RELEASABLE_STATUSES.has(d.status);
    case "void":
      return isDeposit && appliedZero && d.status === "HELD" && within24h;
    default:
      return false;
  }
}
