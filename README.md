# PMS 酒店管理系统 — Sprint 1–14 代码库

> 基于《需求规格说明书（SRS）v1.1》与《详细功能模块开发计划 v1.3》的连续开发迭代。
> 已交付：**平台底座 + 房态状态机（S1）→ 价格库存中心/预订引擎/OTA适配器骨架（S2）→ 夜审/前台收银/会员CRM（S3）→ 财务闭环强化·夜审调度+冲调账（S4）→ 佣金对账+交班（S5）→ 前台运营扩展·街客账+叫醒+PSB队列（S6）→ 权限审计·RBAC+审计留痕+登录安全（S7）→ 移动端直订小程序·微信支付·掉单对账（S8）→ 店长App·经营看板+移动审批+清扫工单+日报推送（S9）→ 集团多店管控·中央房价下发+超权限改价拦截+总部驾驶舱+两级分账（S10）→ AI 客服+自动对账预警（S11）→ 数据中台/经营分析·核心 KPI/门店排名/渠道房型收入/报表导出（S12）→ 开放 API 平台·应用注册+API Key+Webhook 订阅推送+事件总线集成（M18）→ 收益管理·简版调价建议+需求指数+周末因子+竞品对标（M15）→ 餐饮 POS（F&B，M21：菜品/餐桌/开单点菜/挂房账·现金两类结账，复用 CashierService 入账到 Bill）**。

## 技术栈（已定稿 Python）

| 层 | 选型 |
|----|------|
| Web 框架 | FastAPI + uvicorn（全 async） |
| 数据访问 | SQLAlchemy 2.0 async + aiosqlite（开发）/ asyncpg（生产 PostgreSQL） |
| 接口契约 | Pydantic v2（同时作为未来开放 API 文档源） |
| 事件总线 | 进程内 `EventBus`（Kafka 适配器接口预留，见 `app/events/base.py`） |
| 测试 | pytest + pytest-asyncio + httpx TestClient（含 WebSocket 订阅验证） |

> 生产环境数据库切换为 PostgreSQL 时，仅需修改 `PMS_DATABASE_URL` 环境变量，
> 代码层通过 `AsyncSessionLocal` 抽象，无需改动业务代码。

## 目录结构

```
pms/
├── app/
│   ├── core/config.py          # 配置管理（Pydantic Settings，env 注入）
│   ├── db/session.py           # 异步会话工厂（可重置，支撑测试隔离）
│   ├── models/                 # SQLAlchemy 异步模型（tenant_id 贯穿，多租户）
│   │   ├── base.py             # 多租户基表
│   │   ├── tenant.py           # 租户 / 酒店
│   │   ├── room.py             # 房型 / 房间 / 房态事件
│   │   ├── rate.py             # RateCode 价格码（FR-JG-06，五维建模）
│   │   ├── price.py            # PriceCalendar 价格日历
│   │   ├── booking.py          # 预订（M2）
│   │   ├── billing.py          # 账单/账单项/收款（M3）
│   │   ├── member.py           # 会员（M13）
│   │   ├── night_audit.py      # 营业日/营业日报（M4）
│   │   ├── analytics.py        # ★ M16：ReportTemplate / MetricSnapshot
│   │   ├── openapi.py          # ★ M18：ApiApp / ApiKey / WebhookSubscription / WebhookDelivery
│   │   ├── yield_mgmt.py       # ★ M15：PricingRule / PriceRecommendation
│   │   ├── fnb.py              # ★ M21：MenuItem / DiningTable / PosOrder / PosOrderItem
│   │   ├── audit.py            # 审计留痕（DEC-04 WORM 基线，M8-2 结构化扩展）
│   │   ├── rbac.py             # ★ M8-1 RBAC：User / Role / UserRole / LoginSession
│   │   └── pay.py              # ★ M7-2 支付单 PayOrder / 回调流水 PayNotify
│   ├── domain/room_state.py    # ★ M1-1 房态状态机（DEC-02 事件驱动）
│   ├── events/                 # ★ BLK-03 领域事件规范 + 进程内总线
│   │   ├── base.py             # DomainEvent / RoomStateChanged / BookingStateChanged / NightAuditCompleted / BillSettled / UserLoggedIn / PermissionDenied
│   │   └── bus.py              # EventBus：订阅/发布/退订/失败重试
│   ├── services/               # 领域服务
│   │   ├── room_service.py     # 房态流转（M1-1）
│   │   ├── price_service.py    # 价格库存中心（FR-JG，DEC-01）
│   │   ├── booking_service.py  # 预订引擎（M2）
│   │   ├── cashier_service.py  # 前台收银（M3）
│   │   ├── member_service.py   # 会员CRM（M13）
│   │   ├── night_audit_service.py # 夜审引擎（M4）
│   │   ├── analytics_service.py # ★ M16 经营分析/数据中台
│   │   ├── openapi_service.py   # ★ M18 开放 API 平台：应用/密钥/Webhook 投递
│   │   ├── yield_service.py     # ★ M15 简版调价建议：需求指数/规则/竞品对标
│   │   ├── fnb_service.py       # ★ M21 餐饮 POS：菜品/餐桌/开单点菜/两类结账（复用 CashierService）
│   │   ├── rbac_service.py     # ★ M8-1/8-3 RBAC：账号/角色/授权/登录锁定/会话
│   │   ├── audit_service.py    # ★ M8-2 审计埋点 SDK（record()）
│   │   ├── permissions.py      # ★ M8-1 权限码常量 + 默认三档角色定义
│   │   ├── mp_service.py       # ★ M7-1 小程序房型报价 + 一键下单
│   │   └── pay_service.py      # ★ M7-2 统一下单/回调幂等/掉单对账
│   ├── channels/               # OTA 直连适配器骨架（M6-1，渠道中立）
│   │   ├── base.py             # ChannelAdapter 抽象契约
│   │   ├── ctrip.py / meituan.py # 携程/美团骨架
│   │   └── __init__.py         # get_adapter() 注册表
│   ├── api/                    # 路由 + Schema + WebSocket
│   │   ├── routes.py           # 全部 REST 端点
│   │   ├── schemas.py          # Pydantic 接口契约
│   │   └── ws.py               # /ws/rooms/state（房态实时广播）
│   └── main.py                 # FastAPI 装配
├── tests/                      # 126 个测试（S1:25 + S2:12 + S3:8 + S4:6 + S5:6 + S6:9 + S7:9 + S8:9 + S9:9 + S10:6 + S11:6 + S12:8 + S13:7 + S14:6），全覆盖
├── pyproject.toml
└── README.md
```

## 房态状态机（M1-1 / DEC-02）

状态集合：`VACANT_CLEAN`(空净) · `VACANT_DIRTY`(空脏) · `OCCUPIED`(在住) ·
`ARRIVAL_LOCKED`(预抵) · `MAINTENANCE`(维修) · `OUT_OF_SERVICE`(停用)

关键流转（仅合法流转允许，非法流转返回 422）：check_in（空净/预抵→在住）、
check_out（在住→空脏）、clean_done（空脏→空净）、lock_for_arrival（空净→预抵）、
start/end_maintenance。**每次合法流转发布 `RoomStateChanged` 领域事件**。

## 运行

```bash
# 1. 创建隔离环境并安装依赖
python -m venv .venv
.venv/Scripts/python.exe -m pip install fastapi "uvicorn[standard]" \
    sqlalchemy aiosqlite pydantic pydantic-settings pytest pytest-asyncio httpx

# 2. 运行测试（105 passed）
.venv/Scripts/python.exe -m pytest tests/ -v

# 3. 启动开发服务
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
# 交互式文档： http://127.0.0.1:8000/docs
```

## 里程碑验收对照

| 阶段 | 验收项 | 状态 |
|------|--------|------|
| S1 | 多租户基线 / 房态状态机 / 房态事件可订阅 / RateCode / 审计 | ✅ |
| S2 | 价格库存中心(DEC-01) / 预订全周期(M2) / OTA适配器骨架(M6-1) | ✅ |
| S3 | 夜审自动化(M4) / 前台收银(M3) / 会员CRM(M13) | ✅ |
| S4 | 夜审自动调度+异常挂起(M4-2) / 冲调账(M4-5) | ✅ |
| S5 | 夜审佣金对账(M4-4) / 前台收银交班(M3) | ✅ |
| S6 | 街客账+叫醒(M3-7) / PSB上传队列(M3-5) | ✅ |
| S7 | RBAC三级模型(M8-1) / 审计埋点SDK(M8-2) / 登录安全+会话(M8-3) | ✅ |
| S8 | 小程序直订·房型报价+一键下单(M7-1) / 微信支付·回调幂等+掉单对账(M7-2) | ✅ |
| S9 | 店长App·经营看板(M10-1) / 移动审批(M10-2) / 清扫工单(M10-3) / 日报推送(M10-4) | ✅ |
| S10 | 集团多店管控·中央房价下发(M17-2) / 超权限改价拦截(M17-2) / 总部驾驶舱(M17-1) / 两级分账(M17-3) | ✅ |
| S11 | AI 智能客服(M11) / AI 自动对账预警(M12) | ✅ |
| S12 | 数据中台/经营分析·核心 KPI/门店排名/渠道房型收入/报表导出(M16) | ✅ |
| S13 | 开放 API 平台·应用注册(M18) / API Key 生成校验与轮换(M18) / Webhook 订阅与 HMAC 推送(M18) / 事件总线全局投递(M18) | ✅ |
| S14 | 收益管理·简版调价建议(M15)：需求指数(历史出租率) / 规则化涨降价 / 周末因子 / 竞品对标(match·undercut) / 建议落库 | ✅ |
| S15 | 餐饮 POS（M21）：菜品/餐桌管理 / 开单点菜 / 挂房账(room)·现金(cash)两类结账 / 餐饮消费统一经 CashierService 入账到 Bill（余额 = Σ应收 − Σ实收）/ 权限点 `fnb.manage` 赋予经理与前台 | ✅ |

---

## Sprint 3 新增（夜审 + 前台收银 + 会员CRM）

### 夜审引擎（M4，FR-YS）
- `app/models/night_audit.py`：BusinessDay（营业日，DEC-03 与自然日解耦）、DailyReport（不可变营业日报快照）
- `app/services/night_audit_service.py`：`run_night_audit()` —— 取/建 OPEN 营业日 → 统计到离店 → 遍历在住房按价格库存中心解析当日房租并过账（去重防重复）→ 会员房累积积分 → 生成日报 → 营业日置 CLOSED → 发布 `NightAuditCompleted`
  - **房态不变式**：夜审**只过账、不翻房**。在住房一律保持 `occupied` 直到真实退房（`booking_service.check_out` 负责 `occupied→vacant_dirty` + 派清扫工单）。历史版本曾在此做「预离翻房」（`check_out_date == business_date + 1` 即翻脏），造成 `rooms.state` 与 `bookings.status` 不一致：房态盘显示空房（清扫后可被重卖 → 重房）、在住数少算，且真实退房因源状态非 `OCCUPIED` 抛 `InvalidTransition` 被卡死。该逻辑已移除，回归见 `tests/test_night_audit.py::TestNightAudit::test_night_audit_does_not_block_real_checkout`。
- 端点：`POST /night-audit`、`GET /business-days`、`GET /daily-reports`

#### 夜审快照前后对比（操作台增强）
- `DailyReport.snapshot`（原为恒 `"{}"` 占位）现由 `run_night_audit()` 填充 JSON，零模型变更、alembic 零漂移：
  - **before（过账前）**：`room_state_distribution`（六态计数）、`occupied_rooms`、`unsettled_bills`（`count` + `amount`分，取 OPEN 账单 `balance` 之和）、`anomalies`（房态差异检测：在住房但无覆盖营业日的在住预订，脏数据/重复入住）。
  - **after（过账后）**：`room_state_distribution`、`posted_room_charge`（全店过账房租）、`flipped_rooms`（**恒为空数组**；字段保留仅为兼容历史日报 JSON，夜审不再翻房）。
  - **diff**：`occupied_delta`（在住变化数；夜审不翻房，正常应为 0）。
- `DailyReportOut` 新增 `snapshot: str` 字段，前端 `每日营业报表` 表格可展开行解析并对比夜审前后房态/账务/差异提醒。
- 前端 `NightAudit.tsx` 新增「挂账 / 异常营业日」卡片（列 `SUSPENDED` 营业日 + `suspended_reason` + 单笔「重试夜审」按钮 + 「重试全部挂账」批量按钮，复用 `_get_or_open_day` 重开 OPEN 重试）。
- **挂账原因归因**：`NightAuditScheduler.auto_run` 捕获单日异常后置 `SUSPENDED` 时，将原因格式化为 `[分类] 原文`（如 `[重复入住脏数据]`、`[房型数据缺失]`、`[房态流转非法]`、`[数据完整性冲突]`、`[数据库/连接异常]`、`[未知异常]`）；`_categorize_suspended(exc)` 按消息关键字归类（纯函数，不依赖异常类型，新异常自动落入「未知异常」）。前端 `parseSuspended` 解析前缀 → 彩色 Tag，便于运营按原因分组干预。
- 测试：`tests/test_night_audit.py` 新增 3 例快照测试 + `TestSuspendedReasonCategorize` 单测（6 分类用例）；`tests/test_auto_night_audit.py` 扩展 `test_auto_run_suspends_on_failure`（断言 `[未知异常]` 前缀）+ 新增 `test_suspended_reason_categorized`（模拟重复入住脏数据 → 断言 `[重复入住脏数据]` 归因落到 `suspended_reason`）。
- 注意 `_occupied_without_booking` 必须用 `scalars().first()` 而非 `scalar_one_or_none()`，否则重复入住脏数据会抛 `MultipleResultsFound`（见下方排障表）。
- **跨店聚合**：上述单店快照/挂账归因之上，另提供集团级只读看板 `GET /tenants/{tenant_id}/night-audit/board`（M17-lite，详见下方 Sprint 10 集团多店管控段），将各店最新营业日状态 / 挂账数 / 日报摘要汇聚到总部 Dashboard，无需逐店点开操作台。

### 前台收银（M3，FR-QT）
- `app/models/billing.py`：Bill / BillItem / Payment（金额以「分」存储，余额 = Σ应收 − Σ实收）
- `app/services/cashier_service.py`：开单 → 加账(房租/杂费) → 收款(现金/预授权/微信/支付宝/银联/储值) → 退房结账(多方式分账) → 挂账/退款
- 端点：`POST /bills`、`POST /bills/{id}/charges|payments|settle|refund`、`GET /bills/{id}`

### 会员 CRM（M13，FR-MB）
- `app/models/member.py`：Member（等级/储值/积分/客史，租户内跨店共享）
- `app/services/member_service.py`：注册、储值充值、消费累积积分、入住升级、客史聚合；结账时自动累积积分
- 端点：`POST /members`、`GET /members/{phone}`、`POST /members/{phone}/recharge`

### Sprint 3 验收对照
| 验收项 | 状态 |
|--------|------|
| 夜审房租自动过账 + 营业日报 | ✅ 单店秒级，重复夜审 409 拦截 |
| 预离自动翻房（OCCUPIED→VACANT_DIRTY） | ❌ **已移除**——在住房必须保持 OCCUPIED 直到真实退房（房态不变式，见上）；改由 `booking_service.check_out` 负责翻脏 |
| 收银开单/加账/多方式收款/结账/押金退款 | ✅ 余额校验、结账须平账 |
| 会员注册/充值/积分累积（结账联动） | ✅ |

> 下一步 Sprint 6+：前台收银扩展（PSB上传队列/街客账/叫醒）、权限审计 M8、移动端小程序（M7）与店长App（M10）、集团管控 M17。

## Sprint 4 新增（财务闭环强化 · 夜审调度 + 冲调账）

### 夜审自动调度（M4-2，FR-YS-02）
- `app/services/night_audit_scheduler.py`：`NightAuditScheduler.auto_run(tenant_id, as_of, operator)`
  - 遍历租户下全部酒店；对 OPEN/SUSPENDED 且 `<= as_of` 的营业日执行夜审；
  - 无待审日则为 `as_of` 当日创建 OPEN 营业日（代表「今夜应审」）；
  - **单日异常捕获后置 `SUSPENDED` 并记录原因，不阻断其余日（异常挂起）**；挂起日可重试（重开为 OPEN 重新夜审）；
  - 生产环境由 Celery 按租户分波错峰触发（dev-plan 2.2.3），本服务封装「跑批」语义。
- `BusinessDay.status` 扩展 `SUSPENDED`，新增 `suspended_reason` 列；`_get_or_open_day` 允许挂起日重试。
- 端点：`POST /night-audit/auto-run`（返回 `{ran, suspended, errors}`）。

### 冲调账（M4-5，FR-YS-05）
- `app/models/adjustment.py`：`AdjustmentVoucher`（bill_id/business_day_id 可空、`type` VOID|ADJUST、`amount_cents` 有符号、`reason`、`operator`）。
- `CashierService.issue_adjustment()`：在 OPEN 账单上开具有符号调整凭证，原应收/实收条目保持不可变（WORM），按 **余额 = Σ应收 − Σ实收 + Σ调整(有符号)** 重算。
- 端点：`POST /bills/{id}/adjustments`、`GET /adjustments`；`BillOut` 增加 `adjustments` 字段。

### Sprint 4 验收对照
| 验收项 | 状态 |
|--------|------|
| 夜审批量跑批（自动创建当日营业日并过账） | ✅ ran=1、营业日 CLOSED、日报正确 |
| 单日异常挂起（不阻断整批，记录原因） | ✅ SUSPENDED + errors |
| 挂起日重试（重开 OPEN 重新夜审） | ✅ 重试后 CLOSED |
| 冲调账凭证 + 余额重算 | ✅ 调整后余额随之变动 |
| 已结账账单拒收冲调 / 零金额拒收 | ✅ 400 |

## Sprint 5 新增（佣金对账 + 前台收银交班）

### 夜审佣金对账（M4-4，FR-YS-04）
- `app/models/commission.py`：`CommissionRule`（租户级、按渠道设定费率 `rate_bps`，Unique(tenant,channel)）、`CommissionReconciliation`（不可变对账行：酒店×营业日×渠道，含计提基数/费率/应计佣金/状态 PENDING|RECONCILED）。
- `app/services/commission_service.py`：`set_rule()` 设定/更新费率；`reconcile(tenant_id, hotel_id, business_date, revenue_by_channel)` 按规则对各渠道佣金性房费收入计提（无规则或零收入不计提），幂等覆盖同维度行，发布 `CommissionReconciled` 事件。
- **夜审联动**：`NightAuditService.run_night_audit()` 遍历在住房时按 `booking.channel` 累计 `room_rev_by_channel`，夜审末尾自动调用 `CommissionService.reconcile()` 沉淀佣金对账。
- 端点：`POST /commission-rules`、`GET /commission-rules`、`GET /commission-reconciliations`（支持 hotel_id / business_date 过滤）。

### 前台收银交班（M3，FR-QT-交班）
- `app/models/shift.py`：`ShiftHandover`（开班备用金 / 应交现金 / 实点现金 / 差异 / 状态 OPEN|CLOSED）。
- `app/services/shift_service.py`：`open_shift()` 登记备用金开班；`close_shift()` 按 **应交现金 = 备用金 + 班内现金收款**（`Payment(created_by=收银员, method=CASH, created_at>=开班时间)` 聚合）计算差异 = 实点 − 应交，发布 `ShiftClosed` 事件。
- 不解耦 `Payment` 表结构，靠收银员标识 + 时间戳聚合，与收银账务保持单一事实源；`Payment`/`BillItem` 增补 `TimestampMixin`（created_at/updated_at 审计留痕）。
- 端点：`POST /shifts/open`、`POST /shifts/{id}/close`、`GET /shifts`。
- `PaymentIn` 新增 `operator` 字段（收款操作员，交班现金对账按此聚合，同时强化审计）。

### Sprint 5 验收对照
| 验收项 | 状态 |
|--------|------|
| 佣金规则设定/查询（按渠道费率） | ✅ |
| 夜审自动计提佣金（携程 10% → 房费 30000 计 3000） | ✅ 自动沉淀对账行 PENDING |
| 无规则渠道不计提 | ✅ 直订/微信零计 |
| 交班备用金 + 班内现金 → 应交/实点/差异 | ✅ 平衡 0、短款 -2000 正确 |
| 仅本班次本收银员现金计入 | ✅ 跨收银员隔离 |
| 收款操作员随 Payment 落库（审计） | ✅ operator 字段 |

## Sprint 6 新增（前台运营扩展：街客账 + 叫醒 + PSB 队列）

### 街客账（M3-7，散客挂账）
- `Bill.source` 列（`BOOKING` | `WALK_IN`，默认 `BOOKING`）：`CashierService.open_bill()` 在缺 `booking_id` 时自动判定为 `WALK_IN`，财务可据此区分预订账与散客账。
- `POST /bills` 支持可选 `source` 入参；`GET /bills?source=` 按来源过滤（如仅查街客账）。

### 叫醒服务（M3-7，FR-QT-叫醒）
- `app/models/wakeup.py`：`WakeUpCall`（房号 / 叫醒时刻 / 状态 PENDING|DONE|MISSED|CANCELLED / 备注 / 登记人）。
- `app/services/wakeup_service.py`：`create()` 登记（时刻须晚于当前）、`mark_done()` / `mark_missed()` / `cancel()` 状态流转、`due_calls()` 按时刻升序返回待叫列表（供前台轮询）。
- 端点：`POST /wake-up-calls`、`GET /wake-up-calls`（支持 hotel_id / status_ / due_before 过滤）、`POST /wake-up-calls/{id}/done`、`POST /wake-up-calls/{id}/cancel`；登记即发 `WakeUpCallScheduled` 事件。

### PSB 上传队列（M3-5，公安住客登记报送）
- `app/models/psb.py`：`PsbUploadTask`（酒店 / 预订 / 住客 / 证件号 / 房号 / 状态 QUEUED|UPLOADED|FAILED / 上报报文 payload / 上报时间 / 操作员）；`id_doc_no_masked` 属性仅暴露脱敏值（保留前4后2），原始证件号留库供真实报送与审计。
- `app/services/psb_service.py`：`enqueue_from_booking()`（**入住自动建任务**）、`enqueue()`（散客现场登记）、`upload()`（mock 上报置 UPLOADED + 记录报文/时间，发 `PsbUploaded`）。
- **入住联动**：`BookingService.check_in()` 在转在住后自动 `enqueue_from_booking()`，无需前台额外操作。
- 端点：`POST /psb-tasks`（散客手动建）、`GET /psb-tasks`（支持 hotel_id / status_ 过滤）、`POST /psb-tasks/{id}/upload`。

### Sprint 6 验收对照
| 验收项 | 状态 |
|--------|------|
| 无预订直接开单 → 来源 WALK_IN | ✅ |
| 账单按来源过滤（BOOKING / WALK_IN） | ✅ |
| 街客账可加账/收款/平账结账 | ✅ 余额归零 SETTLED |
| 叫醒登记 → PENDING，到点置 DONE | ✅ |
| 叫醒待叫列表按时刻过滤（due_before） | ✅ |
| 入住自动生成 PSB 上报任务 QUEUED | ✅ |
| PSB 上报置 UPLOADED + 记录时间 | ✅ |
| 证件号接口脱敏（前4后2） | ✅ 4403****1X |
| 散客可手动建 PSB 任务（booking_id 空） | ✅ |

## Sprint 7 新增（权限审计 M8：RBAC + 审计留痕 + 登录安全）

### RBAC 三级模型（M8-1，FR-QX-01）
- `app/models/rbac.py`：
  - `User` 门店登录账号（租户内 `username` 唯一、加盐 SHA-256 口令、状态 active|disabled|locked、失败计数 / 锁定到期 / 最近登录 IP）；
  - `Role` 角色（`level` ADMIN|MANAGER|STAFF、`is_system` 系统内置、`hotel_scoped` 是否绑定门店、`permissions` 权限码 JSON 列表）；
  - `UserRole` 用户-角色绑定（可绑定 `hotel_id`，实现**门店级授权**）；
  - `LoginSession` 登录会话（token / IP / 过期时间 / status active|revoked）。
- `app/services/permissions.py`：9 个权限码（`price.edit` / `booking.cancel` / `billing.refund` / `billing.adjust` / `billing.discount` / `night_audit.run` / `audit.view` / `user.manage` / `role.manage`）+ 默认三档角色定义。
- `app/services/rbac_service.py`：建账号 / 建角色 / 授权 / 权限解析 / 登录鉴权 / 会话管理。
- **租户开通即播种默认三档角色**：管理员(租户级,9权限) / 门店经理(门店级,7权限) / 前台(门店级,3权限)，`is_system=True` 不可删。

