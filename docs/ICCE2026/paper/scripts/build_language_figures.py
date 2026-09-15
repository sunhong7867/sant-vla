#!/usr/bin/env python3
"""Build the ICCE 2026 language-conditioned driving figures.

Only frozen experiment artifacts are read.  The script does not start ROS 2,
Gazebo, or a policy server, and it does not alter controller or model code.
"""

from __future__ import annotations

import csv
import json
import os
import re
import statistics
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/navvla-icce2026-mpl")

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


SCRIPT = Path(__file__).resolve()
PAPER = SCRIPT.parents[1]
REPO = SCRIPT.parents[4]
FIG_DIR = PAPER / "figs"
DATA_DIR = PAPER / "data"

MATCHED_PATH = REPO / "eval_out/icce2026/v6_language_chunks_matched_wording.json"
FACTORIAL_DIR = REPO / "eval_out/icce2026_factorial"
FACTORIAL_SOURCES = {
    "baseline": ("baseline_template.json", False, (0, 0, 0), "Base"),
    "template-only": ("baseline_template.json", True, (1, 0, 0), "T"),
    "lane-only": ("lane_speed.json", False, (0, 1, 0), "L"),
    "speed-only": ("lane_speed.json", True, (0, 0, 1), "S"),
    "template-lane": ("template_lane_speed.json", False, (1, 1, 0), "T+L"),
    "template-speed": ("template_lane_speed.json", True, (1, 0, 1), "T+S"),
    "lane-speed": ("lane_speed_all.json", False, (0, 1, 1), "L+S"),
    "all-reserved": ("lane_speed_all.json", True, (1, 1, 1), "T+L+S"),
}
FACTORIAL_EFFECTS = [
    ("T", (0,), "Template (T)"),
    ("L", (1,), "Lane replacement (L)"),
    ("S", (2,), "Speed term (S)"),
    ("T_x_L", (0, 1), "T × L"),
    ("T_x_S", (0, 2), "T × S"),
    ("L_x_S", (1, 2), "L × S"),
    ("T_x_L_x_S", (0, 1, 2), "T × L × S"),
]
CLOSED_LOOP_PATHS = {
    "familiar-wording": [
        REPO / "eval_out/icce26_bal_familiar_outer_ab_map.json",
        REPO / "eval_out/icce26_bal_familiar_outer_ba_map.json",
        REPO / "eval_out/icce26_bal_familiar_inner_ab_map.json",
        REPO / "eval_out/icce26_bal_familiar_inner_ba_map.json",
    ],
    "test-wording": [
        REPO / "eval_out/icce26_bal_test_outer_ab_map.json",
        REPO / "eval_out/icce26_bal_test_outer_ba_map.json",
        REPO / "eval_out/icce26_bal_test_inner_ab_map.json",
        REPO / "eval_out/icce26_bal_test_inner_ba_map.json",
    ],
}
TRACK_PATH = REPO / "src/sant_vla_pkg/config/track_paths.json"

EXPECTED_CONTRACT = {
    "state_steer_source": "zero",
    "goal_conditioning": False,
    "rate_hz": 10.0,
    "chunk_len": 30,
    "refill_at": 0.3,
    "splice_overlap": 5,
    "seed": 0,
    "max_speed": 2.25,
    "speed_scale": 1.0,
    "speed_slew": 0.08,
    "track_mode": "replay",
    "curv_gain_lo": 1.0,
    "curv_boost": 1.0,
    "curv_slow_alat": 0.0,
}
EXPECTED_SENTENCES = {
    "familiar-wording": {
        "Start driving in the inner lane, at a normal speed.",
        "Start driving in the outer lane, at a normal speed.",
    },
    "test-wording": {
        "Roam the track in the innermost lane, at a regular speed.",
        "Roam the track in the outermost lane, at a regular speed.",
    },
}
START_LANE = {"inner": "lane1", "outer": "lane2"}

EXECUTOR_DT = 0.1
EXECUTOR_MAX_SPEED = 2.25
EXECUTOR_SPEED_SLEW = 0.08
EXECUTOR_SIM_WHEEL_BASE = 2.86
EXECUTOR_SIM_MAX_STEER = 0.6
EXECUTOR_MAX_CURVATURE = (
    np.tan(EXECUTOR_SIM_MAX_STEER) / EXECUTOR_SIM_WHEEL_BASE
)
FACTORIAL_BOOTSTRAP_REPEATS = 50000
FACTORIAL_BOOTSTRAP_SEED = 20260901

INK = "#20262d"
MUTED = "#626d78"
GRID = "#d8dde2"
BLUE = "#0072b2"
ORANGE = "#d55e00"
GREEN = "#009e73"
PURPLE = "#7b61a8"
LIGHT_BLUE = "#e8f2f8"
LIGHT_GREEN = "#e8f5ef"
LIGHT_ORANGE = "#fbefe8"

mpl.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 7.2,
        "axes.titlesize": 8.1,
        "axes.labelsize": 7.2,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "legend.fontsize": 6.4,
        "axes.linewidth": 0.65,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def raw_action_path(actions):
    """Compose the stored incremental SE(2) actions, including lateral dy."""
    x = y = yaw = 0.0
    path = []
    for dx, dy, dyaw in np.asarray(actions, dtype=float):
        cosine, sine = np.cos(yaw), np.sin(yaw)
        x += cosine * dx - sine * dy
        y += sine * dx + cosine * dy
        yaw += dyaw
        path.append((x, y))
    return np.asarray(path, dtype=float)


def executor_action_path(actions):
    """Apply the recorded replay contract, then integrate constant twists."""
    x = y = yaw = 0.0
    previous_speed = 0.0
    path = []
    for dx, _dy, dyaw in np.asarray(actions, dtype=float):
        raw_speed = dx / EXECUTOR_DT
        raw_yaw_rate = dyaw / EXECUTOR_DT
        curvature = (
            raw_yaw_rate / raw_speed if abs(raw_speed) > 1e-3 else None
        )

        speed = float(np.clip(raw_speed, -EXECUTOR_MAX_SPEED,
                              EXECUTOR_MAX_SPEED))
        speed = float(np.clip(
            speed,
            previous_speed - EXECUTOR_SPEED_SLEW,
            previous_speed + EXECUTOR_SPEED_SLEW,
        ))
        if curvature is None:
            yaw_rate = raw_yaw_rate
        else:
            curvature = float(np.clip(
                curvature, -EXECUTOR_MAX_CURVATURE,
                EXECUTOR_MAX_CURVATURE,
            ))
            yaw_rate = curvature * speed

        if abs(yaw_rate) > 1e-12:
            next_yaw = yaw + yaw_rate * EXECUTOR_DT
            radius = speed / yaw_rate
            x += radius * (np.sin(next_yaw) - np.sin(yaw))
            y -= radius * (np.cos(next_yaw) - np.cos(yaw))
            yaw = next_yaw
        else:
            x += speed * EXECUTOR_DT * np.cos(yaw)
            y += speed * EXECUTOR_DT * np.sin(yaw)
        previous_speed = speed
        path.append((x, y))
    return np.asarray(path, dtype=float)


