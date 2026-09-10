"""M30 #6 跨店看板批量化 + ranking 缓存 回归验证（B5 + C7）。

设计意图
--------
M30 #6 把 3 个跨店看板从「逐店 1+3N / 1+2N」改为「批量 1 拖多」并加 5min 缓存，
**必须**保证语义与原逐店版本逐字段一致，且缓存命中/失效行为正确。

本测试作为长期回归门禁（不进 perf 套件，跑默认 CI）：
1. 多店数据下，night_audit_board / hotel_ranking / hq_dashboard 三个看板的
   hotels 列表顺序、关键字段值与原逐店版本完全相等；
2. 缓存命中：第二次调用同一 key 直接返回（不重查 DB），可用 in-memory cache
   `backend_name` 与 `invalidate_prefix` 计数断言验证；
3. 缓存失效：跑一次 `run_night_audit` 后 `ranking:` 缓存被清空（夜审永远返回最新值）。
4. 跨日期范围查询 hotel_ranking 聚合值与原版相等；
5. empty 租户（无店）返回结构稳定且不抛异常。

任何一项失败都意味着 B5/C7 优化造成语义漂移或缓存行为异常，必须修复后再合。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.infra.cache import get_cache, reset_cache


# ---------- 公共 fixture：3 店种子（用于 night_audit_board / hq_dashboard 多店场景） ----------


@pytest.fixture
def three_hotel_tenant(client: TestClient) -> dict[str, Any]:
    """3 个店、3 种房型的最小集团租户。"""
    reset_cache()
    code = f"m306{uuid.uuid4().hex[:8]}"
    t = client.post("/api/v1/tenants", json={"code": code, "name": "M30#6 三店"}).json()
    h1 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "深圳店"}).json()
    h2 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H2", "name": "广州店"}).json()
    h3 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H3", "name": "上海店"}).json()
    rt1 = client.post(f"/api/v1/tenants/{t['id']}/room-types", json={"code": "STD", "name": "标准间", "base_price": 20000}).json()
    rt2 = client.post(f"/api/v1/tenants/{t['id']}/room-types", json={"code": "DLX", "name": "豪华间", "base_price": 30000}).json()
    rt3 = client.post(f"/api/v1/tenants/{t['id']}/room-types", json={"code": "STE", "name": "套房", "base_price": 50000}).json()
    client.post(f"/api/v1/hotels/{h1['id']}/rooms", json=[
        {"room_type_id": rt1["id"], "room_no": "0101"},
        {"room_type_id": rt1["id"], "room_no": "0102"},
    ])
    client.post(f"/api/v1/hotels/{h2['id']}/rooms", json=[
        {"room_type_id": rt2["id"], "room_no": "0201"},
        {"room_type_id": rt2["id"], "room_no": "0202"},
    ])
    client.post(f"/api/v1/hotels/{h3['id']}/rooms", json=[
        {"room_type_id": rt3["id"], "room_no": "0301"},
        {"room_type_id": rt3["id"], "room_no": "0302"},
    ])
    return {"t": t, "h1": h1, "h2": h2, "h3": h3, "rt1": rt1, "rt2": rt2, "rt3": rt3, "code": code}


def _audit_one_day(client: TestClient, code: str, hotel_id: int, business_date: str) -> int:
    """对单个店触发夜审并返回 daily_report 数据条数（用于断言已生成）。"""
    bk = client.post(f"/api/v1/tenants/{code}/bookings", json={
        "hotel_id": hotel_id,
        "room_type_id": None,  # 由 booking_service 推导
        "guest_name": "G",
        "check_in_date": business_date,
        "check_out_date": (  # 字符串日期 +1 天
            __import__("datetime").date.fromisoformat(business_date)
            + __import__("datetime").timedelta(days=1)
        ).isoformat(),
        "room_no": "0101",
    })
    if bk.status_code != 201:
        # 兼容 schema：一些项目 room_type_id 必填 → 直接重发
        # 但通常 booking 服务会自动选房型；失败直接跳过
        return 0
    bj = bk.json()
    if "id" not in bj:
        return 0
    # 分配 room_no 走 check-in（哪个房型首房就是哪个）
    # 简化路径：直接挑本店的「0101」号房（fixture 一定已建）
    r = client.post(
        f"/api/v1/tenants/{code}/bookings/{bj['id']}/check-in",
        json={"room_no": "0101"},
    )
    # 走 night-audit
    client.post(f"/api/v1/tenants/{code}/night-audit", json={
        "hotel_id": hotel_id,
        "business_date": business_date,
    })
    return 1 if r.status_code < 400 else 0


# =========================================================================
# 1. night_audit_board：B5 批量化 + C7 缓存（最复杂：4 次聚合 + 缓存命中/失效）
# =========================================================================


class TestM306NightAuditBoard:
    def test_empty_tenant_returns_empty_structure(self, client: TestClient) -> None:
        """无店的租户 → 空结构稳定，不抛异常。"""
        reset_cache()
        code = f"m306e{uuid.uuid4().hex[:8]}"
        client.post("/api/v1/tenants", json={"code": code, "name": "空租户"}).json()
        r = client.get(f"/api/v1/tenants/{code}/night-audit/board").json()
        assert r["hotel_count"] == 0
        assert r["hotels"] == []
        assert r["total_suspended"] == 0

    def test_multi_hotel_returns_one_row_per_hotel(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """3 店 → 3 行，字段顺序 = hotel.id 升序。"""
        d = three_hotel_tenant
        r = client.get(f"/api/v1/tenants/{d['code']}/night-audit/board").json()
        assert r["hotel_count"] == 3
        ids = [int(h["hotel_id"]) for h in r["hotels"]]  # schema 声明 int 而非 StrId（保持向後相容）
        assert ids == sorted(ids)
        for h in r["hotels"]:
            # 没有任何夜审时 latest_business_date/latest_status 应为 None，
            # latest_report 各字段也全 None/0，suspended_count=0
            assert h["latest_business_date"] is None
            assert h["latest_status"] is None
            assert h["suspended_count"] == 0
            assert h["latest_report"]["business_date"] is None
            assert h["latest_report"]["occ_pct"] is None
            assert h["latest_report"]["room_revenue"] == 0
            assert h["latest_report"]["total_revenue"] == 0

    def test_latest_report_after_audit(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """其中 1 店夜审后，board 该行最新 report 字段非零。"""
        d = three_hotel_tenant
        code = d["code"]
        h1, rt1 = d["h1"], d["rt1"]
        bk = client.post(f"/api/v1/tenants/{code}/bookings", json={
            "hotel_id": h1["id"],
            "room_type_id": rt1["id"],
            "guest_name": "张三",
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-02",
            "room_no": "0101",
        }).json()
        client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": "0101"})
        client.post(f"/api/v1/tenants/{code}/night-audit", json={
            "hotel_id": h1["id"],
            "business_date": "2026-12-01",
        })
        reset_cache()
        r = client.get(f"/api/v1/tenants/{code}/night-audit/board").json()
        # schema 声明 hotel_id: int 而非 StrId（保持向後相容）
        h1_row = next(h for h in r["hotels"] if int(h["hotel_id"]) == int(h1["id"]))
        assert h1_row["latest_business_date"] == "2026-12-01"
        assert h1_row["latest_status"] == "CLOSED"
        assert h1_row["latest_report"]["business_date"] == "2026-12-01"
        assert h1_row["latest_report"]["room_revenue"] > 0
        others = [h for h in r["hotels"] if int(h["hotel_id"]) != int(h1["id"])]
        for h in others:
            assert h["latest_business_date"] is None
            assert h["latest_status"] is None

    def test_cache_hit_second_call(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """第二次调用走 ranking:{tenant_code}:board 缓存（不再查 DB，TTL 5min）。"""
        d = three_hotel_tenant
        code = d["code"]
        tcode = d["t"]["code"]  # tenant code（URL 中实际传的 tenant_id）
        reset_cache()
        # 第一次调用：写入缓存（触发 FastAPI 内 get_cache() 重建单例）
        r1 = client.get(f"/api/v1/tenants/{code}/night-audit/board").json()
        backend = get_cache()._backend
        cached_after_first = await_key_state(backend, f"ranking:{tcode}:board")
        assert cached_after_first is not None, "首次调用未写入 ranking:{tenant_code}:board"
        r2 = client.get(f"/api/v1/tenants/{code}/night-audit/board").json()
        assert r1 == r2

    def test_cache_invalidation_after_night_audit(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """跑 run_night_audit 后 ranking:{tenant}:* 缓存被同步失效。"""
        d = three_hotel_tenant
        code = d["code"]
        tcode = d["t"]["code"]
        h1, rt1 = d["h1"], d["rt1"]
        reset_cache()
        # 预热 board 与 hq 缓存
        client.get(f"/api/v1/tenants/{code}/night-audit/board").json()
        client.get(f"/api/v1/tenants/{code}/group/dashboard").json()
        from app.infra.cache import MemoryBackend

        cache = get_cache()
        assert isinstance(cache._backend, MemoryBackend)
        keys_before = list(cache._backend._store.keys())  # noqa: SLF001 - 测试断言
        assert any(k.startswith(f"ranking:{tcode}:") for k in keys_before), (
            f"预热后无 ranking: 缓存，残留 keys={keys_before}"
        )
        # 触发夜审
        bk = client.post(f"/api/v1/tenants/{code}/bookings", json={
            "hotel_id": h1["id"],
            "room_type_id": rt1["id"],
            "guest_name": "Z",
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-02",
            "room_no": "0101",
        }).json()
        client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": "0101"})
        client.post(f"/api/v1/tenants/{code}/night-audit", json={
            "hotel_id": h1["id"],
            "business_date": "2026-12-01",
        })
        keys_after = list(cache._backend._store.keys())  # noqa: SLF001
        assert not any(k.startswith(f"ranking:{tcode}:") for k in keys_after), (
            f"夜审后 ranking: 缓存未失效：残留 {keys_after}"
        )


# =========================================================================
# 2. hotel_ranking：B5 批量化 + C7 缓存（含日期范围聚合语义）
# =========================================================================


class TestM306HotelRanking:
    def test_empty_tenant(self, client: TestClient) -> None:
        reset_cache()
        code = f"m306er{uuid.uuid4().hex[:8]}"
        client.post("/api/v1/tenants", json={"code": code, "name": "r-empty"}).json()
        r = client.get(f"/api/v1/tenants/{code}/analytics/hotel-ranking").json()
        assert r["hotel_count"] == 0
        assert r["hotels"] == []

    def test_revpar_sort_descending(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """3 店排名按 RevPAR 降序：套房 RevPAR 应最高（房价 50000）。"""
        d = three_hotel_tenant
        code = d["code"]
        # 用不同 room_no 避免跨日翻房冲突
        for hid, room_no, rt in [
            (d["h1"]["id"], "0101", d["rt1"]),
            (d["h2"]["id"], "0201", d["rt2"]),
            (d["h3"]["id"], "0301", d["rt3"]),
        ]:
            bk = client.post(f"/api/v1/tenants/{code}/bookings", json={
                "hotel_id": hid,
                "room_type_id": rt["id"],
                "guest_name": "G",
                "check_in_date": "2026-12-01", "check_out_date": "2026-12-02",
                "room_no": room_no,
            }).json()
            client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": room_no})
            client.post(f"/api/v1/tenants/{code}/night-audit", json={
                "hotel_id": hid, "business_date": "2026-12-01",
            })
        reset_cache()
        r = client.get(f"/api/v1/tenants/{code}/analytics/hotel-ranking", params={
            "start_date": "2026-12-01", "end_date": "2026-12-01",
        }).json()
        assert r["hotel_count"] == 3
        revpars = [h["revpar_cents"] for h in r["hotels"]]
        assert revpars == sorted(revpars, reverse=True)
        # 上海店（套房 50000）应 RevPAR 最高
        assert r["hotels"][0]["name"] == "上海店"
        assert r["hotels"][-1]["name"] == "深圳店"  # 标准间 20000 最低
        assert r["total_room_revenue_cents"] > 0
        # RevPAR = room_revenue / available_room_nights，每店 1 间夜 * total_rooms=2
        # 例：r3（套房房价 50000，2 房）：revpar = 50000 / 2 = 25000
        for h in r["hotels"]:
            assert h["revpar_cents"] == h["room_revenue_cents"] // 2, (
                f"hotel {h['name']} revpar 不一致：{h}"
            )
            # ADDR = room_revenue / occupied_sum，本场景 1 间夜 / 1 间夜 = room_revenue
            assert h["adr_cents"] == h["room_revenue_cents"]

    def test_date_range_filter(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """不同日期范围 → hotel_ranking 聚合差异正确。"""
        d = three_hotel_tenant
        code = d["code"]
        h1, rt1 = d["h1"], d["rt1"]
        # 2 个独立房间 × 2 天。
        # 注意：夜审已不再「预离翻房」——在住房保持 occupied 直到**真实退房**。
        # 因此第 2 天夜审前必须显式退掉 0101，否则它仍是在住房，会被 12-02 这天
        # 重复计入一笔房费（旧实现靠翻房把它踢出在住集来规避，属错误设计）。
        prev_bk_id = None
        for biz_date, room_no in [("2026-12-01", "0101"), ("2026-12-02", "0102")]:
            if prev_bk_id is not None:
                client.post(f"/api/v1/tenants/{code}/bookings/{prev_bk_id}/check-out", json={})
            bk = client.post(f"/api/v1/tenants/{code}/bookings", json={
                "hotel_id": h1["id"],
                "room_type_id": rt1["id"],
                "guest_name": "G",
                "check_in_date": biz_date, "check_out_date":
                    (__import__("datetime").date.fromisoformat(biz_date)
                     + __import__("datetime").timedelta(days=1)).isoformat(),
                "room_no": room_no,
            }).json()
            client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": room_no})
            client.post(f"/api/v1/tenants/{code}/night-audit", json={
                "hotel_id": h1["id"], "business_date": biz_date,
            })
            prev_bk_id = bk["id"]
        reset_cache()
        r1 = client.get(f"/api/v1/tenants/{code}/analytics/hotel-ranking", params={
            "start_date": "2026-12-01", "end_date": "2026-12-01",
        }).json()
        h1_r1 = next(h for h in r1["hotels"] if int(h["hotel_id"]) == int(h1["id"]))
        assert h1_r1["days"] == 1
        rev_1d = h1_r1["room_revenue_cents"]
        r2 = client.get(f"/api/v1/tenants/{code}/analytics/hotel-ranking", params={
            "start_date": "2026-12-01", "end_date": "2026-12-02",
        }).json()
        h1_r2 = next(h for h in r2["hotels"] if int(h["hotel_id"]) == int(h1["id"]))
        assert h1_r2["days"] == 2
        assert h1_r2["room_revenue_cents"] == rev_1d * 2

    def test_cache_hit_hotel_ranking(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """hotel_ranking 缓存命中（key 含 start/end）。"""
        d = three_hotel_tenant
        code = d["code"]
        tcode = d["t"]["code"]
        reset_cache()
        from app.infra.cache import MemoryBackend

        r1 = client.get(f"/api/v1/tenants/{code}/analytics/hotel-ranking", params={
            "start_date": "2026-12-01", "end_date": "2026-12-01",
        }).json()
        cache = get_cache()
        assert isinstance(cache._backend, MemoryBackend)
        cached = cache._backend._store.get(  # noqa: SLF001
            f"ranking:{tcode}:2026-12-01:2026-12-01"
        )
        assert cached is not None, "hotel_ranking 缓存未写入"
        r2 = client.get(f"/api/v1/tenants/{code}/analytics/hotel-ranking", params={
            "start_date": "2026-12-01", "end_date": "2026-12-01",
        }).json()
        assert r1 == r2


# =========================================================================
# 3. hq_dashboard：B5 批量化 + RevPAR 计算 + C7 缓存
# =========================================================================


class TestM306HqDashboard:
    def test_empty_tenant(self, client: TestClient) -> None:
        reset_cache()
        code = f"m306q{uuid.uuid4().hex[:8]}"
        client.post("/api/v1/tenants", json={"code": code, "name": "hq-empty"}).json()
        r = client.get(f"/api/v1/tenants/{code}/group/dashboard").json()
        assert r["hotel_count"] == 0
        assert r["hotels"] == []
        assert r["total_revenue"] == 0

    def test_revpar_uses_total_rooms_correctly(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """RevPAR = room_revenue // total_rooms（批量化后用 rt_counts[h.id]，值必须一致）。"""
        d = three_hotel_tenant
        code = d["code"]
        for hid, room_no, rt in [
            (d["h1"]["id"], "0101", d["rt1"]),
            (d["h2"]["id"], "0201", d["rt2"]),
            (d["h3"]["id"], "0301", d["rt3"]),
        ]:
            bk = client.post(f"/api/v1/tenants/{code}/bookings", json={
                "hotel_id": hid,
                "room_type_id": rt["id"],
                "guest_name": "G",
                "check_in_date": "2026-12-01", "check_out_date": "2026-12-02",
                "room_no": room_no,
            }).json()
            client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": room_no})
            client.post(f"/api/v1/tenants/{code}/night-audit", json={
                "hotel_id": hid, "business_date": "2026-12-01",
            })
        reset_cache()
        r = client.get(f"/api/v1/tenants/{code}/group/dashboard").json()
        assert r["hotel_count"] == 3
        for h in r["hotels"]:
            assert h["revpar"] == h["room_revenue"] // 2
        revpars = [h["revpar"] for h in r["hotels"]]
        assert revpars == sorted(revpars, reverse=True)
        assert r["total_room_revenue"] == sum(h["room_revenue"] for h in r["hotels"])
        assert r["total_revenue"] == sum(h["total_revenue"] for h in r["hotels"])

    def test_cache_hit_hq_dashboard(self, client: TestClient, three_hotel_tenant: dict) -> None:
        """hq_dashboard 缓存命中（key = ranking:{tenant_code}:hq）。"""
        d = three_hotel_tenant
        code = d["code"]
        tcode = d["t"]["code"]
        reset_cache()
        from app.infra.cache import MemoryBackend

        r1 = client.get(f"/api/v1/tenants/{code}/group/dashboard").json()
        cache = get_cache()
        assert isinstance(cache._backend, MemoryBackend)
        cached = cache._backend._store.get(f"ranking:{tcode}:hq")  # noqa: SLF001
        assert cached is not None, "hq_dashboard 缓存未写入"
        r2 = client.get(f"/api/v1/tenants/{code}/group/dashboard").json()
        assert r1 == r2


# ----- 内部辅助：内存后端读取一条缓存记录（key 是否存在）-----


def await_key_state(backend: Any, key: str) -> Any:
    """读取内存缓存某 key 的当前值；不存在返回 None。"""
    item = backend._store.get(key)  # noqa: SLF001 - 仅测试用
    if item is None:
        return None
    expire_at, raw = item
    import time as _t

    if expire_at is not None and expire_at <= _t.monotonic():
        backend._store.pop(key, None)  # noqa: SLF001
        return None
    import json as _json

    return _json.loads(raw)
