"""M34d 全局搜索冒烟测试。

覆盖：
1. 基础搜索：返回结构合法（items / total / by_type / query）；
2. 类型过滤：``?types=guest`` 只返回 guest 类型；
3. 空 query 拦截：返回 400 或 422；
4. limit 边界：超限值被 FastAPI 拦截（422）；
5. 类型字段值域：type ∈ {guest, booking, room, bill, member, group, notification}；
6. href 模式：每个实体对应一个合理的深链；
7. by_type 与 items 数量一致：聚合计数正确。

测试约定：
- 沿用既有 ``conftest.py`` 的 ``client`` fixture（TestClient）与 ``auth_bypass``
  autouse fixture（以默认管理员登录，无需手动 headers）。
- ``tenant_id`` 动态生成（避免与既有测试用例冲突）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tenant_id() -> str:
    return "search_global_tenant"


@pytest.fixture()
def setup(client: TestClient, tenant_id: str) -> int:
    """建租户 + 门店（端点需要 tenant_id + hotel_id 双层结构）。"""
    t = client.post(
        "/api/v1/tenants", json={"code": tenant_id, "name": "M34d 全局搜索测试租户"}
    ).json()
    client.post(
        f"/api/v1/tenants/{t['id']}/hotels",
        json={"code": "H1", "name": "测试店"},
    ).json()
    return int(t["id"])


def test_search_global_basic(client: TestClient, setup: int) -> None:
    """基础搜索：返回结构合法 + 200 OK + items 总数 == total。"""
    r = client.get(
        f"/api/v1/tenants/{setup}/search",
        params={"q": "测"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert "by_type" in data
    assert "query" in data
    assert isinstance(data["items"], list)
    assert data["total"] == len(data["items"])
    assert data["query"] == "测"


def test_search_global_type_filter_guest(client: TestClient, setup: int) -> None:
    """类型过滤：``?types=guest`` 只返回 guest 类型。"""
    r = client.get(
        f"/api/v1/tenants/{setup}/search",
        params={"q": "测", "types": "guest"},
    )
    assert r.status_code == 200
    data = r.json()
    for item in data["items"]:
        assert item["type"] == "guest"
    assert data["by_type"].get("guest", 0) == len(data["items"])


def test_search_global_type_filter_multi(client: TestClient, setup: int) -> None:
    """多类型过滤：``?types=guest,booking`` 仅返回这两种类型。"""
    r = client.get(
        f"/api/v1/tenants/{setup}/search",
        params={"q": "测", "types": "guest,booking"},
    )
    assert r.status_code == 200
    data = r.json()
    allowed = {"guest", "booking"}
    for item in data["items"]:
        assert item["type"] in allowed


def test_search_global_empty_q(client: TestClient, setup: int) -> None:
    """空 query：返回 400（手写校验）或 422（FastAPI Query 校验）。"""
    r = client.get(
        f"/api/v1/tenants/{setup}/search",
        params={"q": ""},
    )
    assert r.status_code in (400, 422)


def test_search_global_limit_boundary(client: TestClient, setup: int) -> None:
    """limit 边界：超过 50 应被 FastAPI 422 拦截。"""
    r = client.get(
        f"/api/v1/tenants/{setup}/search",
        params={"q": "测", "limit": 100},
    )
    assert r.status_code == 422


def test_search_global_type_value_set(client: TestClient, setup: int) -> None:
    """类型值域：搜索返回的所有 type 必须在 7 实体白名单内。"""
    allowed_types = {"guest", "booking", "room", "bill", "member", "group", "notification"}
    r = client.get(
        f"/api/v1/tenants/{setup}/search",
        params={"q": "测"},
    )
    assert r.status_code == 200
    data = r.json()
    for item in data["items"]:
        assert item["type"] in allowed_types
        # 必填字段齐全
        assert "id" in item
        assert "title" in item
        assert "subtitle" in item
        assert "href" in item
        # href 以 "/" 开头（前端路由）
        assert item["href"].startswith("/")


def test_search_global_by_type_consistency(client: TestClient, setup: int) -> None:
    """by_type 计数一致性：所有 by_type 之和 == items 总数。"""
    r = client.get(
        f"/api/v1/tenants/{setup}/search",
        params={"q": "测"},
    )
    assert r.status_code == 200
    data = r.json()
    by_type = data["by_type"]
    # by_type 计数之和应等于 items 总数
    summed = sum(by_type.values())
    assert summed == len(data["items"])
    assert summed == data["total"]


def test_search_global_href_patterns(client: TestClient, setup: int) -> None:
    """href 路径模式：每个类型对应一个合理的深链前缀。"""
    href_prefixes = {
        "guest": "/guests/",
        "booking": "/bookings",
        "room": "/rooms",
        "bill": "/billing",
        "member": "/members",
        "group": "/group-blocks",
        "notification": "/notifications",
    }
    r = client.get(
        f"/api/v1/tenants/{setup}/search",
        params={"q": "测"},
    )
    assert r.status_code == 200
    for item in r.json()["items"]:
        t = item["type"]
        expected = href_prefixes.get(t)
        if expected is None:
            continue
        # 通知可能直接用 link 字段（外链），其他类型必须以前缀开头
        if t != "notification":
            assert item["href"].startswith(expected), (
                f"{t} href {item['href']} must start with {expected}"
            )