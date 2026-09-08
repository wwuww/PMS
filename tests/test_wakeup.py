"""Sprint 6 测试：叫醒服务（M3-7）。

验证：登记→PENDING；到点置 DONE；due_calls 按时刻过滤未完成任务。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "wu1", "name": "叫醒测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    return {"t": t, "h": h}


class TestWakeUpCall:
    def test_create_pending(self, client: TestClient) -> None:
        d = _seed(client)
        call = client.post(
            f"/api/v1/tenants/{d['t']['code']}/wake-up-calls",
            json={"hotel_id": d["h"]["id"], "room_no": "0202", "call_at": "2026-12-01T07:30"},
        ).json()
        assert call["status"] == "PENDING"
        assert call["room_no"] == "0202"

    def test_mark_done(self, client: TestClient) -> None:
        d = _seed(client)
        call = client.post(
            f"/api/v1/tenants/{d['t']['code']}/wake-up-calls",
            json={"hotel_id": d["h"]["id"], "room_no": "0203", "call_at": "2026-12-01T07:30"},
        ).json()
        done = client.post(
            f"/api/v1/tenants/{d['t']['code']}/wake-up-calls/{call['id']}/done"
        ).json()
        assert done["status"] == "DONE"

    def test_due_calls_filter(self, client: TestClient) -> None:
        d = _seed(client)
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/wake-up-calls",
            json={"hotel_id": d["h"]["id"], "room_no": "0204", "call_at": "2026-12-01T07:30"},
        )
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/wake-up-calls",
            json={"hotel_id": d["h"]["id"], "room_no": "0205", "call_at": "2026-12-01T08:30"},
        )
        due = client.get(
            f"/api/v1/tenants/{d['t']['code']}/wake-up-calls?hotel_id={d['h']['id']}&due_before=2026-12-01T08:00"
        ).json()
        assert len(due) == 1
        assert due[0]["room_no"] == "0204"
        # 全部待叫
        all_pending = client.get(
            f"/api/v1/tenants/{d['t']['code']}/wake-up-calls?hotel_id={d['h']['id']}&status_=PENDING"
        ).json()
        assert len(all_pending) == 2
