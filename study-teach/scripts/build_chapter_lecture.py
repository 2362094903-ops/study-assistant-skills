#!/usr/bin/env python3
"""Aggregate per-point or per-section lecture JSON files into a combined chapter-level HTML
and/or Obsidian Markdown file.

Why: the learner works through one knowledge point at a time (build_lecture.py),
but a chapter is complete only after one main chapter file is built. This script
reads all unit JSON files (the source of truth), groups point files by section,
and reuses the exact rendering pipeline from build_lecture.py.

Usage:
  python3 build_chapter_lecture.py lessons/chapter-03/                         # both formats
  python3 build_chapter_lecture.py lessons/chapter-03/ --format obsidian       # markdown only
  python3 build_chapter_lecture.py lessons/chapter-03/ --format html           # html only
  python3 build_chapter_lecture.py lessons/chapter-03/ -o lessons/chapter-03/  # output dir (default: same)
  python3 build_chapter_lecture.py internal/lessons/chapter-03/ --format html --publish <study-dir>
"""

import argparse
import datetime
import html as html_mod
import json
import pathlib
import re
import shutil
import sys

# Import the rendering pipeline from the sibling build_lecture.py
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_lecture import (
    render_rich, render_inline_rich, render_html_figures, render_html_points,
    field, html_source, esc, sanitize, validate,
    example_list, figure_list, example_count,
    IMPORTANCE_MARK,
)


# ---------------------------------------------------------------------------
# Natural sort key for section numbers (1.1, 1.2, …, 1.10, 1.11)
# ---------------------------------------------------------------------------
def _section_sort_key(section_str):
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r'(\d+)', section_str)]


# ---------------------------------------------------------------------------
# Load, validate, and group all unit JSONs in a chapter directory
# ---------------------------------------------------------------------------
def load_section_jsons(chapter_dir):
    """Load unit JSON files, group them by section, and return merged sections.

    New workspaces normally have one point per JSON. Legacy section-level JSON
    files remain supported. Duplicate point ids are rejected.
    """
    json_files = sorted(chapter_dir.glob("*.json"),
                        key=lambda f: _section_sort_key(f.stem))
    if not json_files:
        sys.exit(f"未找到讲义 JSON 文件：{chapter_dir}/*.json")
    units = []
    for jf in json_files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        data.setdefault("mode", "deep")
        errs = validate(data)
        if errs:
            sys.exit(f"{jf.name}: validation failed:\n  " + "\n  ".join(errs))
        units.append((data, jf))

    units.sort(key=lambda s: (
        _section_sort_key(s[0].get("section", "")),
        _section_sort_key(s[0].get("points", [{}])[0].get("id", "")),
        s[1].name,
    ))
    grouped = {}
    order = []
    seen_points = {}
    for data, jf in units:
        section = data["section"]
        if section not in grouped:
            grouped[section] = (dict(data, points=[]), jf)
            order.append(section)
        merged, first_path = grouped[section]
        for field_name in ("textbook", "chapter_id", "chapter_title", "mode"):
            if merged.get(field_name) != data.get(field_name):
                sys.exit(
                    f"{jf.name}: section '{section}' has inconsistent {field_name}: "
                    f"{data.get(field_name)!r} != {merged.get(field_name)!r}"
                )
        for point in data["points"]:
            pid = point["id"]
            if pid in seen_points:
                sys.exit(f"duplicate point id {pid}: {seen_points[pid].name} and {jf.name}")
            seen_points[pid] = jf
            merged["points"].append(point)
        grouped[section] = (merged, first_path)

    sections = [grouped[s] for s in order]
    for data, _ in sections:
        data["points"].sort(key=lambda p: _section_sort_key(p["id"]))
    return sections


