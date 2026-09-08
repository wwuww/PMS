"""Sprint 15 基础设施（缓存）+ M18 安全（刷新令牌/限流）+ M20 建议落地 测试。"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.infra.cache import MemoryBackend, get_cache, reset_cache
from app.infra.ratelimit import parse_limit, reset_rate_limiter


# ---------- 缓存单元 ----------


async def test_memory_backend_basic() -> None:
    b = MemoryBackend()
    assert await b.get("k") is None
    await b.set("k", {"v": 1}, ttl=60)
    assert await b.get("k") == {"v": 1}
    await b.delete("k")
    assert await b.get("k") is None


async def test_memory_backend_prefix_invalidate() -> None:
    b = MemoryBackend()
    await b.set("rooms:t1", [1])
    await b.set("rooms:t2", [2])
    await b.set("other:x", 3)
    n = await b.invalidate_prefix("rooms:")
    assert n == 2
    assert await b.get("rooms:t1") is None
    assert await b.get("rooms:t2") is None
    assert await b.get("other:x") == 3


def test_cache_default_backend_is_memory() -> None:
    reset_cache()
    assert get_cache().backend_name == "memory"
    reset_cache()


def test_parse_limit() -> None:
    assert parse_limit("240/60") == (240, 60)
    assert parse_limit("bad") == (0, 0)
    assert parse_limit("0/60") == (0, 0)


# ---------- 房态列表缓存 + 写失效 ----------


@pytest.fixture()
def infra_setup(client: TestClient) -> dict:  # noqa: ANN201
    reset_cache()
    # 雪花 ID 后租户主键为巨整数，必须从创建响应中取真实 id，不能硬编码 1
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-cache", "name": "缓存测试"}
    ).json()
    tid = tenant["id"]
    hotel = client.post(
        f"/api/v1/tenants/{tid}/hotels", json={"code": "HC1", "name": "缓存店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{tid}/room-types",
        json={"code": "STD", "name": "标准间", "base_price": 28000},
    ).json()
    client.post(
        f"/api/v1/hotels/{hotel['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0101", "floor": "1"}],
    )
    return {"hotel_id": hotel["id"], "tenant_id": tid}


def test_rooms_cache_and_invalidation(client: TestClient, infra_setup: dict) -> None:
    tenant_code = "t-cache"
    # 第一次：落库回填缓存
    r1 = client.get(f"/api/v1/tenants/{tenant_code}/rooms")
    assert r1.status_code == 200
    assert r1.json()[0]["state"] == "vacant_clean"
    # 缓存已填充
    assert client.get(f"/api/v1/tenants/{tenant_code}/rooms").status_code == 200

    # 写路径：状态机流转 → 缓存失效 → 新状态立即可见
    tr = client.post(
        f"/api/v1/tenants/{tenant_code}/rooms/0101/transition",
        json={"trigger": "lock_for_arrival", "operator": "tester"},
    )
    assert tr.status_code == 200
    r2 = client.get(f"/api/v1/tenants/{tenant_code}/rooms")
    assert r2.json()[0]["state"] == "arrival_locked"

    # state 过滤走缓存快照
    r3 = client.get(f"/api/v1/tenants/{tenant_code}/rooms?state=vacant_clean")
    assert r3.status_code == 200
    assert r3.json() == []


# ---------- M18-2 刷新令牌 ----------


class TestRefreshToken:
    def _login(self, client: TestClient) -> dict:
        client.post("/api/v1/tenants", json={"code": "t-auth", "name": "认证测试"})
        resp = client.post(
            "/api/v1/tenants/t-auth/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        return body

    def test_login_returns_refresh_token(self, client: TestClient) -> None:
        body = self._login(client)
        assert body["refresh_token"]
        assert len(body["refresh_token"]) >= 16
        assert body["token"]

    def test_refresh_rotation(self, client: TestClient) -> None:
        body = self._login(client)
        r = client.post(
            "/api/v1/tenants/t-auth/auth/refresh",
            json={"refresh_token": body["refresh_token"]},
        )
        assert r.status_code == 200
        out = r.json()
        assert out["token"] and out["refresh_token"]
        # 新 access token 可用
        assert (
            client.get(
                "/api/v1/tenants/t-auth/rooms",
                headers={"Authorization": f"Bearer {out['token']}"},
            ).status_code
            == 200
        )
        # 旧 refresh 已旋转作废 → 重放 401
        replay = client.post(
            "/api/v1/tenants/t-auth/auth/refresh",
            json={"refresh_token": body["refresh_token"]},
        )
        assert replay.status_code == 401

    def test_refresh_invalid_token(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/tenants/t-auth/auth/refresh",
            json={"refresh_token": "nonexistent"},
        )
        assert r.status_code == 401

    def test_logout_revokes_refresh_tokens(self, client: TestClient) -> None:
        body = self._login(client)
        lo = client.post(
            "/api/v1/tenants/t-auth/auth/logout",
            json={"token": body["token"]},
        )
        assert lo.status_code == 200
        r = client.post(
            "/api/v1/tenants/t-auth/auth/refresh",
            json={"refresh_token": body["refresh_token"]},
        )
        assert r.status_code == 401


# ---------- M18-2 接口限流 ----------


@pytest.fixture()
def rate_limited_client(client: TestClient, monkeypatch) -> TestClient:  # noqa: ANN001
    monkeypatch.setenv("PMS_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("PMS_RATE_LIMIT_DEFAULT", "3/60")
    monkeypatch.setenv("PMS_RATE_LIMIT_AUTH", "2/60")
    get_settings.cache_clear()
    reset_rate_limiter()
    yield client
    get_settings.cache_clear()
    reset_rate_limiter()


def test_rate_limit_default_bucket(rate_limited_client: TestClient) -> None:
    for _ in range(3):
        assert rate_limited_client.get("/health").status_code == 200
    r4 = rate_limited_client.get("/health")
    assert r4.status_code == 429
    assert "Retry-After" in r4.headers


def test_rate_limit_auth_bucket_isolated(rate_limited_client: TestClient) -> None:
    for _ in range(2):
        resp = rate_limited_client.post(
            "/api/v1/tenants/none/auth/login",
            json={"username": "xx", "password": "wrongpwd"},
        )
        assert resp.status_code == 200  # 业务层失败但未被限流
    # auth 桶耗尽 → 429
    resp = rate_limited_client.post(
        "/api/v1/tenants/none/auth/login",
        json={"username": "xx", "password": "wrongpwd"},
    )
    assert resp.status_code == 429
    # 默认桶不受 auth 桶影响
    assert rate_limited_client.get("/health").status_code == 200


def test_rate_limit_disabled_by_default(client: TestClient) -> None:
    for _ in range(6):
        assert client.get("/health").status_code == 200


# ---------- M20 建议一键应用 ----------


@pytest.fixture()
def yield_setup(client: TestClient) -> dict:  # noqa: ANN201
    # 雪花 ID 后租户主键为巨整数，必须从创建响应中取真实 id，不能硬编码 1
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-yield", "name": "收益测试"}
    ).json()
    tid = tenant["id"]
    hotel = client.post(
        f"/api/v1/tenants/{tid}/hotels", json={"code": "YH1", "name": "收益店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{tid}/room-types",
        json={"code": "STD", "name": "标准间", "base_price": 30000},
    ).json()
    rec = client.post(
        "/api/v1/tenants/t-yield/yield/pricing/recommend",
        json={
            "hotel_id": hotel["id"],
            "room_type_id": rt["id"],
            "business_date": "2026-09-10",
            "base_price_cents": 30000,
        },
    ).json()
    return {"hotel_id": hotel["id"], "room_type_id": rt["id"], "rec_id": rec["id"],
            "recommended": rec["recommended_price_cents"]}


def test_apply_recommendation_to_calendar(
    client: TestClient, yield_setup: dict
) -> None:
    r = client.post(
        f"/api/v1/tenants/t-yield/yield/pricing/recommendations/{yield_setup['rec_id']}/apply"
    )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "applied"
    assert out["price"] == yield_setup["recommended"]
    assert out["created"] == 1 and out["updated"] == 0  # 新建日历行
    assert out["dates"] == ["2026-09-10"]

    # 价格日历可见
    cal = client.get(
        f"/api/v1/tenants/t-yield/price-calendar?room_type_id={yield_setup['room_type_id']}"
        "&start=2026-09-10&end=2026-09-10"
    )
    assert cal.status_code == 200
    assert cal.json()[0]["price"] == yield_setup["recommended"]

    # 重复应用 → 409
    r2 = client.post(
        f"/api/v1/tenants/t-yield/yield/pricing/recommendations/{yield_setup['rec_id']}/apply"
    )
    assert r2.status_code == 409


def test_apply_recommendation_date_range(
    client: TestClient, yield_setup: dict
) -> None:
    # 区间应用：7 天逐日落价（含已有价的 09-10 会更新，其余新建）
    client.post(
        f"/api/v1/tenants/t-yield/price-calendar",
        json={"room_type_id": yield_setup["room_type_id"], "date": "2026-09-10", "price": 999},
    )
    r = client.post(
        f"/api/v1/tenants/t-yield/yield/pricing/recommendations/{yield_setup['rec_id']}/apply",
        json={"start": "2026-09-10", "end": "2026-09-16"},
    )
    assert r.status_code == 200
    out = r.json()
    assert len(out["dates"]) == 7
    assert out["updated"] == 1 and out["created"] == 6
    cal = client.get(
        f"/api/v1/tenants/t-yield/price-calendar?room_type_id={yield_setup['room_type_id']}"
        "&start=2026-09-10&end=2026-09-16"
    )
    rows = cal.json()
    assert len(rows) == 7
    assert all(row["price"] == yield_setup["recommended"] for row in rows)

    # 非法区间 → 400
    tenant_r = client.post(
        "/api/v1/tenants", json={"code": "t-yield-r", "name": "区间测试"}
    ).json()
    trid = tenant_r["id"]
    rt = client.post(
        f"/api/v1/tenants/{trid}/room-types",
        json={"code": "RSTD", "name": "区间房型", "base_price": 30000},
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{trid}/hotels", json={"code": "RH1", "name": "区间店"}
    ).json()
    rec = client.post(
        "/api/v1/tenants/t-yield-r/yield/pricing/recommend",
        json={"hotel_id": hotel["id"], "room_type_id": rt["id"],
              "business_date": "2026-09-10", "base_price_cents": 30000},
    ).json()
    bad = client.post(
        f"/api/v1/tenants/t-yield-r/yield/pricing/recommendations/{rec['id']}/apply",
        json={"start": "2026-09-16", "end": "2026-09-10"},
    )
    assert bad.status_code == 400


def test_apply_then_reject_conflict(client: TestClient, yield_setup: dict) -> None:
    r = client.post(
        f"/api/v1/tenants/t-yield/yield/pricing/recommendations/{yield_setup['rec_id']}/reject"
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    # rejected 后 apply → 409
    r2 = client.post(
        f"/api/v1/tenants/t-yield/yield/pricing/recommendations/{yield_setup['rec_id']}/apply"
    )
    assert r2.status_code == 409


def test_apply_not_found(client: TestClient) -> None:
    client.post("/api/v1/tenants", json={"code": "t-yield2", "name": "收益测试2"})
    r = client.post("/api/v1/tenants/t-yield2/yield/pricing/recommendations/999/apply")
    assert r.status_code == 404