def path_rms_between(first, second):
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    if first.shape != second.shape or first.ndim != 2 or first.shape[1] != 2:
        raise ValueError(
            f"path shape mismatch: first={first.shape}, second={second.shape}"
        )
    separation = np.linalg.norm(first - second, axis=1)
    return float(np.sqrt(np.mean(separation * separation)))


def load_factorial_cells():
    """Load the eight wording cells and enforce their paired-observation design."""
    reports = {
        filename: load_json(FACTORIAL_DIR / filename)
        for filename in {source[0] for source in FACTORIAL_SOURCES.values()}
    }
    checkpoints = {report["checkpoint"] for report in reports.values()}
    episode_roots = {report["episodes_dir"] for report in reports.values()}
    frames = {int(report["summary"]["frame_index"]) for report in reports.values()}
    seeds = {
        int(report["summary"]["seeds_per_mean"]) for report in reports.values()
    }
    if not (
        len(checkpoints) == len(episode_roots) == len(frames) == len(seeds) == 1
    ):
        raise ValueError("factorial reports do not share one evaluation contract")

    reference = None
    cells = {}
    for condition, (filename, secondary, factors, short_label) in (
        FACTORIAL_SOURCES.items()
    ):
        report = reports[filename]
        observed_condition = (
            report["summary"]["secondary"]["condition"]
            if secondary else report["condition"]
        )
        if observed_condition != condition:
            raise ValueError(
                f"{filename}: condition {observed_condition!r}, expected "
                f"{condition!r}"
            )
        pairs = report["pairs"]
        if len(pairs) != 20 or report["summary"]["n_groups"] != len(pairs):
            raise ValueError(f"{filename}/{condition}: expected 20 observations")
        identity = [
            (row["group"], row["frame"], tuple(row["state"])) for row in pairs
        ]
        if len({item[0] for item in identity}) != len(identity):
            raise ValueError(f"{filename}: duplicate counterfactual group")
        if reference is None:
            reference = identity
        elif identity != reference:
            raise ValueError(
                f"{filename}/{condition}: observations differ from baseline"
            )

        expected_override = (
            report["secondary_instruction_override"]
            if secondary else report["instruction_override"]
        )
        rows = []
        for top_level in pairs:
            row = top_level["secondary"] if secondary else top_level
            if (
                row["instruction_lane1"] != expected_override["lane1"]
                or row["instruction_lane2"] != expected_override["lane2"]
            ):
                raise ValueError(
                    f"{filename}/{condition}: instruction override mismatch"
                )
            action_means = row["action_means"]
            lane1 = np.asarray(action_means["lane1"], dtype=float)
            lane2 = np.asarray(action_means["lane2"], dtype=float)
            repeated_lane1 = np.asarray(
                action_means["same_instruction"], dtype=float
            )
            if any(
                action.shape != (30, 3)
                for action in (lane1, lane2, repeated_lane1)
            ):
                raise ValueError(
                    f"{filename}/{condition}: expected 30x3 action means"
                )

            language_raw = float(row["language"]["path_rms_m"])
            floor_raw = float(row["same_instruction_noise"]["path_rms_m"])
            recomputed_language = path_rms_between(
                raw_action_path(lane1), raw_action_path(lane2)
            )
            recomputed_floor = path_rms_between(
                raw_action_path(lane1), raw_action_path(repeated_lane1)
            )
            if not (
                np.isclose(language_raw, recomputed_language, atol=2e-6, rtol=0)
                and np.isclose(floor_raw, recomputed_floor, atol=2e-6, rtol=0)
            ):
                raise ValueError(
                    f"{filename}/{condition}: stored raw metric does not match "
                    "the saved action means"
                )

            language_executor = path_rms_between(
                executor_action_path(lane1), executor_action_path(lane2)
            )
            floor_executor = path_rms_between(
                executor_action_path(lane1),
                executor_action_path(repeated_lane1),
            )
            values = (
                language_raw,
                floor_raw,
                language_executor,
                floor_executor,
            )
            if not all(np.isfinite(value) and value > 0.0 for value in values):
                raise ValueError(
                    f"{filename}/{condition}: non-positive path separation"
                )
            rows.append(
                {
                    "group": top_level["group"],
                    "language_raw_se2_m": language_raw,
                    "floor_lane1_raw_se2_m": floor_raw,
                    "language_executor_m": language_executor,
                    "floor_lane1_executor_m": floor_executor,
                }
            )
        cells[condition] = {
            "condition": condition,
            "short_label": short_label,
            "factors": {name: value for name, value in zip("TLS", factors)},
            "source": str((FACTORIAL_DIR / filename).relative_to(REPO)),
            "instruction_lane1": expected_override["lane1"],
            "instruction_lane2": expected_override["lane2"],
            "rows": rows,
        }
    return cells, {
        "checkpoint": next(iter(checkpoints)),
        "episodes_dir": next(iter(episode_roots)),
        "frame_index": next(iter(frames)),
        "observation_sample_seed": 20260901,
        "observation_sample_seed_source": "probe script default used for the recorded run",
        "seeds_per_mean": next(iter(seeds)),
        "n_observations": len(reference),
        "observation_speed_range_mps": [
            min(float(item[2][0]) for item in reference),
            max(float(item[2][0]) for item in reference),
        ],
    }


def _factorial_effect_summary(values, factors, bootstrap_indices):
    """Return standard high-minus-low effects for a saturated 2^3 design."""
    summaries = []
    for identifier, axes, label in FACTORIAL_EFFECTS:
        weights = np.prod(2 * factors[:, axes] - 1, axis=1)
        per_observation = np.sum(values * weights[None, :], axis=1) / 4.0
        estimate = float(np.mean(per_observation))
        bootstrap = np.mean(per_observation[bootstrap_indices], axis=1)
        interval = np.quantile(bootstrap, [0.025, 0.975])
        summaries.append(
            {
                "effect": identifier,
                "label": label,
                "order": len(axes),
                "estimate_log2": estimate,
                "bootstrap_95_ci_log2": [float(value) for value in interval],
                "multiplicative_change": float(2.0 ** estimate),
                "multiplicative_change_95_ci": [
                    float(2.0 ** value) for value in interval
                ],
            }
        )
    return summaries


