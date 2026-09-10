import { useEffect, useMemo, useState } from "react";
import {
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
  Typography,
  Switch,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import { listRooms, listRoomTypes, createRooms, listRoomAttributes, setRoomAttributes } from "../api/endpoints";
import type { Room, RoomType, RoomCreate, RoomAttribute } from "../api/types";
import { ATTRIBUTE_OPTIONS, attributeLabel } from "../domain/roomAttributes";
import { currentOperator } from "../utils/permission";

const { Title, Text } = Typography;

const STATE_LABELS: Record<string, { label: string; color: string }> = {
  vacant_clean: { label: "空净", color: "green" },
  vacant_dirty: { label: "空脏", color: "orange" },
  occupied: { label: "在住", color: "blue" },
  arrival_locked: { label: "锁房", color: "purple" },
  maintenance: { label: "维修", color: "red" },
  out_of_service: { label: "停用", color: "default" },
};

const PAGE_SIZE = 14;

/** 房间属性行 → 有效属性编码列表（is_valid=false 视为已移除）。 */
function activeCodes(rows: RoomAttribute[] | undefined): string[] {
  return (rows || [])
    .filter((a) => a.is_valid !== false && !!a.attribute_code)
    .map((a) => a.attribute_code as string);
}

export default function Rooms() {
  const { tenantCode, hotelId } = useTenant();
  const [list, setList] = useState<Room[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(false);
  const [stateFilter, setStateFilter] = useState<string>("ALL");
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // 批次④：房间属性（按当前分页懒加载，避免 N 次全量请求）
  const [page, setPage] = useState(1);
  const [attrMap, setAttrMap] = useState<Record<string, string[]>>({});

  // 批次④：属性编辑抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Room | null>(null);
  const [attrForm] = Form.useForm();
  const [attrSaving, setAttrSaving] = useState(false);

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [rs, rts] = await Promise.all([
        listRooms(tenantCode),
        listRoomTypes(tenantCode),
      ]);
      setList(rs);
      setRoomTypes(rts);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "房间加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  const rtMap = useMemo(() => {
    const m = new Map<string, string>();
    roomTypes.forEach((r) => m.set(r.id, `${r.name}（${r.code}）`));
    return m;
  }, [roomTypes]);

  const filtered = useMemo(() => {
    if (stateFilter === "ALL") return list;
    return list.filter((r) => r.state === stateFilter);
  }, [list, stateFilter]);

  /** 当前分页可见房间（属性只针对可见行懒加载，控制请求量）。 */
  const visible = useMemo(
    () => filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filtered, page]
  );

  // 房号 → 属性编码（后端 /room-attributes 组合查询可能只回 room_no，故两个维度都建索引）
  useEffect(() => {
    if (!tenantCode || !visible.length) return;
    let cancelled = false;
    const missing = visible.filter((r) => attrMap[r.id] === undefined);
    if (!missing.length) return;
    const load = async () => {
      const entries = await Promise.all(
        missing.map(async (r) => {
          try {
            const rows = await listRoomAttributes(tenantCode, r.id);
            return [r.id, activeCodes(rows)] as const;
          } catch {
            // 单间房属性加载失败不阻断列表：记为无属性
            return [r.id, [] as string[]] as const;
          }
        })
      );
      if (cancelled) return;
      setAttrMap((prev) => {
        const next = { ...prev };
        entries.forEach(([id, codes]) => {
          next[id] = codes;
        });
        return next;
      });
    };
    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, visible, attrMap]);

  const openAttr = async (room: Room) => {
    setEditing(room);
    setDrawerOpen(true);
    attrForm.setFieldsValue({ codes: attrMap[room.id] ?? [], memo: room.memo ?? "" });
    if (!tenantCode) return;
    try {
      const rows = await listRoomAttributes(tenantCode, room.id);
      const codes = activeCodes(rows);
      attrForm.setFieldsValue({ codes });
      setAttrMap((prev) => ({ ...prev, [room.id]: codes }));
    } catch {
      /* 拉取失败沿用缓存值 */
    }
  };

  const submitAttr = async () => {
    const v = await attrForm.validateFields();
    if (!editing) return;
    setAttrSaving(true);
    try {
      const rows = await setRoomAttributes(tenantCode, editing.id, {
        codes: v.codes || [],
        memo: v.memo?.trim() || null,
        operator: currentOperator(),
      });
      const codes = activeCodes(rows);
      setAttrMap((prev) => ({ ...prev, [editing.id]: codes }));
      message.success(`房间 ${editing.room_no} 属性已更新`);
      setDrawerOpen(false);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "属性保存失败");
    } finally {
      setAttrSaving(false);
    }
  };

  const handleCreate = async () => {
    if (!hotelId) {
      message.warning("请先在顶部选择门店");
      return;
    }
    const v = await form.validateFields();
    const nos = String(v.room_nos || "")
      .split(/[\n,，]+/)
      .map((s: string) => s.trim())
      .filter(Boolean);
    if (!nos.length) {
      message.warning("请至少填写一个房号");
      return;
    }
    const body: RoomCreate[] = nos.map((room_no: string) => ({
      room_type_id: v.room_type_id,
      room_no,
      floor:
        v.floor ||
        String(room_no).replace(/[^0-9]/g, "").slice(0, 2) ||
        "0",
      // 批次② 核心实体字段补全（批量建房时统一套用到每间房）
      building_id: v.building_id || null,
      telephone: v.telephone || null,
      room_card_no: v.room_card_no || null,
      room_name: v.room_name || null,
      memo: v.memo || null,
      is_valid: v.is_valid ?? true,
    }));
    setSaving(true);
    try {
      await createRooms(hotelId, body);
      message.success(`已创建 ${body.length} 间房`);
      setShow(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    } finally {
      setSaving(false);
    }
  };

  const columns = useMemo(
    () => [
      { title: "房号", dataIndex: "room_no", width: 110 },
      { title: "楼层", dataIndex: "floor", width: 80 },
      {
        title: "房型",
        dataIndex: "room_type_id",
        render: (id: string) =>
          rtMap.get(id) || <Text type="secondary">未关联</Text>,
      },
      // 批次④：房间属性（标签化展示，无属性显示「—」）
      {
        title: "属性",
        key: "attributes",
        width: 240,
        render: (_: unknown, r: Room) => {
          const codes = attrMap[r.id];
          if (!codes) return <Text type="secondary">加载中…</Text>;
          if (!codes.length) return "—";
          return (
            <Space size={4} wrap>
              {codes.map((c) => (
                <Tag key={c} color="geekblue">
                  {attributeLabel(c)}
                </Tag>
              ))}
            </Space>
          );
        },
      },
      {
        title: "状态",
        dataIndex: "state",
        render: (s: string) => {
          const meta = STATE_LABELS[s] || { label: s, color: "default" };
          return <Tag color={meta.color}>{meta.label}</Tag>;
        },
      },
      { title: "门店ID", dataIndex: "hotel_id", width: 90 },
      { title: "楼栋", dataIndex: "building_id", render: (v: string | null) => v || "—" },
      { title: "电话", dataIndex: "telephone", render: (v: string | null) => v || "—" },
      { title: "房卡号", dataIndex: "room_card_no", render: (v: string | null) => v || "—" },
      { title: "房间名", dataIndex: "room_name", render: (v: string | null) => v || "—" },
      { title: "备注", dataIndex: "memo", render: (v: string | null) => v || "—" },
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
        width: 110,
        fixed: "right" as const,
        render: (_: unknown, r: Room) => (
          <Button size="small" type="link" onClick={() => void openAttr(r)}>
            编辑属性
          </Button>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rtMap, attrMap]
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          房间 / 库存管理
        </Title>
        <Space>
          <Select
            value={stateFilter}
            style={{ width: 140 }}
            onChange={(v) => {
              setStateFilter(v);
              setPage(1);
            }}
            options={[
              { value: "ALL", label: "全部状态" },
              ...Object.entries(STATE_LABELS).map(([k, v]) => ({
                value: k,
                label: v.label,
              })),
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setShow(true)}>
            批量建房
          </Button>
        </Space>
      </div>
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={filtered}
          columns={columns}
          scroll={{ x: 1500 }}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            onChange: (p) => setPage(p),
          }}
        />
      </Card>
      <Modal
        title="批量新建房间"
        open={show}
        onOk={handleCreate}
        confirmLoading={saving}
        onCancel={() => {
          setShow(false);
          form.resetFields();
        }}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ floor: "4", is_valid: true }}>
          <Form.Item
            name="room_type_id"
            label="房型"
            rules={[{ required: true, message: "请选择房型" }]}
          >
            <Select
              placeholder="选择房型"
              options={roomTypes.map((r) => ({
                value: r.id,
                label: `${r.name}（${r.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="room_nos"
            label="房号（每行一个，或用逗号分隔）"
            rules={[{ required: true, message: "请填写房号" }]}
          >
            <Input.TextArea rows={6} placeholder={"401\n402\n403"} />
          </Form.Item>
          <Form.Item name="floor" label="楼层（默认取房号前两位，可覆盖）">
            <Input placeholder="如：4" maxLength={8} />
          </Form.Item>
          <Form.Item name="building_id" label="楼栋ID">
            <Input placeholder="如：B1" maxLength={32} />
          </Form.Item>
          <Form.Item name="telephone" label="电话">
            <Input placeholder="分机或电话" maxLength={32} />
          </Form.Item>
          <Form.Item name="room_card_no" label="房卡号">
            <Input placeholder="房卡卡号" maxLength={64} />
          </Form.Item>
          <Form.Item name="room_name" label="房间名">
            <Input placeholder="房间别名" maxLength={64} />
          </Form.Item>
          <Form.Item name="memo" label="备注">
            <Input.TextArea rows={2} maxLength={255} placeholder="房间备注" />
          </Form.Item>
          <Form.Item name="is_valid" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Text type="secondary">目标门店：{hotelId ? `ID ${hotelId}` : "未选择"}</Text>
        </Form>
      </Modal>

      {/* 批次④：房间属性编辑抽屉 */}
      <Drawer
        title={editing ? `房间属性 - ${editing.room_no}` : "房间属性"}
        width={420}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={attrSaving} onClick={() => void submitAttr()}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={attrForm} layout="vertical">
          <Form.Item name="codes" label="房间属性">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择房间属性（可多选）"
              options={ATTRIBUTE_OPTIONS}
            />
          </Form.Item>
          <Form.Item name="memo" label="备注">
            <Input.TextArea rows={3} maxLength={255} placeholder="属性备注（可选）" />
          </Form.Item>
          <Text type="secondary">
            保存将全量覆盖该房间的属性集合（取消勾选即移除）。
          </Text>
        </Form>
      </Drawer>
    </div>
  );
}
