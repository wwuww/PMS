import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Input,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import { listAuditLogs } from "../api/endpoints";
import type { AuditLog } from "../api/types";

const RESULT_COLOR: Record<string, string> = {
  success: "green",
  fail: "red",
  error: "red",
};

export default function Audit() {
  const { tenantCode } = useTenant();
  const [rows, setRows] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [actorFilter, setActorFilter] = useState<string>("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listAuditLogs(tenantCode));
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filtered = actorFilter
    ? rows.filter((r) => r.actor.includes(actorFilter))
    : rows;

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="审计日志（M8）"
        extra={
          <Space>
            <Input.Search
              placeholder="按操作人筛选"
              allowClear
              style={{ width: 200 }}
              onSearch={setActorFilter}
              onChange={(e) => !e.target.value && setActorFilter("")}
            />
            <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
              刷新
            </Button>
          </Space>
        }
      >
        <Table<AuditLog>
          rowKey="id"
          dataSource={filtered}
          loading={loading}
          pagination={{ pageSize: 12 }}
          size="small"
          scroll={{ x: 900 }}
          columns={[
            { title: "时间", dataIndex: "created_at", width: 180, render: (v) => v || "—" },
            { title: "操作人", dataIndex: "actor", width: 120 },
            { title: "动作", dataIndex: "action", width: 150, render: (v) => <Tag>{v}</Tag> },
            {
              title: "资源",
              key: "res",
              width: 160,
              render: (_, r) => `${r.resource_type}:${r.resource_id ?? "-"}`,
            },
            {
              title: "结果",
              dataIndex: "result",
              width: 90,
              render: (s: string) => <Tag color={RESULT_COLOR[s] ?? "default"}>{s}</Tag>,
            },
            { title: "门店", dataIndex: "hotel_id", width: 80, render: (v) => v ?? "—" },
            { title: "IP", dataIndex: "ip", width: 130, render: (v) => v || "—" },
            {
              title: "明细",
              dataIndex: "detail",
              render: (d: Record<string, unknown>) => (
                <span style={{ color: "#666" }}>
                  {d ? JSON.stringify(d) : "—"}
                </span>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
