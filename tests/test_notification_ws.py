"""⑤ 实时推送（WebSocket）按 recipients 路由（M10-4 增强）。

覆盖：
1. RBAC 角色档位 → 通知接收标签映射（recipient_tags_for_roles）；
2. 实时路由判定（notification_matches：命中/静音跳过/无交集跳过/空 recipients 跳过）；
3. /ws/notifications 端点到鉴权（无效会话 4401）；
4. 端到端：admin 连接后触发审批通知，实时收到命中本人角色的通知载荷。
"""

from fastapi.testclient import TestClient

from app.api.ws import notification_matches, recipient_tags_for_roles


class TestNotificationRoutingLogic:
    def test_recipient_tags_for_roles(self) -> None:
        assert recipient_tags_for_roles(["ADMIN"]) == {
            "store_manager",
            "front_desk",
            "night_audit",
        }
        assert recipient_tags_for_roles(["MANAGER"]) == {"store_manager"}
        assert recipient_tags_for_roles(["STAFF"]) == {"front_desk"}
        # 多角色取并集
        assert recipient_tags_for_roles(["MANAGER", "STAFF"]) == {
            "store_manager",
            "front_desk",
        }
        assert recipient_tags_for_roles([]) == set()

    def test_notification_matches(self) -> None:
        tags = {"store_manager"}
        # 命中本人角色 → 下发
        assert notification_matches(tags, ["store_manager"], False) is True
        # 角色无交集 → 不下发
        assert notification_matches(tags, ["front_desk"], False) is False
        # 免打扰静音 → 不下发
        assert notification_matches(tags, ["store_manager"], True) is False
        # ④ 空 recipients=不推送任何人
        assert notification_matches(tags, [], False) is False
        # 连接方无任何接收标签 → 不下发
        assert notification_matches(set(), ["store_manager"], False) is False


class TestNotificationWsAuth:
    def test_requires_valid_token(self, client: TestClient) -> None:
        client.post("/api/v1/tenants", json={"code": "wsn0", "name": "WS通知鉴权"})
        # 无 token → 4401 拒绝
        with client.websocket_connect("/ws/notifications?tenant_id=wsn0") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
        # 有效 token → 订阅成功并回带本人标签
        login = client.post(
            "/api/v1/tenants/wsn0/auth/login",
            json={"username": "admin", "password": "admin123"},
        ).json()
        token = login["token"]
        with client.websocket_connect(
            f"/ws/notifications?tenant_id=wsn0&token={token}"
        ) as ws:
            hello = ws.receive_json()
            assert hello["type"] == "subscribed"
            assert hello["topic"] == "notification.pushed"
            assert "store_manager" in hello["tags"]


class TestNotificationWsDelivery:
    def test_admin_receives_approval_notification(self, client: TestClient) -> None:
        """端到端：admin 连接 → 触发审批通知（默认 recipients=['store_manager']）→ 实时收到。"""
        t = client.post(
            "/api/v1/tenants", json={"code": "wsn1", "name": "WS通知"}
        ).json()
        h = client.post(
            f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}
        ).json()
        login = client.post(
            f"/api/v1/tenants/{t['code']}/auth/login",
            json={"username": "admin", "password": "admin123"},
        ).json()
        token = login["token"]

        with client.websocket_connect(
            f"/ws/notifications?tenant_id={t['code']}&token={token}"
        ) as ws:
            hello = ws.receive_json()
            assert hello["type"] == "subscribed"
            assert "store_manager" in hello["tags"]

            # 触发审批通知（默认派发给 store_manager）
            resp = client.post(
                f"/api/v1/tenants/{t['code']}/approvals",
                json={
                    "hotel_id": h["id"],
                    "type": "OVERBOOK",
                    "payload": {},
                    "reason": "x",
                    "applicant": "fd",
                },
            )
            assert resp.status_code == 201

            # 验收：订阅方实时收到命中本人角色的通知
            msg = ws.receive_json()
            assert msg["type"] == "notification"
            data = msg["data"]
            assert data["ref_type"] == "approval"
            assert data["recipients"] == ["store_manager"]
            assert data["muted"] is False
            assert data["tenant_id"] == t["code"]
            assert data["notification_id"] > 0
            assert data["title"]
