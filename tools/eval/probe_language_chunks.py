#!/usr/bin/env python3
"""Matched-observation language sensitivity for a fine-tuned SmolVLA.

For each counterfactual lane pair, this probe freezes one RGB frame and the
three-dimensional vehicle state, then predicts action chunks for the pair's two
English instructions.  It compares the resulting SE(2) paths with a disjoint-
seed same-instruction floor and a gray-image control.  No simulator or ROS node
is involved, so only the conditioning variable under test changes.
"""

import argparse
import json
import math
import os
import random
import statistics

import numpy as np


def episode_records(root):
    records = []
    for name in sorted(os.listdir(root)):
        base = os.path.join(root, name)
        meta_path = os.path.join(base, "meta.json")
        rows_path = os.path.join(base, "resampled_10hz.jsonl")
        if not os.path.isfile(meta_path) or not os.path.isfile(rows_path):
            continue
        meta = json.load(open(meta_path, encoding="utf-8"))
        if (not meta.get("valid", False)
                or meta.get("termination") != "success"
                or meta.get("cf_axis") != "lane"):
            continue
        rows = [json.loads(line) for line in open(rows_path, encoding="utf-8")
                if line.strip()]
        rows = [row for row in rows if row.get("action") and row.get("frame")]
        if rows:
            records.append((meta, base, rows))
    return records


def matched_pairs(records):
    groups = {}
    for record in records:
        meta = record[0]
        groups.setdefault(meta.get("cf_group_id"), {})[
            meta.get("intent_slots", {}).get("lane")] = record
    pairs = []
    for group, lanes in sorted(groups.items()):
        if "lane1" not in lanes or "lane2" not in lanes:
            continue
        a, b = lanes["lane1"], lanes["lane2"]
        ma, mb = a[0], b[0]
        sa, sb = ma.get("start_pose", []), mb.get("start_pose", [])
        if len(sa) < 2 or len(sb) < 2 or math.hypot(sa[0] - sb[0], sa[1] - sb[1]) > 0.05:
            continue
        pairs.append((group, a, b))
    return pairs


def integrate_chunk(actions):
    x = y = yaw = 0.0
    path = []
    for dx, dy, dyaw in actions:
        c, s = math.cos(yaw), math.sin(yaw)
        x, y = x + c * dx - s * dy, y + s * dx + c * dy
        yaw += dyaw
        path.append((x, y, yaw))
    return np.asarray(path, dtype=np.float64)


def path_metrics(actions_a, actions_b):
    pa, pb = integrate_chunk(actions_a), integrate_chunk(actions_b)
    n = min(len(pa), len(pb))
    xy = np.linalg.norm(pa[:n, :2] - pb[:n, :2], axis=1)
    return {
        "path_rms_m": float(np.sqrt(np.mean(xy * xy))),
        "endpoint_m": float(xy[-1]),
        "yaw_rms_rad": float(np.sqrt(np.mean(
            (pa[:n, 2] - pb[:n, 2]) ** 2))),
    }


def median(values):
    return float(statistics.median(values)) if values else None


