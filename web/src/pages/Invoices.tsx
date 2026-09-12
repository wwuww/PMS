// 批次③ - 发票管理主页面
// 列表（筛选 + 分页）+ 开票 Modal（消费/开票额校验 + 专票税号 + 大额审批人）+ 作废 Popconfirm
// 门控：useCan(PERM.INVOICE_MANAGE)，映射为后端权限码 invoice.manage（路由级） + 表单层校验
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { Dayjs } from "dayjs";
import {
  createInvoice,
  listInvoices,
  voidInvoice,
} from "../api/endpoints";
import type { Invoice } from "../api/types";
import { useTenant } from "../store/tenant";
import { CellAmount } from "../utils/format.tsx";
import { PERM, currentOperator, useCan } from "../utils/permission";

// 后端阈值：开票额 - 消费额 > 1000 分（即 ¥10）时 approver 必填
const APPROVER_THRESHOLD_CENTS = 1000;

const INVOICE_TYPE_OPTIONS = [
  { value: "NORMAL", label: "普票" },
  { value: "VAT_SPECIAL", label: "专票" },
  { value: "ELECTRONIC", label: "电子票" },
];

const INVOICE_TYPE_LABEL: Record<string, string> = {
  NORMAL: "普票",
  VAT_SPECIAL: "专票",
  ELECTRONIC: "电子票",
};

const STATUS_FILTER_OPTIONS = [
  { value: "ALL", label: "全部状态" },
  { value: "ISSUED", label: "已开" },
  { value: "VOID", label: "已作废" },
];

interface Filters {
  status: string;
  bill_id?: number | string;
  booking_id?: number | string;
  range: [Dayjs | null, Dayjs | null] | null;
  limit: number;
}

