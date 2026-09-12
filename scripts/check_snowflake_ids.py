#!/usr/bin/env python
"""哨兵：禁止把 ID 交给 ``Number()`` 加工（雪花 ID 会被截断）。

背景
----
所有 ``IntPkMixin`` 主键（Booking / Bill / Deposit / Hotel / RoomType …）都是 18 位
雪花 ID，后端 JSON 里以**字符串**下发（见 ``app/core/snowflake.py`` 模块注释）。

JS 的 ``Number()`` 会把它们变成 double；**真正的杀伤不在精度，而在转回字符串时**
按「最短往返」只打印 17 位有效数字：

    String(Number("354986244532338688"))  // -> "354986244532338700"

把它拼进 URL 或 JSON 后，后端拿到的是一个**不存在的 ID**，而多数列表/详情接口
对不存在的 ID **只静默返回空列表**，不报错、不 422 ——表现为「点了没反应」。

2026-09-12 就栽在这上面：入住登记页的押金快捷面板永远空白，查了很久才发现
``listDepositsByBooking(tenantCode, Number(bookingId))`` 把订单号打错了。

用法
----
    python scripts/check_snowflake_ids.py          # 检查 web/src
    python scripts/check_snowflake_ids.py <dir>    # 指定目录

退出码：0 = 无违规；1 = 发现违规（CI 应判失败）。

确需把 ID 当数字用时（几乎不会有），在该行末尾加 ``// id-ok: <理由>`` 放行。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Number(...) 调用（忽略 Math.xxx / Number.MAX_SAFE_INTEGER 之类的引用）
_NUMBER_CALL = re.compile(r"\bNumber\s*\(")

# 参数里含这些 ID 名称就判违规：x.id / hotelId / v.booking_id / bill_id ...
_ID_ARG = re.compile(
    r"^(?:.*[.\s(])?"
    r"(id|hotel_id|booking_id|bill_id|room_type_id|pms_room_type_id|guest_id|"
    r"member_id|payment_id|deposit_id|invoice_id|coupon_id|planId|mappingId|"
    r"hotelId|bookingId|billId|roomTypeId)"
    r"\s*$"
)

_ALLOW = re.compile(r"//\s*id-ok")

_SCAN_SUFFIX = (".ts", ".tsx")


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """返回 [(行号, 违规代码片段)]。"""
    hits: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8", errors="replace")

    for lineno, line in enumerate(text.splitlines(), start=1):
        if "Number(" not in line:
            continue
        for m in _NUMBER_CALL.finditer(line):
            # 取 Number( 之后到匹配右括号之间的内容
            start = m.end()
            depth = 1
            idx = start
            while idx < len(line) and depth:
                if line[idx] == "(":
                    depth += 1
                elif line[idx] == ")":
                    depth -= 1
                idx += 1
            if depth:  # 跨行调用，本哨兵不处理（罕见）
                continue
            arg = line[start : idx - 1].strip()
            if _ID_ARG.match(arg) and not _ALLOW.search(line):
                snippet = line.strip()
                hits.append((lineno, snippet[:120]))
                break
    return hits


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "web" / "src"
    if not root.exists():
        print(f"[check-snowflake-ids] 目录不存在：{root}")
        return 1

    files = [p for p in root.rglob("*") if p.suffix in _SCAN_SUFFIX and p.is_file()]
    total = 0
    for f in sorted(files):
        for lineno, snippet in _scan_file(f):
            total += 1
            rel = f.relative_to(root)
            print(f"[check-snowflake-ids] {rel}:{lineno}: {snippet}")

    if total:
        print(
            f"\n[check-snowflake-ids] 发现 {total} 处把 ID 交给 Number() 加工。"
            "\n雪花 ID 是 18 位，String(Number(id)) 只会保留 17 位有效数字，"
            "\n后端拿到不存在的 ID 且通常静默返回空列表。请直接传字符串（后端 pydantic 会正确解析）。"
        )
        return 1

    print(f"[check-snowflake-ids] OK：{len(files)} 个文件，未发现 ID 被 Number() 加工。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
