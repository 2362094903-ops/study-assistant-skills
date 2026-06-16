#!/usr/bin/env python3
"""Render lecture JSON into Obsidian Markdown and/or interactive HTML lecture notes.

Why JSON as the source: the model writes structured content once, and this script
guarantees identical, well-formed output regardless of which model produced it.
The HTML renderer understands a controlled Markdown subset (bold, lists, tables,
figures/images, inline code) so that Markdown the model writes inside fields
renders cleanly instead of leaking raw `**` / `-` / `|` into the page.

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

      // ---- examples (optional; allocate by importance / question-bank frequency) ----
      // 不要求每个知识点都有例题。优先给高重要度、高频题库考点、课件原有例题对应的知识点配题；
      // 低频或纯背景点可以省略 examples，把篇幅留给解释。每道例题都可交互作答，提交后批改再展开
      // solution。请按知识点选择最合适的题型，一节里的例题尽量有变化，不要全是同一种。
      // 题型 type（默认 text）：
      //   "single" 单选：options[] + answer=正确项下标(0=A)
      //   "multi"  多选：options[] + answer=正确项下标数组 [0,2]
      //   "judge"  判断：answer=true/false
      //   "text"   填空/计算/简答：自由作答框；answer 选填=最终答案(字符串或可接受写法数组)，
      //            填了就自动判最终答案✓/✗，不填则提交后揭示解答+自评
      // problem 题面、solution 完整解答/解析 必填（所有题型，提交后展开）。
      // Obsidian 版为静态：题面（选择题附选项列表）+ 折叠解答（含答案）。
      "examples": [
        {"type": "single", "problem": "下列哪项属于资本预算决策？", "options": ["延长应付账款账期", "新建一条生产线", "发行股票融资", "提高存货周转"], "answer": 1, "solution": "B。新建生产线是长期资产支出，属资本预算……"},
        {"type": "judge", "problem": "股东权益 = 资产 + 负债。", "answer": false, "solution": "错误。股东权益 = 资产 − 负债……"},
        {"type": "text", "problem": "U = XY，Pₓ=1，Pᵧ=2，I=40，求最优组合。", "answer": ["X=20,Y=10", "X=20，Y=10"], "solution": "由 MUₓ/Pₓ=MUᵧ/Pᵧ……得 X=20，Y=10。"}
      ],

      // ---- both modes ----
      "pitfalls": "易错辨析",
      "memory_hook": "记忆抓手",
      "figures": [
        {
          "path": "assets/3.5-efn-growth.png",
          "caption": "销售增长率越高，EFN 通常越大",
          "source": "Python/matplotlib: EFN = (A/S − L/S)ΔS − PM×S1×b",
          "alt": "EFN 随销售增长率上升的函数图像"
        }
      ],
      "links": ["1.1.2", "1.1.3"]
    }
  ]
}

Required per point: id and name. Examples are optional, but every included
example (`example` or `examples[]`) must have problem+solution. Deep mode
additionally requires `formal`; speedrun mode additionally requires `method`.
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


def _is_table_sep(line):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    seps = [c for c in cells if c]
    return bool(seps) and all(re.match(r"^:?-{3,}:?$", c) for c in seps)


def _is_table_start(lines, i):
    return (
        i + 1 < len(lines)
        and "|" in lines[i]
        and "|" in lines[i + 1]
        and _is_table_sep(lines[i + 1])
    )


def _split_table_row(row):
    cells, cur, esc_pipe = [], [], False
    text = row.strip().strip("|")
    for ch in text:
        if ch == "\\" and not esc_pipe:
            esc_pipe = True
            continue
        if ch == "|" and not esc_pipe:
            cells.append("".join(cur).strip())
            cur = []
            continue
        if esc_pipe:
            cur.append(ch)
            esc_pipe = False
            continue
        cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def _render_table(lines):
    header = _split_table_row(lines[0])
    body = [_split_table_row(r) for r in lines[2:] if r.strip() and "|" in r]
    width = max([len(header)] + [len(r) for r in body] + [1])
    header += [""] * (width - len(header))
    out = ['<div class="table-wrap"><table class="lec-table"><thead><tr>']
    out += [f"<th>{_inline(html_mod.escape(c, quote=False))}</th>" for c in header]
    out.append("</tr></thead><tbody>")
    for r in body:
        r += [""] * (width - len(r))
        out.append("<tr>" + "".join(
            f"<td>{_inline(html_mod.escape(c, quote=False))}</td>" for c in r) + "</tr>")
    out.append("</tbody></table></div>")
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
    chunks, buf, i = [], [], 0

    def flush_buf():
        if not buf:
            return
        list_lines = [l for l in buf if l.strip()]
        if list_lines and all(re.match(r"^\s*([-*]|\d+\.)\s+", l) for l in list_lines):
            chunks.append(_render_list(buf))
        else:
            body = "<br>".join(_inline(html_mod.escape(l, quote=False)) for l in buf)
            chunks.append(f"<p>{body}</p>")
        buf.clear()

    while i < len(lines):
        if _is_table_start(lines, i):
            flush_buf()
            table_lines = [lines[i], lines[i + 1]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            chunks.append(_render_table(table_lines))
            continue
        buf.append(lines[i])
        i += 1
    flush_buf()
    return "\n".join(chunks)


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


def render_inline_rich(text):
    """Inline-only rich render (bold/code + math), no block/list/table — for option labels."""
    if not text:
        return ""
    math = []

    def stash(m):
        math.append(m.group(1))
        return f"\x00M{len(math) - 1}\x00"

    protected = MATH_RE.sub(stash, text)
    out = _inline(html_mod.escape(protected, quote=False))
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


def example_count(data):
    return sum(len(example_list(p)) for p in data.get("points", []))


def figure_list(p):
    figures = p.get("figures") or p.get("images") or []
    if isinstance(figures, dict):
        return [figures]
    if isinstance(figures, list):
        return figures
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
        for j, ex in enumerate(exs):
            etag = f"{tag}.examples[{j}]"
            if not (ex.get("problem") and ex.get("solution")):
                errs.append(f"{etag}: problem and solution are required")
            etype = ex.get("type", "text")
            a = ex.get("answer")
            if etype not in ("single", "multi", "judge", "text"):
                errs.append(f"{etag}: type must be single / multi / judge / text")
            elif etype in ("single", "multi"):
                opts = ex.get("options")
                if not isinstance(opts, list) or len(opts) < 2:
                    errs.append(f"{etag}: {etype} needs an options list")
                elif etype == "single":
                    if not isinstance(a, int) or not (0 <= a < len(opts)):
                        errs.append(f"{etag}: single answer must be a valid option index")
                else:
                    if (not isinstance(a, list) or not a
                            or not all(isinstance(x, int) and 0 <= x < len(opts) for x in a)):
                        errs.append(f"{etag}: multi answer must be a list of valid option indices")
            elif etype == "judge":
                if not isinstance(a, bool):
                    errs.append(f"{etag}: judge answer must be true or false")
            else:  # text
                if a is not None and not (isinstance(a, str)
                                          or (isinstance(a, list) and all(isinstance(x, str) for x in a))):
                    errs.append(f"{etag}: text answer must be a string or a list of strings")
        if mode == "deep" and not p.get("formal"):
            errs.append(f"{tag}: deep mode requires 'formal' (严谨表述)")
        if mode == "speedrun" and not p.get("method"):
            errs.append(f"{tag}: speedrun mode requires 'method' (解题思维)")
        for j, fig in enumerate(figure_list(p)):
            ftag = f"{tag}.figures[{j}]"
            if not isinstance(fig, dict):
                errs.append(f"{ftag}: must be an object")
                continue
            if not fig.get("path"):
                errs.append(f"{ftag}: path is required")
            if not fig.get("caption"):
                errs.append(f"{ftag}: caption is required")
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


def render_markdown_figures(figures):
    lines = []
    for fig in figures:
        path = str(fig.get("path", "")).replace("\\", "/")
        alt = fig.get("alt") or fig.get("caption") or "讲解配图"
        lines.append(f"![{alt}]({path})")
        if fig.get("caption"):
            lines.append(f"*图：{fig['caption']}*")
        if fig.get("source"):
            lines.append(f"> [!note]\n> {fig['source']}")
        lines.append("")
    return lines


def render_markdown(data):
    mode = data["mode"]
    mode_label = "深入讲解" if mode == "deep" else "考试速通"
    ex_count = example_count(data)
    practice_note = f"例题 {ex_count} 道，答案默认折叠，先自己做再展开。" if ex_count else "本节按考频未配置例题，重点看讲解与易错辨析。"
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
        f"{len(data['points'])} 个知识点 ｜ {practice_note}",
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
        figs = figure_list(p)
        if figs:
            lines.extend(render_markdown_figures(figs))
        exs = example_list(p)
        TYPE_LABEL = {"single": "单选", "multi": "多选", "judge": "判断", "text": ""}
        for n, ex in enumerate(exs, 1):
            base = f"例题{n}" if len(exs) > 1 else "例题"
            etype = ex.get("type", "text")
            tlabel = TYPE_LABEL.get(etype, "")
            head = f"{base}（{tlabel}）" if tlabel else base
            lines.append(f"**{head}**　{ex['problem']}")
            lines.append("")
            opts = ex.get("options") or []
            if etype in ("single", "multi") and opts:
                for i, o in enumerate(opts):
                    lines.append(f"- {chr(65 + i)}. {o}")
                lines.append("")
            if etype == "single":
                ans_line = f"**答案：{chr(65 + ex['answer'])}**\n"
            elif etype == "multi":
                ans_line = f"**答案：{'、'.join(chr(65 + i) for i in sorted(ex['answer']))}**\n"
            elif etype == "judge":
                ans_line = f"**答案：{'正确' if ex.get('answer') else '错误'}**\n"
            else:
                ans_line = ""
            sol_text = ans_line + ex["solution"].strip()
            sol = "\n".join("> " + l for l in sol_text.splitlines())
            lines.append(f"> [!success]- 参考解答（{base}，先自己做，再点开）")
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
  .box .rich {{ display:block; margin-top: 4px; }}
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
  .table-wrap {{ display: block; width: 100%; overflow-x: auto; margin: 12px 0; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; }}
  table.lec-table {{ border-collapse: collapse; border-spacing: 0; margin: 0; font-size: 14px; width: 100%; min-width: max-content; }}
  table.lec-table th, table.lec-table td {{ border: 1px solid #cbd5e1; padding: 7px 10px; text-align: left; vertical-align: top; background-clip: padding-box; }}
  table.lec-table th {{ background: #f1f5f9; font-weight: 700; }}
  table.lec-table tr:last-child td {{ border-bottom: 0; }}
  table.lec-table tr td:first-child, table.lec-table tr th:first-child {{ border-left: 0; }}
  table.lec-table tr td:last-child, table.lec-table tr th:last-child {{ border-right: 0; }}
  .figure {{ margin: 14px 0; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; overflow: hidden; }}
  .figure img {{ display: block; width: 100%; max-height: 460px; object-fit: contain; background: #fff; }}
  .figure figcaption {{ padding: 8px 12px; font-size: 13px; color: #4b5563; border-top: 1px solid #e5e7eb; line-height: 1.6; }}
  .figure .source {{ display: block; color: #6b7280; margin-top: 2px; }}
  details {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 14px; margin: 10px 0; background: #fafafa; }}
  details summary {{ cursor: pointer; font-weight: 600; font-size: 14px; color: #374151; }}
  details .rich {{ margin-top: 10px; }}
  .ex {{ border-top: 1px dashed #e5e7eb; margin-top: 14px; padding-top: 8px; }}
  .ex-in {{ width: 100%; box-sizing: border-box; min-height: 88px; padding: 8px 10px; font: inherit; font-size: 14px;
            border: 1.5px solid #d1d5db; border-radius: 8px; resize: vertical; }}
  .ex-in:focus {{ outline: none; border-color: #3b82f6; }}
  .ex-go {{ margin-top: 8px; padding: 6px 16px; font-size: 13px; border: none; border-radius: 8px; background: #2563eb; color: #fff; cursor: pointer; }}
  .ex-go:disabled {{ background: #93c5fd; cursor: default; }}
  .ex-opts {{ margin: 8px 0; }}
  .ex-opts.judge {{ display: flex; gap: 10px; }}
  .ex-opt {{ display: block; width: 100%; text-align: left; margin: 6px 0; padding: 8px 12px; font-size: 14px;
             line-height: 1.6; border: 1.5px solid #d1d5db; border-radius: 8px; background: #fff; cursor: pointer; }}
  .ex-opts.judge .ex-opt {{ flex: 1; text-align: center; font-weight: 600; }}
  .ex-opt:hover:not(:disabled) {{ border-color: #3b82f6; background: #f8fafc; }}
  .ex-opt:disabled {{ cursor: default; }}
  .ex-opt.picked {{ border-color: #2563eb; background: #eff6ff; }}
  .ex-opt.right {{ border-color: #16a34a; background: #f0fdf4; }}
  .ex-opt.wrong {{ border-color: #ef4444; background: #fef2f2; }}
  .ex-opt.missed {{ border-color: #16a34a; border-style: dashed; background: #f0fdf4; }}
  .ex-opt.dim {{ opacity: .55; }}
  .ex-vd {{ display: none; margin-top: 10px; padding: 8px 12px; border-radius: 8px; font-size: 14px; }}
  .ex-vd.ok {{ background: #f0fdf4; border: 1px solid #86efac; color: #14532d; }}
  .ex-vd.miss {{ background: #fffbeb; border: 1px solid #fcd34d; color: #92400e; }}
  .ex-sol {{ display: none; margin-top: 10px; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 14px; background: #fafafa; }}
  .ex-sol-h {{ font-weight: 600; font-size: 14px; color: #374151; margin-bottom: 6px; }}
  .ex-sg {{ display: none; margin-top: 10px; font-size: 13px; color: #6b7280; }}
  .ex-sg button {{ margin-left: 6px; padding: 4px 12px; border-radius: 99px; border: 1px solid #d1d5db; background: #fff; cursor: pointer; font-size: 13px; }}
  .ex-sg button.sel {{ background: #2563eb; color: #fff; border-color: #2563eb; }}
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
<div class="meta">《{textbook}》{chapter} ｜ {n} 个知识点 ｜ 生成于 {date} ｜ {practice_note}</div>
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

// Interactive examples: attempt -> grade -> reveal solution. Types: single / multi / judge / text.
function normAns(s) {
  return (s || "").replace(/\\s+/g, "")
    .replace(/，/g, ",").replace(/；/g, ";").replace(/：/g, ":")
    .replace(/[（]/g, "(").replace(/[）]/g, ")").replace(/＝/g, "=").toLowerCase();
}
const L = i => String.fromCharCode(65 + i);
document.querySelectorAll(".ex").forEach(ex => {
  const type = ex.dataset.extype || "text";
  const vd = ex.querySelector(".ex-vd"), sol = ex.querySelector(".ex-sol"), sg = ex.querySelector(".ex-sg");
  let ans = null;
  try { ans = JSON.parse(ex.dataset.ans || "null"); } catch (e) {}
  const verdict = (ok, msg) => { vd.style.display = "block"; vd.className = "ex-vd " + (ok ? "ok" : "miss"); vd.textContent = msg; };
  const reveal = () => { sol.style.display = "block"; if (sg) sg.style.display = "block"; };

  if (type === "single" || type === "judge") {
    const opts = [...ex.querySelectorAll(".ex-opt")];
    opts.forEach(b => b.addEventListener("click", () => {
      if (opts.some(o => o.disabled)) return;
      const pick = +b.dataset.i, ok = pick === ans;
      opts.forEach(o => {
        o.disabled = true;
        const i = +o.dataset.i;
        o.classList.add(i === ans ? "right" : (i === pick ? "wrong" : "dim"));
      });
      const correctTxt = type === "judge" ? (ans === 0 ? "正确" : "错误") : L(ans);
      verdict(ok, ok ? "✓ 回答正确" : "✗ 回答错误（正确答案：" + correctTxt + "）");
      reveal();
    }));
  } else if (type === "multi") {
    const opts = [...ex.querySelectorAll(".ex-opt")], go = ex.querySelector(".ex-go"), sel = new Set();
    opts.forEach(b => b.addEventListener("click", () => {
      if (go.disabled) return;
      const i = +b.dataset.i;
      if (sel.has(i)) { sel.delete(i); b.classList.remove("picked"); }
      else { sel.add(i); b.classList.add("picked"); }
    }));
    go.addEventListener("click", () => {
      const want = new Set(ans || []), picks = [...sel];
      const wrong = picks.some(i => !want.has(i)), allRight = picks.length === want.size && !wrong;
      opts.forEach(o => {
        o.disabled = true; o.classList.remove("picked");
        const i = +o.dataset.i, isAns = want.has(i), isPick = sel.has(i);
        o.classList.add(isAns && isPick ? "right" : (!isAns && isPick ? "wrong" : (isAns ? "missed" : "dim")));
      });
      go.disabled = true;
      verdict(allRight, allRight ? "✓ 全部正确" : "✗ 未全对（正确答案：" + [...want].sort((a, b) => a - b).map(L).join("、") + "）");
      reveal();
    });
  } else {  // text
    const go = ex.querySelector(".ex-go"), inp = ex.querySelector(".ex-in");
    const list = Array.isArray(ans) ? ans : (ans ? [ans] : []);
    go.addEventListener("click", () => {
      const user = normAns(inp.value);
      if (list.length && user) {
        const hit = list.some(a => normAns(a) === user);
        verdict(hit, hit
          ? "✓ 最终答案正确（参考：" + list[0] + "）。展开解答核对步骤。"
          : "✗ 与参考最终答案不一致（参考：" + list[0] + "）。对照解答看看哪一步出了问题。");
      } else if (list.length && !user) {
        verdict(false, "你还没作答。参考最终答案：" + list[0]);
      }
      go.disabled = true; inp.readOnly = true; reveal();
    });
  }
  if (sg) sg.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    sg.querySelectorAll("button").forEach(x => x.classList.remove("sel"));
    b.classList.add("sel");
  }));
});
</script>
</body>
</html>
"""


