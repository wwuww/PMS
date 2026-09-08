// 收押金 / 冻结预授权 弹窗表单（M32.18 T05）
import { useEffect } from "react";
import { Form, Input, InputNumber, Modal, Radio, Select, message } from "antd";
import { createDeposit } from "../../api/endpoints";
import type { DepositIn, DepositKind, DepositMethod } from "../../api/types";
import { useTenant } from "../../store/tenant";
import { yuanToCents } from "../../utils/format";
import { currentOperator } from "../../utils/permission";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

interface FormVals {
  kind: DepositKind;
  method: DepositMethod;
  amount: number;
  booking_id?: number | null;
  room_no?: string | null;
  ref_no?: string | null;
  note?: string | null;
}

const KIND_OPTIONS: { value: DepositKind; label: string }[] = [
  { value: "DEPOSIT", label: "收押金" },
  { value: "PREAUTH", label: "冻结预授权" },
];

const METHOD_OPTIONS: { value: DepositMethod; label: string }[] = [
  { value: "CASH", label: "现金" },
  { value: "WECHAT", label: "微信" },
  { value: "ALIPAY", label: "支付宝" },
  { value: "UNIONPAY", label: "银联" },
  { value: "STORE_VALUE", label: "储值" },
];

export default function DepositForm({ open, onClose, onCreated }: Props) {
  const { tenantCode, hotelId } = useTenant();
  const [form] = Form.useForm<FormVals>();

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({ kind: "DEPOSIT", method: "CASH", amount: undefined });
    }
  }, [open, form]);

  const onOk = async () => {
    if (!hotelId) {
      message.warning("请先在右上角选择门店");
      return;
    }
    const vals = await form.validateFields();
    const body: DepositIn = {
      hotel_id: Number(hotelId),
      kind: vals.kind,
      method: vals.method,
      amount: yuanToCents(vals.amount),
      booking_id: vals.booking_id ?? null,
      room_no: vals.room_no?.trim() || null,
      ref_no: vals.ref_no?.trim() || null,
      operator: currentOperator(),
      note: vals.note?.trim() || null,
    };
    try {
      const d = await createDeposit(tenantCode, body);
      message.success(`已开押单 ${d.deposit_no}`);
      onCreated();
      onClose();
    } catch (e: any) {
      message.error(e?.message || "开押失败");
    }
  };

  return (
    <Modal
      title="收押金 / 冻结预授权"
      open={open}
      onOk={onOk}
      onCancel={onClose}
      okText="提交"
      cancelText="取消"
      destroyOnClose
    >
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="kind"
          label="类型"
          rules={[{ required: true, message: "请选择类型" }]}
        >
          <Radio.Group options={KIND_OPTIONS} optionType="button" buttonStyle="solid" />
        </Form.Item>
        <Form.Item
          name="method"
          label="支付方式"
          rules={[{ required: true, message: "请选择方式" }]}
        >
          <Select options={METHOD_OPTIONS} placeholder="请选择" />
        </Form.Item>
        <Form.Item
          name="amount"
          label="金额（元）"
          rules={[
            { required: true, message: "请输入金额" },
            { type: "number", min: 0.01, message: "金额必须大于 0" },
          ]}
        >
          <InputNumber
            addonBefore="¥"
            min={0.01}
            precision={2}
            style={{ width: "100%" }}
            placeholder="0.00"
          />
        </Form.Item>
        <Form.Item name="booking_id" label="关联预订 ID（可选）">
          <InputNumber style={{ width: "100%" }} placeholder="留空表示挂账" min={1} />
        </Form.Item>
        <Form.Item name="room_no" label="房号（可选）">
          <Input placeholder="如 301" maxLength={16} />
        </Form.Item>
        <Form.Item name="ref_no" label="外部流水号（可选）">
          <Input placeholder="微信/支付宝等外部单号" maxLength={64} />
        </Form.Item>
        <Form.Item name="note" label="备注（可选）">
          <Input.TextArea rows={2} maxLength={255} />
        </Form.Item>
      </Form>
    </Modal>
  );
}