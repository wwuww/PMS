# M30 性能与稳定性 —— 全量性能审计报告

> 审计人：架构师（高见远） · 性质：纯研究，未修改任何业务代码
> 仓库根：`F:\PMS\pms` · 基线 commit 工作区时间 2026-09-08
> 目标规模：**1 万家门店 / 100 万间客房**

---

## 0. 结论摘要

| 维度 | 现状 | 目标缺口 |
|---|---|---|
| 表总数 | **62** | — |
| 多列索引总数 | 28，其中**唯一约束（业务键）占 19 条**，真正的性能复合索引仅 **9 条** | 见 A 节，建议新增 **14 条** |
| `selectinload` / `joinedload` 使用 | **0 处**（全仓 `grep` 为空） | 见 B 节 |
| 确认的 N+1 站点 | **23 处**（其中 P0 级 4 处） | 见 B 节 |
| 无 limit 的列表端点 | **51 / 54**（仅 `list_bookings`/`list_bills`/`query_audit_logs` 有 `MAX_LIST_ROWS` 护栏） | 见 D1 |
| 读缓存使用点 | **2 处**（`rooms:` / `dashboard:`） | 见 C 节，建议扩到 6 个域 |
| 连接池配置 | **仅 `pool_pre_ping=True`，无任何池参数** | 见 D3 |

**三条最高优先级结论（按收益）：**

1. **`BillItem.description.like("%{date}%")`**（`night_audit_service.py:442`）前导通配符使任何索引失效，且在夜审主循环里每间在住房执行一次 → 这是夜审「≤5 分钟」达标的最大障碍，**不是加索引能解决的**（D4）。
2. **夜审主循环 N+1**（`night_audit_service.py:95-140`）：每间在住房 ≈ 14 次查询 + 1 次事务提交，300 间在住房 ≈ 4200 查询 + 300 次 COMMIT（B1 / D5）。
3. **`bills` 缺 `(tenant_id, booking_id, status)` 索引**：全仓 6 处「查某预订的在开账单」是入住/加账/换房/联房/退房的必经校验（A4）。

---

# A. 索引缺口审计

## 通用原则（本次审计统一遵守）

- `tenant_id` 几乎出现在所有查询中，且是 ShardingSphere 分片键 → **所有复合索引以 `tenant_id` 为前导列**（唯一例外见 D6 待确认项）。
- 索引不是越多越好：`audit_logs`、`bill_items`、`payments` 为写入最频繁的三张表，新增索引会放大写成本，故只加覆盖高频查询且区分度高的。
- 标注：`【高】`= 覆盖高频查询且区分度高，建议本迭代做；`【中】`= 收益明确但可下迭代；`【缓】`= 暂缓。

---

## A1. `rooms`（目标 100 万行）

**现有索引**
| 类型 | 列 |
|---|---|
| 单列 | `tenant_id`(TenantMixin)、`hotel_id`(`room.py:24`)、`state`(`room.py:29`) |
| 唯一 | `(tenant_id, room_no)` (`room.py:22`) |

**查询证据（grep 实测）**

| 条件 | 出现处 | 频次评估 |
|---|---|---|
| `(tenant_id)` 全量，**无 limit** | `routes.py:628` | 房态盘首屏，命中缓存时免除，miss 时百万级全扫 |
| `(tenant_id, hotel_id, state.in_([VACANT_CLEAN, VACANT_DIRTY]))` | `room_service.py:129` | 智能排房，每次排房调用 |
| `(hotel_id, state == OCCUPIED)` | `night_audit_service.py:77` | 夜审每店每次 |
| `(tenant_id, room_no)` | `room_service.py:108`、`booking_service.py:423`、`housekeeping_service.py:87`、`housekeeping_service.py:156`、`reception_service.py:306/374/551`、`routes.py:1164/4778`、`night_audit_service.py:358` | **13 处**（已被 UQ 覆盖） |
| `(hotel_id, room_no)` | `night_audit_service.py:358` | 已被 UQ 部分覆盖 |
| `group_by(state) where hotel_id` | `night_audit_service.py:371` | 夜审 2 次/店 |
| `count() where hotel_id` | `night_audit_service.py:420`、`analytics_service.py:40` | 见房量聚合 |
| `(tenant_id, room_type_id) count()` | `price_service.py:81` | **房型房量，建单每晚调用** |
| `(tenant_id, floor == str)` | `housekeeping_service.py:200` | 楼层过滤，可选条件 |

**建议新增**
```python
# app/models/room.py  Room.__table_args__
__table_args__ = (
    UniqueConstraint("tenant_id", "room_no"),
    Index("ix_rooms_tenant_hotel_state", "tenant_id", "hotel_id", "state"),  # 【高】
    Index("ix_rooms_tenant_type", "tenant_id", "room_type_id"),              # 【高】
)
```
- `ix_rooms_tenant_hotel_state` 一次覆盖 4 类查询：排房（`room_service.py:129`）、夜审在住房（`night_audit_service.py:77`）、房态分布 `group_by`（`night_audit_service.py:371`，可作覆盖索引）、房态盘按店过滤。**建议排在第一位实施。**
- `ix_rooms_tenant_type` 覆盖 `price_service.py:81` 的房型房量 COUNT。
- `【缓】floor` 索引：`housekeeping_service.py:200` 为可选过滤条件且区分度低。
- 注意：`(tenant_id, room_no)` UQ 已覆盖 13 处按房号查询，**不要**再建单列 `room_no`。

---

## A2. `room_types`（每租户 < 100 行）

**现有索引**：`tenant_id` 单列 + UQ `(tenant_id, code)`

**查询证据**：全部为 `where(tenant_id)` 全量拉取 —— `routes.py:567`、`ota_service.py:240`、`ota_service.py:326`、`chatbot_service.py:247`、`mp_service.py:38`（共 6 处）。

**结论：无需新增复合索引。** `tenant_id` 单列已足够（结果集 <100 行）。

> **附带缺陷（非索引）**：`chatbot_service.py:247`
> ```python
> select(RoomType).where(RoomType.tenant_id == tenant_id, RoomType.id == RoomType.id)
> ```
> `RoomType.id == RoomType.id` 是恒真式，且未按 `hotel_id` 过滤 → 拉全租户房型。应改为修 bug（按 hotel 过滤），而非加索引。`【中】`

---

## A3. `bookings`（目标千万~亿级，增长最快）

**现有索引**
| 类型 | 列 |
|---|---|
| 单列（8） | `tenant_id`、`hotel_id`、`room_type_id`、`external_channel`、`external_ref`、`chat_session_id`、`status`、`link_group_id` |
| 复合 | `ix_bookings_hotel_checkin (hotel_id, check_in_date)` (`booking.py:33`) |

**查询证据（grep 实测：`Booking.tenant_id` 26 处、`status` 21 处、`hotel_id` 13 处、`room_no` 12 处）**

