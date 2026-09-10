# -*- coding: utf-8 -*-
"""解析维也纳 PMS 数据字典 HTM（动软生成器导出，GBK），输出结构化表清单。"""
import re
import json
import os
import html

OUT_DIR = r"F:\PMS\deliverables\pms-schema"
os.makedirs(OUT_DIR, exist_ok=True)

DOC = [
    ("PmsBase", r"G:\维也纳酒店\PMS数据文档\PmsBase_V2.007.htm"),
    ("PmsBusiness", r"G:\维也纳酒店\PMS数据文档\PmsBusiness_V1.21.htm"),
]

ROW_RE = re.compile(
    r"<tr>\s*<td>\s*(\d+)\s*</td>\s*<td>\s*([^<]+?)\s*</td>\s*<td>\s*([^<]*?)\s*</td>\s*<td>\s*([^<]*?)\s*</td>\s*<td>\s*([^<]*?)\s*</td>"
    r"\s*<td>\s*(.*?)\s*</td>\s*<td>\s*(.*?)\s*</td>\s*<td>\s*([^<]*?)\s*</td>\s*<td>\s*(.*?)\s*</td>\s*<td[^>]*>\s*(.*?)\s*</td>\s*</tr>",
    re.S,
)


def clean(s):
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"</br>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).replace("&nbsp;", "").strip()


def parse(db_name, path):
    raw = open(path, "rb").read()
    s = None
    for enc in ("gbk", "gb18030", "utf-8"):
        try:
            s = raw.decode(enc)
            break
        except Exception:
            continue
    if s is None:
        raise SystemExit("decode fail: " + path)

    # 以「表名：」切块（兼容 <div class="styletab">\n 表名：X</div> 带缩进的写法）
    parts = re.split(r'<div class="styletab">\s*表名：', s)
    tables = []
    for p in parts[1:]:
        name = p.split("</div>", 1)[0].strip()
        fields = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", p, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) < 10:
                continue
            seq = clean(tds[0])
            if not seq.isdigit():      # 跳过表头行
                continue
            col = clean(tds[1])
            if not col:
                continue
            fields.append({
                "col": col,
                "type": clean(tds[2]),
                "len": clean(tds[3]),
                "pk": "Y" if "是" in clean(tds[6]) else "",
                "null": clean(tds[7]),
                "desc": clean(tds[9]),
            })
        if fields:
            tables.append({"table": name, "n_fields": len(fields), "fields": fields})
    return {"db": db_name, "n_tables": len(tables), "tables": tables}


summary_lines = []
all_data = {}
for db, path in DOC:
    d = parse(db, path)
    all_data[db] = d
    json.dump(d, open(os.path.join(OUT_DIR, f"{db}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    summary_lines.append(f"# {db} —— {d['n_tables']} 张表\n")
    for t in d["tables"]:
        summary_lines.append(f"\n## {t['table']}（{t['n_fields']} 字段）\n")
        for f in t["fields"]:
            pk = " [PK]" if f["pk"] else ""
            desc = f" — {f['desc']}" if f["desc"] and f["desc"] != "&nbsp;" else ""
            summary_lines.append(f"- `{f['col']}` {f['type']}({f['len']}){pk}{desc}\n")
    print(db, "tables:", d["n_tables"], "fields:", sum(t["n_fields"] for t in d["tables"]))

open(os.path.join(OUT_DIR, "schema-summary.md"), "w", encoding="utf-8").writelines(summary_lines)
print("OUT:", OUT_DIR)
