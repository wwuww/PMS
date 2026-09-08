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
  PARTIALLY_REFUNDED: { label: "部分退款", color: "orange" },
  RELEASED: { label: "已释放", color: "default" },
  VOID: { label: "已作废", color: "red" },
  FORFEITED: { label: "已没收", color: "volcano" },
  EXPIRED: { label: "已过期", color: "gray" },
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
 * 单一真值来源：某押金在某状态下某动作是否可用。
 * 权限在调用处另行与 useCan 叠加（如 apply 需要 DEPOSIT_MANAGE）。
 * - apply   有可用余额 + HELD/PARTIALLY_APPLIED
 * - refund  有可用余额 + HELD/PARTIALLY_APPLIED/APPLIED/PARTIALLY_REFUNDED
 * - release 仅 PREAUTH + applied==0 + HELD/PARTIALLY_APPLIED
 * - void    仅 DEPOSIT + applied==0 + HELD + 24h 内
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
      return avail && (d.status === "HELD" || d.status === "PARTIALLY_APPLIED");
    case "refund":
      return (
        avail &&
        (d.status === "HELD" ||
          d.status === "PARTIALLY_APPLIED" ||
          d.status === "APPLIED" ||
          d.status === "PARTIALLY_REFUNDED")
      );
    case "release":
      return isPreauth && appliedZero && (d.status === "HELD" || d.status === "PARTIALLY_APPLIED");
    case "void":
      return isDeposit && appliedZero && d.status === "HELD" && within24h;
    default:
      return false;
  }
}
