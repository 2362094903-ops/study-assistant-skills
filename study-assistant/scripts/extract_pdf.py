#!/usr/bin/env python3
"""提取 PDF 文字，标记疑似扫描页，可选将扫描页渲染为 PNG 供 study-img 识别。

用法：
  python3 extract_pdf.py book.pdf -o chapter-03.md                 # 整本提取
  python3 extract_pdf.py book.pdf --pages 45-72 -o chapter-03.md   # 指定页码（1 起算）
  python3 extract_pdf.py book.pdf --pages 45-72 -o ch3.md --render-scanned ./scanned/

输出 md 中每页以 "<!-- page N -->" 注释分隔；疑似扫描页（文字 < 50 字符）写入
"<!-- page N: SCANNED, see scanned/page-N.png -->" 占位，待 OCR 后替换。
结束时在 stderr 打印摘要：总页数、扫描页列表。
"""
import argparse
import pathlib
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("缺少 PyMuPDF，请先运行: pip3 install pymupdf")

SCANNED_THRESHOLD = 50  # 每页提取字符数低于此值视为扫描页


def parse_pages(spec: str, total: int):
    """'45-72' / '3' / '1-5,8,10-12' -> 0 起算页码列表"""
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            pages.extend(range(int(a) - 1, int(b)))
        else:
            pages.append(int(part) - 1)
    return [p for p in pages if 0 <= p < total]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", help="页码范围，1 起算，如 45-72 或 1-5,8")
    ap.add_argument("-o", "--out", required=True, help="输出 markdown 路径")
    ap.add_argument("--render-scanned", metavar="DIR",
                    help="把疑似扫描页渲染为 PNG 存到该目录（150dpi）")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    pages = parse_pages(args.pages, len(doc)) if args.pages else range(len(doc))

    scanned = []
    lines = []
    for p in pages:
        page = doc[p]
        text = page.get_text("text").strip()
        lines.append(f"<!-- page {p + 1} -->")
        if len(text) < SCANNED_THRESHOLD:
            scanned.append(p + 1)
            lines.append(f"<!-- page {p + 1}: SCANNED, 待 OCR -->")
        else:
            lines.append(text)
        lines.append("")

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    if args.render_scanned and scanned:
        rdir = pathlib.Path(args.render_scanned)
        rdir.mkdir(parents=True, exist_ok=True)
        for pno in scanned:
            pix = doc[pno - 1].get_pixmap(dpi=150)
            pix.save(rdir / f"page-{pno}.png")

    print(f"已提取 {len(list(pages))} 页 -> {out}", file=sys.stderr)
    if scanned:
        where = f"，PNG 已存到 {args.render_scanned}" if args.render_scanned else ""
        print(f"疑似扫描页（需 OCR）：{scanned}{where}", file=sys.stderr)
    else:
        print("未发现扫描页。", file=sys.stderr)


if __name__ == "__main__":
    main()
