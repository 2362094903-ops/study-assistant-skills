---
name: study-quiz
description: >
  Quiz & assessment sub-skill (orchestrated by study-assistant; also usable standalone). Three mandatory scenarios: (1) the user uploads past exam papers ("真题", 历年试卷, 样题) — analyze the question style into exam-style.md; (2) the user has no papers but wants school-style questions — search the web for that school's papers/sample exams (user-provided papers always take precedence); (3) the user asks to be tested — "出题" "考我" "测验" "模拟题" "来套模拟卷" "复盘错题" — generate an interactive HTML quiz (single/multiple-choice, true-false, free-response; per-question instant answer & explanation), grade submitted answers, maintain the mistake book, update mastery.
---

# Quizzing & Grading

**Output language: ALL learner-facing content MUST be in Simplified Chinese** — questions, explanations, grading feedback, reports.

Two jobs: **exam-style analysis** and **quizzing & grading**. Shared iron rule: never answer questions for the learner in conversation, never leak answers before they attempt.

## Bank first: check the question bank BEFORE writing questions

The workspace keeps a reusable question bank (`question-bank.json`, managed by `bank.py`). Consulting it costs a few lines of context; regenerating questions from chapter text costs thousands of tokens. Flow:

```bash
python3 ~/.claude/skills/study-quiz/scripts/bank.py <study-dir> list --point 3.1.2 3.1.3   # cheap index
python3 ~/.claude/skills/study-quiz/scripts/bank.py <study-dir> stats --point 3.1.2 3.1.3  # per-point frequency summary
python3 ~/.claude/skills/study-quiz/scripts/bank.py <study-dir> get Q0003 Q0007            # full entries
python3 ~/.claude/skills/study-quiz/scripts/bank.py <study-dir> use Q0003 Q0007            # after assembling
```

- Prefer unused / least-used entries; for repeat practice **adapt** bank entries (new numbers/scenario, same point) instead of reusing verbatim.
- Use `stats` before teaching/quiz planning when you need to know which points have historically been tested most often (`entries`, `used_total`, type mix).
- Write brand-new questions ONLY for points the bank doesn't cover. Source them from the section's lecture JSON in `lessons/` when it exists (already-distilled content, far smaller than chapter text); fall back to `textbook/` only when there is no lecture.
- After building any new quiz, ingest it: `bank.py <study-dir> add <quiz.json>` — the bank grows as a side effect of normal use.

## Delivery format: interactive HTML quiz (default)

Quizzes are interactive HTML pages: the learner answers a question and immediately sees the verdict, answer, and explanation; a final score report can be exported and pasted back for grading.

1. Write the questions as quiz JSON (schema at the top of `~/.claude/skills/study-quiz/scripts/build_quiz.py`), saved to `<study-dir>/quizzes/<date>-<topic>.json`. Four question types:
   - `single` (单选), `multi` (多选 — default exam rule: any wrong or missing selection scores 0; set `"partial": true` for half credit on incomplete-but-clean picks), `judge` (判断, answer true/false), `text` (主观题: 名词解释/简答/计算/论述). Match the mix to exam-style.md — if the real exam has no true-false questions, don't invent them.
   - **Math in Unicode** (MU₁/P₁ = λ, U = X²Y, X^0.5) — this HTML is zero-dependency and does not render LaTeX; the build script rejects `\frac` etc.
   - Objective questions REQUIRE `explanation`: why the right option is right and why each distractor is wrong (distractors come from real pitfalls; the explanation is the correction moment).
   - `text` questions REQUIRE `reference`: model answer + point-by-point score breakdown for self-grading.
2. Build and show: `python3 ~/.claude/skills/study-quiz/scripts/build_quiz.py <json>` then `open` the HTML.
3. In conversation say one Chinese sentence only: quiz opened, N questions, click 导出作答记录 when done and paste it back. **Do not repeat the questions in chat.**
4. When the learner pastes the 【作答记录】, grade (section "Grading" below): trust objective scores as-is; re-grade free-response answers yourself (self-grades are reference only); update the mistake book and mastery as usual.

Fall back to pure-conversation quizzing only when the user explicitly asks ("在对话里考我").

## 1. Exam-style analysis

### Paper sources (user-provided always wins)