| 条件 | 出现处 |
|---|---|
| `(tenant_id, status=CHECKED_IN, room_no)` | `booking_service.py:160`（入住查重）、`cashier_service.py:326`（联房结转）、`reception_service.py:480`（联房） |
| `(tenant_id, status=CHECKED_IN, room_no.in_)` | `anomaly_service.py:154` |
| `(hotel_id, room_no, status=CHECKED_IN)` | `night_audit_service.py:97` ← **夜审主循环 N+1** |
| `(hotel_id, status=CREATED, check_in_date < X)` | `night_audit_service.py:332`（NoShow） |
| `(hotel_id, check_in_date==X, status)` | `night_audit_service.py:69-70`（到店/离店计数） |
| `(tenant_id, room_no)` + `order_by(id desc) limit 1` | `reception_service.py:528`（单客上下文，前台最高频） |
| `(tenant_id, guest_phone)` + `order_by(id desc) limit 1` | `reception_service.py:536` |
| `(tenant_id, room_no.isnot(None), guest_phone\|id_doc_no)` + `order_by(id desc) limit 20` | `room_service.py:152`（排房历史偏好） |
| `(tenant_id, room_type_id, status.in_, check_in<=d, check_out>d, stay_type!=hourly)` | `price_service.py:88` ← **房量聚合，建单每晚 + OTA 每次查房** |
| `(tenant_id, link_group_id, is_link_master)` | `reception_service.py:458/468` |
| `(tenant_id, hotel_id) group_by channel` | `analytics_service.py:172` |

**建议新增**
```python
# app/models/booking.py  Booking.__table_args__
__table_args__ = (
    Index("ix_bookings_hotel_checkin", "hotel_id", "check_in_date"),            # 已存在
    Index("ix_bookings_tenant_status_room", "tenant_id", "status", "room_no"),  # 【高】
    Index("ix_bookings_hotel_room_status", "hotel_id", "room_no", "status"),    # 【高】
    Index("ix_bookings_tenant_room_id", "tenant_id", "room_no", "id"),          # 【高】
    Index("ix_bookings_avail", "tenant_id", "room_type_id", "status",
          "check_in_date", "check_out_date"),                                   # 【中】
)
```
- `ix_bookings_tenant_status_room` 覆盖「按房号查在住单」四连（`booking_service.py:160`、`cashier_service.py:326`、`reception_service.py:480`、`anomaly_service.py:154`）—— 入住/联房/结转的必经校验，**收益极高**。
- `ix_bookings_hotel_room_status` 直接服务夜审主循环 `night_audit_service.py:96`（须与 B1 批量化同时做）。
- `ix_bookings_tenant_room_id` 让 `reception_service.py:528` 的 `order_by(id desc) limit 1` 走索引尾部扫描，免 filesort。
- `ix_bookings_avail` 服务 `price_service.py:88`。**注意**：`check_out_date > date` 是范围条件，索引最多用到 `check_in_date`；`stay_type != 'hourly'` 区分度 <5%，放末位仅作过滤不参与定位。
- `【缓】` `external_channel/external_ref`：OTA 回链 QPS 低，单列索引已够。
- **冲突提示**：`ix_bookings_hotel_checkin` 无 `tenant_id` 前导，若分片键为 `tenant_id` 会跨片广播 → 建议改造为 `(tenant_id, hotel_id, check_in_date)`（见 D6）。

---

## A4. `bills`（目标千万级）

**现有索引**：单列 `tenant_id`、`hotel_id`、`booking_id`、`ar_account_id` + UQ `(tenant_id, bill_no)`

**查询证据（`Bill.status` 12 处、`booking_id` 11 处）**

| 条件 | 出现处 |
|---|---|
| `(tenant_id, booking_id, status=="OPEN")` | `booking_service.py:187`（入住开账）、`booking_service.py:313`（换房）、`reception_service.py:191`（单客 folio）、`reception_service.py:337`（open_folio）、`cashier_service.py:352/364`（联房结转） |
| `(hotel_id, status=="OPEN")` count + sum | `night_audit_service.py:386` |
| `(booking_id, status=="OPEN")`（无 tenant） | `night_audit_service.py:426` ← 夜审主循环 |
| `(tenant_id, source)` | `routes.py:1692` |
| `(tenant_id, ar_account_id)` | `ar_service.py:132` |

**建议新增**
```python
# app/models/billing.py  Bill.__table_args__
__table_args__ = (
    UniqueConstraint("tenant_id", "bill_no"),
    Index("ix_bills_tenant_booking_status", "tenant_id", "booking_id", "status"),  # 【高】
    Index("ix_bills_tenant_hotel_status", "tenant_id", "hotel_id", "status"),      # 【高】
)
```
> `ix_bills_tenant_booking_status` 是**本次审计收益最高的单条索引**：把 6 处「查某预订的在开账单」从「单列 `booking_id` 扫描 + 回表过滤 status」变为近唯一命中。每笔入住、每次加账、每次换房、每次退房都走。

---

## A5. `bill_items`（目标亿级，写入最频繁）

**现有索引**：单列 `tenant_id`、`bill_id`

**查询证据**

| 条件 | 出现处 |
|---|---|
| `(bill_id, type=="ROOM_CHARGE", description LIKE '%{date}%')` count | `night_audit_service.py:440` ← **夜审主循环，每房一次** |
| `where bill_id IN (...)` | 由 `Bill.items` 的 `lazy="selectin"` 触发（`billing.py:34`） |
| `join Bill on (hotel_id, status=SETTLED)` + `type=MISC` sum | `night_audit_service.py:451` |
| `join Bill` + `(created_by, created_at >= X)` | `shift_service.py:86`（交班应收） |

**建议新增**
```python
# app/models/billing.py
class BillItem(...):
    __table_args__ = (
        Index("ix_bill_items_bill_type", "bill_id", "type"),   # 【高】
        Index("ix_bill_items_created", "created_at"),          # 【中】
    )
```
> ⚠️ **真正的瓶颈不是索引**：`night_audit_service.py:442` 的 `description.like(f"%{business_date}%")` 前导通配符**无法使用任何索引**，在夜审主循环里对每间在住房做一次 `bill_items`（亿级）全表扫描。必须改数据模型，见 **D4**。

---

## A6. `payments`（目标亿级）

**现有索引**：单列 `tenant_id`、`bill_id`

**查询证据**：`Payment.bill_id` 13 处（主要由 `Bill.payments` 的 `selectin` 触发 `WHERE bill_id IN (...)`，已覆盖）；`join Bill` + `(method, created_by, created_at >= X)` → `shift_service.py:45`（现金流）、`shift_service.py:62`（实收）。

**建议新增**
```python
Index("ix_payments_bill_created", "bill_id", "created_at"),   # 【中】
Index("ix_payments_shift_agg", "created_by", "created_at"),   # 【中】交班三口径
```
交班是每天每班必做；`created_by` 区分度中等（收银员数），配合 `created_at` 范围可显著缩小扫描。

