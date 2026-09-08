import React from "react";
import { fmtBps, fmtCents, fmtInt } from "./format";

/**
 * 金额单元格：正数绿色、负数红色、零默认色（M35a 视觉统一）。
 *
 * 用法（数据页按需升级，替换 fmtCents）：
 *   // 之前：render: (v) => fmtCents(v)
 *   // 之后：render: (v) => <CellAmount value={v} />
 *
 * 说明：fmtCents 等 string 工具保持不变（向后兼容），本组件是可选升级路径。
 */
export function CellAmount({ value }: { value: number | null | undefined }): JSX.Element {
  const v = value ?? 0;
  const cls = v > 0 ? "cell-amount-positive" : v < 0 ? "cell-amount-negative" : "";
  return <span className={`cell-amount ${cls}`.trim()}>{fmtCents(v)}</span>;
}

/** 百分比（bps）单元格：正绿 / 负红。 */
export function CellPct({ value }: { value: number | null | undefined }): JSX.Element {
  const v = value ?? 0;
  const cls = v > 0 ? "cell-amount-positive" : v < 0 ? "cell-amount-negative" : "";
  return <span className={`cell-amount ${cls}`.trim()}>{fmtBps(v)}</span>;
}

/** 整数单元格：等宽数字、常规色（空值显示「—」）。 */
export function CellInt({ value }: { value: number | null | undefined }): JSX.Element {
  return <span className="cell-amount">{fmtInt(value)}</span>;
}
