#!/usr/bin/env python3
"""从 quiz JSON 生成可交互 HTML 试卷（做一题显示一题的答案与解析，零依赖离线可开）。

用法：
  python3 build_quiz.py <quiz.json> [-o 输出.html]    # 默认输出到同名 .html

quiz JSON schema：
{
  "title": "第三章 效用论 · 消费者均衡巩固测验",
  "questions": [
    {
      "type": "single",                      // single=单选；multi=多选；judge=判断；text=主观题
      "qtype_label": "单项选择（2分）",
      "point_id": "3.1.4",
      "point_name": "消费者均衡",
      "score": 2,
      "stem": "题干（公式用 Unicode 写法，如 MU₁/P₁ = λ，不要写 LaTeX 源码）",
      "options": ["...", "...", "...", "..."],   // single/multi
      "answer": 0,                                // single：下标(0=A)；multi：下标列表 [0,2]；judge：true/false
      "partial": false,                           // 仅 multi 可选：true=漏选且无错选得一半分；默认错选漏选均不得分
      "reference": "参考答案与得分点（仅 text）",
      "explanation": "解析/易错提醒（single/multi/judge 必填：为什么对、干扰项/迷惑点错在哪）"
    }
  ]
}
"""
import argparse
import datetime
import json
import pathlib
import sys

TEMPLATE = pathlib.Path(__file__).resolve().parent.parent / "assets" / "quiz_template.html"


def validate(data):
    errs = []
    if not data.get("title"):
        errs.append("缺 title")
    for i, q in enumerate(data.get("questions", [])):
        tag = f"questions[{i}]"
        qtype = q.get("type")
        if qtype not in ("single", "multi", "judge", "text"):
            errs.append(f"{tag}: type 必须是 single / multi / judge / text")
        if not q.get("stem"):
            errs.append(f"{tag}: 缺 stem")
        if not isinstance(q.get("score"), (int, float)):
            errs.append(f"{tag}: 缺 score")
        opts = q.get("options")
        if qtype == "single":
            if not isinstance(opts, list) or len(opts) < 2:
                errs.append(f"{tag}: single 需要 options 列表")
            if not isinstance(q.get("answer"), int) or not (0 <= q["answer"] < len(opts or [])):
                errs.append(f"{tag}: answer 必须是 options 的合法下标")
        elif qtype == "multi":
            if not isinstance(opts, list) or len(opts) < 3:
                errs.append(f"{tag}: multi 需要至少 3 个 options")
            ans = q.get("answer")
            if (not isinstance(ans, list) or not ans
                    or not all(isinstance(a, int) and 0 <= a < len(opts or []) for a in ans)
                    or len(set(ans)) != len(ans)):
                errs.append(f"{tag}: multi 的 answer 必须是不重复的合法下标列表（如 [0,2]）")
            elif len(ans) < 2:
                errs.append(f"{tag}: multi 的正确项应不少于 2 个，只有 1 个正确项请改用 single")
        elif qtype == "judge":
            if not isinstance(q.get("answer"), bool):
                errs.append(f"{tag}: judge 的 answer 必须是 true 或 false")
        if qtype in ("single", "multi", "judge") and not q.get("explanation"):
            errs.append(f"{tag}: 客观题必须给 explanation")
        if qtype == "text" and not q.get("reference"):
            errs.append(f"{tag}: 主观题必须给 reference（参考答案与得分点）")
        if "\\frac" in (q.get("stem", "") + (q.get("reference") or "")):
            errs.append(f"{tag}: 题面含 LaTeX 源码，HTML 不渲染公式，请改用 Unicode 写法")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("quiz_json")
    ap.add_argument("-o", "--out", help="输出 HTML 路径，默认同名 .html")
    args = ap.parse_args()

    src = pathlib.Path(args.quiz_json)
    data = json.loads(src.read_text(encoding="utf-8"))
    errs = validate(data)
    if errs:
        sys.exit("quiz JSON 校验失败：\n  " + "\n  ".join(errs))

    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("__TITLE__", data["title"])
            .replace("__GENERATED__", "生成于 " + datetime.date.today().isoformat())
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    out = pathlib.Path(args.out) if args.out else src.with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    print(f"已生成 {out}（{len(data['questions'])} 题）")


if __name__ == "__main__":
    main()
