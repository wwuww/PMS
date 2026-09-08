import { useCallback, useEffect, useState } from "react";
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  App,
  Space,
  Drawer,
  Empty,
  Descriptions,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import {
  listArAccounts,
  createArAccount,
  listArBills,
  repayArAccount,
  chargeBillToAr,
  listBills,
} from "../api/endpoints";
import type { ArAccount, Bill } from "../api/types";
import { fmtCents } from "../utils/format";
import { useTenant } from "../store/tenant";

const REPAY_METHODS = [
  { value: "BANK", label: "银行转账" },
  { value: "CASH", label: "现金" },
  { value: "WECHAT", label: "微信" },
  { value: "ALIPAY", label: "支付宝" },
  { value: "UNIONPAY", label: "银联" },
];

export default function ArAccountsPage() {
  const { tenantCode, hotelId } = useTenant();
  const { message } = App.useApp();
  const [rows, setRows] = useState<ArAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [repayFor, setRepayFor] = useState<ArAccount | null>(null);
  const [chargeFor, setChargeFor] = useState<ArAccount | null>(null);
  const [billsFor, setBillsFor] = useState<ArAccount | null>(null);
  const [arBills, setArBills] = useState<Bill[]>([]);
  const [openBills, setOpenBills] = useState<Bill[]>([]);
  const [form] = Form.useForm();
  const [repayForm] = Form.useForm();

  const load = useCallback(async () => {
    if (!hotelId) return;
    setLoading(true);
    try {
      setRows(await listArAccounts(tenantCode, hotelId));
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId, message]);

  useEffect(() => {
    load();
  }, [load]);

  async function submitCreate() {
    const v = await form.validateFields();
    try {
      await createArAccount(tenantCode, {
        hotel_id: hotelId!,
        name: v.name,
        contact: v.contact || null,
        contact_phone: v.contact_phone || null,
        credit_limit_cents: v.credit_limit ? Math.round(v.credit_limit * 100) : 0,
        note: v.note || null,
      });
      message.success("协议单位已创建");
      setCreateOpen(false);
      form.resetFields();
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  async function submitRepay() {
    if (!repayFor) return;
    const v = await repayForm.validateFields();
    try {
      const after = await repayArAccount(tenantCode, repayFor.id, {
        amount: Math.round(v.amount * 100),
        method: v.method || "BANK",
        note: v.note || null,
      });
      message.success(
        `还款成功，${after.name} 当前欠款 ${fmtCents(after.balance_cents)}`
      );
      setRepayFor(null);
      repayForm.resetFields();
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  async function openBillsDrawer(a: ArAccount) {
    setBillsFor(a);
    try {
      setArBills(await listArBills(tenantCode, a.id));
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  async function openChargeModal(a: ArAccount) {
    setChargeFor(a);
    try {
      const all = await listBills(tenantCode);
      setOpenBills(all.filter((b) => b.status === "OPEN" && b.balance > 0));
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  async function doCharge(billId: string) {
    if (!chargeFor) return;
    try {
      await chargeBillToAr(tenantCode, chargeFor.id, billId);
      message.success(`账单已挂账至 ${chargeFor.name}`);
      setChargeFor(null);
      load();
    } catch (e: unknown) {
      message.error((e as Error).message);
    }
  }

  const columns = [
    { title: "单位名称", dataIndex: "name", key: "name" },
    {
      title: "联系人",
      key: "contact",
      render: (_: unknown, r: ArAccount) =>
        r.contact ? `${r.contact}${r.contact_phone ? ` / ${r.contact_phone}` : ""}` : "—",
    },
    {
      title: "信用额度",
      dataIndex: "credit_limit_cents",
      key: "credit_limit_cents",
      align: "right" as const,
      render: (v: number) => (v > 0 ? fmtCents(v) : "不限"),
    },
    {
      title: "未清欠款",
      dataIndex: "balance_cents",
      key: "balance_cents",
      align: "right" as const,
      render: (v: number) =>
        v > 0 ? <Tag color="orange">{fmtCents(v)}</Tag> : <Tag color="green">已清</Tag>,
    },
    {
      title: "操作",
      key: "act",
      render: (_: unknown, r: ArAccount) => (
        <Space>
          <Button type="link" onClick={() => openChargeModal(r)}>
            挂账
          </Button>
          <Button type="link" onClick={() => setRepayFor(r)}>
            还款
          </Button>
          <Button type="link" onClick={() => openBillsDrawer(r)}>
            挂账账单
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="协议单位挂账 / 月结"
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={!hotelId}
          onClick={() => setCreateOpen(true)}
        >
          新建协议单位
        </Button>
      }
    >
      {!hotelId ? (
        <Empty description="请先在顶栏选择门店" />
      ) : (
        <Table rowKey="id" loading={loading} columns={columns} dataSource={rows} pagination={false} />
      )}

      <Modal
        title="新建协议单位"
        open={createOpen}
        onOk={submitCreate}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="单位名称" rules={[{ required: true }]}>
            <Input placeholder="如 深圳华创旅行社" />
          </Form.Item>
          <Form.Item name="contact" label="联系人（可选）">
            <Input />
          </Form.Item>
          <Form.Item name="contact_phone" label="联系电话（可选）">
            <Input />
          </Form.Item>
          <Form.Item
            name="credit_limit"
            label="信用额度（元，留空=不限）"
            rules={[{ type: "number", min: 0 }]}
          >
            <Input type="number" min={0} placeholder="如 10000" />
          </Form.Item>
          <Form.Item name="note" label="备注（可选）">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`还款 · ${repayFor?.name ?? ""}（欠款 ${repayFor ? fmtCents(repayFor.balance_cents) : ""}）`}
        open={!!repayFor}
        onOk={submitRepay}
        onCancel={() => setRepayFor(null)}
        okText="确认还款"
        cancelText="取消"
      >
        <Form form={repayForm} layout="vertical">
          <Form.Item
            name="amount"
            label="还款金额（元）"
            rules={[{ required: true, message: "请输入还款金额" }]}
          >
            <Input type="number" min={0.01} />
          </Form.Item>
          <Form.Item name="method" label="还款方式" initialValue="BANK">
            <Select options={REPAY_METHODS} />
          </Form.Item>
          <Form.Item name="note" label="备注（可选）">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`挂账 · ${chargeFor?.name ?? ""}`}
        open={!!chargeFor}
        onCancel={() => setChargeFor(null)}
        footer={null}
      >
        <p style={{ color: "#888" }}>选择未结清账单，将其余额整笔挂至该单位：</p>
        {openBills.length === 0 ? (
          <p>暂无未结清账单</p>
        ) : (
          openBills.map((b) => (
            <div
              key={b.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "6px 0",
                borderBottom: "1px solid #f0f0f0",
              }}
            >
              <span>
                #{b.bill_no} · {b.guest_name || "散客"} ·{" "}
                {b.room_no ? `房 ${b.room_no} · ` : ""}
                应收 {fmtCents(b.balance)}
              </span>
              <Button type="link" onClick={() => doCharge(b.id)}>
                挂这笔
              </Button>
            </div>
          ))
        )}
      </Modal>

      <Drawer
        title={`挂账账单 · ${billsFor?.name ?? ""}`}
        open={!!billsFor}
        onClose={() => setBillsFor(null)}
        width={480}
      >
        {arBills.length === 0 ? (
          <Empty description="暂无挂账账单" />
        ) : (
          arBills.map((b) => (
            <Descriptions
              key={b.id}
              size="small"
              bordered
              column={1}
              style={{ marginBottom: 16 }}
            >
              <Descriptions.Item label="账单号">{b.bill_no}</Descriptions.Item>
              <Descriptions.Item label="客人">{b.guest_name || "—"}</Descriptions.Item>
              <Descriptions.Item label="房号">{b.room_no || "—"}</Descriptions.Item>
              <Descriptions.Item label="状态">{b.status}</Descriptions.Item>
            </Descriptions>
          ))
        )}
      </Drawer>
    </Card>
  );
}
