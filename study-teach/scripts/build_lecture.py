#!/usr/bin/env python3
"""Render lecture JSON into Obsidian Markdown and/or interactive HTML lecture notes.

Why JSON as the source: the model writes structured content once, and this script
guarantees identical, well-formed output regardless of which model produced it.

Usage:
  python3 build_lecture.py <lecture.json>                     # both formats
  python3 build_lecture.py <lecture.json> --format obsidian   # markdown only
  python3 build_lecture.py <lecture.json> --format html       # html only
  python3 build_lecture.py <lecture.json> -o <output dir>     # default: alongside json

Lecture JSON schema (all strings are Simplified Chinese; math written as LaTeX
$...$ — Obsidian renders it natively, the HTML version loads MathJax from CDN
and falls back to showing LaTeX source offline):

{
  "textbook": "西方经济学（微观部分）",
  "chapter_id": 3,
  "chapter_title": "第三章 效用论",
  "section": "3.1 基数效用论",
  "points": [
    {
      "id": "3.1.1",
      "name": "效用与基数效用",
      "importance": "高",                      // 高 / 中 / 低
      "exam_focus": "考情定位：常考题型、分值。",
      "intuition": "直观引入：生活例子或比喻，说明比喻边界。",
      "formal": "严谨表述：教材级定义/定理/公式 $MU=\\frac{\\Delta TU}{\\Delta Q}$，符号逐一交代。",
      "example": {
        "problem": "例题题面（必填）",
        "solution": "完整解答过程（必填，渲染为'点击展开'）"
      },
      "pitfalls": "易错辨析：最容易和什么混、考试在哪挖坑。",
      "memory_hook": "记忆抓手：口诀/框架；文科类附背诵版要点。",
      "links": ["3.1.2", "3.2.1"]             // related point ids, optional
    }
  ]
}

Required per point: id, name, formal, example.problem, example.solution.
Output files: <out>/<section sanitized>.md / .html
"""
import argparse
import datetime
import html as html_mod
import json
import pathlib
import re
import sys

IMPORTANCE_MARK = {"高": "⭐", "中": "", "低": ""}


def validate(data):
    errs = []
    for key in ("textbook", "chapter_id", "chapter_title", "section"):
        if not data.get(key) and data.get(key) != 0:
            errs.append(f"missing top-level field: {key}")
    pts = data.get("points") or []
    if not pts:
        errs.append("points is empty")
    for i, p in enumerate(pts):
        tag = f"points[{i}]"
        for key in ("id", "name", "formal"):
            if not p.get(key):
                errs.append(f"{tag}: missing {key}")
        ex = p.get("example") or {}
        if not ex.get("problem") or not ex.get("solution"):
            errs.append(f"{tag}: example.problem and example.solution are required "
                        "(every knowledge point must carry a worked example)")
    return errs


def sanitize(name):
    return re.sub(r'[\\/:*?"<>|\s]+', "-", name.strip())


def quote_block(text, callout):
    body = "\n".join("> " + line for line in text.strip().splitlines())
    return f"> [!{callout}]\n{body}"


def render_markdown(data):
    lines = [
        "---",
        f"textbook: {data['textbook']}",
        f"chapter: {data['chapter_id']}",
        f"section: \"{data['section']}\"",
        f"points: [{', '.join(p['id'] for p in data['points'])}]",
        f"generated: {datetime.date.today().isoformat()}",
        "---",
        "",
        f"# {data['section']}",
        "",
        f"> 《{data['textbook']}》{data['chapter_title']} ｜ 共 {len(data['points'])} 个知识点 ｜ 例题答案默认折叠，先自己做再展开。",
        "",
    ]
    for p in data["points"]:
        star = IMPORTANCE_MARK.get(p.get("importance", "中"), "")
        lines.append(f"## {p['id']} {p['name']} {star}".rstrip())
        lines.append("")
        if p.get("exam_focus"):
            lines.append(quote_block(p["exam_focus"], "info"))
            lines.append("")
        if p.get("intuition"):
            lines.append(f"**直观理解**　{p['intuition']}")
            lines.append("")
        lines.append(f"**严谨表述**　{p['formal']}")
        lines.append("")
        ex = p["example"]
        lines.append(f"**例题**　{ex['problem']}")
        lines.append("")
        sol = "\n".join("> " + line for line in ex["solution"].strip().splitlines())
        lines.append("> [!success]- 参考解答（先自己做，再点开）")
        lines.append(sol)
        lines.append("")
        if p.get("pitfalls"):
            lines.append(quote_block("**易错辨析**　" + p["pitfalls"], "warning"))
            lines.append("")
        if p.get("memory_hook"):
            lines.append(quote_block("**记忆抓手**　" + p["memory_hook"], "tip"))
            lines.append("")
        if p.get("links"):
            lines.append(f"*关联知识点：{('、'.join(p['links']))}*")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<script>
