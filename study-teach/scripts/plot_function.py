#!/usr/bin/env python3
"""Plot teaching-grade function graphs for study-teach lecture figures.

Examples:
  python3 plot_function.py --expr "x**2" --x-min -3 --x-max 3 -o assets/quadratic.png
  python3 plot_function.py --curve "NPV=-100+35/(1+x)+35/(1+x)**2" --x-min 0 --x-max .4 -o assets/npv.png
  python3 plot_function.py --curve "低留存=0.08*x" --curve "高留存=0.16*x" --x-min 0 --x-max .3 -o assets/growth.png
"""
import argparse
import math
import pathlib

import numpy as np


SAFE_FUNCS = {
    "abs": np.abs,
    "arccos": np.arccos,
    "arcsin": np.arcsin,
    "arctan": np.arctan,
    "cos": np.cos,
    "e": math.e,
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "maximum": np.maximum,
    "minimum": np.minimum,
    "pi": math.pi,
    "sin": np.sin,
    "sqrt": np.sqrt,
    "tan": np.tan,
}


def parse_curve(raw, fallback_label):
    if "=" in raw:
        label, expr = raw.split("=", 1)
        return label.strip() or fallback_label, expr.strip()
    return fallback_label, raw.strip()


def eval_expr(expr, x):
    expr = expr.replace("^", "**")
    env = dict(SAFE_FUNCS)
    env["x"] = x
    return eval(expr, {"__builtins__": {}}, env)


def configure_fonts():
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = [
        "PingFang SC",
        "Hiragino Sans GB",
        "Microsoft YaHei",
        "SimHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expr", help="single y=f(x) expression; ignored when --curve is used")
    ap.add_argument("--curve", action="append", help="curve expression, optionally label=expr; repeatable")
    ap.add_argument("--x-min", type=float, default=-10)
    ap.add_argument("--x-max", type=float, default=10)
    ap.add_argument("--points", type=int, default=500)
    ap.add_argument("--xlabel", default="x")
    ap.add_argument("--ylabel", default="y")
    ap.add_argument("--title", default="")
    ap.add_argument("--caption", default="")
    ap.add_argument("--grid", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--zero-axes", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    curves = args.curve or []
    if not curves:
        if not args.expr:
            raise SystemExit("provide --expr or at least one --curve")
        curves = [args.expr]
    if args.x_max <= args.x_min:
        raise SystemExit("--x-max must be greater than --x-min")

    import matplotlib.pyplot as plt

    configure_fonts()
    x = np.linspace(args.x_min, args.x_max, max(args.points, 50))
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)

    for idx, raw in enumerate(curves, 1):
        label, expr = parse_curve(raw, f"y{idx}")
        try:
            y = eval_expr(expr, x)
        except Exception as exc:
            raise SystemExit(f"failed to evaluate {label}={expr}: {exc}") from exc
        ax.plot(x, y, linewidth=2.2, label=label)

    if args.zero_axes:
        ax.axhline(0, color="#64748b", linewidth=1, alpha=0.75)
        ax.axvline(0, color="#64748b", linewidth=1, alpha=0.75)
    if args.grid:
        ax.grid(True, color="#e2e8f0", linewidth=0.8)
    ax.set_xlabel(args.xlabel)
    ax.set_ylabel(args.ylabel)
    if args.title:
        ax.set_title(args.title, pad=12)
    if len(curves) > 1 or any("=" in c for c in curves):
        ax.legend(frameon=False)
    if args.caption:
        fig.text(0.5, 0.01, args.caption, ha="center", va="bottom", fontsize=9, color="#475569")
        fig.subplots_adjust(bottom=0.18)
    fig.tight_layout()

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    print(f"generated {out}")


if __name__ == "__main__":
    main()
