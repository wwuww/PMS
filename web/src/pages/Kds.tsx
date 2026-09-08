import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Empty,
  Row,
  Segmented,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined, CheckCircleOutlined, InboxOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import { listKitchenTickets, markItemReady, markItemServed } from "../api/endpoints";
import type { KitchenTicket } from "../api/types";

const { Title, Text } = Typography;

const KDS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "待做", color: "red" },
  ready: { label: "已出餐", color: "gold" },
  served: { label: "已上菜", color: "green" },
};

function kdsTag(s: string) {
  const m = KDS_LABELS[s] ?? { label: s, color: "default" };
  return <Tag color={m.color}>{m.label}</Tag>;
}

/** 出单位置：桌台优先，否则房号，再否则散客。 */
function ticketSeat(t: KitchenTicket): string {
  if (t.table_no) return `桌 ${t.table_no}`;
  if (t.room_no) return `房 ${t.room_no}`;
  return "散客";
}

export default function Kds() {
  const { tenantCode, hotelId } = useTenant();
  const [tickets, setTickets] = useState<KitchenTicket[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>("active");

  const load = useCallback(async () => {
    if (!tenantCode || !hotelId) return;
    setLoading(true);
    try {
      const states = filter === "served" ? "served" : filter === "all" ? undefined : "pending,ready";
      setTickets(await listKitchenTickets(tenantCode, hotelId, states));
    } catch {
      message.error("厨房出单加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId, filter]);

  useEffect(() => {
    load();
    // 每 15s 轮询，保持出单屏实时
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  // 按出单位置（桌/房/散客 + 单号）分组
  const groups = useMemo(() => {
    const map = new Map<string, { key: string; seat: string; guest?: string; items: KitchenTicket[] }>();
    for (const t of tickets) {
      const key = `${ticketSeat(t)} #${t.order_id}`;
      if (!map.has(key)) {
        map.set(key, { key, seat: ticketSeat(t), guest: t.guest_name ?? undefined, items: [] });
      }
      map.get(key)!.items.push(t);
    }
    return Array.from(map.values());
  }, [tickets]);

  const handleReady = async (t: KitchenTicket) => {
    try {
      await markItemReady(tenantCode, t.order_id, t.item_id);
      message.success(`已出餐：${t.name}`);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    }
  };

  const handleServed = async (t: KitchenTicket) => {
    try {
      await markItemServed(tenantCode, t.order_id, t.item_id);
      message.success(`已上菜：${t.name}`);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    }
  };

  return (
    <div>
      <Card
        style={{ marginBottom: 16 }}
        styles={{ body: { display: "flex", alignItems: "center", justifyContent: "space-between" } }}
      >
        <Title level={4} style={{ margin: 0 }}>
          厨房出单屏（KDS）
        </Title>
        <Space>
          <Segmented
            value={filter}
            onChange={(v) => setFilter(v as string)}
            options={[
              { label: "待出餐", value: "active" },
              { label: "已上菜", value: "served" },
              { label: "全部", value: "all" },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
        </Space>
      </Card>

      {groups.length === 0 ? (
        <Card>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无出单任务" />
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
          {groups.map((g) => (
            <Col xs={24} sm={12} lg={8} key={g.key}>
              <Card
                size="small"
                title={
                  <Space>
                    <InboxOutlined />
                    <Text strong>{g.seat}</Text>
                    {g.guest && <Tag>{g.guest}</Tag>}
                  </Space>
                }
              >
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  {g.items.map((t) => (
                    <Card key={t.item_id} size="small" styles={{ body: { padding: 10 } }}>
                      <Row align="middle" justify="space-between">
                        <Space wrap>
                          <Text strong>{t.name}</Text>
                          <Tag>×{t.qty}</Tag>
                          {t.category && <Tag color="cyan">{t.category}</Tag>}
                          {kdsTag(t.kds_status)}
                        </Space>
                        <Space>
                          {t.kds_status === "pending" && (
                            <Button size="small" type="primary" onClick={() => handleReady(t)}>
                              出餐
                            </Button>
                          )}
                          {t.kds_status === "ready" && (
                            <Button
                              size="small"
                              type="primary"
                              icon={<CheckCircleOutlined />}
                              onClick={() => handleServed(t)}
                            >
                              上菜
                            </Button>
                          )}
                          {t.kds_status === "served" && (
                            <Button size="small" disabled>
                              已上菜
                            </Button>
                          )}
                        </Space>
                      </Row>
                    </Card>
                  ))}
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}
