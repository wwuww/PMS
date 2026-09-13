import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ApiOutlined,
  PlusOutlined,
  KeyOutlined,
  LinkOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import { PERM, useCan } from "../utils/permission";
import {
  listOpenApiApps,
  registerOpenApiApp,
  listOpenApiKeys,
  createOpenApiKey,
  revokeOpenApiKey,
  listOpenApiWebhooks,
  createOpenApiWebhook,
  testOpenApiWebhook,
} from "../api/endpoints";
import type {
  OpenApiApp,
  OpenApiKey,
  OpenApiWebhook,
  OpenApiKeyWithSecret,
  OpenApiWebhookTest,
} from "../api/types";

const { Title, Text, Paragraph } = Typography;

export default function OpenApi() {
  const { tenantCode } = useTenant();
  // 门控：开放平台管理（注册应用 / 签发密钥 / 注册 Webhook）仅管理员（user.manage）。
  // 后端这 5 个写操作已要求 user.manage，此处同步隐藏入口，避免"点了报 403"。
  const canManage = useCan(PERM.USER_MANAGE);
  const [apps, setApps] = useState<OpenApiApp[]>([]);
  const [loading, setLoading] = useState(false);
  const [showApp, setShowApp] = useState(false);
  const [appForm] = Form.useForm();

  // 密钥弹窗
  const [appKeys, setAppKeys] = useState<Record<string, OpenApiKey[]>>({});
  const [showKey, setShowKey] = useState(false);
  const [keyApp, setKeyApp] = useState<OpenApiApp | null>(null);
  const [keyForm] = Form.useForm();
  const [secret, setSecret] = useState<string | null>(null);

  // Webhook
  const [appHooks, setAppHooks] = useState<Record<string, OpenApiWebhook[]>>({});
  const [showHook, setShowHook] = useState(false);
  const [hookApp, setHookApp] = useState<OpenApiApp | null>(null);
  const [hookForm] = Form.useForm();

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setApps(await listOpenApiApps(tenantCode));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const handleRegister = async () => {
    const v = await appForm.validateFields();
    try {
      await registerOpenApiApp(tenantCode, {
        app_code: v.app_code,
        name: v.name,
        callback_url: v.callback_url || null,
        events_subscribed: v.events_subscribed || [],
      });
      message.success("已注册应用");
      setShowApp(false);
      appForm.resetFields();
      refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "注册失败");
    }
  };

  const openKeys = async (app: OpenApiApp) => {
    setKeyApp(app);
    setSecret(null);
    const keys = await listOpenApiKeys(tenantCode, app.id);
    setAppKeys((m) => ({ ...m, [app.id]: keys }));
    setShowKey(true);
  };

  const handleCreateKey = async () => {
    if (!keyApp) return;
    try {
      const res: OpenApiKeyWithSecret = await createOpenApiKey(tenantCode, keyApp.id);
      setSecret(res.secret);
      const keys = await listOpenApiKeys(tenantCode, keyApp.id);
      setAppKeys((m) => ({ ...m, [keyApp.id]: keys }));
      message.success("密钥已生成（明文仅展示一次）");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    }
  };

  const handleRevoke = async (appId: string, keyId: string) => {
    await revokeOpenApiKey(tenantCode, appId, keyId);
    const keys = await listOpenApiKeys(tenantCode, appId);
    setAppKeys((m) => ({ ...m, [appId]: keys }));
    message.success("已吊销");
  };

  const openHooks = async (app: OpenApiApp) => {
    setHookApp(app);
    const hooks = await listOpenApiWebhooks(tenantCode, app.id);
    setAppHooks((m) => ({ ...m, [app.id]: hooks }));
    setShowHook(true);
  };

  const handleCreateHook = async () => {
    const v = await hookForm.validateFields();
    try {
      await createOpenApiWebhook(tenantCode, {
        app_id: hookApp!.id,
        topic: v.topic,
        endpoint_url: v.endpoint_url,
        secret: v.secret || null,
      });
      message.success("已订阅 Webhook");
      const hooks = await listOpenApiWebhooks(tenantCode, hookApp!.id);
      setAppHooks((m) => ({ ...m, [hookApp!.id]: hooks }));
      hookForm.resetFields();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "订阅失败");
    }
  };

  const handleTestHook = async (subId: string) => {
    try {
      const r: OpenApiWebhookTest = await testOpenApiWebhook(tenantCode, subId);
      message.info(
        `测试：${r.status}${r.http_status ? ` (HTTP ${r.http_status})` : ""}`
      );
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "测试失败");
    }
  };

  const columns = [
    { title: "App 代码", dataIndex: "app_code", width: 120 },
    { title: "名称", dataIndex: "name" },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (v: string) => (
        <Tag color={v === "active" ? "green" : "red"}>{v}</Tag>
      ),
    },
    {
      title: "订阅事件",
      dataIndex: "events_subscribed",
      render: (v: string[]) =>
        v?.length ? (
          v.map((e) => (
            <Tag key={e} color="blue">
              {e}
            </Tag>
          ))
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: "操作",
      width: 180,
      render: (_: unknown, r: OpenApiApp) =>
        canManage ? (
          <Space>
            <Button size="small" icon={<KeyOutlined />} onClick={() => openKeys(r)}>
              密钥
            </Button>
            <Button size="small" icon={<LinkOutlined />} onClick={() => openHooks(r)}>
              Webhook
            </Button>
          </Space>
        ) : (
          <Text type="secondary">仅管理员可管理</Text>
        ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          开放平台 / 第三方集成
        </Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setShowApp(true)}
          disabled={!canManage}
          title={canManage ? undefined : "仅管理员可注册应用"}
        >
          注册应用
        </Button>
      </div>

      <Card size="small">
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={apps}
          columns={columns}
          pagination={{ pageSize: 8 }}
        />
      </Card>

      {/* 注册应用 */}
      <Modal
        title="注册第三方应用"
        open={showApp}
        onOk={handleRegister}
        onCancel={() => setShowApp(false)}
        okText="注册"
        cancelText="取消"
      >
        <Form form={appForm} layout="vertical">
          <Form.Item name="app_code" label="应用代码" rules={[{ required: true }]}>
            <Input placeholder="如 ota-ctrip" />
          </Form.Item>
          <Form.Item name="name" label="应用名称" rules={[{ required: true }]}>
            <Input placeholder="如 携程直连" />
          </Form.Item>
          <Form.Item name="callback_url" label="回调地址">
            <Input placeholder="https://...（选填）" />
          </Form.Item>
          <Form.Item
            name="events_subscribed"
            label="订阅事件"
            tooltip="逗号分隔，如 booking.created, payment.paid"
          >
            <Select
              mode="tags"
              placeholder="输入事件名回车"
              tokenSeparators={[","]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 密钥管理 */}
      <Modal
        title={`API 密钥 · ${keyApp?.name ?? ""}`}
        open={showKey}
        onCancel={() => setShowKey(false)}
        footer={[
          <Button key="close" onClick={() => setShowKey(false)}>
            关闭
          </Button>,
        ]}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Button
            type="primary"
            icon={<KeyOutlined />}
            onClick={handleCreateKey}
            disabled={!canManage}
          >
            生成新密钥
          </Button>
          {secret && (
            <Alert
              type="warning"
              showIcon
              message="密钥明文（仅展示一次）"
              description={
                <Text copyable strong>
                  {secret}
                </Text>
              }
            />
          )}
          <Table
            rowKey="id"
            size="small"
            dataSource={keyApp ? appKeys[keyApp.id] || [] : []}
            pagination={false}
            columns={[
              {
                title: "密钥",
                dataIndex: "key_mask",
                render: (v: string) => <Text code>{v}</Text>,
              },
              {
                title: "状态",
                dataIndex: "status",
                render: (v: string) => (
                  <Tag color={v === "active" ? "green" : "red"}>{v}</Tag>
                ),
              },
              {
                title: "吊销",
                render: (_: unknown, r: OpenApiKey) => (
                  <Button
                    size="small"
                    danger
                    disabled={r.status !== "active" || !canManage}
                    onClick={() => keyApp && handleRevoke(keyApp.id, r.id)}
                  >
                    吊销
                  </Button>
                ),
              },
            ]}
          />
        </Space>
      </Modal>

      {/* Webhook 管理 */}
      <Modal
        title={`Webhook 订阅 · ${hookApp?.name ?? ""}`}
        open={showHook}
        onCancel={() => setShowHook(false)}
        footer={[
          <Button key="close" onClick={() => setShowHook(false)}>
            关闭
          </Button>,
        ]}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Card size="small" title="新增订阅">
            <Form form={hookForm} layout="vertical">
              <Form.Item name="topic" label="事件 Topic" rules={[{ required: true }]}>
                <Input placeholder="如 booking.created 或 *" />
              </Form.Item>
              <Form.Item
                name="endpoint_url"
                label="Endpoint URL"
                rules={[{ required: true }]}
              >
                <Input placeholder="https://..." />
              </Form.Item>
              <Form.Item name="secret" label="签名密钥">
                <Input placeholder="选填" />
              </Form.Item>
              <Button type="primary" onClick={handleCreateHook}>
                订阅
              </Button>
            </Form>
          </Card>
          <Table
            rowKey="id"
            size="small"
            dataSource={hookApp ? appHooks[hookApp.id] || [] : []}
            pagination={false}
            columns={[
              { title: "Topic", dataIndex: "topic" },
              { title: "Endpoint", dataIndex: "endpoint_url", ellipsis: true },
              {
                title: "状态",
                dataIndex: "status",
                render: (v: string) => (
                  <Tag color={v === "active" ? "green" : "red"}>{v}</Tag>
                ),
              },
              {
                title: "测试",
                render: (_: unknown, r: OpenApiWebhook) => (
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    onClick={() => handleTestHook(r.id)}
                  >
                    触发
                  </Button>
                ),
              },
            ]}
          />
        </Space>
      </Modal>
    </div>
  );
}
