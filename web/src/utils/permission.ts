// 权限与会话操作员工具（M32.18 T05）：
// 登录/刷新时由 Login.tsx 与 http.ts 落 localStorage；组件用 useCan / currentOperator 做按钮级 RBAC。
// 引用方：押金页等需要按权限码门控按钮的页面。

// ⚠️ 前端常量名（大写下划线）与后端真实权限码（小写点分）不同。
// 后端权限码以 app/services/permissions.py 为唯一真值来源，本表逐条对齐，**禁止使用字符串变换归一化**
// （例如 NIGHT_AUDIT_RUN → "night_audit.run"，下划线保留；若用 toLowerCase().replace(/_/g,".") 会变成
// "night.audit.run" 从而与后端 night_audit.run 失配）。一律显式映射。
export const PERM = {
  PRICE_EDIT: "price.edit",
  BOOKING_CANCEL: "booking.cancel",
  BILL_REFUND: "billing.refund",
  BILL_ADJUST: "billing.adjust",
  BILL_DISCOUNT: "billing.discount",
  NIGHT_AUDIT_RUN: "night_audit.run", // ← 注意：下划线保留，不是 night.audit.run
  AUDIT_VIEW: "audit.view",
  USER_MANAGE: "user.manage",
  ROLE_MANAGE: "role.manage",
  FNB_MANAGE: "fnb.manage",
  DEPOSIT_MANAGE: "deposit.manage",
  DEPOSIT_REFUND: "deposit.refund",
  OTA_MANAGE: "ota.manage",
  RATE_EDIT: "rate.edit",
  INVOICE_MANAGE: "invoice.manage",
  BLACKLIST_MANAGE: "blacklist.manage",
  COUPON_MANAGE: "coupon.manage",
  BREAKFAST_MANAGE: "breakfast.manage",
} as const;

const LS_PERMS = "pms_permissions";
const LS_USER = "pms_user";

export function setPermissions(p: string[]): void {
  localStorage.setItem(LS_PERMS, JSON.stringify(p));
}

export function getPermissions(): string[] {
  try {
    return JSON.parse(localStorage.getItem(LS_PERMS) || "[]");
  } catch {
    return [];
  }
}

/** 是否拥有某权限码。
 * 兼容两种传入方式：
 *  - 前端常量名（如 "DEPOSIT_MANAGE"）→ 经 PERM 表映射到后端点分码；
 *  - 直接传后端点分码（如 "deposit.manage"）→ 兜底直接匹配，成本为零。
 * 权限在会话内基本不变，读 localStorage 即可。 */
export function useCan(perm: string): boolean {
  const want = (PERM as Record<string, string>)[perm] ?? perm;
  const have = getPermissions();
  return have.includes(want) || have.includes(perm);
}

/** 当前操作员标识：登录显示名优先，回退 front_desk（对齐后端 DepositIn.operator 默认） */
export function currentOperator(): string {
  return localStorage.getItem(LS_USER) || "front_desk";
}
