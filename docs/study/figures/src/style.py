"""Shared look for every study figure.

    import sys, os; sys.path.insert(0, os.path.dirname(__file__))
    from style import *
    fig, ax = canvas(10, 4)          # diagram canvas in "units" (1 unit = 1 inch)
    box(ax, 0.5, 1, 2, 1, "SigLIP\n비전 인코더", role="vision")
    arrow(ax, (2.5, 1.5), (3.5, 1.5), label="64 토큰")
    save(fig, "08_smolvla_prefix_suffix")   # -> figures/08_smolvla_prefix_suffix.png

Colour = meaning, the same in every document:
    vision   blue    camera, image, perception
    language violet  text, tokens, LLM, instruction
    action   orange  action, control output, policy head
    state    aqua    vehicle state, sensors other than camera, data
    model    yellow  shared backbone / generic network block
    neutral  gray    infrastructure, plumbing, "other"
    bad      red     failure, error, wrong answer (only for that meaning)
    good     green   success, correct answer (only for that meaning)
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)  # docs/study/figures

for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
          "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"):
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e4e3df"

# validated categorical slots (dataviz reference palette, light mode)
C = {
    "blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a", "yellow": "#eda100",
    "magenta": "#e87ba4", "green": "#008300", "violet": "#4a3aa7", "red": "#e34948",
    "gray": "#8a8984",
}
ROLE = {
    "vision": C["blue"], "language": C["violet"], "action": C["orange"],
    "state": C["aqua"], "model": C["yellow"], "neutral": C["gray"],
    "bad": C["red"], "good": C["green"],
}
# chart series order (fixed, never cycled)
SERIES = [C["blue"], C["orange"], C["aqua"], C["yellow"], C["magenta"], C["green"],
          C["violet"], C["red"]]

plt.rcParams.update({
    "font.family": ["Noto Sans CJK JP", "DejaVu Sans"],  # TTC registers as JP; it carries Hangul
    "axes.unicode_minus": False,
    "font.size": 11,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK2,
    "axes.titlecolor": INK,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "legend.frameon": False,
    "lines.linewidth": 2.0,
    "lines.markersize": 7,
})


def tint(hex_color, amount=0.85):
    """Mix a colour toward white (amount 0 = colour, 1 = white)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (round(v + (255 - v) * amount) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def canvas(w, h, title=None):
    """Blank diagram canvas; coordinates are in inches from bottom-left."""
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    if title:
        ax.text(0.25, h - 0.3, title, fontsize=14, fontweight="bold", color=INK,
                va="top", ha="left")
    return fig, ax


def box(ax, x, y, w, h, text="", role="neutral", fill=True, fontsize=11,
        dashed=False, bold=False, sub=None, text_color=None, radius=0.08):
    """Rounded box. role picks the colour (see module doc)."""
    col = ROLE.get(role, role)
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
                       linewidth=1.6, edgecolor=col,
                       facecolor=tint(col, 0.86) if fill else SURFACE,
                       linestyle=(0, (4, 3)) if dashed else "solid", zorder=2, clip_on=False)
    ax.add_patch(p)
    if text:
        ty = y + h / 2 + (0.12 if sub else 0)
        ax.text(x + w / 2, ty, text, ha="center", va="center", fontsize=fontsize,
                color=text_color or INK, fontweight="bold" if bold else "normal",
                zorder=3, linespacing=1.3)
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.2, sub, ha="center", va="center",
                fontsize=fontsize - 2, color=INK2, zorder=3)
    return (x, y, w, h)


def group(ax, x, y, w, h, label=None, role="neutral"):
    """Large dashed container with a small label at top-left."""
    col = ROLE.get(role, role)
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.12",
                       linewidth=1.2, edgecolor=col, facecolor="none",
                       linestyle=(0, (5, 4)), zorder=1, clip_on=False)
    ax.add_patch(p)
    if label:
        ax.text(x + 0.12, y + h - 0.1, label, ha="left", va="top", fontsize=10,
                color=col, fontweight="bold", zorder=3)


def arrow(ax, p1, p2, label=None, color=None, style="-|>", lw=1.6, dashed=False,
          rad=0.0, label_offset=(0, 0.14), fontsize=9.5, both=False):
    """Arrow from p1 to p2 (inches). rad != 0 bends it."""
    a = FancyArrowPatch(p1, p2, arrowstyle="<|-|>" if both else style,
                        mutation_scale=13, linewidth=lw, color=color or INK2,
                        linestyle=(0, (4, 3)) if dashed else "solid",
                        connectionstyle=f"arc3,rad={rad}", zorder=1.5,
                        shrinkA=2, shrinkB=2, clip_on=False)
    ax.add_patch(a)
    if label:
        mx, my = (p1[0] + p2[0]) / 2 + label_offset[0], (p1[1] + p2[1]) / 2 + label_offset[1]
        ax.text(mx, my, label, ha="center", va="bottom", fontsize=fontsize, color=INK2,
                zorder=3, bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none"))


def note(ax, x, y, text, fontsize=9.5, color=None, ha="left", va="center", bold=False):
    ax.text(x, y, text, ha=ha, va=va, fontsize=fontsize, color=color or INK2,
            fontweight="bold" if bold else "normal", zorder=3, linespacing=1.35)


def center(b):
    x, y, w, h = b
    return (x + w / 2, y + h / 2)


def right(b):
    x, y, w, h = b
    return (x + w, y + h / 2)


def left(b):
    x, y, w, h = b
    return (x, y + h / 2)


def top(b):
    x, y, w, h = b
    return (x + w / 2, y + h)


def bottom(b):
    x, y, w, h = b
    return (x + w / 2, y)


def save(fig, name, dpi=200):
    for ax in fig.axes:  # nothing drawn outside the canvas may be cut off
        for t in ax.texts:
            t.set_clip_on(False)
    path = os.path.join(OUT, name + ".png")
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("wrote", os.path.relpath(path, os.path.dirname(OUT)))
    return path
