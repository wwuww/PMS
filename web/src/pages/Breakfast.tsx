// 批次④ - 早餐券管理（含餐厅核销）
// 列表（订单号/类型/是否已用/日期范围筛选）+ 发券 Modal + 核销区 + 行内作废
// 门控：useCan(PERM.BREAKFAST_MANAGE)，映射为后端权限码 breakfast.manage
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
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { Dayjs } from "dayjs";
import {
  issueBreakfastTickets,
  listBreakfastTickets,
  useBreakfastTicket,
  voidBreakfastTicket,
} from "../api/endpoints";
import type { BreakfastTicket } from "../api/types";
import { useTenant } from "../store/tenant";
import { PERM, currentOperator, useCan } from "../utils/permission";

const { RangePicker } = DatePicker;

/** 券类型：0 送早 / 5 兑早 / 9 购早。 */
const TICKET_TYPE_LABEL: Record<number, string> = {
  0: "送早",
  5: "兑早",
  9: "购早",
};

const TICKET_TYPE_OPTIONS = [
  { value: 0, label: "送早（赠送）" },
  { value: 5, label: "兑早（积分兑换）" },
  { value: 9, label: "购早（购买）" },
];

const USED_OPTIONS = [
  { value: "ALL", label: "全部状态" },
  { value: "false", label: "未使用" },
  { value: "true", label: "已使用" },
];

interface Filters {
  booking_id: string;
  ticket_type: number | "ALL";
  is_used: string;
  range: [Dayjs | null, Dayjs | null] | null;
}

/** 早餐券状态：已用 / 未用 / 作废。 */
function ticketStatus(t: BreakfastTicket): { label: string; color: string } {
  if (t.is_valid === false) return { label: "作废", color: "red" };
  if (t.is_used) return { label: "已用", color: "green" };
  return { label: "未用", color: "blue" };
}

