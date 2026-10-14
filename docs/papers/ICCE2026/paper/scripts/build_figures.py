#!/usr/bin/env python3
"""Build manuscript figures from the frozen v6 map artifacts.

The script performs manuscript-only analysis.  It does not start ROS 2 or
Gazebo and does not modify the vehicle controller.  Segment summaries mirror
tools/eval/compare_segments.py so every plotted/table value remains traceable to
the existing evaluator.
"""

from __future__ import annotations

import csv
import glob
import json
import math
import os
import statistics as stats
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/navvla-matplotlib")

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


SCRIPT = Path(__file__).resolve()
PAPER = SCRIPT.parents[1]
REPO = SCRIPT.parents[4]
FIG_DIR = PAPER / "figs"
DATA_DIR = PAPER / "data"
EVAL_DIR = REPO / "eval_out"

COLORS = {
    "ink": "#20262d",
    "muted": "#65717d",
    "mid": "#9aa4ad",
    "grid": "#dce1e5",
    "paper": "#fbfcfd",
    "inner": "#0072b2",       # Okabe-Ito blue
    "outer": "#d55e00",       # Okabe-Ito vermillion
    "blue_fill": "#eaf2f8",
    "reference": "#a9b0b6",
    "center": "#d4d8dc",
    "accent": "#2f6f9f",
}

mpl.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "mathtext.fontset": "stixsans",
        "font.size": 7.4,
        "axes.titlesize": 8.0,
        "axes.labelsize": 7.4,
        "xtick.labelsize": 6.8,
        "ytick.labelsize": 6.8,
        "legend.fontsize": 6.8,
        "axes.linewidth": 0.65,
        "axes.edgecolor": COLORS["ink"],
        "axes.labelcolor": COLORS["ink"],
        "xtick.color": COLORS["ink"],
        "ytick.color": COLORS["ink"],
        "xtick.direction": "out",
        "ytick.direction": "out",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def load_reference_geometry():
    """Reconstruct the teacher-corpus lane reference used by the evaluator."""
    with (REPO / "src/sant_vla_pkg/config/track_paths.json").open() as handle:
        center = json.load(handle)["ring_center"]
    n_points = len(center)

    def nearest_index(x, y):
        return min(
            range(n_points),
            key=lambda index: (center[index][0] - x) ** 2
            + (center[index][1] - y) ** 2,
        )

    def lateral(x, y, index):
        nxt = (index + 1) % n_points
        tx = center[nxt][0] - center[index][0]
        ty = center[nxt][1] - center[index][1]
        norm = math.hypot(tx, ty) or 1.0
        return (tx * (y - center[index][1]) - ty * (x - center[index][0])) / norm

    bins = {
        "lane1": [[] for _ in range(n_points)],
        "lane2": [[] for _ in range(n_points)],
    }
    corpus = REPO / "src/sant_vla_pkg/data_v3y/packed_v3y"
    for episode_name in glob.glob(str(corpus / "*")):
        episode = Path(episode_name)
        if not episode.is_dir():
            continue
        try:
            with (episode / "meta.json").open() as handle:
                lane = (json.load(handle).get("intent_slots") or {}).get("lane")
            if lane not in bins:
                continue
            with (episode / "resampled_10hz.jsonl").open() as handle:
                for line in handle:
                    row = json.loads(line)
                    index = nearest_index(row["x"], row["y"])
                    bins[lane][index].append(lateral(row["x"], row["y"], index))
        except FileNotFoundError:
            continue

    reference = {}
    for lane, lane_bins in bins.items():
        medians = [stats.median(values) if values else None for values in lane_bins]
        for index, value in enumerate(medians):
            if value is not None:
                continue
            for distance in range(1, n_points):
                neighbors = [
                    candidate
                    for candidate in (
                        medians[(index - distance) % n_points],
                        medians[(index + distance) % n_points],
                    )
                    if candidate is not None
                ]
                if neighbors:
                    medians[index] = sum(neighbors) / len(neighbors)
                    break
        reference[lane] = medians
    return center, nearest_index, lateral, reference


def segment_offsets(track, lane, nearest_index, lateral, reference, segment_size=20):
    per_segment = {}
    for x, y in track:
        index = nearest_index(x, y)
        if reference[lane][index] is None:
            continue
        per_segment.setdefault(index // segment_size, []).append(
            lateral(x, y, index) - reference[lane][index]
        )
    return {
        segment: stats.median(values)
        for segment, values in per_segment.items()
        if len(values) >= 5
    }


def load_artifact(path, nearest_index, lateral, reference):
    with path.open() as handle:
        records = json.load(handle)
    target = next(record for record in records if "DIFFERENT" in record["case"])
    tracks = {"inner": target["track_a"], "outer": target["track_b"]}
    offsets = {
        "inner": segment_offsets(
            tracks["inner"], "lane1", nearest_index, lateral, reference
        ),
        "outer": segment_offsets(
            tracks["outer"], "lane2", nearest_index, lateral, reference
        ),
    }
    return {"tracks": tracks, "offsets": offsets}