---

## A7. `audit_logs`（**增长最快的表**，每次房态流转/订单状态变更都写）

**现有索引**：单列 `tenant_id`、`hotel_id`、`action`、`resource_type`

**查询证据**

| 条件 | 出现处 |
|---|---|
| `(tenant_id, resource_type=="booking", resource_id==str(id))` + `order_by(id desc) limit 10` | `reception_service.py:561` ← **前台每次点开客人** |
| 同上 `limit 200` | `routes.py:694`（登记单操作日志） |
| `(tenant_id, [action, resource_type, hotel_id, actor, result])` + `order_by(id desc) limit N` | `routes.py:2484`（审计查询/导出） |

**建议新增**
```python
# app/models/audit.py
class AuditLog(...):
    __table_args__ = (
        Index("ix_audit_tenant_res_id", "tenant_id", "resource_type", "resource_id", "id"),  # 【高】
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),                          # 【高】
    )
```
- `ix_audit_tenant_res_id` 让 `reception_service.py:561` 的 `limit 10` 直接走索引尾部扫描（免 filesort + 免回表过滤）。**当前是 `tenant_id` 单列 → 扫该租户全部审计行（千万级）再过滤再排序。**
- 写放大提示：新增 2 个索引约增加 15–20% 写成本 → **必须配套按月分区/归档**（见「需要澄清」#3）。
- `【中】` 可考虑删除 `hotel_id` 单列索引（被 `tenant_id` 前缀覆盖），改由 `(tenant_id, hotel_id, created_at)` 承担。

---

## A8. `housekeeping_tasks`

**现有索引**：单列 `tenant_id`、`hotel_id`、`room_no`、`status`

**查询证据**

| 条件 | 出现处 |
|---|---|
| `(tenant_id, [hotel_id, status, task_type, assignee])` + `order_by(id desc)` **无 limit** | `housekeeping_service.py:187-209` |
| `(tenant_id, hotel_id, status=="DONE", done_at.isnot(None))` | `housekeeping_service.py:253`（员工绩效，拉全量后 Python 过滤日期） |
| `(tenant_id, hotel_id, status.in_([PENDING, ASSIGNED]))` | `housekeeping_service.py:293`（超时计数，拉全量行内存计数） |
| `(tenant_id, task_type=="MAINTENANCE", status.in_, created_at>=X, room_no.in_)` | `room_service.py:180`（排房降权） |

**建议新增**
```python
# app/models/app10.py  HousekeepingTask
__table_args__ = (
    Index("ix_hk_tenant_hotel_status", "tenant_id", "hotel_id", "status"),              # 【高】
    Index("ix_hk_tenant_type_status_created", "tenant_id", "task_type", "status",
          "created_at"),                                                                 # 【中】
)
```
`list_tasks` 是保洁/主管**首页高频**接口且当前无 limit（见 D1）。第一条索引同时服务 `187`/`253`/`293` 三处。

---

## A9. `pos_orders`

**现有索引**：单列 `tenant_id`、`hotel_id`、`table_id`、`booking_id`

**查询证据**
| 条件 | 出现处 |
|---|---|
| `(tenant_id, hotel_id, [status]) order_by(id desc)` **无 limit** | `fnb_service.py:193` |
| `(tenant_id, hotel_id, status=="settled", created_at between)` | `fnb_service.py:374`（餐饮营业报表） |
| `(tenant_id)` 导出 | `analytics_service.py:553` |

**建议新增**
```python
Index("ix_pos_orders_tenant_hotel_status_created",
      "tenant_id", "hotel_id", "status", "created_at"),   # 【高】
```
一个索引覆盖 `list_orders` 与营业报表两处；雪花 ID 与 `created_at` 同向递增，天然有序。

---

## A10. `pos_order_items`

**现有索引**：单列 `tenant_id`、`order_id`

**查询证据**
| 条件 | 出现处 |
|---|---|
| `where order_id == X` | `routes.py:4231`（`_load_order_items`） |
| `join PosOrder` + `(kds_status.in_, voided==0)` `order_by(id asc)` **无 limit** | `fnb_service.py:471`（KDS 厨房屏） |
| `join PosOrder` 报表 | `fnb_service.py:387` |

**建议新增**
```python
Index("ix_pos_items_order_kds", "order_id", "kds_status"),   # 【中】
```
`kds_status` 仅 3 值，区分度低，单独建索引意义有限。**KDS 的真正瓶颈是 B2 的 N+1（逐行 `session.get(PosOrder)`），索引优先级低于 N+1 修复。**

---

## A11. `guests`

**现有索引**：单列 `tenant_id`、`hotel_id`、`phone`、`member_id` + UQ `(tenant_id, phone)`

**查询证据**
| 条件 | 出现处 |
|---|---|
| `(tenant_id, phone)` | `guest_service.py:97`（每次接待） |
| `(tenant_id, id_no)` | `guest_service.py:161` ← **`id_no` 无索引，全表扫描** |
| `(tenant_id, name\|phone\|id_no LIKE '%kw%')` | `guest_service.py:114` ← 前导通配，无法走索引 |
| `(tenant_id, hotel_id) order_by(id desc) limit` | `guest_service.py:117` |
| `(tenant_id, member_id.in_)` | `routes.py:1533`（批量，正例） |

**建议新增**
```python
# app/models/guest.py
__table_args__ = (
    UniqueConstraint("tenant_id", "phone"),
    Index("ix_guests_tenant_idno", "tenant_id", "id_no"),           # 【高】
    Index("ix_guests_tenant_hotel_id", "tenant_id", "hotel_id", "id"),  # 【中】
)
```
`id_no` 当前**零索引**是明确缺陷（3 处查询）。`LIKE '%kw%'` 建议短期改前缀匹配 `kw%`（可走 `phone`/`name` 索引），长期上全文检索。

---

## A12. `members`

**现有索引**：UQ `(tenant_id, phone)` + 单列 `tenant_id`

**结论：无需新增。** `member_service.py:33` 与 `routes.py:1533` 均被 UQ 覆盖。

---

## A13. `shift_handovers`

**现有索引**：单列 `tenant_id`、`hotel_id`

**查询证据**：`(tenant_id, [hotel_id])` **无 limit 无 order** → `shift_service.py:125`

**建议新增**
```python
Index("ix_shift_tenant_hotel_status_id", "tenant_id", "hotel_id", "status", "id"),  # 【中】
```
交班列表高频查询「当前 OPEN 班次」，而 `status` 当前无索引。

---

## A14. `daily_reports`

**现有索引**：单列 `tenant_id`、`hotel_id`

**查询证据**
| 条件 | 出现处 |
|---|---|
| `(tenant_id, hotel_id, business_date between)` | `analytics_service.py:70`+`73`（dashboard） |
| `(tenant_id, hotel_id) order_by(id desc) limit 1` | `night_audit_service.py:296`、`group_service.py:137` ← **跨店看板 N+1** |
| `(tenant_id, [hotel_id])` 无 limit | `routes.py:1942` |