def analyze_factorial_cells(cells, metadata):
    ordered = [cells[condition] for condition in FACTORIAL_SOURCES]
    factors = np.asarray(
        [[cell["factors"][name] for name in "TLS"] for cell in ordered],
        dtype=int,
    )
    groups = [row["group"] for row in ordered[0]["rows"]]
    for cell in ordered[1:]:
        if [row["group"] for row in cell["rows"]] != groups:
            raise ValueError("factorial cell row order is not paired")

    metric_keys = {
        "raw_se2": ("language_raw_se2_m", "floor_lane1_raw_se2_m"),
        "bridge_transform": (
            "language_executor_m",
            "floor_lane1_executor_m",
        ),
    }
    rng = np.random.default_rng(FACTORIAL_BOOTSTRAP_SEED)
    bootstrap_indices = rng.integers(
        0,
        len(groups),
        size=(FACTORIAL_BOOTSTRAP_REPEATS, len(groups)),
    )
    analysis = {
        "design": {
            **metadata,
            "factors": {
                "T": "Start driving -> Roam the track",
                "L": "inner/outer -> innermost/outermost",
                "S": "normal -> regular",
            },
            "floor_definition": (
                "lane-1 same-instruction separation from disjoint seeds 4--7; "
                "the lane-2 stochastic floor was not logged in this run"
            ),
            "primary_factorial_response": (
                "log2(raw composed-path XY RMS language separation / 1 m)"
            ),
            "secondary_factorial_responses": [
                "log2 lane-1 same-instruction separation",
                "log2 language/lane-1-reference ratio",
                "the same three responses after the zero-initial-command bridge transform",
            ],
            "effect_definition": (
                "mean response in effect-coded product-positive cells minus "
                "the mean response in product-negative cells, computed within "
                "each observation before aggregation"
            ),
            "bootstrap": {
                "unit": "matched counterfactual observation",
                "repeats": FACTORIAL_BOOTSTRAP_REPEATS,
                "seed": FACTORIAL_BOOTSTRAP_SEED,
                "interval": "pointwise percentile 95%",
            },
            "bridge_transform_contract": {
                "dt_s": EXECUTOR_DT,
                "speed_scale": 1.0,
                "max_speed_mps": EXECUTOR_MAX_SPEED,
                "speed_slew_mps_per_tick": EXECUTOR_SPEED_SLEW,
                "max_curvature_per_m": float(EXECUTOR_MAX_CURVATURE),
                "initial_previous_command_speed_mps": 0.0,
                "lateral_dy_used": False,
                "integration": "exact constant-twist unicycle",
            },
        },
        "cells": [],
        "effects": {},
    }

    matrices = {}
    for metric, (language_key, floor_key) in metric_keys.items():
        language = np.column_stack(
            [[row[language_key] for row in cell["rows"]] for cell in ordered]
        )
        floor = np.column_stack(
            [[row[floor_key] for row in cell["rows"]] for cell in ordered]
        )
        matrices[metric] = {
            "language": np.log2(language),
            "floor": np.log2(floor),
            "ratio": np.log2(language / floor),
        }

    for cell_index, cell in enumerate(ordered):
        summary = {
            key: value for key, value in cell.items() if key != "rows"
        }
        for metric, (language_key, floor_key) in metric_keys.items():
            language = np.asarray(
                [row[language_key] for row in cell["rows"]], dtype=float
            )
            floor = np.asarray(
                [row[floor_key] for row in cell["rows"]], dtype=float
            )
            ratio = language / floor
            summary[metric] = {
                "language_median_m": float(np.median(language)),
                "floor_lane1_median_m": float(np.median(floor)),
                "per_observation_ratio_median": float(np.median(ratio)),
                "mean_log2_ratio": float(np.mean(np.log2(ratio))),
                "language_above_lane1_floor": int(np.sum(language > floor)),
                "n": len(language),
            }
        analysis["cells"].append(summary)

    for metric, matrices_for_metric in matrices.items():
        metric_effects = {}
        for component, matrix in matrices_for_metric.items():
            metric_effects[component] = _factorial_effect_summary(
                matrix, factors, bootstrap_indices
            )
        analysis["effects"][metric] = metric_effects

    classifications = {}
    for metric in metric_keys:
        classifications[metric] = {
            cell["condition"]: cell[metric]["per_observation_ratio_median"] > 1.0
            for cell in analysis["cells"]
        }
    dominant = {}
    for metric in metric_keys:
        main_effects = analysis["effects"][metric]["ratio"][:3]
        dominant[metric] = min(
            main_effects, key=lambda effect: effect["estimate_log2"]
        )["effect"]
    analysis["raw_bridge_transform_conclusion_consistency"] = {
        "median_above_floor_cell_classification_raw": classifications["raw_se2"],
        "median_above_floor_cell_classification_bridge_transform": classifications[
            "bridge_transform"
        ],
        "all_cell_classifications_match": (
            classifications["raw_se2"] == classifications["bridge_transform"]
        ),
        "dominant_negative_main_effect_raw": dominant["raw_se2"],
        "dominant_negative_main_effect_bridge_transform": dominant[
            "bridge_transform"
        ],
        "dominant_main_effect_matches": (
            dominant["raw_se2"] == dominant["bridge_transform"]
        ),
    }
    return analysis


def rounded_box(ax, xy, wh, title, detail, fill="white", edge=GRID):
    x, y = xy
    w, h = wh
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.004,rounding_size=0.010",
        facecolor=fill,
        edgecolor=edge,
        linewidth=0.70,
    )
    ax.add_patch(patch)
    text_x = x + 0.018
    ax.text(
        text_x,
        y + h * 0.66,
        title,
        color=INK,
        fontsize=7.2,
        ha="left",
        va="center",
    )
    ax.text(
        text_x,
        y + h * 0.28,
        detail,
        color=MUTED,
        fontsize=6.1,
        ha="left",
        va="center",
        linespacing=1.12,
    )


def flow_arrow(
    ax,
    start,
    end,
    color=MUTED,
    connectionstyle="arc3,rad=0",
    linewidth=0.78,
    linestyle="-",
):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=7.8,
            linewidth=linewidth,
            linestyle=linestyle,
            color=color,
            connectionstyle=connectionstyle,
            shrinkA=0.6,
            shrinkB=0.9,
            zorder=3,
        )
    )


