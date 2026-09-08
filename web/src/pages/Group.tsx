import { useEffect, useState } from "react";
import {
  Card,
  Col,
  Empty,
  Row,
  Spin,
  Statistic,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useTenant } from "../store/tenant";
import { groupDashboard, groupSettlement } from "../api/endpoints";
import type { HqDashboard, Settlement, SettlementRow } from "../api/types";
import { fmtCents } from "../utils/format";

const { Title, Text } = Typography;

export default function GroupPage() {
  const { tenantCode } = useTenant();
  const [hq, setHq] = useState<HqDashboard | null>(null);
  const [settlement, setSettlement] = useState<Settlement | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const [h, s] = await Promise.all([groupDashboard(tenantCode), groupSettlement(tenantCode)]);
      setHq(h);
      setSettlement(s);
    } catch (e: any) {
      message.error(e?.message || "集团驾驶舱加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode]);

  if (loading && !hq) return <Spin tip="加载集团驾驶舱…" />;
  if (!hq) return <Empty description="暂无数据" />;

  const columns: ColumnsType<SettlementRow> = [
    { title: "门店", dataIndex: "name", key: "name" },
    {
      title: "现付（CASH/银联）",
      dataIndex: "pay_now_cents",
      align: "right",
      render: (v: number) => fmtCents(v),
    },
    {
      title: "预付（微信/支付宝/储值）",
      dataIndex: "prepaid_cents",
      align: "right",
      render: (v: number) => fmtCents(v),
    },
    {
      title: "合计",
      dataIndex: "total_cents",
      align: "right",
      render: (v: number) => <Text strong>{fmtCents(v)}</Text>,
    },
  ];

  return (
    <div>
      <Title level={4}>集团驾驶舱（M17 总部管控）</Title>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic title="门店数" value={hq.hotel_count} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="集团总营收" value={hq.total_revenue / 100} precision={2} prefix="¥" />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="集团房费收入" value={hq.total_room_revenue / 100} precision={2} prefix="¥" />
          </Card>
        </Col>
      </Row>

      <Card title="门店排名（按最新日报）" style={{ marginBottom: 16 }} loading={loading}>
        {hq.hotels.length === 0 ? (
          <Empty description="暂无门店日报" />
        ) : (
          <Table
            rowKey="hotel_id"
            pagination={false}
            columns={[
              { title: "门店", dataIndex: "name", key: "name" },
              {
                title: "房费收入",
                dataIndex: "room_revenue",
                align: "right",
                render: (v: number) => fmtCents(v),
              },
              {
                title: "总营收",
                dataIndex: "total_revenue",
                align: "right",
                render: (v: number) => fmtCents(v),
              },
              {
                title: "RevPAR",
                dataIndex: "revpar",
                align: "right",
                render: (v: number) => fmtCents(v),
              },
              {
                title: "出租率",
                dataIndex: "occ_pct",
                align: "right",
                render: (v: number) => `${Number(v).toFixed(1)}%`,
              },
            ]}
            dataSource={hq.hotels as Array<Record<string, any>>}
          />
        )}
      </Card>

      <Card title="两级分账汇总" loading={loading}>
        {!settlement || settlement.hotels.length === 0 ? (
          <Empty description="暂无分账数据" />
        ) : (
          <Table rowKey="hotel_id" pagination={false} columns={columns} dataSource={settlement.hotels} />
        )}
      </Card>
    </div>
  );
}
