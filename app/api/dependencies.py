"""公共依赖（Paged 列表分页 + MAX_LIST_ROWS 硬上限）。

M32：将审计 D1（51 个无 limit 端点）的护栏抽成公共依赖，便于逐个端点接入。
"""

from __future__ import annotations

from fastapi import Query

# M30 性能护栏：单次返回行数硬上限（防全表拉取拖垮实例）。
# 默认 None 仍兼容全量，但无论如何不会超过此值；显式 limit 还会被 le= 截断。
MAX_LIST_ROWS = 5000


def Paged(
    limit: int = Query(MAX_LIST_ROWS, le=MAX_LIST_ROWS, ge=1, description="返回行数上限"),
    offset: int = Query(0, ge=0, description="跳过的行数"),
) -> tuple[int, int]:
    """列表分页依赖：返回 (limit, offset)。

    用法：
        @router.get(...)
        async def list_x(
            ...,
            paging: tuple[int, int] = Depends(Paged),
            session: AsyncSession = Depends(get_session),
        ):
            limit, offset = paging
            stmt = select(...).limit(limit).offset(offset)
            ...

    说明：
        - 默认 limit = MAX_LIST_ROWS（5000），与既有默认拉取上限一致；
        - 显式传 ``?limit=N&offset=M`` 时，Pydantic ``Query(le=..., ge=...)``
          会拦截越界（> MAX_LIST_ROWS 或 < 1 返 422），无需手工 ``min/max``；
        - routes 层 inline 模式（不调 service）直接 ``stmt.limit(limit).offset(offset)``；
        - 调 service 模式：把 ``limit`` / ``offset`` 透传到 service 函数。
    """
    return (limit, offset)