def build_pipeline():
    fig, ax = plt.subplots(figsize=(7.08, 2.08))
    fig.subplots_adjust(left=0.006, right=0.994, bottom=0.03, top=0.98)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.add_patch(Rectangle((0.0, 0.535), 1.0, 0.445, color="#f7f9fa", ec="none"))
    ax.add_patch(Rectangle((0.0, 0.020), 1.0, 0.445, color="#fbfcfc", ec="none"))
    ax.text(0.016, 0.925, "OFFLINE FINE-TUNING", color=MUTED, fontsize=6.0)
    ax.text(0.016, 0.405, "CLOSED-LOOP DEPLOYMENT", color=MUTED, fontsize=6.0)

    top_y, box_h = 0.625, 0.235
    top_x = [0.020, 0.270, 0.520, 0.770]
    top_w = [0.210] * 4
    rounded_box(ax, (top_x[0], top_y), (top_w[0], box_h), "Language-tagged demos", "RGB + instruction + state\n+ teacher vehicle motion", LIGHT_BLUE, "#abcddd")
    rounded_box(ax, (top_x[1], top_y), (top_w[1], box_h), "Validated 10-Hz corpus", "406 episodes / 93,733 rows\n388 task strings", "white")
    rounded_box(ax, (top_x[2], top_y), (top_w[2], box_h), "SmolVLA", "60K steps, batch 8\n30-step SE(2) chunks", LIGHT_GREEN, "#a9d8c7")
    rounded_box(ax, (top_x[3], top_y), (top_w[3], box_h), "Frozen checkpoint", "v6-60K\nfixed for evaluation", "white")
    box_pad = 0.004
    for left, width, right in zip(top_x, top_w, top_x[1:]):
        flow_arrow(
            ax,
            (left + width + box_pad, top_y + box_h / 2),
            (right - box_pad, top_y + box_h / 2),
        )

    bottom_y = 0.105
    bottom_x = [0.020, 0.218, 0.416, 0.614, 0.812]
    bottom_w = [0.168] * 5
    rounded_box(ax, (bottom_x[0], bottom_y), (bottom_w[0], box_h), "Observation", "front RGB + instruction\n[v, yaw rate, 0]", LIGHT_BLUE, "#abcddd")
    rounded_box(ax, (bottom_x[1], bottom_y), (bottom_w[1], box_h), "Frozen SmolVLA", "30-step action chunk\nper queue refill", LIGHT_GREEN, "#a9d8c7")
    rounded_box(
        ax,
        (bottom_x[2], bottom_y),
        (bottom_w[2], box_h),
        "Action queue",
        "chunk buffer\n[$\\Delta x$, $\\Delta y$, $\\Delta\\psi$]",
        "white",
    )
    rounded_box(ax, (bottom_x[3], bottom_y), (bottom_w[3], box_h), "Bridge transform", "speed cap + slew\ncurvature limit", LIGHT_ORANGE, "#e6b89d")
    rounded_box(ax, (bottom_x[4], bottom_y), (bottom_w[4], box_h), "Gazebo vehicle", "vehicle motion\ncamera + state", "white")
    for left, width, right in zip(bottom_x, bottom_w, bottom_x[1:]):
        flow_arrow(
            ax,
            (left + width + box_pad, bottom_y + box_h / 2),
            (right - box_pad, bottom_y + box_h / 2),
        )

    observation_center = bottom_x[0] + bottom_w[0] / 2
    vehicle_center = bottom_x[4] + bottom_w[4] / 2
    feedback_y = bottom_y - box_pad
    flow_arrow(
        ax,
        (vehicle_center, feedback_y),
        (observation_center, feedback_y),
        color=PURPLE,
        connectionstyle="arc3,rad=-0.052",
        linewidth=0.82,
        linestyle="--",
    )
    ax.text(
        0.50,
        0.041,
        "closed-loop feedback",
        ha="center",
        va="bottom",
        color=PURPLE,
        fontsize=5.9,
        bbox={"facecolor": "#fbfcfc", "edgecolor": "none", "pad": 0.6},
    )

    deploy_start = (top_x[3] + top_w[3] / 2, top_y - box_pad)
    deploy_end = (bottom_x[1] + bottom_w[1] / 2, bottom_y + box_h + box_pad)
    flow_arrow(
        ax,
        deploy_start,
        deploy_end,
        color=GREEN,
        connectionstyle="arc3,rad=0.06",
        linewidth=0.82,
    )
    ax.text(
        0.605,
        0.490,
        "deploy",
        ha="center",
        va="center",
        color=GREEN,
        fontsize=5.9,
    )

    fig.savefig(FIG_DIR / "fig1_language_pipeline.pdf", bbox_inches="tight", pad_inches=0.01)
    plt.close(fig)


def requested_lane(sentence):
    """Map the controlled English lane words to configured references."""
    inner = re.search(r"\b(?:inner|innermost)\b", sentence.lower()) is not None
    outer = re.search(r"\b(?:outer|outermost)\b", sentence.lower()) is not None
    if inner == outer:
        raise ValueError(f"instruction does not name exactly one lane: {sentence!r}")
    return "lane1" if inner else "lane2"


def _check_expected_contract(contract, source):
    if not isinstance(contract, dict):
        raise ValueError(f"{source}: missing execution contract")
    for key, expected in EXPECTED_CONTRACT.items():
        if key not in contract:
            raise ValueError(f"{source}: execution contract lacks {key!r}")
        actual = contract[key]
        if isinstance(expected, float):
            matches = np.isclose(float(actual), expected, rtol=0.0, atol=1e-9)
        else:
            matches = actual == expected
        if not matches:
            raise ValueError(
                f"{source}: contract {key}={actual!r}, expected {expected!r}"
            )


def _validate_runtime(row, source):
    for side in ("a", "b"):
        status = row.get(f"status_{side}")
        if not isinstance(status, dict):
            raise ValueError(f"{source}: missing status_{side}")
        if int(status.get("watchdog_hits", -1)) != 0:
            raise ValueError(f"{source}: status_{side} has watchdog activations")
        if not np.isclose(
            float(status.get("underrun_pct", float("nan"))),
            0.0,
            rtol=0.0,
            atol=1e-9,
        ):
            raise ValueError(f"{source}: status_{side} has action underrun")
        for key in ("prefill_s", "latency_ms"):
            value = status.get(key)
            if value is None or not np.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{source}: invalid status_{side}.{key}={value!r}")
        _check_expected_contract(status.get("contract"), f"{source}:status_{side}")


def load_balanced_records(geometry):
    """Load and validate the eight fixed, counterbalanced probe artifacts."""
    records_by_regime = {}
    run_ids = set()
    pair_ids = set()
    rollout_ids = set()
    contracts = []
    reset_poses = {}
    for regime, paths in CLOSED_LOOP_PATHS.items():
        records = []
        for path in paths:
            rows = load_json(path)
            if len(rows) != 2:
                raise ValueError(f"{path}: expected one SAME and one DIFFERENT row")
            same = [row for row in rows if row["case"].startswith("SAME")]
            different = [row for row in rows if row["case"].startswith("DIFFERENT")]
            if len(same) != 1 or len(different) != 1:
                raise ValueError(f"{path}: invalid SAME/DIFFERENT composition")
            file_run_ids = {row.get("run_id") for row in rows}
            if len(file_run_ids) != 1 or not next(iter(file_run_ids)):
                raise ValueError(f"{path}: rows do not share one non-empty run_id")
            run_id = next(iter(file_run_ids))
            if run_id in run_ids:
                raise ValueError(f"{path}: duplicate run_id={run_id!r}")
            run_ids.add(run_id)
            for row in rows:
                source = f"{path}:{row.get('pair_id', '?')}"
                start = row.get("start_label")
                if start not in START_LANE:
                    raise ValueError(f"{source}: invalid start_label={start!r}")
                pose = row.get("reset_pose")
                if not isinstance(pose, list) or len(pose) != 3:
                    raise ValueError(f"{source}: invalid reset_pose={pose!r}")
                pose_tuple = tuple(float(value) for value in pose)
                if start in reset_poses and not np.allclose(
                    pose_tuple, reset_poses[start], rtol=0.0, atol=1e-9
                ):
                    raise ValueError(
                        f"{source}: reset pose differs from other {start} runs"
                    )
                reset_poses.setdefault(start, pose_tuple)
                nearest = min(
                    ("lane1", "lane2"),
                    key=lambda lane: distance_to_closed_polyline(
                        pose[:2], geometry[lane]
                    ),
                )
                if nearest != START_LANE[start]:
                    raise ValueError(
                        f"{source}: {start} reset is nearest to {nearest}"
                    )
                target_a = requested_lane(row["say_a"])
                target_b = requested_lane(row["say_b"])
                if row["case"].startswith("SAME"):
                    if row["say_a"] != row["say_b"] or target_a != target_b:
                        raise ValueError(f"{source}: malformed SAME pair")
                elif row["say_a"] == row["say_b"] or {target_a, target_b} != {
                    "lane1",
                    "lane2",
                }:
                    raise ValueError(f"{source}: malformed DIFFERENT pair")
                if len(row.get("track_a", [])) < 5 or len(row.get("track_b", [])) < 5:
                    raise ValueError(f"{source}: trajectory has fewer than five points")
                for key in ("D_shape_m", "shared_m", "arclen_a", "arclen_b"):
                    if not np.isfinite(float(row[key])):
                        raise ValueError(f"{source}: invalid {key}={row[key]!r}")
                _validate_runtime(row, source)
                contracts.extend(
                    (row["status_a"]["contract"], row["status_b"]["contract"])
                )
                pair_id = row.get("pair_id")
                if not pair_id or pair_id in pair_ids:
                    raise ValueError(f"{source}: duplicate or empty pair_id")
                pair_ids.add(pair_id)
                for side in ("a", "b"):
                    rollout_id = row.get(f"rollout_id_{side}")
                    if not rollout_id or rollout_id in rollout_ids:
                        raise ValueError(f"{source}: duplicate or empty rollout_id_{side}")
                    rollout_ids.add(rollout_id)
                records.append(row)

        if len(records) != 8:
            raise ValueError(f"{regime}: expected eight paired rows")
        observed_sentences = {
            row[f"say_{side}"] for row in records for side in ("a", "b")
        }
        if observed_sentences != EXPECTED_SENTENCES[regime]:
            raise ValueError(
                f"{regime}: unexpected controlled instructions {observed_sentences}"
            )
        for start in START_LANE:
            start_rows = [row for row in records if row["start_label"] == start]
            if len(start_rows) != 4:
                raise ValueError(f"{regime}/{start}: expected four paired rows")
            same_targets = {
                requested_lane(row["say_a"])
                for row in start_rows
                if row["case"].startswith("SAME")
            }
            different_orders = {
                (requested_lane(row["say_a"]), requested_lane(row["say_b"]))
                for row in start_rows
                if row["case"].startswith("DIFFERENT")
            }
            if same_targets != {"lane1", "lane2"} or different_orders != {
                ("lane1", "lane2"),
                ("lane2", "lane1"),
            }:
                raise ValueError(f"{regime}/{start}: incomplete AB/BA balance")
        records_by_regime[regime] = records

    canonical_contract = contracts[0]
    if any(contract != canonical_contract for contract in contracts[1:]):
        raise ValueError("execution contracts differ across balanced rollouts")
    return records_by_regime, canonical_contract


