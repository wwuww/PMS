"""OTA 直连适配器骨架测试（M6-1）。"""

from app.channels import get_adapter
from app.channels.base import ChannelAdapter, ChannelResult, ChannelType


class TestChannelRegistry:
    def test_get_adapter_ctrip(self) -> None:
        adapter = get_adapter("ota_ctrip", "t001")
        assert adapter.channel_type == ChannelType.OTA_CTRIP
        assert adapter.display_name == "携程"

    def test_get_adapter_meituan(self) -> None:
        adapter = get_adapter("ota_meituan", "t001")
        assert adapter.channel_type == ChannelType.OTA_MEITUAN

    def test_unknown_channel_falls_back_to_direct(self) -> None:
        adapter = get_adapter("does_not_exist", "t001")
        assert adapter.channel_type == ChannelType.DIRECT

    async def test_skeleton_not_integrated(self) -> None:
        adapter = get_adapter("ota_ctrip", "t001")
        result: ChannelResult = await adapter.push_availability(1, "2026-10-01", 5)
        assert result.integrated is False
        assert "骨架未实现" in result.message
        assert result.payload["available"] == 5

    def test_parse_webhook_contract(self) -> None:
        adapter = get_adapter("ota_ctrip", "t001")
        out = adapter.parse_webhook({"eventType": "NEW_ORDER", "orderId": "C123"})
        assert out["channel"] == "ota_ctrip"
        assert out["booking_ref"] == "C123"

    def test_direct_fallback_parse_webhook_default(self) -> None:
        # 直订回退适配器可实例化，parse_webhook 返回默认占位
        base = ChannelAdapter("t001")
        out = base.parse_webhook({"foo": "bar"})
        assert out["channel"] == ChannelType.DIRECT.value
        assert out["payload"] == {"foo": "bar"}
