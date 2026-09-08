import { useState } from "react";
import { Button, Card, Form, Input, Typography, message } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
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
        background: "linear-gradient(135deg,#1f2a44,#3a4a6b)",
      }}
    >
      <Card style={{ width: 360 }} bordered>
        <div style={{ textAlign: "center", marginBottom: 20 }}>
          <Title level={3} style={{ marginBottom: 4 }}>
            PMS Cloud
          </Title>
          <Text type="secondary">酒店集团经营中台 · 登录</Text>
        </div>
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
        <div style={{ marginTop: 12, textAlign: "center" }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            当前租户：{tenantCode}（后端已强制会话鉴权，默认账号 admin / admin123）
          </Text>
        </div>
      </Card>
    </div>
  );
}