def distance_to_closed_polyline(point, reference):
    """Euclidean distance from one XY point to a closed reference polyline."""
    p = np.asarray(point, dtype=float)
    a = np.asarray(reference, dtype=float)
    b = np.roll(a, -1, axis=0)
    ab = b - a
    denom = np.sum(ab * ab, axis=1)
    t = np.divide(
        np.sum((p - a) * ab, axis=1),
        denom,
        out=np.zeros_like(denom),
        where=denom > 0,
    )
    projection = a + np.clip(t, 0.0, 1.0)[:, None] * ab
    return float(np.min(np.linalg.norm(projection - p, axis=1)))


def polyline_length(track):
    points = np.asarray(track, dtype=float)
    if len(points) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def resample_arclength(track, step_m=0.2):
    """Resample an open trajectory at approximately uniform traveled distance."""
    if step_m <= 0:
        raise ValueError("step_m must be positive")
    points = np.asarray(track, dtype=float)
    if len(points) < 2:
        return points
    sampled = [points[0]]
    target = step_m
    distance = 0.0
    for first, second in zip(points, points[1:]):
        segment = float(np.linalg.norm(second - first))
        if segment <= 0:
            continue
        while distance + segment >= target:
            fraction = (target - distance) / segment
            sampled.append(first + fraction * (second - first))
            target += step_m
        distance += segment
    return np.asarray(sampled)


def track_after_arclength(track, cutoff_m=15.0, step_m=0.2):
    sampled = resample_arclength(track, step_m=step_m)
    first = int(np.ceil(cutoff_m / step_m))
    if len(sampled) <= first:
        raise ValueError(
            f"trajectory length {polyline_length(track):.2f} m does not reach "
            f"the {cutoff_m:.1f}-m analysis cutoff"
        )
    return sampled[first:]


def iter_rollouts(records, comparison=None):
    for record in records:
        current = (
            "different" if record["case"].startswith("DIFFERENT") else "same"
        )
        if comparison is not None and current != comparison:
            continue
        start = record["start_label"]
        for side in ("a", "b"):
            target = requested_lane(record[f"say_{side}"])
            yield {
                "record": record,
                "side": side,
                "comparison": current,
                "run_id": record["run_id"],
                "rollout_id": record[f"rollout_id_{side}"],
                "start_lane": start,
                "requested_lane": target,
                "maneuver": "stay" if START_LANE[start] == target else "change",
                "track": record[f"track_{side}"],
            }


def lane_adherence(records, geometry, regime, cutoff_m=15.0):
    rows = []
    references = {"lane1": geometry["lane1"], "lane2": geometry["lane2"]}
    for rollout in iter_rollouts(records):
        target = rollout["requested_lane"]
        other = "lane2" if target == "lane1" else "lane1"
        track = track_after_arclength(
            rollout["track"], cutoff_m=cutoff_m, step_m=0.2
        )
        intended = [
            distance_to_closed_polyline(point, references[target]) for point in track
        ]
        alternate = [
            distance_to_closed_polyline(point, references[other]) for point in track
        ]
        rows.append(
            {
                "regime": regime,
                "run_id": rollout["run_id"],
                "rollout_id": rollout["rollout_id"],
                "comparison": rollout["comparison"],
                "start_lane": rollout["start_lane"],
                "requested_lane": target,
                "maneuver": rollout["maneuver"],
                "cutoff_m": cutoff_m,
                "trajectory_arclength_m": polyline_length(rollout["track"]),
                "points_after_cutoff": len(track),
                "median_intended_distance_m": statistics.median(intended),
                "p95_intended_distance_m": float(np.percentile(intended, 95)),
                "fraction_closer_to_intended": sum(
                    intended_distance < alternate_distance
                    for intended_distance, alternate_distance in zip(
                        intended, alternate
                    )
                )
                / len(track),
                "median_alternate_distance_m": statistics.median(alternate),
            }
        )
    return rows


def same_instruction_floors(records):
    floors = {}
    for row in records:
        if not row["case"].startswith("SAME"):
            continue
        key = (row["start_label"], requested_lane(row["say_a"]))
        if key in floors:
            raise ValueError(f"duplicate SAME floor for {key}")
        floors[key] = float(row["D_shape_m"])
    expected = {(start, lane) for start in START_LANE for lane in ("lane1", "lane2")}
    if set(floors) != expected:
        raise ValueError(f"SAME floors do not cover all start/target strata: {floors}")
    return floors


def conservative_floor_by_start(records):
    floors = same_instruction_floors(records)
    return {
        start: max(floors[(start, "lane1")], floors[(start, "lane2")])
        for start in START_LANE
    }