**建议新增**
```python
Index("ix_daily_reports_tenant_hotel_date",
      "tenant_id", "hotel_id", "business_date"),   # 【高】
```
同时服务 dashboard 的范围扫描与 `ORDER BY id DESC LIMIT 1`（`business_date` 与雪花 `id` 同向，MySQL 可索引倒扫 + limit 提前终止）。

---

## A15. 其他高收益补充（非 14 张重点表）

| 表 | 建议 | 证据 | 收益 |
|---|---|---|---|
| `business_days` | `Index("ix_bd_hotel_status_date", "hotel_id", "status", "business_date")` | `night_audit_scheduler.py:70-77`（`hotel_id + business_date<=X + status.in_`） | 【中】 |
| `room_state_events` | `Index("ix_rse_room_trigger_id", "room_id", "trigger", "id")` | `room_service.py:34`（`room_id+trigger` order by id desc limit 1）、`routes.py:669`、`routes.py:645`（**无 limit**） | 【中】 |
| `notifications` | `Index("ix_notif_tenant_recipient_read", "tenant_id", "recipient", "read_at")` | 未读角标高频（`web/src/layout/AppLayout.tsx:252` 60s 轮询） | 【中】 |
| `price_calendar` | **无需新增** | UQ `(tenant_id, room_type_id, date)` 已完美覆盖 `price_service.py:23` | — |

---

## A 节汇总

| 收益 | 条数 | 明细 |
|---|---|---|
| **【高】** | **7** | `ix_rooms_tenant_hotel_state`、`ix_rooms_tenant_type`、`ix_bookings_tenant_status_room`、`ix_bookings_hotel_room_status`、`ix_bookings_tenant_room_id`、`ix_bills_tenant_booking_status`、`ix_bills_tenant_hotel_status`、`ix_audit_tenant_res_id`、`ix_audit_tenant_created`、`ix_hk_tenant_hotel_status`、`ix_pos_orders_tenant_hotel_status_created`、`ix_guests_tenant_idno`、`ix_daily_reports_tenant_hotel_date` |
| **【中】** | **7** | `ix_bookings_avail`、`ix_bill_items_created`、`ix_payments_bill_created`、`ix_payments_shift_agg`、`ix_hk_tenant_type_status_created`、`ix_pos_items_order_kds`、`ix_guests_tenant_hotel_id`、`ix_shift_tenant_hotel_status_id`、`ix_bd_hotel_status_date`、`ix_rse_room_trigger_id`、`ix_notif_tenant_recipient_read` |
| **【缓】** | — | `rooms.floor`、`bookings.external_*` |

---

# B. N+1 查询审计

> 检测方法：`for/async for` 语句块后 14 行内出现 `await session.execute(...)` 或 `await session.get(...)`，全仓命中 **26 处**，人工复核确认 **23 处**为真实 N+1。

## B1. 【P0】夜审主循环 —— 全仓最严重

**位置**：`app/services/night_audit_service.py:95-140`

**当前每间在住房的查询次数**

| 行号 | 操作 | 查询数 |
|---|---|---|
| `96-104` | `select(Booking)` where hotel+room_no+status | 1 |
| `117` | `ps.resolve()` → `get(RoomType)` + `select(PriceCalendar)` + `select(RateCode)` | 3 |
| `122` | `_bill_for_booking()` → `select(Bill)` + 3 个 `selectin` 关系（items/payments/adjustments，见 `billing.py:34/37/40`） | **4** |
| `123` | `_has_room_charge_today()` → `select(count)` with `LIKE '%date%'` | 1（全表扫描） |
| `126` | `ms.get_by_phone()` | 1 |
| `137` | `rs.transition()` → `select(RoomStateEvent)` + insert ×2 + **COMMIT** + `refresh` + 缓存失效 | ≈4 |
| **合计** | | **≈ 14 次查询 + 1 次事务提交 / 房** |

300 间在住房 → **≈ 4200 次查询 + 300 次 COMMIT**。

**改写方案**
```python
# ① 一次性取全部在住房的在住单（替换 :96 的逐房查询）
room_nos = [r.room_no for r in occupied_rooms]
bk_rows = await self.session.execute(
    select(Booking).where(
        Booking.hotel_id == hotel_id,
        Booking.status == BookingStatus.CHECKED_IN.value,
        Booking.room_no.in_(room_nos),
    )
)
booking_by_room: dict[str, Booking] = {}
for b in bk_rows.scalars():
    if b.check_in_date <= business_date < b.check_out_date:
        booking_by_room[b.room_no] = b          # 覆盖营业日的优先
    else:
        booking_by_room.setdefault(b.room_no, b)

# ② 批量解析房价（替换 :117 的逐房 resolve）
rt_ids = {r.room_type_id for r in occupied_rooms}
rt_map = {rt.id: rt for rt in (await self.session.execute(
    select(RoomType).where(RoomType.id.in_(rt_ids))
)).scalars()}
cal_map = {(c.room_type_id, c.date): c.price for c in (await self.session.execute(
    select(PriceCalendar).where(
        PriceCalendar.tenant_id == tenant_id,
        PriceCalendar.room_type_id.in_(rt_ids),
        PriceCalendar.date == business_date,
    )
)).scalars()}

# ③ 批量取/建 OPEN 账单（替换 :122）
ids = [b.id for b in booking_by_room.values()]
bill_map = {b.booking_id: b for b in (await self.session.execute(
    select(Bill).where(Bill.booking_id.in_(ids), Bill.status == "OPEN")
)).scalars()}

# ④ 批量判重（替换 :123 的 LIKE，依赖 D4 新增 business_date 列）
charged = {row[0] for row in (await self.session.execute(
    select(BillItem.bill_id).where(
        BillItem.bill_id.in_([b.id for b in bill_map.values()]),
        BillItem.type == "ROOM_CHARGE",
        BillItem.business_date == business_date,
    )
)).all()}
```
**预期**：`≈14N` → 固定 **≈6 次查询**（+ 1 次批量提交）。300 间房：4200 → <20。**收益：极高**。

> **配套必改**：`room_service.py:82` 的 `transition()` 内部 `await self.session.commit()` —— 在夜审循环里每房提交一次事务，既是性能问题也是正确性问题（中途失败无法回滚整个营业日）。见 D5。

---

## B2. 【P0】KDS 厨房出单屏 —— 15s 轮询接口

**位置**：`app/services/fnb_service.py:471-490`（前端 `web/src/pages/Kds.tsx:61` 每 15s 轮询）

```python
rows = list((await self.session.execute(stmt)).scalars().all())   # N 行
for it in rows:
    order = await self.session.get(PosOrder, it.order_id)          # ← N 次
    if order is not None and order.table_id:
        tbl = await self.session.get(DiningTable, order.table_id)  # ← 最多再 N 次
```
50 个待做菜 → **≈100 次查询 / 次轮询**。

