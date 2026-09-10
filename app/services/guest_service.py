"""宾客档案 / 客史服务（M14，FR-GUEST）。

覆盖所有到店客人（散客 + 会员）的统一档案：建档、查询、搜索、编辑，
以及入住时自动累计客史（stay_count / total_spend）。会员可通过 member_id
关联，但建档不强制会员身份。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BlackGuest, Booking, Guest, Member
from app.services.member_service import MemberService


class GuestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _link_member_by_phone(self, guest: Guest, phone: str | None) -> None:
        """按手机号自动关联会员（客档联动会员，FR-GUEST-LINK）：

        建档/入住时若手机号匹配既有会员且 guest 尚未关联，则写入 member_id。
        会员主数据按 tenant 共享，故跨店到店也能识别会员身份。
        """
        if not phone or guest.member_id:
            return
        member = await MemberService(self.session).get_by_phone(guest.tenant_id, phone)
        if member:
            guest.member_id = member.id
            self.session.add(guest)

    async def create(
        self,
        tenant_id: str,
        hotel_id: int,
        name: str,
        phone: str | None = None,
        *,
        id_type: str | None = None,
        id_no: str | None = None,
        vip_level: str = "NORMAL",
        birthday: str | None = None,
        gender: str | None = None,
        email: str | None = None,
        address: str | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
        member_id: int | None = None,
        # 批次② 字段补全
        en_name: str | None = None,
        native_place: str | None = None,
        nation: str | None = None,
        is_valid: bool = True,
        come_time: str | None = None,
        head_url: str | None = None,
        id_doc_sign_org: str | None = None,
        id_doc_valid_to: str | None = None,
    ) -> Guest:
        existing = None
        if phone:
            existing = await self.get_by_phone(tenant_id, phone)
        if existing:
            await self._link_member_by_phone(existing, phone)
            await self.session.flush()
            return existing  # 同租户同手机号视为同一客人，不重复建档
        try:
            bday = date.fromisoformat(birthday) if birthday else None
        except ValueError:
            bday = None
        guest = Guest(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            name=name,
            phone=phone,
            id_type=id_type or "ID",
            id_no=id_no,
            vip_level=vip_level,
            birthday=bday,
            gender=gender,
            email=email,
            address=address,
            notes=notes,
            member_id=member_id,
            # 批次② 字段补全
            en_name=en_name,
            native_place=native_place,
            nation=nation,
            is_valid=is_valid,
            come_time=come_time,
            head_url=head_url,
            id_doc_sign_org=id_doc_sign_org,
            id_doc_valid_to=id_doc_valid_to,
        )
        if tags:
            guest.set_tags(tags)
        self.session.add(guest)
        await self._link_member_by_phone(guest, phone)
        await self.session.flush()
        return guest

    async def get(self, tenant_id: str, guest_id: int) -> Guest | None:
        r = await self.session.execute(
            select(Guest).where(Guest.tenant_id == tenant_id, Guest.id == guest_id)
        )
        return r.scalar_one_or_none()

    async def get_by_phone(self, tenant_id: str, phone: str) -> Guest | None:
        if not phone:
            return None
        r = await self.session.execute(
            select(Guest).where(Guest.tenant_id == tenant_id, Guest.phone == phone)
        )
        return r.scalar_one_or_none()

    async def list(
        self,
        tenant_id: str,
        hotel_id: int | None = None,
        keyword: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Guest]:
        stmt = select(Guest).where(Guest.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(Guest.hotel_id == hotel_id)
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                (Guest.name.like(like)) | (Guest.phone.like(like)) | (Guest.id_no.like(like))
            )
        stmt = stmt.order_by(Guest.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)
        r = await self.session.execute(stmt)
        return list(r.scalars())

    async def search(
        self,
        tenant_id: str,
        phone: str | None = None,
        name: str | None = None,
        id_no: str | None = None,
        booking_id: int | None = None,
    ) -> list[Guest]:
        """多维度快速检索（M23 验收清单#4）：姓名 / 手机号 / 证件号 / 订单号。

        - 姓名、手机号、证件号：客档字段直接匹配（可组合，AND）。
        - 订单号（booking_id）：先取预订，再按预订上的 guest_phone / id_doc_no
          反查客档——Booking 未建 guest 外键，故以电话+证件号双通道关联。
        - 模糊检索请用 `list(keyword=...)`（已支持 name/phone/id_no 的 LIKE）。
        """
        if booking_id is not None:
            bk = await self.session.get(Booking, booking_id)
            if bk is None or bk.tenant_id != tenant_id:
                return []
            conds = []
            if bk.guest_phone:
                conds.append(Guest.phone == bk.guest_phone)
            if bk.id_doc_no:
                conds.append(Guest.id_no == bk.id_doc_no)
            if not conds:
                return []
            r = await self.session.execute(
                select(Guest).where(Guest.tenant_id == tenant_id, or_(*conds))
            )
            return list(r.scalars())

        stmt = select(Guest).where(Guest.tenant_id == tenant_id)
        if phone:
            stmt = stmt.where(Guest.phone == phone)
        if name:
            stmt = stmt.where(Guest.name == name)
        if id_no:
            stmt = stmt.where(Guest.id_no == id_no)
        r = await self.session.execute(stmt)
        return list(r.scalars())

    async def update(self, guest: Guest, **fields) -> Guest:
        allowed = {
            "name",
            "phone",
            "id_type",
            "id_no",
            "vip_level",
            "gender",
            "email",
            "address",
            "notes",
            "member_id",
            "tags",
        }
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "tags":
                guest.set_tags(value if isinstance(value, list) else [])
            else:
                setattr(guest, key, value)
        self.session.add(guest)
        await self.session.flush()
        return guest

    async def record_stay(
        self,
        tenant_id: str,
        hotel_id: int,
        name: str,
        phone: str | None,
        *,
        amount_cents: int = 0,
        member_id: int | None = None,
    ) -> Guest:
        """入住钩子：按手机号 upsert 宾客档案并累计客史。

        - 已建档（同租户同手机号）→ stay_count+1、total_spend 累加；
        - 未建档（或散客无手机号）→ 自动建档（散客 stay_count 从 0 起）。
        返回最终 Guest。
        """
        guest = None
        if phone:
            guest = await self.get_by_phone(tenant_id, phone)
        if guest is None:
            # 新建散客/会员档案：Python 属性未加载列默认值，须显式初始化
            guest = Guest(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                name=name,
                phone=phone,
                id_type="ID",
                member_id=member_id,
                stay_count=1,
                total_spend=max(0, amount_cents),
            )
            self.session.add(guest)
        else:
            guest.stay_count += 1
            guest.total_spend += max(0, amount_cents)
            if member_id and not guest.member_id:
                guest.member_id = member_id
            self.session.add(guest)
        # 入住即按手机号自动关联会员（客档联动会员）
        await self._link_member_by_phone(guest, phone)
        await self.session.flush()
        return guest

    # ---------- 黑名单（M37-④，D1：仅提醒不硬阻断） ----------

    async def add_blacklist(
        self,
        tenant_id: str,
        name: str,
        reason: str,
        hotel_id: int | None = None,
        id_no: str | None = None,
        phone: str | None = None,
        level: int = 0,
        operator: str = "front_desk",
    ) -> BlackGuest:
        """加入黑名单（``hotel_id`` 为空表示全集团生效）。"""
        if not (name or "").strip():
            raise ValueError("黑名单姓名必填")
        if not (reason or "").strip():
            raise ValueError("拉黑原因必填")
        if level < 0 or level > 3:
            raise ValueError("黑名单等级须为 0-3")
        row = BlackGuest(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            name=name.strip(),
            id_no=(id_no or None),
            phone=(phone or None),
            reason=reason.strip(),
            level=level,
            is_valid=True,
            operator=operator,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def remove_blacklist(
        self, tenant_id: str, black_id: int, operator: str = "front_desk"
    ) -> BlackGuest:
        """移出黑名单（WORM 软删：仅置 ``is_valid=False``）。"""
        row = await self.session.get(BlackGuest, black_id)
        if row is None or row.tenant_id != tenant_id:
            raise ValueError("黑名单记录不存在")
        row.is_valid = False
        row.operator = operator
        self.session.add(row)
        await self.session.flush()
        return row

    async def check_blacklist(
        self,
        tenant_id: str,
        name: str | None = None,
        id_no: str | None = None,
        phone: str | None = None,
        hotel_id: int | None = None,
    ) -> list[dict]:
        """黑名单命中检查（**仅提醒**，调用方决定是否阻断）。

        匹配优先级：``id_no`` > ``phone`` > ``name``；``id_no``/``phone`` 命中为
        **强命中**（``strong=True``），姓名误伤率高仅作弱提示。
        生效范围：``hotel_id`` 为空（全集团）或等于当前门店。
        返回 ``BlacklistHit`` 结构字典列表（按 id 去重、level 倒序）。
        """
        if not (name or id_no or phone):
            return []
        found: dict[int, dict] = {}

        async def _query(key: str, value: str) -> None:
            stmt = select(BlackGuest).where(
                BlackGuest.tenant_id == tenant_id,
                BlackGuest.is_valid.is_(True),
                getattr(BlackGuest, key) == value,
            )
            if hotel_id is not None:
                stmt = stmt.where(
                    or_(BlackGuest.hotel_id.is_(None), BlackGuest.hotel_id == hotel_id)
                )
            rows = (await self.session.execute(stmt)).scalars().all()
            for row in rows:
                if row.id in found:
                    continue  # 已在更高优先级命中
                found[row.id] = {
                    "id": row.id,
                    "name": row.name,
                    "reason": row.reason,
                    "level": row.level,
                    "matched_by": key,
                    "strong": key in ("id_no", "phone"),
                }

        # 强键优先：证件号 > 手机号 > 姓名
        if id_no:
            await _query("id_no", id_no)
        if phone:
            await _query("phone", phone)
        if name:
            await _query("name", name)
        return sorted(found.values(), key=lambda x: (-int(x["level"]), int(x["id"])))

    async def list_blacklist(
        self,
        tenant_id: str,
        name: str | None = None,
        id_no: str | None = None,
        level: int | None = None,
        is_valid: bool | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[BlackGuest]:
        """黑名单列表（按 id 倒序，带 MAX_LIST_ROWS 硬上限护栏）。"""
        from app.api.routes import MAX_LIST_ROWS  # noqa: PLC0415 - 延迟导入避免循环依赖

        stmt = select(BlackGuest).where(BlackGuest.tenant_id == tenant_id)
        if name:
            stmt = stmt.where(BlackGuest.name.like(f"%{name}%"))
        if id_no:
            stmt = stmt.where(BlackGuest.id_no == id_no)
        if level is not None:
            stmt = stmt.where(BlackGuest.level == level)
        if is_valid is not None:
            stmt = stmt.where(BlackGuest.is_valid == is_valid)
        stmt = stmt.order_by(BlackGuest.id.desc())
        stmt = stmt.offset(max(0, offset)).limit(
            MAX_LIST_ROWS if limit is None else max(1, min(limit, MAX_LIST_ROWS))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())
