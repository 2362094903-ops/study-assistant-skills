---
name: study-teach
description: >
  Lecture & explanation sub-skill (orchestrated by study-assistant; also usable standalone). Use when the learner wants a chapter/section taught ("开始讲解" "讲一下第三章" "生成讲义" "继续下一节"), asks a follow-up question about studied content, or says they didn't understand ("给我讲讲X" "没听懂，重讲一遍"). Generates complete section-by-section lecture notes in two selectable modes — 深入讲解 (deep understanding, leads with textbook原文) or 考试速通 (exam speed-run, 解题思维 + targeted examples by importance/question frequency) — as Obsidian Markdown and/or interactive HTML with rendered math, robust Markdown tables, and generated function-graph figures when the source teaches with curves; conversation is reserved for targeted Q&A and re-teaching.
---

# Teaching: Lecture Notes + Q&A

**Output language: ALL learner-facing content MUST be in Simplified Chinese** — lecture notes, Q&A answers, examples. These instructions are English only for cross-model reliability.

Two modes. **Lecture mode is the default**: a full set of section notes the learner reads at their own pace beats streaming explanations point by point. **Conversation is for Q&A**: targeted answers, alternative explanations, gaps the notes missed.

## Lecture mode (default)

### One-time setup per textbook

Ask the learner once which lecture format they want and store it as `lecture_format` in progress.json:

- **Obsidian Markdown** — 公式原生渲染、例题答案折叠、双链、手机可同步（学习区文件夹直接作为 vault 打开）
- **interactive HTML** — 浏览器阅读、侧边目录、例题点击展开、"标记已学"进度（公式经 MathJax 渲染，需联网；离线退化为 LaTeX 源码）
- **both**

### Pick the teaching MODE (per section — confirm before generating)

There are two teaching modes. Default to whatever progress.json's `study_mode` last held; before generating each section, briefly let the learner switch (harder chapters → deep, easy ones → speedrun). Store the chosen mode back to progress.json `study_mode`. The mode sets `mode` in the lecture JSON and changes which fields each point carries:

- **`deep` 深入讲解** — truly understand and master the textbook. Each point leads with the textbook's key original wording, then a rich explanation. Substantial: a core point's `formal` runs ~500–1200 Chinese characters with full derivation/reasoning.
- **`speedrun` 考试速通** — exam-focused, no lengthy theory. Each point states the conclusion in 1–3 sentences, then the **解题思维/套路** (how to read and solve this question type). Worked examples are targeted to high-value points, not mechanically attached to every point. The center of gravity is doing problems and the method, not understanding for its own sake.

Mode affects **lectures only** — quizzing (study-quiz) behaves the same in both modes.

### Generate one SECTION per pass — never a whole chapter

Long generations degrade toward the end. One section (3.1, 3.2, ...) at a time; the learner reads it, asks questions, then requests the next.