**改写方案**（单次 JOIN 取齐）
```python
stmt = (
    select(PosOrderItem, PosOrder.room_no, PosOrder.guest_name,
           PosOrder.table_id, DiningTable.table_no)
    .join(PosOrder, PosOrderItem.order_id == PosOrder.id)
    .outerjoin(DiningTable, PosOrder.table_id == DiningTable.id)
    .where(PosOrder.tenant_id == tenant_id, PosOrder.hotel_id == hotel_id,
           PosOrderItem.kds_status.in_(states), PosOrderItem.voided == 0)
    .order_by(PosOrderItem.id.asc())
    .limit(200)                       # 同时补上 D1 的 limit 护栏
)
```
**预期**：100 → 1 次。**收益：高**（且是轮询接口，放大效应显著）。

---

## B3. 【P0】`list_ar_bills` 冗余 refresh

**位置**：`app/api/routes.py:1857` + `app/api/routes.py:4304-4306`

```python
return [await _bill_with_items(b, session) for b in bills]

async def _bill_with_items(bill: Bill, session: AsyncSession) -> Bill:
    await session.refresh(bill, attribute_names=["items", "payments", "adjustments"])
    return bill
```
`refresh` 对 3 个 `selectin` 关系各发一次 SELECT → **3N 次**。100 张账单 = 300 次。

**关键点**：`Bill.items/payments/adjustments` 已是 `lazy="selectin"`（`billing.py:34/37/40`），`select(Bill)` 时**已加载完毕**；且 session 为 `expire_on_commit=False`（`session.py:46`），属性未过期 → **refresh 纯属多余**。

**改写**：直接 `return bills`（1 行改动）。
**预期**：3N → 0。**收益：高（成本极低）**。

---

## B4. 【P0】建单逐晚循环

**位置**：`app/services/booking_service.py:85-88`（房量）+ `99-102`（房价）；同类 `extend_stay` 在 `247-257`

```python
for nd in nights:
    avail = await self.price.availability(tenant_id, room_type_id, nd)   # 2 次 COUNT
...
for nd in nights:
    total += await self.price.resolve(room_type_id, nd, ...)             # 3 次查询
```
`availability` = 2 次 COUNT（`price_service.py:80/87`），`resolve` = `get(RoomType)` + `select(PriceCalendar)` + `select(RateCode)`。
**7 晚住宿 = 5 × 7 = 35 次查询 / 单笔建单**。

**改写方案**
```python
# ① 房量：一次聚合该房型在住期内的全部占用，内存展开逐晚
rows = await self.session.execute(
    select(Booking.check_in_date, Booking.check_out_date, func.count())
    .where(Booking.tenant_id == tenant_id,
           Booking.room_type_id == room_type_id,
           Booking.status.in_([BookingStatus.CREATED.value,
                               BookingStatus.CHECKED_IN.value]),
           Booking.stay_type != "hourly",
           Booking.check_in_date < check_out_date,
           Booking.check_out_date > check_in_date)
    .group_by(Booking.check_in_date, Booking.check_out_date)
)
occupied: dict[str, int] = {}
for ci, co, c in rows:
    for nd in _nights(ci, co):
        occupied[nd] = occupied.get(nd, 0) + c

# ② 房价：一次取住期内全部日历覆盖
cals = await self.session.execute(
    select(PriceCalendar).where(
        PriceCalendar.tenant_id == tenant_id,
        PriceCalendar.room_type_id == room_type_id,
        PriceCalendar.date.in_(nights),
    )
)
```
**预期**：35 → 3 次。**收益：高**（入住/下单是最高频写路径）。

---

## B5. 【P1】跨店看板三处同构 N+1

| 位置 | 当前 | 模式 |
|---|---|---|
| `night_audit_service.py:273-300` (`night_audit_board`) | **3N** | 逐店：最新 `BusinessDay` + `COUNT(SUSPENDED)` + 最新 `DailyReport` |
| `analytics_service.py:127-134` (`hotel_ranking`) | **2N** | 逐店：`COUNT(rooms)` + `select(DailyReport)` |
| `group_service.py:135-142` (`hq_dashboard`) | **2N** | 逐店：最新 `DailyReport` + `COUNT(rooms)` |

100 家店 → 200~300 次查询。

**改写方案（以「每店最新日报」为例）**
```python
latest = (
    select(DailyReport.hotel_id, func.max(DailyReport.business_date).label("bd"))
    .where(DailyReport.tenant_id == tenant_id)
    .group_by(DailyReport.hotel_id)
).subquery()
rows = await self.session.execute(
    select(DailyReport)
    .join(latest, (DailyReport.hotel_id == latest.c.hotel_id)
                & (DailyReport.business_date == latest.c.bd))
    .where(DailyReport.tenant_id == tenant_id)
)
# 房量一次聚合，替换逐店 COUNT
rooms_cnt = dict((await self.session.execute(
    select(Room.hotel_id, func.count())
    .where(Room.tenant_id == tenant_id).group_by(Room.hotel_id)
)).all())
```
**预期**：3N → 3 次固定。100 店：300 → 3。**收益：高**（配合 C7 缓存效果更佳）。

---

## B6. 【P1】漏收检测

**位置**：`app/services/anomaly_service.py:154-172`
```python
for booking in rows.scalars():
    count = await self.session.execute(
        select(func.count()).select_from(Bill).where(Bill.booking_id == booking.id))
```
**改写**：单次反连接
```python
q = (select(Booking)
     .outerjoin(Bill, (Bill.booking_id == Booking.id) & (Bill.tenant_id == tenant_id))
     .where(Booking.tenant_id == tenant_id, Booking.hotel_id == hotel_id,
            Booking.status == "checked_in", Bill.id.is_(None)))
```
**预期**：N+1 → 1。**收益：中**（夜审后跑一次）。

---

## B7. 【P1】批量操作 N+1（5 处）

| 位置 | 当前 | 改写 |
|---|---|---|
| `housekeeping_service.py:218` (`batch_assign`) | `for tid: session.get(...)`，且内部 `assign()` 再 `select(Room)` → **2N** | 一次 `select(...).where(id.in_(task_ids))` + 一次 `select(Room).where(room_no.in_(...))` |
| `housekeeping_service.py:233` (`batch_done`) | 同上 → **N** | 同上 |
| `routes.py:587` (`create_rooms`) | `for item: session.get(RoomType, ...)` → **N** | 一次 `where(id.in_([i.room_type_id for i in body]))` |
| `reception_service.py:454-471` (`unlink_rooms`) | `for gid in group_ids:` 内 2 次查询 → **2N** | 一次 `where(link_group_id.in_(group_ids))` 后内存分组 |
| `routes.py:874-890` (`batch_upsert_price_calendar`) | per item：`assert_price_allowed` + `select(PriceCalendar)` → **2N** | 一次 `where(room_type_id.in_(...), date.in_(...))` 建映射 |