### 权限解析语义（重要）
| 调用 | 语义 |
|------|------|
| `effective_permissions(user)` 不带 hotel_id | 返回用户在**任意门店**的权限并集（登录态概览） |
| `effective_permissions(user, hotel_id=X)` | **严格按门店作用域**：租户级角色全量生效；门店级角色仅当绑定门店 == X 时生效 |
| `has_tenant_scope_permission(user, perm)` | 跨门店资源（如租户级审计查询）只认可**非门店绑定**角色的权限 |

### 审计埋点 SDK（M8-2，FR-QX-02）
- `AuditLog` 结构化扩展：新增 `hotel_id` / `actor_id` / `resource_type` / `resource_id` / `result`(success|failure) / `ip` / `created_at`（原 `resource` 自由文本字段废弃，改为结构化双字段）。
- `app/services/audit_service.py`：`record(session, tenant_id, action, *, actor, ...)` 统一留痕入口。
- **覆盖点**：改价(`price.edit`)、取消单(`booking.cancel`)、折扣(`billing.discount`)、冲账(`billing.adjust`)、导出(`audit.view`)、登录(`auth.login`)、鉴权拒绝(`auth.permission_denied`)；房态/预订/会员充值沿用旧埋点（已迁移至新字段）。
- 端点：`GET /audit-logs`（支持 action / resource_type / hotel_id / actor / result_ / limit 过滤；`token` 存在时强制 `audit.view` 鉴权）。

### 登录安全（M8-3，FR-QX-03）
- `RbacService.authenticate()`：密码校验 + **连续失败 5 次锁定 30 分钟**（锁定到期自动解锁），成功则重置失败计数并记录登录时间/IP。
- `create_session()` / `revoke_session()` / `get_session()`：12 小时会话，过期或已注销的 token 自动失效。
- 事件：`UserLoggedIn`（成功/失败均发布，供安全监控订阅）、`PermissionDenied`（越权尝试留痕）。
- 端点：`POST /auth/login`、`POST /auth/logout`、`POST /auth/check`（按 hotel_id 严格鉴权）、`/users`、`/roles`、`/users/{id}/roles`。

### Sprint 7 验收对照
| 验收项 | 状态 |
|--------|------|
| 租户开通播种默认三档角色 | ✅ 管理员9 / 经理7 / 前台3 权限 |
| 建账号 + 授权 + 登录返回 token/权限 | ✅ |
| 门店级角色作用域严格校验 | ✅ 绑定门店 True / 其他门店 False |
| 登录态权限概览（门店级亦可见） | ✅ 经理返回 7 项权限 |
| 改价留痕 | ✅ `price.edit` |
| 取消单留痕 | ✅ `booking.cancel` |
| 折扣留痕 | ✅ `billing.discount` |
| 冲账留痕 | ✅ `billing.adjust` |
| 审计导出鉴权（无 audit.view → 403） | ✅ 门店经理 403、管理员 200 |
| 连续 5 次失败锁定账号 | ✅ 第6次正确密码仍 locked |
| 登出注销会话（token 失效 → 401） | ✅ revoked |

> 下一步 Sprint 8+：移动端小程序（M7）/ 店长 App（M10）/ 集团多店管控（M17）/ AI 客服与自动对账（M11-M12）。

## Sprint 8 新增（移动端直订小程序 M7：房型报价 + 一键下单 + 微信支付 + 掉单对账）

### 小程序直订（M7-1，FR-MP）
- `app/services/mp_service.py`：
  - `room_type_offers()` 房型报价：逐晚经**价格库存中心**解析（`channel=wechat_mp`，DEC-01 唯一房价源），聚合总价与最低可售量；任一晚无房即 `bookable=False` 并给出 `sold_out_dates`；
  - `place_order()` 一键下单：复用预订引擎建 `Booking(channel=wechat_mp)`（逐晚房量校验 + 总价解析），联动生成支付单，发布 `MpOrderCreated`。
- 端点：`GET /mp/offers?hotel_id&check_in&check_out`、`POST /mp/orders`、`GET /mp/orders/{out_trade_no}`。

### 移动支付（M7-2，微信支付 mock 契约先行）
- `app/models/pay.py`：`PayOrder`（out_trade_no 租户内唯一、amount_cents、状态 CREATED|PAID|CLOSED、prepay_id/transaction_id/paid_at/close_reason）、`PayNotify`（notify_id 唯一约束幂等去重 + 原始报文留痕 WORM 基线）。
- `app/services/pay_service.py`：
  - **统一下单**（`_unified_order` mock prepay_id，真实签名/证书对接按同一契约替换 `_wechat_*`）；
  - **回调验签（P0）**：`X-Pay-Sign = HMAC-SHA256(secret, 原始请求体)`，密钥 `PMS_PAY_NOTIFY_SECRET`；
    无签名/错签名 → **401 且不写回调流水、不落账**；生产可置 `PMS_REQUIRE_PAY_NOTIFY_SECRET=true`，
    未配密钥时**拒绝全部回调**（走人工补单），避免默认密钥被利用；
  - **回调幂等**：同 `notify_id` 去重 DUPLICATE；订单已 PAID 的迟到重放回调放行为 DUPLICATE 不重复落账；
  - **金额校验**：回调金额 ≠ 支付单金额 → REJECTED（防篡改），订单状态不被篡改；
  - **支付成功落账**：预订已有 OPEN 账单 → 直接落 `Payment(WECHAT, ref_no=transaction_id)` 并回填 `bill_id`；尚未开单 → 标记 PAID，开单后经 `apply_prepay()` 预付抵扣；
  - **掉单对账**：`reconcile(before)` 对超时未支付单渠道查单（mock=未支付）→ 关单 `CLOSED(reconcile_timeout)` 防占库存；「已支付但回调丢失」经迟到回调幂等补单；已关单的迟到回调 → REJECTED 走人工补单。
- 事件：`PayOrderPaid` / `PayOrderClosed` / `MpOrderCreated`。
- 端点：`POST /pay/notify`、`GET /pay-orders?status_=`、`POST /pay-orders/{out_trade_no}/close`、`POST /pay/reconcile`、`POST /bills/{id}/apply-prepay`。

### Sprint 8 验收对照
| 验收项 | 状态 |
|--------|------|
| 房型报价逐晚价格 + 总价（走价格库存中心） | ✅ 两晚 30000×2=60000 |
| 任一晚无房 → bookable=False + sold_out_dates | ✅ 满房场景 |
| 下单建 wechat_mp 预订 + 待支付单（含 prepay） | ✅ |
| 回调成功落账（已开账单直接落 Payment） | ✅ 余额 60000→0 |
| 回调幂等（同 notify_id / 迟到重放 DUPLICATE） | ✅ |
| 金额篡改拒绝（REJECTED，状态不被篡改） | ✅ |
| **回调验签：无签名/错签名 → 401 且不落账** | ✅ 6 个新用例 |
| **生产未配密钥时拒绝全部回调** | ✅ |
| 预付抵扣（开单晚于回调 → apply-prepay） | ✅ 余额归零 |
| 掉单对账关单 + 已关单迟到回调拒绝 | ✅ CLOSED / REJECTED |
| 小程序预付订单完成入住结账闭环 | ✅ SETTLED balance=0 |

> 下一步 Sprint 12+：数据中台/BI / 开放 API 平台（M18）/ 收益管理（M15/M20）。

## Sprint 9 新增（店长 App M10：经营看板 + 移动审批 + 清扫工单 + 日报推送）

### 经营看板（M10-1，FR-APP-01）
- `app/services/manager_service.py`：`dashboard()` 一屏聚合——房态盘按状态计数（`rooms.by_state`）、实时出租率 OCC、在住数、**预抵/预离列表**（按营业日过滤）、最新营业日报快照（夜审后自动出现）、**待办提醒三件套**（超时清扫工单 / 待审批单 / 未读推送）。
- 端点：`GET /manager/dashboard?hotel_id&business_date`。

### 移动审批中心（M10-2，FR-APP-02，审批≤2步）
- `app/models/app10.py::ApprovalTicket`：类型 `DISCOUNT|ADJUST|OVERBOOK|REFUND`、`payload`（通过后的执行参数）、状态 `PENDING|APPROVED|REJECTED`、决策人与决策时间、`ref_id` 执行落点回填。
- `app/services/approval_service.py`：`submit()` 提交 → `decide()` 一键决策；**折扣类审批通过即自动执行落账**（复用 `CashierService.add_charge`，收银单一事实源，余额即时冲减）；重复决策 409 拦截；决策全程 `approval.decide` 审计留痕 + `ApprovalDecided` 事件。
- 端点：`POST /approvals`、`GET /approvals?status_&hotel_id`、`POST /approvals/{id}/decide`。

### 清扫工单（M10-3，FR-APP-03 / FR-FT-04）
- `app/models/app10.py::HousekeepingTask`：`CLEANUP|MAINTENANCE|INSPECT`，状态 `PENDING|ASSIGNED|DONE|CANCELLED`，来源 `AUTO_CHECKOUT|MANUAL`，`due_at` 超时阈值。
- `app/services/housekeeping_service.py`：**退房自动建 CLEANUP 工单**（挂接 `BookingService.check_out`，与 PSB 同模式）；`assign()` 派单 → `done()` 完成并**联动房态 空脏→空净 回归可售**；`overdue_count()` 超时未完成统计（看板提醒店长）；完成发 `HousekeepingDone` 事件。
- 端点：`POST /housekeeping-tasks`、`GET /housekeeping-tasks`、`POST /{id}/assign`、`POST /{id}/done`。

### 日报推送（M10-4，FR-APP-04）
- `app/models/app10.py::Notification`：recipient/channel(APP|SMS 预留)/title/body/ref_type/ref_id/read_at 已读回执。
- `app/services/notification_service.py`：**夜审完成自动推送营业日报+摘要**（挂接 `NightAuditService`，06:00 前送达语义）；`list_notifications(unread_only)` 未读过滤；`mark_read()` 已读。
- 端点：`GET /notifications?hotel_id&unread_only`、`POST /notifications/{id}/read`。

### Sprint 9 验收对照
| 验收项 | 状态 |
|--------|------|
| 看板房态盘汇总 + 实时 OCC | ✅ 2房1住 OCC=50% |
| 预抵/预离列表（按营业日） | ✅ |
| 最新日报快照上屏（夜审后） | ✅ |
| 待办提醒三件套（超时工单/待审批/未读） | ✅ |
| 折扣审批通过自动落账（余额即时冲减） | ✅ 30000→28000，ref_bill 回填 |
| 审批驳回不执行 + 重复决策 409 | ✅ |
| 审批留痕（audit-logs 含 approval.decide） | ✅ 操作人=店长 |
| 退房自动建 CLEANUP 工单 | ✅ AUTO_CHECKOUT |
| 派单 → 完成联动房态空脏→空净 | ✅ vacant_clean |
| 夜审自动推送日报 + 已读回执 + 看板未读归零 | ✅ |

> 下一步 Sprint 15+：完整收益管理（M20：动态定价模型/竞品对标强化/超售控制）/ 开放 API 平台深化（应用市场、OAuth2 授权流、限流网关）。

## Sprint 11 新增（AI 服务 M11/M12）

### AI 智能客服（M11，R12）
- `app/models/ai.py::ChatSession / ChatMessage`：多渠道会话（wechat_mp/mini_app/web）、状态 bot/handoff/closed、满意度 1-5 星、消息角色 user/bot/human/system。
- `app/services/chatbot_service.py`：
  - `classify()` 关键词+置信度意图识别（房价 / 退订政策 / 设施 / 交通 / 人工 / 问候 / unknown），接口稳定、后续可平滑替换为 LLM。
  - `reply()` 自动应答；房价意图可 enriched 返回门店实时起价。
  - `handoff()` 显式转人工，给前台推送 APP 通知并发布 `ChatHandoffRequested` 事件。
  - `close_session()` 记录满意度。
- 端点：`POST /ai/chat-sessions`、`GET /ai/chat-sessions`、`GET /ai/chat-sessions/{id}`、`POST /messages`、`POST /handoff`、`POST /close`、`GET /messages`。

### AI 自动对账预警（M12，R13）
- `app/models/ai.py::AlertNotification`：金额异常 / 重复入账 / 漏收 / 渠道佣金差异，severity info/warning/critical，状态 open/acknowledged/resolved/false_positive，含建议操作。
- `app/services/anomaly_service.py`：夜审后自动扫描四类异常：
  - **金额异常**：非折扣/冲账账单项 ≤0、大额现金收款 ≥1000 元；
  - **重复入账**：同一账单同渠道同金额支付 ≥2 笔；
  - **漏收**：已入住订单无关联账单；
  - **渠道佣金差异**：CommissionReconciliation 佣金金额与规则计算值不符。
- 扫描结果发布 `AnomalyDetected` 事件，并可通过 `GET /ai/alerts`、`POST /ai/alerts/{id}/acknowledge`、`POST /ai/alerts/{id}/resolve` 处理。
- `NightAuditService.run_night_audit()` 已接入扫描（夜审完成后二次提交）。

### Sprint 11 验收对照
| 验收项 | 状态 |
|--------|------|
| 房价意图自动回复 | ✅ intent=price，含房价说明 |
| 转人工 + 会话状态 handoff + 消息列表 | ✅ |
| 关闭会话记录满意度 | ✅ satisfaction=5 |
| 金额异常预警（非折扣账单项负数） | ✅ amount_anomaly critical |
| 重复入账预警 | ✅ duplicate_payment critical |
| 预警确认/解决状态流转 | ✅ acknowledged → resolved |

## Sprint 10 新增（集团多店管控 M17）

### 中央房价下发 + 超权限改价拦截（M17-2，FR-R18 / FR-JG-05）
- `app/models/group.py::GroupPricePolicy`：集团价格策略，支持租户级/门店级/房型级维度，`price_floor_cents`/`price_ceiling_cents` 边界；同维度重复下发幂等覆盖。
- `app/services/group_service.py`：`set_price_policy()` 下发策略 → `assert_price_allowed()` 改价拦截；门店改价超出总部策略区间直接 **HTTP 403 + group.price_block 审计留痕**；策略下发本身记录 `group.policy_issue` 审计。
- 改价入口 `POST /price-calendar` 已接入拦截校验（M8 审计 + M17 策略组合）。
- 端点：`POST/GET /group/price-policies`。

### 总部驾驶舱（M17-1）
- `GroupService.hq_dashboard()`：聚合租户下所有门店**最新营业日报**，按 **RevPAR 降序排名**；同时给出集团总营收、总房费收入。
- 端点：`GET /group/dashboard`。

### 跨店夜审看板（M17-lite）
- 只读聚合集团下**各店最新营业日状态 / 挂账数 / 最新日报摘要**，供总部实时掌握各店夜审健康度，无需逐店点开操作台。
- `NightAuditService.night_audit_board(tenant_id)`：遍历租户下 `Hotel`，逐店取最新 `BusinessDay` 状态、按状态统计 `SUSPENDED` 挂账数、取最新 `DailyReport` 摘要（`business_date` / `occ_pct` / `room_revenue` / `total_revenue`）。
- 端点：`GET /tenants/{tenant_id}/night-audit/board`，返回 `{hotels[], hotel_count, total_suspended}`。
- 前端 `Dashboard.tsx` 新增「集团夜审监控（各店）」卡片：表格列门店 / 最新营业日 / 状态 Tag / 挂账数 / 出租率 / 房费收入 / 总营收（金额经 `fmtCents` 渲染）；仅当 `hotel_count >= 1` 时显示。
- **告警可视化**：卡片右上角总览徽标随 `total_suspended` 切换——`>0` 显示红色「⚠ N 家存在挂账」、`==0` 显示绿色「全部门店正常」；`suspended_count > 0` 的门店整行染红（`#fff1f0`），在多店列表中问题店一眼可见；与单店挂账归因彩色 Tag 同色系。
- 与既有 `GroupService.hq_dashboard`（M17-1）同构，复用只读聚合模式，零写入、零副作用。

### 两级分账汇总（M17-3）
- `GroupService.settlement()`：按门店聚合正额收款，拆分为 **现付口径**（CASH/PREAUTH/UNIONPAY）与 **预付口径**（WECHAT/ALIPAY/STORE_VALUE），输出集团汇总 + 各门店明细，双口径合计一致。
- 端点：`GET /group/settlement`。

### Sprint 10 验收对照
| 验收项 | 状态 |
|--------|------|
| 中央下发价格策略（floor/ceiling） | ✅ 同维度幂等覆盖 |
| 低于底价改价 403 拦截 + 留痕 | ✅ 12000 < 15000，group.price_block failure |
| 高于上限改价 403 拦截 + 留痕 | ✅ 60000 > 50000，group.price_block failure |
| 范围内改价正常通过 | ✅ 30000 在区间内，HTTP 201 |
| 总部驾驶舱 RevPAR 排名 | ✅ 广州店 revpar=40000 > 深圳店 revpar=15000 |
| 跨店夜审看板多店聚合 | ✅ 2 店 board：hotel_count=2 / total_suspended=0 / 各店 latest_status=CLOSED / room_revenue=30000 / occ_pct=100 |
| 跨店夜审看板实时链路 | ✅ DEMO2026 GET /night-audit/board → 深圳湾示范店（2035-01-15, CLOSED, 挂账 0, 房费 ¥3450.00） |
| 两级分账 pay_now/prepaid | ✅ 现金 8000 + 微信 22000 = 30000 |

## Sprint 14 新增（收益管理 M15 简版调价建议）

### 数据模型（M15）
- `app/models/yield_mgmt.py`：
  - `PricingRule`：租户级调价规则（high_occ_threshold/low_occ_threshold/max_uplift_bps/max_discount_bps/weekend_uplift_bps/competitor_strategy/competitor_undercut_bps）。幅度以 bps（万分之一）存储，阈值以百分比整数存储。
  - `PriceRecommendation`：调价建议快照（hotel_id/room_type_id/business_date/base_price_cents/recommended_price_cents/adjustment_bps/demand_index/sample_days/rule_id/rationale/status），不可变记录，供审核/回访/未来训练。

### 收益管理服务（M15）
- `app/services/yield_service.py`：
  - `demand_index(tenant_id, hotel_id, window_days=14)`：基于夜审 `DailyReport` 历史出租率（occ_pct）计算需求指数（0–100）与采样天数；无数据返回中性值 60。
  - `recommend(...)`：给定基价 + 目标营业日 + 可选竞品价，输出建议价与可解释理由。规则：
    1. 需求侧：出租率 ≥ high_occ_threshold 按超出比例上调（封顶 max_uplift_bps）；≤ low_occ_threshold 按比例下调（封顶 max_discount_bps）；否则维持。
    2. 周末因子：周五/周六叠加 weekend_uplift_bps。
    3. 落价区间钳制到 [base×(1−max_discount_bps), base×(1+max_uplift_bps)]。
    4. 竞品对标：match→不高于竞品价；undercut→不高于竞品价×(1−competitor_undercut_bps)。
  - `get_or_default_rule` / `set_rule`：租户级启用规则读写（set_rule 禁用旧规则、写入新规则）。

### 接口（M15）
- `GET /api/v1/tenants/{tenant_id}/yield/rules`：获取当前启用规则（无则返回默认）。
- `PUT /api/v1/tenants/{tenant_id}/yield/rules`：更新规则（禁用旧、写新）。
- `POST /api/v1/tenants/{tenant_id}/yield/pricing/recommend`：生成调价建议并落库（201）。
- `GET /api/v1/tenants/{tenant_id}/yield/pricing/recommendations`：查询建议快照（按门店/营业日过滤）。

### Sprint 14 验收对照
| 验收项 | 结果 |
|--------|------|
| 高出租率（>阈值）→ 建议价高于基价且上调 | ✅ 295/300? 实际 33000（occ 95%） |
| 低出租率（<阈值）→ 建议价低于基价且下调 | ✅ 28860（occ 31%） |
| 中性出租率 + 周六高峰 → 叠加周末上调 | ✅ 31500（30000×1.05） |
| 竞品 undercut 策略压价 | ✅ 24250（竞品 25000×0.97） |
| 规则读写 | ✅ PUT 后 GET 反映 competitor_strategy=match |
| 建议列表可查 | ✅ 按 hotel_id 过滤返回 |

### 全测试套件稳定性修复（Sprint 14 收尾）
- **现象**：全量 `pytest` 套件曾在 57% 处卡死 7 分钟+（修复前）。根因：Sprint 13 全局 `#` 通配 Webhook 投递器在每次领域事件发布时开新 DB 连接读 `webhook_subscriptions`，而默认 SQLite 日志模式（DELETE）下读者会被另一连接未提交写事务阻塞，事件风暴测试下 `busy_timeout` 超时叠加成死锁。
- **修复**：`app/db/session.py` 对 `sqlite` 前缀 URL 注册 `connect` 监听器，开启 `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=10000`。WAL 下读者不阻塞写者、写者不阻塞读者，死锁消除；且保留 `test_event_bus_dispatches_to_webhooks` 的同步投递语义（故未采用 `asyncio.create_task` 解耦）。修复后全量 126 用例稳定约 42s 通过。仅对 SQLite 生效，不影响未来 PostgreSQL 生产路径。

## Sprint 13 新增（开放 API 平台 M18）

### 数据模型（M18）
- `app/models/openapi.py`：
  - `ApiApp`：第三方应用（tenant_id/name/app_code/status/events_subscribed），`app_code` 租户内唯一。
  - `ApiKey`：API 密钥，仅存 SHA-256 哈希（`key_hash`）+ 末 4 位掩码（`key_mask`），明文只在创建时返回一次。
  - `WebhookSubscription`：Webhook 订阅（app_id/topic/endpoint_url/secret/status），`topic` 支持精确主题或 `*` 通配。
  - `WebhookDelivery`：每次投递落库（subscription_id/event_topic/event_payload/http_status/attempted_at/response_body/status/error_message），支撑重试与对账。

### 开放平台服务（M18）
- `app/services/openapi_service.py`：
  - `register_app` / `list_apps` / `get_app`：应用注册与查询（同租户 app_code 唯一约束）。
  - `create_key` / `list_keys` / `revoke_key`：密钥生命周期；`verify_key` 用哈希比对且仅放行 active 密钥+active 应用。
  - `subscribe` / `list_subscriptions` / `pause_subscription`：Webhook 订阅管理。
  - `deliver_event`：事件总线入口，按 `topic == event.topic or topic == "*"` 匹配活跃订阅，逐条 HMAC-SHA256 签名（`X-PMS-Signature`）+ 主题头（`X-PMS-Topic`）推送，记录 `WebhookDelivery`。
  - `test_webhook`：手动触发测试事件（`openapi.test_event`）验证可达性。
  - 默认外发走 `httpx`（`_default_http_post`），测试可注入 `http_post` 实现。

### 全局事件集成（M18）
- `app/main.py::lifespan` 通过 `event_bus.subscribe("#", _dispatch_webhooks)` 订阅全部领域事件；发布任意领域事件即自动向已订阅的第三方应用投递 Webhook。
- 注意：`_dispatch_webhooks` 必须经由 `db_session` 模块访问 `_session_factory`（直接 `from import` 会因 `reset_engine()`/`get_engine()` 重新赋值而失效，始终保持旧值 `None`）。

### Sprint 13 验收对照
| 验收项 | 结果 |
|--------|------|
| 应用注册 + 列表 + code 唯一 | ✅ 重复 app_code 返回 409 |
| API Key 生成/列表/吊销 | ✅ secret 前缀 `pms_`、掩码末 4 位、吊销后 verify 返回 401 |
| API Key 校验有效/无效/吊销 | ✅ active 通过，错误与吊销均 401 |
| Webhook 订阅 + 测试投递 + HMAC 头 | ✅ `X-PMS-Signature` / `X-PMS-Topic` 正确 |
| 精确 + `*` 通配匹配投递 | ✅ matched=2 delivered=2 |
| 事件总线发布 → 全局 Webhook 投递 | ✅ `RoomStateChanged` 经 `#` 订阅触发投递并落库 |

## Sprint 12 新增（数据中台/经营分析 M16）

### 数据模型（M16，FR-RP）
- `app/models/analytics.py`：
  - `ReportTemplate`：报表模板（scope/report_type/dimensions/metrics/filters），支持店长/总部保存常用分析组合。
  - `MetricSnapshot`：按酒店+营业日+维度预聚合的指标快照，生产环境可对接 ClickHouse 物化视图/离线图。

