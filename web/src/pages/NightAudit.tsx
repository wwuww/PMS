import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ReloadOutlined,
  PlayCircleOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import { listDailyReports, listBusinessDays, runNightAudit } from "../api/endpoints";
import type { DailyReport, BusinessDay } from "../api/types";
import { fmtCents, fmtInt } from "../utils/format";
// M35b：金额单元格组件（正数绿色、负数红色、等宽数字）
// 注意：必须带 .tsx 后缀 —— 无后缀会优先解析到 format.ts（纯字符串工具），取不到组件。
import { CellAmount } from "../utils/format.tsx";

const { Title, Text } = Typography;

const ROOM_STATE_LABEL: Record<string, string> = {
  vacant_clean: "空净",
  vacant_dirty: "空脏",
  occupied: "在住",
  arrival_locked: "锁房",
  maintenance: "维修",
  out_of_service: "停用",
};

function statusTag(s: string) {
  const map: Record<string, { color: string; label: string }> = {
    OPEN: { color: "processing", label: "营业中" },
    CLOSED: { color: "default", label: "已关账" },
    AUDITED: { color: "green", label: "已夜审" },
    SUSPENDED: { color: "red", label: "挂起" },
  };
  const m = map[s] || { color: "default", label: s };
  return <Tag color={m.color}>{m.label}</Tag>;
}

const SUSPEND_CAT: Record<string, { color: string; label: string }> = {
  重复入住脏数据: { color: "orange", label: "重复入住脏数据" },
  房型数据缺失: { color: "red", label: "房型数据缺失" },
  房态流转非法: { color: "purple", label: "房态流转非法" },
  数据完整性冲突: { color: "magenta", label: "数据完整性冲突" },
  数据库连接异常: { color: "volcano", label: "数据库/连接异常" },
  未知异常: { color: "default", label: "未知异常" },
};

interface ParsedSuspend {
  category: string;
  message: string;
}

function parseSuspended(reason?: string | null): ParsedSuspend {
  if (!reason) return { category: "未知异常", message: "夜审异常挂起，请重试" };
  const m = reason.match(/^\[(.+?)\]\s*(.*)$/s);
  if (m) return { category: m[1], message: m[2] || reason };
  return { category: "未知异常", message: reason };
}

interface Snapshot {
  before?: {
    room_state_distribution?: Record<string, number>;
    occupied_rooms?: number;
    unsettled_bills?: { count: number; amount: number };
    anomalies?: { room_no: string; type: string }[];
  };
  after?: {
    room_state_distribution?: Record<string, number>;
    posted_room_charge?: number;
    flipped_rooms?: string[];
  };
  diff?: { occupied_delta?: number };
}

function parseSnapshot(raw?: string): Snapshot | null {
  if (!raw) return null;
  try {
    const obj = JSON.parse(raw);
    return obj && typeof obj === "object" ? (obj as Snapshot) : null;
  } catch {
    return null;
  }
}

function StateDist({ dist }: { dist?: Record<string, number> }) {
  if (!dist) return <Text type="secondary">—</Text>;
  const entries = Object.entries(dist).filter(([, v]) => v > 0);
  if (entries.length === 0) return <Text type="secondary">无</Text>;
  return (
    <Space wrap size={[4, 4]}>
      {entries.map(([k, v]) => (
        <Tag key={k}>{ROOM_STATE_LABEL[k] || k} {v}</Tag>
      ))}
    </Space>
  );
}