def teacher_path(center, offsets):
    path = []
    n_points = len(center)
    for index, ((x, y), offset) in enumerate(zip(center, offsets)):
        nxt = (index + 1) % n_points
        tx = center[nxt][0] - x
        ty = center[nxt][1] - y
        norm = math.hypot(tx, ty) or 1.0
        path.append((x - ty * offset / norm, y + tx * offset / norm))
    return path


def stage_box(ax, x, width, stage, title, detail, highlighted=False):
    """Draw one stage in the left-to-right system diagram."""
    y, height = 0.37, 0.40
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.006,rounding_size=0.008",
        linewidth=0.75,
        edgecolor=COLORS["mid"],
        facecolor=COLORS["blue_fill"] if highlighted else "white",
    )
    ax.add_patch(box)
    ax.add_patch(
        Rectangle(
            (x, y + height - 0.018),
            width,
            0.018,
            linewidth=0,
            facecolor=COLORS["accent"] if highlighted else COLORS["mid"],
        )
    )
    ax.text(
        x + width / 2,
        0.86,
        stage.upper(),
        ha="center",
        va="center",
        fontsize=5.8,
        weight="bold",
        color=COLORS["muted"],
    )
    ax.text(
        x + width / 2,
        y + 0.28,
        title,
        ha="center",
        va="center",
        fontsize=7.2,
        weight="bold",
        color=COLORS["ink"],
    )
    ax.text(
        x + width / 2,
        y + 0.13,
        detail,
        ha="center",
        va="center",
        fontsize=6.2,
        linespacing=1.15,
        color=COLORS["muted"],
    )
    return x + width


def arrow(ax, start, end, color=None, connectionstyle="arc3,rad=0"):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=7,
            linewidth=0.85,
            color=color or COLORS["muted"],
            connectionstyle=connectionstyle,
            shrinkA=1,
            shrinkB=1,
        )
    )


def build_pipeline_figure():
    fig, ax = plt.subplots(figsize=(7.05, 1.55))
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    stages = [
        (
            0.010,
            0.145,
            "Observation",
            "Policy input",
            r"$I_t$  front RGB" "\n" r"$\ell$  instruction  |  $\mathbf{s}_t\in\mathbb{R}^3$",
            False,
        ),
        (0.180, 0.120, "Transport", "ROS 2 bridge", "JPEG at 10 Hz\nZeroMQ", False),
        (0.325, 0.135, "Inference", r"SmolVLA $\pi_\theta$", "frozen v6-60K\nflow matching", True),
        (0.485, 0.135, "Action", r"$30\times\Delta\mathrm{SE}(2)$", "3.0-s horizon\n5-step splice", True),
        (0.645, 0.165, "Execution", "Queue executor", r"replay $\kappa_i$  |  preview $\hat{\kappa}_t$", True),
        (0.835, 0.155, "Plant", "Gazebo vehicle", r"/cmd_vel" "\n" r"$(v_t,\omega_t)$", False),
    ]
    edges = []
    for x, width, stage, title, detail, highlighted in stages:
        edges.append((x, stage_box(ax, x, width, stage, title, detail, highlighted)))
    for (_, right), (left, _) in zip(edges[:-1], edges[1:]):
        arrow(ax, (right + 0.004, 0.57), (left - 0.004, 0.57))
    arrow(
        ax,
        (0.910, 0.37),
        (0.082, 0.37),
        color=COLORS["accent"],
        connectionstyle="arc3,rad=-0.17",
    )
    ax.text(
        0.50,
        0.075,
        r"closed-loop feedback: $I_{t+1},\,\mathbf{s}_{t+1}$",
        ha="center",
        fontsize=6.3,
        color=COLORS["accent"],
    )
    fig.savefig(FIG_DIR / "fig1_pipeline.pdf", bbox_inches=None, pad_inches=0)
    plt.close(fig)


