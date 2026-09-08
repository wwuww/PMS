// 押金详情抽屉 + 流水时间线（M32.18 T05）
import { useEffect, useState } from "react";
import { Drawer, Descriptions, Spin, Tag, Timeline, Typography, message } from "antd";
import { getDeposit } from "../../api/endpoints";
import type { Deposit } from "../../api/types";
import { useTenant } from "../../store/tenant";
import { fmtCents } from "../../utils/format";
import { ACTION_LABELS, KIND_LABELS, METHOD_LABELS, STATUS_META } from "./meta";

interface Props {
  open: boolean;
  depositId: string | null;
  onClose: () => void;
}

const { Text } = Typography;

export default function DepositDetailDrawer({ open, depositId, onClose }: Props) {
  const { tenantCode } = useTenant();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Deposit | null>(null);

  useEffect(() => {
    if (!open || !depositId) {
      setData(null);
      return;
    }
    let alive = true;
    setLoading(true);
    getDeposit(tenantCode, depositId)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: any) => {
        if (alive) message.error(e?.message || "加载详情失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, depositId, tenantCode]);

  const statusMeta = data ? STATUS_META[data.status] : null;

  return (
    <Drawer title="押金详情" open={open} onClose={onClose} width={560} destroyOnClose>
      {loading ? (
        <div style={{ display: "grid", placeItems: "center", padding: 40 }}>
          <Spin tip="加载中…" />
        </div>
      ) : !data ? (
        <Text type="secondary">无数据</Text>
      ) : (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="押金单号">{data.deposit_no}</Descriptions.Item>
            <Descriptions.Item label="类型">
              <Tag>{KIND_LABELS[data.kind] ?? data.kind}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="支付方式">
              <Tag color="blue">{METHOD_LABELS[data.method] ?? data.method}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {statusMeta ? (
                <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
              ) : (
                <Tag>{data.status}</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="金额">{fmtCents(data.amount_cents)}</Descriptions.Item>
            <Descriptions.Item label="已冲抵 / 已退 / 没收 / 可用">
              {fmtCents(data.applied_cents)} / {fmtCents(data.refunded_cents)} /{" "}
              {fmtCents(data.forfeited_cents)} / <Text strong>{fmtCents(data.available_cents)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="房号">{data.room_no || "—"}</Descriptions.Item>
            <Descriptions.Item label="预订 ID">{data.booking_id || "—"}</Descriptions.Item>
            <Descriptions.Item label="账单 ID">{data.bill_id || "—"}</Descriptions.Item>
            <Descriptions.Item label="操作员">{data.operator}</Descriptions.Item>
            <Descriptions.Item label="版本">{data.version}</Descriptions.Item>
            <Descriptions.Item label="外部流水号">{data.ref_no || "—"}</Descriptions.Item>
            <Descriptions.Item label="备注">{data.note || "—"}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{data.created_at}</Descriptions.Item>
            {data.expires_at && (
              <Descriptions.Item label="过期时间">{data.expires_at}</Descriptions.Item>
            )}
            {data.released_at && (
              <Descriptions.Item label="释放时间">{data.released_at}</Descriptions.Item>
            )}
            {data.captured_at && (
              <Descriptions.Item label="转实收时间">{data.captured_at}</Descriptions.Item>
            )}
            {data.voided_at && (
              <Descriptions.Item label="作废时间">{data.voided_at}</Descriptions.Item>
            )}
          </Descriptions>

          <Typography.Title level={5} style={{ marginTop: 20, marginBottom: 12 }}>
            流水（{data.transactions?.length ?? 0}）
          </Typography.Title>
          {(data.transactions ?? []).length === 0 ? (
            <Text type="secondary">暂无流水</Text>
          ) : (
            <Timeline
              items={(data.transactions ?? []).map((t) => ({
                color:
                  t.action === "REFUND"
                    ? "orange"
                    : t.action === "VOID"
                    ? "red"
                    : t.action === "APPLY"
                    ? "green"
                    : t.action === "RELEASE"
                    ? "blue"
                    : "gray",
                children: (
                  <div>
                    <div>
                      <Text strong>{ACTION_LABELS[t.action] ?? t.action}</Text>{" "}
                      <Text>{fmtCents(t.amount_cents)}</Text>{" "}
                      {t.method && <Tag>{METHOD_LABELS[t.method] ?? t.method}</Tag>}
                    </div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {t.operator} · {t.created_at}
                      {t.bill_id ? ` · 账单 ${t.bill_id}` : ""}
                      {t.note ? ` · ${t.note}` : ""}
                    </Text>
                  </div>
                ),
              }))}
            />
          )}
        </>
      )}
    </Drawer>
  );
}