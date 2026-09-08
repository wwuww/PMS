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
import { ReloadOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  closeShift,
  listShifts,
  openShift,
} from "../api/endpoints";
import type { Shift, ShiftClose, ShiftOpen } from "../api/types";
import { fmtCents } from "../utils/format";

export default function Shifts() {
  const { tenantCode, hotelId } = useTenant();
  const [rows, setRows] = useState<Shift[]>([]);
  const [loading, setLoading] = useState(false);
  const [openVisible, setOpenVisible] = useState(false);
  const [closeTarget, setCloseTarget] = useState<Shift | null>(null);
  const [openForm] = Form.useForm();
  const [closeForm] = Form.useForm();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listShifts(tenantCode, hotelId ?? undefined));
    } catch (e: any) {
      message.error(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tenantCode, hotelId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleOpen = async () => {
    if (!hotelId) {
      message.warning("请先选择门店");
      return;
    }
    const v = await openForm.validateFields();
    const body: ShiftOpen = {
      hotel_id: hotelId,
      cashier: v.cashier,
      opening_float_cents: Math.round(Number(v.float || 0) * 100),
    };
    try {
      await openShift(tenantCode, body);
      message.success("已开班");
      setOpenVisible(false);
      openForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "开班失败");
    }
  };

  const handleClose = async () => {
    if (!closeTarget) return;
    const v = await closeForm.validateFields();
    const body: ShiftClose = {
      counted_cash_cents: Math.round(Number(v.counted) * 100),
      note: v.note || "",
    };
    try {
      await closeShift(tenantCode, closeTarget.id, body);
      message.success("已交班");
      setCloseTarget(null);
      closeForm.resetFields();
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "交班失败");
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="前台交班（M3）"
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
              onClick={() => {
                setOpenVisible(true);
                openForm.resetFields();
              }}
            >
              开班
            </Button>
          </Space>
        }
      >
        <Table<Shift>
          rowKey="id"
          dataSource={rows}
          loading={loading}
          pagination={false}
          size="small"
          columns={[
            { title: "ID", dataIndex: "id" },
            { title: "收银员", dataIndex: "cashier" },
            {
              title: "状态",
              dataIndex: "status",
              render: (s: string) => (
                <Tag color={s === "OPEN" ? "green" : "default"}>{s}</Tag>
              ),
            },
            {
              title: "备用金",
              dataIndex: "opening_float_cents",
              render: (v: number) => fmtCents(v),
            },
            {
              title: "预期现金",
              dataIndex: "expected_cash_cents",
              render: (v: number) => fmtCents(v),
            },
            {
              title: "实点现金",
              dataIndex: "counted_cash_cents",
              render: (v: number) => fmtCents(v),
            },
            {
              title: "班内实收",
              dataIndex: "received_cents",
              render: (v: number) => fmtCents(v || 0),
            },
            {
              title: "班内应收",
              dataIndex: "receivable_cents",
              render: (v: number) => fmtCents(v || 0),
            },
            {
              title: "差异",
              dataIndex: "discrepancy_cents",
              render: (v: number) => (
                <span style={{ color: v === 0 ? "#333" : v > 0 ? "green" : "red" }}>
                  {v > 0 ? "+" : ""}
                  {fmtCents(v)}
                </span>
              ),
            },
            { title: "开班时间", dataIndex: "opened_at", render: (v) => v || "—" },
            { title: "交班时间", dataIndex: "closed_at", render: (v) => v || "—" },
            {
              title: "操作",
              key: "op",
              render: (_, r) =>
                r.status === "OPEN" ? (
                  <Button
                    size="small"
                    type="primary"
                    onClick={() => {
                      setCloseTarget(r);
                      closeForm.resetFields();
                    }}
                  >
                    交班
                  </Button>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </Card>

      <Modal
        title="开班"
        open={openVisible}
        onOk={handleOpen}
        onCancel={() => setOpenVisible(false)}
        okText="开班"
        cancelText="取消"
      >
        <Form form={openForm} layout="vertical">
          <Form.Item
            name="cashier"
            label="收银员"
            rules={[{ required: true, message: "请输入收银员" }]}
          >
            <Input placeholder="收银员姓名" />
          </Form.Item>
          <Form.Item name="float" label="备用金（元）" initialValue={0}>
            <InputNumber min={0} step={50} precision={2} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`交班 · ${closeTarget?.cashier ?? ""}`}
        open={!!closeTarget}
        onOk={handleClose}
        onCancel={() => setCloseTarget(null)}
        okText="确认交班"
        cancelText="取消"
      >
        <Form form={closeForm} layout="vertical">
          <Form.Item
            name="counted"
            label="实点现金（元）"
            rules={[{ required: true, message: "请输入实点现金" }]}
          >
            <InputNumber min={0} step={10} precision={2} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
