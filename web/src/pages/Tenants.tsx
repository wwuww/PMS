import { useEffect, useState } from "react";
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Switch,
  App,
  Tag,
  Space,
  Select,
  Divider,
  Spin,
  Empty,
} from "antd";
import { PlusOutlined, SettingOutlined } from "@ant-design/icons";
import {
  listTenants,
  createTenant,
  updateTenantSettings,
  updateHotelSettings,
  listHotels,
} from "../api/endpoints";
import type { Tenant, Hotel } from "../api/types";
import { useTenant } from "../store/tenant";

export default function TenantsPage() {
  const { message } = App.useApp();
  const { refresh } = useTenant();
  const [rows, setRows] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  // M31：NoShow 扣首晚房费设置弹窗
  const [settingsTenant, setSettingsTenant] = useState<Tenant | null>(null);
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [hotelsLoading, setHotelsLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setRows(await listTenants());
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function submit() {
    const v = await form.validateFields();
    try {
      await createTenant(v);
      message.success("门店/租户创建成功");
      setOpen(false);
      form.resetFields();
      await load();
      await refresh();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  // M31：打开设置弹窗，加载该租户的门店列表
  async function openSettings(t: Tenant) {
    setSettingsTenant(t);
    setHotelsLoading(true);
    setHotels([]);
    try {
      setHotels(await listHotels(t.code));
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setHotelsLoading(false);
    }
  }

  // M31：保存租户级默认开关
  async function saveTenantSetting(v: boolean) {
    if (!settingsTenant) return;
    try {
      await updateTenantSettings(settingsTenant.code, {
        noshow_charge_first_night: v,
      });
      message.success("租户设置已保存");
      setSettingsTenant({ ...settingsTenant, noshow_charge_first_night: v });
      await load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  // M31：保存门店级覆盖（inherit=继承租户 / on=强制扣 / off=强制不扣）
  async function saveHotelSetting(h: Hotel, v: string) {
    if (!settingsTenant) return;
    try {
      await updateHotelSettings(settingsTenant.code, h.id, {
        noshow_charge_first_night: v === "inherit" ? null : v === "on",
      });
      message.success(`门店「${h.name}」设置已保存`);
      setHotels(await listHotels(settingsTenant.code));
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  const columns = [
    { title: "ID", dataIndex: "id", key: "id", width: 70 },
    { title: "编码", dataIndex: "code", key: "code" },
    { title: "名称", dataIndex: "name", key: "name" },
    {
      title: "类型",
      dataIndex: "is_chain",
      key: "is_chain",
      render: (v: boolean) => (v ? <Tag color="blue">连锁</Tag> : <Tag>单体</Tag>),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (v: string) => <Tag color="green">{v}</Tag>,
    },
    {
      title: "操作",
      key: "action",
      width: 90,
      render: (_: unknown, r: Tenant) => (
        <Button
          size="small"
          icon={<SettingOutlined />}
          onClick={() => openSettings(r)}
        >
          设置
        </Button>
      ),
    },
  ];

  return (
    <Card
      title="门店 / 租户管理"
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setOpen(true)}
        >
          新建门店
        </Button>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title="新建门店 / 租户"
        open={open}
        onOk={submit}
        onCancel={() => setOpen(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ is_chain: false }}>
          <Form.Item
            name="code"
            label="编码"
            rules={[{ required: true, message: "请输入编码" }]}
          >
            <Input placeholder="如 DEMO2026" />
          </Form.Item>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="如 深圳湾示范店" />
          </Form.Item>
          <Form.Item name="is_chain" label="是否连锁" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* M31：NoShow 扣首晚房费设置弹窗 */}
      <Modal
        title={`设置 · ${settingsTenant?.name ?? ""}`}
        open={!!settingsTenant}
        onCancel={() => setSettingsTenant(null)}
        footer={null}
        width={520}
      >
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>
            NoShow 自动扣首晚房费（租户级默认）
          </div>
          <Space>
            <Switch
              checked={settingsTenant?.noshow_charge_first_night ?? false}
              onChange={saveTenantSetting}
              checkedChildren="扣首晚"
              unCheckedChildren="不扣"
            />
          </Space>
          <div style={{ color: "#888", fontSize: 12, marginTop: 6 }}>
            启用后，夜审时「应到未到」订单自动按首晚房费过账；门店可单独覆盖此默认值。
          </div>
        </div>

        <Divider orientation="left" style={{ margin: "8px 0 12px" }}>
          门店级覆盖
        </Divider>
        {hotelsLoading ? (
          <div style={{ textAlign: "center", padding: 16 }}>
            <Spin />
          </div>
        ) : hotels.length === 0 ? (
          <Empty description="该租户暂无门店" />
        ) : (
          hotels.map((h) => (
            <div
              key={h.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 10,
              }}
            >
              <span>
                {h.name}（{h.code}）
              </span>
              <Select
                size="small"
                style={{ width: 130 }}
                value={
                  h.noshow_charge_first_night === null
                    ? "inherit"
                    : h.noshow_charge_first_night
                      ? "on"
                      : "off"
                }
                onChange={(v) => saveHotelSetting(h, v)}
                options={[
                  { value: "inherit", label: "继承租户" },
                  { value: "on", label: "强制扣首晚" },
                  { value: "off", label: "强制不扣" },
                ]}
              />
            </div>
          ))
        )}
      </Modal>
    </Card>
  );
}
