"""分布式雪花 ID 生成器（128 分库分表前置）。

标准 snowflake 布局（64 bit）：
- 1 bit  符号位（恒 0）
- 41 bit 毫秒时间戳（相对 EPOCH，约 69 年）
- 10 bit 节点号（datacenter_id 5 + worker_id 5，最多 1024 节点）
- 12 bit 序列号（每毫秒每节点 4096 个）

API/前端统一以字符串传输（避免 JS 2^53 精度丢失），DB 以 BigInteger 存储。
"""

from __future__ import annotations

import os
import threading
import time

# 2024-01-01T00:00:00Z，自定义纪元（比 Twitter 默认纪元更省位、寿命更长）
EPOCH_MS = 1_704_067_200_000

DATACENTER_BITS = 5
WORKER_BITS = 5
SEQUENCE_BITS = 12

MAX_DATACENTER = (1 << DATACENTER_BITS) - 1  # 31
MAX_WORKER = (1 << WORKER_BITS) - 1  # 31
MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1  # 4095

DATACENTER_SHIFT = WORKER_BITS + SEQUENCE_BITS  # 17
WORKER_SHIFT = SEQUENCE_BITS  # 12
TIMESTAMP_SHIFT = DATACENTER_BITS + WORKER_BITS + SEQUENCE_BITS  # 22


def _read_node(env_key: str, default: int, maximum: int) -> int:
    raw = os.getenv(env_key)
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    if val < 0 or val > maximum:
        return default
    return val


class Snowflake:
    """线程安全的雪花 ID 生成器。"""

    __slots__ = ("_datacenter_id", "_worker_id", "_lock", "_last_ts", "_sequence")

    def __init__(self, datacenter_id: int | None = None, worker_id: int | None = None) -> None:
        if datacenter_id is None:
            datacenter_id = _read_node("PMS_DATACENTER_ID", 0, MAX_DATACENTER)
        if worker_id is None:
            worker_id = _read_node("PMS_WORKER_ID", 0, MAX_WORKER)
        if not (0 <= datacenter_id <= MAX_DATACENTER):
            raise ValueError(f"datacenter_id 必须落在 0..{MAX_DATACENTER}")
        if not (0 <= worker_id <= MAX_WORKER):
            raise ValueError(f"worker_id 必须落在 0..{MAX_WORKER}")
        self._datacenter_id = datacenter_id
        self._worker_id = worker_id
        self._lock = threading.Lock()
        self._last_ts = -1
        self._sequence = 0

    @staticmethod
    def _now_ms() -> int:
        return time.time_ns() // 1_000_000

    def _wait_next_ms(self, last_ts: int) -> int:
        ts = self._now_ms()
        while ts <= last_ts:
            ts = self._now_ms()
        return ts

    def next_id(self) -> int:
        with self._lock:
            ts = self._now_ms()
            if ts < self._last_ts:
                # 时钟回拨：等待追平（必要时可抛异常，这里采用保守等待）
                ts = self._wait_next_ms(self._last_ts)
            if ts == self._last_ts:
                self._sequence = (self._sequence + 1) & MAX_SEQUENCE
                if self._sequence == 0:
                    ts = self._wait_next_ms(self._last_ts)
            else:
                self._sequence = 0
            self._last_ts = ts
            return (
                ((ts - EPOCH_MS) << TIMESTAMP_SHIFT)
                | (self._datacenter_id << DATACENTER_SHIFT)
                | (self._worker_id << WORKER_SHIFT)
                | self._sequence
            )


# 进程级单例（默认节点 0/0，生产按 PMS_WORKER_ID/PMS_DATACENTER_ID 注入）
_default_sf = Snowflake()


def next_id() -> int:
    """生成下一个雪花 ID（int）。"""
    return _default_sf.next_id()
