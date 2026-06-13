#!/usr/bin/env python3
"""Render lecture JSON into Obsidian Markdown and/or interactive HTML lecture notes.

Why JSON as the source: the model writes structured content once, and this script
guarantees identical, well-formed output regardless of which model produced it.
The HTML renderer understands a controlled Markdown subset (bold, lists, tables,
inline code) so that Markdown the model writes inside fields renders cleanly
instead of leaking raw `**` / `-` / `|` into the page.

Usage:
  python3 build_lecture.py <lecture.json>                     # both formats
  python3 build_lecture.py <lecture.json> --format obsidian   # markdown only
  python3 build_lecture.py <lecture.json> --format html       # html only
  python3 build_lecture.py <lecture.json> -o <output dir>     # default: alongside json

Lecture JSON schema (all strings are Simplified Chinese; math in LaTeX $...$ /
$$...$$ — Obsidian renders natively, the HTML loads MathJax from CDN and falls
back to LaTeX source offline). `mode` selects the teaching style and the fields
each point is expected to carry:

{
  "textbook": "公司理财（罗斯等）",
  "chapter_id": 1,
  "chapter_title": "第一章 公司理财导论",
  "section": "1.1 什么是公司理财",
  "mode": "deep",                         // "deep" 深入讲解 | "speedrun" 考试速通
  "points": [
    {
      "id": "1.1.1",
      "name": "资产负债表恒等式",
      "importance": "高",                  // 高 / 中 / 低
      "exam_focus": "考情定位（两种模式都填）",

      // ---- deep mode fields ----
      "textbook_excerpt": "教材关键原文（忠实摘录原句，或在原文凌乱时概括其核心表述）",
      "intuition": "直观理解：生活例子/比喻，说明比喻边界",
      "formal": "严谨表述：教材级定义/定理/公式与推导，深入、丰富",

      // ---- speedrun mode fields ----
      "key_point": "核心结论：一两句把考点说透",
      "method": "解题思维/套路：这类题怎么审、用什么公式、按什么步骤解",

      // ---- examples (deep 通常 1 道；speedrun 多道) ----
      "example": {"problem": "题面", "solution": "完整解答"},
      "examples": [{"problem": "...", "solution": "..."}],

      // ---- both modes ----
      "pitfalls": "易错辨析",
      "memory_hook": "记忆抓手",
      "links": ["1.1.2", "1.1.3"]
    }
  ]
}

Required per point: id, name, and at least one complete example (`example` or a
non-empty `examples`, each with problem+solution). Deep mode additionally
requires `formal`; speedrun mode additionally requires `method`.
"""
import argparse
import datetime
import html as html_mod
import json
import pathlib
import re
import sys

IMPORTANCE_MARK = {"高": "⭐", "中": "", "低": ""}
MATH_RE = re.compile(r"(\$\$.+?\$\$|\$[^$\n]+?\$)", re.S)