def paired_bootstrap_summary(matched, repeats=50000):
    rng = np.random.default_rng(20260901)
    output = {}
    for name, language, floor in (
        (
            "in-vocabulary",
            np.asarray([row["language"]["path_rms_m"] for row in matched["pairs"]]),
            np.asarray([row["same_instruction_noise"]["path_rms_m"] for row in matched["pairs"]]),
        ),
        (
            "heldout-lexical",
            np.asarray([row["secondary"]["language"]["path_rms_m"] for row in matched["pairs"]]),
            np.asarray([row["secondary"]["same_instruction_noise"]["path_rms_m"] for row in matched["pairs"]]),
        ),
    ):
        differences = language - floor
        medians = np.empty(repeats)
        ratios = np.empty(repeats)
        for index in range(repeats):
            sample = rng.integers(0, len(differences), len(differences))
            medians[index] = np.median(differences[sample])
            ratios[index] = np.median(language[sample] / np.maximum(floor[sample], 1e-9))
        output[name] = {
            "paired_difference_median_m": float(np.median(differences)),
            "paired_difference_bootstrap_95ci_m": [float(value) for value in np.quantile(medians, [0.025, 0.975])],
            "per_observation_ratio_median": float(np.median(language / np.maximum(floor, 1e-9))),
            "ratio_bootstrap_95ci": [float(value) for value in np.quantile(ratios, [0.025, 0.975])],
            "bootstrap_repeats": repeats,
        }
    return output


