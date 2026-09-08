"""OTA 直连适配器骨架（M6-1，架构决策 DEC-02 事件驱动 + 渠道中立）。

本文件定义统一渠道契约 ChannelAdapter 与 ChannelResult。
各 OTA 适配器（携程/美团/飞猪）实现该契约，使房态/价格/订单的
上行（推送）与下行（拉取/接收 webhook）逻辑与核心域解耦——
核心域只依赖抽象，不依赖任何 OTA 私有协议（SRS FR-ZL-01 渠道中立）。

本 Sprint 为骨架：具体 HTTP 对接在 SG-2 压测准入门前由渠道组补齐，
但接口形态、错误语义、重试边界已固定，便于并行开发。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ChannelType(StrEnum):
    DIRECT = "direct"          # 直订（微信小程序/官网）
    WECHAT = "wechat"          # 微信生态
    OTA_CTRIP = "ota_ctrip"    # 携程（绿云系，需 eBooking 资质）
    OTA_MEITUAN = "ota_meituan"  # 美团（别样红系）
    OTA_FLIGGY = "ota_fliggy"  # 飞猪


@dataclass(frozen=True)
class ChannelResult:
    """渠道操作统一返回。骨架阶段 integrated=False 表示未真正接入。"""

    channel: str
    integrated: bool
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(ABC):
    """渠道适配器契约（M6-1）。

    所有方法返回 ChannelResult；骨架默认返回 integrated=False，
    真实实现替换方法体即可，调用方代码不变。
    """

    channel_type: ChannelType = ChannelType.DIRECT
    display_name: str = "Base"

    def __init__(self, tenant_id: str, config: dict[str, Any] | None = None) -> None:
        self.tenant_id = tenant_id
        self.config = config or {}

    # ---- 下行：从渠道拉取 ----
    async def fetch_rates(self, room_type_id: int, date: str) -> ChannelResult:
        return ChannelResult(
            channel=self.channel_type.value,
            integrated=False,
            message=f"[{self.display_name}] fetch_rates 骨架未实现（待接入 {self.channel_type.value} 报价接口）",
        )

    # ---- 上行：向渠道推送 ----
    async def push_availability(self, room_type_id: int, date: str, available: int) -> ChannelResult:
        return ChannelResult(
            channel=self.channel_type.value,
            integrated=False,
            message=f"[{self.display_name}] push_availability 骨架未实现（待接入 {self.channel_type.value} 房量同步）",
            payload={"room_type_id": room_type_id, "date": date, "available": available},
        )

    async def create_reservation(self, booking_id: int) -> ChannelResult:
        return ChannelResult(
            channel=self.channel_type.value,
            integrated=False,
            message=f"[{self.display_name}] create_reservation 骨架未实现（待接入 {self.channel_type.value} 下单接口）",
            payload={"booking_id": booking_id},
        )

    async def cancel_reservation(self, booking_id: int) -> ChannelResult:
        return ChannelResult(
            channel=self.channel_type.value,
            integrated=False,
            message=f"[{self.display_name}] cancel_reservation 骨架未实现（待接入 {self.channel_type.value} 取消接口）",
            payload={"booking_id": booking_id},
        )

    # ---- 回调：解析渠道下发的 webhook ----
    def parse_webhook(self, raw: dict[str, Any]) -> dict[str, Any]:
        """将渠道 webhook 体规整为本系统的标准事件（订单/取消/改价）。

        基类提供默认实现（直订/未知渠道可用）；真实 OTA 适配器覆写此方法，
        负责字段映射与签名校验。骨架阶段返回未集成占位。
        """
        return {
            "channel": self.channel_type.value,
            "event": "unknown",
            "booking_ref": None,
            "payload": raw,
        }
