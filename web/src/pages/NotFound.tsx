import { Button, Result } from "antd";
import { useNavigate } from "react-router-dom";

/**
 * 应用 404 兜底页（M34c 升级统一版）。
 *
 * 设计要点：
 * - 浅灰渐变背景（`#f5f7fa → #ffffff`），与 Login 三段蓝渐变形成对比（404 是次要页）
 * - antd `Result status="404"` 标准视觉
 * - 单一 "返回经营概览" primary 按钮 → /dashboard
 * - 不挂任何图标（保持简洁）
 *
 * 路由挂载：App.tsx 的 `path: "*"` 路由直接指向本组件，无需调整。
 */
export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%)",
      }}
    >
      <Result
        status="404"
        title="404"
        subTitle="抱歉，您访问的页面不存在。"
        extra={
          <Button type="primary" size="large" onClick={() => navigate("/dashboard")}>
            返回经营概览
          </Button>
        }
      />
    </div>
  );
}
