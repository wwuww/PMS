import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CalendarOutlined,
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
  RiseOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import {
  getYieldRule,
  updateYieldRule,
  recommendPrice,
  listYieldRecommendations,
  applyYieldRecommendation,
  rejectYieldRecommendation,
  listRoomTypes,
} from "../api/endpoints";
import type {
  PricingRule,
  PriceRecommend,
  RoomType,
} from "../api/types";
import { fmtCents, fmtBps } from "../utils/format";

const { Title, Text } = Typography;

export default function Yield() {
  const { tenantCode, hotelId } = useTenant();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [rule, setRule] = useState<PricingRule | null>(null);
  const [recForm] = Form.useForm();
  const [recommendations, setRecommendations] = useState<PriceRecommend[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [r, rt] = await Promise.all([
        getYieldRule(tenantCode),
        listRoomTypes(tenantCode),
      ]);
      setRule(r);
      setRoomTypes(rt);
      setRecommendations(await listYieldRecommendations(tenantCode, hotelId));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, hotelId]);

  // 深链：?date=&room_type= 回填生成建议表单（来自价格日历页跳转）
  useEffect(() => {
    const d = searchParams.get("date");
    const rt = searchParams.get("room_type");
    const v: Record<string, unknown> = {};
    if (d && dayjs(d).isValid()) v.business_date = dayjs(d);
    if (rt) v.room_type_id = rt;
    if (Object.keys(v).length) recForm.setFieldsValue(v);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveRule = async () => {
    const v = await recForm.validateFields();
    try {
      await updateYieldRule(tenantCode, {
        enabled: v.enabled ? 1 : 0,
        high_occ_threshold: v.high_occ_threshold,
        low_occ_threshold: v.low_occ_threshold,
        max_uplift_bps: v.max_uplift_bps,
        max_discount_bps: v.max_discount_bps,
        weekend_uplift_bps: v.weekend_uplift_bps,
        competitor_strategy: v.competitor_strategy,
        competitor_undercut_bps: v.competitor_undercut_bps,
      });
      message.success("调价规则已更新");
      refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    }
  };

  const genRecommend = async () => {
    const v = await recForm.validateFields();
    try {
      const rec = await recommendPrice(tenantCode, {
        hotel_id: hotelId ?? v.hotel_id,
        room_type_id: v.room_type_id ?? null,
        business_date: dayjs(v.business_date).format("YYYY-MM-DD"),
        base_price_cents: Math.round(v.base_price_yuan * 100),
        competitor_price_cents: v.competitor_price_yuan
          ? Math.round(v.competitor_price_yuan * 100)
          : null,
        lead_time_days: v.lead_time_days ?? null,
      });
      setRecommendations((r) => [rec, ...r]);
      message.success(
        `建议价 ${fmtCents(rec.recommended_price_cents)}（${fmtBps(rec.adjustment_bps)}）`
      );
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "生成失败");
    }
  };

  // M20：建议一键应用到价格日历（弹窗可选 单日 / 日期区间）
  const [applyTarget, setApplyTarget] = useState<PriceRecommend | null>(null);
  const [applyForm] = Form.useForm();

  const openApply = (rec: PriceRecommend) => {
    setApplyTarget(rec);
    applyForm.setFieldsValue({ mode: "single", range: null });
  };

  const submitApply = async () => {
    if (!applyTarget) return;
    const v = await applyForm.validateFields();
    const range =
      v.mode === "range" && v.range?.[0] && v.range?.[1]
        ? {
            start: dayjs(v.range[0]).format("YYYY-MM-DD"),
            end: dayjs(v.range[1]).format("YYYY-MM-DD"),
          }
        : undefined;
    try {
      const out = await applyYieldRecommendation(tenantCode, applyTarget.id, range);
      message.success({
        content: (
          <span>
            {`已写入价格日历 ${out.dates.length} 天：${fmtCents(out.price)}` +
              `（新建 ${out.created} / 更新 ${out.updated}） `}
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={() =>
                navigate(
                  `/rate-calendar?date=${out.dates[0]}&room_type=${out.room_type_id}`
                )
              }
            >
              查看日历 →
            </Button>
          </span>
        ),
        duration: 6,
      });
      setApplyTarget(null);
      refresh();
    } catch (e: any) {
      message.error(e?.message || "应用失败");
    }
  };

  // M20：拒绝建议
  const rejectRec = async (rec: PriceRecommend) => {
    try {
      await rejectYieldRecommendation(tenantCode, rec.id);
      message.info("建议已拒绝");
      refresh();
    } catch (e: any) {
      message.error(e?.message || "操作失败");
    }
  };

  const recColumns = [
    { title: "营业日", dataIndex: "business_date", width: 110 },
    {
      title: "房型",
      dataIndex: "room_type_id",
      width: 80,
      render: (v: string | null) =>
        v ? roomTypes.find((r) => r.id === v)?.name ?? `#${v}` : "-",
    },
    {
      title: "基价",
      dataIndex: "base_price_cents",
      render: (v: number) => fmtCents(v),
    },
    {
      title: "建议价",
      dataIndex: "recommended_price_cents",
      render: (v: number) => <Text strong>{fmtCents(v)}</Text>,
    },
    {
      title: "调整",
      dataIndex: "adjustment_bps",
      render: (v: number) => (
        <Tag color={v > 0 ? "red" : "green"}>{fmtBps(v)}</Tag>
      ),
    },
    { title: "需求指数", dataIndex: "demand_index", width: 90 },
    {
      title: "理由",
      dataIndex: "rationale",
      render: (v: string[]) => (
        <Space wrap>
          {v?.map((r, i) => (
            <Tag key={i}>{r}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 150,
      render: (_: unknown, rec: PriceRecommend) =>
        rec.status === "suggested" && rec.room_type_id ? (
          <Space size={4}>
            <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => openApply(rec)}>
              应用
            </Button>
            <Popconfirm
              title="拒绝该建议？"
              onConfirm={() => rejectRec(rec)}
            >
              <Button size="small" icon={<CloseOutlined />}>
                拒绝
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Tag>{rec.status === "applied" ? "已应用" : rec.status === "rejected" ? "已拒绝" : rec.status}</Tag>
        ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          收益管理（动态定价）
        </Title>
        <Space>
          <Button
            icon={<CalendarOutlined />}
            onClick={() => navigate("/rate-calendar")}
          >
            价格日历
          </Button>
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      <Row gutter={16}>
        <Col span={10}>
          <Card title="当前调价规则" size="small">
            <Form
              form={recForm}
              layout="vertical"
              initialValues={{
                enabled: true,
                high_occ_threshold: rule?.high_occ_threshold ?? 85,
                low_occ_threshold: rule?.low_occ_threshold ?? 40,
                max_uplift_bps: rule?.max_uplift_bps ?? 2000,
                max_discount_bps: rule?.max_discount_bps ?? 1500,
                weekend_uplift_bps: rule?.weekend_uplift_bps ?? 800,
                competitor_strategy: rule?.competitor_strategy ?? "match",
                competitor_undercut_bps: rule?.competitor_undercut_bps ?? 300,
                business_date: dayjs(),
                base_price_yuan: 300,
                room_type_id: undefined,
                lead_time_days: 7,
              }}
            >
              <Form.Item name="enabled" label="启用动态定价" valuePropName="checked">
                <Select
                  options={[
                    { value: true, label: "启用" },
                    { value: false, label: "停用" },
                  ]}
                />
              </Form.Item>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item name="high_occ_threshold" label="高出租率阈值(%)">
                    <InputNumber min={0} max={100} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="low_occ_threshold" label="低出租率阈值(%)">
                    <InputNumber min={0} max={100} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="max_uplift_bps" label="最大加价(bps)">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="max_discount_bps" label="最大降价(bps)">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="weekend_uplift_bps" label="周末加价(bps)">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="competitor_strategy" label="竞品策略">
                    <Select
                      options={[
                        { value: "none", label: "不跟" },
                        { value: "match", label: "跟价" },
                        { value: "undercut", label: "压价" },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Button block onClick={saveRule}>
                保存规则
              </Button>
            </Form>
          </Card>
        </Col>

        <Col span={14}>
          <Card
            title="生成调价建议"
            size="small"
            extra={
              <Button
                type="primary"
                icon={<RiseOutlined />}
                onClick={genRecommend}
              >
                生成建议
              </Button>
            }
            style={{ marginBottom: 16 }}
          >
            <Space wrap>
              <Form.Item
                name="hotel_id"
                label="门店 ID"
                style={{ marginBottom: 0 }}
              >
                <InputNumber />
              </Form.Item>
              <Form.Item
                name="room_type_id"
                label="房型"
                style={{ marginBottom: 0 }}
              >
                <Select
                  allowClear
                  style={{ width: 140 }}
                  options={roomTypes.map((r) => ({
                    value: r.id,
                    label: r.name,
                  }))}
                />
              </Form.Item>
              <Form.Item
                name="business_date"
                label="营业日"
                style={{ marginBottom: 0 }}
              >
                <DatePicker />
              </Form.Item>
              <Form.Item
                name="base_price_yuan"
                label="基价(元)"
                style={{ marginBottom: 0 }}
              >
                <InputNumber min={1} addonAfter="元" />
              </Form.Item>
              <Form.Item
                name="competitor_price_yuan"
                label="竞品价(元)"
                style={{ marginBottom: 0 }}
              >
                <InputNumber min={1} addonAfter="元" />
              </Form.Item>
              <Form.Item
                name="lead_time_days"
                label="提前天数"
                style={{ marginBottom: 0 }}
              >
                <InputNumber min={0} max={365} />
              </Form.Item>
            </Space>
          </Card>

          <Card title="调价建议历史" size="small">
            <Table
              rowKey="id"
              size="small"
              loading={loading}
              dataSource={recommendations}
              columns={recColumns}
              pagination={{ pageSize: 6 }}
            />
          </Card>
        </Col>
      </Row>

      {/* M20：应用弹窗（单日 / 日期区间批量落价） */}
      <Modal
        title={`应用建议 #${applyTarget?.id ?? ""} → 价格日历`}
        open={!!applyTarget}
        onOk={submitApply}
        onCancel={() => setApplyTarget(null)}
        okText="应用"
        cancelText="取消"
        destroyOnClose
      >
        {applyTarget && (
          <>
            <Typography.Paragraph>
              建议价 <Text strong>{fmtCents(applyTarget.recommended_price_cents)}</Text>
              （基价 {fmtCents(applyTarget.base_price_cents)}，{fmtBps(applyTarget.adjustment_bps)}）
              ，房型 {applyTarget.room_type_id
                ? roomTypes.find((r) => r.id === applyTarget.room_type_id)?.name ?? `#${applyTarget.room_type_id}`
                : "未指定"}
            </Typography.Paragraph>
            <Form form={applyForm} layout="vertical" initialValues={{ mode: "single" }}>
              <Form.Item name="mode" label="落价方式">
                <Radio.Group
                  options={[
                    { value: "single", label: `仅建议日（${applyTarget.business_date}）` },
                    { value: "range", label: "日期区间（逐日同一价）" },
                  ]}
                  optionType="button"
                />
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prev, cur) => prev.mode !== cur.mode}
              >
                {({ getFieldValue }) =>
                  getFieldValue("mode") === "range" ? (
                    <Form.Item
                      name="range"
                      label="日期区间（含首尾，最多 365 天）"
                      rules={[{ required: true, message: "请选择日期区间" }]}
                    >
                      <DatePicker.RangePicker style={{ width: "100%" }} />
                    </Form.Item>
                  ) : null
                }
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </div>
  );
}
