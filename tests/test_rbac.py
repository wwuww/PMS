"""Sprint 7 测试：权限审计 M8（RBAC + 登录安全 + 审计）。

验证：
- 租户开通播种默认三档角色；
- 建用户 + 登录成功返回 token/权限；
- 连续失败触发账号锁定；
- 门店级角色按门店作用域生效；
- 审计查看权限校验（越权拒绝）。
"""

from fastapi.testclient import TestClient


def _seed_tenant(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "rbac1", "name": "权限测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "0301"}])
    return {"t": t, "h": h, "rt": rt}


class TestRbac:
    def test_default_roles_seeded(self, client: TestClient) -> None:
        d = _seed_tenant(client)
        roles = client.get(f"/api/v1/tenants/{d['t']['code']}/roles").json()
        names = {r["name"] for r in roles}
        assert {"管理员", "门店经理", "前台"} <= names
        admin = next(r for r in roles if r["name"] == "管理员")
        assert admin["is_system"] is True
        assert admin["hotel_scoped"] is False

    def test_create_user_and_login(self, client: TestClient) -> None:
        d = _seed_tenant(client)
        user = client.post(
            f"/api/v1/tenants/{d['t']['code']}/users",
            json={"username": "alice", "password": "secret1", "display_name": "阿丽"},
        ).json()
        assert user["status"] == "active"
        # 绑定管理员角色
        roles = client.get(f"/api/v1/tenants/{d['t']['code']}/roles").json()
        admin = next(r for r in roles if r["name"] == "管理员")
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/users/{user['id']}/roles",
            json={"role_id": admin["id"]},
        )
        login = client.post(
            f"/api/v1/tenants/{d['t']['code']}/auth/login",
            json={"username": "alice", "password": "secret1"},
        ).json()
        assert login["status"] == "ok"
        assert login["token"] is not None
        assert "billing.discount" in login["permissions"]

    def test_login_failure_locks_account(self, client: TestClient) -> None:
        d = _seed_tenant(client)
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/users",
            json={"username": "bob", "password": "rightpw"},
        )
        # 连续 5 次错误密码（注意：密码字段最小长度 6）
        last = None
        for _ in range(5):
            last = client.post(
                f"/api/v1/tenants/{d['t']['code']}/auth/login",
                json={"username": "bob", "password": "wrongpw"},
            ).json()
        assert last["status"] == "bad_credentials"
        # 第 6 次（即便密码正确）应被锁定
        locked = client.post(
            f"/api/v1/tenants/{d['t']['code']}/auth/login",
            json={"username": "bob", "password": "rightpw"},
        ).json()
        assert locked["status"] == "locked"

    def test_hotel_scoped_permission(self, client: TestClient) -> None:
        d = _seed_tenant(client)
        user = client.post(
            f"/api/v1/tenants/{d['t']['code']}/users",
            json={"username": "mgr", "password": "pw123456"},
        ).json()
        roles = client.get(f"/api/v1/tenants/{d['t']['code']}/roles").json()
        manager = next(r for r in roles if r["name"] == "门店经理")
        # 门店经理角色绑定到具体门店 H
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/users/{user['id']}/roles",
            json={"role_id": manager["id"], "hotel_id": d["h"]["id"]},
        )
        login = client.post(
            f"/api/v1/tenants/{d['t']['code']}/auth/login",
            json={"username": "mgr", "password": "pw123456"},
        ).json()
        assert login["status"] == "ok"
        token = login["token"]
        # 登录态概览：返回任意门店权限并集（门店级角色也应可见）
        assert "night_audit.run" in login["permissions"]
        # 对绑定门店 H：拥有夜审权限
        ok = client.post(
            f"/api/v1/tenants/{d['t']['code']}/auth/check",
            json={"token": token, "permission": "night_audit.run", "hotel_id": d["h"]["id"]},
        ).json()
        assert ok["granted"] is True
        # 对非绑定门店：经理权限不生效
        denied = client.post(
            f"/api/v1/tenants/{d['t']['code']}/auth/check",
            json={"token": token, "permission": "night_audit.run", "hotel_id": 999999},
        ).json()
        assert denied["granted"] is False

    def test_audit_view_permission_enforced(self, client: TestClient) -> None:
        d = _seed_tenant(client)
        # 前台账号（无 audit.view）
        staff = client.post(
            f"/api/v1/tenants/{d['t']['code']}/users",
            json={"username": "desk", "password": "pw123456"},
        ).json()
        roles = client.get(f"/api/v1/tenants/{d['t']['code']}/roles").json()
        front = next(r for r in roles if r["name"] == "前台")
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/users/{staff['id']}/roles",
            json={"role_id": front["id"], "hotel_id": d["h"]["id"]},
        )
        staff_login = client.post(
            f"/api/v1/tenants/{d['t']['code']}/auth/login",
            json={"username": "desk", "password": "pw123456"},
        ).json()
        assert staff_login["status"] == "ok"
        # 前台无审计查看权限 → 查询 403
        resp = client.get(
            f"/api/v1/tenants/{d['t']['code']}/audit-logs?token={staff_login['token']}"
        )
        assert resp.status_code == 403
        # 管理员有审计查看权限
        admin = client.post(
            f"/api/v1/tenants/{d['t']['code']}/users",
            json={"username": "boss", "password": "pw123456"},
        ).json()
        admin_role = next(r for r in roles if r["name"] == "管理员")
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/users/{admin['id']}/roles",
            json={"role_id": admin_role["id"]},
        )
        admin_login = client.post(
            f"/api/v1/tenants/{d['t']['code']}/auth/login",
            json={"username": "boss", "password": "pw123456"},
        ).json()
        resp2 = client.get(
            f"/api/v1/tenants/{d['t']['code']}/audit-logs?token={admin_login['token']}"
        )
        assert resp2.status_code == 200
