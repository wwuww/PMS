import { useEffect, useState } from "react";
import {
  Card,
  Col,
  Row,
  Statistic,
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
import GlassStatCard from "../components/GlassStatCard";
import dayjs from "dayjs";
import { managerDashboard, runNightAudit, nightAuditBoard } from "../api/endpoints";
import type { Dashboard, Booking, NightAuditBoard } from "../api/types";
import { useTenant } from "../store/tenant";
import { fmtCents } from "../utils/format";

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
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          经营概览
        </Typography.Title>
        <Button onClick={() => setAuditOpen(true)}>运行夜审</Button>
      </div>

      {/* 玻璃拟态指标带 */}
      <div
        className="glass-band"
        style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12, marginBottom: 16 }}
      >
        <GlassStatCard label="出租率" value={data.occupancy_pct} suffix="%" accent="#1677ff" />
        <GlassStatCard label="在住房间" value={data.in_house} sub={`总房数 ${data.rooms.total}`} accent="#13c2c2" />
        <GlassStatCard label="今日预抵" value={data.arrivals.length} accent="#fa8c16" />
        <GlassStatCard label="今日预离" value={data.departures.length} accent="#2f54eb" />
        <GlassStatCard label="空净可售" value={data.rooms.by_state.vacant_clean ?? "-"} accent="#389e0d" />
        <GlassStatCard label="营业日期" value={data.business_date} accent="#722ed1" />
      </div>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="预抵（Arrivals）" loading={loading}>
            {data.arrivals.length ? (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
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
                rowKey="id"
                size="small"
                pagination={false}
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
            rowKey="hotel_id"
            size="small"
            pagination={false}
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
