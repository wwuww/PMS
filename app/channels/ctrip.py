"""携程直连适配器骨架（M6-1，渠道中立）。

真实接入点（SG-2 前由渠道组补齐）：
- 资质：携程 eBooking / 开放平台 AppKey+AppSecret（注意绿云为携程资本系，本产品渠道中立，可直连）
- 报价拉取：GET /api/rateplan/query
- 房量推送：POST /api/inventory/update（按房型×日期×剩余房量）
- 下单通知：接收携程订单推送 webhook，签名校验后转为本系统 Booking
- 取消：POST /api/order/cancel
"""

from __future__ import annotations

from typing import Any

from app.channels.base import ChannelAdapter, ChannelResult, ChannelType


class CtripAdapter(ChannelAdapter):
    channel_type = ChannelType.OTA_CTRIP
    display_name = "携程"

    def parse_webhook(self, raw: dict[str, Any]) -> dict[str, Any]:
        # 骨架：声明携程 webhook → 标准事件的字段映射位置
        # 真实实现需校验 sign=MD5(appSecret+timestamp+body)
        return {
            "channel": self.channel_type.value,
            "event": raw.get("eventType", "unknown"),
            "booking_ref": raw.get("orderId"),
            "payload": raw,
        }
