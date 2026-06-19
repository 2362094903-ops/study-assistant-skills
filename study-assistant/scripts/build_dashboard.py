#!/usr/bin/env python3
"""Build the learner dashboard and compact session digest.

The current workspace layout keeps user-facing files in open/ and internal
state in internal/.  The script still reads legacy workspaces that keep
knowledge.json, progress.json, lessons/, quizzes/, and reports/ at the root.

Usage:
  python3 build_dashboard.py <study-dir>                # digest + open/dashboard.html
  python3 build_dashboard.py <study-dir> --digest-only  # digest only, for resume
"""
import argparse
import datetime
import html as html_mod
import json
import os
import pathlib
import re
import sys

BUCKETS = [
    ("未学", lambda p: p["mastery"] == 0 and p["status"] == "未学", "#9ca3af"),
    ("薄弱", lambda p: 1 <= p["mastery"] <= 2, "#ef4444"),
    ("基本", lambda p: p["mastery"] == 3, "#f59e0b"),
    ("熟练", lambda p: p["mastery"] == 4, "#84cc16"),
    ("精通", lambda p: p["mastery"] >= 5, "#16a34a"),
]


def state_dir(study_dir):
    internal = study_dir / "internal" / "state"
    if (internal / "knowledge.json").exists() or (study_dir / "internal").exists():
        return internal
    return study_dir


def data_dir(study_dir, name):
    internal = study_dir / "internal" / name
    legacy = study_dir / name
    if internal.exists() or (study_dir / "internal").exists():
        return internal
    return legacy


def public_dir(study_dir):
    return study_dir / "open"


def question_bank_path(study_dir):
    modern = study_dir / "question-bank" / "question-bank.json"
    legacy = study_dir / "question-bank.json"
    return legacy if legacy.exists() and not modern.exists() else modern


def bucket_of(p):
    for name, fn, _ in BUCKETS[1:]:
        if fn(p):
            return name
    return "未学"


def flatten(knowledge):
    pts = []
    for ch in knowledge.get("chapters", []):
        for sec in ch.get("sections", []):
            for p in sec.get("points", []):
                q = dict(p)
                q["chapter_id"], q["chapter"] = ch["id"], ch["title"]
                q["section"] = sec["title"]
                pts.append(q)
    return pts


def load_history(path):
    events = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return sorted(events, key=lambda e: e.get("date", ""))


def trend_series(points, events):
    if not events:
        return []
    state = {p["id"]: 0 for p in points}
    series, n = [], max(len(state), 1)
    by_date = {}
    for e in events:
        if e.get("point") in state and isinstance(e.get("mastery"), (int, float)):
            state[e["point"]] = e["mastery"]
            by_date[e.get("date", "?")] = sum(state.values()) / n
    for d, avg in by_date.items():
        series.append((d, round(avg, 2)))
    return series


def weak_points(points):
    weak = [
        p for p in points
        if p["importance"] == "高"
        and p["status"] in ("已测验", "已检验")
        and 1 <= p["mastery"] <= 2
    ]
    weak.sort(key=lambda p: (p["mastery"], p["id"]))
    return weak[:10]


def count_pending_mistakes(path):
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    entries = len(re.findall(r"^## ", text, re.M))
    reviewed = len(re.findall(r"复盘通过", text))
    return max(entries - reviewed, 0)


def count_bank_entries(path):
    if not path.exists():
        return 0
    try:
        return len(json.loads(path.read_text(encoding="utf-8")).get("entries", []))
    except Exception:
        return 0


def esc(s):
    return html_mod.escape(str(s or ""), quote=False)


def rel_href(from_dir, target):
    try:
        return pathlib.Path(os.path.relpath(target, from_dir)).as_posix()
    except ValueError:
        return target.as_posix()


