import { useEffect, useState } from "react";
import {
  Card,
  Descriptions,
  Empty,
  Select,
  Spin,
  Statistic,
  Table,
  Tabs,
  Typography,
  App,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useTenant } from "../store/tenant";
import {
  analyticsDashboard,
  analyticsRanking,
  analyticsChannelRevenue,
  analyticsRoomTypeRevenue,
  analyticsPaymentSummary,
  analyticsOversellWarnings,
  analyticsForecast,
  analyticsCustomReport,
} from "../api/endpoints";
import type {
  AnalyticsDashboard,
  AnalyticsRanking,
  AnalyticsChannel,
  AnalyticsRoomType,
  AnalyticsPayment,
  DailyPoint,
  OversellWarnings,
  OccupancyForecast,
  CustomReport,
} from "../api/types";
import { fmtCents, fmtBps, fmtInt } from "../utils/format";

const { Text } = Typography;

export default function AnalyticsPage() {
  const { tenantCode, hotelId } = useTenant();
  const { message } = App.useApp();
  const [tab, setTab] = useState("single");
  const [dash, setDash] = useState<AnalyticsDashboard | null>(null);
  const [ranking, setRanking] = useState<AnalyticsRanking | null>(null);
  const [channel, setChannel] = useState<AnalyticsChannel | null>(null);
  const [roomType, setRoomType] = useState<AnalyticsRoomType | null>(null);
  const [payment, setPayment] = useState<AnalyticsPayment | null>(null);
  const [oversell, setOversell] = useState<OversellWarnings | null>(null);
  const [forecast, setForecast] = useState<OccupancyForecast | null>(null);
  const [custom, setCustom] = useState<CustomReport | null>(null);
  const [customGroupBy, setCustomGroupBy] = useState<"room_type" | "channel" | "day">("day");
  const [loading, setLoading] = useState(false);

  const load = (key: string) => {
    if (!tenantCode || (!hotelId && key !== "ranking")) return;
    setLoading(true);
    const done = () => setLoading(false);
    if (key === "single") {
      analyticsDashboard(tenantCode, hotelId!)
        .then(setDash)
        .catch((e: Error) => message.error(e.message))
        .finally(done);
    } else if (key === "ranking") {
      analyticsRanking(tenantCode)
        .then(setRanking)
        .catch((e: Error) => message.error(e.message))
        .finally(done);
    } else if (key === "channel") {
      analyticsChannelRevenue(tenantCode, hotelId!)
        .then(setChannel)
        .catch((e: Error) => message.error(e.message))
        .finally(done);
    } else if (key === "roomtype") {
      analyticsRoomTypeRevenue(tenantCode, hotelId!)
        .then(setRoomType)
        .catch((e: Error) => message.error(e.message))
        .finally(done);
    } else if (key === "payment") {
      analyticsPaymentSummary(tenantCode, hotelId!)
        .then(setPayment)
        .catch((e: Error) => message.error(e.message))
        .finally(done);
    } else if (key === "oversell") {
      const today = new Date();
      const in30 = new Date(today.getTime() + 30 * 86400000);
      const fmt = (d: Date) => d.toISOString().slice(0, 10);
      analyticsOversellWarnings(tenantCode, hotelId!, fmt(today), fmt(in30))
        .then(setOversell)
        .catch((e: Error) => message.error(e.message))
        .finally(done);
    } else if (key === "forecast") {
      analyticsForecast(tenantCode, hotelId!, 14)
        .then(setForecast)
        .catch((e: Error) => message.error(e.message))
        .finally(done);
    } else if (key === "custom") {
      analyticsCustomReport(tenantCode, hotelId!, customGroupBy)
        .then(setCustom)
        .catch((e: Error) => message.error(e.message))
        .finally(done);
    }
  };

  useEffect(() => {
    load(tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, hotelId, tab]);

  if (!hotelId) return <Empty description="该租户下暂未创建门店" />;

  const renderKpi = (d: AnalyticsDashboard) => (
    <>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
        <Card style={{ flex: 1, minWidth: 160 }}>
          <Statistic title="总收入" value={d.total_revenue_cents / 100} precision={2} prefix="¥" />
        </Card>
        <Card style={{ flex: 1, minWidth: 160 }}>
          <Statistic title="房费收入" value={d.room_revenue_cents / 100} precision={2} prefix="¥" />
        </Card>
        <Card style={{ flex: 1, minWidth: 160 }}>
          <Statistic title="RevPAR" value={d.revpar_cents / 100} precision={2} prefix="¥" />
        </Card>
        <Card style={{ flex: 1, minWidth: 160 }}>
          <Statistic title="ADR" value={d.adr_cents / 100} precision={2} prefix="¥" />
        </Card>
        <Card style={{ flex: 1, minWidth: 160 }}>
          <Statistic title="出租率" value={fmtBps(d.occ_pct_bps)} />
        </Card>
      </div>
      <Descriptions bordered column={3} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="门店">{d.hotel_name}</Descriptions.Item>
        <Descriptions.Item label="统计区间">
          {d.start_date || "?"} ~ {d.end_date || "?"}
        </Descriptions.Item>
        <Descriptions.Item label="天数">{d.days}</Descriptions.Item>
        <Descriptions.Item label="总房数">{fmtInt(d.total_rooms)}</Descriptions.Item>
        <Descriptions.Item label="已售房晚">{fmtInt(d.occupied_room_nights)}</Descriptions.Item>
        <Descriptions.Item label="其他收入">{fmtCents(d.other_revenue_cents)}</Descriptions.Item>
      </Descriptions>
      <Card title="日序列（收入 / 出租率）" size="small">
        <DailyTrend series={d.daily_series} />
      </Card>
    </>
  );

  const items = [
    {
      key: "single",
      label: "单店看板",
      children: (
        <Spin spinning={loading}>
          {dash ? renderKpi(dash) : <Empty description="暂无数据" />}
        </Spin>
      ),
    },
    {
      key: "ranking",
      label: "门店排名",
      children: (
        <Spin spinning={loading}>
          {ranking ? (
            <Table
              rowKey="hotel_id"
              pagination={false}
              columns={[
                { title: "门店", dataIndex: "name" },
                { title: "房费收入", dataIndex: "room_revenue_cents", align: "right", render: (v: number) => fmtCents(v) },
                { title: "总营收", dataIndex: "total_revenue_cents", align: "right", render: (v: number) => fmtCents(v) },
                { title: "RevPAR", dataIndex: "revpar_cents", align: "right", render: (v: number) => fmtCents(v) },
                { title: "ADR", dataIndex: "adr_cents", align: "right", render: (v: number) => fmtCents(v) },
                { title: "出租率", dataIndex: "occ_pct_bps", align: "right", render: (v: number) => fmtBps(v) },
              ]}
              dataSource={ranking.hotels}
            />
          ) : (
            <Empty description="暂无数据" />
          )}
        </Spin>
      ),
    },
    {
      key: "channel",
      label: "渠道收入",
      children: (
        <Spin spinning={loading}>
          {channel ? (
            <Table
              rowKey="channel"
              pagination={false}
              columns={[
                { title: "渠道", dataIndex: "channel" },
                { title: "预订数", dataIndex: "booking_count", align: "right" },
                { title: "房费收入", dataIndex: "room_revenue_cents", align: "right", render: (v: number) => fmtCents(v) },
              ]}
              dataSource={channel.channels}
              footer={() => `合计：预订 ${channel.total_bookings} 笔 / 房费 ${fmtCents(channel.total_room_revenue_cents)}`}
            />
          ) : (
            <Empty description="暂无数据" />
          )}
        </Spin>
      ),
    },
    {
      key: "roomtype",
      label: "房型收入",
      children: (
        <Spin spinning={loading}>
          {roomType ? (
            <Table
              rowKey="room_type_id"
              pagination={false}
              columns={[
                { title: "房型", dataIndex: "room_type_name" },
                { title: "预订数", dataIndex: "booking_count", align: "right" },
                { title: "房费收入", dataIndex: "room_revenue_cents", align: "right", render: (v: number) => fmtCents(v) },
              ]}
              dataSource={roomType.room_types}
              footer={() => `合计：预订 ${roomType.total_bookings} 笔 / 房费 ${fmtCents(roomType.total_room_revenue_cents)}`}
            />
          ) : (
            <Empty description="暂无数据" />
          )}
        </Spin>
      ),
    },
    {
      key: "payment",
      label: "支付方式",
      children: (
        <Spin spinning={loading}>
          {payment ? (
            <Table
              rowKey="method"
              pagination={false}
              columns={[
                { title: "支付方式", dataIndex: "method" },
                { title: "金额", dataIndex: "amount_cents", align: "right", render: (v: number) => fmtCents(v) },
              ]}
              dataSource={payment.methods}
              footer={() => `合计：${fmtCents(payment.total_cents)}`}
            />
          ) : (
            <Empty description="暂无数据" />
          )}
        </Spin>
      ),
    },
    {
      key: "oversell",
      label: "超卖预警",
      children: (
        <Spin spinning={loading}>
          {oversell ? (
            oversell.warnings.length === 0 ? (
              <Empty description="未来 30 天无超卖 / 临界风险" />
            ) : (
              <Table
                rowKey="date"
                pagination={false}
                columns={[
                  { title: "日期", dataIndex: "date" },
                  { title: "在手预订", dataIndex: "on_hand_bookings", align: "right" },
                  { title: "可售房", dataIndex: "sellable_rooms", align: "right" },
                  {
                    title: "缺口",
                    dataIndex: "gap",
                    align: "right",
                    render: (v: number) => <Text type="danger">{v}</Text>,
                  },
                  {
                    title: "级别",
                    dataIndex: "level",
                    render: (v: string) =>
                      v === "OVERSELL" ? (
                        <Text type="danger">超卖</Text>
                      ) : (
                        <Text type="warning">临界</Text>
                      ),
                  },
                ]}
                dataSource={oversell.warnings}
                footer={() => `可售房量 ${oversell.sellable_rooms} ｜ 预警 ${oversell.warning_count} 天`}
              />
            )
          ) : (
            <Empty description="暂无数据" />
          )}
        </Spin>
      ),
    },
    {
      key: "forecast",
      label: "远期预测",
      children: (
        <Spin spinning={loading}>
          {forecast ? (
            <>
              <Table
                rowKey="date"
                pagination={false}
                size="small"
                columns={[
                  { title: "日期", dataIndex: "date" },
                  { title: "在手预订", dataIndex: "on_hand_bookings", align: "right" },
                  { title: "可售房", dataIndex: "sellable_rooms", align: "right" },
                  {
                    title: "在手入住率",
                    dataIndex: "occupancy_rate",
                    align: "right",
                    render: (v: number) => `${(v * 100).toFixed(1)}%`,
                  },
                ]}
                dataSource={forecast.forecast}
                footer={() =>
                  `口径：在手（on-the-books）确定性入住率，非统计预测 ｜ 可售房 ${forecast.sellable_rooms}`
                }
              />
              <Card title="近 14 天预订增速（Booking Pace）" size="small" style={{ marginTop: 16 }}>
                {forecast.booking_pace.length === 0 ? (
                  <Empty description="暂无新建预订记录" />
                ) : (
                  <PaceTrend series={forecast.booking_pace} />
                )}
              </Card>
            </>
          ) : (
            <Empty description="暂无数据" />
          )}
        </Spin>
      ),
    },
    {
      key: "custom",
      label: "自定义报表",
      children: (
        <Spin spinning={loading}>
          <div style={{ marginBottom: 12 }}>
            <Select
              value={customGroupBy}
              style={{ width: 160 }}
              onChange={(v: "room_type" | "channel" | "day") => {
                setCustomGroupBy(v);
                load("custom");
              }}
              options={[
                { value: "day", label: "按入住日期" },
                { value: "channel", label: "按渠道" },
                { value: "room_type", label: "按房型" },
              ]}
            />
          </div>
          {custom ? (
            <Table
              rowKey="group"
              pagination={false}
              columns={[
                {
                  title: custom.group_by === "day" ? "入住日期" : custom.group_by === "channel" ? "渠道" : "房型",
                  dataIndex: "group",
                  render: (v: string, r: { label?: string }) => r.label || v,
                },
                { title: "预订数", dataIndex: "booking_count", align: "right" },
                { title: "房费收入", dataIndex: "room_revenue_cents", align: "right", render: (v: number) => fmtCents(v) },
              ]}
              dataSource={custom.rows}
              footer={() => `合计：预订 ${custom.total_bookings} 笔 / 房费 ${fmtCents(custom.total_room_revenue_cents)}`}
            />
          ) : (
            <Empty description="暂无数据" />
          )}
        </Spin>
      ),
    },
  ];

  return (
    <Card>
      <Tabs activeKey={tab} onChange={setTab} items={items} />
    </Card>
  );
}

function DailyTrend({ series }: { series: DailyPoint[] }) {
  const W = 720;
  const H = 160;
  if (!series.length) return <Empty description="暂无日序列" />;
  const maxRev = Math.max(...series.map((p) => Number(p.room_revenue_cents || 0)), 1);
  const maxOcc = 10000;
  const n = series.length;
  const xStep = n > 1 ? W / (n - 1) : 0;
  const revPts = series
    .map((p, i) => `${(i * xStep).toFixed(1)},${(H - (Number(p.room_revenue_cents || 0) / maxRev) * H).toFixed(1)}`)
    .join(" ");
  const occPts = series
    .map((p, i) => `${(i * xStep).toFixed(1)},${(H - (Number(p.occ_pct_bps || 0) / maxOcc) * H).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ background: "#fafafa" }}>
      <polyline points={revPts} fill="none" stroke="#1677ff" strokeWidth={2} />
      <polyline points={occPts} fill="none" stroke="#52c41a" strokeWidth={2} strokeDasharray="4 3" />
      {series.map((p, i) => (
        <text key={i} x={(i * xStep).toFixed(1)} y={H - 4} fontSize={9} fill="#999" textAnchor="middle">
          {(p.business_date || "").slice(5)}
        </text>
      ))}
    </svg>
  );
}


function PaceTrend({ series }: { series: { date: string; bookings: number }[] }) {
  const W = 720;
  const H = 120;
  const max = Math.max(...series.map((p) => p.bookings), 1);
  const n = series.length;
  if (!n) return <Empty description="暂无数据" />;
  const xStep = n > 1 ? W / (n - 1) : 0;
  const pts = series
    .map((p, i) => `${(i * xStep).toFixed(1)},${(H - (p.bookings / max) * (H - 20)).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ background: "#fafafa" }}>
      <polyline points={pts} fill="none" stroke="#fa8c16" strokeWidth={2} />
      {series.map((p, i) => (
        <g key={i}>
          <circle cx={i * xStep} cy={H - (p.bookings / max) * (H - 20)} r={2.5} fill="#fa8c16" />
          {i % Math.ceil(n / 8) === 0 && (
            <text x={i * xStep} y={H - 4} fontSize={9} fill="#999" textAnchor="middle">
              {(p.date || "").slice(5)}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}