# ---------------------------------------------------------------------------
# Chapter-level Obsidian Markdown
# ---------------------------------------------------------------------------
def render_chapter_markdown(sections):
    first = sections[0][0]
    textbook = first["textbook"]
    chapter_id = first["chapter_id"]
    chapter_title = first["chapter_title"]
    total_points = sum(len(data["points"]) for data, _ in sections)
    today = datetime.date.today().isoformat()

    lines = [
        "---",
        f"textbook: {textbook}",
        f"chapter: {chapter_id}",
        f"chapter_title: \"{chapter_title}\"",
        f"sections: [{', '.join('"' + data['section'] + '"' for data, _ in sections)}]",
        f"points: {total_points}",
        f"generated: {today}",
        "---",
        "",
        f"# {chapter_title}",
        "",
        f"> 《{textbook}》 ｜ {len(sections)} 节 ｜ {total_points} 个知识点 ｜ 生成于 {today}",
        "",
    ]

    MODE_LABEL = {"deep": "深入讲解", "speedrun": "考试速通"}
    for data, _ in sections:
        mode = data["mode"]
        mode_label = MODE_LABEL.get(mode, "深入讲解")
        lines.append(f"## {data['section']} `[{mode_label}]`")
        lines.append("")
        for p in data["points"]:
            star = IMPORTANCE_MARK.get(p.get("importance", "中"), "")
            lines.append(f"### {p['id']} {p['name']} {star}".rstrip())
            lines.append("")
            src_line = _markdown_source_line(p)
            if src_line:
                lines.append(src_line)
                lines.append("")
            if p.get("exam_focus"):
                lines.append(_quote_block(p["exam_focus"], "info"))
                lines.append("")
            if mode == "deep":
                if p.get("textbook_excerpt"):
                    lines.append(_quote_block("**教材原文**\n" + p["textbook_excerpt"], "quote"))
                    lines.append("")
                if p.get("intuition"):
                    lines.append(f"**直观理解**　{p['intuition']}")
                    lines.append("")
                if p.get("formal"):
                    lines.append(f"**严谨表述**　{p['formal']}")
                    lines.append("")
            else:
                if p.get("key_point"):
                    lines.append(f"**核心结论**　{p['key_point']}")
                    lines.append("")
                if p.get("method"):
                    lines.append(_quote_block("**解题思维**\n" + p["method"], "example"))
                    lines.append("")
            # Figures
            figs = _fig_list(p)
            if figs:
                for fig in figs:
                    path = fig.get("path", "")
                    caption = fig.get("caption") or ""
                    source = fig.get("source") or ""
                    lines.append(f"![{caption}]({path})")
                    if caption:
                        lines.append(f"*{caption}*")
                    if source:
                        lines.append(f"（{source}）")
                    lines.append("")
            # Examples
            exs = _ex_list(p)
            TYPE_LABEL = {"single": "单选", "multi": "多选", "judge": "判断", "text": ""}
            for n, ex in enumerate(exs, 1):
                base = f"例题{n}" if len(exs) > 1 else "例题"
                etype = ex.get("type", "text")
                tlabel = TYPE_LABEL.get(etype, "")
                head = f"{base}（{tlabel}）" if tlabel else base
                lines.append(f"**{head}**　{ex['problem']}")
                ex_src = _markdown_source_line(ex)
                if ex_src:
                    lines.append(ex_src)
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
                lines.append(_quote_block("**易错辨析**　" + p["pitfalls"], "warning"))
                lines.append("")
            if p.get("memory_hook"):
                lines.append(_quote_block("**记忆抓手**　" + p["memory_hook"], "tip"))
                lines.append("")
            if p.get("links"):
                lines.append(f"*关联知识点：{'、'.join(p['links'])}*")
                lines.append("")
    return "\n".join(lines)


# ---- Markdown helpers (mirror build_lecture.py) ----
def _markdown_source_line(obj):
    src = obj.get("source_ref") or ""
    return f"> 📎 {src.strip()}" if src.strip() else ""


def _quote_block(text, callout, foldable=False):
    body = "\n".join("> " + line for line in text.strip().splitlines())
    return f"> [!{callout}]{'-' if foldable else ''}\n{body}"


def _fig_list(p):
    """Normalize figures/figures/images to a list (same as build_lecture.figure_list)."""
    return figure_list(p)


def _ex_list(p):
    """Normalize example/examples to a list (same as build_lecture.example_list)."""
    return example_list(p)


# ---------------------------------------------------------------------------
# Chapter-level Interactive HTML
# ---------------------------------------------------------------------------
CHAPTER_HTML_HEAD = """<!DOCTYPE html>
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
  #toc h2 {{ font-size: 14px; color: #374151; margin: 0 0 10px; }}
  #toc .toc-sec {{ display: flex; align-items: center; gap: 4px; padding: 8px 4px 4px;
                  font-weight: 600; font-size: 12px; color: #4b5563; line-height: 1.5; }}
  #toc .toc-sec + .toc-sec {{ border-top: 1px solid #e5e7eb; margin-top: 6px; padding-top: 10px; }}
  #toc .modetag-mini {{ display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 99px;
                        background: #eef2ff; color: #4338ca; font-weight: 400; line-height: 1.6; }}
  #toc a {{ display: block; padding: 3px 8px; margin-left: 4px; color: #374151; text-decoration: none;
            border-radius: 6px; line-height: 1.5; }}
  #toc a:hover {{ background: #eef2ff; }}
  #toc a.done {{ color: #16a34a; }}
  main {{ flex: 1; padding: 28px 36px 80px; min-width: 0; }}
  h1 {{ font-size: 22px; }}
  .meta {{ color: #6b7280; font-size: 13px; margin-bottom: 8px; }}
  .modetag {{ display:inline-block; font-size:12px; padding:2px 10px; border-radius:99px;
             background:#eef2ff; color:#4338ca; margin-left:6px; }}
  #mjwarn {{ display: none; background: #fef3c7; border: 1px solid #fcd34d; padding: 8px 12px; border-radius: 8px; font-size: 13px; }}
  div.ch-sec {{ margin-bottom: 40px; padding-bottom: 24px; border-bottom: 2px solid #e5e7eb; }}
  div.ch-sec:last-child {{ border-bottom: none; }}
  h2.sec-title {{ font-size: 18px; display: flex; align-items: center; gap: 8px; margin: 0 0 16px; }}
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
  .source-ref, .ex-source {{ color: #6b7280; font-size: 12px; line-height: 1.6; }}
  .source-ref {{ margin: -2px 0 8px; }}
  .ex-source {{ margin: 4px 0 6px; }}
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
<nav id="toc"><h2>{chapter_title}</h2>{toc}</nav>
<main>
<h1>{chapter_title}</h1>
<div class="meta">《{textbook}》 ｜ {sec_count} 节 ｜ {total_points} 个知识点 ｜ 生成于 {date} ｜ {practice_note}</div>
<div id="mjwarn">⚠️ 离线状态：公式渲染（MathJax）加载失败，以下公式显示为 LaTeX 源码，含义不受影响。</div>
"""

