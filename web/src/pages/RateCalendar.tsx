import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Form,
  InputNumber,
  Modal,
  Radio,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import {
  LeftOutlined,
  RightOutlined,
  EditOutlined,
  RiseOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import dayjs, { Dayjs } from "dayjs";
import { useTenant } from "../store/tenant";
import {
  listPriceCalendar,
  batchUpsertPriceCalendar,
  upsertPriceCalendar,
  listRoomTypes,
} from "../api/endpoints";
import type { PriceCalendar, PriceCalendarCreate, RoomType } from "../api/types";
import { fmtCents } from "../utils/format";

const { Title, Text } = Typography;

const WEEK_HEADER = ["一", "二", "三", "四", "五", "六", "日"];

export default function RateCalendar() {
  const { tenantCode } = useTenant();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [roomTypes, setRoomTypes] = useState<RoomType[]>([]);
  const [roomTypeId, setRoomTypeId] = useState<string | undefined>();
  const [month, setMonth] = useState<Dayjs>(dayjs().startOf("month"));
  const [priceMap, setPriceMap] = useState<Map<string, number>>(new Map());
  const [loading, setLoading] = useState(false);

  // 批量改价
  const [showBatch, setShowBatch] = useState(false);
  const [batchForm] = Form.useForm();
  const [batchLoading, setBatchLoading] = useState(false);

  // 单日改价
  const [showDay, setShowDay] = useState(false);
  const [dayTarget, setDayTarget] = useState<Dayjs | null>(null);
  const [dayForm] = Form.useForm();
  const [dayLoading, setDayLoading] = useState(false);

  const refreshRoomTypes = async () => {
    if (!tenantCode) return;
    const rt = await listRoomTypes(tenantCode);
    setRoomTypes(rt);
    // 深链：?room_type=<id> 优先选中指定房型
    const fromUrl = searchParams.get("room_type");
    if (fromUrl && rt.some((r) => r.id === fromUrl)) {
      setRoomTypeId(fromUrl);
    } else if (!roomTypeId && rt.length) {
      setRoomTypeId(rt[0].id);
    }
  };

  // 深链：?date=YYYY-MM-DD → 跳转到对应月份
  useEffect(() => {
    const d = searchParams.get("date");
    if (d && dayjs(d).isValid()) {
      setMonth(dayjs(d).startOf("month"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshPrices = async () => {
    if (!tenantCode || !roomTypeId) return;
    setLoading(true);
    try {
      const rows: PriceCalendar[] = await listPriceCalendar(tenantCode, {
        room_type_id: roomTypeId,
        start: month.startOf("month").format("YYYY-MM-DD"),
        end: month.endOf("month").format("YYYY-MM-DD"),
      });
      const m = new Map<string, number>();
      rows.forEach((r) => m.set(r.date, r.price));
      setPriceMap(m);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载价格失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshRoomTypes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  useEffect(() => {
    refreshPrices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, roomTypeId, month]);

  // 构建 6 周（42 格）日历网格，周一为首列
  const cells = useMemo(() => {
    const first = month.startOf("month");
    const dow = first.day(); // 0=周日
    const leading = (dow + 6) % 7;
    const arr: { date: Dayjs; inMonth: boolean }[] = [];
    for (let i = 0; i < 42; i++) {
      const d = first.subtract(leading, "day").add(i, "day");
      arr.push({ date: d, inMonth: d.month() === month.month() });
    }
    return arr;
  }, [month]);

  const handleBatch = async () => {
    const v = await batchForm.validateFields();
    if (!roomTypeId) return;
    const mode: string = v.mode;
    const priceCents = Math.round(v.price_yuan * 100);
    const dates: string[] = [];
    cells.forEach(({ date, inMonth }) => {
      if (!inMonth) return;
      const dow = date.day();
      const isWeekend = dow === 0 || dow === 6;
      if (mode === "all") dates.push(date.format("YYYY-MM-DD"));
      else if (mode === "weekday" && !isWeekend) dates.push(date.format("YYYY-MM-DD"));
      else if (mode === "weekend" && isWeekend) dates.push(date.format("YYYY-MM-DD"));
    });
    if (!dates.length) {
      message.warning("当前模式无匹配日期");
      return;
    }
    setBatchLoading(true);
    try {
      const body: PriceCalendarCreate[] = dates.map((d) => ({
        room_type_id: roomTypeId,
        date: d,
        price: priceCents,
      }));
      const res = await batchUpsertPriceCalendar(tenantCode!, body);
      message.success(`已更新 ${res.updated} 天` + (res.blocked.length ? `，${res.blocked.length} 天被集团限价拦截` : ""));
      if (res.blocked.length) console.warn("价格被拦截:", res.blocked);
      setShowBatch(false);
      batchForm.resetFields();
      await refreshPrices();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "批量改价失败");
    } finally {
      setBatchLoading(false);
    }
  };

  const openDay = (date: Dayjs) => {
    setDayTarget(date);
    const existing = priceMap.get(date.format("YYYY-MM-DD"));
    dayForm.setFieldsValue({
      price_yuan: existing != null ? existing / 100 : 300,
    });
    setShowDay(true);
  };

  const handleDay = async () => {
    const v = await dayForm.validateFields();
    if (!roomTypeId || !dayTarget) return;
    setDayLoading(true);
    try {
      await upsertPriceCalendar(tenantCode!, {
        room_type_id: roomTypeId,
        date: dayTarget.format("YYYY-MM-DD"),
        price: Math.round(v.price_yuan * 100),
      });
      message.success("已保存当日价格");
      setShowDay(false);
      await refreshPrices();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setDayLoading(false);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          价格日历
        </Title>
        <Space wrap>
          <Select
            placeholder="选择房型"
            style={{ width: 220 }}
            value={roomTypeId}
            onChange={setRoomTypeId}
            options={roomTypes.map((r) => ({ value: r.id, label: `${r.name}（${r.code}）` }))}
          />
          <Button icon={<LeftOutlined />} onClick={() => setMonth((m) => m.subtract(1, "month"))} />
          <DatePicker
            picker="month"
            value={month}
            onChange={(v) => v && setMonth(v.startOf("month"))}
            allowClear={false}
            style={{ width: 140 }}
          />
          <Button icon={<RightOutlined />} onClick={() => setMonth((m) => m.add(1, "month"))} />
          <Button
            icon={<RiseOutlined />}
            onClick={() =>
              navigate(
                `/yield?room_type=${roomTypeId ?? ""}${month ? `&date=${month.format("YYYY-MM-DD")}` : ""}`
              )
            }
          >
            收益建议
          </Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => setShowBatch(true)}
            disabled={!roomTypeId}
          >
            批量改价
          </Button>
        </Space>
      </div>

      <Card size="small" loading={loading}>
        {!roomTypeId ? (
          <Empty description="请先选择房型" />
        ) : (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 6, marginBottom: 6 }}>
              {WEEK_HEADER.map((w) => (
                <div key={w} style={{ textAlign: "center", fontWeight: 600, color: "#888" }}>
                  {w}
                </div>
              ))}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 6 }}>
              {cells.map(({ date, inMonth }, idx) => {
                const key = date.format("YYYY-MM-DD");
                const price = priceMap.get(key);
                const isToday = date.isSame(dayjs(), "day");
                const dow = date.day();
                const isWeekend = dow === 0 || dow === 6;
                return (
                  <div
                    key={idx}
                    onClick={() => inMonth && openDay(date)}
                    style={{
                      minHeight: 64,
                      padding: 6,
                      borderRadius: 8,
                      border: isToday ? "2px solid #1677ff" : "1px solid #f0f0f0",
                      background: inMonth ? (isWeekend ? "#fff7f5" : "#fff") : "#fafafa",
                      opacity: inMonth ? 1 : 0.45,
                      cursor: inMonth ? "pointer" : "default",
                      transition: "box-shadow .15s",
                    }}
                  >
                    <div style={{ fontSize: 12, color: "#999" }}>{date.date()}</div>
                    {inMonth &&
                      (price != null ? (
                        <div style={{ marginTop: 4, fontWeight: 600 }}>{fmtCents(price)}</div>
                      ) : (
                        <Tag color="default" style={{ marginTop: 4 }}>
                          未设价
                        </Tag>
                      ))}
                    {inMonth && price != null && (
                      <div style={{ marginTop: 2 }}>
                        <EditOutlined style={{ fontSize: 11, color: "#bbb" }} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <Text type="secondary" style={{ display: "block", marginTop: 10, fontSize: 12 }}>
              点击任意日期可单日改价；使用「批量改价」可一次性设定全月 / 工作日 / 周末价格。
            </Text>
          </div>
        )}
      </Card>

      {/* 批量改价 */}
      <Modal
        title={`批量改价 · ${roomTypes.find((r) => r.id === roomTypeId)?.name || ""} · ${month.format("YYYY年M月")}`}
        open={showBatch}
        onOk={handleBatch}
        confirmLoading={batchLoading}
        onCancel={() => setShowBatch(false)}
        okText="应用"
        cancelText="取消"
      >
        <Form form={batchForm} layout="vertical" initialValues={{ mode: "all", price_yuan: 300 }}>
          <Form.Item name="mode" label="应用范围" rules={[{ required: true }]}>
            <Radio.Group optionType="button" buttonStyle="solid">
              <Radio value="all">全月</Radio>
              <Radio value="weekday">仅工作日</Radio>
              <Radio value="weekend">仅周末</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="price_yuan" label="价格（元）" rules={[{ required: true, message: "请输入价格" }]}>
            <InputNumber style={{ width: "100%" }} min={0} step={10} addonAfter="元" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 单日改价 */}
      <Modal
        title={dayTarget ? `单日改价 · ${dayTarget.format("YYYY-MM-DD")}` : "单日改价"}
        open={showDay}
        onOk={handleDay}
        confirmLoading={dayLoading}
        onCancel={() => setShowDay(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={dayForm} layout="vertical">
          <Form.Item name="price_yuan" label="价格（元）" rules={[{ required: true, message: "请输入价格" }]}>
            <InputNumber style={{ width: "100%" }} min={0} step={10} addonAfter="元" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