export default function Invoices() {
  const { tenantCode } = useTenant();
  const canManage = useCan(PERM.INVOICE_MANAGE);

  const [filters, setFilters] = useState<Filters>({
    status: "ALL",
    range: null,
    limit: 100,
  });
  const [data, setData] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);

  const fetchList = useCallback(async () => {
    if (!canManage) {
      setData([]);
      return;
    }
    setLoading(true);
    try {
      const list = await listInvoices(tenantCode, {
        bill_id: filters.bill_id,
        booking_id: filters.booking_id,
        status: filters.status === "ALL" ? undefined : filters.status,
        limit: filters.limit,
      });
      setData(list);
    } catch (e: unknown) {
      message.error((e as Error).message || "加载发票列表失败");
      setData([]);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, canManage, filters.status, filters.bill_id, filters.booking_id, filters.limit]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const refresh = () => fetchList();

  // 监听开票金额变化 → 计算是否需要审批人
  const watchConsume = Form.useWatch("consume_amount_cents", createForm);
  const watchInvoice = Form.useWatch("invoice_amount_cents", createForm);
  const watchType = Form.useWatch("invoice_type", createForm);
  const requireApprover = useMemo(() => {
    const c = Number(watchConsume || 0);
    const i = Number(watchInvoice || 0);
    return i - c > APPROVER_THRESHOLD_CENTS;
  }, [watchConsume, watchInvoice]);

  const openCreate = () => {
    createForm.resetFields();
    // 设置默认值
    createForm.setFieldsValue({
      invoice_type: "NORMAL",
      check_out_at: dayjs(),
      consume_amount_cents: 0,
      invoice_amount_cents: 0,
      operator: currentOperator(),
    });
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    const v = await createForm.validateFields();
    if (watchType === "VAT_SPECIAL" && !v.tax_no?.trim()) {
      message.error("增值税专用发票必填税号");
      return;
    }
    if (requireApprover && !v.approver?.trim()) {
      message.error(`开票额超过消费额 ${APPROVER_THRESHOLD_CENTS / 100} 元，需填写审批人`);
      return;
    }
    const consume = Number(v.consume_amount_cents || 0);
    const invoice = Number(v.invoice_amount_cents || 0);
    if (consume < 0 || invoice < 0) {
      message.error("金额不能为负");
      return;
    }
    setCreating(true);
    try {
      await createInvoice(tenantCode, {
        invoice_no: v.invoice_no?.trim() || null,
        bill_id: v.bill_id ?? null,
        booking_id: v.booking_id ?? null,
        room_no: v.room_no?.trim() || null,
        guest_name: v.guest_name?.trim() || null,
        agreement_no: v.agreement_no?.trim() || null,
        check_in_at: v.check_in_at ? dayjs(v.check_in_at).format("YYYY-MM-DD HH:mm:ss") : null,
        check_out_at: v.check_out_at ? dayjs(v.check_out_at).format("YYYY-MM-DD HH:mm:ss") : (dayjs().format("YYYY-MM-DD HH:mm:ss")),
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
      setCreateOpen(false);
      createForm.resetFields();
      refresh();
    } catch (e: unknown) {
      message.error((e as Error).message || "开票失败");
    } finally {
      setCreating(false);
    }
  };

  const doVoid = async (row: Invoice) => {
    try {
      await voidInvoice(tenantCode, row.id as number, {
        reason: "前台作废",
        operator: currentOperator(),
      });
      message.success(`发票 ${row.invoice_no || row.id} 已作废`);
      refresh();
    } catch (e: unknown) {
      message.error((e as Error).message || "作废失败");
    }
  };

  const columns: ColumnsType<Invoice> = [
    { title: "发票号", dataIndex: "invoice_no", width: 160 },
    { title: "房号", dataIndex: "room_no", width: 90, render: (v) => v || "—" },
    { title: "客人", dataIndex: "guest_name", width: 120, render: (v) => v || "—" },
    {
      title: "消费额",
      dataIndex: "consume_amount_cents",
      width: 130,
      render: (v) => <CellAmount value={v} />,
    },
    {
      title: "开票额",
      dataIndex: "invoice_amount_cents",
      width: 130,
      render: (v) => <CellAmount value={v} />,
    },
    {
      title: "类型",
      dataIndex: "invoice_type",
      width: 90,
      render: (v) => <Tag color="blue">{INVOICE_TYPE_LABEL[v ?? ""] ?? v ?? "—"}</Tag>,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (v) =>
        v === "VOID" ? <Tag color="red">已作废</Tag> : <Tag color="green">已开</Tag>,
    },
    { title: "开票人", dataIndex: "operator", width: 110, render: (v) => v || "—" },
    {
      title: "开票时间",
      dataIndex: "created_at",
      width: 170,
      render: (v) => (v ? new Date(v).toLocaleString() : "—"),
    },
    {
      title: "操作",
      width: 100,
      fixed: "right",
      render: (_, r) => (
        <Popconfirm
          title="确认作废该发票？"
          description="一旦作废不可恢复（WORM）"
          onConfirm={() => doVoid(r)}
          disabled={!canManage || r.status === "VOID"}
        >
          <Button size="small" danger disabled={!canManage || r.status === "VOID"}>
            作废
          </Button>
        </Popconfirm>
      ),
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
            发票管理
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            开票 / 作废 / 查询（INVOICE_MANAGE）
          </Typography.Text>
        </div>
        <Space>
          <Button onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" disabled={!canManage} onClick={openCreate}>
            开票
          </Button>
        </Space>
      </div>

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
          value={filters.status}
          options={STATUS_FILTER_OPTIONS}
          onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
        />
        <Input
          style={{ width: 160 }}
          placeholder="账单号 (bill_id)"
          value={filters.bill_id ?? ""}
          onChange={(e) =>
            setFilters((f) => ({ ...f, bill_id: e.target.value.trim() || undefined }))
          }
        />
        <Input
          style={{ width: 160 }}
          placeholder="预订号 (booking_id)"
          value={filters.booking_id ?? ""}
          onChange={(e) =>
            setFilters((f) => ({ ...f, booking_id: e.target.value.trim() || undefined }))
          }
        />
        <DatePicker.RangePicker
          value={filters.range ?? undefined}
          onChange={(r) =>
            setFilters((f) => ({
              ...f,
              range: r && r[0] ? [r[0], r[1] ?? null] : null,
            }))
          }
        />
        <Select
          style={{ width: 120 }}
          value={filters.limit}
          options={[
            { value: 50, label: "50 条" },
            { value: 100, label: "100 条" },
            { value: 200, label: "200 条" },
          ]}
          onChange={(v) => setFilters((f) => ({ ...f, limit: v }))}
        />
      </div>

      <Table<Invoice>
        rowKey="id"
        loading={loading}
        size="small"
        dataSource={data}
        columns={columns}
        scroll={{ x: 1200 }}
        pagination={false}
        locale={{ emptyText: <Empty description="暂无发票记录" /> }}
      />

      <Modal
        title="开票"
        open={createOpen}
        onOk={submitCreate}
        onCancel={() => setCreateOpen(false)}
        okText="确认开票"
        cancelText="取消"
        confirmLoading={creating}
        width={620}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" preserve={false}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
            <Form.Item name="bill_id" label="账单 ID（可选）">
              <InputNumber style={{ width: "100%" }} min={0} />
            </Form.Item>
            <Form.Item name="booking_id" label="预订 ID（可选）">
              <InputNumber style={{ width: "100%" }} min={0} />
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
              开票额超过消费额 {APPROVER_THRESHOLD_CENTS / 100} 元，需填写审批人
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
            <Input maxLength={128} placeholder="个人 / 公司名称" />
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
            <Input maxLength={64} placeholder={watchType === "VAT_SPECIAL" ? "必填" : "选填"} />
          </Form.Item>

          <Form.Item
            name="approver"
            label="审批人"
            rules={requireApprover ? [{ required: true, message: "开票额超额，必填审批人" }] : []}
          >
            <Input maxLength={64} placeholder={requireApprover ? "必填（审计追溯）" : "选填"} />
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
