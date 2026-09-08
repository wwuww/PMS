import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Row,
  Select,
  Space,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  DownloadOutlined,
  ReloadOutlined,
  DollarOutlined,
  ShopOutlined,
  RiseOutlined,
  FundOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { useSearchParams } from "react-router-dom";
import { useTenant } from "../store/tenant";
import { exportReport } from "../api/endpoints";
import { fmtBps, fmtCents } from "../utils/format";
import type { ReportExport, ReportType } from "../api/types";
import StatCard from "../components/StatCard";
import "./Reports.css";

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const RTYPES: { value: ReportType; label: string; needHotel: boolean }[] = [
  { value: "hotel_ranking", label: "门店营收排行", needHotel: false },
  { value: "channel_revenue", label: "渠道营收", needHotel: true },
  { value: "room_type_revenue", label: "房型营收", needHotel: true },
  { value: "dashboard", label: "门店营业日报", needHotel: true },
];

type Row = Record<string, unknown>;

function collectKeys(rows: Row[]): string[] {
  const set = new Set<string>();
  rows.forEach((r) => Object.keys(r).forEach((k) => set.add(k)));
  return Array.from(set);
}

function toCSV(rows: Row[]): string {
  if (!rows.length) return "";
  const cols = collectKeys(rows);
  const escape = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const head = cols.map(escape).join(",");
  const body = rows
    .map((r) => cols.map((c) => escape(r[c])).join(","))
    .join("\n");
  return `${head}\n${body}`;
}

function extractRows(report: ReportExport | null): Row[] {
  if (!report) return [];
  if (Array.isArray(report.hotels)) return report.hotels;
  if (Array.isArray(report.channels)) return report.channels;
  if (Array.isArray(report.room_types)) return report.room_types;
  if (Array.isArray(report.daily_series)) return report.daily_series;
  if (Array.isArray(report.data)) return report.data;
  return [];
}

