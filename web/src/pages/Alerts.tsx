import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined, EyeOutlined, CheckOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useTenant } from "../store/tenant";
import { listAlerts, acknowledgeAlert, resolveAlert } from "../api/endpoints";
import type { AlertNotification } from "../api/types";

const { Title, Text } = Typography;

function severityTag(s: string) {
  const m: Record<string, { color: string; label: string }> = {
    low: { color: "default", label: "低" },
    medium: { color: "gold", label: "中" },
    high: { color: "red", label: "高" },
  };
  const x = m[s] || { color: "default", label: s };
  return <Tag color={x.color}>{x.label}</Tag>;
}

function statusTag(s: string) {
  const m: Record<string, { color: string; label: string }> = {
    OPEN: { color: "red", label: "待处理" },
    ACKNOWLEDGED: { color: "gold", label: "已确认" },
    RESOLVED: { color: "green", label: "已解决" },
  };
  const x = m[s] || { color: "default", label: s };
  return <Tag color={x.color}>{x.label}</Tag>;
}

export default function AlertsPage() {
  const { tenantCode } = useTenant();
  const [list, setList] = useState<AlertNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>("ALL");

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      setList(await listAlerts(tenantCode, filter === "ALL" ? undefined : filter));
    } catch (e: any) {
      message.error(e?.message || "预警加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, filter]);

  const act = async (id: string, kind: "ack" | "resolve") => {
    try {
      if (kind === "ack") await acknowledgeAlert(tenantCode, id);
      else await resolveAlert(tenantCode, id);
      message.success(kind === "ack" ? "已确认" : "已解决");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    }
  };

  const columns: ColumnsType<AlertNotification> = [
    { title: "ID", dataIndex: "id", key: "id", width: 70 },
    {
      title: "级别",
      dataIndex: "severity",
      key: "severity",
      render: (s: string) => severityTag(s),
    },
    { title: "类型", dataIndex: "alert_type", key: "alert_type" },
    { title: "标题", dataIndex: "title", key: "title" },
    {
      title: "说明",
      dataIndex: "description",
      key: "description",
      render: (v: string) => <Text style={{ fontSize: 13 }}>{v}</Text>,
    },
    {
      title: "建议处理",
      dataIndex: "suggested_action",
      key: "suggested_action",
      render: (v: string | null) => v || "—",
    },
    { title: "状态", dataIndex: "status", key: "status", render: (s: string) => statusTag(s) },
    {
      title: "操作",
      key: "action",
      render: (_, r) => (
        <Space>
          {r.status === "OPEN" && (
            <Button type="link" icon={<EyeOutlined />} onClick={() => act(r.id, "ack")}>
              确认
            </Button>
          )}
          {r.status !== "RESOLVED" && (
            <Button type="link" icon={<CheckOutlined />} style={{ color: "#52c41a" }} onClick={() => act(r.id, "resolve")}>
              解决
            </Button>
          )}
        </Space>
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
          AI 预警中心
        </Title>
        <Space>
          <Tag color="blue">M12 自动对账预警</Tag>
          <Select
            value={filter}
            style={{ width: 140 }}
            onChange={setFilter}
            options={[
              { value: "ALL", label: "全部" },
              { value: "OPEN", label: "待处理" },
              { value: "ACKNOWLEDGED", label: "已确认" },
              { value: "RESOLVED", label: "已解决" },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
        </Space>
      </Card>

      <Card>
        <Table rowKey="id" loading={loading} columns={columns} dataSource={list} pagination={{ pageSize: 10 }} />
      </Card>
    </div>
  );
}
