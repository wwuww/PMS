import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Form,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import dayjs from "dayjs";
import { ReloadOutlined, SyncOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  closePayOrder,
  listPayOrders,
  reconcilePay,
} from "../api/endpoints";
import type { PayOrder, PayReconcileResult } from "../api/types";
import { fmtCents } from "../utils/format";

const ORDER_COLOR: Record<string, string> = {
  CREATED: "orange",
  PAID: "green",
  CLOSED: "default",
};

export default function Reconciliation() {
  const { tenantCode } = useTenant();
  const [rows, setRows] = useState<PayOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [showRecon, setShowRecon] = useState(false);
  const [reconResult, setReconResult] = useState<PayReconcileResult | null>(null);
  const [form] = Form.useForm();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listPayOrders(tenantCode, statusFilter));
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode, statusFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleReconcile = async () => {
    const v = await form.validateFields();
    const before = (v.before as dayjs.Dayjs).format("YYYY-MM-DDTHH:mm:ss");
    try {
      const res = await reconcilePay(tenantCode, before);
      setReconResult(res);
      message.success(
        `对账完成：扫描 ${res.scanned} / 关单 ${res.closed} / 补单 ${res.recovered}`
      );
      setShowRecon(false);
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "对账失败");
    }
  };

  const closeOrder = async (no: string) => {
    try {
      await closePayOrder(tenantCode, no);
      message.success("支付单已关闭");
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "关闭失败");
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="支付对账（M7-2 掉单对账）"
        extra={
          <Space>
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 120 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { value: "CREATED", label: "待支付" },
                { value: "PAID", label: "已支付" },
                { value: "CLOSED", label: "已关闭" },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
              刷新
            </Button>
            <Button
              type="primary"
              icon={<SyncOutlined />}
              onClick={() => {
                setShowRecon(true);
                setReconResult(null);
                form.resetFields();
              }}
            >
              掉单对账
            </Button>
          </Space>
        }
      >
        <Table<PayOrder>
          rowKey="out_trade_no"
          dataSource={rows}
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
          columns={[
            { title: "商户单号", dataIndex: "out_trade_no", width: 200 },
            { title: "渠道", dataIndex: "channel", render: (c) => <Tag>{c}</Tag> },
            { title: "主题", dataIndex: "subject", render: (v) => v || "—" },
            {
              title: "金额",
              dataIndex: "amount_cents",
              render: (v: number) => fmtCents(v),
            },
            {
              title: "状态",
              dataIndex: "status",
              render: (s: string) => <Tag color={ORDER_COLOR[s]}>{s}</Tag>,
            },
            { title: "交易号", dataIndex: "transaction_id", render: (v) => v || "—", width: 180 },
            { title: "支付时间", dataIndex: "paid_at", render: (v) => v || "—" },
            {
              title: "操作",
              key: "op",
              render: (_, r) =>
                r.status === "CREATED" ? (
                  <Button size="small" danger onClick={() => closeOrder(r.out_trade_no)}>
                    关闭
                  </Button>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </Card>

      <Modal
        title="掉单对账"
        open={showRecon}
        onOk={handleReconcile}
        onCancel={() => setShowRecon(false)}
        okText="执行对账"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="before"
            label="处理该时刻之前创建的未支付单"
            rules={[{ required: true, message: "请选择截止时刻" }]}
          >
            <DatePicker showTime style={{ width: "100%" }} />
          </Form.Item>
          {reconResult && (
            <Alert
              type="success"
              message={`扫描 ${reconResult.scanned} 笔，关单 ${reconResult.closed} 笔，补单 ${reconResult.recovered} 笔`}
            />
          )}
        </Form>
      </Modal>
    </div>
  );
}
