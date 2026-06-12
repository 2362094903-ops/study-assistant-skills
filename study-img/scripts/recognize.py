#!/usr/bin/env python3
"""学习资料识图：调用视觉模型识别课本扫描页/插图/试卷照片/手写作答。

本脚本是"当前主模型没有视觉能力"时的回退方案——如果主模型本身能看图（多模态），
应直接用 Read 工具读图，无需本脚本。

用法：
  python3 recognize.py page-1.png --mode ocr            # 扫描页/试卷 -> Markdown 文字
  python3 recognize.py figure.png --mode figure         # 插图/图表 -> 教学角度描述
  python3 recognize.py answer.jpg --mode answer         # 学生手写作答 -> 忠实转录（不纠错）
  python3 recognize.py photo.jpg                        # auto：自动判断综合识别
  python3 recognize.py a.png b.png --mode ocr -o out.md # 多张依次识别并写入文件
  python3 recognize.py --show-config                    # 查看当前生效的配置（密钥打码）

API 配置（优先级：命令行参数 > 环境变量 > 配置文件）：
  命令行参数：--provider openai|anthropic  --base-url URL  --api-key KEY  --model NAME
  环境变量：  STUDY_IMG_PROVIDER / STUDY_IMG_BASE_URL / STUDY_IMG_API_KEY / STUDY_IMG_MODEL
  配置文件：  ~/.config/study-img/config.json，例如：
    {"provider": "openai",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "api_key": "sk-xxxx",
     "model": "qwen3.5-flash"}

  provider 说明：
    openai    任何 OpenAI 兼容接口（DashScope/智谱/Moonshot/SiliconFlow/OpenRouter/OpenAI 等），
              base_url 填到 /v1 这一级（脚本自动拼 /chat/completions）
    anthropic Anthropic Messages API，base_url 可省略（默认 https://api.anthropic.com）

仅用 Python 标准库。失败自动重试 2 次。配置缺失时退出码为 2 并打印配置指引。
"""
import argparse
import base64
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

CONFIG_PATH = pathlib.Path.home() / ".config" / "study-img" / "config.json"

PROMPTS = {
    "ocr": (
        "你是课本数字化助手。请将图片中的全部内容完整转录为 Markdown：\n"
        "- 保留标题层级、段落、编号列表\n"
        "- 数学公式用 LaTeX（行内 $...$，独立公式 $$...$$），符号务必准确\n"
        "- 表格转为 Markdown 表格\n"
        "- 插图/示意图的位置用一行 [图：简要描述图的内容] 标注\n"
        "- 不要遗漏脚注、边栏、例题\n"
        "只输出转录结果，不要任何解释性开场白。使用中文。"
    ),
    "figure": (
        "你是考研辅导老师，正在给学生讲解课本里的这张插图/图表。请详细描述：\n"
        "1. 图的类型与主题（坐标图/流程图/结构图/数据图表…）\n"
        "2. 所有文字标注、坐标轴含义、曲线/元素名称、数据数值\n"
        "3. 各元素之间的关系（交点、移动方向、因果链）\n"
        "4. 这张图在说明什么知识点、关键结论是什么\n"
        "公式用 LaTeX。使用中文，描述要完整到'没看过图的人也能在纸上把它画出来'。"
    ),
    "answer": (
        "这是学生的手写作答（备考练习）。请将其完整转录为文字，规则：\n"
        "- 忠实原样转录，包括写错的步骤、算错的数字和划掉的内容（标注[划掉]）——"
        "不要纠错、不要补全、不要改写表述，批改工作由老师完成\n"
        "- 数学公式与符号用 LaTeX（行内 $...$），保留解题步骤的分行与编号\n"
        "- 无法辨认的字写作【?】，没有把握的字在其后加 (?)\n"
        "- 手画的图形/示意图用一行 [图：简要描述画了什么] 标注\n"
        "只输出转录结果，不要任何点评。使用中文。"
    ),
    "auto": (
        "请详细、全面地识别这张图片的所有内容：如果是文字材料请完整转录"
        "（公式用 LaTeX，表格用 Markdown）；如果是图表/插图请详细描述其结构、"
        "标注和含义；混合内容则两者都做。使用中文，不要遗漏任何信息。"
    ),
}

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}

