import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Dropdown, Input, Layout, Menu, Select, Spin, Tabs, Tag, Typography } from "antd";
import type { MenuProps } from "antd";
import {
  DashboardOutlined,
  BankOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  CalendarOutlined,
  CreditCardOutlined,
  FileDoneOutlined,
  AuditOutlined,
  GiftOutlined,
  ToolOutlined,
  BellOutlined,
  AlertOutlined,
  ClusterOutlined,
  CrownOutlined,
  MoneyCollectOutlined,
  ReconciliationOutlined,
  TeamOutlined,
  FileSearchOutlined,
  SafetyCertificateOutlined,
  ClockCircleOutlined,
  CoffeeOutlined,
  FireOutlined,
  CustomerServiceOutlined,
  IdcardOutlined,
  TagsOutlined,
  LineChartOutlined,
  MobileOutlined,
  ApiOutlined,
  RobotOutlined,
  HomeOutlined,
  KeyOutlined,
  DesktopOutlined,
  SwapOutlined,
  ControlOutlined,
  CloudUploadOutlined,
  FileTextOutlined,
  SearchOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from "@ant-design/icons";
import { useLocation, useNavigate, useRoutes } from "react-router-dom";
import { layoutRoutes } from "../App";
import { useTenant } from "../store/tenant";
import { getUnreadCount } from "../api/endpoints";
import { getToken, wsBase } from "../api/http";
import { NOTIFY_CHANGED_EVENT } from "../pages/Notifications";
import SearchDrawer from "../components/SearchDrawer";

const { Header, Sider, Content } = Layout;

/**
 * 菜单按「业务大类」归纳（M35a）。
 * 12 个一级分组，全部带 children；顺序：前厅 → 客房 → 餐饮 → 客户 → 财务 →
 * 价格 → 集团 → 渠道 → 智能 → 经营总览 → 基础 → 系统。
 * 前厅置顶（最高频），经营总览居中偏后（概览类非操作入口）。
 */
const baseItems: MenuProps["items"] = [
  {
    key: "front-desk",
    icon: <DesktopOutlined />,
    label: "前厅",
    children: [
      { key: "/bookings", icon: <CalendarOutlined />, label: "预订管理" },
      { key: "/billing", icon: <CreditCardOutlined />, label: "前台收银" },
      { key: "/reception", icon: <DesktopOutlined />, label: "前台接待" },
      { key: "/reception-workbench", icon: <IdcardOutlined />, label: "统一接待台" },
      { key: "/check-in-register", icon: <IdcardOutlined />, label: "登记入住" },
      { key: "/rooms", icon: <AppstoreOutlined />, label: "房态盘" },
      { key: "/guests", icon: <IdcardOutlined />, label: "宾客档案" },
      { key: "/breakfast", icon: <CoffeeOutlined />, label: "早餐券" },
      { key: "/complaints", icon: <CustomerServiceOutlined />, label: "投诉管理" },
      { key: "/shifts", icon: <ReconciliationOutlined />, label: "前台交班" },
    ],
  },
  {
    key: "housekeeping-ops",
    icon: <HomeOutlined />,
    label: "客房运营",
    children: [
      { key: "/housekeeping", icon: <ToolOutlined />, label: "清扫工单" },
      { key: "/nightaudit", icon: <FileDoneOutlined />, label: "夜审日报" },
      { key: "/group-blocks", icon: <TeamOutlined />, label: "团队排房" },
      { key: "/wakeup", icon: <ClockCircleOutlined />, label: "叫醒服务" },
      { key: "/psb", icon: <IdcardOutlined />, label: "公安报送" },
    ],
  },
  {
    key: "fnb",
    icon: <CoffeeOutlined />,
    label: "餐饮",
    children: [
      { key: "/pos", icon: <CoffeeOutlined />, label: "餐饮 POS" },
      { key: "/kds", icon: <FireOutlined />, label: "厨房出单" },
    ],
  },
  {
    key: "crm",
    icon: <CrownOutlined />,
    label: "客户与协议",
    children: [
      { key: "/members", icon: <CrownOutlined />, label: "会员管理" },
      { key: "/ar-accounts", icon: <TeamOutlined />, label: "协议挂账" },
    ],
  },
  {
    key: "finance",
    icon: <MoneyCollectOutlined />,
    label: "财务",
    children: [
      { key: "/commission", icon: <MoneyCollectOutlined />, label: "佣金规则" },
      { key: "/reconciliation", icon: <ReconciliationOutlined />, label: "支付对账" },
      { key: "/adjustments", icon: <SwapOutlined />, label: "调账中心" },
      { key: "/deposits", icon: <CreditCardOutlined />, label: "押金管理" },
      { key: "/invoices", icon: <FileDoneOutlined />, label: "发票管理" },
      { key: "/coupons", icon: <GiftOutlined />, label: "优惠券管理" },
    ],
  },
  {
    key: "yield",
    icon: <TagsOutlined />,
    label: "价格",
    children: [
      { key: "/rates", icon: <TagsOutlined />, label: "价格库存中心" },
      { key: "/rate-calendar", icon: <CalendarOutlined />, label: "价格日历" },
      { key: "/yield", icon: <LineChartOutlined />, label: "收益管理" },
    ],
  },
  {
    key: "group",
    icon: <ClusterOutlined />,
    label: "集团",
    children: [
      { key: "/group", icon: <ClusterOutlined />, label: "集团驾驶舱" },
      { key: "/price-policy", icon: <ControlOutlined />, label: "集团价策" },
    ],
  },
  {
    key: "channel",
    icon: <MobileOutlined />,
    label: "渠道",
    children: [
      { key: "/mp-orders", icon: <MobileOutlined />, label: "移动端直订" },
      { key: "/openapi", icon: <ApiOutlined />, label: "开放平台" },
      { key: "/channel-push", icon: <CloudUploadOutlined />, label: "OTA 推送" },
      { key: "/channel-center", icon: <ClusterOutlined />, label: "OTA 渠道中心" },
    ],
  },
  {
    key: "ai",
    icon: <RobotOutlined />,
    label: "智能",
    children: [
      { key: "/ai-chat", icon: <RobotOutlined />, label: "AI 客服中心" },
      { key: "/alerts", icon: <AlertOutlined />, label: "AI 预警" },
    ],
  },
  {
    key: "overview",
    icon: <DashboardOutlined />,
    label: "经营总览",
    children: [
      { key: "/dashboard", icon: <DashboardOutlined />, label: "经营概览" },
      { key: "/analytics", icon: <BarChartOutlined />, label: "经营分析" },
      { key: "/reports", icon: <FileTextOutlined />, label: "报表中心" },
    ],
  },
  {
    key: "base",
    icon: <BankOutlined />,
    label: "基础数据",
    children: [
      { key: "/room-types", icon: <HomeOutlined />, label: "房型管理" },
      { key: "/rooms-inventory", icon: <KeyOutlined />, label: "房间管理" },
      { key: "/tenants", icon: <BankOutlined />, label: "门店管理" },
    ],
  },
  {
    key: "system",
    icon: <SafetyCertificateOutlined />,
    label: "系统",
    children: [
      { key: "/users", icon: <TeamOutlined />, label: "用户与角色" },
      { key: "/audit", icon: <FileSearchOutlined />, label: "审计日志" },
      { key: "/approvals", icon: <AuditOutlined />, label: "审批中心" },
      { key: "/notifications", icon: <BellOutlined />, label: "通知中心" },
    ],
  },
];

/** 一级分组 key（用于 onClick 拦截：点击分组标题不跳转） */
const GROUP_KEYS = [
  "front-desk",
  "housekeeping-ops",
  "fnb",
  "crm",
  "finance",
  "yield",
  "group",
  "channel",
  "ai",
  "overview",
  "base",
  "system",
];

/** 菜单 key（路径）→ 页面名，供选项卡标签使用 */
const PATH_LABELS: Record<string, string> = (() => {
  const map: Record<string, string> = {};
  const walk = (list: MenuProps["items"]) =>
    (list || []).forEach((it: any) => {
      if (it?.children) walk(it.children);
      else if (typeof it?.key === "string" && it.key.startsWith("/")) map[it.key] = it.label;
    });
  walk(baseItems);
  return map;
})();

/** 单个选项卡内容：按固定 path 渲染对应路由元素（keep-alive，切走不卸载） */
function TabPage({ path, search }: { path: string; search: string }) {
  const location = useLocation();
  // 仅激活 Tab 透传当前 URL query，保证 useSearchParams 页面（登记入住/账务等）能拿到参数
  const element = useRoutes(layoutRoutes, {
    pathname: path,
    search: path === location.pathname ? search : undefined,
  });
  return <>{element}</>;
}

/** 把未读数注入「通知中心」菜单项（角标） */
function buildItems(unread: number): MenuProps["items"] {
  const inject = (list: MenuProps["items"]): MenuProps["items"] =>
    (list || []).map((it: any) => {
      if (it.children) return { ...it, children: inject(it.children) };
      if (it.key === "/notifications" && unread > 0) {
        return {
          ...it,
          label: (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              通知中心
              <Badge count={unread} overflowCount={99} />
            </span>
          ),
        };
      }
      return it;
    });
  return inject(baseItems);
}

/**
 * 路径精确命中某一路由段（避免 /rooms 误吞 /rooms-inventory、/group 误吞 /group-blocks）。
 * @param path 当前 location.pathname
 * @param seg 路由段，例如 "/rooms"
 */
function hit(path: string, seg: string): boolean {
  return path === seg || path.startsWith(`${seg}/`);
}

/** 当前路径所属的业务大类（决定菜单默认展开哪一个分组） */
function parentKey(path: string): string | undefined {
  if (
    hit(path, "/bookings") || hit(path, "/billing") || hit(path, "/reception") ||
    hit(path, "/reception-workbench") || hit(path, "/check-in-register") ||
    hit(path, "/rooms") || hit(path, "/guests") || hit(path, "/breakfast") ||
    hit(path, "/complaints") || hit(path, "/shifts")
  ) return "front-desk";
  if (
    hit(path, "/housekeeping") || hit(path, "/nightaudit") ||
    hit(path, "/group-blocks") || hit(path, "/wakeup") || hit(path, "/psb")
  ) return "housekeeping-ops";
  if (hit(path, "/pos") || hit(path, "/kds")) return "fnb";
  if (hit(path, "/members") || hit(path, "/ar-accounts")) return "crm";
  if (
    hit(path, "/commission") || hit(path, "/reconciliation") ||
    hit(path, "/adjustments") || hit(path, "/deposits") ||
    hit(path, "/invoices") || hit(path, "/coupons")
  ) return "finance";
  if (hit(path, "/rates") || hit(path, "/rate-calendar") || hit(path, "/yield")) return "yield";
  if (hit(path, "/group") || hit(path, "/price-policy")) return "group";
  if (
    hit(path, "/mp-orders") || hit(path, "/openapi") ||
    hit(path, "/channel-push") || hit(path, "/channel-center")
  ) return "channel";
  if (hit(path, "/ai-chat") || hit(path, "/alerts")) return "ai";
  if (hit(path, "/dashboard") || hit(path, "/analytics") || hit(path, "/reports")) return "overview";
  if (hit(path, "/room-types") || hit(path, "/rooms-inventory") || hit(path, "/tenants")) return "base";
  if (
    hit(path, "/users") || hit(path, "/audit") ||
    hit(path, "/approvals") || hit(path, "/notifications")
  ) return "system";
  return undefined;
}

export default function AppLayout() {
  const { tenants, tenantCode, setTenant, hotels, hotelId, setHotel, loading } =
    useTenant();
  const navigate = useNavigate();
  const location = useLocation();
  const openKey = parentKey(location.pathname);
  const user = localStorage.getItem("pms_user");
  const [unread, setUnread] = useState(0);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  // Sider 折叠态（M35a）：收起后仅显示图标，宽度 80
  const [collapsed, setCollapsed] = useState(false);
  // 受控展开项：切换业务大类时自动展开对应分组；折叠时清空避免弹出层常驻
  const [openKeys, setOpenKeys] = useState<string[]>(openKey ? [openKey] : []);

  const loadUnread = async () => {
    if (!tenantCode) return;
    try {
      setUnread(await getUnreadCount(tenantCode));
    } catch {
      /* 角标失败不打扰主流程 */
    }
  };

  useEffect(() => {
    loadUnread();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  useEffect(() => {
    const onChanged = () => loadUnread();
    window.addEventListener(NOTIFY_CHANGED_EVENT, onChanged);
    const timer = window.setInterval(loadUnread, 60_000);
    const onVisible = () => document.visibilityState === "visible" && loadUnread();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener(NOTIFY_CHANGED_EVENT, onChanged);
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  // ⑤ 实时推送：建立 /ws/notifications 长连接，命中本人角色的通知即时刷新角标。
  // 既有 60s 轮询 + 可见性恢复作为兜底，WS 仅提供低延迟体验，断连不影响正确性。
  useEffect(() => {
    if (!tenantCode) return;
    const token = getToken();
    if (!token) return;
    const ws = new WebSocket(
      `${wsBase()}/ws/notifications?tenant_id=${encodeURIComponent(tenantCode)}&token=${encodeURIComponent(token)}`
    );
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg && msg.type === "notification") {
          loadUnread();
          window.dispatchEvent(new Event(NOTIFY_CHANGED_EVENT));
        }
      } catch {
        /* 忽略非法消息帧 */
      }
    };
    return () => {
      try {
        ws.close();
      } catch {
        /* noop */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  // 路由切换时展开命中的业务大类；折叠时收起全部（antd 折叠态下 openKeys 会驱动弹出层）
  useEffect(() => {
    if (collapsed) {
      setOpenKeys([]);
      return;
    }
    if (openKey) setOpenKeys((prev) => (prev.includes(openKey) ? prev : [...prev, openKey]));
  }, [collapsed, openKey]);

  const items = useMemo(() => buildItems(unread), [unread]);

  // 选项卡式导航：菜单每打开一个页面即新增一个选项卡（已存在则激活）
  const [tabs, setTabs] = useState<{ key: string; label: string }[]>([]);
  useEffect(() => {
    if (location.pathname === "/") return;
    setTabs((prev) => {
      if (prev.some((t) => t.key === location.pathname)) return prev;
      const label =
        PATH_LABELS[location.pathname] ||
        decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "页面");
      return [...prev, { key: location.pathname, label }];
    });
  }, [location.pathname]);

  const removeTab = (targetKey: string) => {
    const idx = tabs.findIndex((t) => t.key === targetKey);
    if (idx < 0) return;
    const next = tabs.filter((t) => t.key !== targetKey);
    const finalTabs = next.length ? next : [{ key: "/dashboard", label: PATH_LABELS["/dashboard"] || "经营概览" }];
    setTabs(finalTabs);
    if (location.pathname === targetKey) {
      const fallback = finalTabs[Math.min(idx, finalTabs.length - 1)];
      navigate(fallback.key);
    }
  };

  // 刷新：按 Tab 记一个自增 tick，key 变化即重挂载该页面
  const [refreshTick, setRefreshTick] = useState<Record<string, number>>({});
  const refreshTab = (key: string) =>
    setRefreshTick((prev) => ({ ...prev, [key]: (prev[key] || 0) + 1 }));

  const closeOthers = (key: string) => {
    const keep = tabs.find((t) => t.key === key);
    if (!keep) return;
    setTabs([keep]);
    if (location.pathname !== key) navigate(key);
  };

  const closeAll = () => {
    const home = { key: "/dashboard", label: PATH_LABELS["/dashboard"] || "经营概览" };
    setTabs([home]);
    navigate(home.key);
  };

  /** 右键菜单：刷新当前 Tab / 关闭其他 / 关闭全部 */
  const tabContextMenu = (t: { key: string; label: string }) => (
    <Dropdown
      trigger={["contextMenu"]}
      menu={{
        items: [
          { key: "refresh", label: "刷新当前 Tab" },
          { key: "closeOthers", label: "关闭其他", disabled: tabs.length <= 1 },
          { key: "closeAll", label: "关闭全部" },
        ],
        onClick: ({ key, domEvent }) => {
          domEvent.stopPropagation();
          if (key === "refresh") refreshTab(t.key);
          else if (key === "closeOthers") closeOthers(t.key);
          else if (key === "closeAll") closeAll();
        },
      }}
    >
      <span style={{ userSelect: "none" }}>{t.label}</span>
    </Dropdown>
  );

  if (loading) {
    return (
      <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
        <Spin tip="加载中…" size="large">
          <div style={{ width: 200, height: 80 }} />
        </Spin>
      </div>
    );
  }

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        theme="dark"
        width={208}
        collapsedWidth={80}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        breakpoint="lg"
      >
        {/* Logo 区：折叠态只保留渐变方块 */}
        <div
          style={{
            color: "#fff",
            padding: collapsed ? "18px 16px" : "18px 16px 16px",
            borderBottom: "1px solid rgba(255,255,255,.08)",
            marginBottom: 4,
            display: "flex",
            alignItems: "center",
            justifyContent: collapsed ? "center" : "flex-start",
            gap: 10,
          }}
        >
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              background: "linear-gradient(135deg, #1677ff 0%, #69b1ff 100%)",
              display: "grid",
              placeItems: "center",
              fontWeight: 700,
              fontSize: 14,
              color: "#fff",
              boxShadow: "0 2px 8px rgba(22,119,255,.5)",
              flexShrink: 0,
            }}
          >
            P
          </div>
          {!collapsed && (
            <div>
              <div
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  letterSpacing: 0.5,
                  lineHeight: 1.2,
                }}
              >
                PMS Cloud
              </div>
              <div
                style={{
                  fontSize: 10.5,
                  color: "rgba(255,255,255,.55)",
                  letterSpacing: 0.4,
                  marginTop: 2,
                }}
              >
                酒店集团经营中台
              </div>
            </div>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          openKeys={openKeys}
          onOpenChange={(keys) => setOpenKeys(keys as string[])}
          items={items}
          onClick={({ key }) => {
            if (!GROUP_KEYS.includes(key as string)) navigate(key as string);
          }}
        />
      </Sider>
      {/* 自定义折叠按钮：固定在 Sider 右边缘（隐藏 antd 默认 trigger，避免双按钮） */}
      <Button
        type="text"
        icon={
          collapsed ? (
            <MenuUnfoldOutlined style={{ color: "#fff", fontSize: 16 }} />
          ) : (
            <MenuFoldOutlined style={{ color: "#fff", fontSize: 14 }} />
          )
        }
        onClick={() => setCollapsed((v) => !v)}
        title={collapsed ? "展开菜单" : "收起菜单"}
        style={{
          position: "fixed",
          left: collapsed ? 80 : 180,
          top: 76,
          zIndex: 100,
          width: 28,
          height: 28,
          padding: 0,
          background: "rgba(22,119,255,0.85)",
          borderRadius: "0 8px 8px 0",
          transition: "left 0.2s ease",
        }}
      />
      <Layout>
        <Header
          style={{
            background: "#fff",
            padding: "0 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
            borderBottom: "1px solid #eef0f4",
          }}
        >
          <Typography.Title
            level={4}
            style={{ margin: 0, fontWeight: 600, letterSpacing: 0.5 }}
          >
            酒店管理系统
          </Typography.Title>
          <Input
            placeholder="搜索菜单、订单、宾客…（按 Enter）"
            prefix={<SearchOutlined style={{ color: "#b8bfc7" }} />}
            style={{ maxWidth: 360, flex: 1, margin: "0 32px", borderRadius: 8 }}
            allowClear
            onPressEnter={(e) => {
              const v = (e.target as HTMLInputElement).value.trim();
              if (v) {
                setSearchQuery(v);
                setSearchOpen(true);
              }
            }}
            onClick={(e) => (e.target as HTMLInputElement).select()}
          />
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Badge count={unread} overflowCount={99} size="small">
              <Button
                type="text"
                icon={<BellOutlined style={{ fontSize: 18 }} />}
                onClick={() => navigate("/notifications")}
                title="通知中心"
              />
            </Badge>
            {user && <Tag color="blue">{user}</Tag>}
            <Select
              value={tenantCode}
              style={{ width: 200 }}
              onChange={(v) => setTenant(v)}
              options={tenants.map((t) => ({
                value: t.code,
                label: `${t.name}（${t.code}）`,
              }))}
              placeholder="选择租户"
            />
            <Select
              value={hotelId ?? undefined}
              style={{ width: 200 }}
              onChange={(v) => setHotel(v)}
              disabled={!hotels.length}
              options={hotels.map((h) => ({
                value: h.id,
                label: `${h.name}（${h.code}）`,
              }))}
              placeholder="选择门店"
            />
          </div>
        </Header>
        <Content style={{ margin: 16 }}>
          <Tabs
            type="editable-card"
            hideAdd
            activeKey={location.pathname}
            onChange={(k) => navigate(k)}
            onEdit={(targetKey, action) => {
              if (action === "remove") removeTab(targetKey as string);
            }}
            tabBarStyle={{ marginBottom: 0 }}
            items={tabs.map((t) => ({
              key: t.key,
              label: tabContextMenu(t),
              closable: tabs.length > 1,
              children: (
                <div style={{ padding: 16, minHeight: "calc(100vh - 176px)" }}>
                  <TabPage
                    key={`${t.key}#${refreshTick[t.key] || 0}`}
                    path={t.key}
                    search={location.search}
                  />
                </div>
              ),
            }))}
          />
        </Content>
      </Layout>
      <SearchDrawer
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        initialQuery={searchQuery}
      />
    </Layout>
  );
}
