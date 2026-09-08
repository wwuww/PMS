"""④ 多接收人 / 角色订阅（M10-4 增强）。

覆盖：
1. 缺订阅配置时，push 按 DEFAULT_SUBSCRIBERS 解析接收角色（与历史单 recipient 语义对齐）；
2. 配置订阅后，同类通知按订阅列表派发（覆盖默认）；
3. 空订阅列表使该类通知 recipients=[]（不推送）；
4. 订阅配置 GET 返回覆盖全部 ref_type 的矩阵；
5. 订阅配置 PUT 批量 upsert 后 GET 回读一致。
"""

from fastapi.testclient import TestClient

from app.services.notification_service import DEFAULT_SUBSCRIBERS, REF_LABELS


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "sub1", "name": "订阅测试"}).json()
    h = client.post(
        f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "301"}])
    return {"t": t, "h": h, "rt": rt}


def _approval(client: TestClient, code: str, hotel_id: int) -> None:
    client.post(
        f"/api/v1/tenants/{code}/approvals",
        json={"hotel_id": hotel_id, "type": "OVERBOOK", "payload": {}, "reason": "x", "applicant": "fd"},
    )


class TestNotificationRecipients:
    def test_default_recipients_resolved(self, client: TestClient) -> None:
        """缺订阅配置：审批通知按 DEFAULT_SUBSCRIBERS['approval'] 派发给 store_manager。"""
        d = _seed(client)
        code = d["t"]["code"]
        _approval(client, code, d["h"]["id"])
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        approval = [n for n in notifs if n["ref_type"] == "approval"][0]
        assert approval["recipients"] == DEFAULT_SUBSCRIBERS["approval"]

    def test_subscription_overrides_default(self, client: TestClient) -> None:
        """配置订阅后，审批通知按订阅列表派发（覆盖默认单接收人）。"""
        d = _seed(client)
        code = d["t"]["code"]
        client.put(
            f"/api/v1/tenants/{code}/notification-subscriptions",
            json={"items": [{"ref_type": "approval", "recipients": ["front_desk", "store_manager"]}]},
        )
        _approval(client, code, d["h"]["id"])
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        approval = [n for n in notifs if n["ref_type"] == "approval"][0]
        assert approval["recipients"] == ["front_desk", "store_manager"]

    def test_empty_subscription_suppresses_notification(self, client: TestClient) -> None:
        """空订阅列表：该类通知 recipients=[]，④ 不推送、⑥ 列表对所有人不可见。

        列表按登录用户角色做 recipients 行级过滤（与 WS 实时路由同一套映射），
        空 recipients 与任何标签均无交集 → 通知中心列表不返回该审批通知。
        """
        d = _seed(client)
        code = d["t"]["code"]
        client.put(
            f"/api/v1/tenants/{code}/notification-subscriptions",
            json={"items": [{"ref_type": "approval", "recipients": []}]},
        )
        _approval(client, code, d["h"]["id"])
        # 订阅配置回落为空列表（验证 ④ 配置生效）
        sub = client.get(f"/api/v1/tenants/{code}/notification-subscriptions").json()
        assert [r["recipients"] for r in sub if r["ref_type"] == "approval"][0] == []
        # ⑥ 列表不可见：admin 的列表不含该审批通知（被抑制）
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        assert [n for n in notifs if n["ref_type"] == "approval"] == []

    def test_subscriptions_get_matrix(self, client: TestClient) -> None:
        """GET 返回覆盖全部 ref_type 的矩阵；未配置项回落到默认。"""
        d = _seed(client)
        code = d["t"]["code"]
        rows = client.get(f"/api/v1/tenants/{code}/notification-subscriptions").json()
        returned = {r["ref_type"]: r["recipients"] for r in rows}
        # 全部已知 ref_type 均有行
        for ref_type in REF_LABELS:
            assert ref_type in returned
            assert returned[ref_type] == DEFAULT_SUBSCRIBERS.get(ref_type, ["store_manager"])

    def test_subscriptions_put_then_get(self, client: TestClient) -> None:
        """批量 upsert 后 GET 回读与写入一致。"""
        d = _seed(client)
        code = d["t"]["code"]
        body = {"items": [
            {"ref_type": "approval", "recipients": ["store_manager"]},
            {"ref_type": "task", "recipients": ["front_desk"]},
        ]}
        r = client.put(f"/api/v1/tenants/{code}/notification-subscriptions", json=body).json()
        returned = {x["ref_type"]: x["recipients"] for x in r}
        assert returned["approval"] == ["store_manager"]
        assert returned["task"] == ["front_desk"]
        # 未配置项仍回落默认，不丢行
        assert "daily_report" in returned
