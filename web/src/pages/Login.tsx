import { useState } from "react";
import { Button, Card, Form, Input, Typography, message } from "antd";
import {
  LockOutlined,
  UserOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useTenant } from "../store/tenant";
import { login } from "../api/endpoints";
import { setToken, setRefreshToken } from "../api/http";

const { Title, Text } = Typography;

const STATUS_TEXT: Record<string, string> = {
  locked: "账号已锁定",
  bad_credentials: "用户名或密码错误",
  disabled: "账号已禁用",
  not_found: "账号不存在",
};

export default function Login() {
  const { tenantCode } = useTenant();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const res = await login(tenantCode, {
        username: values.username,
        password: values.password,
      });
      if (res.status !== "ok" || !res.token) {
        message.error(STATUS_TEXT[res.status] || "登录失败");
        return;
      }
      setToken(res.token);
      setRefreshToken(res.refresh_token); // M18-2：静默续期凭据
      localStorage.setItem("pms_user", res.display_name || res.username);
      // M32.18 T05：把有效权限落 localStorage（key 与 utils/permission.ts LS_PERMS 一致），供 useCan 做按钮级 RBAC
      localStorage.setItem("pms_permissions", JSON.stringify(res.permissions ?? []));
      message.success(`欢迎，${res.display_name || res.username}`);
      navigate("/dashboard");
    } catch (e: any) {
      message.error(e?.message || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background:
          "linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #1e40af 100%)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* 背景装饰圆：右上 */}
      <div
        style={{
          position: "absolute",
          top: "-10%",
          right: "-5%",
          width: 400,
          height: 400,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />
      {/* 背景装饰圆：左下 */}
      <div
        style={{
          position: "absolute",
          bottom: "-15%",
          left: "-8%",
          width: 500,
          height: 500,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(125,211,252,0.10) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />

      <Card
        style={{
          width: 400,
          borderRadius: 16,
          boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
          position: "relative",
          zIndex: 1,
        }}
        bordered={false}
      >
        {/* 品牌区：渐变方块 logo + 主标 + 副标 */}
        <div style={{ textAlign: "center", marginBottom: 28, paddingTop: 8 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 56,
              height: 56,
              borderRadius: 14,
              background:
                "linear-gradient(135deg, #1677ff 0%, #69b1ff 100%)",
              boxShadow: "0 8px 20px rgba(22,119,255,0.4)",
              marginBottom: 16,
            }}
          >
            <SafetyCertificateOutlined style={{ fontSize: 28, color: "#fff" }} />
          </div>
          <Title
            level={3}
            style={{
              margin: 0,
              marginBottom: 6,
              fontWeight: 700,
              letterSpacing: 0.5,
            }}
          >
            PMS Cloud
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            酒店集团经营中台 · 多门店多渠道一体化
          </Text>
        </div>

        {/* 表单（保持原 onFinish 逻辑） */}
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              size="large"
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" block size="large" loading={loading}>
            登录
          </Button>
        </Form>

        {/* 底部：分割线 + 当前租户 + 默认账号 */}
        <div
          style={{
            marginTop: 16,
            paddingTop: 12,
            borderTop: "1px solid #f0f2f5",
            textAlign: "center",
          }}
        >
          <Text type="secondary" style={{ fontSize: 12 }}>
            当前租户：<Text code style={{ fontSize: 11 }}>{tenantCode}</Text>
            <br />
            默认账号 admin / admin123
          </Text>
        </div>
      </Card>
    </div>
  );
}