def build_trajectory_figure(artifacts, center, reference):
    """Plot every saved target trajectory without selecting a representative run."""
    ref_paths = {
        "inner": teacher_path(center, reference["lane1"]),
        "outer": teacher_path(center, reference["lane2"]),
    }
    fig, axes = plt.subplots(1, 2, figsize=(7.05, 3.40), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.12, top=0.865, wspace=0.11)

    all_points = list(center)
    for path in ref_paths.values():
        all_points.extend(path)
    for artifact in artifacts.values():
        for track in artifact["tracks"].values():
            all_points.extend(track)
    x_values = [point[0] for point in all_points]
    y_values = [point[1] for point in all_points]
    x_limits = (min(x_values) - 1.2, max(x_values) + 1.2)
    y_limits = (min(y_values) - 1.2, max(y_values) + 1.2)

    lane_style = {
        "inner": (COLORS["inner"], "o"),
        "outer": (COLORS["outer"], "^"),
    }
    run_style = {"r1": "-", "r2": (0, (6, 2.4))}
    for ax, mode, title in zip(
        axes,
        ("replay", "preview"),
        ("(a) Direct replay", "(b) Queue preview"),
    ):
        ax.set_facecolor(COLORS["paper"])
        center_x, center_y = zip(*center)
        ax.plot(center_x, center_y, color=COLORS["center"], linestyle=":", linewidth=0.7, zorder=0)
        for path in ref_paths.values():
            path_x, path_y = zip(*path)
            ax.plot(path_x, path_y, color=COLORS["reference"], linewidth=1.15, zorder=1)
        for lane in ("inner", "outer"):
            color, marker = lane_style[lane]
            for replicate in ("r1", "r2"):
                track = artifacts[(mode, replicate)]["tracks"][lane]
                track_x, track_y = zip(*track)
                ax.plot(
                    track_x,
                    track_y,
                    color=color,
                    linestyle=run_style[replicate],
                    linewidth=1.0,
                    marker=marker,
                    markersize=2.4,
                    markevery=130,
                    markerfacecolor="white" if replicate == "r2" else color,
                    markeredgecolor=color,
                    markeredgewidth=0.65,
                    alpha=0.96,
                    zorder=2,
                )
        start = artifacts[(mode, "r1")]["tracks"]["inner"][0]
        ax.scatter(*start, marker="*", s=34, facecolor=COLORS["ink"], edgecolor="white", linewidth=0.5, zorder=4)
        ax.annotate(
            "start",
            xy=start,
            xytext=(4, 5),
            textcoords="offset points",
            fontsize=6.0,
            color=COLORS["ink"],
        )
        ax.set_title(title, loc="left", weight="bold", pad=5)
        ax.set_xlim(*x_limits)
        ax.set_ylim(*y_limits)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(color=COLORS["grid"], linewidth=0.42, linestyle=":")
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlabel("Global x (m)", labelpad=2)
    axes[0].set_ylabel("Global y (m)", labelpad=3)

    legend_handles = [
        Line2D([0], [0], color=COLORS["inner"], marker="o", markersize=3.5, linewidth=1.0, label="Inner target"),
        Line2D([0], [0], color=COLORS["outer"], marker="^", markersize=3.5, linewidth=1.0, label="Outer target"),
        Line2D([0], [0], color=COLORS["ink"], linestyle="-", linewidth=1.0, label="r1"),
        Line2D([0], [0], color=COLORS["ink"], linestyle=(0, (6, 2.4)), linewidth=1.0, label="r2"),
        Line2D([0], [0], color=COLORS["reference"], linewidth=1.15, label="Teacher reference"),
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.53, 0.985),
        ncol=5,
        frameon=False,
        handlelength=2.4,
        columnspacing=1.25,
    )
    fig.savefig(FIG_DIR / "fig2_executor.pdf", bbox_inches=None, pad_inches=0)
    plt.close(fig)


def write_summary_csv(artifacts):
    with (DATA_DIR / "executor_summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "mode",
                "artifact",
                "inner_median_abs_m",
                "inner_max_abs_m",
                "inner_segments_over_0p5",
                "outer_median_abs_m",
                "outer_max_abs_m",
                "outer_segments_over_0p5",
                "combined_segments_over_0p5",
            ]
        )
        for mode in ("replay", "preview"):
            for replicate in ("r1", "r2"):
                offsets = artifacts[(mode, replicate)]["offsets"]
                inner = [abs(value) for value in offsets["inner"].values()]
                outer = [abs(value) for value in offsets["outer"].values()]
                writer.writerow(
                    [
                        mode,
                        replicate,
                        f"{stats.median(inner):.6f}",
                        f"{max(inner):.6f}",
                        sum(value > 0.5 for value in inner),
                        f"{stats.median(outer):.6f}",
                        f"{max(outer):.6f}",
                        sum(value > 0.5 for value in outer),
                        sum(value > 0.5 for value in inner + outer),
                    ]
                )


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    center, nearest_index, lateral, reference = load_reference_geometry()
    paths = {
        ("replay", "r1"): EVAL_DIR / "v6r1_map.json",
        ("replay", "r2"): EVAL_DIR / "v6r2_map.json",
        ("preview", "r1"): EVAL_DIR / "v6pv1_map.json",
        ("preview", "r2"): EVAL_DIR / "v6pv2_map.json",
    }
    artifacts = {
        key: load_artifact(path, nearest_index, lateral, reference)
        for key, path in paths.items()
    }
    build_pipeline_figure()
    build_trajectory_figure(artifacts, center, reference)
    write_summary_csv(artifacts)
    print(f"wrote {FIG_DIR / 'fig1_pipeline.pdf'}")
    print(f"wrote {FIG_DIR / 'fig2_executor.pdf'}")
    print(f"wrote {DATA_DIR / 'executor_summary.csv'}")


if __name__ == "__main__":
    main()