def build_closed_loop_figure(records_by_regime, geometry):
    titles = {
        "familiar-wording": "(a) Base wording",
        "test-wording": r"(b) $T{+}L{+}S$ test wording",
    }
    different_rollouts = [
        rollout
        for records in records_by_regime.values()
        for rollout in iter_rollouts(records, comparison="different")
    ]
    plotted_points = np.concatenate(
        [np.asarray(rollout["track"], dtype=float) for rollout in different_rollouts]
    )
    x_limits = (plotted_points[:, 1].min() - 1.0, plotted_points[:, 1].max() + 1.0)
    y_limits = (plotted_points[:, 0].min() - 1.0, plotted_points[:, 0].max() + 1.0)

    fig, axes = plt.subplots(1, 2, figsize=(7.08, 2.52), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.25, top=0.82, wspace=0.13)
    for ax, (regime, records) in zip(axes, records_by_regime.items()):
        different = [
            row for row in records if row["case"].startswith("DIFFERENT")
        ]
        local_floors = conservative_floor_by_start(records)
        median_distance = statistics.median(row["D_shape_m"] for row in different)
        maximum_floor = max(local_floors.values())
        center = np.asarray(geometry["ring_center"])
        lane1 = np.asarray(geometry["lane1"])
        lane2 = np.asarray(geometry["lane2"])
        ax.plot(center[:, 1], center[:, 0], color="#c4cbd1", lw=0.75, ls=":", zorder=1)
        ax.plot(lane1[:, 1], lane1[:, 0], color="#aeb7bf", lw=0.8, ls="--", zorder=1)
        ax.plot(lane2[:, 1], lane2[:, 0], color="#aeb7bf", lw=0.8, ls="--", zorder=1)
        for rollout in iter_rollouts(records, comparison="different"):
            track = np.asarray(rollout["track"])
            color = BLUE if rollout["requested_lane"] == "lane1" else ORANGE
            linestyle = "-" if rollout["start_lane"] == "outer" else (0, (3, 1.5))
            ax.plot(
                track[:, 1],
                track[:, 0],
                color=color,
                ls=linestyle,
                lw=1.05,
                alpha=0.72,
                zorder=3,
            )
        starts = {
            rollout["start_lane"]: np.asarray(rollout["track"][0])
            for rollout in iter_rollouts(records, comparison="different")
        }
        for start_label, marker in (("outer", "s"), ("inner", "o")):
            start = starts[start_label]
            ax.scatter(
                start[1],
                start[0],
                marker=marker,
                s=24,
                facecolor="white",
                edgecolor=INK,
                linewidth=0.65,
                zorder=5,
            )
        ax.set_title(titles[regime], pad=18, fontweight="normal")
        ax.text(
            0.5,
            1.025,
            f"30-s segments: median $D_{{shape}}$ {median_distance:.2f} m; "
            f"max local repeat reference {maximum_floor:.2f} m",
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            color=MUTED,
            fontsize=6.3,
        )
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(*x_limits)
        ax.set_ylim(*y_limits)
        ax.grid(color=GRID, linewidth=0.45, alpha=0.55)
        ax.set_xlabel("world y (m)")
    axes[0].set_ylabel("world x (m)")
    handles = [
        plt.Line2D([], [], color=BLUE, lw=1.5, label="inner instruction"),
        plt.Line2D([], [], color=ORANGE, lw=1.5, label="outer instruction"),
        plt.Line2D([], [], color="#aeb7bf", lw=0.8, ls="--", label="lane references"),
        plt.Line2D([], [], color=INK, lw=1.0, ls="-", label="outer-lane reset"),
        plt.Line2D([], [], color=INK, lw=1.0, ls=(0, (3, 1.5)), label="inner-lane reset"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, bbox_to_anchor=(0.52, 0.020))
    fig.savefig(FIG_DIR / "fig2_closed_loop_language.pdf", bbox_inches="tight", pad_inches=0.01)
    plt.close(fig)


def build_chunk_figure(matched):
    pairs = matched["pairs"]
    groups = [
        np.asarray([row["language"]["path_rms_m"] for row in pairs]),
        np.asarray([row["same_instruction_noise"]["path_rms_m"] for row in pairs]),
        np.asarray([row["secondary"]["language"]["path_rms_m"] for row in pairs]),
        np.asarray([row["secondary"]["same_instruction_noise"]["path_rms_m"] for row in pairs]),
    ]
    colors = [BLUE, "#78a8c8", ORANGE, "#d9a07f"]
    labels = ["In-vocab.\nlanguage", "In-vocab.\nfloor", "Held-out\nlanguage", "Held-out\nfloor"]

    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    fig.subplots_adjust(left=0.19, right=0.98, bottom=0.25, top=0.84)
    rng = np.random.default_rng(20260901)
    for index, (values, color) in enumerate(zip(groups, colors), start=1):
        jitter = rng.uniform(-0.09, 0.09, size=len(values))
        ax.scatter(np.full_like(values, index, dtype=float) + jitter, values, s=13, color=color, alpha=0.72, edgecolor="white", linewidth=0.25, zorder=3)
        median = statistics.median(values)
        ax.plot([index - 0.20, index + 0.20], [median, median], color=INK, lw=1.8, zorder=4)
        ax.text(index, median * 1.13, f"{median:.3f}", ha="center", va="bottom", fontsize=6.0)
    for row_index, row in enumerate(pairs):
        ax.plot([1, 2], [groups[0][row_index], groups[1][row_index]], color="#c9ced3", lw=0.35, alpha=0.45, zorder=1)
        ax.plot([3, 4], [groups[2][row_index], groups[3][row_index]], color="#c9ced3", lw=0.35, alpha=0.45, zorder=1)
    ax.set_yscale("log")
    ax.set_ylim(0.012, 1.7)
    ax.set_ylabel("predicted-path RMS separation (m)")
    ax.set_xticks(range(1, 5), labels)
    ax.grid(axis="y", which="both", color=GRID, lw=0.45)
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(1.5, 1.48, "20/20 above floor", color=BLUE, ha="center", va="bottom", fontsize=6.3)
    ax.text(3.5, 1.48, "3/20 above floor", color=ORANGE, ha="center", va="bottom", fontsize=6.3)
    ax.set_title("Matched image and state; instruction changed", pad=8)
    fig.savefig(FIG_DIR / "fig3_chunk_conditioning.pdf", bbox_inches="tight", pad_inches=0.01)
    plt.close(fig)


def build_factorial_response_ratios(cells):
    """Plot observation-level language/reference ratios for all eight cells."""
    order = [
        "baseline",
        "template-only",
        "speed-only",
        "template-speed",
        "lane-only",
        "template-lane",
        "lane-speed",
        "all-reserved",
    ]
    positions = np.asarray([0.35, 1.35, 2.35, 3.35, 5.10, 6.10, 7.10, 8.10])
    colors = [BLUE] * 4 + [ORANGE] * 4
    rng = np.random.default_rng(FACTORIAL_BOOTSTRAP_SEED)

    fig, ax = plt.subplots(figsize=(3.45, 2.32))
    fig.subplots_adjust(left=0.18, right=0.985, bottom=0.22, top=0.94)
    for position, condition, color in zip(positions, order, colors):
        cell = cells[condition]
        ratios = np.asarray(
            [
                row["language_raw_se2_m"] / row["floor_lane1_raw_se2_m"]
                for row in cell["rows"]
            ],
            dtype=float,
        )
        jitter = rng.uniform(-0.13, 0.13, size=len(ratios))
        ax.scatter(
            ratios,
            np.full_like(ratios, position) + jitter,
            s=9.0,
            color=color,
            alpha=0.42,
            edgecolor="none",
            zorder=2,
        )
        median = float(np.median(ratios))
        ax.scatter(
            median,
            position,
            s=31,
            marker="D",
            color=color,
            edgecolor="white",
            linewidth=0.55,
            zorder=4,
        )
        ax.text(
            17.2,
            position,
            rf"{median:.2f}$\times$",
            color=color,
            fontsize=6.1,
            ha="right",
            va="center",
        )

    ax.axvline(1.0, color=INK, lw=0.8, ls="--", zorder=1)
    ax.axhline(4.20, color=GRID, lw=0.7, zorder=1)
    ax.set_xscale("log", base=2)
    ax.set_xlim(0.10, 19.0)
    ticks = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
    tick_labels = [
        r"$0.125\times$",
        r"$0.25\times$",
        r"$0.5\times$",
        r"$1\times$",
        r"$2\times$",
        r"$4\times$",
        r"$8\times$",
        r"$16\times$",
    ]
    ax.set_xticks(ticks, tick_labels)
    ax.set_yticks(
        positions,
        [cells[condition]["short_label"] for condition in order],
    )
    ax.set_ylim(8.55, -0.72)
    ax.set_xlabel(r"response ratio $R$ (log scale)")
    ax.grid(axis="x", which="major", color=GRID, lw=0.45, alpha=0.8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.text(
        0.11,
        -0.56,
        "original lane words (no L)",
        color=BLUE,
        fontsize=5.8,
        ha="left",
        va="bottom",
    )
    ax.text(
        0.11,
        4.66,
        "inner/outer -> innermost/outermost (L)",
        color=ORANGE,
        fontsize=5.8,
        ha="left",
        va="bottom",
    )
    fig.savefig(
        FIG_DIR / "fig3_wording_factorial.pdf",
        bbox_inches="tight",
        pad_inches=0.01,
    )
    plt.close(fig)


def write_factorial_summaries(analysis):
    with (DATA_DIR / "factorial_wording_analysis.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(analysis, handle, indent=2)

    with (DATA_DIR / "factorial_wording_cells.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fieldnames = [
            "condition",
            "short_label",
            "T",
            "L",
            "S",
            "raw_language_median_m",
            "raw_lane1_floor_median_m",
            "raw_ratio_median",
            "raw_above_lane1_floor",
            "bridge_transform_language_median_m",
            "bridge_transform_lane1_floor_median_m",
            "bridge_transform_ratio_median",
            "bridge_transform_above_lane1_floor",
            "n",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for cell in analysis["cells"]:
            raw = cell["raw_se2"]
            bridge_transform = cell["bridge_transform"]
            writer.writerow(
                {
                    "condition": cell["condition"],
                    "short_label": cell["short_label"],
                    **cell["factors"],
                    "raw_language_median_m": raw["language_median_m"],
                    "raw_lane1_floor_median_m": raw[
                        "floor_lane1_median_m"
                    ],
                    "raw_ratio_median": raw["per_observation_ratio_median"],
                    "raw_above_lane1_floor": raw[
                        "language_above_lane1_floor"
                    ],
                    "bridge_transform_language_median_m": bridge_transform[
                        "language_median_m"
                    ],
                    "bridge_transform_lane1_floor_median_m": bridge_transform[
                        "floor_lane1_median_m"
                    ],
                    "bridge_transform_ratio_median": bridge_transform[
                        "per_observation_ratio_median"
                    ],
                    "bridge_transform_above_lane1_floor": bridge_transform[
                        "language_above_lane1_floor"
                    ],
                    "n": raw["n"],
                }
            )

    with (DATA_DIR / "factorial_wording_effects.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fieldnames = [
            "metric",
            "component",
            "effect",
            "order",
            "estimate_log2",
            "ci95_low_log2",
            "ci95_high_log2",
            "multiplicative_change",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for metric, components in analysis["effects"].items():
            for component, effects in components.items():
                for effect in effects:
                    writer.writerow(
                        {
                            "metric": metric,
                            "component": component,
                            "effect": effect["effect"],
                            "order": effect["order"],
                            "estimate_log2": effect["estimate_log2"],
                            "ci95_low_log2": effect[
                                "bootstrap_95_ci_log2"
                            ][0],
                            "ci95_high_log2": effect[
                                "bootstrap_95_ci_log2"
                            ][1],
                            "multiplicative_change": effect[
                                "multiplicative_change"
                            ],
                        }
                    )


def _adherence_group_summary(rows):
    if not rows:
        raise ValueError("cannot summarize an empty adherence group")
    return {
        "rollouts": len(rows),
        "median_of_run_medians_m": statistics.median(
            row["median_intended_distance_m"] for row in rows
        ),
        "median_of_run_p95_m": statistics.median(
            row["p95_intended_distance_m"] for row in rows
        ),
        "median_fraction_closer_to_intended": statistics.median(
            row["fraction_closer_to_intended"] for row in rows
        ),
    }


def write_summaries(records_by_regime, geometry, execution_contract):
    with (DATA_DIR / "closed_loop_pairs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "regime",
                "run_id",
                "pair_id",
                "start_lane",
                "comparison",
                "instruction_order",
                "requested_a",
                "requested_b",
                "D_shape_m",
                "local_conservative_floor_m",
                "D_over_local_floor",
                "shared_prefix_m",
                "arclen_a_m",
                "arclen_b_m",
                "watchdog_a",
                "watchdog_b",
                "underrun_a_pct",
                "underrun_b_pct",
                "prefill_a_s",
                "prefill_b_s",
                "latency_a_ms",
                "latency_b_ms",
                "state_steer_source",
                "max_speed_mps",
                "track_mode",
                "policy_seed",
            ]
        )
        for regime, records in records_by_regime.items():
            local_floors = conservative_floor_by_start(records)
            for row in records:
                a, b = row["status_a"], row["status_b"]
                requested_a = requested_lane(row["say_a"])
                requested_b = requested_lane(row["say_b"])
                local_floor = local_floors[row["start_label"]]
                writer.writerow(
                    [
                        regime,
                        row["run_id"],
                        row["pair_id"],
                        row["start_label"],
                        "different"
                        if row["case"].startswith("DIFFERENT")
                        else "same",
                        f"{requested_a}->{requested_b}",
                        requested_a,
                        requested_b,
                        row["D_shape_m"],
                        local_floor,
                        row["D_shape_m"] / max(local_floor, 1e-9),
                        row["shared_m"],
                        row["arclen_a"],
                        row["arclen_b"],
                        a["watchdog_hits"],
                        b["watchdog_hits"],
                        a["underrun_pct"],
                        b["underrun_pct"],
                        a["prefill_s"],
                        b["prefill_s"],
                        a["latency_ms"],
                        b["latency_ms"],
                        execution_contract["state_steer_source"],
                        execution_contract["max_speed"],
                        execution_contract["track_mode"],
                        execution_contract["seed"],
                    ]
                )

    adherence = [
        row
        for regime, records in records_by_regime.items()
        for row in lane_adherence(records, geometry, regime)
    ]
    with (DATA_DIR / "lane_reference_adherence.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(adherence[0]))
        writer.writeheader()
        writer.writerows(adherence)

    summary = {
        "factorial_action_analysis": "factorial_wording_analysis.json",
        "execution_contract": execution_contract,
        "static_source_contract": {
            "max_curvature_1pm": float(EXECUTOR_MAX_CURVATURE),
            "sim_wheel_base_m": EXECUTOR_SIM_WHEEL_BASE,
            "sim_max_steer_rad": EXECUTOR_SIM_MAX_STEER,
            "provenance": (
                "vla_bridge_node.py constants; these static values were not "
                "included in the captured /vla/status contract"
            ),
        },
        "closed_loop": {},
    }
    for regime, records in records_by_regime.items():
        different_rows = [
            row for row in records if row["case"].startswith("DIFFERENT")
        ]
        same_rows = [row for row in records if row["case"].startswith("SAME")]
        different = [float(row["D_shape_m"]) for row in different_rows]
        same = [float(row["D_shape_m"]) for row in same_rows]
        floors = same_instruction_floors(records)
        local_floors = conservative_floor_by_start(records)
        local_ratios = [
            row["D_shape_m"] / max(local_floors[row["start_label"]], 1e-9)
            for row in different_rows
        ]
        statuses = [
            row[f"status_{side}"] for row in records for side in ("a", "b")
        ]
        summary["closed_loop"][regime] = {
            "paired_repeats": len(different),
            "different_pairs": len(different),
            "same_pairs": len(same),
            "different_median_m": statistics.median(different),
            "different_range_m": [min(different), max(different)],
            "same_median_m": statistics.median(same),
            "same_range_m": [min(same), max(same)],
            "ratio_of_medians": statistics.median(different) / statistics.median(same),
            "same_floor_by_start_and_target_m": {
                start: {
                    lane: floors[(start, lane)] for lane in ("lane1", "lane2")
                }
                for start in START_LANE
            },
            "local_conservative_floor_by_start_m": local_floors,
            "different_above_local_conservative_floor": sum(
                row["D_shape_m"] > local_floors[row["start_label"]]
                for row in different_rows
            ),
            "different_to_local_floor_ratio_median": statistics.median(
                local_ratios
            ),
            "different_to_local_floor_ratio_range": [
                min(local_ratios),
                max(local_ratios),
            ],
            "different_shared_prefix_median_m": statistics.median(
                row["shared_m"] for row in different_rows
            ),
            "rollouts": 2 * len(records),
            "valid_rollouts": len(statuses),
            "prefill_range_s": [
                min(status["prefill_s"] for status in statuses),
                max(status["prefill_s"] for status in statuses),
            ],
            "latency_range_ms": [
                min(status["latency_ms"] for status in statuses),
                max(status["latency_ms"] for status in statuses),
            ],
            "trajectory_arclength_range_m": [
                min(
                    row[f"arclen_{side}"]
                    for row in records
                    for side in ("a", "b")
                ),
                max(
                    row[f"arclen_{side}"]
                    for row in records
                    for side in ("a", "b")
                ),
            ],
        }
        regime_adherence = [row for row in adherence if row["regime"] == regime]
        summary["closed_loop"][regime]["lane_reference_after_15m"] = {
            "by_requested_lane": {
                lane: _adherence_group_summary(
                    [
                        row
                        for row in regime_adherence
                        if row["requested_lane"] == lane
                    ]
                )
                for lane in ("lane1", "lane2")
            },
            "by_maneuver": {
                maneuver: _adherence_group_summary(
                    [row for row in regime_adherence if row["maneuver"] == maneuver]
                )
                for maneuver in ("stay", "change")
            },
            "by_start_and_target": {
                f"{start}->{lane}": _adherence_group_summary(
                    [
                        row
                        for row in regime_adherence
                        if row["start_lane"] == start
                        and row["requested_lane"] == lane
                    ]
                )
                for start in START_LANE
                for lane in ("lane1", "lane2")
            },
        }
        sensitivity = {}
        for cutoff in (10.0, 15.0, 20.0):
            cutoff_rows = lane_adherence(
                records, geometry, regime, cutoff_m=cutoff
            )
            sensitivity[str(cutoff)] = {
                "by_requested_lane": {
                    lane: statistics.median(
                        row["fraction_closer_to_intended"]
                        for row in cutoff_rows
                        if row["requested_lane"] == lane
                    )
                    for lane in ("lane1", "lane2")
                },
                "by_maneuver": {
                    maneuver: statistics.median(
                        row["fraction_closer_to_intended"]
                        for row in cutoff_rows
                        if row["maneuver"] == maneuver
                    )
                    for maneuver in ("stay", "change")
                },
            }
        summary["closed_loop"][regime][
            "lane_assignment_cutoff_sensitivity"
        ] = sensitivity
    with (DATA_DIR / "experiment_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    factorial_cells, factorial_metadata = load_factorial_cells()
    factorial_analysis = analyze_factorial_cells(
        factorial_cells, factorial_metadata
    )
    geometry = load_json(TRACK_PATH)
    records_by_regime, execution_contract = load_balanced_records(geometry)
    # Preserve the independently authored vector system diagram when present.
    if not (FIG_DIR / "fig1_language_pipeline.pdf").exists():
        build_pipeline()
    build_closed_loop_figure(records_by_regime, geometry)
    build_factorial_response_ratios(factorial_cells)
    write_summaries(records_by_regime, geometry, execution_contract)
    write_factorial_summaries(factorial_analysis)
    print("wrote ICCE 2026 language figures and summary data")


if __name__ == "__main__":
    main()
