import type { CSSProperties, ReactNode } from "react";

/**
 * 玻璃拟态数据卡片（配合 .glass-band 渐变底带使用）。
 * label：指标名；value：数值；suffix：单位；icon：右上角小图标（可省）；sub：补充说明（可省）。
 */
export default function GlassStatCard({
  label,
  value,
  suffix,
  icon,
  sub,
  accent = "#1677ff",
}: {
  label: string;
  value: ReactNode;
  suffix?: string;
  icon?: ReactNode;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="glass-card" style={{ "--accent": accent } as CSSProperties}>
      <div className="glass-card-top">
        <span className="glass-card-label">{label}</span>
        {icon && <span className="glass-card-icon">{icon}</span>}
      </div>
      <div className="glass-card-value">
        {value}
        {suffix && <span className="glass-card-suffix">{suffix}</span>}
      </div>
      {sub && <div className="glass-card-sub">{sub}</div>}
    </div>
  );
}
