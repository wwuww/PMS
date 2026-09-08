import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  assignUserRole,
  createRole,
  createUser,
  listHotels,
  listRoles,
  listUsers,
} from "../api/endpoints";
import type { Hotel, Role, User, UserCreate } from "../api/types";

const USER_STATUS_COLOR: Record<string, string> = {
  active: "green",
  disabled: "default",
  locked: "red",
};

export default function Users() {
  const { tenantCode } = useTenant();
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [loading, setLoading] = useState(false);

  const [showUser, setShowUser] = useState(false);
  const [showRole, setShowRole] = useState(false);
  const [assignUser, setAssignUser] = useState<User | null>(null);
  const [userForm] = Form.useForm();
  const [roleForm] = Form.useForm();
  const [assignForm] = Form.useForm();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [u, r, h] = await Promise.all([
        listUsers(tenantCode),
        listRoles(tenantCode),
        listHotels(tenantCode),
      ]);
      setUsers(u);
      setRoles(r);
      setHotels(h);
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreateUser = async () => {
    const v = await userForm.validateFields();
    const body: UserCreate = {
      username: v.username,
      password: v.password,
      display_name: v.display_name || "",
      scope: v.scope || "tenant",
    };
    try {
      await createUser(tenantCode, body);
      message.success("用户已创建");
      setShowUser(false);
      userForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "创建失败");
    }
  };

  const handleCreateRole = async () => {
    const v = await roleForm.validateFields();
    try {
      await createRole(tenantCode, {
        name: v.name,
        level: v.level || "STAFF",
        permissions: v.permissions
          ? v.permissions.split(",").map((s: string) => s.trim()).filter(Boolean)
          : [],
        hotel_scoped: !!v.hotel_scoped,
      });
      message.success("角色已创建");
      setShowRole(false);
      roleForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "创建失败");
    }
  };

  const handleAssign = async () => {
    if (!assignUser) return;
    const v = await assignForm.validateFields();
    // 门店级角色（hotel_scoped）分配时必须带 hotel_id，否则后端抛 400
    const role = roles.find((r) => r.id === v.role_id);
    const hotelId = role?.hotel_scoped ? v.hotel_id : null;
    try {
      await assignUserRole(tenantCode, assignUser.id, v.role_id, hotelId);
      message.success("已分配角色");
      setAssignUser(null);
      assignForm.resetFields();
    } catch (e: any) {
      message.error(e?.message || "分配失败");
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Card title="用户与角色（RBAC · M8）">
        <Tabs
          items={[
            {
              key: "users",
              label: "用户",
              children: (
                <>
                  <Space style={{ marginBottom: 12 }}>
                    <Button
                      icon={<ReloadOutlined />}
                      onClick={refresh}
                      loading={loading}
                    >
                      刷新
                    </Button>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        setShowUser(true);
                        userForm.resetFields();
                      }}
                    >
                      新建用户
                    </Button>
                  </Space>
                  <Table<User>
                    rowKey="id"
                    dataSource={users}
                    loading={loading}
                    pagination={{ pageSize: 10 }}
                    size="small"
                    columns={[
                      { title: "ID", dataIndex: "id" },
                      { title: "用户名", dataIndex: "username" },
                      { title: "显示名", dataIndex: "display_name", render: (v) => v || "—" },
                      {
                        title: "状态",
                        dataIndex: "status",
                        render: (s: string) => (
                          <Tag color={USER_STATUS_COLOR[s]}>{s}</Tag>
                        ),
                      },
                      {
                        title: "作用域",
                        dataIndex: "scope",
                        render: (s: string) => <Tag>{s}</Tag>,
                      },
                      { title: "失败次数", dataIndex: "failed_attempts" },
                      {
                        title: "末次登录",
                        dataIndex: "last_login_at",
                        render: (v) => v || "—",
                      },
                      {
                        title: "操作",
                        key: "op",
                        render: (_, r) => (
                          <Button
                            size="small"
                            onClick={() => {
                              setAssignUser(r);
                              assignForm.resetFields();
                            }}
                          >
                            分配角色
                          </Button>
                        ),
                      },
                    ]}
                  />
                </>
              ),
            },
            {
              key: "roles",
              label: "角色",
              children: (
                <>
                  <Space style={{ marginBottom: 12 }}>
                    <Button
                      icon={<PlusOutlined />}
                      type="primary"
                      onClick={() => {
                        setShowRole(true);
                        roleForm.resetFields();
                      }}
                    >
                      新建角色
                    </Button>
                  </Space>
                  <Table<Role>
                    rowKey="id"
                    dataSource={roles}
                    pagination={false}
                    size="small"
                    columns={[
                      { title: "ID", dataIndex: "id" },
                      { title: "名称", dataIndex: "name" },
                      {
                        title: "级别",
                        dataIndex: "level",
                        render: (l: string) => <Tag color="blue">{l}</Tag>,
                      },
                      {
                        title: "系统内置",
                        dataIndex: "is_system",
                        render: (b: boolean) => (b ? "是" : "否"),
                      },
                      {
                        title: "门店级",
                        dataIndex: "hotel_scoped",
                        render: (b: boolean) => (b ? "是" : "否"),
                      },
                      {
                        title: "权限",
                        dataIndex: "permissions",
                        render: (p: string[]) =>
                          p.length ? (
                            <Space wrap>
                              {p.map((x) => (
                                <Tag key={x}>{x}</Tag>
                              ))}
                            </Space>
                          ) : (
                            "—"
                          ),
                      },
                    ]}
                  />
                </>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新建用户"
        open={showUser}
        onOk={handleCreateUser}
        onCancel={() => setShowUser(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={userForm} layout="vertical">
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input placeholder="登录账号" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: "至少 6 位" }]}
          >
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名">
            <Input />
          </Form.Item>
          <Form.Item name="scope" label="作用域" initialValue="tenant">
            <Select
              options={[
                { value: "tenant", label: "租户级" },
                { value: "hotel", label: "门店级" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建角色"
        open={showRole}
        onOk={handleCreateRole}
        onCancel={() => setShowRole(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={roleForm} layout="vertical">
          <Form.Item
            name="name"
            label="角色名"
            rules={[{ required: true, message: "请输入角色名" }]}
          >
            <Input placeholder="如 前台主管" />
          </Form.Item>
          <Form.Item name="level" label="级别" initialValue="STAFF">
            <Select
              options={[
                { value: "ADMIN", label: "ADMIN" },
                { value: "MANAGER", label: "MANAGER" },
                { value: "STAFF", label: "STAFF" },
              ]}
            />
          </Form.Item>
          <Form.Item name="permissions" label="权限（逗号分隔）">
            <Input placeholder="billing.settle, approval.decide" />
          </Form.Item>
          <Form.Item name="hotel_scoped" label="门店级" valuePropName="checked">
            <Select
              options={[
                { value: false, label: "否" },
                { value: true, label: "是" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`分配角色 · ${assignUser?.username ?? ""}`}
        open={!!assignUser}
        onOk={handleAssign}
        onCancel={() => setAssignUser(null)}
        okText="分配"
        cancelText="取消"
      >
        <Form form={assignForm} layout="vertical">
          <Form.Item
            name="role_id"
            label="角色"
            rules={[{ required: true, message: "请选择角色" }]}
          >
            <Select
              placeholder="选择角色"
              options={roles.map((r) => ({
                value: r.id,
                label: `${r.name}${r.hotel_scoped ? "（门店级）" : ""}`,
              }))}
            />
          </Form.Item>
          {/* 门店级角色必须选择门店，租户级角色（如 ADMIN）无需门店 */}
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.role_id !== cur.role_id}
          >
            {({ getFieldValue }) => {
              const roleId = getFieldValue("role_id");
              const role = roles.find((r) => r.id === roleId);
              if (!role?.hotel_scoped) return null;
              return (
                <Form.Item
                  name="hotel_id"
                  label="门店"
                  rules={[{ required: true, message: "门店级角色必须选择门店" }]}
                >
                  <Select
                    placeholder="选择门店"
                    options={hotels.map((h) => ({ value: h.id, label: h.name }))}
                  />
                </Form.Item>
              );
            }}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
