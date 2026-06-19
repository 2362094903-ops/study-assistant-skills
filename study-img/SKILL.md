---
name: study-img
description: >
  Image-reading sub-skill (orchestrated by study-assistant; also usable standalone). Use for ANY study material that must be visually inspected: scanned textbook pages, courseware figures/charts/diagrams, photographed exam papers, photos of handwritten answers or notes, and png/jpg/jpeg/gif/webp/bmp files. Supports OCR, teaching-grade figure descriptions, and verbatim handwritten-answer transcription.
---

# Study Image Reading

**Output language: ALL learner-facing content MUST be Simplified Chinese.**

## Try native vision first

Use the available image-reading capability directly when possible.

- If you can see the image, produce the required mode output below.
- If image reading fails or the model has no vision, use the external vision API script.

One failed native attempt per session is enough evidence; do not retry every image.

## External vision API

```bash
python3 ~/.claude/skills/study-img/scripts/recognize.py <image> --mode <mode>
```

First-use configuration: ask for provider type, base URL/API key, and vision model. Store config in `~/.config/study-img/config.json`, `chmod 600`, and never repeat the full API key in conversation.

## Modes

| Scenario | Mode | Required output |
|---|---|---|
| Scanned textbook page / photographed paper / handout | `--mode ocr` | Structured Markdown transcription; formulas as LaTeX; figures as `[图：...]` placeholders with enough detail to locate them. |
| Textbook/courseware figure, coordinate plot, table image, flowchart, chart | `--mode figure` | Teaching-grade description complete enough to redraw or convert into a lecture figure/table. Include axes, labels, variables, trends, data rows, and the conclusion. |
| Learner handwritten answers | `--mode answer` | Verbatim transcription; preserve errors; LaTeX formulas; use `【?】` for illegible characters. |
| Unsure | no mode | Comprehensive recognition. |

## Workflow hookups

- Scanned PDFs: render flagged pages with `extract_pdf.py --render-scanned`, recognize, and merge into `internal/textbook/chapter-XX.md`.
- Image-heavy PPT slides: export with `extract_pptx.py --render-images`, recognize, and merge into `internal/textbook/chapter-XX.md`.
- Lecture figures: when a `[图：...]`, chart, curve, or table is important for understanding, recognize it with `--mode figure`; then study-teach must include the useful visual/table/formula in the lecture JSON with `source_ref`.
- Handwritten answer grading: transcribe with `--mode answer`, show uncertain parts to the learner, then hand to study-quiz for grading.

## Caveats

Vision output can misread formulas and numbers. Cross-check against surrounding text, dimensions, and internal consistency before teaching or grading from it. If a figure/table remains doubtful, say so and ask the learner to confirm from the original.
