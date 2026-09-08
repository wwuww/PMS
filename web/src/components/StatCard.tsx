import type { CSSProperties, ReactNode } from "react";
import "../styles/stat-card.css";

/**
 * 共享数据卡（M33b 抽共享版本）。
 * - 顶部 3px 渐变色条（accent 色 → 透明）
 * - 30px 数字 + tabular-nums
 * - 悬停浮起 -2px + 阴影加深
 * - 边框悬停变 accent 色
 * - 灰底 #f5f7fa 图标（避免 color-mix 兼容性）
 *
 * 用法：
 *   <StatCard label="出租率" value={75.4} suffix="%" accent="#1677ff" icon={<TeamOutlined />} />
 *   <StatCard label="营业日期" value="2026-09-08" accent="#722ed1" />
 */
export default function StatCard({
  label,
  value,
  suffix,
  sub,
  accent = "#1677ff",
  icon,
}: {
  label: string;
  value: ReactNode;
  suffix?: string;
  sub?: string;
  accent?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="stat-card" style={{ "--stat-accent": accent } as CSSProperties}>
      <span className="stat-card-bar" />
      <div className="stat-card-top">
        {icon && <span className="stat-card-icon">{icon}</span>}
        <span className="stat-card-label">{label}</span>
      </div>
      <div className="stat-card-value">
        {value}
        {suffix && <span className="stat-card-suffix">{suffix}</span>}
      </div>
      {sub && <div className="stat-card-sub">{sub}</div>}
    </div>
  );
}