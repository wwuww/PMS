"""Sprint 9 测试：店长 App（M10）——移动审批中心（M10-2，FR-APP-02）。

验证：折扣审批通过自动落账（余额冲减 + ref_id 回填）；驳回不执行；
重复决策 409；审批留痕（audit-logs 含 approval.decide）；状态过滤。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "app1", "name": "店长App测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "0501"}])
    bill = client.post(
        f"/api/v1/tenants/{t['code']}/bills",
        json={"hotel_id": h["id"], "guest_name": "住客", "room_no": "0501"},
    ).json()
    client.post(
        f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
        json={"charge_type": "ROOM_CHARGE", "amount": 60000},
    )
    return {"t": t, "h": h, "rt": rt, "bill": bill}


def _submit(client: TestClient, code: str, hotel_id: int, bill_id: int, amount: int) -> dict:
    return client.post(
        f"/api/v1/tenants/{code}/approvals",
        json={
            "hotel_id": hotel_id,
            "type": "DISCOUNT",
            "payload": {"bill_id": bill_id, "amount": amount, "description": "会员折扣"},
            "reason": "长住客优惠",
            "applicant": "front_desk",
        },
    ).json()


class TestApproval:
    def test_discount_approval_executes_charge(self, client: TestClient) -> None:
        d = _seed(client)
        code = d["t"]["code"]
        ticket = _submit(client, code, d["h"]["id"], d["bill"]["id"], -2000)
        assert ticket["status"] == "PENDING"
        decided = client.post(
            f"/api/v1/tenants/{code}/approvals/{ticket['id']}/decide",
            json={"decision": "APPROVE", "approver": "店长小李", "note": "同意"},
        ).json()
        assert decided["status"] == "APPROVED"
        assert decided["approver"] == "店长小李"
        assert decided["ref_id"] == d["bill"]["id"]  # 执行落点回填
        # 折扣自动落账：余额 60000 - 2000 = 58000
        bill = client.get(f"/api/v1/tenants/{code}/bills/{d['bill']['id']}").json()
        assert bill["balance"] == 58000
        # 审批留痕
        logs = client.get(f"/api/v1/tenants/{code}/audit-logs?action=approval.decide").json()
        assert any(l["actor"] == "店长小李" for l in logs)

    def test_reject_does_not_execute(self, client: TestClient) -> None:
        d = _seed(client)
        code = d["t"]["code"]
        ticket = _submit(client, code, d["h"]["id"], d["bill"]["id"], -2000)
        decided = client.post(
            f"/api/v1/tenants/{code}/approvals/{ticket['id']}/decide",
            json={"decision": "REJECT", "approver": "店长小李", "note": "折扣超限"},
        ).json()
        assert decided["status"] == "REJECTED"
        assert decided["ref_id"] is None
        bill = client.get(f"/api/v1/tenants/{code}/bills/{d['bill']['id']}").json()
        assert bill["balance"] == 60000  # 未执行
        # 已处理审批单重复决策 → 409
        again = client.post(
            f"/api/v1/tenants/{code}/approvals/{ticket['id']}/decide",
            json={"decision": "APPROVE", "approver": "店长小李"},
        )
        assert again.status_code == 409

    def test_list_filter_by_status(self, client: TestClient) -> None:
        d = _seed(client)
        code = d["t"]["code"]
        t1 = _submit(client, code, d["h"]["id"], d["bill"]["id"], -1000)
        _submit(client, code, d["h"]["id"], d["bill"]["id"], -2000)
        client.post(
            f"/api/v1/tenants/{code}/approvals/{t1['id']}/decide",
            json={"decision": "APPROVE", "approver": "店长小李"},
        )
        pending = client.get(f"/api/v1/tenants/{code}/approvals?status_=PENDING").json()
        approved = client.get(f"/api/v1/tenants/{code}/approvals?status_=APPROVED").json()
        assert len(pending) == 1
        assert len(approved) == 1
        assert approved[0]["applicant"] == "front_desk"

    def test_submit_pushes_approval_notification(self, client: TestClient) -> None:
        """② 提交审批单即向通知中心推送待办（点击深链直达审批单）。"""
        d = _seed(client)
        code = d["t"]["code"]
        ticket = _submit(client, code, d["h"]["id"], d["bill"]["id"], -2000)
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        appr = [n for n in notifs if n["ref_type"] == "approval"]
        assert len(appr) == 1
        n = appr[0]
        assert n["ref_id"] == str(ticket["id"])  # 雪花 id 响应为字符串
        assert n["link"] == f"/approvals?ticket={ticket['id']}"
        assert n["title"].startswith("待审批")
