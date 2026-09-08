import { useCallback, useState } from "react";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Space,
  Statistic,
  Tag,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { useTenant } from "../store/tenant";
import {
  createMember,
  getMember,
  rechargeMember,
} from "../api/endpoints";
import type { Member } from "../api/types";
import { fmtCents } from "../utils/format";

export default function Members() {
  const { tenantCode, hotelId } = useTenant();
  const [phone, setPhone] = useState("");
  const [member, setMember] = useState<Member | null>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [showRecharge, setShowRecharge] = useState(false);
  const [createForm] = Form.useForm();
  const [rechargeForm] = Form.useForm();

  const doSearch = useCallback(async () => {
    if (!phone) {
      message.warning("请输入手机号");
      return;
    }
    setSearching(true);
    try {
      const m = await getMember(tenantCode, phone);
      setMember(m);
    } catch (e: any) {
      setMember(null);
      message.error(e?.message || "未找到会员");
    } finally {
      setSearching(false);
    }
  }, [phone, tenantCode]);

  const refresh = useCallback(() => {
    if (member) doSearch();
  }, [member, doSearch]);

  const handleCreate = async () => {
    if (!hotelId) {
      message.warning("请先选择门店");
      return;
    }
    const v = await createForm.validateFields();
    try {
      const m = await createMember(tenantCode, {
        hotel_id: hotelId,
        name: v.name,
        phone: v.phone,
      });
      message.success("会员创建成功");
      setShowCreate(false);
      createForm.resetFields();
      setPhone(m.phone);
      setMember(m);
    } catch (e: any) {
      message.error(e?.message || "创建失败");
    }
  };

  const handleRecharge = async () => {
    if (!member) return;
    const v = await rechargeForm.validateFields();
    try {
      const m = await rechargeMember(tenantCode, member.phone, {
        amount: Math.round(Number(v.amount) * 100),
        operator: "web",
      });
      message.success(`充值成功 ¥${v.amount}`);
      setShowRecharge(false);
      rechargeForm.resetFields();
      setMember(m);
    } catch (e: any) {
      message.error(e?.message || "充值失败");
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="会员 CRM"
        extra={
          <Space>
            <Button
              icon={<PlusOutlined />}
              type="primary"
              onClick={() => setShowCreate(true)}
            >
              新建会员
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={refresh}
              loading={loading}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }}>
          <Input
            placeholder="输入手机号查询会员"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            onPressEnter={doSearch}
            allowClear
            style={{ width: 260 }}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            loading={searching}
            onClick={doSearch}
          >
            查询
          </Button>
        </Space>

        {member ? (
          <Row gutter={16}>
            <Col span={14}>
              <Descriptions column={2} bordered size="small">
                <Descriptions.Item label="姓名">
                  {member.name}
                </Descriptions.Item>
                <Descriptions.Item label="手机号">
                  {member.phone}
                </Descriptions.Item>
                <Descriptions.Item label="等级">
                  <Tag color="blue">{member.level}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="入住次数">
                  {member.stays}
                </Descriptions.Item>
              </Descriptions>
            </Col>
            <Col span={10}>
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    title="储值余额"
                    value={fmtCents(member.stored_value)}
                    prefix="¥"
                  />
                </Col>
                <Col span={12}>
                  <Statistic title="积分" value={member.points} />
                </Col>
                <Col span={12} style={{ marginTop: 12 }}>
                  <Statistic
                    title="累计消费"
                    value={fmtCents(member.total_spend)}
                    prefix="¥"
                  />
                </Col>
                <Col span={12} style={{ marginTop: 12 }}>
                  <Button
                    type="primary"
                    onClick={() => {
                      setShowRecharge(true);
                      rechargeForm.resetFields();
                    }}
                  >
                    储值充值
                  </Button>
                </Col>
              </Row>
            </Col>
          </Row>
        ) : (
          <div style={{ color: "#999", padding: "24px 0", textAlign: "center" }}>
            输入手机号查询，或点击「新建会员」登记
          </div>
        )}
      </Card>

      <Modal
        title="新建会员"
        open={showCreate}
        onOk={handleCreate}
        onCancel={() => setShowCreate(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="name"
            label="姓名"
            rules={[{ required: true, message: "请输入姓名" }]}
          >
            <Input placeholder="会员姓名" />
          </Form.Item>
          <Form.Item
            name="phone"
            label="手机号"
            rules={[{ required: true, message: "请输入手机号" }]}
          >
            <Input placeholder="11 位手机号" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`储值充值 · ${member?.name ?? ""}`}
        open={showRecharge}
        onOk={handleRecharge}
        onCancel={() => setShowRecharge(false)}
        okText="确认充值"
        cancelText="取消"
      >
        <Form form={rechargeForm} layout="vertical">
          <Form.Item
            name="amount"
            label="充值金额（元）"
            rules={[{ required: true, message: "请输入金额" }]}
          >
            <InputNumber
              min={0.01}
              step={10}
              precision={2}
              style={{ width: "100%" }}
              placeholder="如 100"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