CONFIG_GUIDE = """未配置识图 API。请通过以下任一方式提供配置（优先级从高到低）：
  1) 命令行：--provider openai|anthropic --base-url <URL> --api-key <KEY> --model <模型名>
  2) 环境变量：STUDY_IMG_PROVIDER / STUDY_IMG_BASE_URL / STUDY_IMG_API_KEY / STUDY_IMG_MODEL
  3) 配置文件 ~/.config/study-img/config.json：
     {"provider": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key": "sk-xxxx", "model": "qwen3.5-flash"}
provider=openai 适用于一切 OpenAI 兼容接口（DashScope/智谱/Moonshot/SiliconFlow/OpenRouter 等）；
provider=anthropic 适用于 Anthropic Messages API（base_url 可省略）。"""


def resolve_config(args):
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            sys.exit(f"配置文件 {CONFIG_PATH} 不是合法 JSON，请修复或删除后重新配置。")
    provider = (args.provider or os.environ.get("STUDY_IMG_PROVIDER")
                or cfg.get("provider") or "openai")
    base_url = (args.base_url or os.environ.get("STUDY_IMG_BASE_URL")
                or cfg.get("base_url")
                or ("https://api.anthropic.com" if provider == "anthropic" else None))
    api_key = args.api_key or os.environ.get("STUDY_IMG_API_KEY") or cfg.get("api_key")
    model = args.model or os.environ.get("STUDY_IMG_MODEL") or cfg.get("model")
    if provider not in ("openai", "anthropic"):
        sys.exit(f"不支持的 provider：{provider}（可选 openai / anthropic）")
    if not (base_url and api_key and model):
        print(CONFIG_GUIDE, file=sys.stderr)
        sys.exit(2)
    return provider, base_url.rstrip("/"), api_key, model


def call_openai(base_url, api_key, model, prompt, b64, mime):
    payload = json.dumps({
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
    }).encode()
    req = urllib.request.Request(f"{base_url}/chat/completions", data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return resp["choices"][0]["message"]["content"]


def call_anthropic(base_url, api_key, model, prompt, b64, mime):
    payload = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    }).encode()
    req = urllib.request.Request(f"{base_url}/v1/messages", data=payload, headers={
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    })
    resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return "".join(blk.get("text", "") for blk in resp["content"])


def recognize(path, prompt, conf, retries=2):
    provider, base_url, api_key, model = conf
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    mime = MIME.get(os.path.splitext(path)[1].lower(), "image/png")
    call = call_anthropic if provider == "anthropic" else call_openai
    for attempt in range(retries + 1):
        try:
            return call(base_url, api_key, model, prompt, b64, mime)
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            detail = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    detail = " " + e.read().decode()[:300]
                except Exception:
                    pass
            if attempt == retries:
                raise SystemExit(f"识别失败（{e}{detail}）。请检查配置（--show-config 查看）、网络与模型名。")
            print(f"识别 {path} 失败（{e}），{3 * (attempt + 1)}s 后重试…", file=sys.stderr)
            time.sleep(3 * (attempt + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*", help="图片路径（png/jpg/jpeg/gif/webp/bmp）")
    ap.add_argument("--mode", choices=["ocr", "figure", "answer", "auto"], default="auto")
    ap.add_argument("--prompt", help="自定义提示词（覆盖 --mode）")
    ap.add_argument("-o", "--out", help="结果写入文件，多张图按文件名分节")
    ap.add_argument("--provider", choices=["openai", "anthropic"])
    ap.add_argument("--base-url")
    ap.add_argument("--api-key")
    ap.add_argument("--model")
    ap.add_argument("--show-config", action="store_true", help="显示当前生效配置（密钥打码）后退出")
    args = ap.parse_args()

    conf = resolve_config(args)
    if args.show_config:
        provider, base_url, api_key, model = conf
        masked = api_key[:6] + "…" + api_key[-4:] if len(api_key) > 12 else "***"
        print(f"provider={provider}\nbase_url={base_url}\napi_key={masked}\nmodel={model}\n配置文件路径：{CONFIG_PATH}")
        return
    if not args.images:
        ap.error("缺少图片路径")

    prompt = args.prompt or PROMPTS[args.mode]
    parts = []
    for img in args.images:
        if not os.path.exists(img):
            sys.exit(f"文件不存在：{img}")
        text = recognize(img, prompt, conf)
        parts.append(f"<!-- {os.path.basename(img)} -->\n{text}" if len(args.images) > 1 else text)

    result = "\n\n".join(parts)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"已写入 {args.out}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