**预期**：各 2N → 2。**收益：中**。

---

## B8. 【P2】其他确认的 N+1

| 位置 | 当前 | 建议 | 收益 |
|---|---|---|---|
| `ota_service.py:245-255` | 逐房型 `COUNT(Room)` + `resolve_external_code` → **2N** | 批量 `group_by(room_type_id)` + 批量映射 | 中 |
| `yield_service.py:278` | 逐日期 `select(PriceCalendar)` → **N** | 一次 `where(date.in_(dates))` | 中 |
| `chatbot_service.py:254` | 逐房型 `select(PriceCalendar)` → **N** | 一次 `where(room_type_id.in_(...))` + `order_by(price)` | 中 |
| `group_block_service.py:100-115` | 逐排房 `select(Room)` + `select(GroupAllocation)` → **2N** | 批量 `in_()` | 中 |
| `night_audit_service.py:396-406` (`_occupied_without_booking`) | 逐房 `select(Booking)` → **N** | 与 B1 ① 复用同一批结果（**当前与 `:96` 查询重复**） | 中 |
| `commission_service.py:61` | 逐渠道 `select(CommissionReconciliation)` → **N** | N≈3~5，可接受；可保留 | 低 |
| `rbac_service.py:145` | 播种期逐角色 `select(Role)` → **N** | 仅租户开通时执行，N≈6 | 低 |
| `fnb_service.py:374-397` | 订单与明细分两次查（各 1 次） | 非 N+1，可用 `selectinload` 合并为 1 次 | 低 |
| `room_service.py:169-178` (`recommend_rooms`) | 固定 1 + 3 次（历史房号 → 再查 Room） | 非 N+1；可与 `:129` 合并为一次带 `room_no.in_` 的查询 | 低 |

---

## B9. 【P2】`get_context` 扇出 + 重复调用

**位置**：`app/services/reception_service.py:137-240`

单客上下文串行 6 次查询：`_resolve_booking` → `get_by_phone` → `get(Member)` → `_resolve_room_state` → `select(Bill)` → `_load_audit_log`。

且 `advance()` 在 **`reception_service.py:270` 和 `:393` 各调用一次 `get_context`** → **12 次查询 / 次动作**。

**建议**：member / room / bill / audit 四个可选聚合之间无依赖，可用 `asyncio.gather` 并发；第二次 `get_context` 可复用首次已解析的 `booking`。
**预期**：12 → 6（gather 后 ≈4）。**收益：中**（前台操作台主接口）。

---

## B10. 已有的正确模式（作为改写模板，勿改）

- **`routes.py:1527-1541` `_enrich_guests_with_member`** —— 全仓**唯一**正例，注释明确写「避免 N+1」：
  ```python
  ids = [g.member_id for g in guests if g.member_id]
  rows = await session.execute(select(Member).where(Member.id.in_(ids)))
  ```
  **建议将这一「收集 ID → 批量 `in_()` → 内存映射」写法作为全仓 N+1 改写的统一模板。**
- **`analytics_service.py:530-562` `export_rows`** —— keyset 分页（`id > last_id` + `limit`），内存占用恒定，写法正确。

---

# C. 缓存机会点

## C0. 现状盘点（关键发现）

| 类别 | 位置 | 说明 |
|---|---|---|
| 读缓存 | `routes.py:629-657` `rooms:{tenant_id}` | TTL 30s（默认 `cache_ttl_seconds`） |
| 读缓存 | `routes.py:3284-3293` `dashboard:{tenant_id}:{hotel_id}:{start}:{end}` | TTL 30s |
| 失效 | `room_service.py:89` `invalidate_prefix("rooms:{tenant_id}")` | 房态流转 |
| 失效 | `routes.py:611` / `routes.py:4821` `invalidate_prefix("rooms:{tenant_id}")` | 建房间 / DND 开关 |
| 失效 | `booking_service.py:52` `invalidate_prefix("dashboard:{tenant_id}")` | 预订 create/check_in/check_out |

> ⚠️ **失效覆盖不全（正确性问题）**：`dashboard:` 仅在预订域失效，**收银（add_charge / pay / settle）、夜审（DailyReport 落库）、房价变更均不失效** → 夜审完成后 30s 内看板仍是旧日报数据。见 C4。

## C1. 房态盘 `rooms`

| 项 | 现状 / 建议 |
|---|---|
| Key | 现状 `rooms:{tenant_id}` → **建议改为 `rooms:{tenant_id}:{hotel_id}`** |
| 问题 | 1 万门店租户会把全部 100 万间房塞进**一个** value，JSON 序列化 + 网络开销巨大；且 `state` 过滤在缓存快照上用 Python 做（`routes.py:658-659`） |
| TTL | 房态盘 30s → 建议 **15s**（强实时）；基础房型 600s |
| 失效 | 现状：transition / create_rooms / DND。**缺失**：房间信息编辑（floor/room_type_id）、批量导入 |
| 前置改造 | `list_rooms` 需增加 `hotel_id` 过滤参数（前端配合传） |
| **收益** | 【高】（改 key 粒度） / 【低】（TTL 调整） |

## C2. 房型基础数据 `room_types`

| 项 | 建议 |
|---|---|
| Key | `roomtypes:{tenant_id}` |
| TTL | 600s |
| 读路径 | `routes.py:567`、`ota_service.py:240/326`、`chatbot_service.py:247`、`mp_service.py:38`、`price_service.py:42` |
| 失效 | 房型 CRUD |
| **收益** | 【中】（每租户 <100 行，但被价格解析链路间接放大） |

## C3. 房价日历 `price_calendar`

| 项 | 建议 |
|---|---|
| Key | 单日 `price:{tenant_id}:{room_type_id}:{date}`；区间 `pricecal:{tenant_id}:{room_type_id}:{start}:{end}` |
| TTL | 300s |
| 读路径 | `price_service.py:22` `_base_price`（被 `resolve` 调用 → 建单每晚、夜审每房）、`routes.py:844` 日历视图 |
| 失效 | `routes.py:874` `batch_upsert_price_calendar`、单条 upsert、`yield_service.py` 应用建议价 |
| **收益** | 【**高**】（配合 B4 批量化后，可进一步把建单查询降到 1–2 次） |

## C4. 看板 `dashboard`（已实现 → 补失效）

| 项 | 建议 |
|---|---|
| Key | 现状良好，保留 |
| TTL | 日报数据建议 **60s**（夜审后当天数据才变） |
| **必补失效** | `CashierService.add_charge` / `pay` / `settle`；`NightAuditService.run_night_audit`（DailyReport 落库后） |
| **收益** | 【高】（**正确性 > 性能**：当前夜审后看板必现 30s 脏读） |

## C5. 门店基础数据 `hotels`