def scan_links(study_dir, dashboard_path):
    base = dashboard_path.parent
    chapters = {}
    chapter_candidates = [
        public_dir(study_dir) / "chapters",
        data_dir(study_dir, "lessons"),
        study_dir / "lessons",
    ]
    for root in chapter_candidates:
        if not root.exists():
            continue
        for path in sorted(root.glob("chapter-*/chapter-*.html")) + sorted(root.glob("chapter-*.html")):
            m = re.search(r"chapter-(\d+)\.html$", path.name)
            if m:
                chapters.setdefault(int(m.group(1)), rel_href(base, path))

    quizzes = []
    seen_quiz_names = set()
    for root in [public_dir(study_dir) / "quizzes", data_dir(study_dir, "quizzes"), study_dir / "quizzes"]:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.html")):
            if path.name in seen_quiz_names:
                continue
            seen_quiz_names.add(path.name)
            quizzes.append((path.stem, rel_href(base, path)))
    quizzes = quizzes[-12:]

    reports = []
    audit_status = {}
    for root in [data_dir(study_dir, "reports"), study_dir / "reports"]:
        if not root.exists():
            continue
        for path in sorted(root.glob("chapter-*-audit.json")):
            m = re.search(r"chapter-(\d+)-audit\.json$", path.name)
            if not m:
                continue
            cid = int(m.group(1))
            if cid in audit_status:
                continue
            try:
                audit_status[cid] = json.loads(
                    path.read_text(encoding="utf-8")
                ).get("status", "")
            except Exception:
                audit_status[cid] = "invalid"
        for path in sorted(root.glob("*audit*.md"))[-8:]:
            reports.append((path.stem, rel_href(base, path)))
    return chapters, quizzes, reports, audit_status


def write_update_command(study_dir):
    out_dir = public_dir(study_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    script = pathlib.Path(__file__).resolve()
    cmd = out_dir / "update_dashboard.command"
    cmd.write_text(f"""#!/bin/zsh
set -e
SCRIPT_DIR="${{0:A:h}}"
STUDY_DIR="${{SCRIPT_DIR:h}}"
python3 "{script}" "$STUDY_DIR"
echo
echo "仪表盘已更新：$SCRIPT_DIR/dashboard.html"
echo "按任意键关闭..."
read -k 1
""", encoding="utf-8")
    cmd.chmod(0o755)
    return cmd


def build_digest(knowledge, points, progress, events, pending_mistakes, bank_entries):
    n = len(points)
    counts = {name: sum(1 for p in points if bucket_of(p) == name) for name, _, _ in BUCKETS}
    avg = round(sum(p["mastery"] for p in points) / n, 2) if n else 0
    lines = [
        f"# 学习摘要：{knowledge.get('textbook','')}（{datetime.date.today().isoformat()} 自动生成）",
        "",
        f"- 知识点 {n} 个：未学 {counts['未学']} ｜ 薄弱 {counts['薄弱']} ｜ 基本 {counts['基本']} ｜ 熟练 {counts['熟练']} ｜ 精通 {counts['精通']} ｜ 平均掌握 {avg}/5",
        f"- 错题本待复盘：{pending_mistakes} 条 ｜ 全局题库：{bank_entries} 题",
        "- 常用入口：open/dashboard.html；双击 open/update_dashboard.command 可刷新仪表盘",
    ]
    if progress:
        lines.append(
            f"- 上次位置：第{progress.get('current_chapter','?')}章 {progress.get('current_point','?')} ｜ "
            f"建议下一步：{progress.get('next_action','?')} ｜ 讲义格式：{progress.get('lecture_format','未选')}"
        )
    lines.append("")
    lines.append("## 各章进度")
    by_ch = {}
    for p in points:
        by_ch.setdefault((p["chapter_id"], p["chapter"]), []).append(p)
    for (cid, title), pts in sorted(by_ch.items()):
        cavg = round(sum(p["mastery"] for p in pts) / len(pts), 2)
        unstudied = sum(1 for p in pts if bucket_of(p) == "未学")
        lines.append(f"- {title}：{len(pts)} 点，平均 {cavg}/5，未掌握（含已讲未测）{unstudied}")
    weak = weak_points(points)
    if weak:
        lines.append("")
        lines.append("## 高优先回炉（重要度高 × 掌握≤2）")
        for p in weak:
            note = f"（{p['note']}）" if p.get("note") else ""
            lines.append(f"- {p['id']} {p['name']}：掌握 {p['mastery']}/5，{p['status']}{note}")
    if events:
        lines.append("")
        lines.append("## 最近活动")
        for e in events[-5:]:
            lines.append(
                f"- {e.get('date','?')} {e.get('event','?')} {e.get('point','')}："
                f"掌握 {e.get('prev','?')}→{e.get('mastery','?')} {e.get('note','')}".rstrip()
            )
    return "\n".join(lines) + "\n"


def stacked_bar(pts, width=100):
    n = len(pts) or 1
    segs = []
    for name, _, color in BUCKETS:
        c = sum(1 for p in pts if bucket_of(p) == name)
        if c:
            segs.append(
                f'<span title="{name} {c}" style="display:inline-block;height:14px;'
                f'width:{c / n * width:.1f}%;background:{color}"></span>'
            )
    return f'<div style="font-size:0;border-radius:4px;overflow:hidden;background:#eee">{"".join(segs)}</div>'


def trend_svg(series):
    if len(series) < 2:
        return "<p class='hint'>掌握度变化不足两次，暂无趋势图。</p>"
    w, h, pad = 640, 140, 24
    xs = [pad + i * (w - 2 * pad) / (len(series) - 1) for i in range(len(series))]
    ys = [h - pad - (v / 5) * (h - 2 * pad) for _, v in series]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#2563eb"><title>{esc(d)}: {v}</title></circle>'
        for (d, v), x, y in zip(series, xs, ys)
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:680px">'
        f'<line x1="{pad}" y1="{h-pad}" x2="{w-pad}" y2="{h-pad}" stroke="#d1d5db"/>'
        f'<text x="{pad}" y="14" font-size="11" fill="#6b7280">平均掌握度走势（0-5）</text>'
        f'<polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="2"/>{dots}</svg>'
    )


