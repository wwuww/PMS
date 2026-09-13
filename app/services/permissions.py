"""权限码常量与默认三档角色定义（M8-1）。

权限码命名规范：{domain}.{action}
审计埋点 SDK（M8-2）与鉴权接口（M8-3）共用此清单。
"""

from __future__ import annotations

# ---------- 权限码 ----------
PRICE_EDIT = "price.edit"            # 改价
BOOKING_CANCEL = "booking.cancel"     # 取消/删单
BILL_REFUND = "billing.refund"        # 退款
BILL_ADJUST = "billing.adjust"        # 冲账/调账
BILL_DISCOUNT = "billing.discount"    # 折扣
NIGHT_AUDIT_RUN = "night_audit.run"   # 执行夜审
AUDIT_VIEW = "audit.view"             # 查看/导出审计
USER_MANAGE = "user.manage"           # 账号管理
ROLE_MANAGE = "role.manage"           # 角色管理
FNB_MANAGE = "fnb.manage"             # 餐饮 POS：开单/点菜/结账
# M32.18 押金与预授权（M0-3 后续）
DEPOSIT_MANAGE = "deposit.manage"     # 收押/补交/冲抵/作废/查/明细
DEPOSIT_REFUND = "deposit.refund"     # 退押（原路退/手动退）
# 注：没收（FORFEITED）由 ``deposit.manage`` + ``billing.adjust`` 组合守卫，
# 任何拥有 BILL_ADJUST 的角色才有没收权限（默认仅管理员/门店经理）。
# M29 OTA 直连
OTA_MANAGE = "ota.manage"             # 渠道配置 / 房型映射 / 推送
RATE_EDIT = "rate.edit"               # 渠道价 / 公共价编辑
# M37-③ 发票
INVOICE_MANAGE = "invoice.manage"     # 开票 / 作废 / 查 / 按账单查
# M37-④ 早餐券 + 优惠券 + 房间属性 + 黑名单
BLACKLIST_MANAGE = "blacklist.manage"  # 黑名单 增/删/查（敏感：仅管理员 + 门店经理）
COUPON_MANAGE = "coupon.manage"        # 券模板 / 发券 / 核销 / 作废（前台可用）
BREAKFAST_MANAGE = "breakfast.manage"  # 早餐券 发/核销/作废/查（前台可用）
# M1-A3 权限清偿：基础业务操作码（与 BILL_ADJUST/REFUND/DISCOUNT 的"敏感账务"正交）
BILLING_MANAGE = "billing.manage"      # 建单/挂账/收款/结账/预付冲抵/积分支付（前台必能收款）
AR_MANAGE = "ar.manage"                # 应收账户 建/挂账/回款（仅管理员 + 门店经理）
MEMBER_MANAGE = "member.manage"        # 会员 建档/充值（充值=现金入金，双码 AND billing.manage）
SHIFT_MANAGE = "shift.manage"          # 开班/交班（仅管理员 + 门店经理）

ALL_PERMISSIONS = {
    PRICE_EDIT,
    BOOKING_CANCEL,
    BILL_REFUND,
    BILL_ADJUST,
    BILL_DISCOUNT,
    NIGHT_AUDIT_RUN,
    AUDIT_VIEW,
    USER_MANAGE,
    ROLE_MANAGE,
    FNB_MANAGE,
    DEPOSIT_MANAGE,
    DEPOSIT_REFUND,
    OTA_MANAGE,
    RATE_EDIT,
    INVOICE_MANAGE,
    BLACKLIST_MANAGE,
    COUPON_MANAGE,
    BREAKFAST_MANAGE,
    BILLING_MANAGE,
    AR_MANAGE,
    MEMBER_MANAGE,
    SHIFT_MANAGE,
}


# ---------- 默认三档角色 ----------
# （name, level, hotel_scoped, permissions）
DEFAULT_ROLES: list[tuple[str, str, bool, list[str]]] = [
    (
        "管理员",
        "ADMIN",
        False,
        list(ALL_PERMISSIONS),
    ),
    (
        "门店经理",
        "MANAGER",
        True,  # 经理权限按门店生效
        [
            PRICE_EDIT,
            BOOKING_CANCEL,
            BILL_REFUND,
            BILL_ADJUST,
            BILL_DISCOUNT,
            NIGHT_AUDIT_RUN,
            AUDIT_VIEW,
            FNB_MANAGE,
            DEPOSIT_MANAGE,
            DEPOSIT_REFUND,
            OTA_MANAGE,
            RATE_EDIT,
            INVOICE_MANAGE,
            BLACKLIST_MANAGE,
            COUPON_MANAGE,
            BREAKFAST_MANAGE,
            BILLING_MANAGE,
            AR_MANAGE,
            MEMBER_MANAGE,
            SHIFT_MANAGE,
        ],
    ),
    (
        "前台",
        "STAFF",
        True,
        [
            BOOKING_CANCEL,
            BILL_REFUND,
            BILL_DISCOUNT,
            FNB_MANAGE,
            DEPOSIT_MANAGE,
            DEPOSIT_REFUND,
            INVOICE_MANAGE,
            # 黑名单属敏感数据：前台无 blacklist.manage；券与早餐券前台可用
            COUPON_MANAGE,
            BREAKFAST_MANAGE,
            # M1-A3：收银基础操作（建单/挂账/收款/结账）前台必做，故授予 billing.manage；
            # 但不含 ar.manage（应收）、member.manage（会员充值）、shift.manage（交班）
            BILLING_MANAGE,
        ],
    ),
]
