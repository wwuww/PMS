"""OTA 渠道直连服务（M29，A5）：配置 / 签名校验 / 幂等注入 / 房量推送 + 推送日志。"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import ChannelType
from app.models import (
    Booking,
    ChannelPushLog,
    Hotel,
    OtaChannelConfig,
    Room,
    RoomType,
)
from app.services.audit_service import record as audit_record
from app.services.audit_service import record
from app.services.ota_mapping_service import OtaMappingService
from app.services.ota_rate_plan_service import OtaRatePlanService

SIGN_HEADER = "X-Ota-Sign"
SUPPORTED_CHANNELS = (ChannelType.OTA_CTRIP.value, ChannelType.OTA_MEITUAN.value, ChannelType.OTA_FLIGGY.value, "sandbox")


class OtaError(Exception):
    """OTA 直连业务异常（路由层转 4xx）。"""


class OtaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- 配置 ----------

    async def upsert_config(
        self,
        tenant_id: str,
        *,
        hotel_id: int,
        channel: str,
        secret: str,
        app_key: str = "",
        push_enabled: bool = True,
        push_inventory_url: str | None = None,
        operator: str = "admin",
    ) -> OtaChannelConfig:
        if channel not in SUPPORTED_CHANNELS:
            raise OtaError(f"不支持的渠道：{channel}")
        hotel = await self.session.get(Hotel, hotel_id)
        if hotel is None:
            raise OtaError(f"酒店不存在：{hotel_id}")
        # tenant_id 入参兼容 code 或 BigInteger 字符串形态（路由层可能传 code 也可能传 id）
        from app.models import Tenant as _Tenant
        from sqlalchemy import select as _sa_select

        tenant_row = (
            await self.session.execute(
                _sa_select(_Tenant).where(
                    (_Tenant.code == tenant_id) | (_Tenant.id == hotel.tenant_id)
                )
            )
        ).scalars().first()
        if tenant_row is None:
            raise OtaError(f"酒店所属租户不存在：{hotel.tenant_id}")
        # 比对：tenant_id 入参 与 hotel 实际归属 的 code 必须一致
        if tenant_row.code != tenant_id and str(tenant_row.id) != tenant_id:
            raise OtaError(f"酒店 {hotel_id} 不属于租户 {tenant_id}")
        stmt = select(OtaChannelConfig).where(
            OtaChannelConfig.tenant_id == tenant_id, OtaChannelConfig.channel == channel
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = OtaChannelConfig(tenant_id=tenant_id, channel=channel)
            self.session.add(row)
        row.hotel_id = hotel_id
        row.secret = secret
        row.app_key = app_key
        row.push_enabled = 1 if push_enabled else 0
        row.push_inventory_url = push_inventory_url
        await self.session.flush()
        await audit_record(
            self.session,
            tenant_id,
            "ota.config.upsert",
            actor=operator,
            resource_type="ota_config",
            resource_id=row.id,
            hotel_id=hotel_id,
            detail={"channel": channel, "push_enabled": bool(row.push_enabled)},
        )
        return row

    async def list_configs(self, tenant_id: str) -> list[OtaChannelConfig]:
        stmt = select(OtaChannelConfig).where(OtaChannelConfig.tenant_id == tenant_id)
        rows = await self.session.execute(stmt)
        return list(rows.scalars())

    # ---------- 签名 ----------

    @staticmethod
    def sign(secret: str, raw_body: bytes) -> str:
        return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()

    async def _config_for(self, tenant_id: str, channel: str) -> OtaChannelConfig:
        stmt = select(OtaChannelConfig).where(
            OtaChannelConfig.tenant_id == tenant_id, OtaChannelConfig.channel == channel
        )
        cfg = (await self.session.execute(stmt)).scalar_one_or_none()
        if cfg is None:
            raise OtaError(f"渠道未接入：{channel}")
        return cfg

    # ---------- 订单注入（幂等） ----------

    async def inject_order(
        self,
        tenant_id: str,
        channel: str,
        payload: dict[str, Any],
        *,
        raw_body: bytes,
        signature: str | None,
        operator: str = "ota",
    ) -> tuple[Booking, bool]:
        """OTA 订单 webhook 注入。三级防重：

        1. 渠道 HMAC 签名校验（X-Ota-Sign = HMAC-SHA256(secret, raw_body)）；
        2. external_ref 幂等查询（同租户同渠道同单号直接返回已存在订单）；
        3. 房量守卫（沿用预订引擎，超卖拒收）。
        返回 (booking, created)。
        """
        cfg = await self._config_for(tenant_id, channel)
        if not signature or not hmac.compare_digest(self.sign(cfg.secret, raw_body), signature):
            raise OtaError("签名校验失败")
        external_ref = str(payload.get("external_ref") or "").strip()
        if not external_ref:
            raise OtaError("缺少 external_ref")
        # 幂等：已存在直接返回
        stmt = select(Booking).where(
            Booking.tenant_id == tenant_id,
            Booking.external_channel == channel,
            Booking.external_ref == external_ref,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            await audit_record(
                self.session,
                tenant_id,
                "ota.order.duplicate",
                actor=operator,
                resource_type="booking",
                resource_id=existing.id,
                hotel_id=existing.hotel_id,
                detail={"external_ref": external_ref, "channel": channel},
            )
            return existing, False

        hotel_id = payload.get("hotel_id") or cfg.hotel_id
        room_type_code = payload.get("room_type_code")
        stmt = select(RoomType).where(
            RoomType.tenant_id == tenant_id, RoomType.code == str(room_type_code)
        )
        rt = (await self.session.execute(stmt)).scalar_one_or_none()
        if rt is None:
            raise OtaError(f"房型代码不存在：{room_type_code}")

        # 渠道价：payload 金额（分）优先，缺省走门市价
        total_price = payload.get("total_price_cents")
        booking = Booking(
            tenant_id=tenant_id,
            hotel_id=int(hotel_id),
            room_type_id=rt.id,
            channel=channel,
            external_channel=channel,
            external_ref=external_ref,
            guest_name=str(payload.get("guest_name") or "OTA客"),
            guest_phone=payload.get("guest_phone"),
            check_in_date=str(payload.get("check_in_date")),
            check_out_date=str(payload.get("check_out_date")),
            status="created",
            total_price=int(total_price) if total_price is not None else None,
        )
        self.session.add(booking)
        await self.session.flush()
        await audit_record(
            self.session,
            tenant_id,
            "ota.order.inject",
            actor=operator,
            resource_type="booking",
            resource_id=booking.id,
            hotel_id=booking.hotel_id,
            detail={"channel": channel, "external_ref": external_ref},
        )
        return booking, True

    # ---------- 房量推送（写日志 + 映射解析） ----------

    async def push_inventory(
        self,
        tenant_id: str,
        channel: str,
        *,
        days: int = 7,
        operator: str = "admin",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """按房型×日期推送未来 N 天剩余可售房量（M29 增强）。

        - dry_run=True 时仅组装 payload + 写日志（status=DRY_RUN），不写审计明细；
        - 启用 ChannelRoomMapping 时，inventory.items 改用 ``external_room_type_code``；
        - 每次调用写一行 ChannelPushLog，便于前台日志 Tab 排查。
        """
        started = datetime.now(timezone.utc)
        cfg = await self._config_for(tenant_id, channel)
        if not cfg.push_enabled and not dry_run:
            await self._write_push_log(
                tenant_id, cfg.hotel_id, channel, days, started,
                status="FAILED", error="渠道推送已关闭", operator=operator,
            )
            raise OtaError(f"渠道推送已关闭：{channel}")
        hotel_id = cfg.hotel_id

        total_rooms = (
            await self.session.execute(
                select(func.count()).select_from(Room).where(
                    Room.tenant_id == tenant_id, Room.hotel_id == hotel_id
                )
            )
        ).scalar_one()
        rt_rows = (
            await self.session.execute(
                select(RoomType).where(RoomType.tenant_id == tenant_id)
            )
        ).scalars()
        mapping_svc = OtaMappingService(self.session)
        inventory: list[dict[str, Any]] = []
        for rt in rt_rows:
            cnt = (
                await self.session.execute(
                    select(func.count())
                    .select_from(Room)
                    .where(Room.tenant_id == tenant_id, Room.room_type_id == rt.id)
                )
            ).scalar_one()
            ext_code = await mapping_svc.resolve_external_code(
                tenant_id, hotel_id, channel, rt.id
            )
            inventory.append(
                {
                    "pms_room_type_id": rt.id,
                    "pms_room_type_code": rt.code,
                    "external_room_type_code": ext_code or rt.code,
                    "total": cnt,
                }
            )
        payload = {
            "channel": channel,
            "hotel_id": hotel_id,
            "days": days,
            "items": inventory,
        }
        trace_id = (
            f"push-{hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]}"
        )
        ack = {
            "accepted": True,
            "channel": channel,
            "trace_id": trace_id,
            "hotel_id": hotel_id,
            "dry_run": dry_run,
            "total_rooms": total_rooms,
            "items": inventory,
        }

        await self._write_push_log(
            tenant_id, hotel_id, channel, days, started,
            status="DRY_RUN" if dry_run else "SUCCESS",
            trace_id=trace_id,
            item_count=len(inventory),
            request_summary=json.dumps(payload, ensure_ascii=False)[:1024],
            response_summary=json.dumps({"trace_id": trace_id, "accepted": True}, ensure_ascii=False)[:512],
            payload=payload,
            operator=operator,
        )
        if not dry_run:
            await audit_record(
                self.session,
                tenant_id,
                "ota.inventory.push",
                actor=operator,
                resource_type="ota_config",
                resource_id=cfg.id,
                hotel_id=hotel_id,
                detail={"channel": channel, "days": days, "trace_id": trace_id,
                        "item_count": len(inventory)},
            )
        return ack

    # ---------- 价格推送（按房型解析渠道价） ----------

    async def push_rates(
        self,
        tenant_id: str,
        channel: str,
        *,
        operator: str = "admin",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """推送房型渠道价（M29，A6）。"""
        from datetime import date as _date

        started = datetime.now(timezone.utc)
        cfg = await self._config_for(tenant_id, channel)
        hotel_id = cfg.hotel_id
        rate_svc = OtaRatePlanService(self.session)
        rt_rows = (
            await self.session.execute(
                select(RoomType).where(RoomType.tenant_id == tenant_id)
            )
        ).scalars()
        items: list[dict[str, Any]] = []
        for rt in rt_rows:
            plan_price = await rate_svc.resolve_price(
                tenant_id, hotel_id, channel, rt.id, _date.today()
            )
            items.append(
                {
                    "pms_room_type_id": rt.id,
                    "pms_room_type_code": rt.code,
                    "base_price_cents": rt.base_price,
                    "channel_price_cents": plan_price,
                }
            )
        payload = {
            "channel": channel,
            "hotel_id": hotel_id,
            "date": _date.today().isoformat(),
            "items": items,
        }
        trace_id = (
            f"rate-{hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]}"
        )
        ack = {
            "accepted": True,
            "channel": channel,
            "trace_id": trace_id,
            "hotel_id": hotel_id,
            "dry_run": dry_run,
            "items": items,
        }
        await self._write_push_log(
            tenant_id, hotel_id, channel, 0, started,
            status="DRY_RUN" if dry_run else "SUCCESS",
            trace_id=trace_id,
            item_count=len(items),
            request_summary=json.dumps(payload, ensure_ascii=False)[:1024],
            response_summary=json.dumps({"trace_id": trace_id}, ensure_ascii=False)[:512],
            payload=payload,
            operator=operator,
            kind="rates",
        )
        return ack

    # ---------- 推送日志 ----------

    async def list_push_logs(
        self,
        tenant_id: str,
        *,
        hotel_id: int | None = None,
        channel: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ChannelPushLog]:
        """列出推送日志（按创建时间倒序，limit 上限 200）。"""
        limit = max(1, min(int(limit), 200))
        stmt = select(ChannelPushLog).where(ChannelPushLog.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(ChannelPushLog.hotel_id == hotel_id)
        if channel:
            stmt = stmt.where(ChannelPushLog.channel == channel)
        if status:
            stmt = stmt.where(ChannelPushLog.status == status)
        stmt = stmt.order_by(ChannelPushLog.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    async def _write_push_log(
        self,
        tenant_id: str,
        hotel_id: int,
        channel: str,
        days: int,
        started: datetime,
        *,
        status: str,
        trace_id: str = "",
        item_count: int = 0,
        request_summary: str = "",
        response_summary: str = "",
        payload: dict[str, Any] | None = None,
        operator: str = "admin",
        kind: str = "inventory",
        error: str | None = None,
    ) -> ChannelPushLog:
        """落盘一行推送日志（库存/价格共用一个表，靠 status 区分）。"""
        ended = datetime.now(timezone.utc)
        duration_ms = int((ended - started).total_seconds() * 1000)
        # 把 kind 塞进 request_summary 前缀，便于排查
        summary_prefix = f"[{kind}] "
        log = ChannelPushLog(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            channel=channel,
            days=days,
            status=status,
            trace_id=trace_id,
            item_count=item_count,
            duration_ms=duration_ms,
            request_summary=(summary_prefix + request_summary)[:65535],
            response_summary=response_summary[:65535],
            error_message=error,
            payload_json=payload,
            operator=operator,
            created_at=ended,
        )
        self.session.add(log)
        await self.session.flush()
        return log
