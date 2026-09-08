"""⑤ 实时推送（WebSocket）按 recipients 路由 — 真实服务冒烟验证。

连接 /ws/notifications → 触发审批通知 → 断言实时收到命中本人角色的通知载荷。
连接 /ws/notifications（无效 token）→ 断言 4401 拒绝。
"""

import asyncio
import json
import time

import httpx
import websockets

BASE = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000"


def _post(path: str, body: dict, token: str | None = None) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.post(BASE + path, json=body, headers=headers, timeout=15)


async def main() -> None:
    code = f"wsn-live-{int(time.time())}"
    # 1) 开通租户（公开）
    r = _post("/api/v1/tenants", {"code": code, "name": "live-smoke"})
    assert r.status_code in (200, 201), f"tenant create failed: {r.status_code} {r.text}"
    tid = r.json()["id"]
    # 2) 登录拿 token
    r = _post(f"/api/v1/tenants/{code}/auth/login", {"username": "admin", "password": "admin123"})
    assert r.status_code == 200 and r.json().get("status") == "ok", f"login failed: {r.text}"
    token = r.json()["token"]
    # 3) 建门店（需会话）
    r = _post(f"/api/v1/tenants/{tid}/hotels", {"code": "H", "name": "hotel-smoke"}, token)
    assert r.status_code in (200, 201), f"hotel create failed: {r.status_code} {r.text}"
    hotel_id = r.json()["id"]

    # 4) 鉴权失败 → 4401
    async with websockets.connect(f"{WS}/ws/notifications?tenant_id={code}&token=bad") as ws:
        hello = json.loads(await ws.recv())
        assert hello["type"] == "error", f"expected error, got {hello}"
        print("AUTH_REJECT_OK:", hello)

    # 5) 有效会话 → 订阅成功 + 实时收到审批通知
    async with websockets.connect(
        f"{WS}/ws/notifications?tenant_id={code}&token={token}"
    ) as ws:
        hello = json.loads(await ws.recv())
        assert hello["type"] == "subscribed", f"expected subscribed, got {hello}"
        assert "store_manager" in hello["tags"], f"tags missing store_manager: {hello}"
        print("SUBSCRIBED_OK:", hello)

        r = _post(
            f"/api/v1/tenants/{code}/approvals",
            {
                "hotel_id": hotel_id,
                "type": "OVERBOOK",
                "payload": {},
                "reason": "x",
                "applicant": "fd",
            },
            token,
        )
        assert r.status_code == 201, f"approval failed: {r.status_code} {r.text}"

        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        assert msg["type"] == "notification", f"expected notification, got {msg}"
        d = msg["data"]
        assert d["ref_type"] == "approval"
        assert d["recipients"] == ["store_manager"], d["recipients"]
        assert d["muted"] is False
        assert d["tenant_id"] == code
        assert d["notification_id"] > 0
        print("DELIVERY_OK:", d)

    print("LIVE_WS_SMOKE_PASSED")


asyncio.run(main())