def link_list(items, empty):
    if not items:
        return f"<p class='hint'>{empty}</p>"
    return "<ul class='links'>" + "".join(
        f'<li><a href="{esc(href)}">{esc(label)}</a></li>' for label, href in items
    ) + "</ul>"


def build_html(knowledge, points, progress, events, pending_mistakes, bank_entries, study_dir, dashboard_path):
    n = len(points)
    counts = {name: sum(1 for p in points if bucket_of(p) == name) for name, _, _ in BUCKETS}
    avg = round(sum(p["mastery"] for p in points) / n, 2) if n else 0
    good = counts["熟练"] + counts["精通"]
    chapter_links, quiz_links, audit_links, audit_status = scan_links(study_dir, dashboard_path)
    by_ch = {}
    for p in points:
        by_ch.setdefault((p["chapter_id"], p["chapter"]), []).append(p)
    chapter_parts = []
    for (c, t), pts in sorted(by_ch.items()):
        if c in chapter_links:
            main_link = f'<a href="{esc(chapter_links[c])}">打开整章讲义</a>'
            if audit_status.get(c) == "pass":
                completeness = '<span style="color:#15803d">已完成</span>'
            elif audit_status.get(c) == "blocked":
                completeness = '<span style="color:#b91c1c">需修改</span>'
            elif audit_status.get(c) == "invalid":
                completeness = '<span style="color:#b91c1c">审查文件异常</span>'
            else:
                completeness = '<span style="color:#a16207">待审查</span>'
        else:
            main_link = '<span class="hint">待合并</span>'
            completeness = '<span class="hint">待合并</span>'
        chapter_parts.append(
            f"<tr><td>{esc(t)}</td><td>{main_link}</td><td>{completeness}</td>"
            f"<td style='width:38%'>{stacked_bar(pts)}</td>"
            f"<td>{round(sum(p['mastery'] for p in pts)/len(pts),2)}/5</td><td>{len(pts)}</td></tr>"
        )
    chapter_rows = "".join(chapter_parts)
    weak = weak_points(points)
    weak_rows = "".join(
        f"<tr><td>{esc(p['id'])}</td><td>{esc(p['name'])}</td><td>{p['mastery']}/5</td>"
        f"<td>{esc(p['status'])}</td><td>{esc(p.get('note',''))}</td></tr>" for p in weak
    ) or "<tr><td colspan=5>暂无（要么还没开始测验，要么都掌握得不错）</td></tr>"
    activity = "".join(
        f"<li><b>{esc(e.get('date',''))}</b> ｜ {esc(e.get('event',''))} ｜ {esc(e.get('point',''))} "
        f"掌握 {esc(e.get('prev','?'))}→{esc(e.get('mastery','?'))} {esc(e.get('note',''))}</li>"
        for e in reversed(events[-12:])
    ) or "<li>暂无记录</li>"
    legend = " ".join(
        f'<span style="display:inline-block;width:10px;height:10px;background:{c};'
        f'border-radius:2px"></span>{name} {counts[name]}' for name, _, c in BUCKETS
    )
    command_href = esc(rel_href(dashboard_path.parent, public_dir(study_dir) / "update_dashboard.command"))
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>学习仪表盘 · {esc(knowledge.get('textbook',''))}</title>
<style>
:root {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
body {{ margin:0; background:#f5f5f2; color:#1f2937; }}
#wrap {{ max-width:920px; margin:0 auto; padding:28px 20px 60px; }}
h1 {{ font-size:20px; margin-bottom:4px; }} h2 {{ font-size:15px; margin:26px 0 10px; }}
.meta {{ color:#6b7280; font-size:13px; }}
.cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:18px 0; }}
.card {{ background:#fff; border:1px solid #e5e7eb; border-radius:8px; padding:14px 20px; flex:1; min-width:140px; }}
.card .v {{ font-size:24px; font-weight:700; }} .card .k {{ font-size:12px; color:#6b7280; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; background:#fff; }}
th,td {{ border:1px solid #e5e7eb; padding:7px 10px; text-align:left; }} th {{ background:#f9fafb; }}
ul {{ font-size:13px; line-height:1.9; }} .hint {{ color:#6b7280; font-size:13px; }}
.legend {{ font-size:12px; color:#4b5563; display:flex; gap:14px; align-items:center; flex-wrap:wrap; }}
a {{ color:#1d4ed8; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
.entry {{ background:#fff; border:1px solid #e5e7eb; border-radius:8px; padding:12px 16px; margin:10px 0; }}
</style></head><body><div id="wrap">
<h1>学习仪表盘 · {esc(knowledge.get('textbook',''))}</h1>
<div class="meta">更新于 {datetime.date.today().isoformat()} ｜ 双击 <a href="{command_href}">update_dashboard.command</a> 可一键刷新</div>
<div class="cards">
<div class="card"><div class="v">{n}</div><div class="k">知识点总数</div></div>
<div class="card"><div class="v">{avg}<span style="font-size:13px">/5</span></div><div class="k">平均掌握度</div></div>
<div class="card"><div class="v">{good}</div><div class="k">熟练及以上（{(good*100//n) if n else 0}%）</div></div>
<div class="card"><div class="v">{pending_mistakes}</div><div class="k">错题待复盘</div></div>
<div class="card"><div class="v">{bank_entries}</div><div class="k">全局题库</div></div>
</div>
<div class="legend">{legend}</div>
<div style="margin-top:8px">{stacked_bar(points)}</div>
<h2>常用入口</h2>
<div class="entry"><b>最近题目</b>{link_list(quiz_links, "还没有生成可打开的题目 HTML。")}</div>
<div class="entry"><b>审查报告</b>{link_list(audit_links, "还没有章节审查报告。")}</div>
<h2>各章进度</h2>
<table><tr><th>章节</th><th>主讲义</th><th>完整性</th><th>掌握度分布</th><th>平均</th><th>知识点</th></tr>{chapter_rows}</table>
<h2>掌握度走势</h2>
{trend_svg(trend_series(points, events))}
<h2>高优先回炉（重要度高 × 掌握 ≤ 2）</h2>
<table><tr><th>编号</th><th>知识点</th><th>掌握</th><th>状态</th><th>备注</th></tr>{weak_rows}</table>
<h2>最近活动</h2>
<ul>{activity}</ul>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("study_dir")
    ap.add_argument("--digest-only", action="store_true")
    args = ap.parse_args()
    d = pathlib.Path(args.study_dir)
    sdir = state_dir(d)

    kpath = sdir / "knowledge.json"
    if not kpath.exists():
        sys.exit(f"knowledge.json not found in {sdir}")
    knowledge = json.loads(kpath.read_text(encoding="utf-8"))
    points = flatten(knowledge)
    progress = {}
    if (sdir / "progress.json").exists():
        progress = json.loads((sdir / "progress.json").read_text(encoding="utf-8"))
    events = load_history(sdir / "history.jsonl")
    pending = 0
    for mistakes_path in (sdir / "mistakes.md", data_dir(d, "reports") / "mistakes.md", d / "mistakes.md"):
        if mistakes_path.exists():
            pending = count_pending_mistakes(mistakes_path)
            break
    bank_entries = count_bank_entries(question_bank_path(d))

    sdir.mkdir(parents=True, exist_ok=True)
    digest_path = sdir / "digest.md"
    digest_path.write_text(
        build_digest(knowledge, points, progress, events, pending, bank_entries),
        encoding="utf-8",
    )
    print(f"generated {digest_path}")

    cmd = write_update_command(d)
    if not args.digest_only:
        out = public_dir(d) / "dashboard.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            build_html(knowledge, points, progress, events, pending, bank_entries, d, out),
            encoding="utf-8",
        )
        print(f"generated {out}")
    print(f"generated {cmd}")


if __name__ == "__main__":
    main()