CHAPTER_HTML_TAIL = """</main></div>
<script>
const KEY = "lecture-done-{chapter_key}-";
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


def render_chapter_html(sections):
    first = sections[0][0]
    textbook = first["textbook"]
    chapter_id = first["chapter_id"]
    chapter_title = first["chapter_title"]
    total_points = sum(len(data["points"]) for data, _ in sections)
    total_examples = sum(example_count(data) for data, _ in sections)
    today = datetime.date.today().isoformat()

    practice_note = (f"全章例题 {total_examples} 道 ｜ 先作答再展开解答"
                     if total_examples else "本讲尚未配置例题，重点看讲解与易错辨析")

    # Build multi-level TOC: section groups with nested point links
    MODE_LABEL = {"deep": "深入讲解", "speedrun": "考试速通"}
    toc_parts = []
    for data, _ in sections:
        mode = data["mode"]
        mode_label = MODE_LABEL.get(mode, "深入讲解")
        toc_parts.append(
            f'<div class="toc-sec">{esc(data["section"])}'
            f'<span class="modetag-mini">{mode_label}</span></div>')
        for p in data["points"]:
            star = " ⭐" if p.get("importance") == "高" else ""
            toc_parts.append(
                f'<a href="#p-{esc(p["id"])}">{esc(p["id"])} {esc(p["name"])}{star}</a>')
    toc = "\n".join(toc_parts)

    # Chapter header
    out = [CHAPTER_HTML_HEAD.format(
        title=f"{chapter_title} · 讲义",
        chapter_title=esc(chapter_title),
        textbook=esc(textbook),
        sec_count=len(sections),
        total_points=total_points,
        date=today,
        toc=toc,
        practice_note=esc(practice_note))]

    # Each section as a div.ch-sec
    for data, _ in sections:
        mode = data["mode"]
        mode_label = MODE_LABEL.get(mode, "深入讲解")
        out.append(f'<div class="ch-sec" id="sec-{esc(sanitize(data["section"]))}">')
        out.append(f'<h2 class="sec-title">{esc(data["section"])}'
                   f'<span class="modetag">{mode_label}</span></h2>')
        out.append(render_html_points(data["points"], mode))
        out.append('</div>')

    out.append(CHAPTER_HTML_TAIL.replace("{chapter_key}", f"chapter-{chapter_id}"))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter_dir", help="path to lessons/chapter-XX/ containing point/section JSON files")
    ap.add_argument("--format", choices=["obsidian", "html", "both"], default="both")
    ap.add_argument("-o", "--out", help="output directory (default: same as chapter_dir)")
    ap.add_argument("--publish", help="study-dir; also write main chapter HTML to open/chapters/")
    args = ap.parse_args()

    chapter_dir = pathlib.Path(args.chapter_dir)
    if not chapter_dir.is_dir():
        sys.exit(f"目录不存在：{chapter_dir}")

    sections = load_section_jsons(chapter_dir)

    first = sections[0][0]
    chapter_id = first["chapter_id"]
    out_dir = pathlib.Path(args.out) if args.out else chapter_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"chapter-{chapter_id:02d}"

    if args.format in ("obsidian", "both"):
        out_path = out_dir / f"{stem}.md"
        out_path.write_text(render_chapter_markdown(sections), encoding="utf-8")
        print(f"generated {out_path}")

    if args.format in ("html", "both"):
        html_text = render_chapter_html(sections)
        out_path = out_dir / f"{stem}.html"
        out_path.write_text(html_text, encoding="utf-8")
        print(f"generated {out_path}")
        if args.publish:
            public_dir = pathlib.Path(args.publish) / "open" / "chapters"
            public_dir.mkdir(parents=True, exist_ok=True)
            public_path = public_dir / f"{stem}.html"
            public_asset_dir = public_dir / "assets" / stem
            source_asset_dir = chapter_dir / "assets"
            public_html = html_text.replace('src="assets/', f'src="assets/{stem}/')
            public_path.write_text(public_html, encoding="utf-8")
            if source_asset_dir.exists():
                shutil.copytree(source_asset_dir, public_asset_dir, dirs_exist_ok=True)
            print(f"generated {public_path}")


if __name__ == "__main__":
    main()
