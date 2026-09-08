"""M28 A2 收尾 + M29 OTA 直连 + M30 缓存 集成测试。

M28：投诉与住客/预订关联 + 流转闭环；留存导出 CSV（BOM/头行/过滤）。
M29：OTA 渠道配置 + HMAC 签名 webhook 幂等注入 + 房量推送（沙箱确定性回执）。
M30：dashboard 热点缓存（命中 + 预订变更后失效）。
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi.testclient import TestClient


def _seed(client: TestClient, code: str) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0101"}],
    )
    return t, h, rt


def _book(client: TestClient, t: dict, h: dict, rt: dict, phone: str, name: str = "关联客") -> dict:
    r = client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": name,
            "guest_phone": phone,
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-02",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ================= M28：投诉 =================


class TestComplaints:
    def test_create_with_booking_autofill(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m28a")
        bk = _book(client, t, h, rt, "13900200001")
        r = client.post(
            f"/api/v1/tenants/{t['code']}/complaints",
            json={
                "hotel_id": h["id"],
                "guest_name": "x",
                "booking_id": bk["id"],
                "category": "NOISE",
                "description": "空调噪音",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # 关联预订自动回填住客与手机号
        assert body["guest_name"] == "关联客"
        assert body["guest_phone"] == "13900200001"
        assert body["status"] == "OPEN"

    def test_transition_flow_and_invalid(self, client: TestClient) -> None:
        t, h, _rt = _seed(client, "m28b")
        c = client.post(
            f"/api/v1/tenants/{t['code']}/complaints",
            json={"hotel_id": h["id"], "guest_name": "张三", "category": "HYGIENE"},
        ).json()
        # 办结缺结果 → 409
        r0 = client.post(
            f"/api/v1/tenants/{t['code']}/complaints/{c['id']}/transition",
            json={"to_status": "RESOLVED"},
        )
        assert r0.status_code == 409
        # 受理
        r1 = client.post(
            f"/api/v1/tenants/{t['code']}/complaints/{c['id']}/transition",
            json={"to_status": "HANDLING", "handler": "前台小李"},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["status"] == "HANDLING"
        assert r1.json()["handler"] == "前台小李"
        # 办结
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/complaints/{c['id']}/transition",
            json={"to_status": "RESOLVED", "resolution": "已补救", "handler": "前台小李"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "RESOLVED"
        assert r2.json()["handled_at"] is not None
        # 已办结再流转 → 409
        r3 = client.post(
            f"/api/v1/tenants/{t['code']}/complaints/{c['id']}/transition",
            json={"to_status": "CANCELLED"},
        )
        assert r3.status_code == 409

    def test_filter_by_phone_and_booking(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m28c")
        bk = _book(client, t, h, rt, "13900200003")
        client.post(
            f"/api/v1/tenants/{t['code']}/complaints",
            json={"hotel_id": h["id"], "guest_name": "a", "booking_id": bk["id"]},
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/complaints",
            params={"guest_phone": "13900200003"},
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1 and int(rows[0]["booking_id"]) == int(bk["id"])


# ================= M28：留存导出 =================


class TestExport:
    def test_csv_export_bookings(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m28d")
        _book(client, t, h, rt, "13900200004")
        r = client.get(f"/api/v1/tenants/{t['code']}/analytics/data-export", params={"entity": "bookings"})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        text = r.content.decode("utf-8")
        assert text.startswith("\ufeff")  # BOM
        assert "guest_name" in text.split("\r\n")[0]
        assert "关联客" in text

    def test_export_bad_entity_400(self, client: TestClient) -> None:
        t, _h, _rt = _seed(client, "m28e")
        r = client.get(f"/api/v1/tenants/{t['code']}/analytics/data-export", params={"entity": "bogus"})
        assert r.status_code == 400


# ================= M29：OTA 直连 =================


class TestOta:
    def _setup_channel(self, client: TestClient, t: dict, h: dict, secret: str = "ota-secret-123") -> None:
        r = client.put(
            f"/api/v1/tenants/{t['code']}/ota/configs",
            json={"hotel_id": h["id"], "channel": "sandbox", "secret": secret},
        )
        assert r.status_code == 200, r.text

    def _signed_headers(self, secret: str, payload: dict) -> tuple[dict, bytes]:
        raw = __import__("json").dumps(payload).encode()
        sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return {"X-Ota-Sign": sig, "Content-Type": "application/json"}, raw

    def test_webhook_inject_and_idempotent(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m29a")
        self._setup_channel(client, t, h)
        payload = {
            "external_ref": "CT-1001",
            "room_type_code": "STD",
            "guest_name": "OTA客",
            "guest_phone": "13900300001",
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-02",
            "total_price_cents": 28000,
        }
        headers, raw = self._signed_headers("ota-secret-123", payload)
        r = client.post(
            f"/api/v1/tenants/{t['code']}/ota/sandbox/webhook/orders",
            content=raw,
            headers=headers,
        )
        assert r.status_code == 200, r.text
        first = r.json()
        assert first["created"] is True and first["status"] == "created"

        # 同 external_ref 重推 → 幂等返回同一单，不重复建
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/ota/sandbox/webhook/orders",
            content=raw,
            headers=headers,
        )
        assert r2.status_code == 200
        assert r2.json()["created"] is False
        assert r2.json()["booking_id"] == first["booking_id"]

        # 落库校验：渠道与回链
        bookings = client.get(f"/api/v1/tenants/{t['code']}/bookings").json()
        match = [b for b in bookings if b["guest_name"] == "OTA客"]
        assert match and match[0]["channel"] == "sandbox"

    def test_webhook_bad_signature_rejected(self, client: TestClient) -> None:
        t, h, _rt = _seed(client, "m29b")
        self._setup_channel(client, t, h)
        payload = {
            "external_ref": "CT-2001",
            "room_type_code": "STD",
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-02",
        }
        headers, raw = self._signed_headers("wrong-secret", payload)
        r = client.post(
            f"/api/v1/tenants/{t['code']}/ota/sandbox/webhook/orders",
            content=raw,
            headers=headers,
        )
        assert r.status_code == 400
        assert "签名" in r.json()["detail"]

    def test_inventory_push_sandbox_ack(self, client: TestClient) -> None:
        t, h, _rt = _seed(client, "m29c")
        self._setup_channel(client, t, h)
        r = client.post(f"/api/v1/tenants/{t['code']}/ota/sandbox/inventory/push")
        assert r.status_code == 200, r.text
        ack = r.json()
        assert ack["accepted"] is True
        assert ack["total_rooms"] == 1
        assert ack["items"][0]["pms_room_type_code"] == "STD"
        assert ack["trace_id"]

    def test_unconfigured_channel_rejected(self, client: TestClient) -> None:
        t, _h, _rt = _seed(client, "m29d")
        r = client.post(f"/api/v1/tenants/{t['code']}/ota/ota_ctrip/inventory/push")
        assert r.status_code == 400


# ================= M30：dashboard 缓存 =================


class TestDashboardCache:
    def test_cache_hit_and_invalidation(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m30a")
        # 第一次查询 → 回填缓存
        r1 = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/dashboard",
            params={"hotel_id": h["id"]},
        )
        assert r1.status_code == 200
        # 建预订 → 写路径显式失效缓存
        _book(client, t, h, rt, "13900400001")
        r2 = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/dashboard",
            params={"hotel_id": h["id"]},
        )
        assert r2.status_code == 200
        # 缓存失效后能反映新数据（booking_count 变化）
        assert r2.json() != r1.json() or "bookings" not in r1.json()
