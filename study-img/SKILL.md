---
name: study-img
description: >
  Image-reading sub-skill (orchestrated by study-assistant; also usable standalone). Use for ANY material that must be "seen" during study: scanned textbook pages, textbook figures/charts/diagrams, photographed exam papers, photos of handwritten answers or notes, and any png/jpg/jpeg/gif/webp/bmp file. Strategy: if the current model has native vision, just look (Read tool); otherwise call the vision-model API the user configured (OpenAI-compatible or Anthropic format), guiding configuration on first use.
---

# Study Image Reading

**Output language: ALL learner-facing content MUST be in Simplified Chinese.**

## Step 1: try native vision first (zero config, zero cost)

Use the Read tool on the image file:

- **You can perceive the image** (the model is multimodal) → work directly from what you see; the bundled script is unnecessary. Still follow the per-scenario output requirements in "Modes" below (scanned pages get a full transcription with LaTeX formulas; handwritten answers are transcribed verbatim without corrections; figures get a teaching-grade description).
- **Read errors out or you cannot perceive the image** → the model has no vision; go to step 2. One failed attempt per session is enough evidence — don't retry on every image.

## Step 2: external vision API (script)

```bash
python3 ~/.claude/skills/study-img/scripts/recognize.py <image> --mode <mode>
```

### First use: configuration walkthrough

The script uses the **user's own** vision-model API. With no configuration it exits with code 2 and prints a guide — at that point ask the user for three things (in Chinese):

1. **API type**: OpenAI-compatible (DashScope/Zhipu/Moonshot/SiliconFlow/OpenRouter/OpenAI — almost everything) or Anthropic;
2. **base_url and api_key** (base_url optional for Anthropic);
3. **vision model name** (e.g. qwen3.5-flash, glm-4v-flash, claude-sonnet-4-6).

Write the config to `~/.config/study-img/config.json` (path also shown by `recognize.py --show-config`), `chmod 600`, then verify with one real image. Configure once. **Never repeat the user's full API key back in conversation.** The file lives outside the skill directory: it survives skill updates and can never be committed to git.

Environment variables (`STUDY_IMG_PROVIDER/BASE_URL/API_KEY/MODEL`) and CLI flags also work; precedence: CLI > env > config file.

## Modes

| Scenario | Mode | Output |
|---|---|---|
| Scanned textbook page, photographed paper/handout/notes | `--mode ocr` | Structured Markdown transcription; formulas as LaTeX; figures placeholdered as `[图：…]` |
| Textbook figure, coordinate plot, flowchart, data chart | `--mode figure` | Teaching-grade description (complete enough to redraw on paper) |
| Photo of the learner's handwritten answers | `--mode answer` | Verbatim transcription (errors preserved, no corrections), LaTeX formulas, 【?】 for illegible characters |
| Unsure | no mode (auto) | Comprehensive recognition |

Custom needs via `--prompt "..."` (e.g. "只提取第二大题"). Multiple images in one call are output in sections by filename; `-o out.md` writes to a file. Under native vision the same mode requirements apply — they define what the deliverable looks like, not who looks at the image.

## Workflow hookups

- **Scanned PDFs**: first `~/.claude/skills/study-assistant/scripts/extract_pdf.py --render-scanned` to render flagged pages to PNG, then recognize per this skill (native or `--mode ocr`), and merge results back over the `<!-- page N: SCANNED -->` placeholders in the chapter md.
- **Photographed exam papers**: transcribe per ocr requirements, hand to study-quiz for style analysis.
- **Handwritten answer grading**: transcribe per answer requirements, hand to study-quiz for grading. Transcription must be verbatim — the learner's mistakes are exactly what grading needs — so correction at the recognition stage is forbidden.
- **`[图：…]` markers during lectures**: when the figure carries key content and the source page is locatable (e.g. a PDF page), render it and recognize per figure requirements, then teach from the description.

## Caveats

- External-API results are another model's account; formulas and numbers occasionally come out wrong. Cross-check against context (dimensional sanity, internal consistency) before teaching or quizzing from them; flag doubtful spots to the user ("此处来自图片识别，建议对照原图确认").
- On network failure the script retries twice; if it still fails, tell the user and continue with the parts of the flow that don't depend on the image — never deadlock the study session.
