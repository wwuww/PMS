"""渠道适配器注册表（M6-1）。"""

from __future__ import annotations

from app.channels.base import ChannelAdapter, ChannelType
from app.channels.ctrip import CtripAdapter
from app.channels.meituan import MeituanAdapter

_REGISTRY: dict[ChannelType, type[ChannelAdapter]] = {
    ChannelType.OTA_CTRIP: CtripAdapter,
    ChannelType.OTA_MEITUAN: MeituanAdapter,
}


def get_adapter(channel: str, tenant_id: str, config: dict | None = None) -> ChannelAdapter:
    """按渠道类型获取适配器实例；未知渠道回退直订适配器（永不报错）。"""
    try:
        ctype = ChannelType(channel)
    except ValueError:
        ctype = ChannelType.DIRECT
    adapter_cls = _REGISTRY.get(ctype)
    if adapter_cls is None:
        # 直订/微信等无需外部适配器，返回基类（方法均为 no-op 集成）
        return ChannelAdapter(tenant_id=tenant_id, config=config)
    return adapter_cls(tenant_id=tenant_id, config=config)


__all__ = ["get_adapter", "ChannelAdapter", "ChannelType", "ChannelResult"]
