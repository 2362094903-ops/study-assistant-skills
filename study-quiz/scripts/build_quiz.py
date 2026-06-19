#!/usr/bin/env python3
"""从 quiz JSON 生成可交互 HTML 试卷（做一题显示一题的答案与解析）。

数学公式支持 LaTeX $...$ / $$...$$，HTML 通过 MathJax 渲染；离线时退化为
LaTeX 源码显示。

用法：
  python3 build_quiz.py <quiz.json> [-o 输出.html]    # 默认输出到同名 .html
  python3 build_quiz.py internal/quizzes/ch3.json --publish <study-dir>

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
      "stem": "题干（公式可用 LaTeX，如 $MU_x/P_x=MU_y/P_y=\\lambda$）",
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
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("quiz_json")
    ap.add_argument("-o", "--out", help="输出 HTML 路径，默认同名 .html")
    ap.add_argument("--publish", help="study-dir；同时写一份 HTML 到 open/quizzes/")
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
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"已生成 {out}（{len(data['questions'])} 题）")
    if args.publish:
        pub = pathlib.Path(args.publish) / "open" / "quizzes" / out.name
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(html, encoding="utf-8")
        print(f"已生成 {pub}（仪表盘可链接）")


if __name__ == "__main__":
    main()