### 分析服务（M16）
- `app/services/analytics_service.py`：
  - `dashboard()`：单店 KPI 聚合（RevPAR/OCC/ADR/总收入/日序列）。
  - `hotel_ranking()`：多店横向排名，按 RevPAR 降序。
  - `channel_revenue()`：按预订渠道统计间夜与收入。
  - `room_type_revenue()`：按房型统计间夜与收入。
  - `payment_summary()`：按支付方式汇总实收金额。
  - `export_data()`：统一导出入口，支持 JSON/CSV 语义。
- 所有指标基于既有 `DailyReport`/`Booking`/`Payment` 计算，不破坏单一事实源；ClickHouse 切换时仅替换数据读取层。

### 报表 API
- `GET /analytics/dashboard?hotel_id&start_date&end_date`：单店经营看板。
- `GET /analytics/hotel-ranking?start_date&end_date`：集团门店 RevPAR 排名。
- `GET /analytics/channel-revenue?hotel_id&start_date&end_date`：渠道收入分析。
- `GET /analytics/room-type-revenue?hotel_id&start_date&end_date`：房型收入分析。
- `GET /analytics/payment-summary?hotel_id&start_date&end_date`：支付方式汇总。
- `GET /analytics/export?report_type&format=json|csv`：报表导出。

### Sprint 12 验收对照
| 验收项 | 状态 |
|--------|------|
| 单店看板核心 KPI（RevPAR/OCC/ADR/收入） | ✅ |
| 日序列返回每日 ADR/OCC/收入 | ✅ |
| 空日期范围返回零值不报错 | ✅ |
| 集团门店 RevPAR 排名 | ✅ 广州店 > 深圳店 |
| 渠道收入拆分（direct/ctrip） | ✅ |
| 房型收入拆分 | ✅ |
| 支付方式汇总（CASH/WECHAT） | ✅ |
| JSON/CSV 导出语义 | ✅ |

## 路由级强制会话鉴权（M8-3 落地）

> 此前 M8-3 仅实现了登录/会话/权限校验能力，但后端路由未强制校验，token 仅作前端透传。本步将鉴权落地到**全部业务路由**。

### 机制
- `app/api/routes.py::require_auth`：路由级依赖，解析 `Authorization: Bearer <token>` → `RbacService.get_session()` 校验；缺失 / 伪造 / 过期均返回 `401`。
- 挂载方式：`app/main.py` 通过 `app.include_router(api_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_auth)])` 应用到除公开端点外的所有路由。
- **公开白名单**（无需会话）：`POST /tenants`（租户开通）、`GET /tenants`（租户目录，登录页切换器在未登录时可用）、`POST .../auth/login|logout|check`、`/tenants/{code}/openapi/v1/...`（开放平台**只读**接口，API-Key 独立鉴权）、`POST .../openapi/verify-key`（Key 校验端点）、`/tenants/{code}/ota/{channel}/webhook/...`（HMAC 签名鉴权）。
  - ⚠️ **开放平台管理类写操作不白名单**：注册应用 / 签发密钥 / 吊销密钥 / 注册 webhook / 触发测试，均需**登录会话 + `user.manage`**（仅管理员）。此前 `/openapi/` 整体白名单导致这些操作免登录且零鉴权（P0，已修）。

### 引导账号（让强制鉴权真正可用）
- `RbacService.seed_default_admin()`：`admin / admin123`，**幂等**（已存在则跳过），并绑定 `ADMIN` 角色（完整 9 项权限）。
- `create_tenant` 路由在播种默认三档角色后自动调用；已存在租户（如 `DEMO2026`）通过一次性引导脚本补齐（脚本已清理）。

### 前端联动
- `web/src/api/http.ts` 响应拦截器：收到 `401` → `setToken(null)` + 清除 `pms_user` → `location.href = '/login'`（已登录页判断，避免死循环）。
- `web/src/pages/Login.tsx` 文案更新为「后端已强制会话鉴权，默认账号 admin / admin123」。

### 授权层（RBAC 路由级权限点，M8-3 深化）
> 仅"是否登录"不足以区分操作风险。在认证层之上叠加**授权层**：每个敏感写操作声明所需权限点（`{domain}.{action}`），登录用户还需具备该权限，否则返回 `403`。

- `app/api/routes.py::require_perm`：路由级依赖，在 `require_auth`（认证）之后按 `Security(require_perm, scopes=[权限码])` 二次校验 `RbacService.has_permission(user, perm)`；缺权限返回 `403`。未声明 scopes 的路由仅要求登录态（兼容既有只读接口）。
- 权限码清单见 `app/services/permissions.py`（`PRICE_EDIT` / `BOOKING_CANCEL` / `BILL_REFUND` / `BILL_ADJUST` / `BILL_DISCOUNT` / `NIGHT_AUDIT_RUN` / `AUDIT_VIEW` / `USER_MANAGE` / `ROLE_MANAGE`），与 M8-1 默认三档角色、M8-2 审计埋点共用。
- 已挂载权限点的路由：
  | 权限码 | 路由 | 备注 |
  |--------|------|------|
  | `PRICE_EDIT` | `POST /tenants/{code}/rate-codes` | 改价/房价码 |
  | `BOOKING_CANCEL` | `POST /tenants/{code}/bookings/{id}/cancel` | 取消/删单 |
  | `BILL_REFUND` | `POST /tenants/{code}/bills/{id}/refund` | 退款 |
  | `BILL_ADJUST` | `POST /tenants/{code}/bills/{id}/adjustments` | 冲账/调账 |
  | `BILL_DISCOUNT` | `POST /tenants/{code}/bills/{id}/charges`（仅 `charge_type=DISCOUNT`） | **函数体内精准拦截，加账前即拒 403**，普通加账不受限 |
  | `NIGHT_AUDIT_RUN` | `POST /tenants/{code}/night-audit/auto-run` | 执行夜审 |
  | `AUDIT_VIEW` | `GET /tenants/{code}/audit-logs` | 查看/导出审计 |
  | `USER_MANAGE` | `POST /tenants/{code}/users` | 账号管理 |
  | `ROLE_MANAGE` | `POST /tenants/{code}/roles` | 角色管理 |
- 默认角色权限：`ADMIN`（9 项全有）/ `MANAGER`（7 项，门店级）/ `STAFF`（3 项：取消/退款/折扣）。无角色绑定的用户仅能访问"仅登录"路由，敏感写操作一律 403。

### 验收对照
| 验收项 | 状态 |
|--------|------|
| 无 token 访问受保护端点 → 401 | ✅ `GET /tenants/DEMO2026/bookings` 返回 401 |
| 登录 admin/admin123 → token + 9 权限 | ✅ |
| 带有效 token → 200 | ✅ |
| 伪造/过期 token → 401 | ✅ |
| openapi 只读接口无 token → 200（带无效 Key 则 401） | ✅ `GET .../openapi/v1/hotels` |
| **openapi 管理类写操作无 token → 401** | ✅ `POST .../openapi/apps` |
| **openapi 管理类写操作（前台 token）→ 403** | ✅ 需 `user.manage` |
| 新建租户自动播种 admin 并可登录 | ✅ `PMSNEW01` |
| 前端 `npm run build`（tsc + vite） | ✅ 3130 模块 |
| 无权限用户访问 audit-logs（缺 audit.view）→ 403 | ✅ `newuser` 实测 403 |
| 无权限用户仅登录访问 bookings → 200 | ✅ |
| 无权限用户对账单做折扣（缺 billing.discount）→ 403（加账前拦截） | ✅ |
| 有权限用户（admin）对账单做折扣 → 200 | ✅ |
| 前端 `http.ts` 收 403 → `message.error` 提示 | ✅ |
| 角色分配端点 `POST users/{id}/roles` 补挂 `ROLE_MANAGE`（分配角色须角色管理权限；与 `create_role` 一致） | ✅ |
| 分配 STAFF 后权限集：booking.cancel/billing.discount=true，audit.view/night_audit.run/user.manage/role.manage=false | ✅ 端到端 |
| 无角色用户分配角色（缺 ROLE_MANAGE）→ 403 | ✅ |
| 前端分配角色 Modal：门店级角色（MANAGER/STAFF）自动显示「门店」选择且必填，租户级（ADMIN）不显示 | ✅ `Users.tsx` 用 `shouldUpdate` 按 `role.hotel_scoped` 动态渲染 |
| 门店级角色带 `hotel_id` 分配 → 201 | ✅ `POST users/{id}/roles` `role_id=3,hotel_id=1` |
| 租户级角色 `hotel_id=null` 分配 → 201 | ✅ `role_id=1,hotel_id=null` |
| 门店级角色缺 `hotel_id` → 400（UI 已拦截，验证后端兜底） | ✅ |

## AI 会话建单前端触发（M11 前端落地）

> 让前台在面对「AI 客服」会话时，能一键将会话客人转为真实预订，打通 AI 咨询 → 订单闭环。

- `web/src/pages/AIChat.tsx` 会话详情头部新增「创建预订」按钮（会话 `closed` 态或当前无门店时禁用）：
  - 打开预订表单弹窗，预填会话 `guest_name` / `guest_phone`，渠道默认 `direct`；
  - 房型下拉来自 `listRoomTypes(tenantCode)`（显示「名称（¥基础价）」，基础价按分→元换算）；
  - 提交调用 `createBooking(tenantCode, { hotel_id: 当前门店, room_type_id, guest_name, check_in/out, channel, guest_phone, room_no })`，成功后提示「预订创建成功 #id」。
- 依赖：`useTenant().hotelId`（TenantProvider 自动取租户首店）；未选门店时按钮禁用并提示。
- 后端复用既有 `POST /tenants/{code}/bookings`（已强制鉴权，须带会话 token）。

### 链路留痕（chat_session_id 回链）
> 建单若不回写来源会话，就是"孤儿单"，无法追溯「这笔订单来自哪次 AI 咨询」。本步补齐预订↔会话的关联。

- 后端：`app/models/booking.py` 的 `Booking` 新增可空列 `chat_session_id`（索引）；`BookingCreate` / `BookingOut`（`app/api/schemas.py`）同步加字段；`BookingService.create` 与 `create_booking` 路由透传该参数；`web/src/api/types.ts` 的 `Booking` / `BookingCreate` 同步。
- 前端：`AIChat.tsx` 的 `submitBooking` 在建单时传入 `chat_session_id: current?.id ?? null`；成功后置 `lastBookingId`，会话头部出现「查看订单 #{id}」按钮 → `navigate("/bookings")`，实现 AI 会话 → 订单 → 订单页的闭环跳转。
- dev 库迁移：`bookings` 表经 `ALTER TABLE ... ADD COLUMN chat_session_id INTEGER` 追加列（保留既有演示数据，未重建库）。

### 验收对照（含链路留痕）
| 验收项 | 状态 |
|--------|------|
| 会话详情出现「创建预订」按钮（非关闭态可用） | ✅ |
| 表单预填 guest_name/phone + 房型下拉 | ✅ |
| 提交走 createBooking，返回预订号 | ✅ E2E 建单 #14（HTTP 201） |
| 建单带 chat_session_id → 落库并回查一致 | ✅ E2E 建单 #15（chat_session_id=999，DB 直查确认） |
| 建单不带 chat_session_id → null | ✅ E2E 建单 #16（chat_session_id=None） |
| 建单后头部出现「查看订单」跳转 | ✅ `lastBookingId` 驱动 |
| 前端 `npm run build` | ✅ 3130 模块 |

### 验收对照
| 验收项 | 状态 |
|--------|------|
| 会话详情出现「创建预订」按钮（非关闭态可用） | ✅ |
| 表单预填 guest_name/phone + 房型下拉 | ✅ |
| 提交走 createBooking，返回预订号 | ✅ E2E 建单 #14（HTTP 201） |
| 前端 `npm run build` | ✅ 3130 模块 |

## 房态图双击交互（RoomStatus 前端）

> 房态图是前台最常用的视图。为减少操作路径：空房双击直接办理登记入住，在住双击直接查看订单详情；单击仍保留原有房态流转操作。

- `web/src/pages/RoomStatus.tsx`：
  - 房间卡片**单击**（220ms 延迟，规避与双击冲突）→ 打开房态流转操作框（`transitionRoom` 各触发）。
  - 房间卡片**双击** → 按房态分流：
    - `空净 / 空脏`：打开「办理登记入住」弹窗。提供两路：① 已有预订——列出匹配该房间（`room_no` 相同，或未排房且 `room_type_id` 相同）且 `status=created` 的预订，选定后 `checkInBooking(room_no)` 直接入住；② 散客登记——填客人姓名/住离日期/渠道，`createBooking(walk_in)` 建单后立即 `checkInBooking` 入住。
    - `在住`：打开「订单详情」弹窗，按 `room_no + status=checked_in` 查出在住房间关联的预订，用 `Descriptions` 展示订单号/客人/房型/渠道/住离日期/间夜/房价总额（分→元）/关联会话。
    - 其他房态（预抵锁定/维修/停用）：`message.info` 提示请单击走房态操作。
  - `openDetail` 查单逻辑与后端 `BookingService.check_in` 一致（入住会写回 `booking.room_no`），故双击在住房间必然能命中其订单。
- 依赖：`listBookings` / `createBooking` / `checkInBooking` / `listRoomTypes`；房间状态经既有 `/ws/rooms` 实时推送刷新。

### 验收对照
| 验收项 | 状态 |
|--------|------|
| 前端 `npm run build`（tsc + vite） | ✅ 3130 模块 |
| 空房双击 → 办理登记入住弹窗（已有预订 + 散客两路） | ✅ |
| 散客登记 `createBooking`+`checkInBooking` → 房间 occupied | ✅ E2E 302 房：建单 #17 → check-in 200 → 房间 occupied |
| 在住双击 → 按 room_no 查 checked_in 订单并展示详情 | ✅ E2E 302 房命中 checked_in 订单 |
| 单击仍打开房态流转操作框 | ✅ |

## 房态图在住房间操作闭环（M 房态图续做）

在住房间双击查看订单详情弹窗，补「办理退房」「查看账单」操作，形成在住房间完整操作闭环：

- **订单详情弹窗（occupied 双击）**：`Descriptions` 展示订单号/客人/房型/房号/渠道/住离日期/状态/间夜/房价总额（分→元）/关联会话；底部操作区：
  - 「关闭」：仅关闭弹窗。
  - 「查看账单」：`navigate("/billing?booking={id}&room={room_no}")` 深链跳转前台收银页，自动定位并打开该预订/房间的账单（见 Billing 深链）。
  - 「办理退房」：`Popconfirm` 二次确认后调 `checkOutBooking`，成功提示并**自动跳转收银页定位该账单**（便于前台立即结账），不再仅弹提示。
- **Billing 深链**：`Billing.tsx` 读取 `?booking=` / `?room=` 查询参数，列表加载后优先按 `booking_id` 匹配、未命中再按 `room_no` 匹配，自动 `setOpenId`+`loadDetail` 打开账单抽屉。

### 验收对照
| 项 | 结果 |
| --- | --- |
| 在住双击弹窗底部含「查看账单」「办理退房」按钮 | ✅ |
| 散客建单+入住自动开账，账单 `booking_id` 关联 | ✅ E2E 303 房：建单 #18 → check-in 200 → 自动开账 B46759404(booking_id=18) |
| 查看账单深链按 `booking_id` 命中对应账单 | ✅ 列表中存在 booking_id=18 的账单 |
| 深链 `booking_id` 未命中时回退 `room_no`（兼容历史无关联账单的订单） | ✅ 已加 room_no 兜底分支 |
| 办理退房 `checkOutBooking` 后端链路 | ✅ E2E：#18 check-out 200 → 房间转 vacant_dirty |
| 退房成功自动跳转收银页（`/billing?booking=&room=`）定位账单 | ✅ 深链前端逻辑已落地，前端 `npm run build` 通过 |
| 前端 `npm run build`（tsc + vite） | ✅ 3130 模块 |

### 强制鉴权回归修复（Sprint 14）

M8-3 强制鉴权上线后暴露的真实缺陷，本轮全部修复并补回归测试：

| 缺陷 | 根因 | 修复 | 验收 |
| --- | --- | --- | --- |
| `POST /hotels/{hotel_id}/rooms` 带有效 token 恒 401 | `require_auth` 只认 `/tenants/{id}/...`，门店路径解析不到租户 | 新增 `resolve_tenant_id()`：支持租户编码 / 整型租户 id / 门店 id 三种形态 | ✅ E2E 201（原 401） |
| `POST /tenants/{id}/hotels` 带 token 仍 401 | 少数路由的 `tenant_id` 是整型 id，而会话以租户编码为键 | `resolve_tenant_id()` 对纯数字段回查 `Tenant.code` | ✅ E2E 201（原 401） |
| 夜审 `/night-audit/auto-run` 500 | 「无待审日即插入 as_of」撞 `business_days(hotel_id, business_date)` 唯一约束，且插入在异常隔离块之外 | 无待审日时先查重：已 CLOSED → 跳过（`skipped` 计数），不存在才建 OPEN | ✅ E2E 200 + `skipped=1`，营业日未重复插入 |
| 夜审整店挂起、房租不入账 | 同房间多笔 `checked_in` 订单时 `scalar_one_or_none()` 抛 `MultipleResultsFound` | 按 `id desc` 取候选，优先住期覆盖营业日者，其次取最新一笔 | ✅ 房租正确入账（#20 → 30000），回归测试已覆盖 |
| 退房时房间已非在住态 → 500 | `InvalidTransition` 非 `ValueError`，未被路由 `except ValueError` 捕获 | 入住/退房路由补 `except InvalidTransition` → 409 | ✅ E2E 409 + 明确错误文案 |

**测试态鉴权旁路**：`tests/conftest.py` 新增 autouse fixture，用 `app.dependency_overrides[require_auth]`
覆写为「该租户默认管理员已登录」（返回带真实 `user_id` 的会话对象，授权层仍走真实 RBAC 校验）。
验证鉴权本身的用例用 `@pytest.mark.auth` 退出旁路（新增 `tests/test_auth_enforcement.py`，9 例）。

| 验收 | 结果 |
| --- | --- |
| 全量测试 | ✅ 137 passed（修复前 31 passed / 75 failed / 21 errors） |
| 无 token / 伪造 token 仍 401 | ✅ 认证层未被旁路削弱 |
| 前台角色跑夜审 403、管理员 200 | ✅ 授权层生效 |
| 前端 `npm run build` | ✅ 通过 |

**演示库数据清理**：早期 Sprint 遗留的孤儿在住单（#4/#5/#6/#7/#9/#10/#11/#12/#13，房号对应房间非 occupied）
已置为 `checked_out`；301/404 房已清扫回 `vacant_clean`。当前房态与订单状态完全一致。



## Sprint 15 基础设施 + M18-2 安全 + M20 收益闭环（本轮交付）

### Sprint 15：缓存层 + 生产部署就绪

- **缓存客户端**（`app/infra/cache.py`）：统一 `CacheClient` 门面——
  - 配置 `PMS_REDIS_URL` 且安装 redis 包 → Redis 异步后端；
  - 默认 → 进程内 TTL 字典（接口与 Redis 完全一致，业务代码零改动，多副本部署时切 Redis）；
  - Redis 初始化失败自动降级内存（不致命）。
- **热点读缓存落地**：`GET /tenants/{code}/rooms` 走缓存（key=`rooms:{tenant_id}`，TTL 30s 兜底）；
  写路径显式失效——`RoomService.transition`（房态流转单一收口，入住/退房/夜审全经过）与
  `POST /hotels/{id}/rooms`（建房）失效前缀；`state` 过滤在缓存快照上执行。
- **生产部署样例**（`infra/`）：`docker-compose.yml`（PostgreSQL 16 + Redis 7，应用侧仅环境变量切换、
  业务代码零改动）；`shardingsphere/README.md`（ShardingSphere-Proxy 5.x 128 库分片方案样例：
  tenant_id HASH_MOD 路由、雪花 ID 注意事项、跨分片最终一致靠领域事件+对账）。
- 配置新增（`app/core/config.py`，前缀 `PMS_`）：`REDIS_URL` / `CACHE_TTL_SECONDS`。

### M18-2：刷新令牌 + 接口限流

- **刷新令牌（一次性旋转）**：新模型 `RefreshToken`（14 天有效）；登录返回 `refresh_token`；
  `POST /tenants/{code}/auth/refresh`（公开白名单）校验后旧令牌立即作废、签发新对（同事务原子），
  重放旧令牌 401；登出同步吊销该用户全部刷新令牌（全端下线）。
  用户禁用/删除后刷新同样失效（旋转时复核用户状态）。
- **接口限流**（`app/infra/ratelimit.py` + main.py 挂载 `RateLimitMiddleware`）：
  - 滑动窗口按「客户端 IP + 桶」限速；`/auth/login` 单独收紧（防撞库爆破）；
  - 默认关闭（`PMS_RATE_LIMIT_ENABLED=false`，dev/测试零干扰），生产 compose 开启；
  - 超限 429 + `Retry-After`，响应带 `X-RateLimit-Remaining`；前端 401 拦截器先静默刷新重试一次（防死循环 `_retried` 标志），429 弹提示。
- 配置新增：`RATE_LIMIT_ENABLED` / `RATE_LIMIT_DEFAULT`（240/60）/ `RATE_LIMIT_AUTH`（10/60）。

### M20：调价建议 → 价格日历一键闭环

- 后端：`POST /tenants/{code}/yield/pricing/recommendations/{id}/apply`（`PRICE_EDIT` 权限）——
  suggested 建议按建议价 UPSERT 到价格日历（受 M17-2 集团价策边界校验，越界 403 并记录拦截），
  置 `applied`，审计留痕 `price.edit/source=yield_recommendation`；
  `.../{id}/reject` 拒绝；重复处理 409；未指定房型 400；不存在 404。
- 前端 `Yield.tsx`：建议历史表新增「操作」列——suggested 行「应用」（Popconfirm 确认价）/「拒绝」，
  已处理行显示状态 Tag；新增「房型」列。
- 前端 `http.ts`：登录存 `pms_refresh_token`；401 自动静默刷新重放；`Login.tsx` 持久化刷新令牌。

### 验收对照

| 验收 | 结果 |
| --- | --- |
| 全量测试 | ✅ 152 passed（新增 15：缓存单元/房间缓存失效/刷新令牌/限流/建议应用） |
| 登录返回 refresh_token；旋转后旧令牌重放 401；登出吊销 | ✅ 单测 + E2E |
| 房间列表缓存命中；流转后写失效立即可见新状态 | ✅ 单测 + E2E |
| 限流默认关闭不扰测试；开启后默认桶/auth 桶独立 429 | ✅ 单测 |
| 建议 apply → 价格日历可见建议价；重复 apply 409；reject 互斥 | ✅ 单测 + E2E（12/12 PASS） |
| 前端 `npm run build`（tsc + vite） | ✅ 通过 |
| 建议 apply 受集团价策拦截 | ✅ 单测语义复用（越界 403 + record_price_block） |

## Alembic 迁移落地 + M20 批量应用（续轮交付）

### Alembic 迁移体系（根治 schema 漂移）

- `alembic.ini` + `migrations/env.py`（异步 SQLAlchemy 2.0 版，URL 从 `PMS_DATABASE_URL` 读取，
  `render_as_batch=True` 兼容 SQLite ALTER）；基线迁移 `migrations/versions/69a582a7c5cc_*.py`。
- 验证：空库 `alembic upgrade head` → 43/43 表与模型完全匹配（MATCH）；dev 库 `alembic stamp head`。
- **`alembic check` 立即抓到一处真实漂移**：手工 `ALTER` 加的 `bookings.chat_session_id` 列缺索引
  → 已补 `ix_bookings_chat_session_id`，现零漂移。
- 用法：改模型后 `alembic revision --autogenerate -m "..."` → `alembic upgrade head`。
- 注意：alembic.ini 保持纯 ASCII（Windows configparser 按系统 locale 解码，中文注释会 GBK 报错）。

### M20 批量应用（日期区间落价）

- `POST /tenants/{code}/yield/pricing/recommendations/{id}/apply` 支持可选 body
  `{"start": "...", "end": "..."}`：区间逐日按建议价 UPSERT（闭区间，上限 365 天）；
  不传则仅建议日单日。返回新增 `dates/updated/created`。
- 非法区间（start>end / 格式错）→ 400；区间过长 → 400；重复处理 409；无房型 400；不存在 404。
- `create_room_type` 补 IntegrityError → 409（"房型代码已存在"），替换原 500。
- 前端 `Yield.tsx`：应用改为弹窗（单日 / 日期区间 Radio + RangePicker），成功提示新建/更新天数。

### 环境坑（重要教训）

