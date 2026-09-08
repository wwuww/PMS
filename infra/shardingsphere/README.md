# ShardingSphere-Proxy 5.x 分库分表配置样例（Sprint 15，128 库方案）

目标拓扑（dev-plan：1 万店 / 100 万间客房）：
- 128 个物理库 pms_shard_00 .. pms_shard_127；
- 以 tenant_code 哈希路由：`sharding_alg = Math.abs(tenant_id.hashCode()) % 128`；
- 租户内数据量可控（单租户 ≤ 数百门店），租户间彻底隔离，跨租户报表走数仓（不在 OLTP 库做）。

接入方式二选一：
- 应用 → Proxy(3307, MySQL 协议) → 分片库（应用无需感知分片，SQLAlchemy 驱动换 pymysql）；
- 应用直连 + ShardingSphere-JDBC（Python 生态建议走 Proxy）。

注意事项：
1. 全局唯一主键改用雪花 ID 或「分片位 | 自增位」复合 ID（当前 IntPkMixin 自增需替换）；
2. 跨分片事务仅保证最终一致——当前领域事件 + 对账（reconcile）机制已为此预留；
3. `business_days(hotel_id, business_date)` 等唯一约束在同一租户内，不受分片影响；
4. tenant.code 路由键必须出现在分片 SQL 的 WHERE 中（当前所有服务查询均带 tenant_id ✓）。

proxy 配置（server.yaml + database shard_db）：

databaseName: shard_db
dataSources:
  ds_0: { url: jdbc:mysql://127.0.0.1:3306/pms_shard_00, username: pms, password: pms, ... }
  # ... ds_1 .. ds_127（生产由脚本生成）
rules:
- !SHARDING
  tables:
    bookings:
      actualDataNodes: ds_${0..127}.bookings
      databaseStrategy:
        standard:
          shardingColumn: tenant_id
          shardingAlgorithmName: tenant_hash_mod
    bills:
      actualDataNodes: ds_${0..127}.bills
      databaseStrategy:
        standard:
          shardingColumn: tenant_id
          shardingAlgorithmName: tenant_hash_mod
    rooms:
      actualDataNodes: ds_${0..127}.rooms
      databaseStrategy:
        standard:
          shardingColumn: tenant_id
          shardingAlgorithmName: tenant_hash_mod
    # 其余高水位表（orders/audit_logs/price_calendar...）同规则
  shardingAlgorithms:
    tenant_hash_mod:
      type: HASH_MOD
      props:
        sharding-count: 128
props:
  sql-show: false
