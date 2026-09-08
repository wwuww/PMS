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
} from "@ant-design/icons";
import { useLocation, useNavigate, useRoutes } from "react-router-dom";
import { layoutRoutes } from "../App";
import { useTenant } from "../store/tenant";
import { getUnreadCount } from "../api/endpoints";
import { getToken, wsBase } from "../api/http";
import { NOTIFY_CHANGED_EVENT } from "../pages/Notifications";

const { Header, Sider, Content } = Layout;

const baseItems: MenuProps["items"] = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "经营概览" },
  { key: "/bookings", icon: <CalendarOutlined />, label: "预订管理" },
  { key: "/billing", icon: <CreditCardOutlined />, label: "前台收银" },
  { key: "/pos", icon: <CoffeeOutlined />, label: "餐饮 POS" },
  { key: "/kds", icon: <FireOutlined />, label: "厨房出单" },
  { key: "/complaints", icon: <CustomerServiceOutlined />, label: "投诉管理" },
  { key: "/ar-accounts", icon: <TeamOutlined />, label: "协议挂账" },
  { key: "/rooms", icon: <AppstoreOutlined />, label: "房态盘" },
  { key: "/reception", icon: <DesktopOutlined />, label: "前台接待" },
  { key: "/reception-workbench", icon: <IdcardOutlined />, label: "统一接待台" },
  { key: "/check-in-register", icon: <IdcardOutlined />, label: "登记入住" },
  { key: "/guests", icon: <IdcardOutlined />, label: "宾客档案" },
  {
    key: "ops",
    icon: <ToolOutlined />,
    label: "运营中心",
    children: [
      { key: "/nightaudit", icon: <FileDoneOutlined />, label: "夜审日报" },
      { key: "/approvals", icon: <AuditOutlined />, label: "审批中心" },
      { key: "/housekeeping", icon: <ToolOutlined />, label: "清扫工单" },
      { key: "/notifications", icon: <BellOutlined />, label: "通知中心" },
      { key: "/wakeup", icon: <ClockCircleOutlined />, label: "叫醒服务" },
      { key: "/psb", icon: <IdcardOutlined />, label: "公安报送" },
      { key: "/shifts", icon: <ReconciliationOutlined />, label: "前台交班" },
      { key: "/group-blocks", icon: <TeamOutlined />, label: "团队排房" },
    ],
  },
  {
    key: "crm",
    icon: <CrownOutlined />,
    label: "客户关系",
    children: [{ key: "/members", icon: <CrownOutlined />, label: "会员管理" }],
  },
  {
    key: "fin",
    icon: <MoneyCollectOutlined />,
    label: "财务中心",
    children: [
      { key: "/commission", icon: <MoneyCollectOutlined />, label: "佣金规则" },
      { key: "/reconciliation", icon: <ReconciliationOutlined />, label: "支付对账" },
      { key: "/adjustments", icon: <SwapOutlined />, label: "调账中心" },
      { key: "/deposits", icon: <CreditCardOutlined />, label: "押金管理" },
    ],
  },
  {
    key: "risk",
    icon: <AlertOutlined />,
    label: "风控中心",
    children: [{ key: "/alerts", icon: <AlertOutlined />, label: "AI 预警" }],
  },
  {
    key: "group",
    icon: <ClusterOutlined />,
    label: "集团管控",
    children: [
      { key: "/group", icon: <ClusterOutlined />, label: "集团驾驶舱" },
      { key: "/price-policy", icon: <ControlOutlined />, label: "集团价策" },
    ],
  },
  {
    key: "sec",
    icon: <SafetyCertificateOutlined />,
    label: "安全中心",
    children: [
      { key: "/users", icon: <TeamOutlined />, label: "用户与角色" },
      { key: "/audit", icon: <FileSearchOutlined />, label: "审计日志" },
    ],
  },
  { key: "/analytics", icon: <BarChartOutlined />, label: "经营分析" },
  { key: "/reports", icon: <FileTextOutlined />, label: "报表中心" },
  {
    key: "yield",
    icon: <TagsOutlined />,
    label: "价格收益",
    children: [
      { key: "/rates", icon: <TagsOutlined />, label: "价格库存中心" },
      { key: "/rate-calendar", icon: <CalendarOutlined />, label: "价格日历" },
      { key: "/yield", icon: <LineChartOutlined />, label: "收益管理" },
    ],
  },
  {
    key: "base",
    icon: <HomeOutlined />,
    label: "基础数据",
    children: [
      { key: "/room-types", icon: <HomeOutlined />, label: "房型管理" },
      { key: "/rooms-inventory", icon: <KeyOutlined />, label: "房间管理" },
    ],
  },
  {
    key: "channel",
    icon: <MobileOutlined />,
    label: "渠道与平台",
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
    label: "智能客服",
    children: [{ key: "/ai-chat", icon: <RobotOutlined />, label: "AI 客服中心" }],
  },
  { key: "/tenants", icon: <BankOutlined />, label: "门店管理" },
];

const GROUP_KEYS = ["ops", "crm", "fin", "risk", "group", "sec", "yield", "channel", "ai", "base"];

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

function parentKey(path: string): string | undefined {
  if (path.startsWith("/nightaudit") || path.startsWith("/approvals") ||
      path.startsWith("/housekeeping") ||       path.startsWith("/notifications") ||
      path.startsWith("/wakeup") || path.startsWith("/psb") ||
      path.startsWith("/shifts") || path.startsWith("/group-blocks")) return "ops";
  if (path.startsWith("/members")) return "crm";
  if (path.startsWith("/commission") || path.startsWith("/reconciliation") || path.startsWith("/deposits")) return "fin";
  if (path.startsWith("/alerts")) return "risk";
  if (path.startsWith("/group")) return "group";
  if (path.startsWith("/users") || path.startsWith("/audit")) return "sec";
  if (path.startsWith("/rates") || path.startsWith("/yield")) return "yield";
  if (path.startsWith("/mp-orders") || path.startsWith("/openapi")) return "channel";
  if (path.startsWith("/ai-chat")) return "ai";
  if (path.startsWith("/room-types") || path.startsWith("/rooms-inventory")) return "base";
  if (path.startsWith("/adjustments")) return "fin";
  if (path.startsWith("/price-policy")) return "group";
  if (path.startsWith("/channel-push") || path.startsWith("/channel-center")) return "channel";
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
      <Sider theme="dark" width={208}>
        <div
          style={{
            color: "#fff",
            padding: "18px 16px 16px",
            borderBottom: "1px solid rgba(255,255,255,.08)",
            marginBottom: 4,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
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
              }}
            >
              P
            </div>
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
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          defaultOpenKeys={openKey ? [openKey] : []}
          items={items}
          onClick={({ key }) => {
            if (!GROUP_KEYS.includes(key as string)) navigate(key as string);
          }}
        />
      </Sider>
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
            placeholder="搜索菜单、订单、宾客…"
            prefix={<SearchOutlined style={{ color: "#b8bfc7" }} />}
            style={{ maxWidth: 360, flex: 1, margin: "0 32px", borderRadius: 8 }}
            allowClear
            onPressEnter={(e) => {
              // 占位不实现，留 TODO 注释（M33 视觉升级：搜索框仅作入口占位）
              console.log("TODO: 全局搜索", (e.target as HTMLInputElement).value);
            }}
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
    </Layout>
  );
}
