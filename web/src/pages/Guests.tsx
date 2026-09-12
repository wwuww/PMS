import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  App as AntApp,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Switch,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useTenant } from "../store/tenant";
import {
  createBlackGuest,
  createGuest,
  listBlacklist,
  listGuests,
  listHotels,
  searchGuests,
  updateGuest,
  type GuestCreateBody,
} from "../api/endpoints";
import type {
  BlackGuest,
  Guest,
  GuestIdType,
  GuestVipLevel,
} from "../api/types";
import { PERM, currentOperator, useCan } from "../utils/permission";

/** 黑名单等级：0 提示 / 1 警告 / 2 限制 / 3 拒绝入住。 */
const BLACK_LEVEL_OPTIONS = [
  { value: 0, label: "0 提示" },
  { value: 1, label: "1 警告" },
  { value: 2, label: "2 限制" },
  { value: 3, label: "3 拒绝入住" },
];

/** 归一化比较键：去空白 + 转大写（证件号含字母）。 */
function normKey(v?: string | null): string {
  return (v || "").replace(/\s+/g, "").toUpperCase();
}

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
  const canBlacklist = useCan(PERM.BLACKLIST_MANAGE);

  const [list, setList] = useState<Guest[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [hotels, setHotels] = useState<{ id: string; name: string }[]>([]);

  // 批次④：黑名单（一次拉取全量名单，客户端按姓名/证件号/手机号匹配，避免 N 次 check 请求）
  const [blacklist, setBlacklist] = useState<BlackGuest[]>([]);
  const [blackOpen, setBlackOpen] = useState(false);
  const [blackTarget, setBlackTarget] = useState<Guest | null>(null);
  const [blackSaving, setBlackSaving] = useState(false);
  const [blackForm] = Form.useForm();

  const loadBlacklist = async () => {
    if (!tenantCode) return;
    try {
      const data = await listBlacklist(tenantCode, { is_valid: true });
      setBlacklist(Array.isArray(data) ? data : []);
    } catch {
      // 黑名单加载失败不阻断宾客档案：仅不展示黑名单标签
      setBlacklist([]);
    }
  };

  /** 命中黑名单则返回该条记录（证件号 > 手机号 > 姓名）。 */
  const blackHit = useMemo(() => {
    const byIdNo = new Map<string, BlackGuest>();
    const byPhone = new Map<string, BlackGuest>();
    const byName = new Map<string, BlackGuest>();
    blacklist.forEach((b) => {
      const idk = normKey(b.id_no);
      const pk = normKey(b.phone);
      const nk = normKey(b.name);
      if (idk) byIdNo.set(idk, b);
      if (pk) byPhone.set(pk, b);
      if (nk) byName.set(nk, b);
    });
    return (g: Guest): BlackGuest | undefined => {
      const idk = normKey(g.id_no);
      const pk = normKey(g.phone);
      const nk = normKey(g.name);
      if (idk && byIdNo.has(idk)) return byIdNo.get(idk);
      if (pk && byPhone.has(pk)) return byPhone.get(pk);
      if (nk && byName.has(nk)) return byName.get(nk);
      return undefined;
    };
  }, [blacklist]);

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
    void loadBlacklist();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, keyword]);

  const openBlacklist = (g: Guest) => {
    setBlackTarget(g);
    setBlackOpen(true);
    blackForm.resetFields();
    blackForm.setFieldsValue({
      level: 2,
      hotel_id: g.hotel_id != null ? Number(g.hotel_id) : undefined,
    });
  };

  const submitBlacklist = async () => {
    const v = await blackForm.validateFields();
    if (!blackTarget) return;
    setBlackSaving(true);
    try {
      await createBlackGuest(tenantCode, {
        hotel_id: v.hotel_id ?? null,
        name: blackTarget.name,
        id_no: blackTarget.id_no ?? null,
        phone: blackTarget.phone ?? null,
        reason: String(v.reason || "").trim(),
        level: v.level ?? 0,
        operator: currentOperator(),
      });
      message.success(`${blackTarget.name} 已加入黑名单`);
      setBlackOpen(false);
      blackForm.resetFields();
      await loadBlacklist();
    } catch (e: unknown) {
      message.error((e as Error).message || "加入黑名单失败");
    } finally {
      setBlackSaving(false);
    }
  };

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
      render: (name: string, g: Guest) => {
        const hit = blackHit(g);
        return (
          <Space size={4}>
            <a
              onClick={() => {
                setKeyword(name);
                void quickSearch(name);
              }}
            >
              {name}
            </a>
            {hit && (
              <Tag color="red" title={hit.reason || undefined}>
                黑名单
              </Tag>
            )}
          </Space>
        );
      },
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
        <Space size={4}>
          <Button type="link" onClick={() => openEdit(g)}>
            编辑
          </Button>
          <Button
            type="link"
            danger
            disabled={!canBlacklist}
            onClick={() => openBlacklist(g)}
          >
            加入黑名单
          </Button>
        </Space>
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

      {/* 批次④：加入黑名单 */}
      <Modal
        title={blackTarget ? `加入黑名单 - ${blackTarget.name}` : "加入黑名单"}
        open={blackOpen}
        onOk={() => void submitBlacklist()}
        onCancel={() => setBlackOpen(false)}
        okText="确认加入"
        cancelText="取消"
        confirmLoading={blackSaving}
        destroyOnClose
      >
        <Form form={blackForm} layout="vertical" preserve={false}>
          <Form.Item label="宾客">
            <Input value={blackTarget?.name ?? ""} readOnly disabled />
          </Form.Item>
          <Form.Item label="证件号">
            <Input value={blackTarget?.id_no ?? ""} readOnly disabled />
          </Form.Item>
          <Form.Item label="手机号">
            <Input value={blackTarget?.phone ?? ""} readOnly disabled />
          </Form.Item>
          <Form.Item
            name="reason"
            label="原因"
            rules={[{ required: true, message: "请填写加入黑名单的原因" }]}
          >
            <Input.TextArea rows={3} maxLength={255} placeholder="如：恶意逃单 / 损坏房间设施" />
          </Form.Item>
          <Form.Item name="level" label="等级">
            <Select options={BLACK_LEVEL_OPTIONS} />
          </Form.Item>
          <Form.Item name="hotel_id" label="适用门店（不选=全租户生效）">
            <Select
              allowClear
              placeholder="全租户"
              options={hotels.map((h) => ({ label: h.name, value: Number(h.id) }))}
            />
          </Form.Item>
        </Form>
      </Modal>

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
