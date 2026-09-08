import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Empty,
  Input,
  List,
  Space,
  Switch,
  Select,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  ReloadOutlined,
  CheckOutlined,
  ExportOutlined,
  BellOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useTenant } from "../store/tenant";
import {
  listNotifications,
  readNotification,
  readAllNotifications,
  listHotels,
  getNotificationPreferences,
  updateNotificationPreferences,
  getNotificationSubscriptions,
  updateNotificationSubscriptions,
} from "../api/endpoints";
import type { Notification, NotificationPreference, NotificationSubscription, Hotel } from "../api/types";

const { Title, Text, Paragraph } = Typography;

// ref_type -> 中文分类标签
const REF_LABEL: Record<string, string> = {
  daily_report: "营业日报",
  chat_session: "AI客服转人工",
  booking: "预订",
  bill: "账单",
  bill_item: "账单明细",
  payment: "收款",
  alert: "风险预警",
  approval: "审批待办",
  task: "清扫工单",
  yield_recommendation: "收益建议",
  commission_reconciliation: "佣金对账",
};

const REF_COLOR: Record<string, string> = {
  daily_report: "blue",
  chat_session: "orange",
  booking: "cyan",
  bill: "purple",
  bill_item: "purple",
  payment: "green",
  alert: "red",
  approval: "gold",
  task: "geekblue",
  yield_recommendation: "magenta",
  commission_reconciliation: "volcano",
};

// ③ 通知分级标签
const LEVEL_LABEL: Record<string, string> = {
  critical: "紧急",
  normal: "普通",
  info: "提示",
};
const LEVEL_COLOR: Record<string, string> = {
  critical: "red",
  normal: "blue",
  info: "default",
};

// ④ 接收角色可选项（自由字符串；tags 模式允许自定义角色名）
const ROLE_OPTIONS = [
  { label: "店长", value: "store_manager" },
  { label: "前台", value: "front_desk" },
  { label: "夜审", value: "night_audit" },
];
const ROLE_LABEL: Record<string, string> = {
  store_manager: "店长",
  front_desk: "前台",
  night_audit: "夜审",
};
const roleText = (r: string) => ROLE_LABEL[r] || r;

/** 通知读状态变化后广播，供顶栏角标刷新 */
export const NOTIFY_CHANGED_EVENT = "pms:notifications-changed";

export function notifyChanged() {
  window.dispatchEvent(new Event(NOTIFY_CHANGED_EVENT));
}

// UX 增强：筛选条件持久化（刷新后恢复，避免重复选择）
type NotifFilters = { hotelId: string | null; refType: string | null; level: string | null; unreadOnly: boolean };
const NOTIF_FILTERS_KEY = "pms:notif-filters";
function loadNotifFilters(): NotifFilters {
  try {
    const raw = localStorage.getItem(NOTIF_FILTERS_KEY);
    if (raw) {
      const p = JSON.parse(raw) as Partial<NotifFilters>;
      return {
        hotelId: p.hotelId ?? null,
        refType: p.refType ?? null,
        level: p.level ?? null,
        unreadOnly: p.unreadOnly ?? false,
      };
    }
  } catch {
    /* 忽略损坏的本地存储 */
  }
  return { hotelId: null, refType: null, level: null, unreadOnly: false };
}