def esc(s):
    return html_mod.escape(str(s or ""), quote=False)


def field(lead, text):
    return f'<div class="field"><span class="lead">{lead}</span><div class="rich">{render_rich(text)}</div></div>'


def render_html_figures(figures):
    out = []
    for fig in figures:
        path = html_mod.escape(str(fig.get("path", "")), quote=True)
        alt = html_mod.escape(str(fig.get("alt") or fig.get("caption") or "讲解配图"), quote=True)
        caption = esc(fig.get("caption"))
        source = esc(fig.get("source"))
        source_html = f'<span class="source">{source}</span>' if source else ""
        out.append(
            f'<figure class="figure"><img src="{path}" alt="{alt}" loading="lazy">'
            f'<figcaption>{caption}{source_html}</figcaption></figure>'
        )
    return "".join(out)


def render_html(data):
    mode = data["mode"]
    mode_label = "深入讲解" if mode == "deep" else "考试速通"
    ex_count = example_count(data)
    practice_note = f"例题 {ex_count} 道 ｜ 例题请先作答，提交后批改并展开解答" if ex_count else "本节按考频未配置例题，重点看讲解与易错辨析"
    toc = "".join(
        f'<a href="#p-{esc(p["id"])}">{esc(p["id"])} {esc(p["name"])}'
        f'{" ⭐" if p.get("importance") == "高" else ""}</a>'
        for p in data["points"])
    out = [HTML_HEAD.format(
        title=f"{data['section']} · 讲义", section=esc(data["section"]),
        textbook=esc(data["textbook"]), chapter=esc(data["chapter_title"]),
        n=len(data["points"]), date=datetime.date.today().isoformat(),
        toc=toc, mode_label=mode_label, practice_note=esc(practice_note))]
    for p in data["points"]:
        star = " ⭐" if p.get("importance") == "高" else ""
        out.append(f'<section class="point" id="p-{esc(p["id"])}">')
        out.append(f'<h2>{esc(p["id"])} {esc(p["name"])}{star}</h2>')
        if p.get("exam_focus"):
            out.append(f'<div class="box info">📌 <div class="rich">{render_rich(p["exam_focus"])}</div></div>')
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
        if figure_list(p):
            out.append(render_html_figures(figure_list(p)))
        exs = example_list(p)
        TYPE_LABEL = {"single": "单选", "multi": "多选", "judge": "判断", "text": ""}
        for n, ex in enumerate(exs, 1):
            base = f"例题{n}" if len(exs) > 1 else "例题"
            etype = ex.get("type", "text")
            tlabel = TYPE_LABEL.get(etype, "")
            head = f"{base}（{tlabel}）" if tlabel else base
            if etype == "single":
                ans_data = json.dumps(ex.get("answer"))
            elif etype == "judge":
                ans_data = json.dumps(0 if ex.get("answer") is True else 1)
            elif etype == "multi":
                ans_data = json.dumps(sorted(ex.get("answer") or []))
            else:
                a = ex.get("answer")
                ans_data = json.dumps(a if isinstance(a, list) else ([a] if a else []), ensure_ascii=False)
            out.append(f'<div class="ex" data-extype="{etype}" data-ans="{html_mod.escape(ans_data, quote=True)}">')
            out.append(f'<div class="field"><span class="lead">{head}</span>'
                       f'<div class="rich">{render_rich(ex["problem"])}</div></div>')
            if etype in ("single", "multi"):
                out.append('<div class="ex-opts">')
                for i, o in enumerate(ex.get("options") or []):
                    out.append(f'<button class="ex-opt" data-i="{i}">{chr(65 + i)}. {render_inline_rich(o)}</button>')
                out.append('</div>')
                if etype == "multi":
                    out.append('<div class="hint" style="font-size:12px;color:#6b7280">多选：选齐后点确认</div>'
                               '<div><button class="ex-go">确认作答</button></div>')
            elif etype == "judge":
                out.append('<div class="ex-opts judge">'
                           '<button class="ex-opt" data-i="0">正确</button>'
                           '<button class="ex-opt" data-i="1">错误</button></div>')
            else:
                out.append('<textarea class="ex-in" placeholder="先自己作答，写出关键步骤或最终答案…"></textarea>')
                out.append('<div><button class="ex-go">提交批改</button></div>')
            out.append('<div class="ex-vd"></div>')
            out.append(f'<div class="ex-sol"><div class="ex-sol-h">📖 参考解答（{base}）</div>'
                       f'<div class="rich">{render_rich(ex["solution"])}</div></div>')
            if etype == "text":
                out.append('<div class="ex-sg">对照参考给自己打分：'
                           '<button data-g="right">完全正确</button>'
                           '<button data-g="part">部分正确</button>'
                           '<button data-g="no">还不太会</button></div>')
            out.append('</div>')
        if p.get("pitfalls"):
            out.append(f'<div class="box warn">⚠️ <b>易错辨析</b> <div class="rich">{render_rich(p["pitfalls"])}</div></div>')
        if p.get("memory_hook"):
            out.append(f'<div class="box tip">💡 <b>记忆抓手</b> <div class="rich">{render_rich(p["memory_hook"])}</div></div>')
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
