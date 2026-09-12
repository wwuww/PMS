"""PMS 配置管理（pydantic-settings，环境变量前缀 PMS_）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PMS_", env_file=".env", extra="ignore")

    # 开发/测试默认 SQLite；生产切换 MySQL（ShardingSphere-Proxy 128 分片）：
    # PMS_DATABASE_URL=mysql+asyncmy://user:pass@host:3306/pms
    database_url: str = "sqlite+aiosqlite:///./pms_dev.db"
    app_name: str = "PMS Cloud"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True

    # ----- M30 连接池参数化（生产 MySQL）-----
    # SQLAlchemy 默认 pool_size=5 / max_overflow=10（共 15）；高并发下需上调。
    # pool_recycle：MySQL wait_timeout 常为 28800s（8h），连接闲置超时被服务端回收，
    #   需在服务端回收前主动回收（设 3600s 安全裕量），配合 pool_pre_ping 双保险。
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 3600  # 秒；-1 禁用
    db_pool_timeout: int = 30  # 秒；借连接超时（避免雪崩时无限等待）

    # ----- Sprint 15 基础设施 -----
    # Redis 缓存（生产）：PMS_REDIS_URL=redis://localhost:6379/0；留空 = 内存缓存（单进程 dev）
    redis_url: str = ""
    # 热点读缓存默认 TTL（秒）
    cache_ttl_seconds: int = 30

    # ----- M18 接口限流（滑动窗口，按 IP + 桶）-----
    # 默认关闭（dev/测试零干扰）；生产 docker-compose 中开启
    rate_limit_enabled: bool = False
    # 格式 "次数/窗口秒"；default 全局桶，auth 仅 /auth/login（防撞库爆破）
    rate_limit_default: str = "240/60"
    rate_limit_auth: str = "10/60"

    # ----- 支付回调验签（P0 安全）-----
    # 生产必须通过 PMS_PAY_NOTIFY_SECRET 注入；留空 = dev/测试用内置默认值。
    # 校验方式：X-Pay-Sign = HMAC-SHA256(secret, raw_body)，与 OTA webhook 同一套契约。
    pay_notify_secret: str = ""
    # 生产环境（debug=False）未配置密钥时，回调一律拒绝而不是放行——避免"默认密钥"裸奔。
    require_pay_notify_secret: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