1. Read the section's source text in `textbook/` — lectures must stay faithful to the textbook, exams grade against it. Check `exam-style.md` if present; `exam_focus` fields must cite it.
2. Write the lecture as JSON to `lessons/chapter-XX/<section>.json` with `"mode": "deep"|"speedrun"`, schema documented at the top of `~/.claude/skills/study-teach/scripts/build_lecture.py`. Every point of this section in knowledge.json must appear, with the same ids. Fields by mode:

   **Both modes**: `exam_focus` (importance + question types, cite exam-style.md when present), `pitfalls`, `memory_hook` (mnemonic/framework; humanities: a 3–5 bullet recitation version), optional `figures`, `links`.

   **deep mode**: `textbook_excerpt` (教材关键原文 — quote the source verbatim when the extracted `textbook/` text is clean; paraphrase the core wording when it is scanned/messy), `intuition` (analogy + where it breaks), `formal` (REQUIRED — textbook-grade statement, LaTeX for every formula, every symbol explained, full derivation/reasoning; this is where depth lives — be thorough, ~500–1200 chars for core points). Add examples only where practice meaningfully improves understanding or the point is frequently tested.

   **speedrun mode**: `key_point` (1–3 sentences nailing the exam point), `method` (REQUIRED — 解题思维: how to recognize this question type, which formula, what steps, what traps to watch), and optional `examples` for high-value points; emphasize the solving routine, not theory.

   **Example allocation** (both modes): examples are optional. Do **not** require every knowledge point to have an example. Before writing examples, inspect `question-bank.json` when present: points that already appear often, have high `used` counts, or map to common quiz/question-bank entries deserve examples first. If there is no useful question bank, use the courseware/textbook's own worked examples as the priority signal. Then allocate by `importance`: high-importance points usually get 1–3 examples, medium points get an example only if they are computational/confusable, and low/background points can have none. Each included example is `{problem, solution, answer?}`. `solution` is the complete worked solution. `answer` (optional) is the problem's **final answer** — a string, or a list of acceptable forms (e.g. `["50", "50万元"]`). In the HTML lecture each example is **interactive**: the learner types an attempt and submits; if `answer` is present the page auto-checks it (✓/✗) and then reveals the full solution + a self-grade; if `answer` is absent it reveals the solution + self-grade on submit. So provide `answer` for calculation/short-answer problems (definite final answer) and omit it for open conceptual ones. Obsidian Markdown stays static (problem + foldable solution).

   **Markdown is fine in any text field** — `**bold**`, `-`/`1.` lists, and standard Markdown tables render correctly in both HTML and Obsidian. Keep math in LaTeX `$...$` / `$$...$$`.

   **Tables**: when the source contains financial statements, ratio summaries, formula comparisons, or step-by-step computation grids, write them as normal Markdown tables with a separator row (`|---|---|`). Do not simulate tables with spaces, tabs, ASCII boxes, or screenshots. The HTML renderer gives tables visible borders and horizontal scrolling, so use real tables whenever comparison is the point.

   **Function graphs / curve explanations**: if the textbook or courseware explains a concept through a function image, curve, coordinate plot, slope, intersection, convexity/concavity, or comparative statics, the lecture must include a generated figure rather than text-only explanation.
   - Prefer Python/matplotlib via the bundled helper:
     ```bash
     python3 ~/.claude/skills/study-teach/scripts/plot_function.py \
       --curve "低增长情形=0.08*x" --curve "高增长情形=0.16*x" \
       --x-min 0 --x-max 0.3 --xlabel "销售增长率" --ylabel "外部融资需求" \
       --title "增长率与外部融资需求" \
       -o <study-dir>/lessons/chapter-XX/assets/<section>-<point>-curve.png
     ```
   - MATLAB is also acceptable when the user's environment already has it and the graph is easier to express there; still save a PNG under the same `assets/` folder.
   - Include the figure in the point JSON:
     ```json
     "figures": [
       {
         "path": "assets/3.5-efn-growth.png",
         "caption": "销售增长率越高，EFN 通常越大；斜率由资产需求、自发负债和留存收益共同决定。",
         "source": "Python/matplotlib；根据教材 EFN 公式绘制",
         "alt": "EFN 随销售增长率上升的函数图像"
       }
     ]
     ```
   - In the surrounding explanation, explicitly teach the graph: axes mean什么、曲线/斜率/交点说明什么、考试中如何从图转成公式或判断题结论。Do not add decorative figures that are not used in the explanation.
3. Render (the script validates the JSON and fails loudly on missing/mode-required fields):

```bash
python3 ~/.claude/skills/study-teach/scripts/build_lecture.py <section>.json --format <lecture_format>
```

4. Deliver: `open` the HTML, or for Obsidian give the file path inside the vault. In conversation say only 2–3 Chinese sentences: what the section covers, the 1–2 points that deserve the most attention, and a reminder that solutions are collapsed — attempt first.
5. Update state: covered points `status` → 已讲解; progress.json (`current_point`, `next_action`, one log entry); regenerate the mind map; ingest any section examples into the question bank (`python3 ~/.claude/skills/study-quiz/scripts/bank.py <study-dir> add-lecture <section>.json`) so study-quiz can reuse them later without re-reading source text. It is fine if a low-frequency section adds zero examples. Show the pacing menu.

## Q&A / re-teach mode (conversation)

Triggered by any question about the material, or "没听懂".

- Answer exactly what was asked — targeted and concise, in Chinese. Point back to the lecture file ("讲义 3.1 的易错辨析也写了这一点") so the notes remain the single source of truth.
- Re-teaching means a genuinely different path: different analogy, different example, a text sketch — never the lecture's wording again.
- Socratic touches are welcome ("想一想，如果价格翻倍会怎样？——对，……").
- If a question exposes a real gap in the notes, offer to patch the section JSON and re-render.

## After every unit

Lecture generation changes status; Q&A alone does not. Update files immediately, then show the menu. A nudge is fine ("趁热打铁来几道题？") — the learner decides.
