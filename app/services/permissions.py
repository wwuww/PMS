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
        ],
    ),
]