export default function NotificationsPage() {
  const { tenantCode } = useTenant();
  const navigate = useNavigate();
  const initialNotifFilters = loadNotifFilters();
  const [list, setList] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(initialNotifFilters.unreadOnly);
  const [busyId, setBusyId] = useState<string | null>(null);
  // ⑥ UX 增强：类型/级别筛选 + 分页（加载更多）
  const [refType, setRefType] = useState<string | null>(initialNotifFilters.refType);
  const [level, setLevel] = useState<string | null>(initialNotifFilters.level);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const PAGE = 20;
  // ③ 免打扰偏好
  const [dndEnabled, setDndEnabled] = useState(false);
  const [dndStart, setDndStart] = useState("22:00");
  const [dndEnd, setDndEnd] = useState("08:00");
  const [prefSaving, setPrefSaving] = useState(false);
  // ④ 角色订阅配置
  const [subs, setSubs] = useState<NotificationSubscription[]>([]);
  const [subSaving, setSubSaving] = useState(false);
  // UX 增强：按门店维度筛选（后端 hotel_id 已支持 list/count/read-all，前端补选择器）
  const [hotelId, setHotelId] = useState<string | null>(initialNotifFilters.hotelId);
  const [hotels, setHotels] = useState<Hotel[]>([]);

  const load = async (append: boolean) => {
    if (!tenantCode) return;
    setLoading(true);
    try {
      const nextOffset = append ? offset : 0;
      const data = await listNotifications(tenantCode, {
        unreadOnly,
        refType,
        level,
        hotelId: hotelId ? Number(hotelId) : null,
        limit: PAGE,
        offset: nextOffset,
      });
      setList((prev) => (append ? [...prev, ...data] : data));
      setOffset(nextOffset + data.length);
      setHasMore(data.length === PAGE);
    } catch (e: any) {
      message.error(e?.message || "消息加载失败");
    } finally {
      setLoading(false);
    }
  };

  const loadPref = async () => {
    if (!tenantCode) return;
    try {
      const p = await getNotificationPreferences(tenantCode);
      setDndEnabled(p.dnd_enabled);
      setDndStart(p.dnd_start);
      setDndEnd(p.dnd_end);
    } catch {
      /* 无偏好记录则用默认（关闭） */
    }
  };

  const savePref = async () => {
    if (!tenantCode) return;
    setPrefSaving(true);
    try {
      await updateNotificationPreferences(tenantCode, {
        dnd_enabled: dndEnabled,
        dnd_start: dndStart,
        dnd_end: dndEnd,
      });
      message.success("免打扰设置已保存");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setPrefSaving(false);
    }
  };

  // ④ 读取/保存角色订阅配置
  const loadSubs = async () => {
    if (!tenantCode) return;
    try {
      setSubs(await getNotificationSubscriptions(tenantCode));
    } catch {
      /* 忽略：前端用默认回落 */
    }
  };

  const saveSubs = async () => {
    if (!tenantCode) return;
    setSubSaving(true);
    try {
      const items = subs.map((s) => ({ ref_type: s.ref_type, recipients: s.recipients }));
      setSubs(await updateNotificationSubscriptions(tenantCode, items));
      message.success("接收人设置已保存");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setSubSaving(false);
    }
  };

  useEffect(() => {
    if (tenantCode) listHotels(tenantCode).then(setHotels).catch(() => {});
  }, [tenantCode]);

  useEffect(() => {
    load(false);
    loadPref();
    loadSubs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantCode, unreadOnly, refType, level, hotelId]);

  // UX 增强：筛选条件持久化到 localStorage（刷新后自动恢复）
  useEffect(() => {
    try {
      localStorage.setItem(
        NOTIF_FILTERS_KEY,
        JSON.stringify({ hotelId, refType, level, unreadOnly })
      );
    } catch {
      /* 忽略写入失败（如隐私模式禁用存储） */
    }
  }, [hotelId, refType, level, unreadOnly]);

  /** 点击消息：先标记已读（幂等），再跳转到 link 指向的业务页 */
  const open = async (n: Notification) => {
    if (busyId !== null) return;
    setBusyId(n.id);
    try {
      const updated = await readNotification(tenantCode, n.id);
      setList((prev) => prev.map((x) => (x.id === n.id ? { ...x, ...updated } : x)));
      notifyChanged();
      const target = updated.link || n.link;
      if (target) {
        navigate(target);
      } else {
        message.info("该消息无关联页面，已标记为已读");
        if (unreadOnly) load(false);
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "标记已读失败");
    } finally {
      setBusyId(null);
    }
  };

  const markRead = async (n: Notification) => {
    try {
      const updated = await readNotification(tenantCode, n.id);
      setList((prev) => prev.map((x) => (x.id === n.id ? { ...x, ...updated } : x)));
      notifyChanged();
      if (unreadOnly) load(false);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "标记已读失败");
    }
  };

  const markAll = async () => {
    try {
      const updated = await readAllNotifications(tenantCode, hotelId ? Number(hotelId) : null);
      message.success(`已标记 ${updated} 条为已读`);
      notifyChanged();
      load(false);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    }
  };

  const unread = list.filter((n) => !n.read_at).length;

  return (
    <div>
      <Card
        style={{ marginBottom: 16 }}
        styles={{ body: { display: "flex", alignItems: "center", justifyContent: "space-between" } }}
      >
        <Title level={4} style={{ margin: 0 }}>
          通知中心 <Badge count={unread} style={{ backgroundColor: "#fa8c16" }} />
        </Title>
        <Space wrap>
          <Select
            allowClear
            placeholder="全部类型"
            style={{ width: 140 }}
            value={refType}
            onChange={setRefType}
            options={Object.entries(REF_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select
            allowClear
            placeholder="全部级别"
            style={{ width: 120 }}
            value={level}
            onChange={setLevel}
            options={Object.entries(LEVEL_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select
            allowClear
            placeholder="全部门店"
            style={{ width: 160 }}
            value={hotelId}
            onChange={setHotelId}
            options={hotels.map((h) => ({ label: h.name, value: h.id }))}
          />
          <Space size={4}>
            <Text>仅看未读</Text>
            <Switch checked={unreadOnly} onChange={setUnreadOnly} />
          </Space>
          <Button icon={<CheckOutlined />} onClick={markAll} disabled={!unread}>
            全部已读
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => load(false)} loading={loading}>
            刷新
          </Button>
        </Space>
      </Card>

      <Card style={{ marginBottom: 16 }} title={<Space><BellOutlined /> 免打扰设置</Space>}>
        <Space wrap align="center">
          <Space size={4}>
            <Text>启用免打扰</Text>
            <Switch checked={dndEnabled} onChange={setDndEnabled} />
          </Space>
          <Space size={4}>
            <Text>安静时段</Text>
            <Input
              value={dndStart}
              onChange={(e) => setDndStart(e.target.value)}
              style={{ width: 96 }}
              placeholder="22:00"
            />
            <Text>至</Text>
            <Input
              value={dndEnd}
              onChange={(e) => setDndEnd(e.target.value)}
              style={{ width: 96 }}
              placeholder="08:00"
            />
          </Space>
          <Button type="primary" onClick={savePref} loading={prefSaving}>
            保存
          </Button>
          <Text type="secondary">
            安静时段内仅「紧急」通知（风险预警）仍触达，其余不计入未读角标
          </Text>
        </Space>
      </Card>

      <Card
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <TeamOutlined /> 接收人设置
          </Space>
        }
      >
        <Text type="secondary">配置每类通知推送给哪些角色；空列表表示该类型不推送。</Text>
        <div style={{ marginTop: 12, maxHeight: 320, overflowY: "auto" }}>
          {subs.map((s) => (
            <div
              key={s.ref_type}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "8px 0",
                borderBottom: "1px solid #f0f0f0",
              }}
            >
              <Tag color={REF_COLOR[s.ref_type] || "default"} style={{ minWidth: 88, textAlign: "center" }}>
                {s.label || s.ref_type}
              </Tag>
              <Select
                mode="tags"
                style={{ flex: 1 }}
                placeholder="选择或输入接收角色"
                value={s.recipients}
                options={ROLE_OPTIONS}
                onChange={(vals: string[]) =>
                  setSubs((prev) =>
                    prev.map((x) => (x.ref_type === s.ref_type ? { ...x, recipients: vals } : x))
                  )
                }
              />
            </div>
          ))}
        </div>
        <Space style={{ marginTop: 12 }}>
          <Button type="primary" onClick={saveSubs} loading={subSaving}>
            保存接收人
          </Button>
          <Text type="secondary">保存后，新推送按此配置派发（影响后续消息，不改历史）</Text>
        </Space>
      </Card>

      <Card loading={loading}>
        {list.length === 0 ? (
          <Empty description="暂无消息" />
        ) : (
          <>
            <List
            itemLayout="horizontal"
            dataSource={list}
            renderItem={(n) => {
              const isUnread = !n.read_at;
              return (
                <List.Item
                  onClick={() => open(n)}
                  style={{
                    cursor: "pointer",
                    opacity: isUnread ? 1 : 0.62,
                    background: isUnread ? "#fffbe6" : undefined,
                    paddingLeft: 8,
                    paddingRight: 8,
                    borderRadius: 6,
                  }}
                  actions={[
                    n.link ? (
                      <Tooltip title={`跳转到 ${n.link}`}>
                        <Text type="secondary">
                          <ExportOutlined /> 查看
                        </Text>
                      </Tooltip>
                    ) : (
                      <Text type="secondary">无跳转</Text>
                    ),
                    isUnread ? (
                      <Button
                        type="link"
                        size="small"
                        icon={<CheckOutlined />}
                        loading={busyId === n.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          markRead(n);
                        }}
                      >
                        标记已读
                      </Button>
                    ) : (
                      <Text type="secondary">已读</Text>
                    ),
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        {n.ref_type && (
                          <Tag color={REF_COLOR[n.ref_type] || "default"}>
                            {REF_LABEL[n.ref_type] || n.ref_type}
                          </Tag>
                        )}
                        {n.level && (
                          <Tag color={LEVEL_COLOR[n.level] || "default"}>
                            {LEVEL_LABEL[n.level] || n.level}
                          </Tag>
                        )}
                        {n.muted && <Tag color="default">免打扰</Tag>}
                        {n.recipients && n.recipients.length > 0 && (
                          <Tag color="geekblue" style={{ marginRight: 4 }}>
                            接收：{n.recipients.map(roleText).join("、")}
                          </Tag>
                        )}
                        <Text strong={isUnread}>{n.title}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {n.channel} ·{" "}
                          {n.created_at?.slice(0, 19).replace("T", " ") || "—"}
                        </Text>
                        {isUnread && <Badge status="processing" text="未读" />}
                      </Space>
                    }
                    description={<Paragraph style={{ margin: 0 }}>{n.body}</Paragraph>}
                  />
                </List.Item>
              );
            }}
          />
          <div style={{ textAlign: "center", paddingTop: 12 }}>
            <Button onClick={() => load(true)} loading={loading} disabled={!hasMore}>
              {hasMore ? "加载更多" : "没有更多了"}
            </Button>
          </div>
          </>
        )}
      </Card>
    </div>
  );
}
