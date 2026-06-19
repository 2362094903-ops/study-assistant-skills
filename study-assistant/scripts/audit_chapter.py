#!/usr/bin/env python3
"""Audit one chapter after lecture generation.

The audit catches workflow regressions that are easy for different models to
miss: incomplete point coverage, courseware figures/tables/formulas not carried
into the lecture, and source examples not represented as worked examples.

Usage:
  python3 audit_chapter.py <study-dir> --chapter 3

Outputs:
  internal/reports/chapter-03-audit.md and .json (or reports/ in legacy layout)
Exit code:
  0 = pass or warnings only; 1 = blocking issues that should be fixed, then rerun
"""
import argparse
from collections import Counter
import datetime
import json
import pathlib
import re
import sys


VISUAL_RE = re.compile(r"(\[图|!\[|图\s*\d|表\s*\d|图表|曲线|坐标|函数图|示意图|流程图|IMAGE-HEAVY|待 OCR)")
TABLE_RE = re.compile(r"^\s*\|.+\|\s*$", re.M)
EXAMPLE_RE = re.compile(r"(例题|例\s*\d|【例|案例|练习题|随堂练习|典型题)")
FORMULA_RE = re.compile(r"(\$[^$]+\$|\\frac|\\sum|\\sqrt|公式|方程|[A-Za-z]\s*[=<>≤≥]|[∑√πλμσ∞≈≠≤≥])")

TEXT_KEYS = {
    "exam_focus", "textbook_excerpt", "intuition", "formal", "key_point",
    "method", "pitfalls", "memory_hook", "problem", "solution", "answer",
    "reference", "explanation", "caption", "source", "source_ref", "alt",
}


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


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def text_from(obj):
    parts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in TEXT_KEYS:
                parts.append(text_from(v))
            elif isinstance(v, (dict, list)):
                parts.append(text_from(v))
    elif isinstance(obj, list):
        for v in obj:
            parts.append(text_from(v))
    elif obj is not None:
        parts.append(str(obj))
    return "\n".join(p for p in parts if p)


def example_list(point):
    out = []
    if isinstance(point.get("examples"), list):
        out.extend(point["examples"])
    if isinstance(point.get("example"), dict):
        out.append(point["example"])
    return out


def figure_list(point):
    figures = point.get("figures") or point.get("images") or []
    if isinstance(figures, dict):
        return [figures]
    if isinstance(figures, list):
        return [f for f in figures if isinstance(f, dict)]
    return []


def chapter_from_knowledge(knowledge, chapter_id):
    for ch in knowledge.get("chapters", []):
        if ch.get("id") == chapter_id:
            return ch
    return None


def expected_points(chapter):
    ids = []
    for sec in chapter.get("sections", []):
        for p in sec.get("points", []):
            ids.append(p.get("id"))
    return [x for x in ids if x]


def load_source_text(study_dir, chapter_id):
    tdir = data_dir(study_dir, "textbook")
    candidates = [
        tdir / f"chapter-{chapter_id:02d}.md",
        tdir / f"chapter-{chapter_id}.md",
        study_dir / "textbook" / f"chapter-{chapter_id:02d}.md",
        study_dir / "textbook" / f"chapter-{chapter_id}.md",
    ]
    for path in candidates:
        if path.exists():
            return path, path.read_text(encoding="utf-8")
    if tdir.exists():
        matches = sorted(tdir.glob(f"*{chapter_id:02d}*.md")) + sorted(tdir.glob(f"*{chapter_id}*.md"))
        matches = [p for p in matches if p.is_file()]
        if matches:
            return matches[0], matches[0].read_text(encoding="utf-8")
    return None, ""


def load_lecture_jsons(study_dir, chapter_id):
    root = data_dir(study_dir, "lessons") / f"chapter-{chapter_id:02d}"
    legacy = study_dir / "lessons" / f"chapter-{chapter_id:02d}"
    paths = []
    for base in [root, legacy]:
        if base.exists():
            paths.extend(p for p in sorted(base.glob("*.json")) if not p.name.startswith("chapter-"))
    seen = set()
    uniq = []
    for p in paths:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            uniq.append(p)
    data = []
    for path in uniq:
        try:
            data.append((path, load_json(path)))
        except Exception as e:
            data.append((path, {"__load_error__": str(e)}))
    return data


