import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  Card,
  Col,
  Row,
  Table,
  Tag,
  Empty,
  App,
  Button,
  Modal,
  DatePicker,
  Typography,
  Descriptions,
} from "antd";
import {
  AreaChartOutlined,
  TeamOutlined,
  LoginOutlined,
  LogoutOutlined,
  CheckCircleOutlined,
  CalendarOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { managerDashboard, runNightAudit, nightAuditBoard } from "../api/endpoints";
import type { Dashboard, Booking, NightAuditBoard } from "../api/types";
import { useTenant } from "../store/tenant";
import { fmtCents } from "../utils/format";
import "./Dashboard.css";

/**
 * 数据卡（M33 升级版）
 * - 顶部 3px 渐变色条（驱动色 = --stat-accent）
 * - 28px 灰底图标 + accent 描边色
 * - 数字 30px tabular-nums + 悬停浮起
 */
export function StatCard({
  label,
  value,
  suffix,
  sub,
  accent,
  icon,
}: {
  label: string;
  value: ReactNode;
  suffix?: string;
  sub?: string;
  accent: string;
  icon?: ReactNode;
}) {
  return (
    <div
      className="stat-card"
      style={{ "--stat-accent": accent } as CSSProperties}
    >
      <span className="stat-card-bar" />
      <div className="stat-card-top">
        <span className="stat-card-icon">{icon}</span>
        <span className="stat-card-label">{label}</span>
      </div>
      <div className="stat-card-value">
        {value}
        {suffix && <span className="stat-card-suffix">{suffix}</span>}
      </div>
      {sub && <div className="stat-card-sub">{sub}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const { tenantCode, hotelId } = useTenant();
  const { message } = App.useApp();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [auditDate, setAuditDate] = useState<dayjs.Dayjs>(dayjs());
  const [auditing, setAuditing] = useState(false);
  const [auditResult, setAuditResult] = useState<{
    ran: number;
    suspended: number;
    errors: unknown[];
  } | null>(null);
  const [board, setBoard] = useState<NightAuditBoard | null>(null);
  const [boardLoading, setBoardLoading] = useState(false);

  const load = () => {
    if (!hotelId) return;
    setLoading(true);
    managerDashboard(tenantCode, hotelId)
      .then(setData)
      .catch((e: Error) => message.error(e.message))
      .finally(() => setLoading(false));
  };

  const loadBoard = () => {
    if (!tenantCode) return;
    setBoardLoading(true);
    nightAuditBoard(tenantCode)
      .then(setBoard)
      .catch((e: Error) => message.error(e.message))
      .finally(() => setBoardLoading(false));
  };

  useEffect(() => {
    load();
    loadBoard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, hotelId]);

  async function runAudit() {
    setAuditing(true);
    try {
      const res = await runNightAudit(
        tenantCode,
        auditDate.format("YYYY-MM-DD"),
        "web"
      );
      setAuditResult(res);
      message.success(`夜审完成：跑批 ${res.ran} 家，挂起 ${res.suspended} 家`);
      setAuditOpen(false);
      load(); // 刷新看板（含最新日报）
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setAuditing(false);
    }
  }

  if (!hotelId) return <Empty description="该租户下暂未创建门店" />;
  if (!data) return <Card loading={loading} />;

  const bookingCols = [
    { title: "房号", dataIndex: "room_no", key: "room_no" },
    { title: "客人", dataIndex: "guest_name", key: "guest_name", render: (v: string) => v || "—" },
    { title: "状态", dataIndex: "status", key: "status", render: (v: string) => <Tag>{v || "—"}</Tag> },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: 20,
        }}
      >
        <div>
          <Typography.Title level={4} style={{ margin: 0, marginBottom: 4 }}>
            经营概览
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            实时数据 · 营业日报视图
          </Typography.Text>
        </div>
        <Button type="primary" onClick={() => setAuditOpen(true)}>
          运行夜审
        </Button>
      </div>

      {/* 数据卡 6 列网格（M33：自建 StatCard + 渐变色条） */}
      <div
        className="dashboard-stat-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(6, 1fr)",
          gap: 14,
          marginBottom: 16,
        }}
      >
        <StatCard
          label="出租率"
          value={data.occupancy_pct}
          suffix="%"
          accent="#1677ff"
          icon={<AreaChartOutlined />}
        />
        <StatCard
          label="在住房间"
          value={data.in_house}
          sub={`总房数 ${data.rooms.total}`}
          accent="#13c2c2"
          icon={<TeamOutlined />}
        />
        <StatCard
          label="今日预抵"
          value={data.arrivals.length}
          accent="#fa8c16"
          icon={<LoginOutlined />}
        />
        <StatCard
          label="今日预离"
          value={data.departures.length}
          accent="#2f54eb"
          icon={<LogoutOutlined />}
        />
        <StatCard
          label="空净可售"
          value={data.rooms.by_state.vacant_clean ?? "-"}
          accent="#389e0d"
          icon={<CheckCircleOutlined />}
        />
        <StatCard
          label="营业日期"
          value={data.business_date}
          accent="#722ed1"
          icon={<CalendarOutlined />}
        />
      </div>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="预抵（Arrivals）" loading={loading}>
            {data.arrivals.length ? (
              <Table
                className="dashboard-table"
                rowKey="id"
                size="small"
                pagination={false}
                scroll={{ x: 600 }}
                columns={bookingCols}
                dataSource={data.arrivals as Booking[]}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无预抵" />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="预离（Departures）" loading={loading}>
            {data.departures.length ? (
              <Table
                className="dashboard-table"
                rowKey="id"
                size="small"
                pagination={false}
                scroll={{ x: 600 }}
                columns={bookingCols}
                dataSource={data.departures as Booking[]}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无预离" />
            )}
          </Card>
        </Col>
      </Row>

      {board && board.hotel_count >= 1 && (
        <Card
          title="集团夜审监控（各店）"
          style={{ marginTop: 16 }}
          loading={boardLoading}
          extra={
            board.total_suspended > 0 ? (
              <Tag color="red">⚠ {board.total_suspended} 家存在挂账</Tag>
            ) : (
              <Tag color="green">全部门店正常</Tag>
            )
          }
        >
          <Table
            className="dashboard-table"
            rowKey="hotel_id"
            size="small"
            pagination={false}
            scroll={{ x: 720 }}
            dataSource={board.hotels}
            onRow={(record) => ({
              style: record.suspended_count > 0 ? { background: "#fff1f0" } : undefined,
            })}
            columns={[
              { title: "门店", dataIndex: "name", key: "name" },
              {
                title: "最新营业日",
                dataIndex: "latest_business_date",
                key: "latest_business_date",
                render: (v: string | null) => v || "—",
              },
              {
                title: "营业日状态",
                dataIndex: "latest_status",
                key: "latest_status",
                render: (v: string | null) => {
                  if (!v) return <Tag>无</Tag>;
                  const m: Record<string, { color: string; label: string }> = {
                    OPEN: { color: "processing", label: "营业中" },
                    CLOSED: { color: "default", label: "已关账" },
                    AUDITED: { color: "green", label: "已夜审" },
                    SUSPENDED: { color: "red", label: "挂起" },
                  };
                  const s = m[v] || { color: "default", label: v };
                  return <Tag color={s.color}>{s.label}</Tag>;
                },
              },
              {
                title: "挂账数",
                dataIndex: "suspended_count",
                key: "suspended_count",
                render: (v: number) =>
                  v > 0 ? <Tag color="red">{v}</Tag> : <span>{v}</span>,
              },
              {
                title: "出租率",
                key: "occ_pct",
                render: (_: unknown, r: NightAuditBoard["hotels"][number]) =>
                  r.latest_report?.occ_pct != null ? `${r.latest_report.occ_pct}%` : "—",
              },
              {
                title: "房费收入",
                key: "room_revenue",
                align: "right",
                render: (_: unknown, r: NightAuditBoard["hotels"][number]) =>
                  r.latest_report ? fmtCents(r.latest_report.room_revenue) : "—",
              },
              {
                title: "总营收",
                key: "total_revenue",
                align: "right",
                render: (_: unknown, r: NightAuditBoard["hotels"][number]) =>
                  r.latest_report ? fmtCents(r.latest_report.total_revenue) : "—",
              },
            ]}
          />
        </Card>
      )}

      <Modal
        title="运行夜审"
        open={auditOpen}
        onOk={runAudit}
        confirmLoading={auditing}
        onCancel={() => setAuditOpen(false)}
        okText="开始跑批"
        cancelText="取消"
      >
        <p>对当前租户下全部门店批量跑批夜审，生成营业日日报（单店异常挂起不阻断整批）。</p>
        <DatePicker
          style={{ width: "100%" }}
          value={auditDate}
          onChange={(d) => d && setAuditDate(d)}
        />
        {auditResult && (
          <Descriptions column={1} style={{ marginTop: 12 }} size="small" bordered>
            <Descriptions.Item label="跑批成功">
              {auditResult.ran} 家
            </Descriptions.Item>
            <Descriptions.Item label="异常挂起">
              {auditResult.suspended} 家
            </Descriptions.Item>
            <Descriptions.Item label="错误">
              {auditResult.errors.length} 条
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
}