- **沙箱透明代理会干扰 localhost HTTP E2E**：`HTTP_PROXY`/透明代理层可能对 POST 重发（相差 ~1s），
  造成「首次请求落库成功但客户端收 500（第二次撞唯一约束）」的假象——差点误判为应用 bug。
  排查三板斧：① 进程内 `TestClient` 探测（应用正确性金标准）；② `curl --noproxy '*'` 直连；
  ③ 直查 DB 行 created_at 对比两次执行时间戳。pytest 走 TestClient 不受影响。
- uvicorn `--reload` 热加载不可靠 + 残留 master 进程会复活 worker 并可能与服务新实例重复绑定端口
  （Windows 允许同端口重复绑定）——改后端代码后必须 kill 全部 python uvicorn 进程再单实例重启。

### 验收对照

| 验收 | 结果 |
| --- | --- |
| 空库 alembic upgrade head 后表结构 vs 模型 | ✅ 43/43 MATCH |
| dev 库 alembic check 无漂移（含补齐 chat_session_id 索引） | ✅ No new upgrade operations detected |
| 建议区间应用 5 天 → 日历 5 行建议价；非法区间 400 | ✅ 测试 + 实机验证 |
| 重复房型 409（IntegrityError 兜底） | ✅ 进程内 TestClient 验证 |
| 全量测试 | ✅ 153 passed |

## M18-3 WebSocket 鉴权 + 演示库清理（续轮交付）

### WebSocket 强制鉴权（M18-3，安全缺口修复）

- 此前 `ws://host/ws/rooms` 无需登录即可订阅任意租户房态事件——安全缺口。
- 修复：连接必须携带 `?tenant_id=xxx&token=<登录会话>`，走与 HTTP `require_auth` 同一套
  LoginSession 校验；无效连接 accept 后立即 `close(4401)` 并回 `{"type":"error"}`；
  订阅后仍保持多租户隔离（不跨租户推送）。
- 前端 `RoomStatus.tsx` 订阅 URL 追加 `token`（getToken()）。
- 测试 `test_ws_auth.py`（无 token/伪造 token 拒绝 + 有效订阅 + 租户隔离）；既有
  `test_api.py` WS 用例更新为带 token 连接。

### 演示库 E2E 残留清理（pms_dev.db，备份：pms_dev_backup_20260903.db）

- 删除：测试订单 19 笔（保留 #2 小程序客人及其 SETTLED/OPEN 两张账单作演示）、
  关联 bill_items/bills；测试房型 9 个（FIXX/INTX/Y20E2E/Y20BATCH/YDIAG/Y20B2/Y20FIN/YCUR/Y20GO）
  及其 price_calendar/price_recommendations/房间 8F1；测试用户 5 个（newuser/newuser2/smoke_user/e2e_h/e2e_a）。
- 现状：2 租户（DEMO2026/PMSNEW01）各 1 admin；STD/DLX 2 房型 12 房（7 空净/3 空脏/1 维修/1 停用）；
  房态与订单一致（无 occupied 无 checked_in）；日历 30 行演示价、1 条 suggested 建议示例。

| 验收 | 结果 |
| --- | --- |
| 全量测试 | ✅ 155 passed（新增 WS 鉴权 2 例） |
| 前端 `npm run build` | ✅ 通过 |
| WS 无 token/伪造 token 拒绝 4401、有效 token 可订阅 | ✅ 测试覆盖 |
| 演示库房态/订单/用户一致性 | ✅ 复核通过 |

## 前端联动深化：WS 自动重连 + 日历↔收益互跳（续轮交付）

- **WS 断线自动重连**（RoomStatus）：连接断开后指数退避重连（3s 起 ×1.5，封顶 15s），
  重连时重新读取 token（配合 http.ts 401 静默续期，会话刷新后 WS 可自动恢复），卸载/切租户时终止。
- **价格日历 ↔ 收益管理互跳**：
  - `RateCalendar`：头部新增「收益建议」按钮 → `/yield?date=&room_type=`；
    页面支持深链 `?date=YYYY-MM-DD`（跳月）与 `?room_type=<id>`（选中房型）。
  - `Yield`：头部新增「价格日历」按钮 → `/rate-calendar`；接收 `?date=&room_type=` 深链回填
    生成建议表单；应用成功后的提示内嵌「查看日历 →」链接（带日期与房型深链，6s 时长）。
- 验收：`npm run build`（tsc + vite）✅ 通过；路由 `/yield` `/rate-calendar` 已存在，深链参数解析经类型检查。

## 通知中心点击跳转深链（M10-4 增强，本轮交付）

### 后端：消息即入口

- **新增字段 `notifications.link`**（String(255)，可空）：消息自带前端路由，点击直达业务页。
  迁移 `7c1d4f8a2b90_notifications_add_link`（`alembic upgrade head` 已落到 dev 库）。
- **`NotificationService.build_link(ref_type, ref_id)`**：`REF_LINK_TEMPLATES` 按业务类型推导深链，
  `push()` 未显式传 `link` 时自动填充；显式传入优先（不被模板覆盖）。

  | ref_type | 推导深链 |
  |---|---|
  | `daily_report` | `/reports?type=dashboard`（日报推送额外带 `&date=<营业日>`） |
  | `chat_session` | `/ai-chat?session=<id>` |
  | `booking` / `bill` / `payment` / `alert` / `approval` / `task` / `yield_recommendation` / `commission_reconciliation` | `/bookings?booking=` / `/billing?bill=` / `/billing?payment=` / `/alerts?alert=` / `/approvals?ticket=` / `/housekeeping?task=` / `/yield?rec=` / `/commission?recon=` |

  未知类型 / 缺 `ref_id` / 无 `ref_type` → `link=None`，前端退化为「仅标记已读」并提示「该消息无关联页面」。

- **新增端点**：
  - `GET /tenants/{tid}/notifications/unread-count` → `{"unread": n}`（顶栏角标）
  - `POST /tenants/{tid}/notifications/read-all` → `{"updated": n}`（一键已读，仅更新未读行，幂等）
  - `POST /tenants/{tid}/notifications/{id}/read` 语义扩展为「点击消息」：幂等标记已读并回传 `link`

### 前端：点击 → 已读 → 跳转

- `Notifications`：整行可点击（先标记已读再 `navigate(link)`，无深链则停留并提示）；
  `ref_type` 中文分类 Tag + 配色；未读行淡黄底 + 未读圆点、已读行降透明度；
  头部「全部已读」按钮；读状态变化广播 `pms:notifications-changed` 事件。
- `AppLayout`：顶栏铃铛 Badge + 侧边「通知中心」菜单项角标，60s 轮询 / 页面重新可见 / 自定义事件三重刷新。
- **目标页面深链接收**：
  - `Reports`：`?type=&date=` 自动回填报表类型与日期区间，门店就绪即自动出报表，顶部提示「来自通知中心」。
  - `AIChat`：`?session=<id>` 自动切「全部」筛选并打开该会话（转人工提醒直达）。

### 验收对照（E2E，演示库 DEMO2026）

| 步骤 | 结果 |
|---|---|
| `GET /notifications/unread-count` | `{"unread":3}` ✅ |
| `GET /notifications` | `#3 daily_report → /reports?type=dashboard&date=2026-09-03`；`#4 chat_session → /ai-chat?session=1` ✅ |
| 点击（read） | 返回 link、`read_at` 落值；重复点击 `read_at` 不回退（幂等）✅ |
| `unread_only=true` | 过滤后仅剩未读 ✅ |
| `read-all` ×2 | 首次 `{"updated":3}`，再次 `{"updated":0}`，`unread-count` 归零 ✅ |

- 门禁：pytest **164 passed**（新增 `tests/test_notifications.py` 9 例）；`npm run build` ✅ 通过。
- 演示库历史 2 条通知已按 ref_type 回填 link，并复原 2 条未读（#3 日报 / #4 转人工）供点击演示。

## E2E 冒烟脚本固化（scripts/e2e_smoke.py，本轮交付）

把手搓 curl 验证固化为一键可跑的回归套件，覆盖核心读链路 + 通知深链 + WS 鉴权全闭环，作为后续破坏性变更（如 ① 雪花 ID 替换自增主键）的回归保护网。

### 用法

```bash
# 复用已在 8000 运行的实例（默认，非破坏，不动演示未读角标）
.venv/Scripts/python.exe scripts/e2e_smoke.py

# CI / 完整闭环：自动拉起后端并验证写操作（标已读 / 全部已读，会清空未读）
.venv/Scripts/python.exe scripts/e2e_smoke.py --spawn --mutate

# 自定义目标
.venv/Scripts/python.exe scripts/e2e_smoke.py --base-url http://127.0.0.1:8000 --tenant DEMO2026
```

### 设计要点

- **零三方依赖**：HTTP 用标准库 `urllib`，WS 用 `websockets`（缺失则跳过 WS 项）。
- **自动绕过沙箱透明代理**：脚本启动时显式清空 `http(s)_proxy` 并设 `NO_PROXY=*`，杜绝 POST 被代理重放造成的「假 500」。
- **自带后端生命周期**：默认复用已监听实例；无实例且 `--spawn` 时用当前 venv 拉起 uvicorn，跑完自动回收（仅自建的才回收）。
- **非破坏性**：默认只读；`--mutate` 才验证写操作（点击标已读 + 全部已读幂等），用于完整闭环回归。
- **退出码**：0 = 全通过；非 0 = 存在失败项，可直接接入 CI gate。

### 覆盖项（默认 10 项 / --mutate 13 项）

| 类别 | 检查点 |
|---|---|
| 存活 | `/health`、登录获取 token |
| 通知深链 | 列表含 `link`、未读计数 `unread`、点击标已读回传 `link`（mutate）、`read-all` 幂等归零（mutate） |
| 核心读链路 | 房态 `rooms`、收益规则 `yield/rules`、收益建议 `recommendations`、夜审日报 `daily-reports` |
| WS 鉴权 | 无 token 必须拒绝（收 error/close）、带 token 必须 `subscribed` |

- 验收：`scripts/e2e_smoke.py` 默认 **10/10 通过**（EXIT=0）、`--mutate` **13/13 通过**；演示库未读角标保持 2 条供点击演示。

---

## ① 雪花 ID 替换自增主键（128 分库硬前置）

> Sprint 15 之后、128 分库分表（ShardingSphere-Proxy）落地前的架构级改造：
> 全库主键 / 外键从 `INTEGER` 自增改为 **BigInteger + 雪花 ID**，规避 JS `Number` 2⁵³
> 精度丢失（当前雪花值约 1.9×10¹⁸，远超 2⁵³≈9×10¹⁵）。

### 两项不可回退决策（已与用户确认）

1. **全链路 string**：数据库仍存 `BigInteger` 整数；API 请求 / 响应 / 前端统一用
   **字符串**。DB→API 由 Pydantic `StrId` 别名序列化，前端传参由 FastAPI 路径
   `: int` 自动解析（Python 任意精度，无损失）。
2. **节点号环境变量注入**：worker / datacenter 号从 `PMS_WORKER_ID` /
   `PMS_DATACENTER_ID` 读取（缺省 0），生产按 128 分库实例注入以避免 ID 冲突。

### 改造点（4 层）

| 层 | 文件 | 关键改动 |
|---|---|---|
| 生成器 | `app/core/snowflake.py`（新建） | 标准 64bit 布局：41bit 相对纪元毫秒（EPOCH=2024-01-01）+ 10bit 节点（5+5）+ 12bit 序列；线程安全；进程级单例 `next_id()` |
| ORM | `app/models/base.py` `IntPkMixin.id` | `BigInteger, primary_key=True, autoincrement=False, default=lambda: next_id()`（列级默认，比 `before_insert` 事件可靠） |
| ORM FK | 19 个模型共 39 个 FK 列 | `mapped_column(ForeignKey("x.id"))` → `mapped_column(BigInteger, ForeignKey("x.id"))`；`rbac`/`audit` 逻辑引用列同步 BigInteger |
| Schema | `app/api/schemas.py` | 新增 `StrId = Annotated[str, BeforeValidator(_coerce_str_id)]`；**仅 `*Out` 响应类的 id 字段为 `StrId`**，`*In`/`*Create` 输入类保持 `int`（FK 比较与 `Field(gt=0)` 需 int） |
| Routes | `app/api/routes.py` | `create_hotel`/`create_room_type` 的 `tenant_id: str` + `_lookup_tenant()` 兼容「数字 id」与「字母 code」两种解析 |
| 迁移 | `migrations/versions/4fc9553da160_*.py` | `op.batch_alter_table` 对所有表 PK+FK `INTEGER→BigInteger`；`alembic upgrade head` 零漂移落库 |

### 关键设计定论

- **主键型路径参数保持 `: int`**：前端传 string 数字 ID，FastAPI 自动转 Python int（无精度损失），无需改动。
- **仅 `tenant_id` 改 `str`**：租户业务标识是字母 code（如 `DEMO2026`/`psb1`），`tenant_id` 模型列为 `String(32)`，故 API 输入 / 输出均为 `str`——属 code 非 id，不受影响。
- **输入侧 int、输出侧 string**：body 内 id 需 int 才能与 ORM `BigInteger` 正确比较（曾因误用 `StrId` 触发 409「房型不一致」）；响应侧 string 保证 JS 安全。

### 回归验证（本轮交付）

- **pytest：164 passed**（0 failed / 0 error）。修复了 6 处测试：硬编码 `tenant_id=1/2` 改为捕获真实租户 id；响应 string id 与 int 断言统一 `str()` 比较。
- **前端 `npm run build` ✅**：`web/src/api/types.ts` + `endpoints.ts` 全部 id 字段 `number→string`（含可选 `?: ` 修饰符）；页面组件 21 个文件修复 id `useState`、移除 `Number()` 包裹、局部 helper 改 `string`、比较/数组索引/排序适配（`b.id - a.id` → `b.id.localeCompare(a.id)`）。
- **E2E 冒烟：`scripts/e2e_smoke.py` 默认 10/10、`--mutate` 13/13 通过**（含标已读 / 全部已读幂等写路径）。
- 可启动后端：`PMS_DATABASE_URL="sqlite+aiosqlite:///./pms_dev.db" .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`。

### 迁移注意事项

- Alembic 仅变更**列类型**，不重写既有行值：演示库历史数据（tenant/hotel/notification 等）仍保留原小整数 id（现以字符串返回），**新插入行才生成雪花巨整数**——两端 JS 均安全。
- 生产切 PostgreSQL 前，须为每个分库实例注入不同的 `PMS_WORKER_ID` / `PMS_DATACENTER_ID`，否则跨实例恐生成重复 ID。

---

## ② 通知中心补充 ref_type 推送点（点击深链闭环）

> 在「① 雪花 ID」完成、通知中心深链跳转机制已就绪的基础上，补齐**尚有模板 / 标签但从未在业务流中推送**的
> `ref_type`，使其审核 / 工单 / 收益建议 / 风险预警也能在通知中心点击直达。

### 改造前现状

`app/services/notification_service.py` 的 `REF_LINK_TEMPLATES` / `REF_LABELS` 定义了 11 个 `ref_type` 深链，
但通知中心（`Notification` 表）此前仅由两处真正推送：`daily_report`（夜审）与 `chat_session`（AI 转人工）。
其余 4 个 `ref_type` 虽有模板却无业务推送点：

| ref_type | 中文标签 | 推送点（新增） | 深链模板 |
| --- | --- | --- | --- |
| `approval` | 审批待办 | `ApprovalService.submit` 创建审批单后 | `/approvals?ticket={id}` |
| `task` | 清扫工单 | `HousekeepingService.create_task` 建单后（含退房自动派单） | `/housekeeping?task={id}` |
| `yield_recommendation` | 收益建议 | `YieldService.recommend` 生成建议后 | `/yield?rec={id}` |
| `alert` | 风险预警 | `AnomalyService.scan_after_night_audit` 扫描出预警后逐条推送 | `/alerts?alert={id}` |

> 注：`booking` / `bill` / `bill_item` / `payment` / `commission_reconciliation` 五个模板由 `AlertNotification`
> （风险预警独立信息流）使用，不经通知中心 `Notification` 表，故不在此重复推送，避免噪声。

### 关键改造点

1. **`Notification.ref_id` 列型 `Integer → BigInteger`**（`app/models/app10.py`）：① 之后实体 id 为雪花巨整数
   （≈1.9×10¹⁸），原 `Integer` 在 MySQL 会溢出 `INT`；迁移 `a4c58ae1396f_notification_ref_id_bigint`
   （`op.batch_alter_table` 改列型，`alembic check` 零漂移）已落 `pms_dev.db`。
2. **四处业务流新增 `NotificationService.push(...)`**（见各 service 文件 `② 通知中心推送点` 注释）：
   - `approval_service.py`、`housekeeping_service.py`、`yield_service.py`、`anomaly_service.py` 均新增
     `from app.services.notification_service import NotificationService` 并在落库 flush 后推送，
     `ref_id` 取对应实体的雪花 id（ORM `BigInteger`，经 `NotificationOut.ref_id: StrId` 序列化回字符串，前端安全）。
3. **深链自动推导**：推送未显式传 `link` 时，`build_link(ref_type, ref_id)` 按模板补 `{id}`，前端点击即用。

### 回归验证

- **pytest：168 passed**（0 failed / 0 error）。新增 4 个推送点断言测试：
  - `tests/test_approval.py::test_submit_pushes_approval_notification`
  - `tests/test_housekeeping.py::test_checkout_pushes_task_notification`
  - `tests/test_yield.py::test_recommend_pushes_notification`
  - `tests/test_ai_anomaly.py::test_scan_pushes_alert_notification`
  - 并修正 `tests/test_manager.py` 仪表盘断言：未读通知从「仅日报=1」更新为「日报 + 清扫工单 + 待审批 = 3」。
- **E2E 冒烟：`scripts/e2e_smoke.py` 默认 10/10、`--mutate` 13/13 通过**。

### 后续（未做）

- ③ 通知分级 / 免打扰。

---

## ③ 通知分级 / 免打扰（M10-4 增强）

> 在 ② 的推送点闭环之上，为通知增加**重要级别**与**租户级安静时段**，让低优先级消息在夜间不打扰店长，
> 而风险预警始终触达。

### 通知分级（level）

`Notification` 新增 `level` 列，三档：

| level | 含义 | 推送点 | 免打扰时段 |
| --- | --- | --- | --- |
| `critical` | 紧急（风险预警） | `anomaly_service` 扫描出的预警 | **始终突破**，照常触达 |
| `normal` | 普通待办 | 审批 `approval`、清扫工单 `task`、AI 转人工 `chat_session` | 被静音 |
| `info` | 提示 / 日报 | 营业日报 `daily_report`、收益建议 `yield_recommendation` | 被静音 |

### 免打扰（DND）模型

- 新增 `notification_preferences` 表（每租户一行）：`dnd_enabled`、`dnd_start`、`dnd_end`（本地 `HH:MM`，支持跨午夜如 22:00–08:00）。
- `Notification` 新增 `muted` 列：`NotificationService.push` 落库后查询租户偏好——
  若 `dnd_enabled` 且当前本地时间落在安静时段且 `level ∉ {critical}`，则置 `muted=True`。
- **未读角标（`count_unread`）排除 `muted` 项**——安静时段内低优先级消息不计入顶栏角标，但打开通知中心仍可见（带「免打扰」灰标）。
- 突破规则常量：`BREAKTHROUGH_LEVELS = {"critical"}`（见 `app/services/notification_service.py`）。
- 时段判定：`in_dnd_window(now, start, end)`，跨午夜用 `cur >= s or cur <= e`。

### API

- `GET /tenants/{code}/notification-preferences` → 默认值（无记录时 `dnd_enabled=false, 22:00–08:00`）。
- `PUT /tenants/{code}/notification-preferences` → 更新 `dnd_enabled / dnd_start / dnd_end`。
- 响应 `NotificationOut` 新增 `level`、`muted` 字段；前端 `Notifications.tsx` 渲染分级标签与免打扰标记，并新增「免打扰设置」卡片（开关 + 起止时间 + 保存）。

### 迁移

- `ae16e2cfc5a2_notification_level_muted_and_preferences`：`notifications` 加 `level`/`muted`（带 `server_default`，避免既有行 NOT NULL 冲突）、新建 `notification_preferences` 表；`alembic check` 零漂移，已落 `pms_dev.db`。

### 回归验证

- **pytest：172 passed**（0 failed / 0 error）。新增 `tests/test_notification_preferences.py` 4 例：level 落库、DND 静音非 critical、critical 突破免打扰、偏好 GET/PUT。
- **前端 `npm run build` ✅**（tsc 0 error + vite build）。
- **E2E 冒烟：`scripts/e2e_smoke.py` 默认 10/10、`--mutate` 13/13 通过**。

### 后续（未做）

- 实时推送（WebSocket）与免打扰联动 —— 已在 **⑤** 落地（`/ws/notifications` 按 `recipients` 路由，静音通知不实时弹出）。

## ④ 多接收人 / 角色订阅（M10-4 增强）

> 在 ② 推送点闭环 + ③ 分级免打扰之上，让每类通知可配置**推送给哪些角色**，
> 为后续 WebSocket 实时推送的接收人路由打基础——每条通知落库时即存最终接收人列表。

### 模型

- `Notification` 新增 `recipients` 列（`JSON`，`nullable=False` + `server_default='[]'`）：本通知的最终接收角色列表。
- 新增 `notification_subscriptions` 表（每租户每 `ref_type` 一行，`(tenant_id, ref_type)` 唯一约束）：`recipients` 接收角色列表（自由字符串，空列表=该类通知不推送）。

### 接收人解析（`NotificationService.push`）

- 解析优先级：**显式订阅配置（含空列表=不推送）** > `DEFAULT_SUBSCRIBERS[ref_type]`（缺配置默认）> 历史单 `recipient` 形参（最终兜底）。
- `DEFAULT_SUBSCRIBERS` 覆盖全部 `ref_type`（如 `approval→["store_manager"]`、`task→["front_desk","store_manager"]`、`chat_session→["front_desk"]`），与历史单接收人语义对齐。
- 关键方法：`get_subscribers(tenant_id, ref_type, fallback)` 解析；`get_subscription` / `get_subscriptions` / `set_subscription`（upsert）。

### API

- `GET /tenants/{code}/notification-subscriptions` → 覆盖全部 `ref_type` 的矩阵（含未单独配置的，回落默认），返回 `ref_type`+`label`+`recipients`。
- `PUT /tenants/{code}/notification-subscriptions` → 批量 upsert（按 `(tenant_id, ref_type)`），回读完整矩阵。
- `NotificationOut` 新增 `recipients`；前端 `Notifications.tsx` 列表项渲染「接收：店长、前台」标签，并新增「接收人设置」卡片（每类通知多选/自定义角色 + 保存）。

### 迁移

- `271462418bcd_notification_recipients_and_subscriptions`：`notifications` 加 `recipients`（`server_default='[]'` 既有行安全填充）、新建 `notification_subscriptions` 表；`alembic check` 零漂移，已落 `pms_dev.db`。

### 回归验证

- **pytest：177 passed**（含新增 `tests/test_notification_recipients.py` 5 例：默认回落、订阅覆盖默认、空订阅不推送、GET 矩阵、PUT 回读一致）。
- **前端 `npm run build` ✅**（tsc 0 error + vite build）。
- **E2E 冒烟 10/10 默认 / 13/13 `--mutate` 通过**；订阅→推送→落库 `recipients` 已 curl 实跑验证。

### 后续（可选增强）

- 通知中心列表按 `recipients` 做行级可见性过滤 —— 已在 **⑥** 落地（读取路径与 WS 实时推送走同一套 `ROLE_TAG_MAP` 映射，`recipient_tags` 行级过滤）。

## ⑤ 实时推送（WebSocket）按 recipients 路由（M10-4 增强）

> 在 ④ 落库 `recipients` 基础上增加 WebSocket 实时通道：通知一经落库即扇出给命中本人角色的连接，
> 把「拉取式角标」升级为「低延迟实时提醒」，并与 ③ 免打扰联动（静音通知不实时弹出）。

### 事件（`app/events/base.py`）

- 新增 `NotificationPushed`（`TOPIC = "notification.pushed"`）：落库后由 `NotificationService.push` 发布，
  载荷含 `notification_id / ref_type / ref_id / recipients / muted / level / title / body / link / tenant_id`。
- 发布与落库解耦：`push` 内 `await event_bus.publish(...)` 包在 try/except，发布失败不影响通知落库。

### 路由端点（`app/api/ws.py`）

