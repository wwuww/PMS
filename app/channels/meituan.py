"""美团直连适配器骨架（M6-1，渠道中立）。

真实接入点（SG-2 前由渠道组补齐）：
- 资质：美团酒店开放平台 AppId+AppKey（注意别样红为美团系，本产品渠道中立，可直连）
- 报价拉取：mt hotel.room.getRatePlan
- 房量推送：mt hotel.inventory.batchUpdate
- 下单通知：接收美团订单推送（signature 校验）转为本系统 Booking
- 取消：mt hotel.order.cancel
"""

from __future__ import annotations

from typing import Any

from app.channels.base import ChannelAdapter, ChannelResult, ChannelType


class MeituanAdapter(ChannelAdapter):
    channel_type = ChannelType.OTA_MEITUAN
    display_name = "美团"

    def parse_webhook(self, raw: dict[str, Any]) -> dict[str, Any]:
        # 骨架：声明美团 webhook → 标准事件的字段映射位置
        return {
            "channel": self.channel_type.value,
            "event": raw.get("type", "unknown"),
            "booking_ref": raw.get("orderId"),
            "payload": raw,
        }
