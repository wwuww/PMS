"""⑥ 通知列表按 recipients 行级可见性过滤（M10-4 增强）。

覆盖：
1. 服务层 list_notifications / count_unread 按 recipient_tags 过滤：
   仅返回与本人标签交集的通知；空 recipients 对任何人不可见（与 WS 实时路由一致）。
2. 路由层接线：真实 STAFF 登录后仅见 front_desk 通知，store_manager 专属审批不可见；
   ADMIN 登录可见全部（FULL 标签集）。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_engine
from app.services.notification_service import NotificationService


def _run(coro):  # noqa: ANN001, ANN202
    return asyncio.run(coro)


def _push(tenant_id: str, hotel_id: int, items: list[dict]) -> None:
    factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

    async def _go() -> None:
        async with factory() as session:
            for it in items:
                await NotificationService(session).push(tenant_id=tenant_id, hotel_id=hotel_id, **it)
            await session.commit()

    _run(_go())


@pytest.fixture()
def tenant_id() -> str:
    return "vis_tenant"


@pytest.fixture()
def setup(client: TestClient, tenant_id: str) -> int:
    t = client.post("/api/v1/tenants", json={"code": tenant_id, "name": "可见性测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "测试店"}).json()
    return int(h["id"])


class TestListRecipientVisibility:
    def test_filter_by_tag(self, client: TestClient, tenant_id: str, setup: int) -> None:
        """store_manager 只见审批；front_desk 只见工单；并集见两者；空集见无。"""
        _push(
            tenant_id,
            setup,
            [
                {"title": "审批待办", "ref_type": "approval", "recipients": ["store_manager"]},
                {"title": "清扫工单", "ref_type": "task", "recipients": ["front_desk"]},
            ],
        )
        factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

        async def _go() -> tuple[int, int, int, int]:
            async with factory() as session:
                svc = NotificationService(session)
                sm = await svc.list_notifications(tenant_id, recipient_tags={"store_manager"})
                fd = await svc.list_notifications(tenant_id, recipient_tags={"front_desk"})
                both = await svc.list_notifications(
                    tenant_id, recipient_tags={"store_manager", "front_desk"}
                )
                none = await svc.list_notifications(tenant_id, recipient_tags=set())
                return len(sm), len(fd), len(both), len(none)

        sm, fd, both, none = _run(_go())
        assert sm == 1 and fd == 1 and both == 2 and none == 0

    def test_empty_recipients_invisible_to_all(self, client: TestClient, tenant_id: str, setup: int) -> None:
        """④ 空 recipients 的通知对任何人不可见（ADMIN 全量标签亦不例外）。"""
        _push(tenant_id, setup, [{"title": "抑制通知", "ref_type": "approval", "recipients": []}])
        factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

        async def _go() -> int:
            async with factory() as session:
                svc = NotificationService(session)
                return len(
                    await svc.list_notifications(
                        tenant_id, recipient_tags={"store_manager", "front_desk", "night_audit"}
                    )
                )

        assert _run(_go()) == 0

    def test_count_unread_filtered(self, client: TestClient, tenant_id: str, setup: int) -> None:
        """未读计数同样受本人标签约束。"""
        _push(
            tenant_id,
            setup,
            [
                {"title": "审批待办", "ref_type": "approval", "recipients": ["store_manager"]},
                {"title": "清扫工单", "ref_type": "task", "recipients": ["front_desk"]},
            ],
        )
        factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

        async def _go() -> tuple[int, int]:
            async with factory() as session:
                svc = NotificationService(session)
                sm = await svc.count_unread(tenant_id, recipient_tags={"store_manager"})
                fd = await svc.count_unread(tenant_id, recipient_tags={"front_desk"})
                return sm, fd

        sm, fd = _run(_go())
        assert sm == 1 and fd == 1


class TestNotificationVisibilityOverHttp:
    @pytest.mark.auth
    def test_staff_sees_only_front_desk_notifications(
        self, client: TestClient, tenant_id: str
    ) -> None:
        """路由层接线：STAFF 登录后仅见 front_desk 通知，store_manager 审批不可见。"""
        code = tenant_id
        # POST /tenants 公开，随带播种默认 admin + 三档角色
        t = client.post("/api/v1/tenants", json={"code": code, "name": "可见性测试"}).json()
        admin_login = client.post(
            f"/api/v1/tenants/{code}/auth/login",
            json={"username": "admin", "password": "admin123"},
        ).json()
        admin_token = admin_login["token"]
        ah = {"Authorization": f"Bearer {admin_token}"}
        # 门店创建需鉴权（本用例退出 auth_bypass）
        h = client.post(
            f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "店"}, headers=ah
        ).json()
        hotel_id = int(h["id"])

        # 建 STAFF 用户并绑定 STAFF 角色
        user = client.post(
            f"/api/v1/tenants/{code}/users",
            json={"username": "fd1", "password": "fd12345", "display_name": "前台1"},
            headers=ah,
        )
        assert user.status_code == 201, user.text
        user_id = user.json()["id"]
        roles = client.get(f"/api/v1/tenants/{code}/roles", headers=ah).json()
        staff_role = next(r for r in roles if r["level"] == "STAFF")
        bind = client.post(
            f"/api/v1/tenants/{code}/users/{user_id}/roles",
            json={"role_id": staff_role["id"], "hotel_id": hotel_id},
            headers=ah,
        )
        assert bind.status_code == 201, bind.text

        # 触发 store_manager 专属（审批）与 front_desk（清扫工单）通知
        client.post(
            f"/api/v1/tenants/{code}/approvals",
            json={"hotel_id": hotel_id, "type": "OVERBOOK", "payload": {}, "reason": "x", "applicant": "fd"},
            headers=ah,
        )
        client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks",
            json={"hotel_id": hotel_id, "room_no": "101", "task_type": "CLEANUP"},
            headers=ah,
        )

        # STAFF 登录并拉取列表
        staff_login = client.post(
            f"/api/v1/tenants/{code}/auth/login",
            json={"username": "fd1", "password": "fd12345"},
        ).json()
        sh = {"Authorization": f"Bearer {staff_login['token']}"}
        notifs = client.get(f"/api/v1/tenants/{code}/notifications", headers=sh).json()
        ref_types = {n["ref_type"] for n in notifs}
        # ⑥ 行级可见性：STAFF 仅收 front_desk 类（工单），看不到 store_manager 专属审批
        assert "task" in ref_types
        assert "approval" not in ref_types

    @pytest.mark.auth
    def test_admin_sees_all_notifications(
        self, client: TestClient, tenant_id: str
    ) -> None:
        """路由层接线：ADMIN（FULL 标签）可见全部通知。"""
        code = tenant_id
        t = client.post("/api/v1/tenants", json={"code": code, "name": "可见性测试"}).json()
        admin_login = client.post(
            f"/api/v1/tenants/{code}/auth/login",
            json={"username": "admin", "password": "admin123"},
        ).json()
        ah = {"Authorization": f"Bearer {admin_login['token']}"}
        h = client.post(
            f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "店"}, headers=ah
        ).json()
        hotel_id = int(h["id"])
        client.post(
            f"/api/v1/tenants/{code}/approvals",
            json={"hotel_id": hotel_id, "type": "OVERBOOK", "payload": {}, "reason": "x", "applicant": "fd"},
            headers=ah,
        )
        client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks",
            json={"hotel_id": hotel_id, "room_no": "101", "task_type": "CLEANUP"},
            headers=ah,
        )
        notifs = client.get(f"/api/v1/tenants/{code}/notifications", headers=ah).json()
        ref_types = {n["ref_type"] for n in notifs}
        assert "approval" in ref_types
        assert "task" in ref_types


class TestNotificationReadGating:
    def test_mark_all_read_filtered_by_tag(self, client: TestClient, tenant_id: str, setup: int) -> None:
        """⑥ 收尾：全部已读仅清除本人可见的未读项，不越权清除他人专属通知。"""
        _push(
            tenant_id,
            setup,
            [
                {"title": "审批待办", "ref_type": "approval", "recipients": ["store_manager"]},
                {"title": "清扫工单", "ref_type": "task", "recipients": ["front_desk"]},
            ],
        )
        factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

        async def _go() -> tuple[int, int]:
            async with factory() as session:
                svc = NotificationService(session)
                await svc.mark_all_read(tenant_id, recipient_tags={"store_manager"})
                sm_items = await svc.list_notifications(tenant_id, recipient_tags={"store_manager"})
                fd_items = await svc.list_notifications(tenant_id, recipient_tags={"front_desk"})
                sm_unread = sum(1 for n in sm_items if n.read_at is None)
                fd_unread = sum(1 for n in fd_items if n.read_at is None)
                return sm_unread, fd_unread

        sm_unread, fd_unread = _run(_go())
        assert sm_unread == 0  # store_manager 通知已被标记已读
        assert fd_unread == 1  # front_desk 通知仍未被清除

    @pytest.mark.auth
    def test_staff_cannot_read_or_clear_store_manager_notification(
        self, client: TestClient, tenant_id: str
    ) -> None:
        """⑥ 收尾：STAFF 不能读取/全部已读越权清除店长专属通知。"""
        code = tenant_id
        t = client.post("/api/v1/tenants", json={"code": code, "name": "可见性测试"}).json()
        admin_login = client.post(
            f"/api/v1/tenants/{code}/auth/login",
            json={"username": "admin", "password": "admin123"},
        ).json()
        admin_token = admin_login["token"]
        ah = {"Authorization": f"Bearer {admin_token}"}
        h = client.post(
            f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "店"}, headers=ah
        ).json()
        hotel_id = int(h["id"])

        user = client.post(
            f"/api/v1/tenants/{code}/users",
            json={"username": "fd1", "password": "fd12345", "display_name": "前台1"},
            headers=ah,
        )
        assert user.status_code == 201, user.text
        user_id = user.json()["id"]
        roles = client.get(f"/api/v1/tenants/{code}/roles", headers=ah).json()
        staff_role = next(r for r in roles if r["level"] == "STAFF")
        bind = client.post(
            f"/api/v1/tenants/{code}/users/{user_id}/roles",
            json={"role_id": staff_role["id"], "hotel_id": hotel_id},
            headers=ah,
        )
        assert bind.status_code == 201, bind.text

        # 触发 store_manager 专属审批通知（admin 视角）
        client.post(
            f"/api/v1/tenants/{code}/approvals",
            json={"hotel_id": hotel_id, "type": "OVERBOOK", "payload": {}, "reason": "x", "applicant": "fd"},
            headers=ah,
        )
        admin_notifs = client.get(f"/api/v1/tenants/{code}/notifications", headers=ah).json()
        approval_id = next(n["id"] for n in admin_notifs if n["ref_type"] == "approval")

        staff_login = client.post(
            f"/api/v1/tenants/{code}/auth/login",
            json={"username": "fd1", "password": "fd12345"},
        ).json()
        sh = {"Authorization": f"Bearer {staff_login['token']}"}

        # STAFF 按 id 读取店长专属通知 → 404（不可见）
        r = client.post(f"/api/v1/tenants/{code}/notifications/{approval_id}/read", headers=sh)
        assert r.status_code == 404, r.text

        # STAFF 全部已读后，该店长专属通知仍未被越权清除（admin 视角仍可见且未读）
        client.post(f"/api/v1/tenants/{code}/notifications/read-all", headers=sh)
        admin_notifs2 = client.get(f"/api/v1/tenants/{code}/notifications", headers=ah).json()
        approval2 = next(n for n in admin_notifs2 if n["ref_type"] == "approval")
        assert approval2["read_at"] is None


class TestNotificationListFiltering:
    def test_ref_type_level_and_pagination(self, client: TestClient, tenant_id: str, setup: int) -> None:
        """⑥ UX：list_notifications 支持 ref_type/level 筛选与 limit/offset 分页。"""
        _push(
            tenant_id,
            setup,
            [
                {"title": "审批A", "ref_type": "approval", "recipients": ["store_manager"], "level": "normal"},
                {"title": "审批B", "ref_type": "approval", "recipients": ["store_manager"], "level": "critical"},
                {"title": "工单A", "ref_type": "task", "recipients": ["front_desk"], "level": "normal"},
            ],
        )
        factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

        async def _go() -> dict:
            async with factory() as session:
                svc = NotificationService(session)
                # ref_type 筛选
                approvals = await svc.list_notifications(tenant_id, ref_type="approval")
                # level 筛选
                criticals = await svc.list_notifications(tenant_id, level="critical")
                # 分页：首页取 2 条（id desc，最新在前）
                page1 = await svc.list_notifications(tenant_id, limit=2, offset=0)
                # 第二页取剩余
                page2 = await svc.list_notifications(tenant_id, limit=2, offset=2)
                # 组合：ref_type + 分页
                combo = await svc.list_notifications(tenant_id, ref_type="approval", limit=1, offset=0)
                return {
                    "approvals": len(approvals),
                    "criticals": len(criticals),
                    "page1": len(page1),
                    "page2": len(page2),
                    "combo": len(combo),
                    "total": len(await svc.list_notifications(tenant_id)),
                }

        r = _run(_go())
        assert r["approvals"] == 2
        assert r["criticals"] == 1
        assert r["page1"] == 2 and r["page2"] == 1  # 共 3 条，分页切分
        assert r["combo"] == 1  # ref_type=approval 共 2，limit=1 → 1
        assert r["total"] == 3

    def test_hotel_id_filtering(self, client: TestClient, tenant_id: str) -> None:
        """UX 增强：list_notifications / count_unread 按 hotel_id 过滤（门店维度）。"""
        code = tenant_id
        t = client.post("/api/v1/tenants", json={"code": code, "name": "门店筛选测试"}).json()
        h1 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "店1"}).json()
        h2 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H2", "name": "店2"}).json()
        hotel1, hotel2 = int(h1["id"]), int(h2["id"])
        _push(
            code,
            hotel1,
            [
                {"title": "店1审批", "ref_type": "approval", "recipients": ["store_manager"]},
                {"title": "店1工单", "ref_type": "task", "recipients": ["front_desk"]},
            ],
        )
        _push(code, hotel2, [{"title": "店2审批", "ref_type": "approval", "recipients": ["store_manager"]}])
        factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)

        async def _go() -> tuple[int, int, int, int, int]:
            async with factory() as session:
                svc = NotificationService(session)
                h1_items = await svc.list_notifications(code, hotel_id=hotel1)
                h2_items = await svc.list_notifications(code, hotel_id=hotel2)
                all_items = await svc.list_notifications(code)
                u1 = await svc.count_unread(code, hotel_id=hotel1)
                u2 = await svc.count_unread(code, hotel_id=hotel2)
                return len(h1_items), len(h2_items), len(all_items), u1, u2

        n1, n2, nall, u1, u2 = _run(_go())
        assert n1 == 2  # 店1 共 2 条
        assert n2 == 1  # 店2 共 1 条
        assert nall == 3  # 不过滤返回全部
        assert u1 == 2 and u2 == 1  # 门店维度未读计数独立
