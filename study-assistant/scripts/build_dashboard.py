#!/usr/bin/env python3
"""Build the mastery dashboard (dashboard.html for the learner) and the compact
session digest (digest.md for the model) from the study workspace.

Why: at the start of a new session the model should read digest.md ONLY —
a ~30-line summary — instead of parsing the whole knowledge.json, saving context.

Usage:
  python3 build_dashboard.py <study-dir>                # both outputs
  python3 build_dashboard.py <study-dir> --digest-only  # digest.md only (cheap, for resume)

Inputs: knowledge.json (required), progress.json, history.jsonl (optional,
one JSON object per line: {"date","point","event","mastery","prev","note"}),
mistakes.md (counted only).
Outputs: <study-dir>/dashboard.html, <study-dir>/digest.md
"""
import argparse
import datetime
import html as html_mod
import json
import pathlib
import re
import sys

BUCKETS = [("未学", lambda p: p["mastery"] == 0 and p["status"] == "未学", "#9ca3af"),
           ("薄弱", lambda p: 1 <= p["mastery"] <= 2, "#ef4444"),
           ("基本", lambda p: p["mastery"] == 3, "#f59e0b"),
           ("熟练", lambda p: p["mastery"] == 4, "#84cc16"),
           ("精通", lambda p: p["mastery"] >= 5, "#16a34a")]


def bucket_of(p):
    # 已讲解但 mastery 仍为 0 的点算"未学"之外的过渡态，按未学统计但单列提示
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
    """Replay history to get average mastery per event date."""
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
    # 只算"真正测过且得分低"的点：必须已测验/已检验且 mastery 1–2。
    # mastery 0 表示还没测（哪怕已讲解），不算薄弱，否则刚讲完的点会被误列为回炉项。
    weak = [p for p in points
            if p["importance"] == "高"
            and p["status"] in ("已测验", "已检验")
            and 1 <= p["mastery"] <= 2]
    weak.sort(key=lambda p: (p["mastery"], p["id"]))
    return weak[:10]


def count_pending_mistakes(path):
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    entries = len(re.findall(r"^## ", text, re.M))
    reviewed = len(re.findall(r"复盘通过", text))
    return max(entries - reviewed, 0)


def build_digest(knowledge, points, progress, events, pending_mistakes):
    n = len(points)
    counts = {name: sum(1 for p in points if bucket_of(p) == name) for name, _, _ in BUCKETS}
    avg = round(sum(p["mastery"] for p in points) / n, 2) if n else 0
    lines = [f"# 学习摘要：{knowledge.get('textbook','')}（{datetime.date.today().isoformat()} 自动生成，模型续学时只需读本文件）",
             "",
             f"- 知识点 {n} 个：未学 {counts['未学']} ｜ 薄弱 {counts['薄弱']} ｜ 基本 {counts['基本']} ｜ 熟练 {counts['熟练']} ｜ 精通 {counts['精通']} ｜ 平均掌握 {avg}/5",
             f"- 错题本待复盘：{pending_mistakes} 条"]
    if progress:
        lines.append(f"- 上次位置：第{progress.get('current_chapter','?')}章 {progress.get('current_point','?')} ｜ 建议下一步：{progress.get('next_action','?')} ｜ 讲义格式：{progress.get('lecture_format','未选')}")
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
            lines.append(f"- {e.get('date','?')} {e.get('event','?')} {e.get('point','')}：掌握 {e.get('prev','?')}→{e.get('mastery','?')} {e.get('note','')}".rstrip())
    return "\n".join(lines) + "\n"


def esc(s):
    return html_mod.escape(str(s or ""), quote=False)


def stacked_bar(pts, width=100):
    n = len(pts) or 1
    segs = []
    for name, _, color in BUCKETS:
        c = sum(1 for p in pts if bucket_of(p) == name)
        if c:
            segs.append(f'<span title="{name} {c}" style="display:inline-block;height:14px;'
                        f'width:{c / n * width:.1f}%;background:{color}"></span>')
    return f'<div style="font-size:0;border-radius:4px;overflow:hidden;background:#eee">{"".join(segs)}</div>'


def trend_svg(series):
    if len(series) < 2:
        return "<p class='hint'>掌握度变化不足两次，暂无趋势图。</p>"
    w, h, pad = 640, 140, 24
    xs = [pad + i * (w - 2 * pad) / (len(series) - 1) for i in range(len(series))]
    ys = [h - pad - (v / 5) * (h - 2 * pad) for _, v in series]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#2563eb"><title>{esc(d)}: {v}</title></circle>'
                   for (d, v), x, y in zip(series, xs, ys))
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:680px">'
            f'<line x1="{pad}" y1="{h-pad}" x2="{w-pad}" y2="{h-pad}" stroke="#d1d5db"/>'
            f'<text x="{pad}" y="14" font-size="11" fill="#6b7280">平均掌握度走势（0–5）</text>'
            f'<polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="2"/>{dots}</svg>')


