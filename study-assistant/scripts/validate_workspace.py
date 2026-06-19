#!/usr/bin/env python3
"""Validate the study workspace state files (knowledge.json / progress.json).

Run this after creating or modifying state files. It enforces the shared state
contract so that any model driving the skills produces identical structures.

Usage:
  python3 validate_workspace.py <study-dir>          # validate both files
  python3 validate_workspace.py <study-dir> -q       # quiet: errors only

Exit code 0 = valid; 1 = contract violations (listed on stderr).
"""
import argparse
import json
import pathlib
import re
import sys

STATUS_ENUM = ["未学", "已讲解", "已测验", "已检验"]
IMPORTANCE_ENUM = ["高", "中", "低"]
ID_RE = re.compile(r"^\d+(\.\d+)+$")


def state_dir(study_dir):
    internal = study_dir / "internal" / "state"
    if (internal / "knowledge.json").exists() or (study_dir / "internal").exists():
        return internal
    return study_dir


def check_layout(study_dir, errs):
    """Require the full modern layout once internal/ exists; ignore legacy workspaces."""
    if not (study_dir / "internal").exists():
        return
    expected_dirs = [
        study_dir / "open",
        study_dir / "open" / "chapters",
        study_dir / "open" / "quizzes",
        study_dir / "internal" / "state",
        study_dir / "internal" / "textbook",
        study_dir / "internal" / "lessons",
        study_dir / "internal" / "mindmaps",
        study_dir / "internal" / "reports",
        study_dir / "question-bank",
    ]
    for d in expected_dirs:
        if not d.exists():
            errs.append(f"layout: missing directory '{d.relative_to(study_dir)}'")


def check_knowledge(path, errs):
    if not path.exists():
        errs.append("knowledge.json missing")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errs.append(f"knowledge.json is not valid JSON: {e}")
        return
    for key in ("textbook", "subject_type", "updated", "chapters"):
        if key not in data:
            errs.append(f"knowledge.json: missing top-level field '{key}'")
    seen_ids = set()
    for ci, ch in enumerate(data.get("chapters", [])):
        ctag = f"chapters[{ci}]"
        if not isinstance(ch.get("id"), int):
            errs.append(f"{ctag}: 'id' must be an integer")
        if not ch.get("title"):
            errs.append(f"{ctag}: missing 'title'")
        sections = ch.get("sections")
        if not sections:
            errs.append(f"{ctag}: 'sections' is empty")
            continue
        for si, sec in enumerate(sections):
            stag = f"{ctag}.sections[{si}]"
            if not sec.get("title"):
                errs.append(f"{stag}: missing 'title'")
            for pi, p in enumerate(sec.get("points", [])):
                ptag = f"{stag}.points[{pi}]"
                pid = p.get("id", "")
                if not ID_RE.match(str(pid)):
                    errs.append(f"{ptag}: id '{pid}' must look like 3.1.2")
                elif pid in seen_ids:
                    errs.append(f"{ptag}: duplicate id '{pid}'")
                else:
                    seen_ids.add(pid)
                if not p.get("name"):
                    errs.append(f"{ptag}: missing 'name'")
                if p.get("importance") not in IMPORTANCE_ENUM:
                    errs.append(f"{ptag}: importance must be one of {IMPORTANCE_ENUM}")
                if p.get("status") not in STATUS_ENUM:
                    errs.append(f"{ptag}: status must be one of {STATUS_ENUM}")
                m = p.get("mastery")
                if not isinstance(m, (int, float)) or not 0 <= m <= 5:
                    errs.append(f"{ptag}: mastery must be a number in 0..5")
                if "note" not in p:
                    errs.append(f"{ptag}: missing 'note' (use \"\" when empty)")
    return seen_ids


def check_progress(path, errs, known_ids):
    if not path.exists():
        errs.append("progress.json missing")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errs.append(f"progress.json is not valid JSON: {e}")
        return
    for key in ("current_chapter", "current_point", "next_action", "exam_style_ready", "log"):
        if key not in data:
            errs.append(f"progress.json: missing field '{key}'")
    cp = data.get("current_point")
    if known_ids and cp and cp not in known_ids:
        errs.append(f"progress.json: current_point '{cp}' not found in knowledge.json")
    if not isinstance(data.get("log"), list):
        errs.append("progress.json: 'log' must be a list")
    else:
        for i, entry in enumerate(data["log"]):
            if not (isinstance(entry, dict) and entry.get("date") and entry.get("event")):
                errs.append(f"progress.json: log[{i}] must be {{'date': ..., 'event': ...}}")
    if "lecture_format" in data and data["lecture_format"] not in ("obsidian", "html", "both"):
        errs.append("progress.json: lecture_format must be obsidian / html / both")
    if "study_mode" in data and data["study_mode"] not in ("deep", "speedrun"):
        errs.append("progress.json: study_mode must be deep / speedrun")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("study_dir")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()
    d = pathlib.Path(args.study_dir)
    sdir = state_dir(d)

    errs = []
    check_layout(d, errs)
    known_ids = check_knowledge(sdir / "knowledge.json", errs) or set()
    check_progress(sdir / "progress.json", errs, known_ids)

    if errs:
        print("workspace contract violations:", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        sys.exit(1)
    if not args.quiet:
        print(f"OK: state files in {sdir} ({len(known_ids)} points) conform to the contract")


if __name__ == "__main__":
    main()