| 项 | 建议 |
|---|---|
| Key | `hotels:{tenant_id}` |
| TTL | 600s |
| 读路径 | `routes.py:526`、`night_audit_service.py:262`、`night_audit_scheduler.py:56`、`analytics_service.py:123`、`group_service.py:131` |
| 失效 | 门店 CRUD |
| **收益** | 【低】—— **可暂缓**（门店数少，且多为跨店看板的驱动表，B5 批量化后收益已覆盖） |

## C6. 餐饮菜单 `menu_items`

| 项 | 建议 |
|---|---|
| Key | `menu:{tenant_id}:{hotel_id}` |
| TTL | 300s |
| 读路径 | `fnb_service.py:56` `list_menu_items`（点菜页每次开） |
| 失效 | 菜单 CRUD；**`fnb_service.py:203` `set_menu_sold_out` 必须失效**（否则沽清不生效，属功能缺陷） |
| **收益** | 【中】 |

## C7. 跨店看板 / 报表快照 `report_snapshots`

| 项 | 建议 |
|---|---|
| 说明 | `ReportSnapshot`（`app10.py`）**本身已是「物化缓存」**，模式正确，应沿用 |
| 扩展 | 把 `hotel_ranking` / `night_audit_board` / `hq_dashboard` 三个跨店看板也走缓存：key `ranking:{tenant_id}:{start}:{end}`，TTL 300s，夜审后失效 |
| **收益** | 【高】—— 这三个都是 2N/3N 的 N+1 接口，**B5 批量化 + C7 缓存双管齐下**效果最佳 |

## C8. 明确**不建议**加缓存的

| 数据 | 理由 |
|---|---|
| `audit_logs` | 写入极频繁、查询条件多维、合规要求强一致 → 靠 A7 索引解决 |
| `bill_items` / `payments` | 账务强一致，缓存脏读风险远大于收益 |
| `bookings` 列表 | 写频繁且需实时（入住/退房即时可见）→ 靠 A3 索引 + 分页 |

---

# D. 其他风险

## D1. 无 limit 的列表查询（**51 / 54**）

> 全仓仅 `list_bookings`(`routes.py:994`)、`list_bills`(`routes.py:1708`)、`query_audit_logs`(`routes.py:2502`) 有护栏（`MAX_LIST_ROWS = 5000`，`routes.py:425`）。

**高基数、必须处理**（其余为低基数基础数据，可暂缓）：

| 端点 | 位置 | 实际查询 | 风险 |
|---|---|---|---|
| `list_rooms` | `routes.py:615` | `select(Room).where(tenant_id)` | 百万级；缓存 miss 时全扫 |
| `list_daily_reports` | `routes.py:1962` | 无 limit **无 order** | 无 |
| `list_business_days` | `routes.py:1949` | 无 limit **无 order** | 无 |
| `list_housekeeping_tasks` | `routes.py:2768` → `housekeeping_service.py:187` | 无 limit | 无 |
| `list_pos_orders` | `routes.py:4156` → `fnb_service.py:193` | 无 limit | 无 |
| `list_kitchen_tickets` | `routes.py:4194` → `fnb_service.py:471` | 无 limit | 无 |
| `list_shifts` | `routes.py:2110` → `shift_service.py:125` | 无 limit **无 order** | 无 |
| `list_complaints` | `routes.py:4347` → `complaint_service.py:84-96` | 无 limit | 无 |
| `list_price_calendar` | `routes.py:844` | 无 limit | 无 |
| `list_group_blocks` | `routes.py:1325` | 无 limit | 无 |
| `list_alerts` | `routes.py:3235` | 无 limit | 无 |
| `list_push_logs` | `routes.py:4704` | 无 limit | 无 |
| `list_yield_recommendations` | `routes.py:3742` | 无 limit | 无 |
| `list_report_snapshots` | `routes.py:4897` | 无 limit | 无 |
| `openapi_read_rooms` | `routes.py:3610` | 无 limit | 无 |
| `openapi_read_bookings` | `routes.py:3649` | 无 limit | 无 |
| **房间锁房事件子查询** | **`routes.py:645-657`** | `.order_by(id.desc())` **无 limit** | **扫全部锁房事件再 `setdefault`** |

**另有两处「拉全量后在 Python 里过滤」**
- `housekeeping_service.py:253` `staff_performance`：拉全部 `DONE` 工单后按日期过滤 → 应下推为 SQL `WHERE done_at BETWEEN`。
- `housekeeping_service.py:293` `overdue_count`：拉全部行内存计数 → 应改 `COUNT(*) WHERE due_at < now()`。

**建议**：把 `MAX_LIST_ROWS` 抽成公共依赖 `paged(default=50, max=5000)` 逐个端点接入；对 `daily_reports`/`business_days` 等时序数据强制 `order_by(desc).limit()`。
**收益：高**（防 OOM 与慢查询）。

---

## D2. `SELECT COUNT(*)` 高频调用

| 位置 | 说明 | 建议 | 收益 |
|---|---|---|---|
| `price_service.py:80/87` `availability` | 2 次 COUNT/调用；被 `booking_service.py:86` **逐晚**调用（占 5N 中的 2N） | 随 B4 批量化；`total`（房型总房数）几乎不变 → 可缓存 | 高 |
| `night_audit_service.py:283-292` | **逐店** `COUNT(SUSPENDED)` | 随 B5 批量化 | 高 |
| `analytics_service.py:40/128` `_total_rooms` | **逐店** `COUNT(Room)` | 随 B5 批量化 | 高 |
| `night_audit_service.py:410-422` `_count`/`_total_rooms` | 每次夜审固定 3 次 COUNT | 可接受，暂缓 | — |
| `housekeeping_service.py:293` | 拉全量行内存计数 | 改 SQL COUNT（见 D1） | 中 |

---

## D3. 连接池 / 会话配置

**位置**：`app/db/session.py:41-50`
```python
_engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
```

| # | 问题 | 影响 |
|---|---|---|
| 1 | **未配置任何池参数** | MySQL/ShardingSphere 下 `QueuePool` 默认 `pool_size=5, max_overflow=10` → 最多 **15 连接**。1 万门店 + 夜审批量并发下严重不足 |
| 2 | 未设 `pool_recycle` | MySQL 默认 `wait_timeout=28800s`，但 ShardingSphere-Proxy / 云 RDS 常设 300–900s → 连接被静默回收后报 "MySQL server has gone away"。`pool_pre_ping=True` 能兜底但每次借连接多一次 ping RTT |
| 3 | 未设 `pool_timeout`（默认 30s） | 池耗尽时请求排队 30s 才报错 → 表现为雪崩而非快速失败 |
| 4 | 未设 `pool_use_lifo`（默认 False） | LIFO 可显著降低空闲连接被 MySQL 回收的概率 |
| 5 | **文档与实现不一致** | `session.py:3` 注释写「生产环境为 PostgreSQL」、`config.py:11` 也写 PostgreSQL，但实际生产是 **MySQL + ShardingSphere-Proxy** |