def add_issue(issues, severity, code, message, fix):
    issues.append({"severity": severity, "code": code, "message": message, "fix": fix})


def audit(study_dir, chapter_id):
    sdir = state_dir(study_dir)
    knowledge_path = sdir / "knowledge.json"
    if not knowledge_path.exists():
        sys.exit(f"knowledge.json not found in {sdir}")
    knowledge = load_json(knowledge_path)
    chapter = chapter_from_knowledge(knowledge, chapter_id)
    if not chapter:
        sys.exit(f"knowledge.json has no chapter id {chapter_id}")

    expected = expected_points(chapter)
    source_path, source = load_source_text(study_dir, chapter_id)
    lectures = load_lecture_jsons(study_dir, chapter_id)
    issues = []

    if not source:
        add_issue(
            issues, "warning", "source_missing",
            "未找到本章教材/课件 Markdown，无法审查图表、公式、例题是否从原始材料进入讲义。",
            "把本章材料保存到 internal/textbook/chapter-XX.md，或确认旧目录 textbook/chapter-XX.md 存在。",
        )
    if not lectures:
        add_issue(
            issues, "blocker", "lecture_json_missing",
            "未找到本章单知识点讲义 JSON。",
            "先按知识点生成 internal/lessons/chapter-XX/*.json，再运行审查。",
        )

    actual = []
    lecture_text = []
    figure_count = 0
    example_count = 0
    table_count = 0
    figure_refs_missing = []
    example_refs_missing = []
    load_errors = []

    for path, data in lectures:
        if "__load_error__" in data:
            load_errors.append(f"{path.name}: {data['__load_error__']}")
            continue
        lecture_text.append(text_from(data))
        for p in data.get("points", []):
            if p.get("id"):
                actual.append(p["id"])
            figs = figure_list(p)
            figure_count += len(figs)
            for fig in figs:
                if not (fig.get("source") or fig.get("source_ref")):
                    figure_refs_missing.append(f"{p.get('id','?')} {p.get('name','')}")
            exs = example_list(p)
            example_count += len(exs)
            for ex in exs:
                if not (ex.get("source_ref") or ex.get("source")):
                    example_refs_missing.append(f"{p.get('id','?')} {p.get('name','')}")
            if TABLE_RE.search(text_from(p)):
                table_count += 1

    if load_errors:
        add_issue(
            issues, "blocker", "lecture_json_invalid",
            "部分讲义 JSON 无法读取：" + "；".join(load_errors),
            "修复 JSON 格式后重新运行 build_lecture.py 和 audit_chapter.py。",
        )

    duplicate_ids = sorted(pid for pid, count in Counter(actual).items() if count > 1)
    if duplicate_ids:
        add_issue(
            issues, "blocker", "points_duplicated",
            "同一知识点被多个讲义 JSON 重复定义：" + "、".join(duplicate_ids),
            "每个知识点只保留一个 JSON/HTML；删除或合并重复定义后重新生成整章讲义。",
        )

    missing = sorted(set(expected) - set(actual), key=lambda x: [int(n) for n in x.split(".") if n.isdigit()])
    extra = sorted(set(actual) - set(expected))
    if missing:
        add_issue(
            issues, "blocker", "points_missing",
            "讲义缺少 knowledge.json 中的知识点：" + "、".join(missing),
            "为缺失知识点补生成单独的讲义 JSON/HTML，确保 id 与 knowledge.json 完全一致。",
        )
    if extra:
        add_issue(
            issues, "warning", "points_extra",
            "讲义包含 knowledge.json 中没有的知识点：" + "、".join(extra),
            "确认是否应把这些点加入 knowledge.json，或修正讲义中的 id。",
        )

    joined_lecture = "\n".join(lecture_text)
    source_has_visual = bool(VISUAL_RE.search(source) or TABLE_RE.search(source))
    source_has_example = bool(EXAMPLE_RE.search(source))
    source_has_formula = bool(FORMULA_RE.search(source))
    lecture_has_visual = figure_count > 0 or table_count > 0
    lecture_has_formula = bool(FORMULA_RE.search(joined_lecture))

    if source_has_visual and not lecture_has_visual:
        add_issue(
            issues, "blocker", "visuals_not_carried",
            "原始材料出现图、表、曲线或图片型课件标记，但本章讲义没有 figures，也没有 Markdown 表格。",
            "逐页检查相关图表；凡对理解有帮助的，加入 figures 或重写为 Markdown 表格，并在正文解释图表含义。",
        )
    if source_has_example and example_count == 0:
        add_issue(
            issues, "blocker", "examples_not_carried",
            "原始材料出现例题/案例/练习标记，但本章讲义没有任何 worked examples。",
            "把教材或课件中的关键例题改写进对应知识点 examples，并保留 source_ref。",
        )
    if source_has_formula and not lecture_has_formula:
        add_issue(
            issues, "blocker", "formulas_not_carried",
            "原始材料出现公式/方程/数学符号，但讲义正文没有可识别公式。",
            "把必要公式写入 formal/method/solution，优先用 LaTeX $...$，并解释每个符号。",
        )
    if source_has_visual and figure_refs_missing:
        add_issue(
            issues, "warning", "figure_source_refs_missing",
            "部分讲义图缺少 source/source_ref：" + "、".join(figure_refs_missing[:8]),
            "给每个从教材/课件来的图写明来源，例如 课件第12页图3-2。",
        )
    if source_has_example and example_refs_missing:
        add_issue(
            issues, "warning", "example_source_refs_missing",
            "部分例题缺少 source_ref：" + "、".join(example_refs_missing[:8]),
            "给从教材/课件/真题改写的例题写明来源；原创题可写 source_ref: 讲义原创。",
        )

    blockers = [i for i in issues if i["severity"] == "blocker"]
    summary = {
        "date": datetime.date.today().isoformat(),
        "chapter": chapter_id,
        "chapter_title": chapter.get("title", ""),
        "source": str(source_path) if source_path else "",
        "expected_points": len(expected),
        "lecture_json_files": len(lectures),
        "lecture_points": len(actual),
        "figures": figure_count,
        "tables": table_count,
        "examples": example_count,
        "source_markers": {
            "visual": source_has_visual,
            "example": source_has_example,
            "formula": source_has_formula,
        },
        "status": "blocked" if blockers else "pass",
        "issues": issues,
    }
    return summary