def build_html(knowledge, points, progress, events, pending_mistakes):
    n = len(points)
    counts = {name: sum(1 for p in points if bucket_of(p) == name) for name, _, _ in BUCKETS}
    avg = round(sum(p["mastery"] for p in points) / n, 2) if n else 0
    good = counts["熟练"] + counts["精通"]
    by_ch = {}
    for p in points:
        by_ch.setdefault((p["chapter_id"], p["chapter"]), []).append(p)
    chapter_rows = "".join(
        f"<tr><td>{esc(t)}</td><td style='width:45%'>{stacked_bar(pts)}</td>"
        f"<td>{round(sum(p['mastery'] for p in pts)/len(pts),2)}/5</td><td>{len(pts)}</td></tr>"
        for (c, t), pts in sorted(by_ch.items()))
    weak = weak_points(points)
    weak_rows = "".join(
        f"<tr><td>{esc(p['id'])}</td><td>{esc(p['name'])}</td><td>{p['mastery']}/5</td>"
        f"<td>{esc(p['status'])}</td><td>{esc(p.get('note',''))}</td></tr>" for p in weak) or \
        "<tr><td colspan=5>暂无（要么还没开始测验，要么都掌握得不错）</td></tr>"
    activity = "".join(
        f"<li><b>{esc(e.get('date',''))}</b> ｜ {esc(e.get('event',''))} ｜ {esc(e.get('point',''))} "
        f"掌握 {esc(e.get('prev','?'))}→{esc(e.get('mastery','?'))} {esc(e.get('note',''))}</li>"
        for e in reversed(events[-12:])) or "<li>暂无记录</li>"
    legend = " ".join(f'<span style="display:inline-block;width:10px;height:10px;background:{c};'
                      f'border-radius:2px"></span>{name} {counts[name]}' for name, _, c in BUCKETS)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>学习仪表盘 · {esc(knowledge.get('textbook',''))}</title>
<style>
:root {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
body {{ margin:0; background:#f5f5f2; color:#1f2937; }}
#wrap {{ max-width:880px; margin:0 auto; padding:28px 20px 60px; }}
h1 {{ font-size:20px; margin-bottom:4px; }} h2 {{ font-size:15px; margin:26px 0 10px; }}
.meta {{ color:#6b7280; font-size:13px; }}
.cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:18px 0; }}
.card {{ background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:14px 20px; flex:1; min-width:140px; }}
.card .v {{ font-size:24px; font-weight:700; }} .card .k {{ font-size:12px; color:#6b7280; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; background:#fff; }}
th,td {{ border:1px solid #e5e7eb; padding:7px 10px; text-align:left; }} th {{ background:#f9fafb; }}
ul {{ font-size:13px; line-height:1.9; }} .hint {{ color:#6b7280; font-size:13px; }}
.legend {{ font-size:12px; color:#4b5563; display:flex; gap:14px; align-items:center; flex-wrap:wrap; }}
</style></head><body><div id="wrap">
<h1>📊 学习仪表盘 · {esc(knowledge.get('textbook',''))}</h1>
<div class="meta">更新于 {datetime.date.today().isoformat()} ｜ 由 build_dashboard.py 生成，每次批改/费曼后自动刷新</div>
<div class="cards">
<div class="card"><div class="v">{n}</div><div class="k">知识点总数</div></div>
<div class="card"><div class="v">{avg}<span style="font-size:13px">/5</span></div><div class="k">平均掌握度</div></div>
<div class="card"><div class="v">{good}</div><div class="k">熟练及以上（{(good*100//n) if n else 0}%）</div></div>
<div class="card"><div class="v">{pending_mistakes}</div><div class="k">错题待复盘</div></div>
</div>
<div class="legend">{legend}</div>
<div style="margin-top:8px">{stacked_bar(points)}</div>
<h2>各章进度</h2>
<table><tr><th>章节</th><th>掌握度分布</th><th>平均</th><th>知识点</th></tr>{chapter_rows}</table>
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

    kpath = d / "knowledge.json"
    if not kpath.exists():
        sys.exit(f"knowledge.json not found in {d}")
    knowledge = json.loads(kpath.read_text(encoding="utf-8"))
    points = flatten(knowledge)
    progress = {}
    if (d / "progress.json").exists():
        progress = json.loads((d / "progress.json").read_text(encoding="utf-8"))
    events = load_history(d / "history.jsonl")
    pending = count_pending_mistakes(d / "mistakes.md")

    (d / "digest.md").write_text(build_digest(knowledge, points, progress, events, pending), encoding="utf-8")
    print(f"generated {d / 'digest.md'}")
    if not args.digest_only:
        (d / "dashboard.html").write_text(build_html(knowledge, points, progress, events, pending), encoding="utf-8")
        print(f"generated {d / 'dashboard.html'}")


if __name__ == "__main__":
    main()
