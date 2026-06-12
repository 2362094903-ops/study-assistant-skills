---
name: study-teach
description: >
  Lecture & explanation sub-skill (orchestrated by study-assistant; also usable standalone). Use when the learner wants a chapter/section taught ("开始讲解" "讲一下第三章" "生成讲义" "继续下一节"), asks a follow-up question about studied content, or says they didn't understand ("给我讲讲X" "没听懂，重讲一遍"). Default mode generates complete section-by-section lecture notes — Obsidian Markdown and/or interactive HTML with rendered math, one worked example per knowledge point; conversation is reserved for targeted Q&A and re-teaching.
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

### Generate one SECTION per pass — never a whole chapter

Long generations degrade toward the end. One section (3.1, 3.2, ...) at a time; the learner reads it, asks questions, then requests the next.

1. Read the section's source text in `textbook/` — lectures must stay faithful to the textbook, exams grade against it. Check `exam-style.md` if present; `exam_focus` fields must cite it.
2. Write the lecture as JSON to `lessons/chapter-XX/<section>.json`, schema documented at the top of `~/.claude/skills/study-teach/scripts/build_lecture.py`. Content contract per knowledge point (every point of this section in knowledge.json must appear, with the same ids):
   - `exam_focus` — 1–2 sentences: importance and typical question types (cite exam-style.md when it exists).
   - `intuition` — daily-life example or analogy; state where the analogy breaks so it is never mistaken for the definition.
   - `formal` — textbook-grade statement. LaTeX for every formula; explain every symbol; include the derivation when the subject demands it (full derivation for math subjects, logic chain for humanities).
   - `example` — REQUIRED: one representative worked problem with a complete solution. It renders as click-to-expand, so the solution must be complete enough to self-check against.
   - `pitfalls` — what it gets confused with, where exams set traps; contrast explicitly.
   - `memory_hook` — mnemonic / framework; for humanities subjects add a 3–5 bullet recitation version.
   - `links` — related point ids.
   - Length matches weight: a minor concept ≈ 200–400 Chinese characters across fields; a core theorem ≈ 600–1000. Never pad small points.
3. Render (the script validates the JSON and fails loudly on missing required fields):

```bash
python3 ~/.claude/skills/study-teach/scripts/build_lecture.py <section>.json --format <lecture_format>
```

4. Deliver: `open` the HTML, or for Obsidian give the file path inside the vault. In conversation say only 2–3 Chinese sentences: what the section covers, the 1–2 points that deserve the most attention, and a reminder that solutions are collapsed — attempt first.
5. Update state: covered points `status` → 已讲解; progress.json (`current_point`, `next_action`, one log entry); regenerate the mind map; ingest the section's examples into the question bank (`python3 ~/.claude/skills/study-quiz/scripts/bank.py <study-dir> add-lecture <section>.json`) so study-quiz can reuse them later without re-reading source text. Show the pacing menu.

## Q&A / re-teach mode (conversation)

Triggered by any question about the material, or "没听懂".

- Answer exactly what was asked — targeted and concise, in Chinese. Point back to the lecture file ("讲义 3.1 的易错辨析也写了这一点") so the notes remain the single source of truth.
- Re-teaching means a genuinely different path: different analogy, different example, a text sketch — never the lecture's wording again.
- Socratic touches are welcome ("想一想，如果价格翻倍会怎样？——对，……").
- If a question exposes a real gap in the notes, offer to patch the section JSON and re-render.

## After every unit

Lecture generation changes status; Q&A alone does not. Update files immediately, then show the menu. A nudge is fine ("趁热打铁来几道题？") — the learner decides.
