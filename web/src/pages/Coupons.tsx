// 批次④ - 优惠券管理（券模板 + 券实例）
// Tab1 券模板：列表 + 新建模板 Modal；Tab2 券实例：列表 + 发券 Modal + 核销输入 + 作废
// 门控：useCan("COUPON_MANAGE")，后端要求 coupon.manage
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import {
  createCouponTemplate,
  issueCoupons,
  listCouponTemplates,
  listCoupons,
  useCoupon,
  voidCoupon,
} from "../api/endpoints";
import type { Coupon, CouponTemplate } from "../api/types";
import { useTenant } from "../store/tenant";
import { currentOperator, useCan } from "../utils/permission";

const { RangePicker } = DatePicker;

const TICKET_TYPE_LABEL: Record<string, string> = {
  VOUCHER: "代金券",
  FREE: "免费券",
};

const TICKET_TYPE_OPTIONS = [
  { value: "VOUCHER", label: "代金券" },
  { value: "FREE", label: "免费券" },
];

const DISCOUNT_TYPE_LABEL: Record<string, string> = {
  AMOUNT: "减免金额",
  PERCENT: "折扣百分比",
  FIXED_PRICE: "固定价",
};

const DISCOUNT_TYPE_OPTIONS = [
  { value: "AMOUNT", label: "减免金额（分）" },
  { value: "PERCENT", label: "折扣百分比（如 85 表示 8.5 折）" },
  { value: "FIXED_PRICE", label: "固定价（分）" },
];

const STATUS_META: Record<string, { label: string; color: string }> = {
  ISSUED: { label: "已发放", color: "blue" },
  USED: { label: "已核销", color: "green" },
  VOID: { label: "已作废", color: "red" },
  EXPIRED: { label: "已过期", color: "default" },
};

const STATUS_FILTER_OPTIONS = [
  { value: "ALL", label: "全部状态" },
  { value: "ISSUED", label: "已发放" },
  { value: "USED", label: "已核销" },
  { value: "VOID", label: "已作废" },
  { value: "EXPIRED", label: "已过期" },
];

/** 折扣值展示：金额/固定价按分转元，百分比按「x 折」展示。 */
function renderDiscount(type?: string | null, value?: number | null): string {
  if (value == null) return "—";
  if (type === "PERCENT") return `${value / 10} 折`;
  return `¥${(value / 100).toFixed(2)}`;
}