1. **User uploaded papers**: the gold standard. Papers may be PDF/image/text — extract per study-assistant's decision tree (scans via study-img).
2. **No papers**: proactively offer to search the web for the target school's past papers or official sample exams. Before searching, confirm three things: school name, subject name & code (e.g. 811 西方经济学), year range. Use WebSearch/WebFetch. Source priority: **official syllabus/sample papers > prep-institution compilations > forum recollections (回忆版)**.
3. Web-source caveats: recollected papers often have missing questions, wrong scores, imprecise wording — the profile MUST open with source URLs and confidence labels per claim (e.g. "题型结构由两个独立来源交叉印证，可信；分值仅单一回忆帖提及，存疑"). If the target school can't be found, fall back to a same-tier school's same subject and say so explicitly.
4. If the user later uploads real papers, immediately re-analyze and overwrite the web-sourced profile.

### Produce the profile

Write `<study-dir>/exam-style.md`:

```markdown
# 命题风格档案：<院校/科目>（来源：<真题年份 或 网络检索+URL+置信度>）
## 试卷结构
（题型、每型几题、分值、总分）
## 难度与风格特征
（考记忆还是考应用？题干长短？结合时事/案例吗？计算量？）
## 高频考点 → 教材章节映射
（真题反复出现的主题对应 knowledge.json 的哪些知识点；据此把这些点的 importance 改为"高"）
## 各题型出题模板与评分标准
（题干句式、得分点结构——之后出题的直接依据）
## 典型真题摘录
（每种题型抄 1 道原题作为风格锚点）
```

Tell the user the conclusions in one Chinese paragraph, and update the named points' `importance` in knowledge.json.

## 2. Question setting

### Point-reinforcement quiz (after a point/section is taught)

- Default 2–3 questions per point, easy → hard: first "can you recognize it" (概念辨析/选择/判断), then "can you use it" (小计算/简答/情景应用).
- With exam-style.md: imitate its stem phrasing and question types strictly. Without: use the subject's conventional exam style (math → 计算/证明; humanities → 名词解释/简答; STEM → 概念+应用).
- A good question tests understanding, not verbatim recall; distractors come from genuine confusions (相近概念、符号方向、适用条件); stems are self-contained.

### Chapter quiz (after a chapter)

A miniature paper following exam-style.md structure, covering ≥60% of the chapter's points (all high-importance points included), with per-question scores. Without a profile, use the conventional objective+subjective split.

### Mistake-book review ("复盘错题")

Pick entries not yet marked 已复盘 from `mistakes.md` and **re-ask in disguise** (same point, different scenario/numbers). Only a correct answer marks the entry 复盘通过.

### Full mock exam ("模拟考" "来套整卷", or multiple chapters done)

- **Full structure, not miniature**: question counts, scores, and total exactly per exam-style.md; state the real exam duration at the top and recommend timed answering.
- **Cross-chapter sampling**: allocate by each chapter's score share in real papers; within a chapter prefer points with high importance × low mastery — mock exams exist to expose weaknesses, not to comfort.
- Same HTML delivery. After grading, additionally write `<study-dir>/reports/mock-<date>.md`: gap to target score, per-chapter score table, weak-point redo plan ("接下来三次学习该做什么").

## 3. Grading

Answers arrive three ways: ① the HTML quiz's exported 【作答记录】; ② typed in conversation; ③ **photos of handwritten work** — transcribe via study-img `--mode answer` (verbatim, no corrections), show the learner the key transcribed steps to confirm recognition before grading; ask about every 【?】 instead of guessing.

Per question give: verdict (partial scores for free-response, e.g. 7/10), correct answer, **exactly where the learner's reasoning broke** (the specific step, not just the model answer), and which knowledge.json point it maps to.

### State updates after grading (immediately)

1. **Mistake book** `mistakes.md`, one entry per miss:

```markdown
## <日期> ｜ <知识点id 知识点名>
**题目**：…
**你的答案**：…
**正确答案/得分点**：…
**错因**：（概念不清 / 记混了 / 计算失误 / 审题偏差）一句话点透
```

2. **knowledge.json**: point `status` → 已测验; `mastery` by performance — clean & correct 4, mostly right 3, half wrong 2, mostly lost 1 (5 is Feynman-only). Write the failure cause into `note`.
3. **progress.json** log entry; per changed point append one line to `history.jsonl` ({"date","point","event":"quiz","prev","mastery","note"}); regenerate the mind map (study-mindmap) and refresh the dashboard (`build_dashboard.py <study-dir>`).
4. Show the pacing menu. If mastery ≤ 2, the recommended next step is re-teaching, not advancing.