# ---------------------------------------------------------------------------
# Controlled Markdown -> HTML (bold, lists, tables, inline code; math-safe)
# ---------------------------------------------------------------------------
def _inline(escaped):
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+?)`", r"<code>\1</code>", escaped)
    return escaped


def _render_table(lines):
    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]
    header = cells(lines[0])
    body = [cells(r) for r in lines[2:] if r.strip()]
    out = ['<table class="lec-table"><thead><tr>']
    out += [f"<th>{_inline(html_mod.escape(c, quote=False))}</th>" for c in header]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join(
            f"<td>{_inline(html_mod.escape(c, quote=False))}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _render_list(lines):
    parsed = []
    for line in lines:
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            indent = len(m.group(1).replace("\t", "    "))
            ordered = bool(re.match(r"\d+\.", m.group(2)))
            parsed.append([indent, ordered, m.group(3)])
        elif line.strip() and parsed:
            parsed[-1][2] += " " + line.strip()
    if not parsed:
        return ""
    levels = {ind: i for i, ind in enumerate(sorted({p[0] for p in parsed}))}
    out, open_tags, cur = [], [], -1
    for indent, ordered, text in parsed:
        lvl = levels[indent]
        while cur < lvl:
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>")
            open_tags.append(tag)
            cur += 1
        while cur > lvl:
            out.append(f"</{open_tags.pop()}>")
            cur -= 1
        out.append(f"<li>{_inline(html_mod.escape(text, quote=False))}</li>")
    while open_tags:
        out.append(f"</{open_tags.pop()}>")
    return "".join(out)


def _render_block(block):
    lines = block.split("\n")
    if (len(lines) >= 2 and all("|" in l for l in lines[:2])
            and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[1]) and "-" in lines[1]):
        return _render_table(lines)
    list_lines = [l for l in lines if l.strip()]
    if list_lines and all(re.match(r"^\s*([-*]|\d+\.)\s+", l) for l in list_lines):
        return _render_list(lines)
    body = "<br>".join(_inline(html_mod.escape(l, quote=False)) for l in lines)
    return f"<p>{body}</p>"


def render_rich(text):
    """Render the controlled Markdown subset to HTML, keeping LaTeX intact."""
    if not text:
        return ""
    math = []

    def stash(m):
        math.append(m.group(1))
        return f"\x00M{len(math) - 1}\x00"

    protected = MATH_RE.sub(stash, text)
    blocks = [b for b in re.split(r"\n\s*\n", protected.strip()) if b.strip()]
    out = "\n".join(_render_block(b) for b in blocks)
    return re.sub(r"\x00M(\d+)\x00",
                  lambda m: html_mod.escape(math[int(m.group(1))], quote=False), out)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def example_list(p):
    if isinstance(p.get("examples"), list) and p["examples"]:
        return p["examples"]
    if p.get("example"):
        return [p["example"]]
    return []


def validate(data):
    errs = []
    for key in ("textbook", "chapter_id", "chapter_title", "section", "mode"):
        if not data.get(key) and data.get(key) != 0:
            errs.append(f"missing top-level field: {key}")
    mode = data.get("mode")
    if mode not in ("deep", "speedrun"):
        errs.append("mode must be 'deep' or 'speedrun'")
    for i, p in enumerate(data.get("points") or []):
        tag = f"points[{i}]"
        for key in ("id", "name"):
            if not p.get(key):
                errs.append(f"{tag}: missing {key}")
        exs = example_list(p)
        if not exs:
            errs.append(f"{tag}: needs at least one example (example or examples[])")
        for j, ex in enumerate(exs):
            if not (ex.get("problem") and ex.get("solution")):
                errs.append(f"{tag}.examples[{j}]: problem and solution are required")
        if mode == "deep" and not p.get("formal"):
            errs.append(f"{tag}: deep mode requires 'formal' (严谨表述)")
        if mode == "speedrun" and not p.get("method"):
            errs.append(f"{tag}: speedrun mode requires 'method' (解题思维)")
    if not (data.get("points")):
        errs.append("points is empty")
    return errs


def sanitize(name):
    return re.sub(r'[\\/:*?"<>|\s]+', "-", name.strip())


# ---------------------------------------------------------------------------
# Obsidian Markdown
# ---------------------------------------------------------------------------
def quote_block(text, callout, foldable=False):
    body = "\n".join("> " + line for line in text.strip().splitlines())
    return f"> [!{callout}]{'-' if foldable else ''}\n{body}"


def render_markdown(data):
    mode = data["mode"]
    mode_label = "深入讲解" if mode == "deep" else "考试速通"
    lines = [
        "---",
        f"textbook: {data['textbook']}",
        f"chapter: {data['chapter_id']}",
        f'section: "{data["section"]}"',
        f"mode: {mode}",
        f"points: [{', '.join(p['id'] for p in data['points'])}]",
        f"generated: {datetime.date.today().isoformat()}",
        "---",
        "",
        f"# {data['section']}",
        "",
        f"> 《{data['textbook']}》{data['chapter_title']} ｜ {mode_label}模式 ｜ "
        f"{len(data['points'])} 个知识点 ｜ 例题答案默认折叠，先自己做再展开。",
        "",
    ]
    for p in data["points"]:
        star = IMPORTANCE_MARK.get(p.get("importance", "中"), "")
        lines.append(f"## {p['id']} {p['name']} {star}".rstrip())
        lines.append("")
        if p.get("exam_focus"):
            lines.append(quote_block(p["exam_focus"], "info"))
            lines.append("")
        if mode == "deep":
            if p.get("textbook_excerpt"):
                lines.append(quote_block("**教材原文**\n" + p["textbook_excerpt"], "quote"))
                lines.append("")
            if p.get("intuition"):
                lines.append(f"**直观理解**　{p['intuition']}")
                lines.append("")
            if p.get("formal"):
                lines.append(f"**严谨表述**　{p['formal']}")
                lines.append("")
        else:  # speedrun
            if p.get("key_point"):
                lines.append(f"**核心结论**　{p['key_point']}")
                lines.append("")
            if p.get("method"):
                lines.append(quote_block("**解题思维**\n" + p["method"], "example"))
                lines.append("")
        exs = example_list(p)
        for n, ex in enumerate(exs, 1):
            label = f"例题{n}" if len(exs) > 1 else "例题"
            lines.append(f"**{label}**　{ex['problem']}")
            lines.append("")
            sol = "\n".join("> " + l for l in ex["solution"].strip().splitlines())
            lines.append(f"> [!success]- 参考解答（{label}，先自己做，再点开）")
            lines.append(sol)
            lines.append("")
        if p.get("pitfalls"):
            lines.append(quote_block("**易错辨析**　" + p["pitfalls"], "warning"))
            lines.append("")
        if p.get("memory_hook"):
            lines.append(quote_block("**记忆抓手**　" + p["memory_hook"], "tip"))
            lines.append("")
        if p.get("links"):
            lines.append(f"*关联知识点：{'、'.join(p['links'])}*")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive HTML
# ---------------------------------------------------------------------------
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
  .modetag {{ display:inline-block; font-size:12px; padding:2px 10px; border-radius:99px;
             background:#eef2ff; color:#4338ca; margin-left:6px; }}
  #mjwarn {{ display: none; background: #fef3c7; border: 1px solid #fcd34d; padding: 8px 12px; border-radius: 8px; font-size: 13px; }}
  section.point {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px 24px; margin: 18px 0; }}
  section.point h2 {{ font-size: 17px; margin: 0 0 10px; display: flex; align-items: center; gap: 8px; }}
  .box {{ border-radius: 8px; padding: 10px 14px; margin: 10px 0; font-size: 14px; }}
  .box.info {{ background: #eff6ff; border: 1px solid #bfdbfe; }}
  .box.warn {{ background: #fffbeb; border: 1px solid #fde68a; }}
  .box.tip {{ background: #f0fdf4; border: 1px solid #bbf7d0; }}
  .box .rich {{ display:inline; }}
  .field {{ margin: 12px 0; }}
  .field .lead {{ color: #1d4ed8; font-weight: 600; display: block; margin-bottom: 4px; }}
  .excerpt {{ background: #faf5ff; border-left: 3px solid #a855f7; padding: 10px 14px; margin: 10px 0;
             font-size: 14px; color: #4b5563; }}
  .excerpt .lead {{ color:#7e22ce; }}
  .method {{ background: #ecfeff; border: 1px solid #67e8f9; border-radius: 8px; padding: 10px 14px; margin: 10px 0; }}
  .method .lead {{ color:#0e7490; }}
  .rich {{ font-size: 14.5px; line-height: 2; }}
  .rich p {{ margin: 6px 0; }}
  .rich ul, .rich ol {{ margin: 6px 0; padding-left: 22px; line-height: 1.9; }}
  .rich li {{ margin: 3px 0; }}
  .rich code {{ background: #f3f4f6; padding: 1px 5px; border-radius: 4px; font-size: .9em; }}
  table.lec-table {{ border-collapse: collapse; margin: 10px 0; font-size: 14px; width: 100%; }}
  table.lec-table th, table.lec-table td {{ border: 1px solid #d1d5db; padding: 6px 10px; text-align: left; vertical-align: top; }}
  table.lec-table th {{ background: #f3f4f6; }}
  details {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 14px; margin: 10px 0; background: #fafafa; }}
  details summary {{ cursor: pointer; font-weight: 600; font-size: 14px; color: #374151; }}
  details .rich {{ margin-top: 10px; }}
  .donebtn {{ margin-top: 10px; font-size: 13px; padding: 5px 14px; border-radius: 99px; border: 1px solid #d1d5db; background: #fff; cursor: pointer; }}
  .donebtn.on {{ background: #dcfce7; border-color: #16a34a; color: #14532d; }}
  .links {{ font-size: 13px; color: #6b7280; font-style: italic; }}
</style>
</head>
<body>
<div id="layout">
<nav id="toc"><h2>{section}</h2>{toc}</nav>
<main>
<h1>{section}<span class="modetag">{mode_label}</span></h1>
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
    return html_mod.escape(str(s or ""), quote=False)


def field(lead, text):
    return f'<div class="field"><span class="lead">{lead}</span><div class="rich">{render_rich(text)}</div></div>'


def render_html(data):
    mode = data["mode"]
    mode_label = "深入讲解" if mode == "deep" else "考试速通"
    toc = "".join(
        f'<a href="#p-{esc(p["id"])}">{esc(p["id"])} {esc(p["name"])}'
        f'{" ⭐" if p.get("importance") == "高" else ""}</a>'
        for p in data["points"])
    out = [HTML_HEAD.format(
        title=f"{data['section']} · 讲义", section=esc(data["section"]),
        textbook=esc(data["textbook"]), chapter=esc(data["chapter_title"]),
        n=len(data["points"]), date=datetime.date.today().isoformat(),
        toc=toc, mode_label=mode_label)]
    for p in data["points"]:
        star = " ⭐" if p.get("importance") == "高" else ""
        out.append(f'<section class="point" id="p-{esc(p["id"])}">')
        out.append(f'<h2>{esc(p["id"])} {esc(p["name"])}{star}</h2>')
        if p.get("exam_focus"):
            out.append(f'<div class="box info">📌 <span class="rich">{render_rich(p["exam_focus"])}</span></div>')
        if mode == "deep":
            if p.get("textbook_excerpt"):
                out.append(f'<div class="excerpt"><span class="lead">📖 教材原文</span>'
                           f'<div class="rich">{render_rich(p["textbook_excerpt"])}</div></div>')
            if p.get("intuition"):
                out.append(field("直观理解", p["intuition"]))
            if p.get("formal"):
                out.append(field("严谨表述", p["formal"]))
        else:
            if p.get("key_point"):
                out.append(field("核心结论", p["key_point"]))
            if p.get("method"):
                out.append(f'<div class="method"><span class="lead">🧭 解题思维</span>'
                           f'<div class="rich">{render_rich(p["method"])}</div></div>')
        exs = example_list(p)
        for n, ex in enumerate(exs, 1):
            label = f"例题{n}" if len(exs) > 1 else "例题"
            out.append(f'<div class="field"><span class="lead">{label}</span>'
                       f'<div class="rich">{render_rich(ex["problem"])}</div></div>')
            out.append(f'<details><summary>参考解答（{label}，先自己做，再点开）</summary>'
                       f'<div class="rich">{render_rich(ex["solution"])}</div></details>')
        if p.get("pitfalls"):
            out.append(f'<div class="box warn">⚠️ <b>易错辨析</b> <span class="rich">{render_rich(p["pitfalls"])}</span></div>')
        if p.get("memory_hook"):
            out.append(f'<div class="box tip">💡 <b>记忆抓手</b> <span class="rich">{render_rich(p["memory_hook"])}</span></div>')
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
    data.setdefault("mode", "deep")  # backward compatible with pre-v1.1 lecture JSON
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
