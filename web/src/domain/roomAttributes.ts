// 房间属性字典（批次④）：与后端 room attribute_code 取值保持一致。
// 用于房间管理页的属性多选、属性标签渲染与排房偏好匹配。

/** 单个房间属性选项（antd Select options 兼容结构）。 */
export interface AttributeOption {
  label: string;
  value: string;
}

/** 全部可选房间属性（顺序即下拉展示顺序）。 */
export const ATTRIBUTE_OPTIONS: AttributeOption[] = [
  { label: "无烟房", value: "SMOKE_FREE" },
  { label: "大床", value: "BIG_BED" },
  { label: "双床", value: "TWIN_BED" },
  { label: "有窗", value: "WINDOW" },
  { label: "无窗", value: "NO_WINDOW" },
  { label: "高层", value: "HIGH_FLOOR" },
  { label: "低层", value: "LOW_FLOOR" },
  { label: "安静", value: "QUIET" },
  { label: "近电梯", value: "NEAR_ELEVATOR" },
  { label: "近楼梯", value: "NEAR_STAIRS" },
  { label: "无障碍", value: "ACCESSIBLE" },
];

/** code → 中文标签映射（属性列渲染用）。 */
export const ATTRIBUTE_LABELS: Record<string, string> = ATTRIBUTE_OPTIONS.reduce(
  (acc: Record<string, string>, item: AttributeOption) => {
    acc[item.value] = item.label;
    return acc;
  },
  {}
);

/**
 * 取属性中文名；未知 code 原样返回（后端扩展新属性时不至于显示空白）。
 * @param code 属性编码，如 SMOKE_FREE
 */
export function attributeLabel(code?: string | null): string {
  if (!code) return "—";
  return ATTRIBUTE_LABELS[code] ?? code;
}
