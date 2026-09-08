"""Sprint 11：M11 AI 智能客服测试。"""

import pytest


@pytest.fixture
def tenant(client):
    return client.post("/api/v1/tenants", json={"code": "ai11", "name": "AI 测试租户"}).json()


class TestChatbot:
    def test_price_intent_auto_reply(self, client, tenant):
        sess = client.post(
            f"/api/v1/tenants/{tenant['code']}/ai/chat-sessions",
            json={"channel": "wechat_mp", "guest_name": "李先生"},
        ).json()
        r = client.post(
            f"/api/v1/tenants/{tenant['code']}/ai/chat-sessions/{sess['id']}/messages",
            json={"content": "今晚大床房多少钱？"},
        ).json()
        assert r["intent"] == "price"
        assert "房价" in r["bot_message"]["content"]
        assert r["handoff"] is False

    def test_human_handoff(self, client, tenant):
        sess = client.post(
            f"/api/v1/tenants/{tenant['code']}/ai/chat-sessions",
            json={"channel": "wechat_mp"},
        ).json()
        r = client.post(
            f"/api/v1/tenants/{tenant['code']}/ai/chat-sessions/{sess['id']}/messages",
            json={"content": "我要找人工客服"},
        ).json()
        assert r["intent"] == "human"
        assert r["handoff"] is True
        sess2 = client.get(f"/api/v1/tenants/{tenant['code']}/ai/chat-sessions/{sess['id']}").json()
        assert sess2["status"] == "handoff"

    def test_close_session_with_satisfaction(self, client, tenant):
        sess = client.post(
            f"/api/v1/tenants/{tenant['code']}/ai/chat-sessions",
            json={"channel": "web"},
        ).json()
        closed = client.post(
            f"/api/v1/tenants/{tenant['code']}/ai/chat-sessions/{sess['id']}/close",
            json={"satisfaction": 5},
        ).json()
        assert closed["status"] == "closed"
        assert closed["satisfaction"] == 5
