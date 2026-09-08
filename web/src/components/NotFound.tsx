import { Button, Result } from "antd";
import { useNavigate } from "react-router-dom";

/**
 * M34a: 兜底 404 组件（components/）。
 *
 * 注：项目当前 404 路由仍由 `pages/NotFound.tsx` 承担（见 web/src/App.tsx）。
 * 本组件作为可复用的"应用级 404 兜底"模块独立交付，待 M34c 阶段统一迁移挂载点。
 *
 * 设计要点：
 * - 浅灰渐变背景（与 colorBgLayout token #f5f7fa 同色系）
 * - antd `Result status="404"` 标准视觉
 * - "返回经营概览"主按钮 → /dashboard
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
          <Button
            type="primary"
            size="large"
            onClick={() => navigate("/dashboard")}
          >
            返回经营概览
          </Button>
        }
      />
    </div>
  );
}
