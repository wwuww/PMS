import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  listCommissionReconciliations,
  listCommissionRules,
  setCommissionRule,
} from "../api/endpoints";
import type {
  CommissionReconciliation,
  CommissionRule,
} from "../api/types";
import { fmtBps, fmtCents } from "../utils/format";

export default function Commission() {
  const { tenantCode, hotelId } = useTenant();
  const [rules, setRules] = useState<CommissionRule[]>([]);
  const [recons, setRecons] = useState<CommissionReconciliation[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [form] = Form.useForm();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [r, c] = await Promise.all([
        listCommissionRules(tenantCode),
        listCommissionReconciliations(tenantCode, hotelId ?? undefined),
      ]);
      setRules(r);
      setRecons(c);
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreate = async () => {
    const v = await form.validateFields();
    try {
      await setCommissionRule(tenantCode, {
        channel: v.channel,
        rate_bps: Math.round(Number(v.rate_bps) * 100),
        note: v.note || "",
      });
      message.success("佣金规则已保存");
      setShowCreate(false);
      form.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "保存失败");
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="佣金规则（M9）"
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={refresh}
              loading={loading}
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setShowCreate(true);
                form.resetFields();
              }}
            >
              新增规则
            </Button>
          </Space>
        }
      >
        <Table<CommissionRule>
          rowKey="id"
          dataSource={rules}
          pagination={false}
          size="small"
          columns={[
            { title: "渠道", dataIndex: "channel", render: (c) => <Tag>{c}</Tag> },
            {
              title: "费率",
              dataIndex: "rate_bps",
              render: (v: number) => fmtBps(v),
            },
            { title: "备注", dataIndex: "note" },
          ]}
        />
      </Card>

      <Card title="佣金对账明细" style={{ marginTop: 16 }}>
        <Table<CommissionReconciliation>
          rowKey="id"
          dataSource={recons}
          loading={loading}
          pagination={false}
          size="small"
          columns={[
            { title: "营业日", dataIndex: "business_date" },
            { title: "门店", dataIndex: "hotel_id" },
            { title: "渠道", dataIndex: "channel", render: (c) => <Tag>{c}</Tag> },
            {
              title: "房费（分）",
              dataIndex: "room_revenue_cents",
              render: (v: number) => fmtCents(v),
            },
            {
              title: "费率",
              dataIndex: "commission_rate_bps",
              render: (v: number) => fmtBps(v),
            },
            {
              title: "佣金（分）",
              dataIndex: "commission_cents",
              render: (v: number) => fmtCents(v),
            },
            {
              title: "状态",
              dataIndex: "status",
              render: (s: string) => (
                <Tag color={s === "RECONCILED" ? "green" : "orange"}>{s}</Tag>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新增佣金规则"
        open={showCreate}
        onOk={handleCreate}
        onCancel={() => setShowCreate(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="channel"
            label="渠道"
            rules={[{ required: true, message: "请输入渠道" }]}
          >
            <Input placeholder="如 CTRIP / DIRECT / AGODA" />
          </Form.Item>
          <Form.Item
            name="rate_bps"
            label="费率（%，如 12 表示 12%）"
            rules={[{ required: true, message: "请输入费率" }]}
          >
            <InputNumber min={0} max={100} step={0.5} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
