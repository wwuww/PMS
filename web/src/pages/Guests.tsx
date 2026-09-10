import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  App as AntApp,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Switch,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useTenant } from "../store/tenant";
import {
  createGuest,
  listGuests,
  listHotels,
  searchGuests,
  updateGuest,
  type GuestCreateBody,
} from "../api/endpoints";
import type {
  Guest,
  GuestIdType,
  GuestVipLevel,
} from "../api/types";

const VIP_LABEL: Record<GuestVipLevel, string> = {
  NORMAL: "普通",
  SILVER: "银卡",
  GOLD: "金卡",
  PLATINUM: "白金",
  DIAMOND: "钻石",
};

const VIP_COLOR: Record<GuestVipLevel, string> = {
  NORMAL: "default",
  SILVER: "blue",
  GOLD: "gold",
  PLATINUM: "purple",
  DIAMOND: "magenta",
};

const ID_LABEL: Record<GuestIdType, string> = {
  ID: "身份证",
  PASSPORT: "护照",
  OFFICER: "军官证",
  OTHER: "其他",
};

function yuan(cents: number): string {
  return `¥${(cents / 100).toFixed(2)}`;
}

export default function GuestsPage() {
  const { tenantCode } = useTenant();
  const navigate = useNavigate();
  const { message } = AntApp.useApp();

  const [list, setList] = useState<Guest[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [hotels, setHotels] = useState<{ id: string; name: string }[]>([]);

  const loadHotels = async () => {
    if (!tenantCode) return;
    try {
      const data = await listHotels(tenantCode);
      setHotels(data.map((h) => ({ id: h.id, name: h.name })));
    } catch {
      /* 门店加载失败不阻断 */
    }
  };

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Guest | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const data = await listGuests(tenantCode, {
        keyword: keyword || undefined,
        limit: 100,
      });
      setList(data);
    } catch (e) {
      message.error("加载宾客档案失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    void loadHotels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, keyword]);

  const hotelName = useMemo(() => {
    const m = new Map(hotels.map((h) => [h.id, h.name]));
    return (id: string) => m.get(id) ?? id;
  }, [hotels]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ id_type: "ID", vip_level: "NORMAL", is_valid: true });
    setDrawerOpen(true);
  };

  const openEdit = (g: Guest) => {
    setEditing(g);
    form.setFieldsValue({
      hotel_id: Number(g.hotel_id),
      name: g.name,
      phone: g.phone ?? "",
      id_type: g.id_type ?? "ID",
      id_no: g.id_no ?? "",
      vip_level: g.vip_level,
      gender: g.gender ?? undefined,
      email: g.email ?? "",
      address: g.address ?? "",
      tags: g.tags ?? [],
      notes: g.notes ?? "",
      // 批次② 核心实体字段补全：回显
      en_name: g.en_name ?? "",
      native_place: g.native_place ?? "",
      nation: g.nation ?? "",
      is_valid: g.is_valid ?? true,
      come_time: g.come_time ?? "",
      head_url: g.head_url ?? "",
      id_doc_sign_org: g.id_doc_sign_org ?? "",
      id_doc_valid_to: g.id_doc_valid_to ?? "",
    });
    setDrawerOpen(true);
  };

  const submit = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updateGuest(tenantCode, editing.id, {
          name: v.name,
          phone: v.phone || null,
          id_type: v.id_type,
          id_no: v.id_no || null,
          vip_level: v.vip_level,
          gender: v.gender || null,
          email: v.email || null,
          address: v.address || null,
          tags: v.tags || [],
          notes: v.notes || null,
          // 批次② 核心实体字段补全
          en_name: v.en_name || null,
          native_place: v.native_place || null,
          nation: v.nation || null,
          is_valid: v.is_valid ?? true,
          come_time: v.come_time || null,
          head_url: v.head_url || null,
          id_doc_sign_org: v.id_doc_sign_org || null,
          id_doc_valid_to: v.id_doc_valid_to || null,
        });
        message.success("已更新宾客档案");
      } else {
        const body: GuestCreateBody = {
          hotel_id: Number(v.hotel_id),
          name: v.name,
          phone: v.phone || null,
          id_type: v.id_type,
          id_no: v.id_no || null,
          vip_level: v.vip_level,
          gender: v.gender || null,
          email: v.email || null,
          address: v.address || null,
          tags: v.tags || [],
          notes: v.notes || null,
          // 批次② 核心实体字段补全
          en_name: v.en_name || null,
          native_place: v.native_place || null,
          nation: v.nation || null,
          is_valid: v.is_valid ?? true,
          come_time: v.come_time || null,
          head_url: v.head_url || null,
          id_doc_sign_org: v.id_doc_sign_org || null,
          id_doc_valid_to: v.id_doc_valid_to || null,
        };
        await createGuest(tenantCode, body);
        message.success("已建档");
      }
      setDrawerOpen(false);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const quickSearch = async (q: string) => {
    if (!tenantCode || !q.trim()) {
      void load();
      return;
    }
    const s = q.trim();
    setLoading(true);
    try {
      // M23 清单#4：姓名/手机号/证件号/订单号 智能判别
      // 纯数字：≤6 位→订单号；7~14 位→手机号；≥15 位→证件号；其余→姓名
      const opts = /^\d+$/.test(s)
        ? s.length <= 6
          ? { booking_id: s }
          : s.length >= 15
            ? { id_no: s }
            : { phone: s }
        : { name: s };
      const data = await searchGuests(tenantCode, opts);
      setList(data);
    } finally {
      setLoading(false);
    }
  };

  const columns: ColumnsType<Guest> = [
    {
      title: "姓名",
      dataIndex: "name",
      render: (name: string, g) => (
        <a
          onClick={() => {
            setKeyword(name);
            void quickSearch(name);
          }}
        >
          {name}
        </a>
      ),
    },
    { title: "手机号", dataIndex: "phone", render: (p: string | null) => p || "—" },
    {
      title: "证件",
      key: "id",
      render: (_: unknown, g: Guest) =>
        g.id_type ? `${ID_LABEL[g.id_type] ?? g.id_type}${g.id_no ? ` ${g.id_no}` : ""}` : "—",
    },
    {
      title: "等级",
      dataIndex: "vip_level",
      render: (lv: GuestVipLevel) => <Tag color={VIP_COLOR[lv]}>{VIP_LABEL[lv]}</Tag>,
    },
    {
      title: "关联会员",
      key: "member",
      render: (_: unknown, g: Guest) =>
        g.member_id ? (
          <Space size={4}>
            <Tag color={VIP_COLOR[g.member_level ?? "NORMAL"]}>
              {VIP_LABEL[g.member_level ?? "NORMAL"]}
            </Tag>
            {g.member_points != null && <span>积分 {g.member_points}</span>}
          </Space>
        ) : (
          <Tag>散客</Tag>
        ),
    },
    {
      title: "客史标签",
      dataIndex: "tags",
      render: (tags: string[]) =>
        tags && tags.length ? (
          <Space size={4} wrap>
            {tags.map((t) => (
              <Tag key={t}>{t}</Tag>
            ))}
          </Space>
        ) : (
          "—"
        ),
    },
    { title: "入住次数", dataIndex: "stay_count" },
    {
      title: "累计消费",
      dataIndex: "total_spend",
      render: (c: number) => yuan(c),
    },
    { title: "英文名", dataIndex: "en_name", render: (v: string | null) => v || "—" },
    {
      title: "启用",
      dataIndex: "is_valid",
      align: "center" as const,
      render: (v: boolean | undefined) =>
        v === false ? <Tag color="default">停用</Tag> : <Tag color="green">启用</Tag>,
    },
    {
      title: "操作",
      key: "op",
      render: (_: unknown, g: Guest) => (
        <Button type="link" onClick={() => openEdit(g)}>
          编辑
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Card
        title="宾客档案 / 客史"
        extra={
          <Space>
            <Input.Search
              placeholder="搜索姓名 / 手机号 / 证件号"
              allowClear
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={(v) => void quickSearch(v)}
              style={{ width: 240 }}
            />
            <Button type="primary" onClick={openCreate}>
              新建宾客
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={list}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 位宾客` }}
          size="middle"
        />
      </Card>

      <Drawer
        title={editing ? "编辑宾客档案" : "新建宾客档案"}
        width={420}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} onClick={submit}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="hotel_id" label="归属门店" rules={[{ required: true, message: "请选择门店" }]}>
            <Select
              placeholder="选择门店"
              options={hotels.map((h) => ({ label: h.name, value: Number(h.id) }))}
            />
          </Form.Item>
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input />
          </Form.Item>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="id_type" label="证件类型" style={{ flex: 1 }}>
              <Select
                options={(Object.keys(ID_LABEL) as GuestIdType[]).map((k) => ({
                  label: ID_LABEL[k],
                  value: k,
                }))}
              />
            </Form.Item>
            <Form.Item name="id_no" label="证件号" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </Space>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="vip_level" label="会员等级" style={{ flex: 1 }}>
              <Select
                options={(Object.keys(VIP_LABEL) as GuestVipLevel[]).map((k) => ({
                  label: VIP_LABEL[k],
                  value: k,
                }))}
              />
            </Form.Item>
            <Form.Item name="gender" label="性别" style={{ flex: 1 }}>
              <Select
                allowClear
                placeholder="不选"
                options={[
                  { label: "男", value: "M" },
                  { label: "女", value: "F" },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="email" label="邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="address" label="地址">
            <Input />
          </Form.Item>
          <Form.Item name="tags" label="客史标签" tooltip="如：高楼层、无烟房、安静房">
            <Select mode="tags" placeholder="输入后回车添加标签" />
          </Form.Item>
          <Form.Item name="notes" label="偏好 / 备注">
            <Input.TextArea rows={3} />
          </Form.Item>
          {/* 批次② 核心实体字段补全 */}
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="en_name" label="英文名" style={{ flex: 1 }}>
              <Input placeholder="English name" maxLength={64} />
            </Form.Item>
            <Form.Item name="native_place" label="籍贯" style={{ flex: 1 }}>
              <Input placeholder="如：广东广州" maxLength={64} />
            </Form.Item>
          </Space>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="nation" label="民族" style={{ flex: 1 }}>
              <Input placeholder="如：汉" maxLength={32} />
            </Form.Item>
            <Form.Item name="is_valid" label="启用" valuePropName="checked" style={{ flex: 1 }}>
              <Switch />
            </Form.Item>
          </Space>
          <Form.Item name="come_time" label="到店时间" tooltip="ISO8601 时间字符串，如 2024-01-15T14:00:00">
            <Input placeholder="YYYY-MM-DDTHH:mm:ss" maxLength={32} />
          </Form.Item>
          <Form.Item name="head_url" label="头像URL">
            <Input placeholder="https://..." maxLength={255} />
          </Form.Item>
          <Space size={12} style={{ display: "flex" }}>
            <Form.Item name="id_doc_sign_org" label="证件签发机关" style={{ flex: 1 }}>
              <Input placeholder="如：XX公安局" maxLength={64} />
            </Form.Item>
            <Form.Item name="id_doc_valid_to" label="证件有效期至" style={{ flex: 1 }}>
              <Input placeholder="YYYY-MM-DD" maxLength={10} />
            </Form.Item>
          </Space>
        </Form>
      </Drawer>
    </div>
  );
}
