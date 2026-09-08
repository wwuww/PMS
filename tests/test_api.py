"""API 集成测试：租户开通→房型→房间→房态流转→WebSocket 订阅（Sprint 1 验收链路）。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestHealth:
    def test_health(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestTenantOnboarding:
    def test_full_flow(self, client: TestClient) -> None:
        # 1. 开通租户
        resp = client.post(
            "/api/v1/tenants", json={"code": "demo-hotel", "name": "示例酒店"}
        )
        assert resp.status_code == 201
        tenant = resp.json()
        assert tenant["code"] == "demo-hotel"

        # 2. 建门店
        resp = client.post(
            f"/api/v1/tenants/{tenant['id']}/hotels",
            json={"code": "H001", "name": "示例酒店-总店"},
        )
        assert resp.status_code == 201
        hotel = resp.json()

        # 3. 建房型
        resp = client.post(
            f"/api/v1/tenants/{tenant['id']}/room-types",
            json={"code": "STD", "name": "标准间", "base_price": 28000},
        )
        assert resp.status_code == 201
        room_type = resp.json()

        # 4. 建房间
        resp = client.post(
            f"/api/v1/hotels/{hotel['id']}/rooms",
            json=[{"room_type_id": room_type["id"], "room_no": "0101", "floor": "1"}],
        )
        assert resp.status_code == 201
        assert resp.json()[0]["state"] == "vacant_clean"

    def test_duplicate_tenant_rejected(self, client: TestClient) -> None:
        client.post("/api/v1/tenants", json={"code": "dup", "name": "重复"})
        resp = client.post("/api/v1/tenants", json={"code": "dup", "name": "重复"})
        assert resp.status_code == 409


class TestRoomTransition:
    @pytest.fixture()
    def setup(self, client: TestClient) -> dict:  # noqa: ANN201
        tenant = client.post(
            "/api/v1/tenants", json={"code": "t-flow", "name": "流转测试"}
        ).json()
        hotel = client.post(
            f"/api/v1/tenants/{tenant['id']}/hotels",
            json={"code": "H1", "name": "店"},
        ).json()
        room_type = client.post(
            f"/api/v1/tenants/{tenant['id']}/room-types",
            json={"code": "STD", "name": "标间", "base_price": 10000},
        ).json()
        room = client.post(
            f"/api/v1/hotels/{hotel['id']}/rooms",
            json=[{"room_type_id": room_type["id"], "room_no": "0101"}],
        ).json()[0]
        return {"tenant": tenant, "room": room}

    def _transition(self, client: TestClient, tenant_code: str, room_no: str, trigger: str):  # noqa: ANN202
        return client.post(
            f"/api/v1/tenants/{tenant_code}/rooms/{room_no}/transition",
            json={"trigger": trigger, "operator": "front_desk"},
        )

    def test_checkin_checkout_cycle(self, client: TestClient, setup: dict) -> None:
        code = setup["tenant"]["code"]
        # 空净 → 在住
        resp = self._transition(client, code, "0101", "check_in")
        assert resp.status_code == 200
        assert resp.json()["state"] == "occupied"
        # 在住 → 空脏
        resp = self._transition(client, code, "0101", "check_out")
        assert resp.json()["state"] == "vacant_dirty"
        # 空脏 → 空净
        resp = self._transition(client, code, "0101", "clean_done")
        assert resp.json()["state"] == "vacant_clean"

    def test_illegal_transition_returns_422(self, client: TestClient, setup: dict) -> None:
        resp = self._transition(client, setup["tenant"]["code"], "0101", "check_out")
        assert resp.status_code == 422
        assert "非法流转" in resp.json()["detail"]

    def test_unknown_trigger_returns_422(self, client: TestClient, setup: dict) -> None:
        resp = self._transition(client, setup["tenant"]["code"], "0101", "explode")
        assert resp.status_code == 422

    def test_room_not_found(self, client: TestClient, setup: dict) -> None:
        resp = self._transition(client, setup["tenant"]["code"], "9999", "check_in")
        assert resp.status_code == 404


class TestWebSocketSubscription:
    """Sprint 1 验收标准：房态事件可订阅。"""

    def test_subscribe_room_state_events(self, client: TestClient) -> None:
        tenant = client.post(
            "/api/v1/tenants", json={"code": "t-ws", "name": "订阅测试"}
        ).json()
        hotel = client.post(
            f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "H1", "name": "店"}
        ).json()
        room_type = client.post(
            f"/api/v1/tenants/{tenant['id']}/room-types",
            json={"code": "STD", "name": "标间", "base_price": 10000},
        ).json()
        client.post(
            f"/api/v1/hotels/{hotel['id']}/rooms",
            json=[{"room_type_id": room_type["id"], "room_no": "0201"}],
        )

        # M18-3：WS 订阅需携带有效登录会话
        login = client.post(
            f"/api/v1/tenants/{tenant['code']}/auth/login",
            json={"username": "admin", "password": "admin123"},
        ).json()
        token = login["token"]

        with client.websocket_connect(
            f"/ws/rooms?tenant_id={tenant['code']}&token={token}"
        ) as ws:
            hello = ws.receive_json()
            assert hello["type"] == "subscribed"

            # 触发一次房态流转
            resp = client.post(
                f"/api/v1/tenants/{tenant['code']}/rooms/0201/transition",
                json={"trigger": "check_in", "operator": "front_desk"},
            )
            assert resp.status_code == 200

            # 验收：订阅方实时收到房态事件
            message = ws.receive_json()
            assert message["type"] == "event"
            data = message["data"]
            assert data["topic"] == "room.room.state_changed"
            assert data["from_state"] == "vacant_clean"
            assert data["to_state"] == "occupied"
            assert data["trigger"] == "check_in"
            assert data["tenant_id"] == tenant["code"]


class TestRateCode:
    def test_create_and_list(self, client: TestClient) -> None:
        tenant = client.post(
            "/api/v1/tenants", json={"code": "t-rc", "name": "价格码测试"}
        ).json()
        resp = client.post(
            f"/api/v1/tenants/{tenant['code']}/rate-codes",
            json={
                "code": "OTA-CTRIP-GOLD",
                "name": "携程金牌会员价",
                "channel": "ota_ctrip",
                "member_level": "gold",
                "discount_pct": 9200,
            },
        )
        assert resp.status_code == 201
        codes = client.get(f"/api/v1/tenants/{tenant['code']}/rate-codes").json()
        assert len(codes) == 1
        assert codes[0]["channel"] == "ota_ctrip"