export default function Reports() {
  const { tenantCode, hotelId, hotels } = useTenant();
  const [data, setData] = useState<ReportExport | null>(null);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();
  const [searchParams] = useSearchParams();
  // 来自通知中心的深链：?type=dashboard&date=2026-09-03
  const deepType = searchParams.get("type");
  const deepDate = searchParams.get("date");
  const booted = useRef(false);

  const rows = useMemo(() => extractRows(data), [data]);

  // dashboard（门店营业日报）的顶部汇总卡：后端直接返回顶层聚合字段
  const summary = useMemo(() => {
    const d = data as (ReportExport & {
      room_revenue_cents?: number;
      other_revenue_cents?: number;
      total_revenue_cents?: number;
      revpar_cents?: number;
      adr_cents?: number;
      occ_pct_bps?: number;
      hotel_name?: string;
      days?: number;
    }) | null;
    if (typeof d?.room_revenue_cents !== "number") return null;
    return {
      room: d.room_revenue_cents,
      other: d.other_revenue_cents ?? 0,
      total: d.total_revenue_cents ?? 0,
      revpar: d.revpar_cents ?? 0,
      adr: d.adr_cents ?? 0,
      occPctBps: d.occ_pct_bps ?? 0,
      hotelName: d.hotel_name,
      days: d.days,
    };
  }, [data]);

  const run = async () => {
    if (!tenantCode) return;
    const v = await form.validateFields();
    const range = (v.range as [dayjs.Dayjs, dayjs.Dayjs] | undefined) || undefined;
    setLoading(true);
    try {
      const res = await exportReport(tenantCode, {
        report_type: v.report_type,
        hotel_id: v.hotel_id || null,
        start_date: range ? dayjs(range[0]).format("YYYY-MM-DD") : null,
        end_date: range ? dayjs(range[1]).format("YYYY-MM-DD") : null,
        format: "json",
      });
      setData(res);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || "报表生成失败");
    } finally {
      setLoading(false);
    }
  };

  // 深链落地：回填报表类型/日期并在门店就绪时自动出报表（仅首帧执行一次）
  useEffect(() => {
    if (booted.current || !tenantCode) return;
    if (!deepType && !deepDate) return;
    booted.current = true;
    const validType = RTYPES.some((r) => r.value === (deepType as ReportType));
    form.setFieldsValue({
      ...(validType ? { report_type: deepType as ReportType } : {}),
      ...(deepDate
        ? { range: [dayjs(deepDate), dayjs(deepDate)] as [dayjs.Dayjs, dayjs.Dayjs] }
        : {}),
    });
    if (hotelId) {
      setTimeout(() => run(), 0);
    } else {
      message.info("请先选择门店，再点击「生成报表」");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, hotelId, deepType, deepDate]);

  const columns = useMemo<ColumnsType<Row>>(() => {
    if (!rows.length) return [];
    return collectKeys(rows).map((k) => {
      // 动态判断：列首行若为 number → 数字列 → 右对齐 + 等宽
      const isNum = rows.length > 0 && typeof rows[0][k] === "number";
      return {
        title: k,
        dataIndex: k,
        key: k,
        align: isNum ? ("right" as const) : ("left" as const),
        render: (val: unknown) =>
          typeof val === "number"
            ? val.toLocaleString("zh-CN")
            : val == null
            ? "—"
            : String(val),
      };
    });
  }, [rows]);

  const handleCSV = () => {
    if (!rows.length) return;
    const csv = toCSV(rows);
    const blob = new Blob([`﻿${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `report_${
      (data?.report_type as string) || "export"
    }_${dayjs().format("YYYYMMDD")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div
        className="reports-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: 20,
        }}
      >
        <div>
          <Title level={4} style={{ margin: 0, marginBottom: 4 }}>
            报表中心
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            多维度经营报表 · 导出与下载
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={run} loading={loading} type="primary">
            生成报表
          </Button>
          <Button icon={<DownloadOutlined />} disabled={!rows.length} onClick={handleCSV}>
            导出 CSV
          </Button>
        </Space>
      </div>
      {summary && (
        <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
          <Col xs={12} sm={12} md={6}>
            <StatCard
              label="房票收入"
              value={fmtCents(summary.room)}
              sub={`${summary.hotelName ?? ""}${summary.days ? ` · ${summary.days} 天` : ""}`}
              accent="#1677ff"
              icon={<DollarOutlined />}
            />
          </Col>
          <Col xs={12} sm={12} md={6}>
            <StatCard
              label="其他应收"
              value={fmtCents(summary.other)}
              sub="杂费 / 餐饮 / 其他"
              accent="#13c2c2"
              icon={<ShopOutlined />}
            />
          </Col>
          <Col xs={12} sm={12} md={6}>
            <StatCard
              label="总营收"
              value={fmtCents(summary.total)}
              sub="房票 + 其他应收"
              accent="#fa8c16"
              icon={<RiseOutlined />}
            />
          </Col>
          <Col xs={12} sm={12} md={6}>
            <StatCard
              label="单房收益 RevPAR"
              value={fmtCents(summary.revpar)}
              sub={`ADR ${fmtCents(summary.adr)} · 出租率 ${fmtBps(summary.occPctBps)}`}
              accent="#722ed1"
              icon={<FundOutlined />}
            />
          </Col>
        </Row>
      )}
      {(deepType || deepDate) && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={
            deepDate
              ? `来自通知中心：营业日 ${deepDate} 的营业日报已自动载入`
              : "来自通知中心：已按消息指定的报表类型载入"
          }
        />
      )}
      <Card className="reports-filter-card">
        <Form
          form={form}
          layout="inline"
          initialValues={{ report_type: "hotel_ranking", hotel_id: hotelId ?? undefined }}
        >
          <Form.Item name="report_type" label="报表类型" rules={[{ required: true }]}>
            <Select
              style={{ width: 180 }}
              options={RTYPES.map((r) => ({ value: r.value, label: r.label }))}
            />
          </Form.Item>
          <Form.Item
            name="hotel_id"
            label="门店（渠道/房型/日报必填）"
            rules={[{ required: true, message: "请选择门店" }]}
          >
            <Select
              style={{ width: 200 }}
              allowClear
              options={hotels.map((h) => ({
                value: h.id,
                label: `${h.name}（${h.code}）`,
              }))}
              placeholder="选择门店"
            />
          </Form.Item>
          <Form.Item name="range" label="日期区间（选填）">
            <RangePicker />
          </Form.Item>
        </Form>
      </Card>
      <Card
        className="reports-preview-card"
        title={
          data
            ? `报表：${data.report_type ?? "未命名"}（${rows.length} 行）`
            : "报表预览"
        }
      >
        {rows.length ? (
          <Table
            rowKey={(_, i) => String(i)}
            size="small"
            loading={loading}
            dataSource={rows}
            columns={columns}
            scroll={{ x: "max-content" }}
            pagination={{ pageSize: 20 }}
            className="reports-table"
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            imageStyle={{ height: 80 }}
            description={
              <div>
                <div style={{ marginBottom: 4, color: "#646a73" }}>暂无报表数据</div>
                <div style={{ fontSize: 12, color: "#8a919c" }}>
                  选择报表类型与门店后点击「生成报表」开始查询
                </div>
              </div>
            }
            className="reports-empty"
            style={{ padding: "40px 0" }}
          >
            <Button type="primary" onClick={run} icon={<ReloadOutlined />} loading={loading}>
              立即生成
            </Button>
          </Empty>
        )}
      </Card>
    </div>
  );
}
