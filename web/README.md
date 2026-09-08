# PMS Cloud · 前端（Web）

酒店管理系统 PMS 的 Web 管理后台。技术栈遵循《详细功能模块开发计划》：**React 18 + TypeScript + Vite + Ant Design 5**（注：会话记忆曾记为 Vue3，以权威 dev-plan 为准，采用 React 体系）。

## 运行方式

```bash
# 1) 启动后端（FastAPI，端口 8000；已含 CORS 与 /tenants/{code}/hotels 端点）
cd ../pms
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) 另开终端启动前端（Vite，端口 5173）
cd web
npm install        # 首次
npm run dev        # 开发服务器 http://127.0.0.1:5173
```

浏览器打开 http://127.0.0.1:5173 即可。Vite 已配置代理：`/api` → 后端 8000、`/ws` → 后端 WebSocket（房态实时广播）。

## 目录结构

```
web/
├── index.html
├── package.json
├── vite.config.ts          # 代理 /api、/ws 到后端 8000
├── tsconfig.json
└── src/
    ├── main.tsx            # 入口：ConfigProvider(zhCN) + TenantProvider + Router
    ├── App.tsx             # 路由：/login 独立 + /dashboard /bookings /billing /nightaudit /approvals /housekeeping /notifications /alerts /group /members /commission /shifts /wakeup /psb /users /audit /reconciliation /rates /rate-calendar /mp-orders /ai-chat /openapi /yield /tenants /rooms /analytics /room-types /rooms-inventory /adjustments /price-policy /channel-push /reports
    ├── api/
    │   ├── http.ts         # axios 实例 + WebSocket base
    │   ├── endpoints.ts    # 各业务 API 封装
    │   └── types.ts        # 与后端 Pydantic 对齐的 TS 类型
    ├── store/
    │   └── tenant.tsx      # 租户/门店选择上下文（localStorage 持久化）
    ├── layout/
    │   └── AppLayout.tsx   # 侧边栏菜单 + 顶栏租户/门店选择器
    └── pages/
        ├── Dashboard.tsx   # 经营概览：出租率/在住/预抵/预离
        ├── Bookings.tsx    # 预订管理：列表 + 新建 + 入住/退房/取消
        ├── Billing.tsx     # 前台收银：开账 → 记账 → 收款 → 结账/退款
        ├── NightAudit.tsx  # 夜审日报：营业日状态 + 每日报表 + 运行夜审
        ├── Approvals.tsx   # 审批中心：提交/通过/驳回（折扣审批自动落账）
        ├── Housekeeping.tsx# 清扫工单：建单/派单/完成（完成联动房态净房）
        ├── Notifications.tsx # 通知中心：列表 + 标记已读
        ├── Alerts.tsx      # AI 预警中心：确认/解决
        ├── Group.tsx       # 集团驾驶舱：门店排名 + 两级分账
        ├── Members.tsx     # 会员 CRM：手机号查询 + 新建 + 储值充值
        ├── Commission.tsx  # 佣金规则：费率维护 + 佣金对账明细
        ├── Shifts.tsx      # 前台交班：开班/交班 + 现金差异
        ├── WakeUp.tsx      # 叫醒服务：登记/完成/取消
        ├── PSB.tsx         # 公安报送：散客录入 + 上报
        ├── Users.tsx       # 用户与角色 RBAC：用户/角色管理 + 分配
        ├── Audit.tsx       # 审计日志：操作留痕检索
        ├── Reconciliation.tsx # 支付对账：支付单 + 掉单对账
        ├── Rates.tsx       # 价格库存中心：费率码 + 设价(UPSERT) + 房量/解析价查询
        ├── MpOrders.tsx    # 移动端直订：小程序报价查询 + 一键下单 + 凭单号查单
        ├── AIChat.tsx      # AI 客服中心：会话列表 + 对话 + 转人工 + 关闭(满意度)
        ├── OpenApi.tsx     # 开放平台：应用注册 + API 密钥 + Webhook 订阅/测试
        ├── Yield.tsx       # 收益管理：动态调价规则 + 调价建议生成/历史
        ├── Login.tsx       # 登录页（token 持久化 + axios 拦截器）
        ├── Analytics.tsx   # 经营分析（Tabs：单店看板/门店排名/渠道/房型/支付方式）
        ├── Tenants.tsx     # 门店/租户管理：列表 + 新建
        └── NotFound.tsx
```

## 已实现的页面