- 新增 `GET /ws/notifications?tenant_id={code}&token={会话token}`：复用 `/ws/rooms` 的 `_authorize` 强制会话鉴权（无效连接 4401 关闭）。
- 连接建立后，按登录会话的 RBAC 角色档位映射为接收标签集合 `user_tags`（`_resolve_user_tags`）：
  - `ADMIN` → `{store_manager, front_desk, night_audit}`
  - `MANAGER` → `{store_manager}`
  - `STAFF` → `{front_desk}`
- 订阅 `notification.pushed`；每收到事件：先 `tenant_id` 隔离 → 再 `notification_matches(user_tags, recipients, muted)` 判定（静音/空 recipients/无交集均不下发）→ 命中才 `send_json({"type":"notification","data":payload})`。
- `QueuedSubscriber(maxsize=500)` 解耦发布与写入；多租户隔离（不跨租户推送）。

### 前端（`web/src/layout/AppLayout.tsx`）

- 新增 `/ws/notifications` 长连接（携带 `tenantCode` + `pms_token`，经 Vite 代理 `/ws` 转发后端）；
- 收到 `type:"notification"` 即刷新未读角标（`getUnreadCount`）+ 派发 `NOTIFY_CHANGED_EVENT` 让通知中心页即时刷新；
- 既有 60s 轮询 + 页面可见性恢复作为兜底，WS 断连不影响正确性。

### 回归验证

- **pytest：181 passed**（含新增 `tests/test_notification_ws.py` 4 例：角色→标签映射、路由判定、WS 鉴权 4401、admin 端到端实时收到审批通知）。
- **前端 `npm run build` ✅**（tsc 0 error + vite build）。
- **E2E 冒烟 10/10 默认 / 13/13 `--mutate` 通过**；`scripts/ws_smoke_live.py` 真实服务验证：无效 token 4401、admin 订阅回带 tags、触发审批通知实时收到 `recipients=["store_manager"]` 且 `muted=false`。
- 无 Schema 变更，`alembic check` 零漂移。

## ⑥ 通知列表按 recipients 行级可见性过滤（M10-4 增强）

> 在 ④ 落库 `recipients` 与 ⑤ 实时路由的基础上，把同一套角色→标签映射复用到**读取路径**：
> 通知中心列表（`GET /notifications`）与未读计数（`GET /notifications/unread-count`）按登录用户 RBAC 档位做行级过滤，
> 使 STAFF 不再看到店长专属通知——与 WS 实时扇出保持完全一致的行为。

### 共享映射（`app/services/notification_service.py`）

- 将 `ROLE_TAG_MAP` 与 `recipient_tags_for_roles` 从 `app/api/ws.py` 上移至此（服务层），保证实时推送与列表读取**同一份映射、零漂移**：
  - `ADMIN` → `{store_manager, front_desk, night_audit}`
  - `MANAGER` → `{store_manager}`
  - `STAFF` → `{front_desk}`
- `ws.py` 改为从 `notification_service` 导入，不再各自维护。

### 服务层（`NotificationService`）

- `list_notifications` / `count_unread` 新增 `recipient_tags: set[str] | None = None`：
  - 为 `None`（无登录态/内部调用）时退回「租户内全部」，保持既有行为；
  - 非空时对 `Notification.recipients`（`JSON` 列表）做 Python 交集判定——**仅返回与本人标签交集的通知**；
  - **空 `recipients` 对任何人不可见**（与 ④「空列表=不推送」、⑤ `notification_matches` 空 recipients 跳过完全一致）。
- 新增 `resolve_user_tags(tenant_id, user_id)`：经 `RbacService.list_user_roles` → `Role.level` → `recipient_tags_for_roles` 解析当前用户标签（无角色绑定返回空集）。

### 路由层（`app/api/routes.py`）

- `GET /tenants/{code}/notifications` 与 `/unread-count` 注入 `login_session: LoginSession = Depends(require_auth)`，
  调用 `resolve_user_tags` 解析标签后传入服务层；多租户隔离由 `tenant_id` 路径参数保证。
- ADMIN（FULL 标签）可见全部；STAFF 仅见 `front_desk` 类；空 recipients 抑制项全员不可见。

### 回归验证

- **pytest：186 passed**（含新增 `tests/test_notification_visibility.py` 5 例：按标签过滤、空 recipients 全员不可见、未读计数过滤、STAFF 登录仅见 front_desk、ADMIN 登录可见全部）。
- 既有 `tests/test_notification_recipients.py::test_empty_subscription_no_recipients` 同步重构为 `test_empty_subscription_suppresses_notification`：空订阅使审批通知 `recipients=[]`，验证其在列表中缺位（④+⑥ 联合语义）。
- **前端 `npm run build` ✅**（⑥ 仅改后端，前端无需改动；既有 WS 实时刷新不受影响）。
- **E2E 冒烟 10/10 默认 / 13/13 `--mutate` 通过**；admin 仍可见全部通知、未读角标正确。
- 无 Schema 变更，`alembic check` 零漂移。

### 收尾：已读标记行级授权（⑥ 安全加固）

> ⑥ 落地后，列表/未读已按角色隐藏店长专属通知，但仍存在越权面：`read` / `read-all` 仅按 `notification_id` 在租户内操作，
> 拥有 id 的调用方（或猜测）可标记他人专属通知已读，间接篡改店长的未读角标。补齐为同一套 `recipient_tags` 路由。

- 新增模块级 `notification_visible_to(recipients, user_tags)`（与 WS `notification_matches` 同口径但忽略 `muted`——③ 免打扰项在列表仍可见，已读不应以静音拒绝）。
- `NotificationService.mark_all_read` 增 `recipient_tags`：仅清除与本人标签交集的未读项（空 recipients 抑制项不计入）。
- `GET /notifications/{id}/read` 与 `/read-all` 路由注入 `login_session`，解析标签后：
  - 单条 `read`：不可见（空交集）返回 **404**「消息不存在或无权访问」，杜绝越权标记；
  - `read-all`：仅标记本人可见项，店长专属通知的未读状态不被 STAFF 清除。
- 验证：新增 `tests/test_notification_visibility.py::TestNotificationReadGating` 2 例（服务层 `mark_all_read` 按标签过滤；STAFF 按 id 读店长专属通知 404、read-all 后店长通知仍未见）。pytest **188 passed**；E2E 不变。

### UX 增强：类型 / 级别筛选 + 分页（⑥ 收尾，低风险）

> 通知中心列表量大后缺筛选与分页：运营想按 `ref_type`（审批 / 工单 / 收益建议…）或 `level`（critical/warning/info）快速定位，
> 且一次拉全量既慢又浪费。在 ⑥ 行级可见性之上叠加**后端过滤参数 + 前端筛选条 / 加载更多**。

**后端（`app/services/notification_service.py`）**

- `list_notifications` 增 `ref_type: str | None = None` / `level: str | None = None` / `limit: int = 50` / `offset: int = 0`：
  - `ref_type` / `level` 在 **SQL 层** 加 `WHERE`（索引友好，跨库无方言差异）；
  - 行级可见性（⑥ 的 `recipient_tags` Python 交集）**先于**分页切片执行，保证「先按权限过滤、再翻页」语义正确；
  - `offset` / `limit` 在可见性过滤后的 Python 列表上切片（规避 SQLite / MySQL 对 `JSON` 字段 `LIMIT/OFFSET` 与 `WHERE JSON` 的方言差异）。

**路由层（`app/api/routes.py`）**

- `GET /tenifications` 接收 `ref_type` / `level` / `limit` / `offset`，夹紧后透传：`limit = max(1, min(limit, 200))`、`offset = max(0, offset)`（防超大页 / 负数越界）。

**前端（`web/src/api/endpoints.ts` + `web/src/pages/Notifications.tsx`）**

- `listNotifications(tenantCode, opts?)` 接受 `{ unreadOnly?, ref_type?, level?, limit?, offset? }`，仅非空字段拼入 query；
- 列表页头部新增两个 `Select`（类型 / 级别，`allowClear`，由 `REF_LABEL` / `LEVEL_LABEL` 生成 options），`load(append)` 统一处理筛选 + 分页：
  - 非 append 时 `offset=0` 重查，`append` 时拼接并 `setOffset(prev + data.length)`、`setHasMore(data.length === PAGE)`；
  - 列表底部「加载更多」按钮（`PAGE=20`），无更多时禁用；`useEffect` 依赖 `[tenantCode, unreadOnly, refType, level]` 自动重查。
- ⚠️ 实施中曾误植重复 `<List` 起始标签导致前端 `vite build` 报 `Expected ">" but found "itemLayout"`；已删除冗余 `<List` 行修复，构建通过。

**验证**

- 新增 `tests/test_notification_visibility.py::TestNotificationListFiltering::test_ref_type_level_and_pagination` 1 例（断言 `ref_type` 筛选=2、`level=critical`=1、page1=2、page2=1、组合筛选=1、total=3）。
- **pytest：189 passed**（188 + 1）；**前端 `vite build` ✅**；**alembic check 零漂移**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**；后端已重启加载最新代码。

### UX 增强：按门店维度筛选（⑥ 收尾之二，复用既有 `hotel_id`）

> ⑥ 行级可见性 + 已读授权 + 类型/级别筛选分页之后，通知中心仍缺「按门店」视角：连锁/多店租户（ADMIN）的通知混在一起，
> 难聚焦单店运营。后端 `list_notifications` / `count_unread` / `mark_all_read` 早已支持 `hotel_id`，但前端未暴露 —— 本次补齐门店选择器。

**后端（`app/api/routes.py`）**

- `read_all_notifications`（POST `/notifications/read-all`）新增 `hotel_id: int | None = None`，透传 `svc.mark_all_read(tenant_id, hotel_id, recipient_tags=tags)`：选中门店时「全部已读」仅清该店未读（与列表/计数口径一致）。
- `list_notifications` / `count_unread` 的 `hotel_id` 参数此前已存在（⑥ 复用 `Notification.hotel_id` 列），本次仅做前端接线，无 Schema 变更。

**前端（`web/src/api/endpoints.ts` + `web/src/pages/Notifications.tsx`）**

- `listNotifications(opts)` / `getUnreadCount(hotelId?)` / `readAllNotifications(hotelId?)` 增 `hotelId?: number | null`（仅非空拼 `hotel_id` query；`getUnreadCount` 顶栏角标保持不传=全租户总量，向后兼容）。
- 列表页 `useEffect` 挂载时 `listHotels(tenantCode)` 拉门店清单；头部新增「全部门店」`Select`（`allowClear`，选项取自 `Hotel.name`/`id`）；
- `load(append)` 与 `markAll` 透传 `hotelId ? Number(hotelId) : null`（前端 `Hotel.id` 为 `string`，后端 `hotel_id` 为 `int`，由 FastAPI 查询参数自动转整）；`useEffect` 依赖增 `hotelId`，切换门店即重查。

**验证**

- 新增 `tests/test_notification_visibility.py::TestNotificationListFiltering::test_hotel_id_filtering` 1 例（店1=2 / 店2=1 / 全量=3 / 门店维度未读计数独立）。
- **pytest：190 passed**（189 + 1）；**前端 `vite build` ✅**；**alembic check 零漂移**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**；后端已重启（task `C7XYOW`）加载最新代码。

### UX 增强：筛选条件持久化（localStorage，⑥ 收尾之三）

> 门店/类型/级别/仅看未读筛选在刷新后丢失，需重复选择。本次将四类筛选条件持久化到 localStorage，刷新自动恢复。

**前端（`web/src/pages/Notifications.tsx`）**

- 模块级 `loadNotifFilters()` 解析 `localStorage["pms:notif-filters"]`（`{hotelId, refType, level, unreadOnly}`），`useState` 初值从之读取（解析失败/缺失回落默认全量）。
- 新增持久化 `useEffect`：任一筛选变化即写回 localStorage（`try/catch` 包容隐私模式禁用存储）。
- 刷新后：状态从存储恢复 → 既有的 `[tenantCode, unreadOnly, refType, level, hotelId]` 重查 effect 自动带恢复后的条件重新拉取；门店 Select 在 `listHotels` 返回后回填名称（恢复瞬间短暂显示 id 属正常）。

**验证**

- 纯前端行为，无后端变更：**pytest 基线 190 passed 不变**；**前端 `vite build` ✅**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**（API 未变）；后端无需重启。

---

## ⑦ 在住房间业务操作：续住 / 换房（对齐绿云前台操作台）

> 绿云前台操作台点击「在住」房间可执行的典型动作为：续住、换房、账单、退房、叫醒。原系统房态总览（RoomStatus）对在住房间仅提供「退房」，缺失续住与换房两项高频业务动作。本次补齐，使前端操作界面与绿云前台接待能力对齐。

### 房态机扩展（`app/domain/room_state.py`）

- 新增触发器 `ROOM_SWAP`（在住 → 空脏）：仅供换房时腾退原房间使用，订单仍保持 `CHECKED_IN`（区别于 `CHECK_OUT` 会置订单已离）。

### 服务层（`app/services/booking_service.py`）

- `extend_stay(booking, new_check_out_date, operator)`：仅 `CHECKED_IN` 可续住；新离店日须晚于当前；按增量晚逐晚校验房量并累加房费（`total_price` 增量），重算 `nights`（属性派生），写 `booking.extend_stay` 审计 + 发布 `BookingStateChanged`。
- `change_room(booking, new_room_no, operator)`：仅 `CHECKED_IN` 且有房号可换；目标房须 `vacant_clean` 且同房型；新房 `CHECK_IN` → 在住、原房 `ROOM_SWAP` → 空脏（均经 `RoomService.transition` 发布 `RoomStateChanged`，房态图即时刷新）；同步更新在开账单 `room_no`；写 `booking.change_room` 审计 + 事件。

### API（`app/api/routes.py` + `app/api/schemas.py`）

- `POST /tenants/{t}/bookings/{id}/extend-stay`，`BookingExtendIn{new_check_out_date, operator}`。
- `POST /tenants/{t}/bookings/{id}/change-room`，`BookingChangeRoomIn{new_room_no, operator}`。
- 异常处理复用入住/退房口径：`ValueError`/`InvalidTransition` → **409**。

### 前端（`web/src/pages/RoomStatus.tsx` + `endpoints.ts` + `domain/roomActions.ts`）

- 在住订单详情弹窗新增「续住」「换房」按钮：续住弹 DatePicker（禁用 ≤ 当前离店日）；换房弹同房型「空净」房号下拉（取自 `listRooms` 过滤，原房排除）。
- `endpoints.ts` 新增 `extendStayBooking` / `changeRoomBooking`；`roomActions.ts` 新增 `ROOM_SWAP` 标签「换房腾退」。

### 测试（`tests/test_booking.py::TestBookingInHouseOps`）

- 续住：10-01~10-03（2 晚/60000）→ 续至 10-04（3 晚/90000）；离店日不晚于当前 → 409；非 `CHECKED_IN` → 409。
- 换房：0101→0102，新房转在住、原房转空脏；目标=原房 → 409；目标房不存在 → 409。

### 回归验证（本轮交付）

- **pytest 194 passed**（190 + 4）；**alembic check 零漂移**；**前端 `vite build` ✅**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**；后端已重启（task `htxdQZ`）加载最新代码。

---

## ⑧ 前台接待看板（对齐绿云前台主面板）

> 绿云前台主面板将「房态总览 + 今日预抵/预离 + 在住 + 待清扫」聚合为一站式操作台，前台据此快速排房/入住/退房/派清扫。原系统房态盘(RoomStatus)侧重房态网格、Dashboard 偏经营指标，缺少面向前台当班人员的「当日工作量」总览。本次新增独立「前台接待」页，纯前端聚合既有 `listRooms`/`listBookings`/`listRoomTypes`，无后端变更。

### 前端（`web/src/pages/Reception.tsx` + `App.tsx` + `layout/AppLayout.tsx`）

- 房态概览：6 张统计卡（空净/空脏/在住/预抵锁定/维修/停用），颜色与房态盘一致。
- 今日预抵（`created` 且入住日=今天）：客人/房型/房号/渠道 + 「排房/入住」跳转房态盘。
- 今日预离（`checked_in` 且离店日=今天）：同上 + 「退房/结账」跳转房态盘。
- 在住（全部 `checked_in`）：客人/房号/离店 + 「账单」深链 `/billing?booking=&room=`。
- 待清扫（`vacant_dirty` 房）：房号/楼层/状态 + 「派单」跳转清扫工单。
- 侧边栏新增「前台接待」(`/reception`，`DesktopOutlined`)，置于房态盘之后。

### 验证

- 纯前端聚合，无后端/模型/迁移变更：**pytest 基线 194 passed 不变**；**前端 `vite build` ✅**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**（API 未变）；后端无需重启。

---

## ⑨ 宾客档案 / 客史（对齐绿云 Guest Profile，M14 FR-GUEST）

绿云前台对所有到店客人（散客 + 会员）维护统一客史档案。本系统原仅有会员 CRM（`members`），缺散客客史与证件/偏好/标签维度，故新建 `Guest` 宾客档案模型，覆盖全部客人，并复用预订入住钩子自动累计客史。

### 数据模型（`app/models/guest.py` + 迁移 `b1c2d3e4f5a6_guest_profile.py`）

- `guests` 表：tenant_id / hotel_id（归属门店）/ name / phone（同租户唯一）/ id_type / id_no / vip_level / gender / birthday / email / address / tags(JSON) / notes / stay_count / total_spend(分) / member_id（可关联会员）。
- 与 `members` 区别：会员是储值/积分体系；宾客档案是统一的到店客史视图，建档不强制会员身份，会员经 `member_id` 可选关联。
- 迁移链已接回真 head `271462418bcd`（通知接收人迁移）：`... → 271462418bcd → b1c2d3e4f5a6`；时间列 `nullable=False` 对齐基线约定，`alembic check` 零漂移。

### 服务层（`app/services/guest_service.py`）

- `create`（同租户同手机号视为同一客人，不重复建档）、`get`、`list`（支持 hotel_id + keyword 模糊匹配 name/phone/id_no）、`search`（phone / name）、`update`、`record_stay`（入住钩子：按手机号 upsert 并 `stay_count+1`、`total_spend` 累加；新建时显式置初值，规避列默认未加载导致的 `None+=1` 异常）。

### 入住钩子（`app/services/booking_service.py::check_in`）

- 入住成功后异常安全地调用 `GuestService.record_stay`（手机号来自 `booking.guest_phone`，房费来自 `booking.total_price`）→ 自动累计客史，失败不影响入住主流程。

### API（`app/api/routes.py` + `app/api/schemas.py`）

- `POST /tenants/{tenant_id}/guests`（建档，201）、`GET /guests/{guest_id}`、`GET /guests`（列表 + keyword + 分页）、`GET /guests/search`（phone/name 搜索；路由置于 `/guests/{guest_id}` 之前避免被参数路由吞掉）、`PATCH /guests/{guest_id}`。响应 `GuestOut` 经 `field_validator` 将 tags 的 JSON 文本解析为数组。

### 前端（`web/src/pages/Guests.tsx` + `endpoints.ts` + `types.ts` + `App.tsx` + `layout/AppLayout.tsx`）

- 宾客档案列表（姓名/手机号/证件/等级 Tag/客史标签/入住次数/累计消费 ¥）+ 关键字搜索（姓名/手机号/证件号）+ 新建/编辑抽屉（门店/姓名/手机/证件/等级/性别/邮箱/地址/标签/备注）；侧栏新增「宾客档案」(`/guests`)。

### 客档联动会员（建档/入住按手机号自动关联 member_id，FR-GUEST-LINK）

绿云前台在宾客档案直接呈现会员身份（等级/积分/储值），到店即识别会员。本系统在 ⑨ 基础上做紧耦合增量：在 `GuestService` 新增 `_link_member_by_phone`，于建档（`create` 的 existing/new 两路径）与入住（`record_stay` 末尾）按手机号查 `members`（租户内跨店共享），命中且 `guest.member_id` 为空则写入 `member_id`；API 层 `_enrich_guests_with_member` 批量回填关联会员的 `level`/`points`/`stored_value` 至 `GuestOut`（`member_level`/`member_points`/`member_stored_value`），避免 N+1，覆盖 `search`/`get_guest`/`list_guests`/`update_guest`/`create_guest` 全部读路径。建档即返回关联（原 `create_guest` 漏 enrich 已修复）。

### 测试（`tests/test_guest.py::TestGuest`，9 例）

- 建档/查重(同手机返同 id)/无手机散客建档/搜索(phone·name·缺参 400)/编辑(notes·tags·vip)/列表 keyword/入住自动累计客史(stay_count≥1, total_spend>0)/建档按手机号自动关联会员并回填等级积分储值/入住后仍保留会员关联且客史继续累计（record_stay 幂等重关联）。

### 回归验证（本轮交付）

- **pytest 206 passed**（204 + 2 客档联动会员）；**alembic upgrade head + check 零漂移**（无模型/迁移变更）；**前端 `vite build` ✅**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**；后端已重启（task `oFBqtt`）加载最新代码，实时链路验证：建会员→同号建档宾客→返回 `member_id`/`member_level=NORMAL`/`member_points`/`member_stored_value` 全部回填。

### 绿云对齐进度

- 已完成：⑦ 在住房间续住/换房 + ⑧ 前台接待看板 + ⑨ 宾客档案/客史 + ⑨-联动会员（建档/入住按手机号自动关联 member_id）。
- 剩余可选：① 在住加床/同住人（已并入 ⑩）；② 团队/会议排房；③ 散客/预订统一接待办理流。

---

## ⑩ 在住附加服务：加床 / 同住人（对齐绿云前台操作台，M14-2 FR-GUEST-EXT）

绿云前台对在住房间可维护附加服务（加床、同住人）。本系统原 `bookings` 仅有主客人信息，缺加床数与同住人维度，故扩展 `Booking` 模型并接入在住房间操作面板。

### 数据模型（`app/models/booking.py` + 迁移 `c2d3e4f5a6b7_booking_extras.py`）

- `bookings` 新增 `extra_bed_count`（int，默认 0）、`companion_names`（Text JSON 数组，同住人姓名）。`Booking.companion_list` / `set_companions` 提供 JSON 解析与写入。

### 服务层（`app/services/booking_service.py`）

- `update_stay_extras(booking, extra_bed_count?, companion_names?, operator?)`：仅 `CREATED`/`CHECKED_IN` 可维护（退房后 409）；写审计事件。

### API（`app/api/routes.py` + `app/api/schemas.py`）

- `POST /tenants/{tenant_id}/bookings/{booking_id}/extras`（body `BookingExtrasIn`：extra_bed_count≥0 / companion_names 数组）。`BookingOut` 新增 `extra_bed_count` 与 `companion_names`（经 `field_validator` 解析 JSON 文本为数组）。

### 前端（`web/src/pages/RoomStatus.tsx` + `endpoints.ts` + `types.ts`）

- 在住房间详情弹窗新增「加床 / 同住人」两行展示；操作区新增「附加服务」按钮 → 抽屉式弹窗（`InputNumber` 加床数 + `Select(tags)` 同住人），保存调用 `updateBookingExtras`，并将返回写回 `dtBooking` 即时刷新。

### 测试（`tests/test_booking.py::TestBookingExtras`，3 例）

- CREATED 设附加服务（加床 2 + 同住人 2）、CHECKED_IN 设附加服务、CHECKED_OUT 后设附加服务返回 409。

### 回归验证（本轮交付）

- **pytest 204 passed**（201 + 3）；**alembic upgrade head + check 零漂移**；**前端 `vite build` ✅**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**；后端已重启（task `rhgUpm`）加载最新代码，OpenAPI 已确认 `/bookings/{id}/extras` 路由上线。

### 绿云对齐进度

- 已完成：⑦ 续住/换房 + ⑧ 接待看板 + ⑨ 宾客档案/客史 + ⑨-联动会员（建档/入住按手机号自动关联 member_id）+ ⑩ 在住附加服务（加床/同住人）+ ⑪ 散客/预订统一接待办理流。
- 剩余可选：① 团队/会议排房。

---

## ⑪ 统一接待办理（绿云前台散客/预订双模式入住，M14-3 FR-RECEPTION）

绿云前台把「到店办理」收敛为一站式入口：无论散客还是预订客人，前台在一屏内完成证件登记 → 排房 → 入住。本系统在既有 `BookingService.check_in`（房态/PSB/开账/客史）之上新增统一编排层，避免前端分别调建预订/建档/入住三个接口、并复用全部副作用。

### 服务层（`app/services/reception_service.py`）

