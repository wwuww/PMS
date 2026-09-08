"""Sprint 6 测试：PSB 上传队列（M3-5）。

验证：入住自动建上报任务(QUEUED, 证件号脱敏)；手动上报置 UPLOADED；散客可手动建任务。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "psb1", "name": "PSB测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "0301"}])
    return {"t": t, "h": h, "rt": rt}


class TestPsbUpload:
    def test_check_in_auto_creates_psb(self, client: TestClient) -> None:
        d = _seed(client)
        bk = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bookings",
            json={
                "hotel_id": d["h"]["id"],
                "room_type_id": d["rt"]["id"],
                "guest_name": "住客A",
                "guest_phone": "13700000001",
                "id_doc_no": "44030019900101001X",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-03",
                "room_no": "0301",
            },
        ).json()
        client.post(f"/api/v1/tenants/{d['t']['code']}/bookings/{bk['id']}/check-in", json={"room_no": "0301"})
        tasks = client.get(f"/api/v1/tenants/{d['t']['code']}/psb-tasks?hotel_id={d['h']['id']}").json()
        assert len(tasks) == 1
        assert tasks[0]["status"] == "QUEUED"
        assert tasks[0]["guest_name"] == "住客A"
        assert tasks[0]["booking_id"] == bk["id"]
        # 证件号脱敏：保留前4后2
        assert tasks[0]["id_doc_no_masked"] == "4403****1X"

    def test_upload_psb(self, client: TestClient) -> None:
        d = _seed(client)
        bk = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bookings",
            json={
                "hotel_id": d["h"]["id"],
                "room_type_id": d["rt"]["id"],
                "guest_name": "住客B",
                "id_doc_no": "44030019900202002Y",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-03",
                "room_no": "0301",
            },
        ).json()
        client.post(f"/api/v1/tenants/{d['t']['code']}/bookings/{bk['id']}/check-in", json={"room_no": "0301"})
        tasks = client.get(f"/api/v1/tenants/{d['t']['code']}/psb-tasks?hotel_id={d['h']['id']}").json()
        uploaded = client.post(
            f"/api/v1/tenants/{d['t']['code']}/psb-tasks/{tasks[0]['id']}/upload"
        ).json()
        assert uploaded["status"] == "UPLOADED"
        assert uploaded["uploaded_at"] is not None
        assert uploaded["id_doc_no_masked"] == "4403****2Y"

    def test_manual_enqueue_walk_in(self, client: TestClient) -> None:
        d = _seed(client)
        task = client.post(
            f"/api/v1/tenants/{d['t']['code']}/psb-tasks",
            json={
                "hotel_id": d["h"]["id"],
                "guest_name": "散客C",
                "id_doc_no": "44030019900303003Z",
                "room_no": "0301",
            },
        ).json()
        assert task["status"] == "QUEUED"
        assert task["booking_id"] is None
        assert task["id_doc_no_masked"] == "4403****3Z"