window.MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }} }};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"
        onerror="document.getElementById('mjwarn').style.display='block'"></script>
<style>
  :root {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  body {{ margin: 0; background: #f7f7f4; color: #1f2937; }}
  #layout {{ display: flex; max-width: 1100px; margin: 0 auto; }}
  #toc {{ width: 230px; flex-shrink: 0; position: sticky; top: 0; align-self: flex-start;
         height: 100vh; overflow-y: auto; padding: 24px 10px 24px 18px; box-sizing: border-box;
         border-right: 1px solid #e5e7eb; font-size: 13px; }}
  #toc h2 {{ font-size: 13px; color: #6b7280; margin: 0 0 8px; }}
  #toc a {{ display: block; padding: 5px 8px; color: #374151; text-decoration: none; border-radius: 6px; line-height: 1.5; }}
  #toc a:hover {{ background: #eef2ff; }}
  #toc a.done {{ color: #16a34a; }}
  main {{ flex: 1; padding: 28px 36px 80px; min-width: 0; }}
  h1 {{ font-size: 22px; }}
  .meta {{ color: #6b7280; font-size: 13px; margin-bottom: 8px; }}
  #mjwarn {{ display: none; background: #fef3c7; border: 1px solid #fcd34d; padding: 8px 12px; border-radius: 8px; font-size: 13px; }}
  section.point {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px 24px; margin: 18px 0; }}
  section.point h2 {{ font-size: 17px; margin: 0 0 10px; display: flex; align-items: center; gap: 8px; }}
  .box {{ border-radius: 8px; padding: 10px 14px; margin: 10px 0; font-size: 14px; line-height: 1.9; white-space: pre-wrap; }}
  .box.info {{ background: #eff6ff; border: 1px solid #bfdbfe; }}
  .box.warn {{ background: #fffbeb; border: 1px solid #fde68a; }}
  .box.tip {{ background: #f0fdf4; border: 1px solid #bbf7d0; }}
  .para {{ font-size: 14.5px; line-height: 2; white-space: pre-wrap; margin: 10px 0; }}
  .para b.lead {{ color: #1d4ed8; }}
  details {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 14px; margin: 10px 0; background: #fafafa; }}
  details summary {{ cursor: pointer; font-weight: 600; font-size: 14px; color: #374151; }}
  details .para {{ margin-top: 10px; }}
  .donebtn {{ margin-top: 10px; font-size: 13px; padding: 5px 14px; border-radius: 99px; border: 1px solid #d1d5db; background: #fff; cursor: pointer; }}
  .donebtn.on {{ background: #dcfce7; border-color: #16a34a; color: #14532d; }}
  .links {{ font-size: 13px; color: #6b7280; font-style: italic; }}
</style>
</head>
<body>
<div id="layout">
<nav id="toc"><h2>{section}</h2>{toc}</nav>
<main>
<h1>{section}</h1>
<div class="meta">《{textbook}》{chapter} ｜ {n} 个知识点 ｜ 生成于 {date} ｜ 例题先自己做，再点开解答</div>
<div id="mjwarn">⚠️ 离线状态：公式渲染（MathJax）加载失败，以下公式显示为 LaTeX 源码，含义不受影响。</div>
"""

HTML_TAIL = """</main></div>
<script>
const KEY = "lecture-done-" + location.pathname;
const done = new Set(JSON.parse(localStorage.getItem(KEY) || "[]"));
function refresh() {
  document.querySelectorAll(".donebtn").forEach(b => {
    const on = done.has(b.dataset.id);
    b.classList.toggle("on", on);
    b.textContent = on ? "✓ 已学完" : "标记为已学";
    const a = document.querySelector(`#toc a[href="#p-${CSS.escape(b.dataset.id)}"]`);
    if (a) a.classList.toggle("done", on);
  });
}
document.querySelectorAll(".donebtn").forEach(b => b.addEventListener("click", () => {
  done.has(b.dataset.id) ? done.delete(b.dataset.id) : done.add(b.dataset.id);
  localStorage.setItem(KEY, JSON.stringify([...done]));
  refresh();
}));
refresh();
</script>
</body>
</html>
"""


def esc(s):
    return html_mod.escape(s or "", quote=False)


def render_html(data):
    toc = "".join(
        f'<a href="#p-{esc(p["id"])}">{esc(p["id"])} {esc(p["name"])}'
        f'{" ⭐" if p.get("importance") == "高" else ""}</a>'
        for p in data["points"])
    out = [HTML_HEAD.format(
        title=f"{data['section']} · 讲义", section=esc(data["section"]),
        textbook=esc(data["textbook"]), chapter=esc(data["chapter_title"]),
        n=len(data["points"]), date=datetime.date.today().isoformat(), toc=toc)]
    for p in data["points"]:
        star = " ⭐" if p.get("importance") == "高" else ""
        out.append(f'<section class="point" id="p-{esc(p["id"])}">')
        out.append(f'<h2>{esc(p["id"])} {esc(p["name"])}{star}</h2>')
        if p.get("exam_focus"):
            out.append(f'<div class="box info">📌 {esc(p["exam_focus"])}</div>')
        if p.get("intuition"):
            out.append(f'<div class="para"><b class="lead">直观理解</b>　{esc(p["intuition"])}</div>')
        out.append(f'<div class="para"><b class="lead">严谨表述</b>　{esc(p["formal"])}</div>')
        ex = p["example"]
        out.append(f'<div class="para"><b class="lead">例题</b>　{esc(ex["problem"])}</div>')
        out.append(f'<details><summary>参考解答（先自己做，再点开）</summary>'
                   f'<div class="para">{esc(ex["solution"])}</div></details>')
        if p.get("pitfalls"):
            out.append(f'<div class="box warn">⚠️ <b>易错辨析</b>　{esc(p["pitfalls"])}</div>')
        if p.get("memory_hook"):
            out.append(f'<div class="box tip">💡 <b>记忆抓手</b>　{esc(p["memory_hook"])}</div>')
        if p.get("links"):
            out.append(f'<div class="links">关联知识点：{esc("、".join(p["links"]))}</div>')
        out.append(f'<button class="donebtn" data-id="{esc(p["id"])}"></button>')
        out.append("</section>")
    out.append(HTML_TAIL)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lecture_json")
    ap.add_argument("--format", choices=["obsidian", "html", "both"], default="both")
    ap.add_argument("-o", "--out", help="output directory, default alongside the json")
    args = ap.parse_args()

    src = pathlib.Path(args.lecture_json)
    data = json.loads(src.read_text(encoding="utf-8"))
    errs = validate(data)
    if errs:
        sys.exit("lecture JSON validation failed:\n  " + "\n  ".join(errs))

    out_dir = pathlib.Path(args.out) if args.out else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize(data["section"])
    if args.format in ("obsidian", "both"):
        (out_dir / f"{stem}.md").write_text(render_markdown(data), encoding="utf-8")
        print(f"generated {out_dir / (stem + '.md')}")
    if args.format in ("html", "both"):
        (out_dir / f"{stem}.html").write_text(render_html(data), encoding="utf-8")
        print(f"generated {out_dir / (stem + '.html')}")


if __name__ == "__main__":
    main()