- `ReceptionService.unified_check_in(tenant_id, hotel_id, operator, *, booking_id?, room_no, room_type_id?, guest_name?, guest_phone?, id_type?, id_no?, check_in_date?, check_out_date?)`：
  - **预订模式**（`booking_id` 给定）：校验预订存在且 `CREATED`；可选前台证件登记（`guest_phone`/`id_type`/`id_no`）→ 确保客档（含会员关联）+ 回写 `booking.id_doc_no` → 调 `BookingService.check_in`。
  - **散客模式**（`booking_id` 空）：必填 `room_type_id`/`guest_name`/`check_in_date`/`check_out_date`；自动建档（同手机号不重复、命中会员自动关联 `member_id`）→ 建预订（`channel=walk_in`，预锁房）→ 调 `BookingService.check_in`。
  - `hotel_id` 由路由解析：预订模式取 `booking.hotel_id`，散客模式从 `room_no` 反查 `room.hotel_id`，调用方无需显式传。

### API（`app/api/routes.py` + `app/api/schemas.py`）

- `POST /tenants/{tenant_id}/reception/check-in`（`body: ReceptionCheckInIn`，响应 `BookingOut`）。
- `ReceptionCheckInIn`：`room_no`（必填，前台指定物理房）+ `booking_id?` + `room_type_id?`/`guest_name?`/`check_in_date?`/`check_out_date?`（散客必填）+ `guest_phone?`/`id_type?`/`id_no?`（证件登记）+ `operator`。
- 校验失败映射：预订不存在→404；非 `CREATED` 预订/散客缺字段→409（与 check_in/booking 同口径）。
- **无模型/迁移变更**（纯服务编排 + 路由 + 前端）。

### 前端（`web/src/pages/Reception.tsx` + `endpoints.ts` + `types.ts`）

- 看板标题栏新增「接待办理」按钮 → Modal（`Tabs`：预订入住 / 散客登记）。房号 `Select` 仅列可排房（空净 / 预抵锁定）；预订 `Select` 列 `CREATED` 预订（客人·房型·入住日·房号）。散客登记含房型/姓名/手机/证件/入住日(默认今日)/离店日(默认明日)。提交调 `receptionCheckIn`，成功提示并刷新看板。

### 测试（`tests/test_reception.py::TestReception`，5 例）

- 预订模式入住（status=checked_in、客史累计）/ 散客模式入住（channel=walk_in、客档自动建档并关联会员）/ 预订不存在 404 / 重复办理同一预订 409 / 散客缺字段 409。

### 回归验证（本轮交付）

- **pytest 211 passed**（206 + 5 接待办理）；**alembic check 零漂移**（无模型/迁移变更）；**前端 `vite build` ✅**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**；后端已重启（task `Yeor42`）加载最新代码，实时链路验证：散客办理→`checked_in`/`walk_in`/客档 `member_id` 关联+`stay=1`；预订办理→`checked_in`。

### 绿云对齐进度

- 已完成：⑦ 续住/换房 + ⑧ 接待看板 + ⑨ 宾客档案/客史 + ⑨-联动会员 + ⑩ 在住附加服务 + ⑪ 散客/预订统一接待办理流。
- 剩余可选：① 团队/会议排房。

## ⑬ 统一接待办理流基座（M1 基座，PRD ③ R1+R2）

⑪ 把「到店办理」收敛为一站式入口；本基座在其上补齐**单客上下文聚合（R1）**与**半自动编排状态机（R2）**，为 M2 工作台 UI（R3+R4）与 ①客档联动会员 联合排期提供后端骨架。决策沿用 PRD：Q1=扩展 `ReceptionService` 作编排层（非新建独立 service）；Q2=半自动（每步预填、「继续」确认、可回溯）。

### 状态机（`app/domain/reception_flow.py`）

- 流水线：`QUERY → REGISTER → CHECKIN → INHOUSE → FOLIO → CHECKOUT`。
- **状态不持久化**，始终由域派生（`derive_flow_state`：预订 `CHECKED_IN`→`INHOUSE`、`CREATED`→`REGISTER`、`CHECKED_OUT`→`CHECKOUT`、无/已取消→`QUERY`）；`FOLIO` 作为 `INHOUSE` 内的结账子阶段，由 UI 借 `open_folio` 动作提示，避免与入住自动开账冲突产生第二真相源。
- 仅 4 个有副作用动作：`register`（建档）/ `check_in`（排房+入住）/ `open_folio`（确认在开账单）/ `check_out`（退房）。`ALLOWED_ACTIONS` 守卫非法流转，失败抛 `InvalidReceptionTransition`（API→409）。

### 服务层（`app/services/reception_service.py`）

- `ReceptionService.get_context(tenant_id, *, guest_phone?, booking_id?, room_no?, hotel_id?)`：**只读聚合**（零写），按 `booking_id → room_no(在住预订) → guest_phone(最新预订)` 定位，返回 `ReceptionContext`：`guest`(客档+联动 `member_level`)/`membership`(CRM)/`booking`(含间夜)/`room_no`+`room_state`/`folio`(在开账单摘要，含 `balance`/`item_count`/`payment_count`)/`audit_log`(该预订最近 10 条) + `flow_state`(派生) + `can_advance`(可继续动作，供 UI 单步按钮)。
- `ReceptionService.advance(tenant_id, action, *, guest_phone?, booking_id?, room_no?, hotel_id?, …)`：R2 编排驱动。先取当前上下文判定 `flow_state`，校验动作合法后委托既有服务回写各域：`register`→`GuestService.create`（同手机号幂等）；`check_in`→`unified_check_in`（散客模式由房号反查 `hotel_id`，与路由一致）；`open_folio`→幂等确保 `OPEN` 账单（无则 `CashierService.open_bill`）；`check_out`→`BookingService.check_out`。动作后重定位上下文返回。

### API（`app/api/routes.py` + `app/api/schemas.py`）

- `GET /tenants/{tenant_id}/reception/context`（`response_model=ReceptionContext`，query：`guest_phone?`/`booking_id?`/`room_no?`/`hotel_id?`）。
- `POST /tenants/{tenant_id}/reception/advance`（`body: ReceptionAdvanceIn`，`response_model=ReceptionContext`）。非法流转/缺参→409。
- 新增 schema：`ReceptionContext` / `ReceptionGuestOut` / `ReceptionMembershipOut` / `ReceptionBookingOut` / `ReceptionFolioOut` / `ReceptionAuditOut` / `ReceptionAdvanceIn`。
- **无模型/迁移变更**（纯服务编排 + 域状态机 + 路由 + schema）。

### 测试（`tests/test_reception.py::TestReceptionFlow`，5 例）

- 全新客人 `get_context`→`query` 且 `can_advance` 含 `register`/`check_in`；入住后 `get_context` 聚合客档/会员/预订/房态(`occupied`)/在开账单/审计全链路；`advance` 走 `register→check_in` 半自动单步（`query→inhouse`）；`open_folio→check_out`（`inhouse→checkout`）；非法流转（query 态 `open_folio`）→409。

### 回归验证（本轮交付）

- **pytest 228 passed**（223 + 5 M1 基座；0 失败，无回归）；**alembic check 零漂移**（无模型/迁移变更）；前端无文件改动（M1 属后端/架构范围，M2 再补工作台 UI）。

## ⑭ 统一接待工作台 UI（PRD ③ M2，R3 一站式 + R4 续住/换房）

在 ⑬ 基座之上补齐**前端一站式办理工作台**，消费 `get_context` + `advance`：单页聚合「客档·会员·预订·房态·账单·审计」，以 Steps 呈现办理流进度（`query→register→checkin→inhouse→folio→checkout`），并把 `can_advance` 渲染为「继续」按钮（半自动：每步预填、确认、可回溯，对齐 PRD Q2）。

### 新增页面 `web/src/pages/ReceptionWorkbench.tsx`（路由 `/reception-workbench`，侧栏「统一接待台」）