export default function Breakfast() {
  const { tenantCode } = useTenant();
  const canManage = useCan(PERM.BREAKFAST_MANAGE);

  const [filters, setFilters] = useState<Filters>({
    booking_id: "",
    ticket_type: "ALL",
    is_used: "ALL",
    range: null,
  });
  const [data, setData] = useState<BreakfastTicket[]>([]);
  const [loading, setLoading] = useState(false);

  // 发券
  const [issueOpen, setIssueOpen] = useState(false);
  const [issueForm] = Form.useForm();
  const [issuing, setIssuing] = useState(false);

  // 核销
  const [useForm] = Form.useForm();
  const [using, setUsing] = useState(false);

  const fetchList = useCallback(async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const list = await listBreakfastTickets(tenantCode, {
        booking_id: filters.booking_id.trim() || undefined,
        ticket_type: filters.ticket_type === "ALL" ? undefined : Number(filters.ticket_type),
        is_used: filters.is_used === "ALL" ? undefined : filters.is_used === "true",
        date_from: filters.range?.[0]?.format("YYYY-MM-DD") || undefined,
        date_to: filters.range?.[1]?.format("YYYY-MM-DD") || undefined,
        limit: 200,
      });
      setData(Array.isArray(list) ? list : []);
    } catch (e: unknown) {
      message.error((e as Error).message || "加载早餐券失败");
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [tenantCode, filters]);

  useEffect(() => {
    void fetchList();
  }, [fetchList]);

  const refresh = () => void fetchList();

  const openIssue = () => {
    issueForm.resetFields();
    issueForm.setFieldsValue({
      ticket_type: 0,
      count: 1,
      operator: currentOperator(),
    });
    setIssueOpen(true);
  };

  const submitIssue = async () => {
    const v = await issueForm.validateFields();
    const range = v.range as [Dayjs, Dayjs] | null | undefined;
    setIssuing(true);
    try {
      const created = await issueBreakfastTickets(tenantCode, {
        booking_id: v.booking_id ?? null,
        room_no: v.room_no?.trim() || null,
        ticket_type: Number(v.ticket_type),
        ticket_type_name: v.ticket_type_name?.trim() || TICKET_TYPE_LABEL[Number(v.ticket_type)] || null,
        count: Number(v.count || 1),
        valid_from: range?.[0]?.format("YYYY-MM-DD") ?? null,
        valid_to: range?.[1]?.format("YYYY-MM-DD") ?? null,
        card_type: v.card_type?.trim() || null,
        memo: v.memo?.trim() || null,
        operator: currentOperator(),
      });
      const n = Array.isArray(created) ? created.length : Number(v.count || 1);
      message.success(`发券成功，共 ${n} 张`);
      setIssueOpen(false);
      issueForm.resetFields();
      refresh();
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
      const t = await useBreakfastTicket(tenantCode, {
        ticket_no: String(v.ticket_no || "").trim(),
        business_date: dayjs(v.business_date).format("YYYY-MM-DD"),
        operator: currentOperator(),
      });
      message.success(`券 ${t.ticket_no || v.ticket_no} 核销成功`);
      useForm.setFieldsValue({ ticket_no: "" });
      refresh();
    } catch (e: unknown) {
      // 后端 400（已核销 / 已作废 / 不在有效期）会带 detail，原样透出
      message.error((e as Error).message || "核销失败");
    } finally {
      setUsing(false);
    }
  };

  const doVoid = async (row: BreakfastTicket) => {
    try {
      await voidBreakfastTicket(tenantCode, row.id as number, {
        reason: "前台作废",
        operator: currentOperator(),
      });
      message.success(`券 ${row.ticket_no || row.id} 已作废`);
      refresh();
    } catch (e: unknown) {
      message.error((e as Error).message || "作废失败");
    }
  };

  const columns: ColumnsType<BreakfastTicket> = useMemo(
    () => [
      { title: "券号", dataIndex: "ticket_no", width: 170, render: (v) => v || "—" },
      { title: "房号", dataIndex: "room_no", width: 90, render: (v) => v || "—" },
      { title: "订单号", dataIndex: "booking_id", width: 110, render: (v) => v ?? "—" },
      {
        title: "类型",
        dataIndex: "ticket_type",
        width: 160,
        render: (v: number | undefined, r: BreakfastTicket) => {
          const label = TICKET_TYPE_LABEL[v ?? -1] ?? (v == null ? "—" : String(v));
          const name = r.ticket_type_name?.trim();
          return (
            <Space size={4}>
              <Tag color="orange">{label}</Tag>
              {name && name !== label && <span>{name}</span>}
            </Space>
          );
        },
      },
      {
        title: "有效期",
        key: "valid",
        width: 190,
        render: (_: unknown, r: BreakfastTicket) => {
          const from = r.valid_from || "—";
          const to = r.valid_to || "—";
          return `${from} ~ ${to}`;
        },
      },
      {
        title: "状态",
        key: "status",
        width: 90,
        render: (_: unknown, r: BreakfastTicket) => {
          const s = ticketStatus(r);
          return <Tag color={s.color}>{s.label}</Tag>;
        },
      },
      {
        title: "使用营业日",
        dataIndex: "used_business_date",
        width: 120,
        render: (v: string | null) => v || "—",
      },
      { title: "操作人", dataIndex: "operator", width: 110, render: (v) => v || "—" },
      {
        title: "操作",
        key: "op",
        width: 90,
        fixed: "right",
        render: (_: unknown, r: BreakfastTicket) => {
          const disabled = !canManage || r.is_valid === false || !!r.is_used;
          return (
            <Popconfirm
              title="确认作废该早餐券？"
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
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canManage, tenantCode]
  );

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
            早餐券管理
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            发券 / 核销 / 作废（BREAKFAST_MANAGE）
          </Typography.Text>
        </div>
        <Space>
          <Button onClick={refresh} loading={loading}>
            刷新
          </Button>
          <Button type="primary" disabled={!canManage} onClick={openIssue}>
            发券
          </Button>
        </Space>
      </div>

      {/* 核销区：餐厅同一个页面直接扫券核销（D5） */}
      <Card size="small" title="早餐券核销" style={{ marginBottom: 12 }}>
        <Form
          form={useForm}
          layout="inline"
          onFinish={submitUse}
          initialValues={{ business_date: dayjs(), ticket_no: "" }}
        >
          <Form.Item
            name="ticket_no"
            label="券号"
            rules={[{ required: true, message: "请扫描或输入券号" }]}
          >
            <Input
              placeholder="扫描 / 输入券号"
              allowClear
              style={{ width: 260 }}
              autoFocus
              onPressEnter={submitUse}
            />
          </Form.Item>
          <Form.Item
            name="business_date"
            label="营业日期"
            rules={[{ required: true, message: "请选择营业日期" }]}
          >
            <DatePicker style={{ width: 160 }} allowClear={false} />
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

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          marginBottom: 12,
          alignItems: "center",
        }}
      >
        <Input
          style={{ width: 170 }}
          placeholder="订单号"
          allowClear
          value={filters.booking_id}
          onChange={(e) => setFilters((f) => ({ ...f, booking_id: e.target.value }))}
        />
        <Select
          style={{ width: 170 }}
          value={filters.ticket_type}
          options={[{ value: "ALL", label: "全部类型" }, ...TICKET_TYPE_OPTIONS]}
          onChange={(v) => setFilters((f) => ({ ...f, ticket_type: v }))}
        />
        <Select
          style={{ width: 140 }}
          value={filters.is_used}
          options={USED_OPTIONS}
          onChange={(v) => setFilters((f) => ({ ...f, is_used: v }))}
        />
        <RangePicker
          value={filters.range ?? undefined}
          onChange={(r) =>
            setFilters((f) => ({ ...f, range: r && r[0] ? [r[0], r[1] ?? null] : null }))
          }
        />
        <Button onClick={() => setFilters({ booking_id: "", ticket_type: "ALL", is_used: "ALL", range: null })}>
          重置
        </Button>
      </div>

      <Table<BreakfastTicket>
        rowKey="id"
        loading={loading}
        size="small"
        dataSource={data}
        columns={columns}
        scroll={{ x: 1180 }}
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 张券` }}
        locale={{ emptyText: <Empty description="暂无早餐券" /> }}
      />

      <Modal
        title="发放早餐券"
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
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
            <Form.Item name="booking_id" label="订单 ID（可选）">
              <InputNumber style={{ width: "100%" }} min={0} />
            </Form.Item>
            <Form.Item name="room_no" label="房号（可选）">
              <Input maxLength={16} placeholder="如 408" />
            </Form.Item>
          </div>
          <Form.Item
            name="ticket_type"
            label="券类型"
            rules={[{ required: true, message: "请选择券类型" }]}
          >
            <Select options={TICKET_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="ticket_type_name" label="类型名称（可选，默认按类型生成）">
            <Input maxLength={32} placeholder="如 自助早餐券" />
          </Form.Item>
          <Form.Item
            name="count"
            label="发放张数"
            rules={[{ required: true, message: "请输入发放张数" }]}
          >
            <InputNumber min={1} max={100} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="range" label="有效期（可选，不填由后端按默认规则生成）">
            <RangePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="card_type" label="卡类型（可选）">
            <Input maxLength={32} placeholder="如 房卡 / 会员卡" />
          </Form.Item>
          <Form.Item name="memo" label="备注">
            <Input.TextArea rows={2} maxLength={255} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
