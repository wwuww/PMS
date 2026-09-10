import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Button,
  Card,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, PlusOutlined, EyeOutlined, FileDoneOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { useTenant } from "../store/tenant";
import {
  listBills,
  getBill,
  openBill,
  addCharge,
  takePayment,
  settleBill,
  refundBill,
  applyPrepay,
  createInvoice,
  listInvoicesByBill,
} from "../api/endpoints";
import type {
  Bill,
  BillSource,
  ChargeType,
  Invoice,
  PaymentMethod,
} from "../api/types";
import { currentOperator, useCan } from "../utils/permission";

// 后端阈值：开票额 - 消费额 > 1000 分（即 ¥10）时 approver 必填
const INVOICE_APPROVER_THRESHOLD = 1000;

const INVOICE_TYPE_OPTIONS = [
  { value: "NORMAL", label: "普票" },
  { value: "VAT_SPECIAL", label: "专票" },
  { value: "ELECTRONIC", label: "电子票" },
];

const { Title, Text } = Typography;

const fmtCents = (c: number) =>
  `¥${(c / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const CHARGE_LABELS: Record<ChargeType, string> = {
  ROOM_CHARGE: "房费",
  MISC: "杂费",
  DISCOUNT: "折扣",
  REFUND: "退款",
};

const METHOD_LABELS: Record<PaymentMethod, string> = {
  CASH: "现金",
  PREAUTH: "预授权",
  WECHAT: "微信",
  ALIPAY: "支付宝",
  UNIONPAY: "银联",
  STORE_VALUE: "储值",
};

const SOURCE_LABELS: Record<BillSource, string> = {
  BOOKING: "预订账",
  WALK_IN: "散客账",
};

function sourceTag(source: BillSource | null) {
  if (!source) return <Tag>未知</Tag>;
  const color = source === "BOOKING" ? "blue" : "gold";
  return <Tag color={color}>{SOURCE_LABELS[source]}</Tag>;
}

function statusTag(status: string) {
  const settled = status === "SETTLED" || status === "settled";
  return (
    <Tag color={settled ? "green" : "processing"}>
      {settled ? "已结" : "未结"}
    </Tag>
  );
}

const amountValidator = (_: unknown, value: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return Promise.reject(new Error("请输入金额"));
  }
  if (value <= 0) return Promise.reject(new Error("金额需大于 0"));
  return Promise.resolve();
};

export default function Billing() {
  const { tenantCode, hotelId } = useTenant();
  const [searchParams] = useSearchParams();
  const [bills, setBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<string>("ALL");

  const canManageInvoice = useCan("INVOICE_MANAGE");

  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Bill | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [showOpen, setShowOpen] = useState(false);
  const [openForm] = Form.useForm();

  const [showRefund, setShowRefund] = useState(false);
  const [refundForm] = Form.useForm();
  const [refundBusy, setRefundBusy] = useState(false);

  // 批次③：开票弹窗 + 按账单查发票记录
  const [invoiceOpen, setInvoiceOpen] = useState(false);
  const [invoiceForm] = Form.useForm();
  const [invoiceBusy, setInvoiceBusy] = useState(false);
  const [existingInvoices, setExistingInvoices] = useState<Invoice[]>([]);
  const [existingInvoicesLoading, setExistingInvoicesLoading] = useState(false);
  // 监听开票金额 → 计算是否需要审批人
  const watchConsume = Form.useWatch("consume_amount_cents", invoiceForm);
  const watchInvoice = Form.useWatch("invoice_amount_cents", invoiceForm);
  const watchType = Form.useWatch("invoice_type", invoiceForm);
  const requireApprover = useMemo(() => {
    const c = Number(watchConsume || 0);
    const i = Number(watchInvoice || 0);
    return i - c > INVOICE_APPROVER_THRESHOLD;
  }, [watchConsume, watchInvoice]);

  const refresh = useCallback(async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const list = await listBills(
        tenantCode,
        sourceFilter === "ALL" ? undefined : sourceFilter
      );
      setBills(list);
    } catch (e) {
      message.error("账单列表加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode, sourceFilter]);

  const loadDetail = useCallback(
    async (id: string) => {
      if (!tenantCode) return;
      setDetailLoading(true);
      try {
        const b = await getBill(tenantCode, id);
        setDetail(b);
      } catch {
        message.error("账单详情加载失败");
      } finally {
        setDetailLoading(false);
      }
    },
    [tenantCode]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 深链：从房态图双击「查看账单」跳入时，自动定位并打开对应预订/房间的账单
  const deepBooking = searchParams.get("booking");
  const deepRoom = searchParams.get("room");
  useEffect(() => {
    if ((!deepBooking && !deepRoom) || !bills.length) return;
    const m =
      (deepBooking ? bills.find((b) => b.booking_id === deepBooking) : null) ||
      (deepRoom ? bills.find((b) => b.room_no === deepRoom) : null);
    if (m) {
      setOpenId(m.id);
      loadDetail(m.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bills, deepBooking, deepRoom]);

  const handleOpen = async () => {
    if (!hotelId) {
      message.warning("请先在顶部选择门店");
      return;
    }
    const v = await openForm.validateFields();
    try {
      const created = await openBill(tenantCode, {
        hotel_id: hotelId,
        guest_name: v.guest_name,
        room_no: v.room_no || null,
        booking_id: v.booking_id || null,
        source: v.source || null,
      });
      message.success(`已开账 ${created.bill_no}`);
      setShowOpen(false);
      openForm.resetFields();
      await refresh();
      setOpenId(created.id);
      await loadDetail(created.id);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "开账失败");
    }
  };

  const handleCharge = async (vals: {
    charge_type: ChargeType;
    amount: number;
    description?: string;
  }) => {
    if (!openId || !detail) return;
    try {
      const updated = await addCharge(tenantCode, openId, {
        charge_type: vals.charge_type,
        amount: Math.round(vals.amount * 100),
        description: vals.description || "",
      });
      setDetail(updated);
      message.success("已记账");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "记账失败");
    }
  };

  const handlePayment = async (vals: {
    method: PaymentMethod;
    amount: number;
    is_deposit?: boolean;
    ref_no?: string;
  }) => {
    if (!openId || !detail) return;
    try {
      const updated = await takePayment(tenantCode, openId, {
        method: vals.method,
        amount: Math.round(vals.amount * 100),
        is_deposit: vals.is_deposit || false,
        ref_no: vals.ref_no || null,
      });
      setDetail(updated);
      message.success("已收款");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "收款失败");
    }
  };

  const handleSettle = async () => {
    if (!openId || !detail) return;
    try {
      const updated = await settleBill(tenantCode, openId);
      setDetail(updated);
      message.success("账单已结清");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "结账失败（余额需为 0）");
    }
  };

  const handleRefund = async () => {
    if (!openId || !detail) return;
    const v = await refundForm.validateFields();
    setRefundBusy(true);
    try {
      const updated = await refundBill(tenantCode, openId, {
        method: (v.method as PaymentMethod) || "CASH",
        amount: Math.round(v.amount * 100),
      });
      setDetail(updated);
      message.success("已退款");
      setShowRefund(false);
      refundForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "退款失败");
    } finally {
      setRefundBusy(false);
    }
  };

  const handlePrepay = async () => {
    if (!openId || !detail) return;
    try {
      const updated = await applyPrepay(tenantCode, openId);
      setDetail(updated);
      message.success("预付已落账");
      await refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "预付落账失败");
    }
  };

  // 批次③：开票 → 弹窗预填当前账单总额
  const openInvoiceForBill = async () => {
    if (!openId || !detail) return;
    // 消费额 = 当前账单所有 OPEN 条目金额合计（按现有约定；不含已红冲/Void）
    const consume = detail.items
      .filter((i) => i.amount > 0)
      .reduce((s, i) => s + i.amount, 0);
    invoiceForm.resetFields();
    invoiceForm.setFieldsValue({
      bill_id: detail.id,
      booking_id: detail.booking_id ?? undefined,
      room_no: detail.room_no ?? "",
      guest_name: detail.guest_name ?? "",
      check_out_at: dayjs(),
      consume_amount_cents: consume,
      invoice_amount_cents: consume,
      invoice_type: "NORMAL",
      title: "",
      tax_no: "",
      approver: "",
      operator: currentOperator(),
      memo: "",
    });
    setInvoiceOpen(true);
    // 异步拉该账单已有发票
    setExistingInvoicesLoading(true);
    try {
      const list = await listInvoicesByBill(tenantCode, detail.id);
      setExistingInvoices(list);
    } catch {
      setExistingInvoices([]);
    } finally {
      setExistingInvoicesLoading(false);
    }
  };

  const submitInvoice = async () => {
    if (!detail) return;
    const v = await invoiceForm.validateFields();
    if (watchType === "VAT_SPECIAL" && !v.tax_no?.trim()) {
      message.error("增值税专用发票必填税号");
      return;
    }
    const consume = Number(v.consume_amount_cents || 0);
    const invoice = Number(v.invoice_amount_cents || 0);
    if (invoice - consume > INVOICE_APPROVER_THRESHOLD && !v.approver?.trim()) {
      message.error(`开票额超过消费额 ${INVOICE_APPROVER_THRESHOLD / 100} 元，需填写审批人`);
      return;
    }
    setInvoiceBusy(true);
    try {
      await createInvoice(tenantCode, {
        invoice_no: v.invoice_no?.trim() || null,
        bill_id: v.bill_id ?? null,
        booking_id: v.booking_id ?? null,
        room_no: v.room_no?.trim() || null,
        guest_name: v.guest_name?.trim() || null,
        agreement_no: v.agreement_no?.trim() || null,
        check_in_at: v.check_in_at ? dayjs(v.check_in_at).format("YYYY-MM-DD HH:mm:ss") : null,
        check_out_at: v.check_out_at
          ? dayjs(v.check_out_at).format("YYYY-MM-DD HH:mm:ss")
          : dayjs().format("YYYY-MM-DD HH:mm:ss"),
        check_in_type: v.check_in_type?.trim() || null,
        consume_amount_cents: consume,
        invoice_amount_cents: invoice,
        invoice_type: v.invoice_type || "NORMAL",
        title: v.title?.trim() || null,
        tax_no: v.tax_no?.trim() || null,
        approver: v.approver?.trim() || null,
        work_shift: v.work_shift?.trim() || null,
        memo: v.memo?.trim() || null,
        operator: currentOperator(),
      });
      message.success("开票成功");
      // 刷新该账单的发票列表
      try {
        const list = await listInvoicesByBill(tenantCode, detail.id);
        setExistingInvoices(list);
      } catch {
        /* 静默 */
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || (e as Error).message || "开票失败");
    } finally {
      setInvoiceBusy(false);
    }
  };

  const columns: ColumnsType<Bill> = useMemo(
    () => [
      { title: "账单号", dataIndex: "bill_no", key: "bill_no" },
      { title: "客人", dataIndex: "guest_name", key: "guest_name" },
      {
        title: "房号",
        dataIndex: "room_no",
        key: "room_no",
        render: (v: string | null) => v || <Text type="secondary">—</Text>,
      },
      {
        title: "来源",
        dataIndex: "source",
        key: "source",
        render: (v: BillSource | null) => sourceTag(v),
      },
      {
        title: "状态",
        dataIndex: "status",
        key: "status",
        render: (v: string) => statusTag(v),
      },
      {
        title: "余额",
        dataIndex: "balance",
        key: "balance",
        align: "right",
        render: (v: number) => (
          <Text type={v > 0 ? "danger" : v < 0 ? "success" : undefined}>
            {fmtCents(v)}
          </Text>
        ),
      },
      {
        title: "操作",
        key: "action",
        render: (_: unknown, row: Bill) => (
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => {
              setOpenId(row.id);
              loadDetail(row.id);
            }}
          >
            查看
          </Button>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const itemColumns: ColumnsType<Bill["items"][number]> = [
    { title: "类型", dataIndex: "type", render: (t: ChargeType) => CHARGE_LABELS[t] },
    {
      title: "金额",
      dataIndex: "amount",
      align: "right",
      render: (v: number) => (
        <Text type={v < 0 ? "success" : undefined}>{fmtCents(v)}</Text>
      ),
    },
    { title: "说明", dataIndex: "description", render: (v: string) => v || "—" },
  ];

  const payColumns: ColumnsType<Bill["payments"][number]> = [
    { title: "方式", dataIndex: "method", render: (m: PaymentMethod) => METHOD_LABELS[m] },
    {
      title: "金额",
      dataIndex: "amount",
      align: "right",
      render: (v: number) => fmtCents(v),
    },
    {
      title: "押金",
      dataIndex: "is_deposit",
      render: (b: boolean) => (b ? <Tag color="purple">押金</Tag> : "—"),
    },
  ];

  const adjColumns: ColumnsType<Bill["adjustments"][number]> = [
    {
      title: "类型",
      dataIndex: "type",
      render: (t: string) => (
        <Tag color={t === "VOID" ? "red" : "orange"}>
          {t === "VOID" ? "红冲" : "调账"}
        </Tag>
      ),
    },
    {
      title: "金额",
      dataIndex: "amount_cents",
      align: "right",
      render: (v: number) => fmtCents(v),
    },
    { title: "原因", dataIndex: "reason", render: (v: string) => v || "—" },
  ];

  return (
    <div>
      <Card
        style={{ marginBottom: 16 }}
        styles={{ body: { display: "flex", alignItems: "center", justifyContent: "space-between" } }}
      >
        <Title level={4} style={{ margin: 0 }}>
          前台收银
        </Title>
        <Space>
          <Segmented
            value={sourceFilter}
            onChange={(v) => setSourceFilter(v as string)}
            options={[
              { label: "全部", value: "ALL" },
              { label: "预订账", value: "BOOKING" },
              { label: "散客账", value: "WALK_IN" },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setShowOpen(true)}
          >
            开账
          </Button>
        </Space>
      </Card>

      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={bills}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Drawer
        width={560}
        open={openId !== null}
        onClose={() => {
          setOpenId(null);
          setDetail(null);
        }}
        title={detail ? `账单 ${detail.bill_no}` : "账单详情"}
        loading={detailLoading}
      >
        {detail && (
          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="客人">
                {detail.guest_name}
              </Descriptions.Item>
              <Descriptions.Item label="房号">
                {detail.room_no || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                {sourceTag(detail.source)}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {statusTag(detail.status)}
              </Descriptions.Item>
              <Descriptions.Item label="应收合计">
                {fmtCents(
                  detail.items.reduce((s, i) => s + i.amount, 0)
                )}
              </Descriptions.Item>
              <Descriptions.Item label="已收合计">
                {fmtCents(
                  detail.payments.reduce((s, p) => s + p.amount, 0)
                )}
              </Descriptions.Item>
              <Descriptions.Item label="当前余额" span={2}>
                <Text
                  strong
                  type={detail.balance > 0 ? "danger" : detail.balance < 0 ? "success" : undefined}
                >
                  {fmtCents(detail.balance)}
                </Text>
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title="记账（应收 / 冲减）">
              <Form
                layout="inline"
                onFinish={handleCharge}
                initialValues={{ charge_type: "MISC" }}
              >
                <Form.Item
                  name="charge_type"
                  rules={[{ required: true }]}
                >
                  <Select
                    style={{ width: 100 }}
                    options={(
                      Object.keys(CHARGE_LABELS) as ChargeType[]
                    ).map((k) => ({
                      value: k,
                      label: CHARGE_LABELS[k],
                    }))}
                  />
                </Form.Item>
                <Form.Item
                  name="amount"
                  rules={[{ validator: amountValidator }]}
                >
                  <InputNumber
                    addonBefore="¥"
                    min={0}
                    step={10}
                    placeholder="金额"
                    style={{ width: 130 }}
                  />
                </Form.Item>
                <Form.Item name="description">
                  <Input placeholder="说明" style={{ width: 120 }} />
                </Form.Item>
                <Form.Item>
                  <Button type="primary" htmlType="submit">
                    记账
                  </Button>
                </Form.Item>
              </Form>
            </Card>

            <Card size="small" title="收款">
              <Form
                layout="inline"
                onFinish={handlePayment}
                initialValues={{ method: "CASH", is_deposit: false }}
              >
                <Form.Item name="method" rules={[{ required: true }]}>
                  <Select
                    style={{ width: 110 }}
                    options={(
                      Object.keys(METHOD_LABELS) as PaymentMethod[]
                    ).map((k) => ({
                      value: k,
                      label: METHOD_LABELS[k],
                    }))}
                  />
                </Form.Item>
                <Form.Item
                  name="amount"
                  rules={[{ validator: amountValidator }]}
                >
                  <InputNumber
                    addonBefore="¥"
                    min={0}
                    step={10}
                    placeholder="金额"
                    style={{ width: 130 }}
                  />
                </Form.Item>
                <Form.Item name="is_deposit" valuePropName="checked">
                  <Switch checkedChildren="押金" unCheckedChildren="否" />
                </Form.Item>
                <Form.Item name="ref_no">
                  <Input placeholder="凭证号" style={{ width: 110 }} />
                </Form.Item>
                <Form.Item>
                  <Button type="primary" htmlType="submit">
                    收款
                  </Button>
                </Form.Item>
              </Form>
            </Card>

            <Card size="small" title="明细">
              <Title level={5} style={{ marginTop: 0 }}>
                应收明细
              </Title>
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                columns={itemColumns}
                dataSource={detail.items}
              />
              <Title level={5}>收款明细</Title>
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                columns={payColumns}
                dataSource={detail.payments}
              />
              {detail.adjustments.length > 0 && (
                <>
                  <Title level={5}>调整明细</Title>
                  <Table
                    rowKey="id"
                    size="small"
                    pagination={false}
                    columns={adjColumns}
                    dataSource={detail.adjustments}
                  />
                </>
              )}
            </Card>

            {/* 批次③：当前账单已开发票 */}
            <Card
              size="small"
              title={
                <Space>
                  发票记录
                  <Button
                    size="small"
                    type="link"
                    loading={existingInvoicesLoading}
                    onClick={async () => {
                      if (!detail) return;
                      setExistingInvoicesLoading(true);
                      try {
                        const list = await listInvoicesByBill(tenantCode, detail.id);
                        setExistingInvoices(list);
                      } catch {
                        /* noop */
                      } finally {
                        setExistingInvoicesLoading(false);
                      }
                    }}
                  >
                    刷新
                  </Button>
                </Space>
              }
            >
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                loading={existingInvoicesLoading}
                dataSource={existingInvoices}
                locale={{ emptyText: "该账单暂未开票" }}
                columns={[
                  { title: "发票号", dataIndex: "invoice_no", width: 150 },
                  {
                    title: "开票额",
                    dataIndex: "invoice_amount_cents",
                    width: 110,
                    render: (v: number) => fmtCents(v),
                  },
                  {
                    title: "消费额",
                    dataIndex: "consume_amount_cents",
                    width: 110,
                    render: (v: number) => fmtCents(v),
                  },
                  {
                    title: "类型",
                    dataIndex: "invoice_type",
                    width: 90,
                    render: (v: string) => <Tag>{v || "—"}</Tag>,
                  },
                  {
                    title: "状态",
                    dataIndex: "status",
                    width: 100,
                    render: (v: string) =>
                      v === "VOID" ? <Tag color="red">已作废</Tag> : <Tag color="green">已开</Tag>,
                  },
                  { title: "开票人", dataIndex: "operator", width: 110 },
                  {
                    title: "开票时间",
                    dataIndex: "created_at",
                    render: (v: string) => (v ? new Date(v).toLocaleString() : "—"),
                  },
                ]}
              />
            </Card>

            <Space>
              <Popconfirm
                title="确认结账？"
                description="结账要求余额归零"
                disabled={detail.balance !== 0}
                onConfirm={handleSettle}
              >
                <Button
                  type="primary"
                  disabled={detail.balance !== 0}
                >
                  结账
                </Button>
              </Popconfirm>
              <Button
                danger
                disabled={detail.balance >= 0}
                onClick={() => setShowRefund(true)}
              >
                退款
              </Button>
              <Button onClick={handlePrepay}>预付落账</Button>
              <Button
                icon={<FileDoneOutlined />}
                disabled={!canManageInvoice}
                onClick={openInvoiceForBill}
              >
                开票
              </Button>
            </Space>
            {detail.balance !== 0 && (
              <Text type="secondary">
                余额不为 0，{detail.balance > 0 ? "请先收款" : "可发起退款"}。
              </Text>
            )}
          </Space>
        )}
      </Drawer>

      <Modal
        title="开新账单"
        open={showOpen}
        onOk={handleOpen}
        onCancel={() => {
          setShowOpen(false);
          openForm.resetFields();
        }}
        okText="开账"
        cancelText="取消"
      >
        <Form form={openForm} layout="vertical" initialValues={{ source: "WALK_IN" }}>
          <Form.Item
            name="guest_name"
            label="客人姓名"
            rules={[{ required: true, message: "请输入客人姓名" }]}
          >
            <Input placeholder="如：张三" maxLength={64} />
          </Form.Item>
          <Form.Item name="room_no" label="房号（可选）">
            <Input placeholder="如：401" />
          </Form.Item>
          <Form.Item name="source" label="账单来源">
            <Select
              options={[
                { value: "BOOKING", label: "预订账" },
                { value: "WALK_IN", label: "散客账" },
              ]}
            />
          </Form.Item>
          <Form.Item name="booking_id" label="关联预订 ID（可选）">
            <InputNumber style={{ width: "100%" }} min={1} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="退款"
        open={showRefund}
        onOk={handleRefund}
        confirmLoading={refundBusy}
        onCancel={() => {
          setShowRefund(false);
          refundForm.resetFields();
        }}
        okText="确认退款"
        cancelText="取消"
      >
        <Form form={refundForm} layout="vertical" initialValues={{ method: "CASH" }}>
          <Form.Item
            name="amount"
            label="退款金额（元）"
            rules={[{ validator: amountValidator }]}
          >
            <InputNumber addonBefore="¥" min={0} step={10} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="method" label="退款方式">
            <Select
              options={[
                { value: "CASH", label: "现金" },
                { value: "WECHAT", label: "微信" },
                { value: "ALIPAY", label: "支付宝" },
                { value: "UNIONPAY", label: "银联" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 批次③：开票 Modal（前台收银 → 当前账单 → 开票） */}
      <Modal
        title={`开票 · 账单 ${detail?.bill_no ?? ""}`}
        open={invoiceOpen}
        onOk={submitInvoice}
        onCancel={() => setInvoiceOpen(false)}
        okText="确认开票"
        cancelText="取消"
        confirmLoading={invoiceBusy}
        width={620}
        destroyOnClose
      >
        <Form form={invoiceForm} layout="vertical" preserve={false}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
            <Form.Item name="bill_id" label="账单 ID">
              <InputNumber style={{ width: "100%" }} disabled />
            </Form.Item>
            <Form.Item name="booking_id" label="预订 ID">
              <InputNumber style={{ width: "100%" }} disabled />
            </Form.Item>
            <Form.Item name="room_no" label="房号">
              <Input maxLength={16} />
            </Form.Item>
            <Form.Item name="guest_name" label="客人姓名">
              <Input maxLength={128} />
            </Form.Item>
            <Form.Item
              name="check_out_at"
              label="退房时间"
              rules={[{ required: true, message: "请选择退房时间" }]}
            >
              <DatePicker
                showTime
                format="YYYY-MM-DD HH:mm:ss"
                style={{ width: "100%" }}
              />
            </Form.Item>
            <Form.Item name="check_in_type" label="入住类型">
              <Input maxLength={16} placeholder="如 全日租/钟点房" />
            </Form.Item>
          </div>
          <Form.Item
            name="consume_amount_cents"
            label="消费额（分）"
            rules={[{ required: true, message: "请输入消费额" }]}
          >
            <InputNumber min={0} step={1} style={{ width: "100%" }} addonBefore="分" />
          </Form.Item>
          <Form.Item
            name="invoice_amount_cents"
            label="开票额（分）"
            rules={[{ required: true, message: "请输入开票额" }]}
          >
            <InputNumber min={0} step={1} style={{ width: "100%" }} addonBefore="分" />
          </Form.Item>
          {requireApprover && (
            <Typography.Text type="warning" style={{ display: "block", marginBottom: 8 }}>
              开票额超过消费额 {INVOICE_APPROVER_THRESHOLD / 100} 元，需填写审批人
            </Typography.Text>
          )}
          <Form.Item
            name="invoice_type"
            label="发票类型"
            rules={[{ required: true, message: "请选择发票类型" }]}
          >
            <Radio.Group options={INVOICE_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="title" label="抬头">
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item
            name="tax_no"
            label="税号"
            rules={
              watchType === "VAT_SPECIAL"
                ? [{ required: true, message: "专票必填税号" }]
                : []
            }
          >
            <Input
              maxLength={64}
              placeholder={watchType === "VAT_SPECIAL" ? "必填" : "选填"}
            />
          </Form.Item>
          <Form.Item
            name="approver"
            label="审批人"
            rules={requireApprover ? [{ required: true, message: "开票额超额，必填审批人" }] : []}
          >
            <Input
              maxLength={64}
              placeholder={requireApprover ? "必填（审计追溯）" : "选填"}
            />
          </Form.Item>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
            <Form.Item name="work_shift" label="班次">
              <Input maxLength={50} placeholder="如 早班/中班/晚班" />
            </Form.Item>
            <Form.Item name="invoice_no" label="发票号（可选，不填自动生成）">
              <Input maxLength={32} />
            </Form.Item>
          </div>
          <Form.Item name="memo" label="备注">
            <Input.TextArea rows={2} maxLength={255} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
