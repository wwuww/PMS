"""缓存客户端（Sprint 15）。

- 生产（配置 PMS_REDIS_URL 且安装 redis 包）：Redis 异步客户端。
- 开发/测试（默认）：进程内 TTL 字典，接口与 Redis 完全一致，业务代码零改动。

值统一 JSON 序列化，跨后端行为一致。热点读 + 显式写失效模式：
  读：GET /tenants/{code}/rooms 先查 cache，未命中查库回填；
  写：RoomService.transition / create_rooms 等写路径调用 invalidate 前缀删除。
TTL 作为兜底（默认 30s），即使失效遗漏也不会长期读到旧值。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class MemoryBackend:
    """进程内 TTL 缓存（单进程语义；多副本部署请配置 Redis）。"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expire_at, raw = item
        if expire_at is not None and expire_at <= time.monotonic():
            self._store.pop(key, None)
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expire_at = time.monotonic() + ttl if ttl else None
        self._store[key] = (expire_at, json.dumps(value, ensure_ascii=False, default=str))

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    async def invalidate_prefix(self, prefix: str) -> int:
        victims = [k for k in self._store if k.startswith(prefix)]
        for k in victims:
            self._store.pop(k, None)
        return len(victims)


class RedisBackend:
    """Redis 异步后端（redis.asyncio）。连接失败自动降级内存。"""

    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis  # noqa: PLC0415 延迟导入，未安装则降级

        self._redis = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        raw = await self._redis.get(key)
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        if ttl:
            await self._redis.setex(key, ttl, payload)
        else:
            await self._redis.set(key, payload)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._redis.delete(*keys)

    async def invalidate_prefix(self, prefix: str) -> int:
        victims = [k async for k in self._redis.scan_iter(match=f"{prefix}*")]
        if victims:
            await self._redis.delete(*victims)
        return len(victims)


class CacheClient:
    """统一缓存门面。backend 选择失败（Redis 不可达/未安装）自动降级 Memory。"""

    def __init__(self) -> None:
        self._backend: MemoryBackend | RedisBackend = MemoryBackend()
        url = get_settings().redis_url
        if url:
            try:
                self._backend = RedisBackend(url)
                logger.info("缓存后端：Redis (%s)", url)
            except Exception as exc:  # noqa: BLE001 降级不致命
                logger.warning("Redis 初始化失败，降级内存缓存：%s", exc)
                self._backend = MemoryBackend()

    @property
    def backend_name(self) -> str:
        return "redis" if isinstance(self._backend, RedisBackend) else "memory"

    async def get(self, key: str) -> Any | None:
        return await self._backend.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if ttl is None:
            ttl = get_settings().cache_ttl_seconds
        await self._backend.set(key, value, ttl)

    async def delete(self, *keys: str) -> None:
        await self._backend.delete(*keys)

    async def invalidate_prefix(self, prefix: str) -> int:
        return await self._backend.invalidate_prefix(prefix)


_cache: CacheClient | None = None


def get_cache() -> CacheClient:
    """全局单例（测试可 reset_cache 后重建以切换后端）。"""
    global _cache
    if _cache is None:
        _cache = CacheClient()
    return _cache


def reset_cache() -> None:
    """重置单例（测试隔离用；生产勿调用）。"""
    global _cache
    _cache = None
