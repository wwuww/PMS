import { useEffect, useState } from "react";
import {
  Drawer,
  Input,
  List,
  Tag,
  Typography,
  Spin,
  Empty,
} from "antd";
import {
  SearchOutlined,
  UserOutlined,
  CalendarOutlined,
  AppstoreOutlined,
  CreditCardOutlined,
  CrownOutlined,
  TeamOutlined,
  BellOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { globalSearch } from "../api/endpoints";
import type {
  SearchResult,
  SearchResultItem,
  SearchEntityType,
} from "../api/types";
import { useTenant } from "../store/tenant";

const { Text } = Typography;

const TYPE_META: Record<
  SearchEntityType,
  { label: string; icon: React.ReactNode; color: string }
> = {
  guest: { label: "宾客", icon: <UserOutlined />, color: "#1677ff" },
  booking: { label: "订单", icon: <CalendarOutlined />, color: "#fa8c16" },
  room: { label: "房间", icon: <AppstoreOutlined />, color: "#389e0d" },
  bill: { label: "账单", icon: <CreditCardOutlined />, color: "#722ed1" },
  member: { label: "会员", icon: <CrownOutlined />, color: "#eb2f96" },
  group: { label: "团队", icon: <TeamOutlined />, color: "#13c2c2" },
  notification: { label: "通知", icon: <BellOutlined />, color: "#2f54eb" },
};

interface SearchDrawerProps {
  open: boolean;
  onClose: () => void;
  initialQuery?: string;
}

export default function SearchDrawer({
  open,
  onClose,
  initialQuery = "",
}: SearchDrawerProps) {
  const { tenantCode } = useTenant();
  const navigate = useNavigate();
  const [query, setQuery] = useState(initialQuery);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);

  useEffect(() => {
    if (open) {
      setQuery(initialQuery);
      if (initialQuery && initialQuery.trim()) {
        void doSearch(initialQuery);
      } else {
        setResult(null);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialQuery]);

  async function doSearch(q: string) {
    if (!tenantCode || !q.trim()) return;
    setLoading(true);
    try {
      const r = await globalSearch(tenantCode, q.trim());
      setResult(r);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("Search failed", e);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  // 按 type 分组（保持后端 by_type 顺序：guest → booking → room → bill → member → group → notification）
  const grouped = ((result?.items ?? []).reduce(
    (acc, item) => {
      if (!acc[item.type]) acc[item.type] = [];
      acc[item.type].push(item);
      return acc;
    },
    {} as Record<SearchEntityType, SearchResultItem[]>,
  ));

  function handleItemClick(item: SearchResultItem) {
    onClose();
    navigate(item.href);
  }

  return (
    <Drawer
      title={
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索宾客 / 订单 / 房间 / 账单 / 会员 / 团队 / 通知"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={() => doSearch(query)}
          allowClear
          autoFocus
          size="large"
          style={{ borderRadius: 8 }}
        />
      }
      placement="right"
      width={480}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      {loading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin tip="搜索中…" />
        </div>
      ) : !result ? (
        <Empty description="输入关键词开始搜索" style={{ paddingTop: 40 }} />
      ) : result.items.length === 0 ? (
        <Empty
          description={`未找到「${result.query}」相关结果`}
          style={{ paddingTop: 40 }}
        />
      ) : (
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            共 {result.total} 条结果 · 关键词「{result.query}」
          </Text>
          {Object.entries(grouped).map(([type, items]) => {
            const meta = TYPE_META[type as SearchEntityType];
            if (!meta) return null;
            return (
              <div key={type} style={{ marginTop: 16 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    color: meta.color,
                  }}
                >
                  {meta.icon}
                  {meta.label}
                  <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                    {items.length} 条
                  </Text>
                </div>
                <List
                  size="small"
                  dataSource={items}
                  renderItem={(item) => (
                    <List.Item
                      onClick={() => handleItemClick(item)}
                      style={{
                        cursor: "pointer",
                        padding: "8px 12px",
                        borderRadius: 6,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 2,
                          flex: 1,
                          minWidth: 0,
                        }}
                      >
                        <Text strong style={{ fontSize: 13 }}>
                          {item.title}
                        </Text>
                        <Text
                          type="secondary"
                          style={{ fontSize: 12 }}
                          ellipsis
                        >
                          {item.subtitle}
                        </Text>
                      </div>
                      {item.badge && (
                        <Tag
                          color={item.badge_color || "default"}
                          style={{ marginRight: 0 }}
                        >
                          {item.badge}
                        </Tag>
                      )}
                    </List.Item>
                  )}
                />
              </div>
            );
          })}
        </div>
      )}
    </Drawer>
  );
}