def write_reports(study_dir, summary):
    rdir = data_dir(study_dir, "reports")
    rdir.mkdir(parents=True, exist_ok=True)
    cid = summary["chapter"]
    json_path = rdir / f"chapter-{cid:02d}-audit.json"
    md_path = rdir / f"chapter-{cid:02d}-audit.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# 第{cid}章讲义审查报告",
        "",
        f"- 状态：{'需要修改' if summary['status'] == 'blocked' else '通过'}",
        f"- 章节：{summary['chapter_title']}",
        f"- 来源文件：{summary['source'] or '未找到'}",
        f"- 知识点覆盖：{summary['lecture_points']} / {summary['expected_points']}",
        f"- 讲义文件：{summary['lecture_json_files']} 个",
        f"- 图：{summary['figures']} ｜ 表：{summary['tables']} ｜ 例题：{summary['examples']}",
        f"- 原始材料标记：图表={summary['source_markers']['visual']} ｜ 例题={summary['source_markers']['example']} ｜ 公式={summary['source_markers']['formula']}",
        "",
    ]
    if summary["issues"]:
        lines.append("## 问题清单")
        for item in summary["issues"]:
            sev = "阻塞" if item["severity"] == "blocker" else "提醒"
            lines.append(f"- [{sev}] {item['code']}：{item['message']}")
            lines.append(f"  修改：{item['fix']}")
    else:
        lines.append("## 问题清单")
        lines.append("- 未发现阻塞项或提醒项。")
    lines.append("")
    lines.append("## 下一步")
    if summary["status"] == "blocked":
        lines.append("按问题清单修改对应知识点 JSON，重新渲染单知识点 HTML，再重新合并整章 HTML，最后再次运行本审查。")
    else:
        lines.append("审查已通过；确认整章主 HTML 为最新版本，然后刷新仪表盘。")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("study_dir")
    ap.add_argument("--chapter", type=int, required=True)
    args = ap.parse_args()

    study_dir = pathlib.Path(args.study_dir)
    summary = audit(study_dir, args.chapter)
    md_path, json_path = write_reports(study_dir, summary)
    print(f"generated {md_path}")
    print(f"generated {json_path}")
    if summary["status"] == "blocked":
        sys.exit(1)


if __name__ == "__main__":
    main()
