// 金额与比率格式化工具（金额单位统一为「分」）

export const fmtCents = (c: number): string =>
  `¥${(c / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

// 基点（bps）转百分比，1 bps = 0.01%
export const fmtBps = (bps: number): string => `${(bps / 100).toFixed(1)}%`;

export const fmtInt = (n: number | null | undefined): string =>
  n == null ? "—" : n.toLocaleString("zh-CN");

// 元 → 分（押金/支付输入框提交用；提交时一律 Math.round(yuan*100)）
export const yuanToCents = (y: number): number => Math.round(y * 100);
