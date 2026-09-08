// 权限与会话操作员工具（M32.18 T05）：
// 登录/刷新时由 Login.tsx 与 http.ts 落 localStorage；组件用 useCan / currentOperator 做按钮级 RBAC。
// 引用方：押金页等需要按权限码门控按钮的页面。

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

/** 是否拥有某权限码（权限在会话内基本不变，读 localStorage 即可） */
export function useCan(perm: string): boolean {
  return getPermissions().includes(perm);
}

/** 当前操作员标识：登录显示名优先，回退 front_desk（对齐后端 DepositIn.operator 默认） */
export function currentOperator(): string {
  return localStorage.getItem(LS_USER) || "front_desk";
}