| 页面 | 路由 | 对接后端端点 | 说明 |
|------|------|--------------|------|
| 经营概览 | `/dashboard` | `GET /tenants/{code}/manager/dashboard` + `POST /night-audit/auto-run` | 出租率、在住、预抵/预离、营业日期；顶部「运行夜审」按钮批量跑批并生成日报 |
| 房态盘 | `/rooms` | `GET /tenants/{code}/rooms` + `ws:///ws/rooms?tenant_id=` + `POST .../transition` | 楼层分组房态卡片，状态色块；**点击房间弹出合法房态操作（入住/退房/清扫/维修/停用等），操作后即时刷新并 WebSocket 自动回显** |
| 预订管理 | `/bookings` | `GET/POST /bookings` + `check-in`/`check-out`/`cancel` + `GET /room-types` | 预订列表（状态筛选）+ 新建预订 + 办理入住（选空净房）+ 退房 + 取消；入住/退房联动房态盘实时变化 |
| 前台收银 | `/billing` | `GET/POST /bills` + `/charges` + `/payments` + `/settle` + `/refund` | 账单列表（按来源 BOOKING/WALK_IN 过滤）+ 开账 + 记账（房费/杂费/折扣/退款）+ 收款（6 种支付）+ 结账（余额非零 409 拦截）+ 退款；金额单位「分」 |
| 夜审日报 | `/nightaudit` | `GET /daily-reports` + `GET /business-days` + `POST /night-audit/auto-run` | 营业日状态 chips + 每日报表（出租率/房费/总收/ADR）+ 选营业日运行夜审；附日序列收入/出租率迷你趋势图 |
| 审批中心 | `/approvals` | `GET/POST /approvals` + `POST .../decide` | 审批列表（按状态过滤）+ 提交（类型 DISCOUNT/ADJUST/OVERBOOK/REFUND + 关联账单 + 折扣金额）+ 一键通过/驳回；**DISCOUNT 通过即自动向账单落折扣应收**（单一事实源） |
| 清扫工单 | `/housekeeping` | `GET/POST /housekeeping-tasks` + `/assign` + `/done` | 工单列表（按状态过滤）+ 新建（房号/类型/责任人）+ 派单 + 完成（完成联动房态 空脏→空净） |
| 通知中心 | `/notifications` | `GET /notifications` + `POST .../read` | 消息列表（未读徽标 + 仅看未读开关）+ 标记已读 |
| AI 预警中心 | `/alerts` | `GET /ai/alerts` + `/acknowledge` + `/resolve` | 预警列表（按状态过滤）+ 确认 + 解决（M12 自动对账预警） |
| 集团驾驶舱 | `/group` | `GET /group/dashboard` + `GET /group/settlement` | 门店数/集团总收/房费汇总 + 门店排名（按最新日报 RevPAR）+ 两级分账（现付/预付口径） |
| 会员管理 | `/members` | `POST /members` + `GET /members/{phone}` + `POST .../recharge` | 手机号查询会员（等级/储值/积分/累计消费）+ 新建会员 + 储值充值（元→分）；会员列表为按手机号检索（后端无 list 端点） |
| 佣金规则 | `/commission` | `GET/POST /commission-rules` + `GET /commission-reconciliations` | 渠道费率维护（%→bps 转换）+ 佣金对账明细（房费/费率/佣金/状态） |
| 前台交班 | `/shifts` | `POST /shifts/open` + `POST /shifts/{id}/close` + `GET /shifts` | 开班（收银员/备用金）+ 交班（实点现金→自动算差异）+ 班次列表 |
| 叫醒服务 | `/wakeup` | `GET/POST /wake-up-calls` + `/done` + `/cancel` | 叫醒登记（房号/时间）+ 完成/取消（列表按门店过滤，必传 hotel_id） |
| 公安报送 | `/psb` | `GET/POST /psb-tasks` + `/upload` | 散客（无预订）现场登记上报 + 一键上报公安（预订入住由 check-in 自动建，无需调用） |
| 用户与角色 | `/users` | `GET/POST /users` + `GET/POST /roles` + `POST /users/{id}/roles` | 用户/角色 Tabs：新建用户、新建角色、为用户分配角色（RBAC M8） |
| 审计日志 | `/audit` | `GET /audit-logs` | 操作留痕检索（操作人/动作/资源/结果/IP/明细） |
| 支付对账 | `/reconciliation` | `GET /pay-orders` + `POST /pay/reconcile` + `POST /pay-orders/{no}/close` | 支付单列表（按状态）+ 掉单对账（扫描/关单/补单）+ 关闭未支付单（M7-2） |
| 登录 | `/login` | `POST /auth/login` | 登录页（独立路由）：成功存 token 至 localStorage 并经 axios 拦截器透传 `Authorization`；后端路由当前未强制鉴权，属 token 透传演示 |
| 经营分析 | `/analytics` | `GET /analytics/dashboard` + `/hotel-ranking` + `/channel-revenue` + `/room-type-revenue` + `/payment-summary` | Tabs：单店看板（KPI + 日序列趋势）/门店排名/渠道收入/房型收入/支付方式汇总；金额「分」、比率 bps 格式化 |
| 价格库存中心 | `/rates` | `GET /rate-codes` + `POST /price-calendar`（UPSERT）+ `GET /room-types/{id}/availability` | 费率码列表（discount_pct 基点→折）+ 按房型×日期设价（元→分，受集团价策边界 403 拦截）+ 房量/解析价查询 |
| 价格日历 | `/rate-calendar` | `GET /price-calendar`（范围列表）+ `POST /price-calendar/batch`（批量 UPSERT）+ `POST /price-calendar`（单日） | 月视图网格（周一为首列，周末高亮、今日描边）+ 点击单日改价 + 批量改价（全月/工作日/周末，受集团价策边界拦截并计入 blocked） |
| 移动端直订 | `/mp-orders` | `GET /mp/offers` + `POST /mp/orders` + `GET /mp/orders/{no}` | 小程序房型报价（逐晚价+可售量，任一晚无房即不可订）+ 一键下单（建预订 channel=wechat_mp + 待支付单）+ 凭订单号查单 |
| AI 客服中心 | `/ai-chat` | `GET /ai/chat-sessions` + `/messages` + `POST .../messages` + `/handoff` + `/close` | 会话列表（状态过滤）+ 对话气泡（用户/机器人/人工）+ 机器人自动应答（意图/置信度）+ 转人工 + 关闭（满意度 1-5） |
| 开放平台 | `/openapi` | `GET/POST /openapi/apps` + `/keys` + `POST .../keys/{id}/revoke` + `GET/POST /openapi/webhooks` + `POST .../test` | 第三方应用注册 + API 密钥生成（明文仅一次）/吊销 + Webhook 订阅（topic 匹配）+ 测试触发（HTTP 状态回显） |
| 收益管理 | `/yield` | `GET/PUT /yield/rules` + `POST /yield/pricing/recommend` + `GET /yield/pricing/recommendations` | 动态调价规则维护（占用率阈值/最大加减价 bps/竞品策略）+ 调价建议生成（需求指数+周末因子+竞品对标，返回建议价与理由）+ 建议历史 |
| 门店管理 | `/tenants` | `GET/POST /tenants` | 租户列表与新建 |
| 房型管理 | `/room-types` | `GET /tenants/{code}/room-types` + `POST /tenants/{id}/room-types` | 房型列表 + 新建（base_price 元→分；**POST 路由使用 int 租户 ID**，前端按 code 解析 id） |
| 房间管理 | `/rooms-inventory` | `GET /tenants/{code}/rooms` + `POST /hotels/{hotel_id}/rooms` | 房间列表（按房态筛选）+ 批量建房（房号多行/逗号分隔，目标门店取顶部选择） |
| 调账中心 | `/adjustments` | `GET /tenants/{code}/adjustments` + `POST /tenants/{code}/bills/{id}/adjustments` | 调账/红冲记录列表 + 发起（bill_id/type/金额元→分有符号/原因/操作员） |
| 集团价策 | `/price-policy` | `GET/POST /tenants/{code}/group/price-policies` | 集团限价策略下发列表 + 新建（限价上下限元→分，可按门店/房型限定，不填=集团全局） |
| OTA 推送 | `/channel-push` | `POST /tenants/{code}/channels/{channel}/availability-push` | 房量/价格推送至 OTA（携程/美团/飞猪/Booking/Agoda），展示回传集成状态与载荷 |
| 报表中心 | `/reports` | `GET /tenants/{code}/analytics/export` | 报表生成（hotel_ranking/channel_revenue/room_type_revenue/dashboard，raw dict 按 hotels/channels/room_types/daily_series 取数组）+ 前端导出 CSV |
| 预付落账 | 账单抽屉内按钮 | `POST /tenants/{code}/bills/{id}/apply-prepay` | 前台收银账单抽屉新增「预付落账」按钮，调用 apply-prepay 将预付押金落账并重算余额 |

