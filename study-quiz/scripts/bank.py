#!/usr/bin/env python3
"""Question bank manager. The bank lets the model REUSE previously written
questions and lecture examples instead of regenerating from chapter text —
listing the bank costs a few lines of context; regenerating costs thousands.

Bank file: <study-dir>/question-bank.json

Usage:
  python3 bank.py <study-dir> add <quiz.json>          # ingest a quiz's questions (dedup by stem hash)
  python3 bank.py <study-dir> add-lecture <lec.json>   # ingest any lecture examples
  python3 bank.py <study-dir> list [--point ID ...] [--type T] [--unused]
                                                       # compact index: qid|point|type|score|used|stem head
  python3 bank.py <study-dir> stats [--point ID ...]   # compact per-point frequency summary
  python3 bank.py <study-dir> get QID [QID ...]        # full JSON of selected entries (quiz-JSON ready)
  python3 bank.py <study-dir> use QID [QID ...]        # mark as used (after assembling a quiz)

Recommended flow when quizzing: `list --point ...` first → `get` the picks
(prefer unused / least used; adapt numbers for repeat practice) → write new
questions ONLY for uncovered points → assemble quiz JSON → build_quiz.py → `use`.
"""
import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import json
import pathlib
import sys

QUESTION_FIELDS = ("type", "qtype_label", "point_id", "point_name", "score",
                   "stem", "options", "answer", "partial", "reference", "explanation",
                   "source_ref")


def load_bank(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"next_id": 1, "entries": []}


def save_bank(path, bank):
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")


def stem_hash(stem):
    return hashlib.sha1("".join((stem or "").split()).encode()).hexdigest()[:12]


def ingest(bank, questions, source):
    existing = {e["hash"] for e in bank["entries"]}
    added = 0
    for q in questions:
        h = stem_hash(q.get("stem"))
        if h in existing:
            continue
        entry = {k: q[k] for k in QUESTION_FIELDS if k in q}
        entry.update({"qid": f"Q{bank['next_id']:04d}", "hash": h, "source": source,
                      "added": datetime.date.today().isoformat(), "used": 0, "last_used": ""})
        bank["entries"].append(entry)
        bank["next_id"] += 1
        existing.add(h)
        added += 1
    return added


def cmd_add(bank, args):
    data = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
    n = ingest(bank, data.get("questions", []), pathlib.Path(args.file).name)
    print(f"added {n} new question(s) (duplicates skipped: {len(data.get('questions', [])) - n})")


def cmd_add_lecture(bank, args):
    data = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
    qs = []
    for p in data.get("points", []):
        examples = []
        if isinstance(p.get("examples"), list):
            examples.extend(p["examples"])
        if isinstance(p.get("example"), dict):
            examples.append(p["example"])
        for ex in examples:
            if ex.get("problem") and ex.get("solution"):
                qs.append({"type": ex.get("type", "text"), "qtype_label": "例题改编",
                           "point_id": p.get("id"), "point_name": p.get("name"), "score": 10,
                           "stem": ex["problem"], "options": ex.get("options"),
                           "answer": ex.get("answer"), "reference": ex["solution"],
                           "source_ref": ex.get("source_ref") or p.get("source_ref"),
                           "explanation": "源自讲义例题；出题时建议换数字/情境改编，避免原题复现。"})
    n = ingest(bank, qs, pathlib.Path(args.file).name + " (lecture)")
    print(f"added {n} lecture example(s) to question bank")


def cmd_list(bank, args):
    rows = bank["entries"]
    if args.point:
        rows = [e for e in rows if e.get("point_id") in args.point]
    if args.type:
        rows = [e for e in rows if e.get("type") == args.type]
    if args.unused:
        rows = [e for e in rows if not e["used"]]
    if not rows:
        print("(no matching entries)")
        return
    for e in sorted(rows, key=lambda e: (e.get("point_id") or "", e["qid"])):
        head = (e.get("stem") or "").replace("\n", " ")[:34]
        print(f"{e['qid']} | {e.get('point_id','?'):8} | {e.get('type','?'):6} | "
              f"{e.get('score','?'):>3}分 | used:{e['used']} | {head}")


def cmd_stats(bank, args):
    rows = bank["entries"]
    if args.point:
        wanted = set(args.point)
        rows = [e for e in rows if e.get("point_id") in wanted]
    groups = defaultdict(list)
    for e in rows:
        groups[e.get("point_id") or "?"].append(e)
    if not groups:
        print("(no matching entries)")
        return
    summary = []
    for pid, entries in groups.items():
        used_total = sum(int(e.get("used") or 0) for e in entries)
        unused = sum(1 for e in entries if not int(e.get("used") or 0))
        types = Counter(e.get("type") or "?" for e in entries)
        point_name = next((e.get("point_name") for e in entries if e.get("point_name")), "")
        qids = ",".join(e["qid"] for e in sorted(entries, key=lambda x: x["qid"])[:5])
        summary.append((len(entries), used_total, pid, point_name, unused, types, qids))
    for count, used_total, pid, point_name, unused, types, qids in sorted(
            summary, key=lambda x: (-x[0], -x[1], x[2])):
        type_txt = ",".join(f"{k}:{v}" for k, v in sorted(types.items()))
        name_txt = f" {point_name}" if point_name else ""
        print(f"{pid:8}{name_txt} | entries:{count} | used_total:{used_total} | "
              f"unused:{unused} | types:{type_txt} | sample:{qids}")


def cmd_get(bank, args):
    idx = {e["qid"]: e for e in bank["entries"]}
    out = []
    for qid in args.qids:
        if qid not in idx:
            sys.exit(f"unknown qid: {qid}")
        q = {k: v for k, v in idx[qid].items() if k in QUESTION_FIELDS and v not in (None, "")}
        out.append(q)
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_use(bank, args):
    idx = {e["qid"]: e for e in bank["entries"]}
    today = datetime.date.today().isoformat()
    for qid in args.qids:
        if qid in idx:
            idx[qid]["used"] += 1
            idx[qid]["last_used"] = today
    print(f"marked {len(args.qids)} entr(ies) used")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("study_dir")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add"); p.add_argument("file")
    p = sub.add_parser("add-lecture"); p.add_argument("file")
    p = sub.add_parser("list")
    p.add_argument("--point", nargs="*"); p.add_argument("--type"); p.add_argument("--unused", action="store_true")
    p = sub.add_parser("stats"); p.add_argument("--point", nargs="*")
    p = sub.add_parser("get"); p.add_argument("qids", nargs="+")
    p = sub.add_parser("use"); p.add_argument("qids", nargs="+")
    args = ap.parse_args()

    bank_path = pathlib.Path(args.study_dir) / "question-bank.json"
    bank = load_bank(bank_path)
    {"add": cmd_add, "add-lecture": cmd_add_lecture, "list": cmd_list, "stats": cmd_stats,
     "get": cmd_get, "use": cmd_use}[args.cmd](bank, args)
    if args.cmd in ("add", "add-lecture", "use"):
        save_bank(bank_path, bank)


if __name__ == "__main__":
    main()
