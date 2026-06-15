---
name: study-mindmap
description: >
  Mind-map sub-skill (orchestrated by study-assistant; also usable standalone). Use whenever a chapter knowledge-point mind map needs to be generated or refreshed — the user says "思维导图" "知识图谱" "脑图", or any knowledge point's mastery/status changed (regenerate to refresh colors). Renders knowledge.json into a zero-dependency, offline-capable interactive HTML: collapse/expand, drag & zoom, search, mastery color coding.
---

# Study Mind Map

Render the knowledge tree in `knowledge.json` into an interactive HTML mind map. **Never hand-write the HTML** — run the bundled script; it guarantees identical interaction and coloring regardless of which model invokes it:

```bash
python3 ~/.claude/skills/study-mindmap/scripts/build_mindmap.py <study-dir>/knowledge.json --chapter <N>
python3 ~/.claude/skills/study-mindmap/scripts/build_mindmap.py <study-dir>/knowledge.json --book   # whole-book overview
```

Output: `<study-dir>/mindmaps/chapter-XX.html` (or `book.html`). `open` it in the browser the first time; for subsequent color refreshes just tell the user (in Chinese) to refresh the tab.

Node labels show only the knowledge point's short name — the build script auto-shortens long names (cuts at the first separator, caps length) and shows the full name on hover. Keep knowledge.json point `name` concise (≤ ~12 Chinese chars) so labels read cleanly; structural chapter/section titles stay as-is.

## Precondition: knowledge.json must exist

This skill only renders — it does not split knowledge points. If knowledge.json is missing, build it first (contract in `~/.claude/skills/study-assistant/SKILL.md`, then run validate_workspace.py). When building the list, remember the map's mission: **the user revises the whole chapter from this picture** — every definition, formula, law, and method is its own leaf. A missing point is far worse than an extra one.

## Map features (worth mentioning to the user, in Chinese)

- Click a node to collapse/expand its subtree (collapsed nodes show the hidden count)
- Drag to pan, wheel to zoom; one-click 适应窗口 / 展开全部 / 折叠到小节
- Search box highlights matches and auto-expands their path
- Leaves are colored by mastery: 灰 = 未学, 红 = 薄弱 (1–2), 黄 = 基本 (3), 浅绿 = 熟练 (4), 绿 = 精通 (5); ★ marks high-frequency exam points
- Hovering a leaf shows id, importance, status, mastery, note

## When to regenerate

- After any point's `status` / `mastery` / `note` changes (teaching, quizzing, Feynman checks)
- After the knowledge list itself is revised

Re-running the same command overwrites the file in place; the browser tab just needs a refresh.
