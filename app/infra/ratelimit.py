"""接口限流（M18-2）：滑动窗口计数，按「客户端 IP + 桶」限速。

- 中间件默认关闭（PMS_RATE_LIMIT_ENABLED=false），生产 docker-compose 开启；
- /auth/login 单独收紧（防撞库爆破），其余走默认桶；
- 内存滑动窗口（单进程）；上 Redis 集群时可替换为 Redis ZSET 实现，接口不变。
"""

from __future__ import annotations

import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings


def parse_limit(spec: str) -> tuple[int, int]:
    """解析 "次数/窗口秒"，如 "240/60" → (240, 60)。非法配置退化为不限。"""
    try:
        n, w = spec.split("/", 1)
        limit, window = int(n), int(w)
        if limit <= 0 or window <= 0:
            raise ValueError
        return limit, window
    except ValueError:
        return 0, 0  # 0 = 不限


_windows: dict[str, deque[float]] = {}


def hit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """滑动窗口放行判定。返回 (是否放行, 窗口内剩余额度)。"""
    if limit <= 0 or window <= 0:
        return True, -1
    now = time.monotonic()
    q = _windows.setdefault(key, deque())
    cutoff = now - window
    while q and q[0] <= cutoff:
        q.popleft()
    if len(q) >= limit:
        return False, 0
    q.append(now)
    return True, limit - len(q)


def reset_rate_limiter() -> None:
    """清空窗口状态（测试隔离用）。"""
    _windows.clear()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """全局限流中间件。settings 每请求读取，测试可经环境变量动态开关。"""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path
        is_auth = path.endswith("/auth/login")
        spec = settings.rate_limit_auth if is_auth else settings.rate_limit_default
        limit, window = parse_limit(spec)
        if limit <= 0:
            return await call_next(request)

        bucket = "auth" if is_auth else "default"
        key = f"{_client_ip(request)}:{bucket}"
        allowed, remaining = hit(key, limit, window)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后重试"},
                headers={"Retry-After": str(window)},
            )
        response = await call_next(request)
        if remaining >= 0:
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