def metricwise_max(a, b):
    """Conservative envelope of two same-instruction path metrics."""
    return {key: max(float(a[key]), float(b[key])) for key in a}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--episodes-dir", required=True)
    parser.add_argument("--n-groups", type=int, default=12)
    parser.add_argument("--frame-index", type=int, default=5,
                        help="10-Hz row index; 5 is early enough that lane choice "
                             "is not yet visually revealed")
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--sample-seed", type=int, default=20260901)
    parser.add_argument("--instruction-lane1", default="",
                        help="override every lane-1 instruction; use with the "
                             "lane-2 override for a same-observation wording test")
    parser.add_argument("--instruction-lane2", default="")
    parser.add_argument("--condition", default="metadata-paired")
    parser.add_argument("--secondary-instruction-lane1", default="")
    parser.add_argument("--secondary-instruction-lane2", default="")
    parser.add_argument("--secondary-condition", default="")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import torch
    from PIL import Image
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    print(f"loading {args.checkpoint} on {device}")
    policy = SmolVLAPolicy.from_pretrained(args.checkpoint).to(device).eval()
    preproc, postproc = make_pre_post_processors(policy.config, args.checkpoint)
    cam_key = next(key for key in policy.config.input_features
                   if key.startswith("observation.images."))

    def act(image, state, task, seed):
        torch.manual_seed(int(seed))
        tensor = (torch.from_numpy(image.copy()).permute(2, 0, 1).float()
                  / 255.0).unsqueeze(0)
        batch = {cam_key: tensor,
                 "observation.state": torch.tensor(
                     state, dtype=torch.float32).unsqueeze(0),
                 "task": [task]}
        batch = preproc(batch)
        with torch.inference_mode():
            action = policy.predict_action_chunk(batch)
        return postproc(action).squeeze(0).float().cpu().numpy()

    def act_mean(image, state, task, seeds):
        return np.mean([act(image, state, task, seed) for seed in seeds], axis=0)

    pairs = matched_pairs(episode_records(os.path.abspath(args.episodes_dir)))
    random.Random(args.sample_seed).shuffle(pairs)
    pairs = pairs[:args.n_groups]
    if len(pairs) < args.n_groups:
        print(f"warning: requested {args.n_groups} groups, found {len(pairs)}")
    if not pairs:
        raise SystemExit("no complete lane counterfactual groups found")

    primary = list(range(args.seeds))
    alternate = list(range(args.seeds, 2 * args.seeds))
    rows_out = []
    for index, (group, lane1, lane2) in enumerate(pairs, start=1):
        meta1, base1, rows1 = lane1
        meta2 = lane2[0]
        row = rows1[min(args.frame_index, len(rows1) - 1)]
        image_path = os.path.join(base1, row["frame"])
        image = np.asarray(Image.open(image_path).convert("RGB"))
        gray = np.full_like(image, 128)
        state = row["state"]
        task1 = args.instruction_lane1 or meta1["instruction"]
        task2 = args.instruction_lane2 or meta2["instruction"]

        a = act_mean(image, state, task1, primary)
        b = act_mean(image, state, task2, primary)
        same = act_mean(image, state, task1, alternate)
        same_lane2 = act_mean(image, state, task2, alternate)
        masked = act_mean(gray, state, task1, primary)
        lang = path_metrics(a, b)
        noise = path_metrics(a, same)
        noise_lane2 = path_metrics(b, same_lane2)
        noise_conservative = metricwise_max(noise, noise_lane2)
        vision = path_metrics(a, masked)
        item = {
            "group": group,
            "frame": os.path.relpath(image_path, args.episodes_dir),
            "state": state,
            "instruction_lane1": task1,
            "instruction_lane2": task2,
            "language": lang,
            "same_instruction_noise": noise,
            "same_instruction_noise_lane2": noise_lane2,
            "same_instruction_noise_conservative": noise_conservative,
            "gray_image": vision,
            # Keep the averaged raw chunks so the exact bridge transform can
            # be evaluated later without another expensive policy pass.
            "action_means": {
                "lane1": a.tolist(),
                "lane2": b.tolist(),
                "same_instruction": same.tolist(),
                "same_instruction_lane2": same_lane2.tolist(),
                "gray_image": masked.tolist(),
            },
            "language_over_noise": lang["path_rms_m"] /
                                   max(noise["path_rms_m"], 1e-9),
            "language_over_conservative_noise": lang["path_rms_m"] /
                max(noise_conservative["path_rms_m"], 1e-9),
            "vision_over_noise": vision["path_rms_m"] /
                                 max(noise["path_rms_m"], 1e-9),
        }
        if (args.secondary_instruction_lane1
                and args.secondary_instruction_lane2):
            task3 = args.secondary_instruction_lane1
            task4 = args.secondary_instruction_lane2
            c = act_mean(image, state, task3, primary)
            d = act_mean(image, state, task4, primary)
            same_secondary = act_mean(image, state, task3, alternate)
            same_secondary_lane2 = act_mean(
                image, state, task4, alternate)
            secondary = path_metrics(c, d)
            secondary_noise = path_metrics(c, same_secondary)
            secondary_noise_lane2 = path_metrics(d, same_secondary_lane2)
            secondary_noise_conservative = metricwise_max(
                secondary_noise, secondary_noise_lane2)
            item["secondary"] = {
                "condition": args.secondary_condition or "secondary",
                "instruction_lane1": task3,
                "instruction_lane2": task4,
                "language": secondary,
                "same_instruction_noise": secondary_noise,
                "same_instruction_noise_lane2": secondary_noise_lane2,
                "same_instruction_noise_conservative": (
                    secondary_noise_conservative),
                "action_means": {
                    "lane1": c.tolist(),
                    "lane2": d.tolist(),
                    "same_instruction": same_secondary.tolist(),
                    "same_instruction_lane2": same_secondary_lane2.tolist(),
                },
                "language_over_noise": secondary["path_rms_m"] /
                                       max(secondary_noise["path_rms_m"], 1e-9),
                "language_over_conservative_noise": (
                    secondary["path_rms_m"] /
                    max(secondary_noise_conservative["path_rms_m"], 1e-9)),
            }
        rows_out.append(item)
        print(f"[{index:02d}/{len(pairs):02d}] {group}: "
              f"language {lang['path_rms_m']:.4f} m, "
              f"noise {noise_conservative['path_rms_m']:.4f} m (max), "
              f"gray {vision['path_rms_m']:.4f} m")

    summary = {
        "n_groups": len(rows_out),
        "frame_index": args.frame_index,
        "seeds_per_mean": args.seeds,
        "language_path_rms_median": median(
            [row["language"]["path_rms_m"] for row in rows_out]),
        "noise_path_rms_median": median(
            [row["same_instruction_noise"]["path_rms_m"] for row in rows_out]),
        "conservative_noise_path_rms_median": median(
            [row["same_instruction_noise_conservative"]["path_rms_m"]
             for row in rows_out]),
        "gray_path_rms_median": median(
            [row["gray_image"]["path_rms_m"] for row in rows_out]),
        "language_over_noise_median": median(
            [row["language_over_noise"] for row in rows_out]),
        "language_over_conservative_noise_median": median(
            [row["language_over_conservative_noise"] for row in rows_out]),
        "vision_over_noise_median": median(
            [row["vision_over_noise"] for row in rows_out]),
        "language_above_noise": sum(
            row["language"]["path_rms_m"] >
            row["same_instruction_noise"]["path_rms_m"] for row in rows_out),
        "language_above_conservative_noise": sum(
            row["language"]["path_rms_m"] >
            row["same_instruction_noise_conservative"]["path_rms_m"]
            for row in rows_out),
        "vision_above_noise": sum(
            row["gray_image"]["path_rms_m"] >
            row["same_instruction_noise"]["path_rms_m"] for row in rows_out),
    }
    secondary_rows = [row["secondary"] for row in rows_out
                      if "secondary" in row]
    if secondary_rows:
        summary["secondary"] = {
            "condition": secondary_rows[0]["condition"],
            "language_path_rms_median": median(
                [row["language"]["path_rms_m"] for row in secondary_rows]),
            "noise_path_rms_median": median(
                [row["same_instruction_noise"]["path_rms_m"]
                 for row in secondary_rows]),
            "conservative_noise_path_rms_median": median(
                [row["same_instruction_noise_conservative"]["path_rms_m"]
                 for row in secondary_rows]),
            "language_over_noise_median": median(
                [row["language_over_noise"] for row in secondary_rows]),
            "language_over_conservative_noise_median": median(
                [row["language_over_conservative_noise"]
                 for row in secondary_rows]),
            "language_above_noise": sum(
                row["language"]["path_rms_m"] >
                row["same_instruction_noise"]["path_rms_m"]
                for row in secondary_rows),
            "language_above_conservative_noise": sum(
                row["language"]["path_rms_m"] >
                row["same_instruction_noise_conservative"]["path_rms_m"]
                for row in secondary_rows),
        }
    report = {
        "checkpoint": os.path.abspath(args.checkpoint),
        "episodes_dir": os.path.abspath(args.episodes_dir),
        "condition": args.condition,
        "instruction_override": {
            "lane1": args.instruction_lane1 or None,
            "lane2": args.instruction_lane2 or None,
        },
        "secondary_instruction_override": {
            "lane1": args.secondary_instruction_lane1 or None,
            "lane2": args.secondary_instruction_lane2 or None,
        },
        "sampling_contract": {
            "observation_sample_seed": args.sample_seed,
            "primary_action_seeds": primary,
            "alternate_action_seeds": alternate,
        },
        "summary": summary,
        "pairs": rows_out,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
