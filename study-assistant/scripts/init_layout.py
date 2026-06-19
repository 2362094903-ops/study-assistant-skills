#!/usr/bin/env python3
"""Create the standard study workspace folders.

Usage:
  python3 init_layout.py <study-dir>

The script is idempotent. It does not move existing files; use it before
creating a new workspace so generated artifacts stay classified from the start.
"""
import argparse
import pathlib


DIRS = [
    "open",
    "open/chapters",
    "open/quizzes",
    "internal",
    "internal/state",
    "internal/textbook",
    "internal/lessons",
    "internal/mindmaps",
    "internal/reports",
    "internal/assets",
    "internal/quizzes",
    "question-bank",
]


def write_command(study_dir):
    out_dir = study_dir / "open"
    out_dir.mkdir(parents=True, exist_ok=True)
    dashboard_script = pathlib.Path(__file__).resolve().with_name("build_dashboard.py")
    cmd = out_dir / "update_dashboard.command"
    cmd.write_text(f"""#!/bin/zsh
set -e
SCRIPT_DIR="${{0:A:h}}"
STUDY_DIR="${{SCRIPT_DIR:h}}"
python3 "{dashboard_script}" "$STUDY_DIR"
echo
echo "仪表盘已更新：$SCRIPT_DIR/dashboard.html"
echo "按任意键关闭..."
read -k 1
""", encoding="utf-8")
    cmd.chmod(0o755)
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("study_dir")
    args = ap.parse_args()
    d = pathlib.Path(args.study_dir)
    for name in DIRS:
        (d / name).mkdir(parents=True, exist_ok=True)
    cmd = write_command(d)
    print(f"initialized {d}")
    print(f"generated {cmd}")


if __name__ == "__main__":
    main()
