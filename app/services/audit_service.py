"""审计埋点 SDK（M8-2）。

统一的操作留痕入口，覆盖：改价(price.edit)、取消单(booking.cancel)、折扣(billing.discount)、
冲账(billing.adjust)、导出(audit.view)、登录(auth.login) 等敏感操作。
所有写操作经此记录，满足 WORM 审计基线与监管留痕要求。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def record(
    session: AsyncSession,
    tenant_id: str,
    action: str,
    *,
    actor: str,
    actor_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    hotel_id: int | None = None,
    ip: str | None = None,
    result: str = "success",
    detail: dict | None = None,
) -> AuditLog:
    """写入一条审计记录并 flush（由调用方统一 commit）。"""
    rid = str(resource_id) if resource_id is not None else None
    log = AuditLog(
        tenant_id=tenant_id,
        hotel_id=hotel_id,
        actor_id=actor_id,
        actor=actor,
        action=action,
        resource_type=resource_type or "",
        resource_id=rid,
        result=result,
        ip=ip,
        detail=detail or {},
    )
    session.add(log)
    await session.flush()
    return log
