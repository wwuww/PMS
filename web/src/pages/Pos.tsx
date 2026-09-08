import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  PlusOutlined,
  ReloadOutlined,
  ShoppingCartOutlined,
  BarChartOutlined,
  UndoOutlined,
  PercentageOutlined,
} from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  listMenuItems,
  createMenuItem,
  listTables,
  setTableState,
  openPosOrder,
  addPosOrderItem,
  settlePosRoom,
  settlePosCash,
  listPosOrders,
  fnbReport,
  setMenuSoldOut,
  voidPosOrderItem,
  applyPosOrderDiscount,
  type PosOrderOpenBody,
  type PosOrderItemBody,
  fnbRoomLookup,
} from "../api/endpoints";
import type {
  MenuItem,
  DiningTable,
  PosOrder,
  PosOrderItem,
  FnbReport,
} from "../api/types";

const { Title, Text } = Typography;

/** 分 → 元（人民币，涨红跌绿非此语境，这里统一正色）。 */
const fmtCents = (c: number) =>
  `¥${(c / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const TABLE_STATE_LABELS: Record<string, { label: string; color: string }> = {
  free: { label: "空闲", color: "green" },
  occupied: { label: "占用", color: "red" },
  cleaning: { label: "清洁中", color: "gold" },
};

function tableStateTag(state: string) {
  const s = TABLE_STATE_LABELS[state] ?? { label: state, color: "default" };
  return <Tag color={s.color}>{s.label}</Tag>;
}

function orderStatusTag(status: string) {
  const settled = status === "settled";
  return (
    <Tag color={settled ? "green" : "processing"}>
      {settled ? "已结" : "未结"}
    </Tag>
  );
}

function settleTypeTag(t: string | null) {
  if (!t) return <Text type="secondary">—</Text>;
  return <Tag color={t === "room" ? "blue" : "purple"}>{t === "room" ? "挂房账" : "现金"}</Tag>;
}

export default function Pos() {
  const { tenantCode, hotelId } = useTenant();
  const [menus, setMenus] = useState<MenuItem[]>([]);
  const [tables, setTables] = useState<DiningTable[]>([]);
  const [orders, setOrders] = useState<PosOrder[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [active, setActive] = useState<PosOrder | null>(null);

  const [loading, setLoading] = useState(false);
  const [menuQuery, setMenuQuery] = useState("");
  const [menuCat, setMenuCat] = useState<string>("ALL");

  const [showOpen, setShowOpen] = useState(false);
  const [openForm] = Form.useForm<PosOrderOpenBody>();

  const [showItem, setShowItem] = useState(false);
  const [itemForm] = Form.useForm<{ name: string; qty: number; unit_price: number }>();
  const [itemBusy, setItemBusy] = useState(false);

  const [settleMode, setSettleMode] = useState<"room" | "cash" | null>(null);
  const [settleForm] = Form.useForm<{ room_no: string; amount_paid?: number | string }>();
  const [settleBusy, setSettleBusy] = useState(false);
  // M32（验收 #48）：挂账前房号查询 —— 展示客人姓名/离店日期，防挂错
  const [roomInfo, setRoomInfo] = useState<Awaited<ReturnType<typeof fnbRoomLookup>> | null>(null);

  const lookupRoom = async (roomNo: string) => {
    const no = roomNo.trim();
    if (!no) {
      setRoomInfo(null);
      return;
    }
    try {
      setRoomInfo(await fnbRoomLookup(tenantCode, no));
    } catch {
      setRoomInfo(null);
    }
  };

  const [showMenuMgr, setShowMenuMgr] = useState(false);
  const [menuForm] = Form.useForm<{ name: string; category?: string; price: number }>();
  const [menuBusy, setMenuBusy] = useState(false);

  // ---------- M27：沽清 / 退菜 / 折扣 ----------
  const [voidTarget, setVoidTarget] = useState<PosOrderItem | null>(null);
  const [voidForm] = Form.useForm<{ reason?: string }>();
  const [voidBusy, setVoidBusy] = useState(false);
  const [showDiscount, setShowDiscount] = useState(false);
  const [discountForm] = Form.useForm<{ mode: "amount" | "percent"; value: number }>();
  const [discountBusy, setDiscountBusy] = useState(false);

  const handleSoldOut = async (item: MenuItem, sold: boolean) => {
    try {
      const updated = await setMenuSoldOut(tenantCode, item.id, sold);
      setMenus((prev) => prev.map((x) => (x.id === item.id ? updated : x)));
      message.success(sold ? `「${item.name}」已沽清，今日停点` : `「${item.name}」恢复供应`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "沽清操作失败");
    }
  };

  const handleVoidItem = async () => {
    if (!active || !voidTarget) return;
    const v = await voidForm.validateFields();
    setVoidBusy(true);
    try {
      await voidPosOrderItem(tenantCode, active.id, voidTarget.id, v.reason);
      message.success("已退菜，账单金额已重算");
      setVoidTarget(null);
      voidForm.resetFields();
      await refreshOrder(active.id);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "退菜失败");
    } finally {
      setVoidBusy(false);
    }
  };

  const handleDiscount = async () => {
    if (!active) return;
    const v = await discountForm.validateFields();
    setDiscountBusy(true);
    try {
      const body =
        v.mode === "percent"
          ? { percent: v.value, operator: "fnb" }
          : { discount_cents: Math.round(v.value * 100), operator: "fnb" };
      const updated = await applyPosOrderDiscount(tenantCode, active.id, body);
      setActive(updated);
      setShowDiscount(false);
      discountForm.resetFields();
      message.success("折扣已应用，结账按折后金额");
      await refreshAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "折扣设置失败");
    } finally {
      setDiscountBusy(false);
    }
  };

  // ---------- 餐饮报表（M22） ----------
  const [showReport, setShowReport] = useState(false);
  const [report, setReport] = useState<FnbReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const openReport = useCallback(async () => {
    if (!tenantCode || !hotelId) {
      message.warning("请先选择门店");
      return;
    }
    setShowReport(true);
    setReportLoading(true);
    try {
      setReport(await fnbReport(tenantCode, hotelId));
    } catch {
      message.error("报表加载失败");
    } finally {
      setReportLoading(false);
    }
  }, [tenantCode, hotelId]);

  // ---------- 数据加载 ----------
  const refreshAll = useCallback(async () => {
    if (!tenantCode || !hotelId) return;
    setLoading(true);
    try {
      const [m, t, o] = await Promise.all([
        listMenuItems(tenantCode, hotelId, true),
        listTables(tenantCode, hotelId),
        listPosOrders(tenantCode, hotelId, "open"),
      ]);
      setMenus(m);
      setTables(t);
      setOrders(o);
      // 保持当前激活账单同步
      setActive((prev) => {
        if (!prev) return null;
        const found = o.find((x) => x.id === prev.id);
        return found ?? null;
      });
      setActiveId((prev) => (o.some((x) => x.id === prev) ? prev : prev));
    } catch {
      message.error("餐饮数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const refreshOrder = useCallback(
    async (id: number) => {
      if (!tenantCode || !hotelId) return;
      const list = await listPosOrders(tenantCode, hotelId, "open");
      setOrders(list);
      const found = list.find((x) => x.id === id) ?? null;
      setActive(found);
      if (!found) setActiveId(null);
    },
    [tenantCode, hotelId]
  );

  // ---------- 桌台：开 / 选单 ----------
  const openOrSelect = useCallback(
    (t: DiningTable) => {
      const existing = orders.find(
        (o) => o.table_id === t.id && o.status === "open"
      );
      if (existing) {
        setActiveId(existing.id);
        setActive(existing);
        return;
      }
      openForm.resetFields();
      openForm.setFieldsValue({ hotel_id: hotelId ?? undefined, table_id: t.id });
      setShowOpen(true);
    },
    [orders, openForm, hotelId]
  );

  const handleOpenSubmit = async () => {
    if (!hotelId) {
      message.warning("请先在顶部选择门店");
      return;
    }
    const v = await openForm.validateFields();
    try {
      const created = await openPosOrder(tenantCode, {
        hotel_id: hotelId,
        table_id: v.table_id ?? null,
        room_no: v.room_no || null,
        guest_name: v.guest_name || null,
      });
      message.success("已开台");
      setShowOpen(false);
      setActiveId(created.id);
      setActive(created);
      await refreshAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "开台失败");
    }
  };

  const handleTableState = async (t: DiningTable, state: string) => {
    try {
      const updated = await setTableState(tenantCode, t.id, state);
      setTables((prev) => prev.map((x) => (x.id === t.id ? updated : x)));
      message.success(`桌台 ${t.table_no} → ${TABLE_STATE_LABELS[state]?.label ?? state}`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "状态切换失败");
    }
  };

  // ---------- 点菜 ----------
  const quickAdd = async (item: MenuItem) => {
    if (!active) {
      message.warning("请先开台或选择一个在开账单");
      return;
    }
    if (active.status === "settled") {
      message.warning("该账单已结账");
      return;
    }
    try {
      await addPosOrderItem(tenantCode, active.id, {
        name: item.name,
        qty: 1,
        unit_price_cents: item.price_cents,
        item_id: item.id,
      });
      message.success(`已加菜：${item.name}`);
      await refreshOrder(active.id);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加菜失败");
    }
  };

  const handleManualAdd = async () => {
    if (!active) {
      message.warning("请先开台或选择一个在开账单");
      return;
    }
    const v = await itemForm.validateFields();
    setItemBusy(true);
    try {
      const body: PosOrderItemBody = {
        name: v.name,
        qty: v.qty ?? 1,
        unit_price_cents: Math.round(v.unit_price * 100),
      };
      await addPosOrderItem(tenantCode, active.id, body);
      message.success("已加菜");
      setShowItem(false);
      itemForm.resetFields();
      await refreshOrder(active.id);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加菜失败");
    } finally {
      setItemBusy(false);
    }
  };

  // ---------- 结账 ----------
  const handleSettle = async () => {
    if (!active || !settleMode) return;
    const v = await settleForm.validateFields();
    setSettleBusy(true);
    try {
      if (settleMode === "room") {
        await settlePosRoom(tenantCode, active.id, {
          room_no: v.room_no,
          operator: "fnb",
        });
        message.success("已挂房账结账");
      } else {
        const paid =
          v.amount_paid != null && v.amount_paid !== ""
            ? Math.round(Number(v.amount_paid) * 100)
            : null;
        await settlePosCash(tenantCode, active.id, {
          amount_paid: paid,
          operator: "fnb",
        });
        message.success("已现金结账");
      }
      setSettleMode(null);
      await refreshAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "结账失败");
    } finally {
      setSettleBusy(false);
    }
  };

  // ---------- 菜品管理（新增） ----------
  const handleCreateMenu = async () => {
    if (!hotelId) {
      message.warning("请先在顶部选择门店");
      return;
    }
    const v = await menuForm.validateFields();
    setMenuBusy(true);
    try {
      await createMenuItem(tenantCode, {
        hotel_id: hotelId,
        name: v.name,
        category: v.category || "其他",
        price_cents: Math.round(v.price * 100),
        is_active: 1,
      });
      message.success("菜品已新增");
      setShowMenuMgr(false);
      menuForm.resetFields();
      await refreshAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "新增失败");
    } finally {
      setMenuBusy(false);
    }
  };

  // ---------- 渲染辅助 ----------
  const categories = useMemo(
    () => Array.from(new Set(menus.map((m) => m.category))),
    [menus]
  );

  const filteredMenu = useMemo(() => {
    const q = menuQuery.trim().toLowerCase();
    return menus.filter((m) => {
      if (menuCat !== "ALL" && m.category !== menuCat) return false;
      if (q && !m.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [menus, menuQuery, menuCat]);

  const itemColumns: ColumnsType<PosOrderItem> = [
    { title: "菜品", dataIndex: "name", key: "name" },
    { title: "数量", dataIndex: "qty", key: "qty", align: "center", width: 70 },
    {
      title: "单价",
      dataIndex: "unit_price_cents",
      key: "unit_price_cents",
      align: "right",
      render: (v: number) => fmtCents(v),
    },
    {
      title: "小计",
      dataIndex: "subtotal_cents",
      key: "subtotal_cents",
      align: "right",
      render: (v: number) => <Text strong>{fmtCents(v)}</Text>,
    },
    {
      title: "状态",
      dataIndex: "voided",
      key: "voided",
      width: 80,
      render: (v: number, row: PosOrderItem) =>
        v ? (
          <Tag color="red">已退</Tag>
        ) : row.kds_status === "served" ? (
          <Tag color="green">已上</Tag>
        ) : (
          <Tag>制作中</Tag>
        ),
    },
    {
      title: "操作",
      key: "void",
      width: 80,
      render: (_: unknown, row: PosOrderItem) =>
        row.voided ? null : (
          <Button
            size="small"
            danger
            icon={<UndoOutlined />}
            disabled={active?.status === "settled"}
            onClick={() => {
              voidForm.resetFields();
              setVoidTarget(row);
            }}
          >
            退菜
          </Button>
        ),
    },
  ];

  const menuColumns: ColumnsType<MenuItem> = [
    { title: "菜名", dataIndex: "name", key: "name" },
    {
      title: "分类",
      dataIndex: "category",
      key: "category",
      width: 90,
      render: (c: string) => <Tag>{c}</Tag>,
    },
    {
      title: "价格",
      dataIndex: "price_cents",
      key: "price_cents",
      align: "right",
      width: 100,
      render: (v: number) => fmtCents(v),
    },
    {
      title: "沽清",
      dataIndex: "sold_out",
      key: "sold_out",
      width: 70,
      align: "center",
      render: (v: number, row: MenuItem) => (
        <Switch
          size="small"
          checked={!!v}
          onChange={(c) => handleSoldOut(row, c)}
        />
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 90,
      render: (_: unknown, row: MenuItem) => (
        <Button
          size="small"
          type="primary"
          icon={<PlusOutlined />}
          disabled={!active || active.status === "settled" || !!row.sold_out}
          onClick={() => quickAdd(row)}
        >
          加1
        </Button>
      ),
    },
  ];

  const orderColumns: ColumnsType<PosOrder> = [
    {
      title: "单号",
      key: "id",
      render: (_: unknown, row: PosOrder) => `#${row.id}`,
    },
    {
      title: "桌台",
      key: "table",
      render: (_: unknown, row: PosOrder) =>
        row.table_id != null
          ? tables.find((t) => t.id === row.table_id)?.table_no ?? `桌#${row.table_id}`
          : "散客",
    },
    {
      title: "客人",
      dataIndex: "guest_name",
      key: "guest_name",
      render: (v: string | null) => v || <Text type="secondary">—</Text>,
    },
    { title: "状态", dataIndex: "status", key: "status", render: (s: string) => orderStatusTag(s) },
    {
      title: "金额",
      dataIndex: "total_cents",
      key: "total_cents",
      align: "right",
      render: (v: number) => fmtCents(v),
    },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, row: PosOrder) => (
        <Button
          size="small"
          type={activeId === row.id ? "default" : "link"}
          onClick={() => {
            setActiveId(row.id);
            setActive(row);
          }}
        >
          {activeId === row.id ? "当前" : "选单"}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Card
        style={{ marginBottom: 16 }}
        styles={{ body: { display: "flex", alignItems: "center", justifyContent: "space-between" } }}
      >
        <Title level={4} style={{ margin: 0 }}>
          餐饮 POS · 点单工作台
        </Title>
        <Space>
          <Button icon={<PlusOutlined />} onClick={() => setShowMenuMgr(true)}>
            菜品管理
          </Button>
          <Button icon={<BarChartOutlined />} onClick={openReport}>
            报表
          </Button>
          <Button icon={<ReloadOutlined />} onClick={refreshAll} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { openForm.resetFields(); openForm.setFieldsValue({ hotel_id: hotelId ?? undefined }); setShowOpen(true); }}>
            开新单
          </Button>
        </Space>
      </Card>

      <Row gutter={16}>
        {/* 左栏：桌台 + 在开账单 */}
        <Col xs={24} lg={9}>
          <Card size="small" title="桌台" style={{ marginBottom: 16 }}>
            {tables.length === 0 ? (
              <Empty description="暂无餐桌，请在菜品管理中维护（或后端新增）" />
            ) : (
              <Row gutter={[12, 12]}>
                {tables.map((t) => (
                  <Col xs={12} sm={8} key={t.id}>
                    <Card
                      size="small"
                      hoverable
                      onClick={() => openOrSelect(t)}
                      styles={{ body: { padding: 12 } }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <Text strong>{t.table_no}</Text>
                        {tableStateTag(t.state)}
                      </div>
                      <div style={{ fontSize: 12, color: "#888", margin: "4px 0 8px" }}>
                        {t.seats} 座{t.zone ? ` · ${t.zone}` : ""}
                      </div>
                      <Select
                        size="small"
                        value={t.state}
                        style={{ width: "100%" }}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(s) => handleTableState(t, s)}
                        options={[
                          { value: "free", label: "空闲" },
                          { value: "occupied", label: "占用" },
                          { value: "cleaning", label: "清洁中" },
                        ]}
                      />
                    </Card>
                  </Col>
                ))}
              </Row>
            )}
          </Card>

          <Card size="small" title="在开账单" styles={{ body: { padding: 0 } }}>
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              loading={loading}
              columns={orderColumns}
              dataSource={orders}
              locale={{ emptyText: "暂无在开账单" }}
            />
          </Card>
        </Col>

        {/* 右栏：当前账单 + 点菜 */}
        <Col xs={24} lg={15}>
          {!active ? (
            <Card>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="请点击左侧桌台开单，或在「在开账单」中选单"
              />
            </Card>
          ) : (
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <Card size="small">
                <Row align="middle" justify="space-between">
                  <Space wrap>
                    <Text strong style={{ fontSize: 16 }}>账单 #{active.id}</Text>
                    {orderStatusTag(active.status)}
                    {settleTypeTag(active.settle_type)}
                    {active.table_id != null && (
                      <Tag color="cyan">
                        {tables.find((t) => t.id === active.table_id)?.table_no ?? `桌#${active.table_id}`}
                      </Tag>
                    )}
                    {active.guest_name && <Tag>{active.guest_name}</Tag>}
                    {active.room_no && <Tag color="blue">房 {active.room_no}</Tag>}
                  </Space>
                  <Space align="center">
                    <Space size={4} direction="vertical" style={{ alignItems: "flex-end" }}>
                      {active.discount_cents > 0 && (
                        <Text delete type="secondary" style={{ fontSize: 13 }}>
                          {fmtCents(active.total_cents)}
                        </Text>
                      )}
                      <Text strong style={{ fontSize: 20, color: "#cf1322", lineHeight: 1.1 }}>
                        {fmtCents(active.total_cents - active.discount_cents)}
                      </Text>
                      {active.discount_cents > 0 && (
                        <Tag color="orange">已优惠 {fmtCents(active.discount_cents)}</Tag>
                      )}
                    </Space>
                    <Button
                      size="small"
                      icon={<PercentageOutlined />}
                      disabled={active.status === "settled"}
                      onClick={() => {
                        discountForm.resetFields();
                        discountForm.setFieldsValue({ mode: "percent" });
                        setShowDiscount(true);
                      }}
                    >
                      折扣
                    </Button>
                  </Space>
                </Row>
              </Card>

              <Card
                size="small"
                title="菜品目录"
                extra={
                  <Space>
                    <Input.Search
                      allowClear
                      placeholder="搜索菜名"
                      style={{ width: 150 }}
                      value={menuQuery}
                      onChange={(e) => setMenuQuery(e.target.value)}
                    />
                    <Select
                      style={{ width: 110 }}
                      value={menuCat}
                      onChange={setMenuCat}
                      options={[
                        { value: "ALL", label: "全部分类" },
                        ...categories.map((c) => ({ value: c, label: c })),
                      ]}
                    />
                    <Button
                      icon={<PlusOutlined />}
                      onClick={() => { itemForm.resetFields(); setShowItem(true); }}
                      disabled={active.status === "settled"}
                    >
                      手动加菜
                    </Button>
                  </Space>
                }
              >
                <Table
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 6 }}
                  columns={menuColumns}
                  dataSource={filteredMenu}
                  locale={{ emptyText: "无匹配菜品" }}
                />
              </Card>

              <Card size="small" title={`已点明细（${active.items.length} 项）`}>
                <Table
                  rowKey="id"
                  size="small"
                  pagination={false}
                  columns={itemColumns}
                  dataSource={active.items}
                  locale={{ emptyText: "尚未点菜" }}
                />
                <Row justify="end" style={{ marginTop: 12 }}>
                  <Space>
                    <Popconfirm
                      title="挂房账结账"
                      description="消费将计入客房在开账单，要求该房有在开账单。"
                      disabled={active.status === "settled"}
                      onConfirm={() => { settleForm.resetFields(); setSettleMode("room"); }}
                    >
                      <Button icon={<ShoppingCartOutlined />} disabled={active.status === "settled"}>
                        挂房账
                      </Button>
                    </Popconfirm>
                    <Button
                      type="primary"
                      disabled={active.status === "settled"}
                      onClick={() => { settleForm.resetFields(); setSettleMode("cash"); }}
                    >
                      现金结账
                    </Button>
                  </Space>
                </Row>
                {active.status === "settled" && (
                  <Text type="secondary">该账单已结账，可重新开台或选其他在开账单。</Text>
                )}
              </Card>
            </Space>
          )}
        </Col>
      </Row>

      {/* 退菜 Modal（M27） */}
      <Modal
        title={`退菜：${voidTarget?.name ?? ""}`}
        open={voidTarget != null}
        onOk={handleVoidItem}
        confirmLoading={voidBusy}
        onCancel={() => setVoidTarget(null)}
        okText="确认退菜"
        okButtonProps={{ danger: true }}
        cancelText="取消"
      >
        <Form form={voidForm} layout="vertical">
          <Form.Item name="reason" label="退菜原因（可选，留痕用）">
            <Input placeholder="如：客人不吃辣 / 上错菜" maxLength={128} />
          </Form.Item>
          <Typography.Paragraph type="secondary">
            退菜后账单总额即时重算；若已有整单折扣，折扣将自动收敛至不超过新总额。
          </Typography.Paragraph>
        </Form>
      </Modal>

      {/* 整单折扣 Modal（M27） */}
      <Modal
        title="整单折扣"
        open={showDiscount}
        onOk={handleDiscount}
        confirmLoading={discountBusy}
        onCancel={() => setShowDiscount(false)}
        okText="应用折扣"
        cancelText="取消"
      >
        <Form form={discountForm} layout="vertical" initialValues={{ mode: "percent" }}>
          <Form.Item name="mode" label="折扣方式">
            <Select
              options={[
                { value: "percent", label: "按百分比（1-99）" },
                { value: "amount", label: "按金额（元）" },
              ]}
            />
          </Form.Item>
          <Form.Item name="value" label="折扣值" rules={[{ required: true, message: "请输入折扣值" }]}>
            <InputNumber min={0} max={999999} style={{ width: "100%" }} placeholder="百分比填 10 = 九折优惠 10%" />
          </Form.Item>
          <Typography.Paragraph type="secondary">
            折扣不可超过账单总额；现金结账按折后金额收款，挂房账按折后金额入客房账单。
          </Typography.Paragraph>
        </Form>
      </Modal>

      {/* 开新单 Modal */}
      <Modal
        title="开台 / 开新单"
        open={showOpen}
        onOk={handleOpenSubmit}
        onCancel={() => setShowOpen(false)}
        okText="开台"
        cancelText="取消"
      >
        <Form form={openForm} layout="vertical" initialValues={{ hotel_id: hotelId ?? undefined }}>
          <Form.Item name="table_id" label="关联桌台（可选）">
            <Select
              allowClear
              placeholder="不关联（散客单）"
              options={tables.map((t) => ({ value: t.id, label: `${t.table_no}（${TABLE_STATE_LABELS[t.state]?.label ?? t.state}）` }))}
            />
          </Form.Item>
          <Form.Item name="guest_name" label="客人姓名（可选）">
            <Input placeholder="如：张三" maxLength={64} />
          </Form.Item>
          <Form.Item name="room_no" label="关联房号（可选，用于挂房账）">
            <Input placeholder="如：401" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 手动加菜 Modal */}
      <Modal
        title="手动加菜（非目录菜品）"
        open={showItem}
        onOk={handleManualAdd}
        confirmLoading={itemBusy}
        onCancel={() => setShowItem(false)}
        okText="加入账单"
        cancelText="取消"
      >
        <Form form={itemForm} layout="vertical" initialValues={{ qty: 1 }}>
          <Form.Item name="name" label="菜品名称" rules={[{ required: true, message: "请输入菜名" }]}>
            <Input placeholder="如：定制套餐" maxLength={128} />
          </Form.Item>
          <Form.Item name="qty" label="数量" rules={[{ required: true }]}>
            <InputNumber min={1} max={999} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="unit_price" label="单价（元）" rules={[{ required: true, message: "请输入单价" }]}>
            <InputNumber addonBefore="¥" min={0} step={1} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 挂房账 Modal */}
      <Modal
        title="挂房账结账"
        open={settleMode === "room"}
        onOk={handleSettle}
        confirmLoading={settleBusy}
        onCancel={() => { setSettleMode(null); setRoomInfo(null); }}
        okText="确认挂账"
        cancelText="取消"
      >
        <Form form={settleForm} layout="vertical">
          <Form.Item
            name="room_no"
            label="客房房号"
            rules={[{ required: true, message: "请输入房号" }]}
          >
            <Input placeholder="如：401，该房需有在开账单" />
          </Form.Item>
          <Typography.Paragraph type="secondary">
            消费将计入该客房的在开账单（统一走 Bill 入账，余额 = Σ应收 − Σ实收）。
          </Typography.Paragraph>
        </Form>
      </Modal>

      {/* 现金结账 Modal */}
      <Modal
        title="现金结账"
        open={settleMode === "cash"}
        onOk={handleSettle}
        confirmLoading={settleBusy}
        onCancel={() => setSettleMode(null)}
        okText="确认收款"
        cancelText="取消"
      >
        <Form form={settleForm} layout="vertical">
          <Form.Item name="amount_paid" label="收款金额（元，留空按账单总额）">
            <InputNumber
              addonBefore="¥"
              min={0}
              step={1}
              style={{ width: "100%" }}
              placeholder={`账单总额 ${active ? fmtCents(active.total_cents) : ""}`}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 菜品管理 Drawer */}
      <Drawer
        title="菜品管理"
        width={520}
        open={showMenuMgr}
        onClose={() => setShowMenuMgr(false)}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateMenu} loading={menuBusy}>
            新增菜品
          </Button>
        }
      >
        <Form form={menuForm} layout="vertical" style={{ marginBottom: 16 }}>
          <Form.Item name="name" label="菜名" rules={[{ required: true, message: "请输入菜名" }]}>
            <Input placeholder="如：宫保鸡丁" maxLength={128} />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Select
              defaultValue="其他"
              options={[
                { value: "热菜", label: "热菜" },
                { value: "凉菜", label: "凉菜" },
                { value: "酒水", label: "酒水" },
                { value: "主食", label: "主食" },
                { value: "其他", label: "其他" },
              ]}
            />
          </Form.Item>
          <Form.Item name="price" label="价格（元）" rules={[{ required: true, message: "请输入价格" }]}>
            <InputNumber addonBefore="¥" min={0} step={1} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
        <Table
          rowKey="id"
          size="small"
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "菜名", dataIndex: "name" },
            { title: "分类", dataIndex: "category", render: (c: string) => <Tag>{c}</Tag> },
            { title: "价格", dataIndex: "price_cents", align: "right", render: (v: number) => fmtCents(v) },
            {
              title: "沽清",
              dataIndex: "sold_out",
              width: 70,
              align: "center",
              render: (v: number, row: MenuItem) => (
                <Switch size="small" checked={!!v} onChange={(c) => handleSoldOut(row, c)} />
              ),
            },
          ]}
          dataSource={menus}
          locale={{ emptyText: "暂无菜品" }}
        />
      </Drawer>

      {/* 餐饮报表 Drawer（M22） */}
      <Drawer
        title="餐饮销售报表"
        width={560}
        open={showReport}
        onClose={() => setShowReport(false)}
      >
        {reportLoading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="报表加载中…" />
        ) : !report || report.order_count === 0 ? (
          <Empty description="暂无已结账餐饮数据" />
        ) : (
          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <Row gutter={12}>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="总营收" value={fmtCents(report.total_revenue_cents)} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="已结单数" value={report.order_count} suffix="单" />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <Statistic title="桌均消费" value={fmtCents(report.avg_per_table_cents)} />
                </Card>
              </Col>
            </Row>

            <Card size="small" title="品类销售">
              <Table
                rowKey="category"
                size="small"
                pagination={false}
                columns={[
                  { title: "品类", dataIndex: "category" },
                  { title: "数量", dataIndex: "qty", align: "center", width: 80 },
                  {
                    title: "营收",
                    dataIndex: "revenue_cents",
                    align: "right",
                    render: (v: number) => <Text strong>{fmtCents(v)}</Text>,
                  },
                ]}
                dataSource={report.by_category}
                locale={{ emptyText: "暂无" }}
              />
            </Card>

            <Card size="small" title="桌均消费（按桌台）">
              <Table
                rowKey="table_no"
                size="small"
                pagination={false}
                columns={[
                  { title: "桌台", dataIndex: "table_no" },
                  { title: "单数", dataIndex: "order_count", align: "center", width: 80 },
                  {
                    title: "营收",
                    dataIndex: "revenue_cents",
                    align: "right",
                    render: (v: number) => fmtCents(v),
                  },
                ]}
                dataSource={report.by_table}
                locale={{ emptyText: "无关联餐桌的账单" }}
              />
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