- **查询栏**：手机号 / 预订号 / 房号（后端按 `booking_id → room_no → guest_phone` 优先级定位）。
- **单客全貌六卡片**：客档（`stay_count`/`total_spend` 分→元）、会员（CRM `level`/`stored_value`/`points`/`stays`）、预订（渠道/房型/房号/日期/状态）、房态（`room_no`+`room_state` 标签）、在开账单（`bill_no`/`balance` 分→元/笔数）、审计轨迹（Timeline）。
- **动作区**：`can_advance` 渲染为「继续」按钮（`register`/`check_in`/`open_folio`/`check_out`），点击弹 Modal 预填对应字段（建档需门店+姓名；散客 `check_in` 需房号+姓名+日期，房号反查 `room_type_id`；预订 `check_in` 复用既有预订号；`open_folio`/`check_out` 确认式）。执行后自动 `refresh` 重取上下文刷新进度。
- **在住附加（R4）**：`flow_state==inhouse` 时暴露「续住」/`换房」按钮，复用既有 `extendStayBooking` / `changeRoomBooking`（`booking/{id}/extend-stay`、`/change-room`）原子编排，执行后重取上下文。

### 前端契约

- `web/src/api/types.ts`：新增 `ReceptionContext` / `ReceptionGuest` / `ReceptionMembership` / `ReceptionBooking` / `ReceptionFolio` / `ReceptionAudit` + 联合类型 `ReceptionFlowState` / `ReceptionAction`（与后端 schema 字段一一对应，金额单位均为分）。
- `web/src/api/endpoints.ts`：新增 `receptionContext(tenantCode, opts)`（GET）/ `receptionAdvance(tenantCode, body)`（POST），复用既有 `extendStayBooking`/`changeRoomBooking`。
- `web/src/App.tsx`：`/reception-workbench` → `ReceptionWorkbench`；`web/src/layout/AppLayout.tsx`：侧栏新增「统一接待台」入口（紧邻「前台接待」）。

### 回归验证（本轮交付）

- **vite build 通过**（3134 modules transformed，exit 0）；前端 0 TypeScript 运行期错误（esbuild 转译通过）。
- 后端无变更：**pytest 228 passed**（10/10 接待路由级用例覆盖 `context`/`advance` 全链路）、**alembic 零漂移**。
- 说明：本仓库未配置 Playwright 等 E2E 目录，且当前无运行中的 8000/5173 服务；工作台所依赖的 `context`/`advance` 后端链路已由 TestClient 路由级用例（同 ASGI 应用）完整覆盖，故未重复拉起服务做浏览器冒烟。

## ⑮ 统一接待增强：客史洞察（PRD ③ M3，R7；R6 房态联动已随基座满足）

在 ⑭ 工作台之上补齐 **R7 客史洞察**（只读派生、零写），让前台一键识别常客/VIP/高价值/偏好；**R6 房态联动** 由 ⑬ 基座的 `unified_check_in`/`check_out` 副作用（房态转在住/退房）与工作台的 `room_state` 实时反映共同满足，无需额外改动。R5 批量办理已由 ⑫ 团队排房覆盖；R8 AI 预填依赖 LLM 接入，归入 v2。

### 后端（`app/services/reception_service.py` + `app/api/schemas.py`）

- `ReceptionService._derive_insights(guest, membership)`：基于聚合后的 `Guest`/`Member` 派生可读提示——`常客 · 第 N 次入住`(stay_count≥3)、`VIP 等级`、`会员等级（储值/积分）`、`高价值客户 · 累计消费`（total_spend≥1000 元）、`标签：X`、`客史备注：X`。
- `ReceptionContext` schema 新增 `insights: list[str]`（纯 schema 字段，**无模型/迁移变更**）。
- 命中逻辑：`get_context` 聚合完客档/会员后调用 `_derive_insights` 注入返回。

### 前端（`web/src/pages/ReceptionWorkbench.tsx` + `types.ts`）

- `ReceptionContext` 类型新增 `insights: string[]`。
- 工作台在 Steps 进度条下方新增「客史洞察」绿色 Banner，以 `Tag` 逐条呈现 `insights`（无洞察时整块隐藏，避免噪声）。

### 测试（`tests/test_reception.py::TestReceptionFlow::test_context_insights_r7`）

- 散客入住 → 经既有 API 回填客档 `vip_level=GOLD`/`tags=[吸烟房,高楼层]`/`notes=偏好安静` → 重取 `context`，断言 `insights` 含「VIP 等级：GOLD」「标签：吸烟房」「标签：高楼层」「客史备注：偏好安静」。

### 回归验证（本轮交付）

- **pytest 229 passed**（228 + 1 R7 洞察；0 失败，无回归）；**alembic check 零漂移**（无模型/迁移变更）；**vite build 通过**（3135 modules transformed，exit 0）。

## ⑯ 客档联动会员·深度联动（PRD ①，前台现场办会员并关联客档）

在 ⑬ 基座「按手机号自动关联既有会员」之上，补齐**主动办会员**能力：前台在办理流中可现场为客人开通会员，并回写客档 `member_id`，实现「建档即会员」的深度联动（① 客档联动会员主线）。

### 后端（状态机 + 编排层 + 路由提交修复）

- `ReceptionAction` 新增 `ENROLL_MEMBER = "enroll_member"`；`ALLOWED_ACTIONS` 在 `QUERY / REGISTER / CHECKIN / INHOUSE / FOLIO` 均允许（终态 `CHECKOUT` 除外），即建档前/在住/结账全阶段均可办会员。
- `ReceptionService.advance` 新增 `ENROLL_MEMBER` 分支：解析归属门店（动作显式 > 在住预订 > 房号反查）→ `MemberService.register(tenant_id, hotel_id, guest.name, guest.phone)`（按手机号幂等，命中既有会员直接复用）→ 回写 `guest.member_id`（仅当本次新建或发生变更时）→ `flush`。
- 守卫：缺 `guest_phone` → 409「办会员需提供 guest_phone」；无对应客档 → 409「请先建档…后再办会员」；缺归属门店 → 409。
- **关键修复**：`reception_advance` 路由原缺 `await session.commit()`，`get_session` 退出仅关闭会话不自动提交，导致 register/enroll 等 flush 但未提交的写操作在请求后被回滚（跨请求读不到客档）。已在 `advance` 成功返回前补 `await session.commit()`，与 check_in 路径（复用 `BookingService.check_in` 内部提交）行为对齐。

### 前端（`web/src/pages/ReceptionWorkbench.tsx` + `types.ts`）

- `ReceptionAction` 类型新增 `"enroll_member"`；`ACTION_LABEL` 加「现场办会员」；`can_advance` 含该动作即渲染「继续」按钮。
- 办会员 Modal：复用门店 `Select`（预填当前 `hotel_id`），确认后 `POST /reception/advance`（`action=enroll_member`）并自动重取上下文。

### 测试（`tests/test_reception.py::TestReceptionFlow`）

- `test_advance_enroll_member_links_guest`：register 建档 → enroll_member 办会员 → 断言 `membership.level==NORMAL`、`guest.member_id == membership.member_id`、`insights` 含「会员等级：NORMAL」；第三次同手机号幂等重办 `member_id` 不变。
- `test_advance_enroll_member_requires_guest`：无客档直接办会员 → 409「先建档」。

### 回归验证（本轮交付）

- **pytest 231 passed**（229 + 2 办会员；0 失败，无回归）；**alembic check 零漂移**（无模型/迁移变更）；**vite build 通过**（3136 modules transformed，exit 0）。
- 关键链路验证：`register`（提交后跨请求可查）→ `enroll_member`（关联客档、幂等重办）端到端通过。

## ⑰ 统一接待·断网降级容错（PRD ③ 待确认项 Q4 关闭）

**目标**：接待上下文聚合多个下游域（会员主数据 / 在开账单 / 审计轨迹），任一暂不可用时**降级展示而非整页 500 白屏**，关闭 PRD Q4 开放问题。

### 后端（`app/services/reception_service.py` → `get_context`）
- 会员聚合、folio 聚合、audit 聚合三处分别 `try/except Exception`，异常时该字段置 `None/[]` 并追加 `degradation_notes`（如「审计轨迹暂不可用」），其余字段正常返回。
- 返回体新增 `degraded: bool`（由 notes 非空推导）与 `degradation_notes: list[str]`；`ReceptionContext` schema 同步新增两字段（纯 schema，**无模型/迁移变更**）。
- audit 提取抽为独立方法 `_load_audit_log`（便于单测注入故障）。

### 前端（`web/src/pages/ReceptionWorkbench.tsx` + `types.ts`）
- 类型 `ReceptionContext` 增 `degraded: boolean` / `degradation_notes: string[]`。
- 上下文 `degraded` 为真时渲染橙色 `Alert`「部分信息降级展示」，逐条 `Tag` 列出降级项，其余卡片照常展示。

### 测试（`tests/test_reception.py`，+2 例）
- `test_context_not_degraded_on_happy_path`：happy path `degraded=False`、`degradation_notes=[]`。
- `test_context_degrades_when_audit_aggregation_fails`：`monkeypatch` 注入 `RuntimeError` 到 `_load_audit_log`，断言返回 **200（非 500）** 且 `degraded=True`、含审计降级项、`booking`/`flow_state` 仍正确。

### 回归验证（本轮交付）
- **pytest 233 passed**（231 + 2 降级；0 失败，无回归）；**alembic check 零漂移**；**vite build 通过**（3137 modules transformed，exit 0）。

## ⑱ 开放 API 平台·第三方只读接口（M18 最后一公里）

**背景 / 缺口**：Sprint 13 已落地 M18 管理面（`/tenants/{code}/openapi/apps`·`/keys`·`/webhooks`，由登录会话 `require_auth` 保护，供管理员注册应用/管密钥/配 Webhook）+ `OpenApiService`（密钥生成/校验/吊销、HMAC 投递）+ `RateLimitMiddleware`。但**面向 ISV 的「持 API-key 读取数据的只读接口」与 `require_api_key` 鉴权依赖缺失**——这正是路线图「开放 API 平台」的核心面，`require_auth` 也已白名单 `/openapi/` 路径预留。

### 后端（`app/api/routes.py` + `app/services/openapi_service.py`）
- 新增依赖 `require_api_key`：解析 `Authorization: Bearer pms_xxx` → `OpenApiService.verify_key` → 解析出 `app_id`/`tenant_id`/`scopes`；密钥不存在/吊销/过期 → 401。复用既有 `OpenApiService`（含限流 key：`openapi:{app_id}`）。
- 新增 `/openapi/v1/...` 只读接口组（`token_scopes=["read"]`，仅读），复用既有查询与输出 schema：
  - `GET /openapi/v1/hotels` — 门店列表
  - `GET /openapi/v1/hotels/{hotel_id}/rooms` — 房态/房间列表
  - `GET /openapi/v1/hotels/{hotel_id}/availability` — 房量可用性
  - `GET /openapi/v1/tenants/{tenant_id}/bookings` — 预订列表（按状态/日期过滤）
  - `GET /openapi/v1/tenants/{tenant_id}/night-audit/board` — 跨店夜审看板（只读聚合）
- 所有接口强制 `scope=read`，无写操作；密钥体系沿用管理面已建流程。

### 前端
- **本轮无前端改动**：只读接口面向 ISV 服务端调用，无新增页面（管理面密钥/Webhook 配置页此前已存在）。

### 测试（`tests/test_openapi.py`，+5 例）
- `test_third_party_read_hotels`：创建应用→创建密钥→`Bearer pms_xxx` 调 `/openapi/v1/hotels` 返回 200 且含播种门店。
- `test_third_party_read_rooms` / `test_third_party_read_availability` / `test_third_party_read_bookings`：各只读接口 200 + 字段断言。
- `test_third_party_requires_key` / `test_third_party_invalid_key`：无密钥→401、伪造密钥→401。
- `test_third_party_night_audit_board`：夜审看板 200 + `hotel_count` 字段。

### 回归验证（本轮交付）
- **pytest 238 passed**（含 openapi 12 例：7 既有 + 5 新增；0 失败，无回归）；**alembic check 零漂移**（无模型/迁移变更）；**vite build 通过**（无前端改动）。
- 关键链路：管理面注册应用→签发密钥→第三方 `Bearer` 调只读接口全 200；鉴权失败一律 401。

## ⑲ 餐饮 POS（F&B，M21）

**背景 / 缺口**：PMS 既有 `CashierService`/`Bill` 财务内核（余额 = Σ应收 − Σ实收，WORM 账项）仅服务于房账与杂费。餐饮消费（菜品/餐桌/开单点菜/结账）此前**完全缺失**（无 model、无 service、无路由、前端无 Pos 页），是绿云前台「餐饮收银」块的真实业务面。M21 将其实现为**编排层**：不新建独立账务体系，餐饮消费统一经 `CashierService` 入账到 `Bill`，保证财务口径一致、无双账本漂移。

### 数据模型（`app/models/fnb.py`）
- `MenuItem`（菜品，租户级，可按门店下架 `is_active`）：`hotel_id` / `name` / `category`(热菜/凉菜/酒水/主食) / `price_cents` / `is_active`。
- `DiningTable`（餐桌/桌台）：`hotel_id` / `table_no` / `seats` / `zone`(大厅/包厢) / `state`(free|occupied|cleaning，仅供前厅可视化，不影响账务)。
- `PosOrder`（餐饮账单，开单→点菜→结账）：`hotel_id` / `table_id`(可选关联餐桌) / `status`(open|settled) / `settle_type`(room|cash) / `room_no` / `booking_id` / `guest_name` / `total_cents`(累计应收)。
- `PosOrderItem`（点菜明细行）：`order_id` / `item_id`(可选关联菜品) / `name` / `qty` / `unit_price_cents` / `subtotal_cents`(= 单价×数量，加菜时回写 `order.total_cents`)。
- 迁移 `e4f5a6b7c8d9`（down_revision `d3e4f5a6b7c8`）：建四表及索引；列约束与模型一致（非可选注解 `Mapped[X]` 经 SQLAlchemy 2.0 推断 `NOT NULL`）。

### 后端（`app/api/routes.py` + `app/services/fnb_service.py` + `app/services/permissions.py`）
- **`PosService`**：`create_menu_item` / `list_menu_items`(默认仅上架) / `update_menu_item`(部分更新，仅写显式字段) / `create_table` / `list_tables` / `set_table_state`(校验 free|occupied|cleaning) / `open_order`(占用餐桌 state→occupied) / `add_order_item`(回写 `order.total_cents`，已结账拒绝) / `list_orders`(可按 status 过滤) / `settle_room`(挂房账) / `settle_cash`(现金)。
- **两类结账复用 CashierService**：
  - `settle_room`：经 `open_bill`(source=FNB) + `add_charge(FNB, 应收)` 计入客房在开账单（按房号 `_resolve_booking_id` 找 CHECKED_IN 预订，无则在住开街客账）；保持 `Bill.OPEN`（随房账退房时结），`PosOrder` 置 `settled` + `settle_type=room`，餐桌释放为 `cleaning`。
  - `settle_cash`：经 `open_bill` + `add_charge(FNB)` + `take_payment(CASH)` + `settle`(内部 commit，须平账)；`PosOrder` 置 `settled` + `settle_type=cash`，餐桌释放为 `cleaning`。
- **权限**：`permissions.py` 新增 `FNB_MANAGE="fnb.manage"`，加入 `ALL_PERMISSIONS`，并赋予「门店经理」「前台」角色；11 个 `/fnb/*` 端点均 `dependencies=[Security(require_perm, scopes=[FNB_MANAGE])]`。

### 前端（`web/src/pages/Pos.tsx`，M21 点单工作台）
- **入口**：侧边栏新增「餐饮 POS」（`/pos`，`CoffeeOutlined`），`App.tsx` 注册路由，`AppLayout.tsx` 菜单新增项。
- **类型与 API 客户端**：`web/src/api/types.ts` 新增 `MenuItem` / `DiningTable` / `PosOrder` / `PosOrderItem`；`web/src/api/endpoints.ts` 新增菜品/餐桌/餐饮账单的 list / create / patch（菜品上下架）/ set_table_state / open_pos_order / add_pos_order_item / settle_pos_room / settle_pos_cash / list_pos_orders，路径严格对齐 `routes.py` 的 `/fnb/*` 端点（F&B 端点均需 `FNB_MANAGE`）。`hotel_id` 入参按前端 `useTenant().hotelId`（string）实际类型收 `number | string`，发送前 `Number()` 化，保证后端 `int` 字段一致。
- **页面能力**：左栏桌台网格（点击开/选单 + 状态 free/occupied/cleaning 切换）+ 在开账单列表（切换当前单）；右栏当前账单——菜品目录（搜索 + 分类过滤，点「加1」按目录单价加菜）、手动加菜（非目录菜品，单价按元录入）、已点明细（数量/单价/小计）、挂房账（需房号，消费计入客房在开账单）与现金结账（金额留空按总额）；顶部「菜品管理」抽屉支持新增菜品（菜名/分类/价格）。全部复用 antd + `useTenant` 约定，对齐 `Billing.tsx` 写法。
- **构建验证**：`npm run build`（`tsc --noEmit && vite build`）通过，0 类型错误。顺带修复两处既有 tsc 错误（`endpoints.ts` 漏导 `ReceptionCheckIn`、`Guests.tsx` 误从 endpoints 导入 `Guest/GuestIdType/GuestVipLevel` 类型）。

### 报表与厨房出单（M22）
**模型扩展**（`app/models/fnb.py`）：`PosOrderItem` 新增 `category`（冗余自 `MenuItem.category`，手动加菜兜底「其他」，供品类销售报表免 join）与 `kds_status`（`pending`→`ready`→`served`）。迁移 `f1a2b3c4d5e6`（down_revision `e4f5a6b7c8d9`）以 batch 方式给 `pos_order_items` 加两列；`add_order_item` 落库时回填 `category`。

**餐饮报表**（`app/services/fnb_service.py` + `report_sales`）：仅统计已结账(`settled`)餐饮账单，按 `PosOrder.created_at` 可选时间窗过滤，聚合：总营收 / 单数 / 总件数 / **品类销售**（按 `category` 汇总 qty 与营收）/ **桌均消费**（仅关联餐桌的账单，按桌号汇总后求均值）。端点 `GET /tenants/{t}/fnb/reports/sales`（`FNB_MANAGE`，query: `hotel_id` 必填、`start`/`end` 可选）。

**厨房出单 KDS**（`list_kitchen_tickets` / `mark_item_ready` / `mark_item_served`）：取待做/已出餐菜品行（默认 `pending|ready`，按下单顺序）附账单上下文（桌号/房号/客人）；`POST .../items/{item_id}/ready` 标记出餐、`/served` 标记上菜（均 `FNB_MANAGE`）。出单屏实时轮询，状态推进即驱动后厨动作。

**前端**：`Pos.tsx` 新增「报表」抽屉（总营收/已结单数/桌均消费三张统计卡 + 品类销售表 + 桌均消费表，数据来自 `fnbReport`）；新增 `web/src/pages/Kds.tsx` 厨房出单屏（按出单位置分组卡片、待做出餐/已出餐上菜按钮、15s 轮询），`App.tsx` 注册 `/kds`，`AppLayout.tsx` 侧栏新增「厨房出单」（`FireOutlined`）。`types.ts`/`endpoints.ts` 补齐 `FnbReport`/`KitchenTicket` 类型与 `fnbReport`/`listKitchenTickets`/`markItemReady`/`markItemServed` 客户端函数。`npm run build` 通过、0 类型错误。

### 测试（`tests/test_fnb.py`，12 例）
- 菜品 CRUD + 列表（默认仅上架 / 下架后 `active_only` 过滤）。
- 餐桌生命周期 free→occupied→cleaning→free；非法状态 → 409。
- 开单 → 加菜（金额累计 `total_cents`）→ 现金结账：返回 200 + `settle_type=cash`，餐桌释放 `cleaning`，并经 `GET /bills?source=FNB` 验证入账到 `Bill`（状态 `SETTLED`、余额 0、含 `FNB` 应收项）。
- 挂房账结账：返回 200 + `settle_type=room` + `room_no`，`Bill` 保持 `OPEN`（随房账结），餐桌释放 `cleaning`。
- 账单列表 + `status` 过滤。
- 餐饮报表：开台→点菜单品(带品类)+手动菜(兜底其他)→现金结账，经 `GET /fnb/reports/sales` 校验总营收/单数/品类销售/桌均消费聚合正确（未结账账单不计入）。
- KDS：加菜后 `kds_status=pending`；出单屏默认取 `pending|ready`；`ready`→`served` 状态推进；`served` 后退出默认列表（`states=served` 仍可查）。

### 真实栈端到端冒烟
- `scripts/smoke_fnb_e2e.py`（M21，22/22 全绿）：真实 uvicorn + httpx 直打，覆盖开台现金结账 + 散客挂房账全链路及 `Bill` 入账联动；dev 库留隔离租户 `fnb-smoke-<时间戳>`。
- `scripts/smoke_fnb_m22.py`（M22，13/13 全绿）：真实 uvicorn + httpx 直打，覆盖报表聚合（总营收/品类销售/桌均消费）+ KDS 状态流转（pending→ready→served 及出单屏列表过滤）；dev 库留隔离租户 `fnb-m22-<时间戳>`。
- 以真实 uvicorn（`http://127.0.0.1:8000`）+ httpx 直打，**不走 TestClient**，验证 F&B 在真实 HTTP 栈下生效；覆盖：`POST /tenants`(白名单免认证) → 登录(`admin/admin123`) → 开通酒店 → 菜品/餐桌(`state` 切 occupied) → **链路A** 开台(关联餐桌)→加菜(目录单价×2=6400 + 手动价 4800)→现金结账(`status=settled`/`settle_type=cash`/`total=11200`，`Bill` SETTLED/余额0/已挂 CASH 收款)→餐桌释放 `cleaning`→已结账加菜 409 → **链路B** 散客开单(挂房账)→加菜(19800)→挂房账(`settle_type=room`/`room_no=808`，`Bill` 保持 OPEN)，再经 `GET /bills?source=FNB` 校验两类账单入账联动。冒烟在 dev 库留隔离租户 `fnb-smoke-<时间戳>`，不污染业务数据。
- 边界：金额为 0 结账 → 409；已结账账单再加菜 → 409。
- 权限守卫（`@pytest.mark.auth` 退出 admin 旁路）：无 token → 401；前台（含 `fnb.manage`）→ 200；自定义无 `fnb.manage` 角色 → 403。

### 回归验证（本轮交付）
- **全量 pytest 通过**（含 fnb 10 例，0 失败、无回归）；**alembic check 零漂移**（迁移 `e4f5a6b7c8d9` 与模型一致）；**vite build 通过**（无前端改动）。
- 关键链路：开单→点菜→现金/挂房账两类结账全通，餐饮消费经 `CashierService` 入账到 `Bill`，财务口径一致。

## ⑫ 团队 / 会议排房（对齐绿云前台团队块，M15 FR-GROUP）

绿云前台对旅游团、会议等批量到店客人提供「团队排房」：先把若干物理房间作为一个 block 分配（锁房预留），到点一键批量入住。本系统将其实现为编排层——排房只是「房间分配 + 批量入住」的编排，入住仍复用 `BookingService.check_in` 的全部副作用（房态/PSB/开账/客史/会员关联），与会员 CRM、宾客档案、预订引擎解耦。

### 模型（`app/models/group_block.py` + 迁移 `d3e4f5a6b7c8_group_block`）

- `GroupBlock`（团队块）：`hotel_id`/`name`/`arrival_date`/`departure_date`/`status`(draft/active/closed，默认 active)/`notes`；多租户 `tenant_id` + 雪花主键。
- `GroupAllocation`（房间分配）：`block_id`/`room_id`/`room_no`/`room_type_id`/`guest_name?`/`guest_phone?`/`status`(assigned/checked_in/checked_out，默认 assigned)。
- 迁移已接回真 head（`down_revision=c2d3e4f5a6b8` → `d3e4f5a6b7c8`），时间列 `nullable=False` 对齐基线约定，`alembic check` 零漂移。

### 服务层（`app/services/group_block_service.py`）

- `GroupBlockService.create_block`：校验 `departure_date > arrival_date`（否则 409）。
- `assign_rooms`：仅空净房可排；排房即 `RoomTrigger.LOCK_FOR_ARRIVAL`（空净→预抵锁定）锁房预留；已被其他活动 block 占用的房 409（防重排）；已关闭 block 拒绝排房。
- `check_in_block`：对每个 `assigned` 分配——按 `guest_phone` 建档（命中会员自动关联）→ 建 `channel=group` 预订（按 block 抵离店日）→ `BookingService.check_in`（房态转在住 + 全部副作用）→ 分配置 `checked_in`；已关闭 block 拒绝入住。
- `close_block`：置 `closed`，关闭后不可再排房 / 入住（409）。

### API（`app/api/routes.py` + `app/api/schemas.py`）

- `POST /tenants/{tenant_id}/group-blocks`（`GroupBlockCreate`，201）/ `GET .../group-blocks`（list，可按 `hotel_id` 过滤）/ `GET .../group-blocks/{block_id}`。
- `POST .../group-blocks/{block_id}/assign`（`GroupBlockAssignIn`，排房锁房）/ `POST .../group-blocks/{block_id}/check-in`（批量入住）/ `POST .../group-blocks/{block_id}/close`（关闭）。
- 校验映射：block 不存在→404；离店≤抵店、非空净房、重复排房、关闭后操作→409。
- `_group_block_out` 聚合 `allocations`（Pydantic v2 `model_validate` 构造）。

### 前端（`web/src/pages/GroupBlock.tsx` + `endpoints.ts` + `types.ts` + 路由/侧栏）

- 独立「团队排房」页（侧栏挂「运营中心」分组，`/group-blocks`）：列表展示团队块（门店/抵离店/状态/排房数）。
- 「新建团队排房」Modal：名称/抵店/离店/备注。抽屉内可对生效中 block「添加房间」（Form.List 动态行，房号仅列空净且未被本 block 占用、自动带出房型）+「确认排房」（锁房预留）+「批量入住」+「关闭」。
- `endpoints`：`listGroupBlocks`/`getGroupBlock`/`createGroupBlock`/`assignGroupBlockRooms`/`checkInGroupBlock`/`closeGroupBlock`；`types`：`GroupBlock`/`GroupAllocation`。

### 测试（`tests/test_group_block.py::TestGroupBlock`，6 例）

- 建块→排房锁房→批量入住（房态落地 `occupied`、生成 2 笔 `group` 渠道预订、带手机号客档建档）/ block 不存在 404 / 占用房排房 409 / 同房两 block 重复排房 409 / 关闭后不可再入住 409 / 离店≤抵店 409。

### 回归验证（本轮交付）

- **pytest 217 passed**（211 + 6 团队排房）；**alembic check 零漂移**；**前端 `vite build` ✅**；**E2E 10/10 默认 / 13/13 `--mutate` 通过**；后端已重启加载最新代码，实时链路验证：建块→排房（402/404 `arrival_locked`）→批量入住（转 `occupied`、2 笔 group 预订）→关闭（`closed`）→关闭后再入住 409。

### 绿云对齐进度（全部完成）

- 已完成：⑦ 续住/换房 + ⑧ 接待看板 + ⑨ 宾客档案/客史 + ⑨-联动会员 + ⑩ 在住附加服务（加床/同住人）+ ⑪ 散客/预订统一接待办理流 + ⑫ 团队/会议排房 + ⑬ 统一接待办理流基座（M1，PRD ③ R1 单客上下文 + R2 编排状态机）+ ⑭ 统一接待工作台 UI（M2，PRD ③ R3 一站式 + R4 续住/换房）+ ⑮ 统一接待增强·客史洞察（M3，PRD ③ R7）+ ⑯ 客档联动会员·深度联动（现场办会员并关联客档，PRD ①）+ ⑰ 统一接待·断网降级容错（关闭 PRD ③ Q4）+ ⑱ 开放 API 平台·第三方只读接口（M18 最后一公里，API-key 鉴权 `require_api_key` + `/openapi/v1` 只读面）。
- 绿云前台核心操作界面业务功能已全部对齐，无剩余可选项。


## M23 前台运营深度（64 项验收清单 #3 / #4 / #11）

### NoShow 自动处理（#3）
- `BookingStatus` 新增 `NOSHOW`；`bookings.noshow_reason` 记录原因（迁移 `a7b8c9d0e1f2`）。
- **夜审自动**：`NightAuditService._auto_noshow` 扫描「逾期应到未到」（`status=CREATED` 且 `check_in_date < 营业日`）→ 标记 NoShow + 记录原因；已锁房（`arrival_locked`）经 `RELEASE_ARRIVAL` 释放为空净可售；快照记录 `noshow.count/booking_ids`。
- **前台手动**：`POST /tenants/{t}/bookings/{id}/noshow`（复用 `BOOKING_CANCEL` 权限），非 CREATED 状态返 409；审计留痕 `booking.noshow`。
- 前端：`Bookings.tsx` 新增「未到店」操作 + `noshow` 状态标签（橙色）。

### 客人多维检索（#4）
- `GET /tenants/{t}/guests/search` 新增 `id_no`（证件号）与 `booking_id`（订单号）参数；订单号经预订 `guest_phone`/`id_doc_no` 反查客档。
- 前端 `Guests.tsx` 智能判别：纯数字 ≤6 位→订单号、7~14 位→手机号、≥15 位→证件号，其余→姓名。

### 交班三口径（#11）
- `shift_handovers` 新增 `received_cents`（班内实收，全支付方式）/ `receivable_cents`（班内应收，正向条目）。
- `close_shift` 自动核对：**现金流**（备用金+班内现金 vs 实点，差异照旧）+ **实收/应收** 两口径随班次沉淀；`ChargeIn` 补 `operator` 贯通加账操作员。
- 前端 `Shifts.tsx` 交班表新增「班内实收 / 班内应收」列。

### 验收对照
| 门禁 | 结果 |
|---|---|
| pytest | **258 例全绿**（0 错 0 失败，M23 新增 8 例） |
| alembic | `a7b8c9d0e1f2` 零漂移 |
| 前端 `npm run build` | tsc 0 错 + vite 通过 |
| 真实栈 E2E | `scripts/smoke_m23_frontdesk.py` **14/14** |

## M24 前台深度 II：协议挂账月结 / 时租房 / 智能排房（64 项清单 #10 / #1 / #5）

### 公司协议挂账月结（#10）
- 新模型 `ArAccount`（协议单位：信用额度、未清欠款 `balance_cents`）+ `ArRepayment`（还款流水）；`bills.ar_account_id` 回填挂账关联（迁移 `b8c9d0e1f2a3`，batch + 命名 FK，零漂移）。
- 挂账 = `ArService.settle_to_account`：整笔余额以 `COMPANY` 方式收款 → 账单 `SETTLED` → 协议单位欠款累计；`credit_limit_cents > 0` 时超额挂账返 409。
- 还款冲减欠款并落 `ArRepayment`；审计 `ar.account.create` / `ar.bill.charge` / `ar.repay`。
- 路由：`GET/POST /ar-accounts`、`GET /ar-accounts/{id}/bills`、`POST /ar-accounts/{id}/charge`、`POST /ar-accounts/{id}/repayments`。
- 前端新增 `ArAccounts.tsx`（`/ar-accounts`，侧栏「协议挂账」）：单位列表 / 新建 / 挂账（选未结清账单）/ 还款 / 挂账账单抽屉。

### 时租房按小时计价（#1）
- `RoomType.hourly_rate`（分/小时，空则按日价 1/4 折算）；`Booking.stay_type=daily|hourly` + `hourly_hours`。
- 创建预订：时租允许同日入住退房，总价 = 时租价 × 小时数；夜审过账跳过时租房（即住即结，防整晚重复计费）。
- 前端新建预订表单支持「住宿类型」切换 + 时长输入。

### 智能排房推荐（#5）
- `GET /tenants/{tenant}/rooms/recommend`：候选 = 空净(100)/空脏(60)，排除在住/锁房/维修/停用；
  评分 = 状态基分 + 曾住过该房 +50 + 历史楼层一致 +30 + 多房型时同房型 +10；返回评分与理由。
- 前端 `Bookings.tsx` 新增「智能排房」行操作 → 推荐弹窗（匹配度 + 理由 + 一键入住此房）。

### 验收对照
| 门禁 | 结果 |
|---|---|
| pytest | **266 例全绿**（0 错 0 失败，M24 新增 8 例） |
| alembic | `b8c9d0e1f2a3` 零漂移（含 downgrade 往返） |
| 前端 `npm run build` | tsc 0 错 + vite 通过 |
| 真实栈 E2E | `scripts/smoke_m24_frontdesk.py` **20/20** |

## M25 店总 BI 深度（64 项验收清单 #19 / #16 / #15）

### 超卖预警（#19）
- `GET /tenants/{t}/analytics/oversell-warnings?hotel_id=&start_date=&end_date=`：逐日对比「在手预订量（created/checked_in，时租计入入住当日）」vs「可售房量（总房 − 维修 − 停用）」。
- 分级：`OVERSELL`（需求 > 供给）/ `CRITICAL`（恰好满房）。返回缺口 gap 与预警天数。
- 前端「经营分析 → 超卖预警」Tab：预警表 + 缺口红字 + 级别标签。

### 远期趋势 + 在手入住率（#16）
- `GET /tenants/{t}/analytics/forecast?hotel_id=&days=14`：未来 N 天逐日**在手（OTB）入住率** + 近 14 天预订增速（Booking Pace）。
- 口径诚实标注：on-the-books 确定性口径，非统计预测；超卖时入住率可 >100%（即预警信号）。
- 前端「远期预测」Tab：预测表 + Pace 折线（SVG）。

### 自定义报表（#15）
- `GET /tenants/{t}/analytics/custom-report?group_by=room_type|channel|day&start_date=&end_date=`：按维度聚合预订数与房费收入，排除已取消/NoShow。
- 前端「自定义报表」Tab：维度下拉切换 + 汇总行。

### 验收对照
| 门禁 | 结果 |
|---|---|
| pytest | **272 例全绿**（0 错 0 失败，M25 新增 6 例） |
| 前端 `npm run build` | tsc 0 错 + vite 通过 |
| 真实栈 E2E | `scripts/smoke_m25_bi.py` **18/18**（含维修收缩触发超卖、非法 group_by 400） |

> 注：本 Sprint 为纯只读分析接口，无 schema 变更、无迁移。

## M26 客房深度 + M27 餐饮运营深度（64 项清单 #6 / #24 / #27 / #28 等）

### M26 客房深度
- **批量派单 / 批量完成**：`POST /housekeeping-tasks/batch-assign`（逐单尝试，返回 assigned/failed 明细）、`POST /housekeeping-tasks/batch-done`（逐单联动空脏→空净）；前端工单表支持多选 + 批量操作条。
- **多维过滤**：`GET /housekeeping-tasks` 支持 status / task_type / assignee / floor / hotel_id；前端状态、类型下拉 + 楼层、责任人输入即时过滤。
- **员工清扫绩效**：`GET /analytics/housekeeping-performance?hotel_id=&start_date=&end_date=`，按员工统计完成单数 + 平均耗时分钟（done_at - assigned_at）；前端「绩效」按钮展开绩效卡。

### M27 餐饮运营深度
- **沽清（86 拆出）**：`MenuItem.sold_out` 列（迁移 `c9d0e1f2a3b4`）；`POST /fnb/menu-items/{id}/sold-out` 标记/恢复；`add_order_item` 拒点沽清菜（409）；前端菜品目录与管理抽屉均有沽清开关。
- **退菜**：`PosOrderItem.voided / void_reason`；`POST /fnb/orders/{id}/items/{item_id}/void` 退菜重算总额（重复退 409，已结算拒退）；退菜行不计品类销售、不出现在厨房屏；折扣自动收敛至不超过新总额。
- **整单折扣**：`PosOrder.discount_cents`；`POST /fnb/orders/{id}/discount`（金额分或百分比 1-99 二选一，超总额 409）；现金/挂房结账均按折后净额入账；销售报表营收、桌均按净额；前端账单头显示划线原价 + 已优惠 + 折后应付 + 折扣弹窗。

### 验收对照
| 门禁 | 结果 |
|---|---|
| pytest | **280 例全绿**（0 错 0 失败，M26/M27 新增 8 例） |
| alembic | `c9d0e1f2a3b4` 零漂移（sold_out / voided / void_reason / discount_cents） |
| 前端 `npm run build` | tsc 0 错 + vite 通过 |
| 真实栈 E2E | `scripts/smoke_m26_m27_ops.py` **33/33**（含沽清拒点、重复退菜 409、超额折扣 409、净额入账联动） |

## M28 A2 收尾 + M29 OTA 直连 + M30 性能（64 项清单收口冲刺）

### M28-1 投诉与住客关联（#32 类）
- 新模型 `Complaints`（hotel/booking_id 关联、住客姓名/手机号/房号、source、category、status 流转 OPEN→HANDLING→RESOLVED/CANCELLED、handler/resolution/handled_at）。迁移 `d0e1f2a3b4c5`。
- 路由：`POST/GET /complaints`、`POST /complaints/{id}/transition`。**关联预订自动回填住客姓名/手机号/房号**；办结必须填处理结果；非法流转 409；审计留痕。
- 前端新增「投诉管理」页（/complaints）：登记（可填预订号回填）/ 受理 / 办结 / 状态过滤。

### M28-2 历史数据留存导出（#30 类）
- `GET /tenants/{t}/analytics/data-export?entity=bookings|bills|fnb_orders&start_date=&end_date=`：**流式 CSV（UTF-8 BOM，Excel 直接打开）**，逐批 500 行，内存占用恒定；导出动作写审计 `data.export`。与 M16 报表导出（`/analytics/export`）并存、路径区分。

### M29 OTA 渠道直连框架 + 沙箱（#12）
- 新模型 `OtaChannelConfig`（每租户每渠道：app_key/secret/push_enabled）；`bookings` 加 `external_channel/external_ref` 回链（含索引）。
- **订单注入**：`POST /tenants/{t}/ota/{channel}/webhook/orders`（公网端点，`require_auth` 白名单放行，改由 **HMAC-SHA256 签名**鉴权）。三级防重：签名校验 → external_ref 幂等查询（重推返回原单 created=false）→ 预订引擎房量守卫。
- **房量推送**：`POST /tenants/{t}/ota/{channel}/inventory/push?days=N`：按房型×日期聚合剩余房量；`sandbox` 渠道返回**确定性模拟回执**（trace_id 由 payload 内容哈希），真实渠道只需填 `push_inventory_url` 由渠道组补齐。
- 与既有 `app/channels/` 骨架（ctrip/meituan 适配器、ChannelType）打通。

### M30 性能与稳定性
- **dashboard 热点读缓存**：读路径查 cache（key=dashboard:{tenant}:{hotel}:{start}:{end}），TTL 30s 兜底；**预订创建/入住/退房写路径显式失效**（`BookingService._invalidate_dashboard_cache`）。房态缓存（Sprint 15）已有，模式一致。
- **索引审计**：补 `ix_bookings_hotel_checkin`（hotel_id+check_in_date 复合索引，可用性热点查询），已在 Booking 模型声明保持零漂移。
- **压测工具**：`scripts/load_test.py`（--spawn --concurrency N --requests M）：并发打点 rooms / dashboard，输出 RPS 与 p50/p95/p99；只读不污染数据。基线（20 并发 × 200 请求，本机 dev 单进程）：400 请求 0 错误，dashboard p95≈1.4s——单进程 dev 瓶颈，生产多 worker + Redis 上量后重测。

### 验收对照
| 门禁 | 结果 |
|---|---|
| pytest | **290 例全绿**（0 错 0 失败，M28-M30 新增 10 例） |
| alembic | `d0e1f2a3b4c5` 零漂移（complaints / ota_channel_configs / bookings 回链与索引） |
| 前端 `npm run build` | tsc 0 错 + vite 通过 |
| 真实栈 E2E | `scripts/smoke_m28_m30_ops.py` **19/19**（含签名拒绝、幂等重推、办结闭环、CSV BOM） |
| 压测 | `scripts/load_test.py` 400 请求 0 错误（工具链就绪，基线已记录） |

## M31 核心缺口关闭冲刺（58 项验收核心 3 缺口）

### #9 会员积分支付
- `POST /tenants/{t}/bills/{id}/pay-points`（1 积分 = 1 分）：校验会员与余额 → 扣减积分 → 落 `method=POINTS` 收款流水 + 审计 `payment.points`；积分不足 / 超账单余额 → 409。
- **防积分回流**：结账再累积积分时，累积基数扣除积分支付部分（`settle` 内 SUM(POINTS 支付)），堵套利闭环。

### #10 团队分批结账
- `POST /tenants/{t}/group-blocks/{id}/allocations/{alloc_id}/settle`：逐间结清（余额 >0 自动 CASH 补收 / <0 自动 CASH 退回）→ 结账 → 退房释放 → allocation 置 `checked_out`；返回该间状态 + 整团进度（`block_settled_count/total`）。
- `GET /tenants/{t}/group-blocks/{id}/settlement`：团主结算汇总（逐间账单状态 / 已结金额 / 进度）。重复结账 409。

### #34 免打扰（DND）房态
- `rooms` 表加 `dnd` 列（迁移 `e1f2a3b4c5d6`）；`POST /tenants/{t}/rooms/{room_no}/dnd` 开关 + 审计 `room.dnd`；房态图卡片「免打扰」紫标 + 详情弹窗 Switch。
- **DND 不影响可售状态**；**清扫派单守卫**：CLEANUP 工单派单时房挂 DND → 409（维修/查房不受限）；开关联动房态热点缓存失效。

### 验收对照（58 项报告更新）
核心项 23 项全 PASS（#9/#10/#34 关闭）→ **核心 100% 达标**；非核心维持 8 PASS / 21 PARTIAL / 6 GAP（P1/P2 路线见验收报告）。

### 门禁
pytest **299 例全绿**（+9）｜迁移 `e1f2a3b4c5d6` 零漂移｜前端 tsc 0 错 + vite 通过｜真实栈冒烟 `scripts/smoke_m31_core_gaps.py` **25/25**

## M32 P1 四项冲刺（验收非核心提升）

### #5 排房推荐补维修/噪音维度
- `GET /rooms/recommend` 新增两个评分维度：**近 30 天维修工单 −40**（复发风险）、**近 30 天 NOISE 投诉 −30**；原因列表输出，便于前台解释。

### #14 周报/月报定时产物
- 新模型 `ReportSnapshot`（WEEKLY|MONTHLY，指标 JSON 固化，同周期幂等覆盖，迁移 `f2a3b4c5d6e7` 零漂移）。
- **夜审自动钩子**：周一固化上周周报、月初 1 号固化上月月报（source=AUTO）；手动生成 `POST /analytics/snapshots/generate`、查询 `GET /analytics/snapshots`。

### #38 清洁「待检查」态 + 主管通知
- CLEANUP 完成 → `PENDING_INSPECT`（不再直接 DONE），站内通知主管（recipient=housekeeping_manager，ref_type=task）。
- `POST /housekeeping-tasks/{id}/inspect`：通过 → DONE + 净房可售 + done_at（计入绩效）；不通过 → 退回 ASSIGNED 返工（记录原因）。前端房态「待检查」紫标 + 通过/退回操作。

### #48 挂账客人信息展示
- `GET /fnb/room-lookup?room_no=`：在住客人姓名/脱敏手机号/离店日期/在开账单余额；无在住返回警示。
- POS 挂房账弹窗输入房号即查，绿/橙信息面板防挂错。

### 门禁
pytest **308 例全绿**（+9 M32 + 2 M26 适配）｜迁移 `f2a3b4c5d6e7` 零漂移｜tsc 0 错 + vite 通过｜真实栈冒烟 `scripts/smoke_m32_p1.py` **20/20**

### M32.1 DND 规则收紧（产品反馈）
- **免打扰仅限在住状态设置**：`POST /rooms/{room_no}/dnd` 开启时校验 `room.state == occupied`，非在住 → 409；关闭随时可操作。
- **退房自动清除 DND**：`BookingService.check_out` 腾退时自动置 `dnd=0`；换房腾退（ROOM_SWAP 原房）同样清除——保证「DND ⇒ occupied」不变式。
- 前端房态盘：非在住房 DND 开关置灰，并提示「仅在住房间可开启；退房后自动取消」。
- **修复补充（用户实测反馈）**：房态盘上直接点「退房」走的是房态流转端点 `/rooms/{room_no}/transition`，此前 DND 清除只挂在预订层退房——已将清除逻辑下沉至**房态状态机层**（`RoomService.transition`：任何离开 `occupied` 的流转统一清 DND），并在审计 detail 记录 `dnd_cleared`。预订退房/房态盘手动退房/换房/团队结账四条路径全部覆盖，回归 52 passed + 运行实例双路径实测通过。

### M32.2 经典房态盘重构（参考维也纳 PMS 5.0 截图）
- **左侧状态过滤面板**：各房态（含免打扰）带计数，点击过滤/再点取消。
- **顶部房型 Tab**：`全部[n] / 豪双[88] / 高单[65] …` 带计数切换。
- **高密度实色卡片墙**：房号大字 + 住客姓名（在住）/ 房型（空房），免打扰白底紫字角标；交互不变（单击房态操作、双击入住/订单详情）。
- **视图切换**：大图标平铺 / 按楼层分组。
- **底部经营统计条**：总数/在住/空净/空脏/预抵锁/维修/停用/免打扰/平均房价/出租率（平均房价取在住订单 total_price 均值）。
- 数据面：listBookings 映射在住客 guestMap；vite build 通过，tsc 0 错。

### M32.3 通用锁房 + 预抵/预离筛选（产品反馈）
- **预抵锁房 → 通用锁房**：`lock_for_arrival` 改为空净/空脏均可锁定（M32.3）；解锁（`release_arrival`）从房态事件流水取最近一次锁房记录的 `from_state` 恢复空净/空脏，无记录回退空净。前端标签改为「锁房/解锁」。
- **左侧过滤栏新增预抵/预离**：预抵=今日已分房未入住订单（含计数）；预离=在住且订单离店日=今天（含计数）。锁房状态不再混入预抵口径。
- **锁房不变色（用户反馈）**：锁房卡片不再整体变青色，改为**按锁房前房态着色**（空净绿/空脏灰）+ 第一行**小锁图标**（LockOutlined）。实现：`/rooms` 列表对锁房房间附带 `pre_lock_state`（取事件流水最近一次锁房的 from_state）；坑：RoomOut dump 出的 id 是 str，事件 room_id 是 int，dict.get 键类型必须统一（str）。

### M32.4 选项卡式导航（产品反馈）
- 菜单打开页面 → 顶部**选项卡**（editable-card）：点击菜单新增/激活 Tab，Tab 可切换、可关闭（最后一个不可关），关闭当前 Tab 自动跳到相邻 Tab。
- **keep-alive**：App.tsx 抽出 `layoutRoutes` 路由表，AppLayout 用 `useRoutes(layoutRoutes, { pathname })` 按固定 path 渲染每个 Tab 的页面（antd Tabs 默认保留已挂载 pane），切走再切回不丢页面状态。
- Tab 标签取自菜单 label（PATH_LABELS 扁平映射），非菜单路径用路径段兜底。
- **术语统一（用户反馈）**：全代码库「预抵锁定/预抵锁房/预抵锁/释放预抵」→「锁房/解锁」共 15 处（夜审、前台接待、统一接待台、房间管理、域模型、团队排房、夜审服务、测试注释）。注意「预抵」（今日到店预离）是另一个概念，保持不变。

### M32.5 全局视觉优化（产品反馈：美观/清晰/大方/简约/细致）
- 新增 `web/src/styles/global.css` 全局样式层 + main.tsx 扩展 antd 主题令牌（ConfigProvider theme.components），一次覆盖全部页面：
  - 底色统一 `#f5f7fa` 低饱和冷灰；文字主色 `#1f2329`/次要 `#646a73`；统一字体栈（PingFang/微软雅黑）。
  - 卡片：轻描边 + 微阴影 + 悬浮微抬；表格：浅色表头(#fafbfd)、细分隔线、行悬停 `#f7faff`、去分页贴边。
  - 按钮/输入框：去默认投影、统一描边色、主按钮悬停光晕；弹窗 12px 圆角大投影；抽屉右侧圆角。
  - 左侧菜单：菜单项圆角化、品牌区加分隔线；细滚动条；Tab 卡片圆角。
- 逐页 DOM 未动（40+ 页零侵入），后端无关。
- **分割加重 + 玻璃拟态数据卡片**：分割线统一加重至 `#d9dde3`、斑马纹加深；新增 `components/GlassStatCard`（backdrop-blur 玻璃拟态）与 `.glass-band` 渐变底带——经营概览顶部 6 卡（出租率/在住/预抵/预离/空净/营业日期），房态盘主区顶部 5 卡（在住/预抵/预离/空净/平均房价）。
- **玻璃拟态全站化**：body::before 全局固定彩色氛围底（蓝/紫/青/橙四角柔光），所有 antd Card 统一改为半透明白 + backdrop-blur(20px) + 白描边；Layout bodyBg 与 Tab 内容区改透明让氛围光透出。仍为零 DOM 侵入（纯 CSS + 主题令牌）。

### M32.6 房态盘紧凑点击菜单（参考维也纳 PMS 截图）
- 单击房态卡片 → **紧凑小菜单**（按房态出项，不再直接弹大框）：
  - 在住：客人详情 / 收银结账（跳账务）/ 免打扰开关
  - 空净：办理入住 / **置脏** / 更多房态操作
  - 空脏：办理入住 / 清扫完成 / 更多房态操作；锁房：办理入住 / 房态操作
- 新增后端流转 `set_dirty`（空净→空脏，前台手工标记），域/前端镜像同步；原大弹窗保留在「更多房态操作」。
- 实现：受控 Dropdown + 定位 span（本项目 antd 版本 Dropdown 无 point 属性）；双击快捷操作保持不变。
- **菜单全量化 + 房态日志（用户反馈）**：紧凑菜单不再有「更多房态操作」二级入口——免打扰/锁房/解锁/维修/停用（带确认）/恢复使用全部直达；新增 `GET /tenants/{id}/rooms/{room_no}/state-events` 房态日志接口（事件流水倒序，limit≤200），菜单「房态日志」打开流水表格（时间/操作/状态流转/操作人）。停用前 modal.confirm 二次确认。

### M32.7 登记入住页面（参考截图完善业务信息）
- 新增 `/check-in-register?room_no=xxx` 独立登记页（侧边栏「登记入住」）：房态盘小菜单「办理入住」与双击空房均跳转至此，不再原地弹窗。
- 页面分块：房卡信息条（房型/房态/门市价/到店时间）→ 基本信息 → 证件信息（证件类型/号码）→ 联系与档案（性别/生日/邮箱/地址/国籍/民族）→ 备注 → 入住/离店日期与预离。
- 预订模式自动带入预订单信息，仅需补录证件与联系方式；散客模式选房型后按门市价×间夜自动计价。
- 后端 `ReceptionCheckIn` 扩展字段（gender/birthday/email/address/nationality/ethnicity/note）随入住一并写入客档（国籍/民族以 tag 形式存 guest.tags）。
- 散客模式接口要求：room_no + room_type_id + guest_name + check_in_date + check_out_date（缺一 409）。
- 验证：pytest 310 passed；tsc 0 错；vite build 通过；冒烟「散客全字段登记 → 房态 occupied → 客档 7 项字段落库」全绿。

### M32.8 撤销全站玻璃拟态（用户要求「去掉全站化」）
- 移除 body::before 全局彩色氛围底；`.ant-card` 恢复常规实色卡片（仅保留轻阴影）。
- Layout bodyBg 由 transparent 恢复 `#f5f6fa`，Tab 内容区恢复默认背景。
- **保留**局部玻璃组件 `.glass-band` / `.glass-card`（Dashboard、登记入住页信息条仍在用，自带渐变底不依赖全局氛围光）。
- tsc 0 错，vite build 通过。
- **局部组件也换普通卡片（用户确认）**：`.glass-band`/`.glass-card` 去掉渐变底与 backdrop-filter，改白底 + #eef0f4 描边 + 轻阴影；图标 accent 色与数字排版保留。类名不改（Dashboard/CheckInRegister/GlassStatCard 零改动）。

### M32.9 排房预抵自动带入（用户需求）
- 登记页加载时按 `room_no + status=created` 匹配排房预抵订单（多笔取最早抵店），命中即自动转**预订模式**并预填姓名/电话/房型/预离，提示「已自动带入」。
- 房态盘双击与菜单「办理入住」跳转登记页时带 `room_no`，页面自动选中该房；若该房有排房预抵订单则整单带入，仅需补证件信息即可入住。
- 验证：排房建预订 → 房态自动 arrival_locked → 登记页可匹配 → 预订模式 check-in 200 → 房态 occupied，全链路冒烟 ✅；tsc 0 错、build 通过。

### M32.10 修复：Tab 架构丢失 URL query 导致登记页收不到房号（用户反馈）
- 根因：AppLayout 的 TabPage 用 `useRoutes(routes, { pathname })` 渲染页面，只传 pathname 丢掉 search，所有 `useSearchParams` 深链（登记入住/账务/报表等 6 页）都收不到参数；且同 Tab 二次跳转不重挂，状态不刷新。
- 修复：TabPage 对**激活 Tab** 透传当前 `location.search`；登记页加 ref 哨兵 effect，`room_no` 参数变化即重选房、清带入状态并重跑排房预抵匹配。
- E2E（playwright-core + Edge 实测）：登录 → 深链 `/check-in-register?room_no=0101` 自动选中 0101/带入房型 ✅；房态盘双击 0101 房卡跳登记页并自动选中 ✅。

### M32.11 在住登记单 + 登记页紧凑化（用户需求）
- 在住房双击 / 菜单「客人详情」→ 跳登记页并带出**在住登记单**：客人/电话/出入日期/天数/房费总额/客源/同住人/加床，标题切「在住登记单 · 房号」。
- 在住单业务按钮直达：**续住**（选新预离→extend-stay）、**换房**（选空净房→change-room）、**免打扰**（开关）、**收银结账**（跳账务）、**退房结账**（确认→check-out→回房态盘）。换房后 URL 与页面同步切到新房号。
- 登记页排版紧凑化：散客/预订信息合并为单卡，small 控件 + gutter 12，天数与门市价合并一格，备注并入卡底；最大宽 1080 居中。
- E2E（Edge 实测 13 项）：在住单带出、5 个业务按钮、续住弹窗真实操作成功、房态盘双击在住房自动带单 ✅；tsc 0 错、build 通过。
- **在住单卡片美化（用户反馈「太丑、缺时间」）**：重做为信息瓦片布局——客人主卡（姓名+客源 tag+电话/同住人/加床）｜到店时间（取房态事件 check_in 的 occurred_at，精确到分）｜离店时间（预离 12:00 + 共 N 晚/已住 N 晚）｜房费总额（accent 蓝）。顶部信息条「到店时间」在住模式同步显示实际到店时刻。修 dnd=0 被 React 渲染成 "0" 的坑。
- **办理入住改连续登记单（用户反馈「还是卡片分块」）**：去掉 Card 容器，整表一张白底面板；「入住信息」「客人信息」用蓝条 SectionTitle 分区 + 1px 细线过渡，按钮区并入表尾；在住模式保持瓦片布局不变。
- **修复房型下拉不自动选中（用户截图反馈）**：根因是 id 类型不一致——房间数据 `room_type_id` 为数字 1，而房型 Select 选项 value 为 `Number(rt.id)`、选中值却经 `room.room_type_id` 字符串链路传入，`"1" !== 1` 匹配失败导致 antd 回显原始 id。修复：form.room_type_id 改 string、选项 value 与选中值全部 `String()` 统一（排房预抵/预订带入预填同步改）。

### M32.12 完全复刻 C/S 版登记单布局（用户参考图）
- **顶部页签**：基本讯息(1) / 账务信息(2) / 操作日志(3)——账务显示房费概要+跳收银，操作日志为房态流转表（复用 state-events 接口）。
- **左侧操作栏**：房间讯息盒（房号大字/房型/房价/在住 Tag/免打扰快捷开关）+ 基本操作（保存(S)、打印(P)、补交押金(O)→账务、续住/延住(Y)、结账退房(Y)红钮）+ 扩展操作（**增加随行人(A)**→extras 接口、换房/升级(H)、团队/关联(L)预留、制房卡(K)预留、查看订单(I)→订单页）。
- **右侧表单**：基本讯息（客源门店/客源/房号/房型/市场活动/到店/离店(带12:00)/天数/房价+刷新房价）；客人讯息（红标题+读卡按钮占位+证件照「没有图像数据」占位框）；押金行（本卡押金/授权金额/币种/金额，预留禁用）；标志位（兑点/当日起早/VIP客人/信息保密/价格保密/匿名单，预留禁用）；备注/习性/黑名单三行。
- **底部随行人表格**：主单/房号/姓名/状态/客源/房型/入住时间/离店时间，数据来自 booking.companion_names。
- 在住模式表单只读并回填登记单客人信息；散客/预订模式可编辑。E2E：布局 9 项 + 在住回填（姓名/电话 input 值）全绿；tsc 0 错、build 通过。

### M32.13 操作日志页签改为登记单操作日志（用户反馈）
- 新接口 `GET /tenants/{id}/bookings/{booking_id}/logs`：按 resource_type=booking + resource_id 过滤审计流水（无需 audit.view 权限，前台可查本单）。
- 操作日志页签：有登记单（在住/预订）时显示该单审计流水——时间/操作（续住/换房/随行人/登记入住/退房等中文映射）/操作人/结果/详情；无单时退回房态流转参考并提示。
- 实测：入住 + 2 笔续住 → 3 条流水倒序展示 ✅；tsc 0 错、build 通过。
- **免打扰挪入扩展操作（用户反馈）**：房间讯息盒只展示信息（含免打扰 Tag），切换按钮改为扩展操作组「设为/取消免打扰(D)」。
- **界面用字/数字错误修复（用户反馈）**：房态盘经营统计「平均房价」漏除 100（显示 ¥84000）→ 修为 ¥xxx.xx；登记页左栏热键去重（结账退房 Y→T，避免与续住/延住(Y) 撞字母）。全站菜单/标签/按钮文案逐一校对无错别字。
- **用字调整（用户指定）**：基本讯息→基本信息、客人讯息→客人信息、本卡押金→本人押金（页签/分区标题/字段同步改，含注释）；「房间讯息」保留未动。
- 房间讯息→房间信息（用户确认，登记页左栏盒子标题）。
- **房态盘批量操作（M32.14，用户需求）**：工具栏新增「批量操作」开关；批量模式点选房间（蓝框+✓角标，自动跳过房态不匹配者），底部操作条支持批量 **置脏 / 打扫 / 锁房 / 联房**；联房走团队排房（createGroupBlock + assign），仅空净房可联（与后端 assign_rooms 校验一致）。E2E 13/13 通过（含 API 落库复核），演示数据已复原。

### M32.15 在住联房（用户业务纠正：联房 = 在住房之间的账务关联）

- **业务规则**：联房只在**在住单**之间建立账务关联（合并结算到主房场景）；**各单保留自己的来离店日期/房价**，联房不触碰任何入住信息。
- **后端**：`Booking.link_group_id` + `is_link_master`（迁移 f3b4c5d6e7f8）；`POST /tenants/{t}/bookings/link`（≥2 间在住、主房必须在列表内、重复联房自动换组）、`POST /tenants/{t}/bookings/unlink`（主房移出时组内字典序第一间自动接管主房）；AuditLog 记录 link_rooms/unlink_rooms。
- **前端**：房态盘批量操作条「联房」改为在住房联房（弹窗单选主房、展示各房来离店日期）；新增「取消联房」；联房房间卡片显示 🔗 图标（悬停示主/从房），登记页房间信息盒显示「联房·主房/从房」紫色 Tag。
- **验证**：pytest 全量 314 passed（新增 tests/test_link_rooms.py 4 例）；房态盘 UI E2E 14/14（含 API 落库复核：组ID一致/主从标记/日期不变/主房移交）；e2e_smoke 10/10。
- 演示数据现状：0101（陈在住，联房·主房）+ 0102（李联房 09-01→09-10，联房·从房）为联房演示组。

### M32.16 联房结转（settle-to-master）

- **业务**：从房未结余额整体并入主房账单——从房账单加等额 REFUND 冲减项归零（随后可正常退房），主房账单加 MISC 转入项；组内净额守恒，负债集中到主房，联房退房一次结清。
- **后端**：`POST /tenants/{t}/bookings/settle-to-master`（CashierService.transfer_to_master：校验从房/主房在住、从房有未结账务；audit 留痕 settle_to_master）。
- **前端**：登记页扩展操作组「并入主房(M)」（仅联房从房可用），成功提示并入金额与主房号。
- **验证**：pytest 317 passed（新增 3 例：结转+归零后退房 / 主房与未联房拒绝 / 零余额拒绝）；UI E2E 9/9（演示组 0101→0102 结转 ¥50.00，余额复核 0 / +5000）；e2e_smoke 10/10。
- **预离图标 BUG 修复（用户反馈）**：卡片预离图标原先只看「离店日期=今天」未校验房态，空房也会挂预离；已补 `state === "occupied"` 守卫（与统计口径 isDueOut 对齐）。同时清理 8 间孤儿在住单（订单 checked_in 但房态已流转为空房/锁房的历史测试脏数据），按「房态恢复 occupied → 补退房」对齐状态机，301 现为空脏，无预离。
- **302 预离误显修复（用户反馈）**：302 挂两笔在住单（G 2027-08-10 / 吴 2026-09-06），guestMap 被后者覆盖致误显预离。数据侧退掉「吴」并恢复 302 occupied、完结自动清扫单；UI 侧 gmap 构建加「一房多单取最近入住」守卫。E2E 5/5：302 显示 G、无预离，全盘预离图标与 API 名单一致（当前为空）。
- **一房一在住单硬校验（用户业务规则）**：BookingService.check_in 增加同房在住单唯一性守卫——房间已有 checked_in 单时拒绝重复入住（409「已有在住单」），其余订单只能走取消(X)/离店(O)/NoShow(N)/挂账(S)。这是此前 302 双单脏数据的根因堵截。pytest 318 全绿（新增守卫测试），实弹验证 409 生效，e2e_smoke 10/10。

### M32.17 钟点房入住（用户需求：不占当天过夜房可售房量）

- **后端**：统一接待 `POST /reception/check-in` 散客模式支持 `stay_type=hourly` + `hourly_hours`（服务端强制同日入住退房，跨日传参自动收敛）；`price_service.availability` 显式排除 `stay_type=hourly`（跨日脏数据也不占量）；预锁房 InvalidTransition 转 409 业务错误。
- **前端**：登记页「钟点房」勾选 + 时长选择（1-12 小时，时租价按房型 hourly_rate 计）；在住房间信息盒显示「钟点房·X小时」青色 Tag。
- **计价**：hourly_rate 未配置时按日价 1/4 折算（M24 既有规则）；夜审跳过时租房房租过账。
- **验证**：pytest 322 全绿（新增 4 例：不占量/强制同日/缺时长 409/一房一在住单约束）；UI E2E 7/7（304 开钟点房 4 小时，可售房量 9→9 实证不变）；e2e_smoke 10/10。
- **钟点房到离店时刻显示（M32.17b，用户反馈）**：Booking 新增 `hourly_start_time`（迁移 f4a5b6c7d8e9，入住时写入 HH:MM）；登记页入住/离店时间对钟点房显示真实时刻（离店=到店+时长，跨日自动进位，不再 12:00 占位）；房态卡片新增 🕐 图标悬停显示「钟点房 22:37-次日 02:37」。pytest 322 全绿（含 HH:MM 格式断言）、UI E2E 5/5。
- **房态卡片三行重排（M32.17c，用户反馈）**：房号大字保留第一行左侧；**房型名称上移到第一行右侧**（11px、半透白、ellipsis）；原第一行免打扰/锁房等小图标统一归到**第二行右侧图标组**（顺序：锁房→免打扰→住脏→联房→钟点）；原第二行住脏图标也并入图标组；第三行左侧对在住显示「至 MM-DD」或「钟点 HH:MM-次日 HH:MM」、空房留空，右侧保留预抵/预离金黄箭头。卡片尺寸 104×76 → 112×82 以容纳新布局。pytest 322、smoke 10/10。
- **卡片精简 + Ctrl 多选（M32.17d，用户反馈）**：房态卡片由三行压缩为两行（112×70），**在住房不再在图上显示完整离店/钟点时段**，改为图标表达——🕐 钟点房（悬停显示「钟点房 22:52-次日 02:52（4 小时）」）、🟡预抵/预离、🔒锁房、🔇免打扰、🧹住脏、🔗联房统一排在第二行右侧图标组。**Ctrl/⌘ + 左键**可直接多选房间（无需先点「批量操作」），选中即高亮并自动弹出底部批量条：**置脏 / 打扫 / 锁房 / 解锁 / 联房 / 取消联房 / 清空选择**；**Esc** 清空选择。批量条新增「解锁」以对称批量锁房。UI E2E 12/12（含批量置脏→打扫→锁房→解锁→联房弹窗全链路）。
- **卡片三行最终版（M32.17e，用户反馈）**：第二行**整行只放客人姓名**（在住）或状态文字（空房），不被图标挤压；原第二行图标组下移到**第三行右侧**（顺序：预抵/预离 → 锁房 → 免打扰 → 住脏 → 联房 → 钟点），第三行左侧补充在住的「住净/住脏」状态小字。卡片高度 70 → 78。E2E 6/6（三行结构、姓名独占 R2、图标在 R3）。
- **姓名居中 + 去住脏文字（M32.17f，用户反馈）**：第二行姓名/状态文字改 `textAlign:center` + `justifyContent:center` 水平居中；第三行去除在住房的「住净/住脏」文字，住脏仅以 🧹 图标表达（视觉更聚焦）。E2E 6/6。