## 开发约定

- 顶栏可选租户（默认 `DEMO2026`）与门店，选择持久化到 `localStorage`。
- 所有写操作目前直连后端公开端点（RBAC 登录尚未在前端接入，后端路由亦未强制鉴权）。
- 金额单位为「分」，后端 `base_price` 等为整数分。

## 后端配套改动（Sprint 前端奠基）

- `app/main.py`：新增 `CORSMiddleware`（`allow_origins=["*"]`，开发期），支持跨端口调用。
- `app/api/routes.py`：新增 `GET /tenants/{tenant_id}/hotels`（前端门店选择器依赖）；新增 `GET /tenants/{tenant_id}/room-types`（前端房型下拉依赖）。
- 演示数据：已为 `DEMO2026` 灌入「深圳湾示范店」+ 2 房型 + 12 间房（含 occupied / arrival_locked / maintenance / vacant_dirty / out_of_service / vacant_clean 多样房态），房态盘与看板可直接查看。

> 注：开发库 `pms_dev.db` 曾因 `AuditLog` 模型新增 `hotel_id` 列而 schema 漂移（旧表缺列导致房态流转 500）。已通过 `drop_all` + `create_all` 按当前模型重建解决。

## 后端行为：入住自动开账联动（M3-7）

- `BookingService.check_in` 在办理入住、房态转在住后，**自动为该预订开出一张在住账单**（`CashierService.open_bill`，`source=BOOKING`，`booking_id` 回写），幂等：仅当该预订尚无 `OPEN` 账单时才创建，重复入住（409）不会重复开账。
- 夜审房费过账（`night_audit_service`）依赖此 OPEN 账单存在，故入住即开账是夜审的前置条件。
- `BillOut` 已新增 `booking_id` 字段，账单列表/详情可直接看到「关联预订」。
- 验证（DEMO2026）：新建预订 → 办理入住（200）→ 账单列表出现 `source=BOOKING`、`booking_id` 等于该预订、`status=OPEN`；再次入住返回 409。
