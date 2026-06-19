---
name: study-teach
description: >
  Lecture & explanation sub-skill (orchestrated by study-assistant; also usable standalone). Use when the learner wants a chapter/section/knowledge point taught ("开始讲解" "讲一下第三章" "生成讲义" "继续下一个知识点"), asks a follow-up question about studied content, or says they didn't understand. Generates exactly one high-quality knowledge-point lecture at a time as structured JSON plus HTML/Markdown, then merges all completed points into one audited chapter-level main HTML. Must preserve source formulas, figures/tables, and worked examples when they help understanding.
---

# Teaching: Lecture Notes + Q&A

**Output language: ALL learner-facing content MUST be Simplified Chinese.**

Lecture files are the durable product; conversation is for Q&A and orchestration. Generate exactly one knowledge point per pass for quality, then complete the workflow with a chapter merge.

## File and rendering standards

Use the scripts. Do not hand-write lecture HTML.

- Point JSON: `<study-dir>/internal/lessons/chapter-XX/<point-id>-<name>.json`
- Point HTML/MD: same folder, rendered by `build_lecture.py`
- Chapter assets: `<study-dir>/internal/lessons/chapter-XX/assets/`
- Main chapter HTML: `<study-dir>/open/chapters/chapter-XX.html`, published by `build_chapter_lecture.py --publish <study-dir>`
- Audit reports: `<study-dir>/internal/reports/chapter-XX-audit.md`

Legacy root `lessons/` workspaces are acceptable, but new work should use `internal/lessons/`.

## One-time setup per textbook

Ask once which lecture format to use and store it in `progress.json` as `lecture_format`:

- `obsidian`
- `html`
- `both`

Ask/confirm the teaching mode per section, then use that mode consistently for every point in the section. Default to `progress.json.study_mode`:

- `deep` 深入讲解: source wording, intuition, formal derivation, symbols explained.
- `speedrun` 考试速通: exam conclusion, recognition cues, solving routine, traps.

## Generate one knowledge point per pass

Long generations degrade. Each pass must produce one lecture JSON containing exactly one item in `points`, then render one point HTML/MD. Do not batch a whole section or chapter into one model generation.

1. Read the source passages needed for the selected point from `internal/textbook/chapter-XX.md`.
2. Check `internal/state/exam-style.md` if present.
3. Check the global question-bank frequency before allocating examples:
   ```bash
   python3 ~/.claude/skills/study-quiz/scripts/bank.py <study-dir> stats --point <id1> <id2> ...
   ```
4. Scan the source section for formulas, figures/tables/charts, and examples. If they help understanding, they must appear in the lecture:
   - formulas in LaTeX `$...$` / `$$...$$`, with every symbol explained;
   - source tables as real Markdown tables, not spacing or screenshots;
   - useful figures/charts as `figures[]` with `path`, `caption`, `source`, and `alt`;
   - source examples as `examples[]` with complete solution and `source_ref`.
5. Write one lecture JSON using the schema in `build_lecture.py`. `points` must contain only the selected knowledge point, with the exact id/name from `knowledge.json`; keep the top-level `section` field for chapter grouping.
6. Render:
   ```bash
   python3 ~/.claude/skills/study-teach/scripts/build_lecture.py \
     <study-dir>/internal/lessons/chapter-XX/<point>.json --format <lecture_format>
   ```
7. Update state, regenerate mind map/dashboard, and ingest examples:
   ```bash
   python3 ~/.claude/skills/study-quiz/scripts/bank.py <study-dir> add-lecture <point>.json
   ```

## Lecture JSON expectations

Required top-level fields: `textbook`, `chapter_id`, `chapter_title`, `section`, `mode`, `points`.

Each point needs `id`, `name`, `importance`, and:

- both modes: `exam_focus`, `pitfalls`, `memory_hook`, optional `source_ref`, `figures`, `links`;
- `deep`: `textbook_excerpt`, `intuition`, required `formal`;
- `speedrun`: `key_point`, required `method`.

Examples are optional overall, but not optional when the source material has a worked example that is useful for understanding or exams. Allocate examples in this order:

1. uploaded/source examples and real exam questions;
2. high-frequency points from the global question bank;
3. high-importance/confusable/computational points;
4. medium points only when practice materially helps;
5. low/background points usually get none.

Each example must include `problem` and `solution`; calculation/short-answer examples should include `answer` for auto-checking. Use `source_ref` for textbook/courseware/paper examples; use `source_ref: "讲义原创"` for original examples.

## Figures, tables, and graphs

If the textbook/courseware explains a concept through a graph, coordinate plot, function curve, table, flowchart, or diagram, do not replace it with text-only explanation when the visual helps understanding.

- For source images/figures, use `study-img` to produce a teaching-grade description before writing the lecture.
- For function graphs or comparative statics, generate a clean PNG with `plot_function.py` or another reliable plotting tool and save it under `assets/`.
- Explain every included visual: axes/rows/columns, what changes, what conclusion follows, and how exams transform the visual into formulas or judgments.

## Q&A / re-teach mode

Answer exactly what was asked, in Chinese. Point back to the lecture file so the notes stay the source of truth. If the question exposes a real gap, offer to patch the point JSON and rerender.

Re-teaching must use a different route: different analogy, example, drawing description, or step sequence. Do not merely repeat the lecture wording.

## Chapter aggregation (mandatory for chapter completion)

Immediately after the last knowledge point in a chapter has its lecture JSON/HTML, build the main chapter lecture:

```bash
python3 ~/.claude/skills/study-teach/scripts/build_chapter_lecture.py \
  <study-dir>/internal/lessons/chapter-XX/ --format html --publish <study-dir>
```

Then run:

```bash
python3 ~/.claude/skills/study-assistant/scripts/audit_chapter.py <study-dir> --chapter <N>
```

The merger groups one-point JSON files by their top-level `section` and orders points by id. If the audit reports blockers, modify the relevant point JSON, rerender the point, rerun chapter aggregation, and rerun the audit. Only after the audit passes should the dashboard be refreshed and the chapter presented as complete.

The learner-facing final chapter file is `open/chapters/chapter-XX.html`. Individual point HTML files stay internal.

## After every unit

Lecture generation changes status; Q&A alone does not.

1. Update covered points to `已讲解`.
2. Update `progress.json` and append the log entry.
3. Regenerate the mind map and dashboard.
4. Show the pacing menu.