export default function Coupons() {
  const { tenantCode } = useTenant();
  const canManage = useCan("COUPON_MANAGE");

  const [tab, setTab] = useState<string>("templates");

  // ---- 券模板 ----
  const [templates, setTemplates] = useState<CouponTemplate[]>([]);
  const [tplLoading, setTplLoading] = useState(false);
  const [tplOpen, setTplOpen] = useState(false);
  const [tplForm] = Form.useForm();
  const [tplSaving, setTplSaving] = useState(false);

  // ---- 券实例 ----
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [cpLoading, setCpLoading] = useState(false);
  const [cpStatus, setCpStatus] = useState<string>("ALL");
  const [cpBookingId, setCpBookingId] = useState<string>("");
  const [cpNo, setCpNo] = useState<string>("");

  const [issueOpen, setIssueOpen] = useState(false);
  const [issueForm] = Form.useForm();
  const [issuing, setIssuing] = useState(false);

  const [useForm] = Form.useForm();
  const [using, setUsing] = useState(false);

  const watchTemplateId = Form.useWatch("template_id", issueForm);

  const fetchTemplates = useCallback(async () => {
    if (!tenantCode) return;
    setTplLoading(true);
    try {
      const list = await listCouponTemplates(tenantCode);
      setTemplates(Array.isArray(list) ? list : []);
    } catch (e: unknown) {
      message.error((e as Error).message || "加载券模板失败");
      setTemplates([]);
    } finally {
      setTplLoading(false);
    }
  }, [tenantCode]);

  const fetchCoupons = useCallback(async () => {
    if (!tenantCode) return;
    setCpLoading(true);
    try {
      const list = await listCoupons(tenantCode, {
        status: cpStatus === "ALL" ? undefined : cpStatus,
        booking_id: cpBookingId.trim() || undefined,
        coupon_no: cpNo.trim() || undefined,
        limit: 200,
      });
      setCoupons(Array.isArray(list) ? list : []);
    } catch (e: unknown) {
      message.error((e as Error).message || "加载优惠券失败");
      setCoupons([]);
    } finally {
      setCpLoading(false);
    }
  }, [tenantCode, cpStatus, cpBookingId, cpNo]);

  useEffect(() => {
    void fetchTemplates();
  }, [fetchTemplates]);

  useEffect(() => {
    if (tab === "instances") void fetchCoupons();
  }, [tab, fetchCoupons]);

  const tplMap = useMemo(() => {
    const m = new Map<string, CouponTemplate>();
    templates.forEach((t) => m.set(String(t.id), t));
    return m;
  }, [templates]);

  const openTplCreate = () => {
    tplForm.resetFields();
    tplForm.setFieldsValue({
      ticket_type: "VOUCHER",
      discount_type: "AMOUNT",
      total_quantity: 100,
      operator: currentOperator(),
    });
    setTplOpen(true);
  };

  const submitTpl = async () => {
    const v = await tplForm.validateFields();
    const range = v.range as [Dayjs, Dayjs] | null | undefined;
    if (!range?.[0] || !range?.[1]) {
      message.error("请选择有效期");
      return;
    }
    setTplSaving(true);
    try {
      await createCouponTemplate(tenantCode, {
        hotel_id: v.hotel_id ?? null,
        code: String(v.code || "").trim(),
        name: String(v.name || "").trim(),
        ticket_type: v.ticket_type || "VOUCHER",
        discount_type: v.discount_type || "AMOUNT",
        discount_value: v.discount_value ?? 0,
        valid_from: range[0].format("YYYY-MM-DD"),
        valid_to: range[1].format("YYYY-MM-DD"),
        total_quantity: v.total_quantity ?? 0,
        operator: currentOperator(),
      });
      message.success("券模板已创建");
      setTplOpen(false);
      tplForm.resetFields();
      await fetchTemplates();
    } catch (e: unknown) {
      message.error((e as Error).message || "创建券模板失败");
    } finally {
      setTplSaving(false);
    }
  };

  const openIssue = () => {
    issueForm.resetFields();
    issueForm.setFieldsValue({
      count: 1,
      is_cover_other_discount: false,
      is_transfer_to_account: false,
      operator: currentOperator(),
    });
    setIssueOpen(true);
  };

  const submitIssue = async () => {
    const v = await issueForm.validateFields();
    const range = v.range as [Dayjs, Dayjs] | null | undefined;
    const hasTemplate = v.template_id != null && v.template_id !== "";
    // 散券（未选模板）必须手填规则与有效期
    if (!hasTemplate && (!range?.[0] || !range?.[1])) {
      message.error("散券请填写有效期");
      return;
    }
    setIssuing(true);
    try {
      const created = await issueCoupons(tenantCode, {
        hotel_id: v.hotel_id ?? null,
        template_id: hasTemplate ? v.template_id : null,
        count: Number(v.count || 1),
        ticket_type: hasTemplate ? undefined : v.ticket_type || "VOUCHER",
        discount_type: hasTemplate ? undefined : v.discount_type || "AMOUNT",
        discount_value: hasTemplate ? undefined : v.discount_value ?? 0,
        valid_from: range?.[0]?.format("YYYY-MM-DD") ?? null,
        valid_to: range?.[1]?.format("YYYY-MM-DD") ?? null,
        is_cover_other_discount: !!v.is_cover_other_discount,
        is_transfer_to_account: !!v.is_transfer_to_account,
        operator: currentOperator(),
      });
      const n = Array.isArray(created) ? created.length : Number(v.count || 1);
      message.success(`发券成功，共 ${n} 张`);
      setIssueOpen(false);
      issueForm.resetFields();
      await fetchCoupons();
      await fetchTemplates();
    } catch (e: unknown) {
      message.error((e as Error).message || "发券失败");
    } finally {
      setIssuing(false);
    }
  };

  const submitUse = async () => {
    const v = await useForm.validateFields();
    setUsing(true);
    try {
      const c = await useCoupon(tenantCode, {
        coupon_no: String(v.coupon_no || "").trim(),
        booking_id: v.booking_id ?? null,
        bill_id: v.bill_id ?? null,
        operator: currentOperator(),
      });
      message.success(`券 ${c.coupon_no || v.coupon_no} 核销成功`);
      useForm.setFieldsValue({ coupon_no: "" });
      await fetchCoupons();
    } catch (e: unknown) {
      message.error((e as Error).message || "核销失败");
    } finally {
      setUsing(false);
    }
  };

  const doVoid = async (row: Coupon) => {
    try {
      await voidCoupon(tenantCode, row.id as number, {
        reason: "前台作废",
        operator: currentOperator(),
      });
      message.success(`券 ${row.coupon_no || row.id} 已作废`);
      await fetchCoupons();
    } catch (e: unknown) {
      message.error((e as Error).message || "作废失败");
    }
  };

  const tplColumns: ColumnsType<CouponTemplate> = [
    { title: "编码", dataIndex: "code", width: 140, render: (v) => v || "—" },
    { title: "名称", dataIndex: "name", width: 180, render: (v) => v || "—" },
    {
      title: "类型",
      dataIndex: "ticket_type",
      width: 100,
      render: (v: string | null) =>
        v ? <Tag color="blue">{TICKET_TYPE_LABEL[v] ?? v}</Tag> : "—",
    },
    {
      title: "折扣方式",
      dataIndex: "discount_type",
      width: 110,
      render: (v: string | null) => (v ? DISCOUNT_TYPE_LABEL[v] ?? v : "—"),
    },
    {
      title: "折扣值",
      dataIndex: "discount_value",
      width: 120,
      render: (v: number | null, r: CouponTemplate) => renderDiscount(r.discount_type, v),
    },
    {
      title: "有效期",
      key: "valid",
      width: 190,
      render: (_: unknown, r: CouponTemplate) =>
        `${r.valid_from || "—"} ~ ${r.valid_to || "—"}`,
    },
    {
      title: "总量",
      dataIndex: "total_quantity",
      width: 90,
      render: (v: number | null) => (v == null ? "—" : v),
    },
    {
      title: "已发",
      dataIndex: "issued_quantity",
      width: 90,
      render: (v: number | null) => (v == null ? 0 : v),
    },
    {
      title: "启用",
      dataIndex: "is_valid",
      width: 90,
      render: (v: boolean | undefined) =>
        v === false ? <Tag color="default">停用</Tag> : <Tag color="green">启用</Tag>,
    },
  ];

  const cpColumns: ColumnsType<Coupon> = [
    { title: "券号", dataIndex: "coupon_no", width: 170, render: (v) => v || "—" },
    {
      title: "模板",
      dataIndex: "template_id",
      width: 160,
      render: (v: number | string | null) => {
        if (v == null) return <Tag>散券</Tag>;
        const t = tplMap.get(String(v));
        return t ? `${t.name || ""}（${t.code || ""}）` : `模板 #${v}`;
      },
    },
    {
      title: "类型",
      dataIndex: "ticket_type",
      width: 100,
      render: (v: string | null) =>
        v ? <Tag color="blue">{TICKET_TYPE_LABEL[v] ?? v}</Tag> : "—",
    },
    {
      title: "折扣",
      key: "discount",
      width: 160,
      render: (_: unknown, r: Coupon) => (
        <Space size={4}>
          <span>{renderDiscount(r.discount_type, r.discount_value)}</span>
          {r.discount_type && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {DISCOUNT_TYPE_LABEL[r.discount_type] ?? r.discount_type}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: "有效期",
      key: "valid",
      width: 190,
      render: (_: unknown, r: Coupon) => `${r.valid_from || "—"} ~ ${r.valid_to || "—"}`,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (v: string | null) => {
        const meta = STATUS_META[v ?? ""] ?? { label: v ?? "—", color: "default" };
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "核销订单",
      dataIndex: "booking_id",
      width: 110,
      render: (v: number | string | null) => (v == null ? "—" : String(v)),
    },
    {
      title: "核销时间",
      dataIndex: "used_at",
      width: 170,
      render: (v: string | null) => (v ? new Date(v).toLocaleString() : "—"),
    },
    {
      title: "操作",
      key: "op",
      width: 90,
      fixed: "right",
      render: (_: unknown, r: Coupon) => {
        const disabled = !canManage || r.status !== "ISSUED";
        return (
          <Popconfirm
            title="确认作废该优惠券？"
            description="作废后不可恢复"
            onConfirm={() => doVoid(r)}
            disabled={disabled}
          >
            <Button size="small" danger disabled={disabled}>
              作废
            </Button>
          </Popconfirm>
        );
      },
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: 16,
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <Typography.Title level={4} style={{ margin: 0, marginBottom: 4 }}>
            优惠券管理
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            券模板 / 发券 / 核销 / 作废（COUPON_MANAGE）
          </Typography.Text>
        </div>
      </div>

      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: "templates",
            label: "券模板",
            children: (
              <Card
                size="small"
                title="券模板"
                extra={
                  <Space>
                    <Button onClick={() => void fetchTemplates()} loading={tplLoading}>
                      刷新
                    </Button>
                    <Button type="primary" disabled={!canManage} onClick={openTplCreate}>
                      新建模板
                    </Button>
                  </Space>
                }
              >
                <Table<CouponTemplate>
                  rowKey="id"
                  loading={tplLoading}
                  size="small"
                  dataSource={templates}
                  columns={tplColumns}
                  scroll={{ x: 1180 }}
                  pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 个模板` }}
                  locale={{ emptyText: <Empty description="暂无券模板" /> }}
                />
              </Card>
            ),
          },
          {
            key: "instances",
            label: "券实例",
            children: (
              <>
                {/* 核销区 */}
                <Card size="small" title="优惠券核销" style={{ marginBottom: 12 }}>
                  <Form form={useForm} layout="inline" onFinish={submitUse}>
                    <Form.Item
                      name="coupon_no"
                      label="券号"
                      rules={[{ required: true, message: "请输入券号" }]}
                    >
                      <Input
                        placeholder="扫描 / 输入券号"
                        allowClear
                        style={{ width: 240 }}
                      />
                    </Form.Item>
                    <Form.Item name="booking_id" label="订单 ID">
                      <InputNumber style={{ width: 140 }} min={0} />
                    </Form.Item>
                    <Form.Item name="bill_id" label="账单 ID">
                      <InputNumber style={{ width: 140 }} min={0} />
                    </Form.Item>
                    <Form.Item>
                      <Button
                        type="primary"
                        htmlType="submit"
                        loading={using}
                        disabled={!canManage}
                      >
                        核销
                      </Button>
                    </Form.Item>
                  </Form>
                </Card>

                <Card
                  size="small"
                  title="券实例"
                  extra={
                    <Space>
                      <Button onClick={() => void fetchCoupons()} loading={cpLoading}>
                        刷新
                      </Button>
                      <Button type="primary" disabled={!canManage} onClick={openIssue}>
                        发券
                      </Button>
                    </Space>
                  }
                >
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 12,
                      marginBottom: 12,
                      alignItems: "center",
                    }}
                  >
                    <Select
                      style={{ width: 140 }}
                      value={cpStatus}
                      options={STATUS_FILTER_OPTIONS}
                      onChange={setCpStatus}
                    />
                    <Input
                      style={{ width: 170 }}
                      placeholder="订单号"
                      allowClear
                      value={cpBookingId}
                      onChange={(e) => setCpBookingId(e.target.value)}
                    />
                    <Input
                      style={{ width: 190 }}
                      placeholder="券号"
                      allowClear
                      value={cpNo}
                      onChange={(e) => setCpNo(e.target.value)}
                    />
                    <Button onClick={() => void fetchCoupons()}>查询</Button>
                  </div>
                  <Table<Coupon>
                    rowKey="id"
                    loading={cpLoading}
                    size="small"
                    dataSource={coupons}
                    columns={cpColumns}
                    scroll={{ x: 1300 }}
                    pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 张券` }}
                    locale={{ emptyText: <Empty description="暂无优惠券" /> }}
                  />
                </Card>
              </>
            ),
          },
        ]}
      />

      {/* 新建券模板 */}
      <Modal
        title="新建券模板"
        open={tplOpen}
        onOk={submitTpl}
        onCancel={() => setTplOpen(false)}
        okText="创建"
        cancelText="取消"
        confirmLoading={tplSaving}
        width={560}
        destroyOnClose
      >
        <Form form={tplForm} layout="vertical" preserve={false}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
            <Form.Item
              name="code"
              label="模板编码"
              rules={[{ required: true, message: "请输入模板编码" }]}
            >
              <Input maxLength={32} placeholder="如 BREAKFAST10" />
            </Form.Item>
            <Form.Item
              name="name"
              label="模板名称"
              rules={[{ required: true, message: "请输入模板名称" }]}
            >
              <Input maxLength={64} placeholder="如 早餐 10 元券" />
            </Form.Item>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
            <Form.Item name="ticket_type" label="券类型">
              <Select options={TICKET_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item name="discount_type" label="折扣方式">
              <Select options={DISCOUNT_TYPE_OPTIONS} />
            </Form.Item>
          </div>
          <Form.Item name="discount_value" label="折扣值（分 / 百分比）">
            <InputNumber min={0} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            name="range"
            label="有效期"
            rules={[{ required: true, message: "请选择有效期" }]}
          >
            <RangePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="total_quantity" label="发行总量">
            <InputNumber min={0} precision={0} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 发券 */}
      <Modal
        title="发放优惠券"
        open={issueOpen}
        onOk={submitIssue}
        onCancel={() => setIssueOpen(false)}
        okText="确认发券"
        cancelText="取消"
        confirmLoading={issuing}
        width={560}
        destroyOnClose
      >
        <Form form={issueForm} layout="vertical" preserve={false}>
          <Form.Item
            name="template_id"
            label="券模板（不选则为散券，需手填规则与有效期）"
          >
            <Select
              allowClear
              placeholder="选择模板"
              options={templates.map((t) => ({
                value: t.id as number | string,
                label: `${t.name || ""}（${t.code || ""}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="count"
            label="发放张数"
            rules={[{ required: true, message: "请输入发放张数" }]}
          >
            <InputNumber min={1} max={1000} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          {watchTemplateId == null || watchTemplateId === "" ? (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
                <Form.Item name="ticket_type" label="券类型">
                  <Select options={TICKET_TYPE_OPTIONS} />
                </Form.Item>
                <Form.Item name="discount_type" label="折扣方式">
                  <Select options={DISCOUNT_TYPE_OPTIONS} />
                </Form.Item>
              </div>
              <Form.Item name="discount_value" label="折扣值（分 / 百分比）">
                <InputNumber min={0} precision={0} style={{ width: "100%" }} />
              </Form.Item>
            </>
          ) : null}
          <Form.Item
            name="range"
            label="有效期（选模板时可留空，沿用模板规则）"
            rules={
              watchTemplateId == null || watchTemplateId === ""
                ? [{ required: true, message: "散券请填写有效期" }]
                : []
            }
          >
            <RangePicker style={{ width: "100%" }} />
          </Form.Item>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
            <Form.Item
              name="is_cover_other_discount"
              label="可叠加其他折扣"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
            <Form.Item
              name="is_transfer_to_account"
              label="可转挂账"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </div>
        </Form>
      </Modal>
    </div>
  );
}