**建议**
```python
# app/core/config.py  Settings 新增
db_pool_size: int = 20
db_max_overflow: int = 30

# app/db/session.py
_engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,       # 建议 20–50
    max_overflow=settings.db_max_overflow, # 建议 30–50
    pool_recycle=1800,                     # < MySQL wait_timeout
    pool_timeout=10,
    pool_use_lifo=True,
)
```
SQLite 时保持现状（`NullPool` 或不传池参数）。
**收益：高**（生产可用性）。

---

## D4. 【最高优先级】数据模型问题：`LIKE '%{date}%'` 判重

**位置**：`app/services/night_audit_service.py:435-445`
```python
select(func.count()).select_from(BillItem).where(
    BillItem.bill_id == bill_id,
    BillItem.type == "ROOM_CHARGE",
    BillItem.description.like(f"%{business_date}%"),   # ← 前导通配符
)
```

**问题**
1. 前导通配符 → **任何索引都失效**，只能全表扫描 `bill_items`（亿级）。
2. 位于夜审主循环 → **每间在住房一次**，300 间房 = 300 次全表扫描。
3. 语义不安全：`description` 形如 `房租 2026-09-20`，若客人备注含日期串会**误判为已过账**（漏收房租）。

**建议**：`BillItem` 增加 `business_date` 列，写入时回填，判重改等值匹配。
```python
business_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

# 判重改写
select(BillItem.bill_id).where(
    BillItem.bill_id.in_(...),
    BillItem.type == "ROOM_CHARGE",
    BillItem.business_date == business_date,
)
# 配套索引
Index("ix_bill_items_bill_type_date", "bill_id", "type", "business_date")
```
含 Alembic 迁移 + 历史数据回填（`UPDATE bill_items SET business_date = SUBSTR(description, -10) WHERE type='ROOM_CHARGE'`）。
**收益：极高** —— 这是夜审「≤5 分钟」验收达标的最大障碍，且**不是加索引能解决的**。

---

## D5. 事务边界：`transition()` 内部 COMMIT

**位置**：`app/services/room_service.py:82`（`await self.session.commit()`）

被夜审主循环 `night_audit_service.py:137` 每房调用 → **300 次事务提交**。
同时是**正确性问题**：中途失败无法回滚整个营业日（只能靠 `night_audit_scheduler.py:127` 的 try/except + SUSPENDED 补偿）。

**建议**：`transition()` 增加 `auto_commit: bool = True` 参数，批量场景（夜审、批量换房）传 `False`，由调用方统一提交。
**收益：高**。

---

## D6. 【架构提醒】分片键与索引前导列的冲突

ShardingSphere 分库分表下，若 `tenant_id` 为分片键，则**所有复合索引必须以 `tenant_id` 为前导列**，否则跨片广播。本次审计 A 节建议均遵守，但发现 3 处例外：

| 位置 | 现状 | 风险 |
|---|---|---|
| `booking.py:33` | `ix_bookings_hotel_checkin (hotel_id, check_in_date)` | 无 `tenant_id` 前导 → 跨片 |
| `night_audit.py:19` | UQ `(hotel_id, business_date)` | 无 `tenant_id` |
| A15 建议 | `ix_bd_hotel_status_date (hotel_id, status, business_date)` | 无 `tenant_id` |

**⚠️ 首要待确认**：分片键究竟是 `tenant_id` 还是 `hotel_id`？
- 若为 `tenant_id`：上述 3 处需改为 `tenant_id` 前导（UQ 改为 `(tenant_id, hotel_id, business_date)`）。
- 若为 `hotel_id`：**A 节所有 `tenant_id` 前导索引都要改成 `hotel_id` 前导** —— 这会推翻本审计的大部分索引建议，必须优先确认。

---

# 按收益排序的实施清单（前 10）

| # | 项目 | 类型 | 关键证据 | 收益 | 工作量 |
|---|---|---|---|---|---|
| 1 | `BillItem` 增加 `business_date` 列 + 索引，替换 `LIKE` 判重 | D4 | `night_audit_service.py:442` | **极高** | 0.5d（含迁移+回填） |
| 2 | 13 条【高】收益复合索引 + Alembic 迁移 | A | 见 A 节汇总 | 高 | 0.5d |
| 3 | 夜审主循环批量化 + `transition(auto_commit=False)` | B1 / D5 | `night_audit_service.py:95-140`、`room_service.py:82` | 高 | 2d |
| 4 | `MAX_LIST_ROWS` 护栏推广到 51 个列表端点 | D1 | `routes.py:425`，16 个高基数端点 | 高 | 1.5d |
| 5 | 连接池参数化 + `Settings` 字段 | D3 | `session.py:41-50` | 高 | 0.5d |
| 6 | KDS 厨房屏 N+1 → 单次 JOIN + limit | B2 | `fnb_service.py:485` | 高 | 0.5d |
| 7 | 移除 `_bill_with_items` 冗余 `refresh`（1 行） | B3 | `routes.py:4305` | 高 | 0.1d |
| 8 | 建单 `availability`/`resolve` 批量化 | B4 | `booking_service.py:85/99` | 高 | 1d |
| 9 | 跨店看板 3 处 N+1 改写 + 快照缓存 | B5 / C7 | `night_audit_service.py:273`、`analytics_service.py:127`、`group_service.py:135` | 高 | 1d |
| 10 | `dashboard` 缓存补全失效点 + `rooms` 缓存 key 按店拆分 | C1 / C4 | `booking_service.py:52`、`routes.py:629` | 中高 | 0.5d |

**合计 ≈ 8.1 人天**（不含联调与压测验证）

> **强烈建议的排序理由**：#1 是唯一「不加它，其他优化都被淹没」的项（单次全表扫描的成本 >> 其余所有查询之和）；#7 是 0.1 人天换 3N 查询的极低成本项，可与 #2 同批次提交。

---

# 需要澄清（阻塞项）

1. **【阻塞 A 节全部建议】ShardingSphere 分片键是 `tenant_id` 还是 `hotel_id`？** 直接决定所有复合索引的前导列（见 D6）。**请优先确认。**
2. **`rooms` 缓存 key 粒度**：`list_rooms` 目前无 `hotel_id` 过滤，是否接受改造为按店缓存（需前端配合传 `hotel_id`）？
3. **`audit_logs` 保留期 / 分区策略**：是否有归档方案？决定 A7 新增 2 个索引的写放大（15–20%）是否可接受。
4. **`MAX_LIST_ROWS = 5000` 是否符合产品预期**？前端是否有依赖「全量拉取」的页面（如房态盘需要一次拿到全部房间）？
5. **夜审「≤5 分钟」验收的房量规模**：100 间 / 500 间 / 1000 间？决定 #3 的优化是否够。
6. **生产 MySQL 版本**：是否 MySQL 8.0+（决定能否用降序索引、不可见索引、函数索引等辅助手段）。
