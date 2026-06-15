#!/usr/bin/env python3
"""从 knowledge.json 生成可交互思维导图 HTML（零依赖，离线可开）。

用法：
  python3 build_mindmap.py <study目录>/knowledge.json                 # 所有章各生成一个
  python3 build_mindmap.py knowledge.json --chapter 3                # 只生成第 3 章
  python3 build_mindmap.py knowledge.json --book                     # 整本书总览图
  python3 build_mindmap.py knowledge.json -o <输出目录>               # 默认输出到 knowledge.json 同级 mindmaps/

输出文件：mindmaps/chapter-03.html / mindmaps/book.html
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

TEMPLATE = pathlib.Path(__file__).resolve().parent.parent / "assets" / "template.html"

# 节点上只显示知识点短名；完整描述在悬停提示里。优先用 knowledge.json 的 short 字段，
# 否则从 name 自动精简：取第一个分隔符之前的核心词，并限制长度（兜底处理过长/带描述的旧 name）。
_SEP_RE = re.compile(r"[：:；;，,。（(、]")


def short_label(name, max_len=16):
    name = (name or "").strip()
    m = _SEP_RE.search(name)
    label = (name[:m.start()] if m else name).strip()
    if not label or len(label) > max_len:
        label = name[:max_len]
    return label


def point_node(p):
    return {
        "name": p["name"],                       # 完整名称（悬停显示）
        "label": p.get("short") or short_label(p["name"]),  # 节点上显示的短名
        "id": p.get("id", ""),
        "importance": p.get("importance", "中"),
        "status": p.get("status", "未学"),
        "mastery": p.get("mastery", 0),
        "note": p.get("note", ""),
    }


def chapter_tree(ch):
    return {
        "name": ch["title"],
        "children": [
            {"name": sec["title"], "children": [point_node(p) for p in sec.get("points", [])]}
            for sec in ch.get("sections", [])
        ],
    }


def write_map(tree, title, out_path, template):
    html = (template
            .replace("__TITLE__", title)
            .replace("__GENERATED__", "更新于 " + datetime.date.today().isoformat())
            .replace("__DATA__", json.dumps(tree, ensure_ascii=False)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"已生成 {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("knowledge", help="knowledge.json 路径")
    ap.add_argument("--chapter", type=int, action="append",
                    help="只生成指定章（可重复传入），默认全部章节")
    ap.add_argument("--book", action="store_true", help="生成整本书总览图")
    ap.add_argument("-o", "--out", help="输出目录，默认 knowledge.json 同级的 mindmaps/")
    args = ap.parse_args()

    kpath = pathlib.Path(args.knowledge)
    data = json.loads(kpath.read_text(encoding="utf-8"))
    out_dir = pathlib.Path(args.out) if args.out else kpath.parent / "mindmaps"
    template = TEMPLATE.read_text(encoding="utf-8")
    book = data.get("textbook", "教材")

    chapters = data.get("chapters", [])
    if args.book:
        tree = {"name": book, "children": [chapter_tree(ch) for ch in chapters]}
        write_map(tree, f"{book} · 全书知识图谱", out_dir / "book.html", template)
        return

    wanted = set(args.chapter) if args.chapter else None
    hit = False
    for ch in chapters:
        if wanted and ch["id"] not in wanted:
            continue
        hit = True
        write_map(chapter_tree(ch), f"{book} · {ch['title']}",
                  out_dir / f"chapter-{ch['id']:02d}.html", template)
    if not hit:
        sys.exit(f"knowledge.json 中没有找到章节 {sorted(wanted)}")


if __name__ == "__main__":
    main()
