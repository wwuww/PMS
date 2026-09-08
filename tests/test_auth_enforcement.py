"""强制鉴权回归测试（Sprint 14）。

本文件全部用例标记 ``@pytest.mark.auth``，退出 conftest 的测试态鉴权旁路，
直接验证 M8-3 认证层 / 授权层的真实行为：

- 认证层：无 token / 伪造 token → 401（白名单端点除外）；
- 授权层：登录但缺权限点 → 403；管理员 → 通过；
- 门店路径（``/hotels/{hotel_id}/rooms``）携带有效 token → 可用（回归：
  此前租户解析只认 ``/tenants/{id}/...``，导致该路径恒 401）。
"""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.auth

ADMIN = {"username": "admin", "password": "admin123"}


def _seed(client: TestClient, code: str = "authz") -> dict:
    """开通租户（公开端点）+ 用管理员 token 建门店/房型（受保护端点）。"""
    t = client.post("/api/v1/tenants", json={"code": code, "name": "鉴权测试"}).json()
    token = client.post(
        f"/api/v1/tenants/{code}/auth/login", json=ADMIN
    ).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    # 注意：酒店/房型的 tenant_id 路径参数是整型 id，其余业务端点用租户编码
    h = client.post(
        f"/api/v1/tenants/{t['id']}/hotels",
        json={"code": "H1", "name": "一号店"},
        headers=auth,
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
        headers=auth,
    ).json()
    return {"t": t, "token": token, "auth": auth, "h": h, "rt": rt}


class TestAuthenticationLayer:
    def test_no_token_returns_401(self, client: TestClient) -> None:
        _seed(client, "authz1")
        r = client.get("/api/v1/tenants/authz1/rooms")
        assert r.status_code == 401
        assert "凭证" in r.json()["detail"]

    def test_forged_token_returns_401(self, client: TestClient) -> None:
        _seed(client, "authz2")
        r = client.get(
            "/api/v1/tenants/authz2/rooms",
            headers={"Authorization": "Bearer forged-token-not-exists"},
        )
        assert r.status_code == 401

    def test_valid_token_passes(self, client: TestClient) -> None:
        d = _seed(client, "authz3")
        r = client.get("/api/v1/tenants/authz3/rooms", headers=d["auth"])
        assert r.status_code == 200

    def test_public_endpoints_open(self, client: TestClient) -> None:
        # 租户开通 / 登录 属白名单，无需 token
        r = client.post("/api/v1/tenants", json={"code": "authz4", "name": "公开"})
        assert r.status_code == 201
        r2 = client.post(
            "/api/v1/tenants/authz4/auth/login",
            json={"username": "nobody", "password": "whatever1"},
        )
        assert r2.status_code == 200  # 登录失败也返回 200 + status=bad_credentials


class TestHotelPathTenantResolution:
    def test_hotel_scoped_room_create_works_with_token(self, client: TestClient) -> None:
        """回归：/hotels/{hotel_id}/rooms 需按门店反查租户，带 token 应可用。"""
        d = _seed(client, "authz5")
        hotel_id = d["h"]["id"]
        r = client.post(
            f"/api/v1/hotels/{hotel_id}/rooms",
            json=[{"room_type_id": d["rt"]["id"], "room_no": "0101"}],
            headers=d["auth"],
        )
        assert r.status_code == 201, r.text

    def test_hotel_scoped_path_rejects_missing_token(self, client: TestClient) -> None:
        d = _seed(client, "authz6")
        r = client.post(
            f"/api/v1/hotels/{d['h']['id']}/rooms",
            json=[{"room_type_id": d["rt"]["id"], "room_no": "0102"}],
        )
        assert r.status_code == 401


class TestAuthorizationLayer:
    def _staff_token(self, client: TestClient, code: str, d: dict) -> str:
        """建一个「前台」账号（仅 booking.cancel/billing.discount/billing.refund）并登录。"""
        u = client.post(
            f"/api/v1/tenants/{code}/users",
            json={"username": "desk", "password": "pw123456"},
            headers=d["auth"],
        ).json()
        roles = client.get(f"/api/v1/tenants/{code}/roles", headers=d["auth"]).json()
        front = next(r for r in roles if r["name"] == "前台")
        client.post(
            f"/api/v1/tenants/{code}/users/{u['id']}/roles",
            json={"role_id": front["id"], "hotel_id": d["h"]["id"]},
            headers=d["auth"],
        )
        return client.post(
            f"/api/v1/tenants/{code}/auth/login",
            json={"username": "desk", "password": "pw123456"},
        ).json()["token"]

    def test_staff_denied_on_night_audit(self, client: TestClient) -> None:
        d = _seed(client, "authz7")
        token = self._staff_token(client, "authz7", d)
        r = client.post(
            "/api/v1/tenants/authz7/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert "night_audit.run" in r.json()["detail"]

    def test_admin_allowed_on_night_audit(self, client: TestClient) -> None:
        d = _seed(client, "authz8")
        r = client.post(
            "/api/v1/tenants/authz8/night-audit/auto-run",
            json={"as_of": "2026-10-01"},
            headers=d["auth"],
        )
        assert r.status_code == 200
        assert r.json()["ran"] >= 1

    def test_staff_denied_on_user_create(self, client: TestClient) -> None:
        d = _seed(client, "authz9")
        token = self._staff_token(client, "authz9", d)
        r = client.post(
            "/api/v1/tenants/authz9/users",
            json={"username": "x", "password": "pw123456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