function SnapshotDetail({ report }: { report: DailyReport }) {
  const snap = parseSnapshot(report.snapshot);
  if (!snap) {
    return <Empty description="该日报无快照数据（历史数据）" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }
  const before = snap.before || {};
  const after = snap.after || {};
  const diff = snap.diff || {};
  return (
    <div style={{ padding: "4px 0" }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={`夜审前后对比 · 在住变化 ${diff.occupied_delta ?? 0} 间`}
      />
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <Card size="small" title="夜审前（过账/翻房前）" style={{ flex: 1, minWidth: 280 }}>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="房态分布">
              <StateDist dist={before.room_state_distribution} />
            </Descriptions.Item>
            <Descriptions.Item label="在住房数">{before.occupied_rooms ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="未结账单">
              {before.unsettled_bills
                ? `${before.unsettled_bills.count} 笔 / ${fmtCents(before.unsettled_bills.amount)}`
                : "—"}
            </Descriptions.Item>
            <Descriptions.Item label="房态差异">
              {before.anomalies && before.anomalies.length > 0 ? (
                <Space wrap>
                  {before.anomalies.map((a) => (
                    <Tag key={a.room_no} color="orange" icon={<WarningOutlined />}>
                      {a.room_no} 在住无订单
                    </Tag>
                  ))}
                </Space>
              ) : (
                <Text type="secondary">无</Text>
              )}
            </Descriptions.Item>
          </Descriptions>
        </Card>
        <Card size="small" title="夜审后（过账/翻房后）" style={{ flex: 1, minWidth: 280 }}>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="房态分布">
              <StateDist dist={after.room_state_distribution} />
            </Descriptions.Item>
            <Descriptions.Item label="过账房租">
              {after.posted_room_charge != null ? fmtCents(after.posted_room_charge) : "—"}
            </Descriptions.Item>
            <Descriptions.Item label="预离翻房">
              {after.flipped_rooms && after.flipped_rooms.length > 0 ? (
                <Space wrap>
                  {after.flipped_rooms.map((r) => (
                    <Tag key={r} color="blue">{r}</Tag>
                  ))}
                </Space>
              ) : (
                <Text type="secondary">无</Text>
              )}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </div>
    </div>
  );
}

export default function NightAuditPage() {
  const { tenantCode, hotelId } = useTenant();
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [days, setDays] = useState<BusinessDay[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryingAll, setRetryingAll] = useState(false);
  const [asOf, setAsOf] = useState<string>(dayjs().format("YYYY-MM-DD"));

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [r, d] = await Promise.all([
        listDailyReports(tenantCode, hotelId ?? undefined),
        listBusinessDays(tenantCode, hotelId ?? undefined),
      ]);
      setReports(r);
      setDays(d);
    } catch (e: any) {
      message.error(e?.message || "夜审日报加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, hotelId]);

  const handleRun = async () => {
    setRunning(true);
    try {
      const res = await runNightAudit(tenantCode, asOf, "web");
      const skipTip =
        res.skipped > 0
          ? `，跳过 ${res.skipped} 笔（该营业日已夜审）`
          : "";
      message.success(
        `夜审完成：跑批 ${res.ran} 笔，挂起 ${res.suspended} 笔${skipTip}`
      );
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "夜审执行失败");
    } finally {
      setRunning(false);
    }
  };

  const handleRetry = async (businessDate: string) => {
    setRetrying(businessDate);
    try {
      const res = await runNightAudit(tenantCode, businessDate, "web");
      message.success(`营业日 ${businessDate} 重试夜审：成功 ${res.ran} 笔`);
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "重试夜审失败");
    } finally {
      setRetrying(null);
    }
  };

  const handleRetryAll = async () => {
    if (suspended.length === 0) return;
    setRetryingAll(true);
    try {
      // 逐笔对挂账营业日重试（复用 _get_or_open_day 重开 OPEN 重新夜审）
      let total = 0;
      for (const d of suspended) {
        const res = await runNightAudit(tenantCode, d.business_date, "web");
        total += res.ran;
      }
      message.success(`批量重试完成：共处理 ${suspended.length} 笔挂账，成功 ${total} 笔`);
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "批量重试夜审失败");
    } finally {
      setRetryingAll(false);
    }
  };

  const suspended = days.filter((d) => d.status === "SUSPENDED");

  const columns: ColumnsType<DailyReport> = [
    { title: "营业日", dataIndex: "business_date", key: "business_date" },
    { title: "在住房/总数", key: "occ", render: (_, r) => `${r.occupied_rooms}/${r.total_rooms}` },
    {
      title: "出租率",
      dataIndex: "occ_pct",
      key: "occ_pct",
      render: (v: number) => `${v}%`,
    },
    {
      title: "房费收入",
      dataIndex: "room_revenue",
      key: "room_revenue",
      align: "right",
      render: (v: number) => <CellAmount value={v} />,
    },
    {
      title: "其他收入",
      dataIndex: "other_revenue",
      key: "other_revenue",
      align: "right",
      render: (v: number) => <CellAmount value={v} />,
    },
    {
      title: "总收入",
      dataIndex: "total_revenue",
      key: "total_revenue",
      align: "right",
      render: (v: number) => (
        <Text strong>
          <CellAmount value={v} />
        </Text>
      ),
    },
    {
      title: "ADR",
      dataIndex: "adr",
      key: "adr",
      align: "right",
      render: (v: number) => <CellAmount value={v} />,
    },
    {
      title: "抵店/离店",
      key: "flow",
      render: (_, r) => `${fmtInt(r.arrived_rooms)} / ${fmtInt(r.departed_rooms)}`,
    },
  ];

  return (
    <div>
      <Card
        style={{ marginBottom: 16 }}
        styles={{ body: { display: "flex", alignItems: "center", justifyContent: "space-between" } }}
      >
        <Title level={4} style={{ margin: 0 }}>
          夜审日报
        </Title>
        <Space>
          <DatePicker value={dayjs(asOf)} onChange={(d) => d && setAsOf(d.format("YYYY-MM-DD"))} />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={running}
            onClick={handleRun}
          >
            运行夜审
          </Button>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
        </Space>
      </Card>

      {suspended.length > 0 && (
        <Card
          title={
            <span>
              <WarningOutlined style={{ color: "#faad14", marginRight: 8 }} />
              挂账 / 异常营业日（{suspended.length}）
            </span>
          }
          extra={
            <Button
              size="small"
              danger
              type="primary"
              loading={retryingAll}
              onClick={handleRetryAll}
            >
              重试全部挂账
            </Button>
          }
          style={{ marginBottom: 16 }}
          styles={{ header: { color: "#d46b08" } }}
        >
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            {suspended.map((d) => {
              const ps = parseSuspended(d.suspended_reason);
              const cat = SUSPEND_CAT[ps.category] || SUSPEND_CAT["未知异常"];
              return (
                <Alert
                  key={d.id}
                  type="error"
                  showIcon
                  message={
                    <Space wrap>
                      <Text strong>{d.business_date}</Text>
                      {statusTag(d.status)}
                      <Tag color={cat.color}>{cat.label}</Tag>
                      <Button
                        size="small"
                        type="primary"
                        loading={retrying === d.business_date}
                        onClick={() => handleRetry(d.business_date)}
                      >
                        重试夜审
                      </Button>
                    </Space>
                  }
                  description={ps.message}
                />
              );
            })}
          </Space>
        </Card>
      )}

      <Card title="营业日状态" style={{ marginBottom: 16 }}>
        {days.length === 0 ? (
          <Empty description="暂无营业日" />
        ) : (
          <Space wrap>
            {days.map((d) => (
              <Tag key={d.id} color={d.status === "AUDITED" ? "green" : "blue"}>
                {d.business_date} {statusTag(d.status).props.children}
              </Tag>
            ))}
          </Space>
        )}
      </Card>

      <Card title="每日营业报表" loading={loading}>
        {reports.length === 0 ? (
          <Empty description="暂无日报，点击「运行夜审」生成" />
        ) : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={reports}
            pagination={{ pageSize: 12 }}
            expandable={{
              expandedRowRender: (record) => <SnapshotDetail report={record} />,
            }}
          />
        )}
      </Card>
    </div>
  );
}
