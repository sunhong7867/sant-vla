#!/usr/bin/env python3
"""Co-train SmolVLA action + reasoning head (custom loop; lerobot 0.4.4).

`lerobot-train` cannot express a second loss, so this is a minimal loop
around ReasoningSmolVLAPolicy: LeRobotDataset + reasoning sidecar ->
preprocessor pipeline -> policy.forward (flow + CE) -> AdamW.

Run on the lab server (GPU1 = 3090) from ~/sunhong/nav-vla::

    CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/train_reasoning.py \
        --dataset data/lerobot/v3y \
        --base-checkpoint runs/navvla_smolvla_v3y/checkpoints/last/pretrained_model \
        --out runs/navvla_reasoning_r1 --steps 20000

The base checkpoint provides action competence and the normalizer stats;
the vision encoder is frozen (it already adapted during the base run) and
the trunk/expert train at a low LR while the reasoning head catches up at
a higher one. Every checkpoint dir is served exactly like a stock one —
the action path is untouched by the subclass.
"""

import argparse
import random
import re
import json
import math
import os
import shutil
import time

import torch


# Reasoning labels name the obstacle by noun since the multi-object axis
# (2026-09-22: box, barrel, cone, barrier, person); older corpora say "car".
OBSTACLE_NOUNS = ("car", "box", "barrel", "cone", "barrier", "person",
                  "obstacle")


def _multiobj_avoid(row):
    """nav_vla_index row -> is this a multi-object AVOIDANCE demo (v1)?

    Multi-object sessions start 2026-09-22 (packed name session_20260922+).
    Only the variant with the obstacle in OUR lane is the avoidance demo;
    v0 (clear) and v2 (other lane) are plain pure-pursuit cruise.
    """
    name = row.get("packed_episode", "")
    try:
        day = int(name.split("session_")[1][:8])
    except (IndexError, ValueError):
        return False
    if day < 20260922:
        return False
    ob = (row.get("intent_slots") or {}).get("obstacle") or {}
    return bool(ob.get("present") and ob.get("in_our_lane"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--base-checkpoint", required=True)
    ap.add_argument("--base-config", default="",
                    help="2026-10-08: take the policy CONFIG from here instead of "
                         "from --base-checkpoint. Needed to start from stock "
                         "lerobot/smolvla_base, whose schema is state[6]/action[6]/"
                         "chunk 50 while ours is state[4]/action[3]/chunk 30 plus the "
                         "two empty camera keys. Tensors whose shape disagrees with "
                         "the config (state_proj, action_in_proj, action_out_proj) are "
                         "dropped from the state dict and keep their fresh init — "
                         "that is the point of the A/B: every goto run so far was "
                         "fine-tuned on the lane-driving model r26, whose off-lane "
                         "prior is to hunt for the track (64%% of closed-loop trials "
                         "went right regardless of the command, and 10k steps of "
                         "100%% goto data moved it only 81%% -> 78%%).")
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--num-workers", type=int, default=8)
    ap.add_argument("--save-freq", type=int, default=5000)
    ap.add_argument("--log-freq", type=int, default=100)
    ap.add_argument("--lr-trunk", type=float, default=1e-5)
    ap.add_argument("--lr-head", type=float, default=5e-5)
    ap.add_argument("--warmup", type=int, default=250)
    ap.add_argument("--ce-weight", type=float, default=0.1)
    ap.add_argument("--grad-clip", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--sample-decode", action="store_true",
                    help="greedy-decode 2 samples at every save (slow)")
    ap.add_argument("--boost-target",
                    choices=("sampler", "language", "resample-comp"),
                    default="sampler",
                    help="sampler: r5-r11 behaviour, weighted resampling "
                    "boosts BOTH losses (this regressed r11's lane "
                    "centering, median 0.88 vs v3y 0.25 m). language: "
                    "natural-frequency sampling; the same weights apply "
                    "to the reasoning CE only, the action expert sees the "
                    "true data distribution.")
    ap.add_argument("--action-v10p-weight", type=float, default=1.0,
                    help="r23: action-loss multiplier for v10p RECOVERY "
                    "demos (session_20260915, jittered-start return-to-lane). "
                    ">1 amplifies the rare closed-loop correction signal r22 "
                    "proved works but was diluted at 10%% (recovery gain "
                    "+0.01 vs demo -0.10). Applied before other v10 rules.")
    ap.add_argument("--action-signal-weight", type=float, default=1.0,
                    help="boost visual-grounded signal-stop episodes "
                    "(session_20260918: red->stop, green->pass)")
    ap.add_argument("--action-multiobj-weight", type=float, default=1.0,
                    help="r29/r30: ABSOLUTE action-loss weight for multi-"
                    "object AVOIDANCE episodes (session_2026092x+, obstacle "
                    "in our lane: brake, watch, pass, return), replacing the "
                    "1/w resample compensation on those frames. Their v0/v2 "
                    "cruise siblings stay under the v3y-cruise rule (pure-"
                    "pursuit line, not the Stanley cruise teacher).")
    ap.add_argument("--action-v10-weight", type=float, default=1.0,
                    help="r21: action-loss multiplier for v10 sessions "
                    "(2026-09-14+). 0.0 = bank v10's language win while "
                    "the action expert keeps the proven v3y-only diet "
                    "(the v10-action oscillation is an open problem, "
                    "docs/experiments/log/20260915_1006).")
    ap.add_argument("--action-crossing-weight", type=float, default=1.0,
                    help="r20: action-loss multiplier for v10 frames "
                    "BEFORE the episode first reaches its commanded lane "
                    "(crossing_cut.json in the dataset root). The oracle's "
                    "slow sweeping lane entries taught mid-gap cruising as "
                    "a stable mode (r19 isolation, 2026-09-15); crossing "
                    "skill itself stays in the corpus via v3y.")
    ap.add_argument("--action-non-v10-weight", type=float, default=1.0,
                    help="r19 diagnostic: action-loss multiplier for every "
                    "frame OUTSIDE the v10 sessions (2026-09-14+). 0.0 "
                    "isolates whether v10 alone yields clean driving.")
    ap.add_argument("--action-v3y-cruise-weight", type=float, default=1.0,
                    help="r18: action-loss multiplier for v3y-era CRUISE "
                    "episodes (ring_goal keeps full weight). r17 mixed two "
                    "teacher styles (YOLO v3y + oracle v10) under the same "
                    "cruise sentences and the policy mode-hopped between "
                    "their lines (periodic mid-gap excursions, measured "
                    "2026-09-15). One consistent cruise teacher only.")
    ap.add_argument("--action-v9-weight", type=float, default=1.0,
                    help="r15: action-loss multiplier for EVERY frame of a "
                    "v9-era episode (packed name session_202609*) — the "
                    "r4 probe proved the v9 corpus, not co-training, costs "
                    "lane centering (0.24 vs 0.54-0.88 m median).")
    ap.add_argument("--action-obstacle-weight", type=float, default=1.0,
                    help="r13: multiply the FLOW-MATCHING loss of every "
                    "boosted (obstacle-phase) frame by this factor. <1 "
                    "keeps those frames narrating at full CE weight while "
                    "their swerve/stop trajectories barely train the "
                    "action expert. Requires --boost-target language.")
    ap.add_argument("--contrast-twin-boost", action="store_true",
                    help="r36 (2026-09-29): give each v0 (empty lane) episode "
                    "the same boost as its v1 (obstacle) sibling at the same "
                    "frame index (cf_group_id pairs from nav_vla_index.jsonl; "
                    "same start + speed, so frames align to ~1.4 m before the "
                    "swerve). Without it the boosted 'ahead' frames all show "
                    "the obstacle and the fixed spot alone predicts a swerve")
    ap.add_argument("--contrast-twin-variants", default="v0",
                    help="2026-10-02: which siblings of a v1 episode get its "
                    "boost under --contrast-twin-boost (comma list). 'v0,v2' "
                    "also weights the adjacent-lane keep-straight twin of the "
                    "v1+v2 pair corpus (packed_boxpair) like its swerve sibling, "
                    "so swerve and its same-start counter-example are sampled "
                    "equally")
    ap.add_argument("--state-dropout", type=float, default=0.0,
                    help="r37: per-sample probability of blanking the "
                    "--state-dropout-dims of the NORMALIZED state (0 = the "
                    "dataset mean). Mid-swerve frames are solvable from "
                    "steer/yaw_rate alone (2579 of 2782 swerve frames in "
                    "packed_swerve), so the image never has to explain them")
    ap.add_argument("--situation-prompt", action="store_true",
                    help="r40: append the fixed situation phrase derived from "
                    "the gold skeleton (reasoning_dataset.situation_of) to the "
                    "task. The action expert never reads reasoning tokens, so "
                    "this is the only path by which the narration's obstacle "
                    "detection reaches the action. Serve with "
                    "vla_policy_server.py --situation-from-reasoning")
    ap.add_argument("--state-dropout-dims", default="1,2",
                    help="state indices for --state-dropout "
                    "(state = speed, yaw_rate, steer[, standstill_s])")
    ap.add_argument("--goto-early-boost", type=float, default=1.0,
                    help="2026-10-04 (r51): sampling weight for the first "
                         "--goto-early-frames frames of goto_object episodes. "
                         "r50 probe: swapping the target noun on the same frame "
                         "moved the predicted path 0.02 m vs 0.55 m in the demos "
                         "— after ~1 s the car already faces the target, so the "
                         "image alone predicts the action and the words are only "
                         "needed at the start. Used only when --obstacle-boost is 1.")
    ap.add_argument("--goto-early-frames", type=int, default=20)
    ap.add_argument("--sector-balance", action="store_true",
                    help="2026-10-08: inverse-frequency resampling over the three "
                         "direction sectors. Per-frame relabelling (to_lerobot "
                         "--sector-per-frame) makes 'ahead' 63%% of frames "
                         "(left 18%%, right 19%%) because every episode ends with "
                         "the target centred; without this the policy's cheapest "
                         "answer is 'go straight'. Sector is read off the task "
                         "sentence, so it costs nothing for non-sector corpora "
                         "(frames with no direction word keep weight 1).")
    ap.add_argument("--blank-task", default="",
                    help="2026-10-05: replace every task string with this "
                         "constant — the vision-action baseline. The data "
                         "itself carries language information (CMI debiased "
                         "0.743 b on g1, 0.965 b on gv2b, both GATE PASS), so "
                         "a matched pair of runs that differ ONLY in whether "
                         "the sentence is informative is what separates a "
                         "data problem from a learning problem.")
    ap.add_argument("--cf-sidecar", default="",
                    help="2026-10-05: counterfactual go-to rows (code/course/make_cf_sidecar.py); "
                         "same frame, another object's name, the teacher's chunk toward it")
    ap.add_argument("--cf-share", type=float, default=0.5,
                    help="probability a frame that has counterfactual rows is swapped for one")
    ap.add_argument("--cf-boost", type=float, default=1.0,
                    help="sampling weight for frames that have counterfactual rows")
    ap.add_argument("--goto-mirror", type=float, default=0.0,
                    help="2026-10-05 (r54): probability of mirroring a goto_object "
                         "sample left<->right — image flipped, yaw rate/steer and "
                         "action dy/dyaw negated, 'left'/'right' (왼쪽/오른쪽) swapped "
                         "in task and reasoning. r52 kept a +0.6..0.9 m left drift "
                         "for EVERY sentence on the closed-loop E frames ('right' "
                         "never crossed it; data left 278 / right 211, CCW-track "
                         "base) — mirroring cancels the side prior by construction. "
                         "goto only: lane words (inner/outer) do not mirror.")
    ap.add_argument("--obstacle-boost", type=float, default=1.0,
                    help="sampling weight for frames whose reasoning "
                         "mentions the parked car (r5 lesson: at natural "
                         "frequency, 10%% of frames, the model ignores the "
                         "car entirely — obstacle mention 7%% on heldout)")
    args = ap.parse_args()

    if os.path.exists(args.out):
        raise SystemExit(f"{args.out} exists — refusing to overwrite "
                         "(same rule as train_smolvla.sh)")

    torch.manual_seed(args.seed)
    device = torch.device("cuda")

    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reasoning_vla import ReasoningDataset, ReasoningSmolVLAPolicy
    from reasoning_vla.reasoning_dataset import collate_with_text
    from reasoning_vla.reasoning_policy import (
        OBS_LANGUAGE_ATTENTION_MASK, OBS_LANGUAGE_TOKENS,
        REASONING_LANG_MASK, REASONING_LANG_TOKENS)
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.configs.policies import PreTrainedConfig
    from safetensors.torch import load_file

    # PreTrainedConfig dispatches on the "type" field in config.json;
    # calling SmolVLAConfig.from_pretrained directly chokes on it (draccus)
    cfg = PreTrainedConfig.from_pretrained(args.base_config or args.base_checkpoint)
    cfg.freeze_vision_encoder = True   # already adapted in the base run
    cfg.device = "cuda"
    policy = ReasoningSmolVLAPolicy(cfg, ce_weight=args.ce_weight)
    sd = load_file(os.path.join(args.base_checkpoint, "model.safetensors"))
    # Drop tensors the config disagrees with, so a stock base can seed the VLM
    # and expert while the schema-bound projections start fresh. Silent on the
    # normal path (shapes all match), loud when it fires.
    own = policy.state_dict()
    dropped = [k for k, v in sd.items()
               if k in own and tuple(own[k].shape) != tuple(v.shape)]
    for k in dropped:
        sd.pop(k)
    if dropped:
        print(f"shape mismatch -> fresh init for {len(dropped)} tensor(s): "
              + ", ".join(dropped[:8]) + (" ..." if len(dropped) > 8 else ""))
    missing, unexpected = policy.load_state_dict(sd, strict=False)
    # only the new head and the dropped projections may be missing
    allow = set(dropped)
    bad = [k for k in missing
           if not k.startswith("reasoning_head") and k not in allow]
    assert not bad and not unexpected, (bad, unexpected)
    # head init from the checkpoint's lm_head (the ctor used base weights)
    if "reasoning_head.weight" not in sd:
        with torch.no_grad():
            policy.reasoning_head.weight.copy_(
                sd["model.vlm_with_expert.vlm.lm_head.weight"])
    else:
        print("base is a reasoning checkpoint — keeping its trained head")
    policy = policy.to(device).train()

    n_train = sum(p.numel() for p in policy.parameters() if p.requires_grad)
    print(f"trainable params: {n_train / 1e6:.1f}M")

    fps = 10
    delta_timestamps = {
        "action": [i / fps for i in range(cfg.chunk_size)]}
    # pyav: the lab box has FFmpeg 4.4, torchcodec needs 5+ (same reason
    # train_smolvla.sh passes --dataset.video_backend=pyav)
    ds = LeRobotDataset("navvla/reasoning", root=args.dataset,
                        delta_timestamps=delta_timestamps,
                        video_backend="pyav")
    sidecar = os.path.join(args.dataset, "reasoning_labels.jsonl")
    rds = ReasoningDataset(ds, sidecar, seed=args.seed,
                           blank_task=args.blank_task or None)
    if args.blank_task:
        print(f"vision-action baseline: every task replaced by {args.blank_task!r}")
    if args.cf_sidecar:
        n_cf, n_fr = rds.load_cf(args.cf_sidecar, args.cf_share)
        print(f"counterfactual rows {n_cf} on {n_fr} frames, swap share {args.cf_share}")
    print(f"dataset: {len(rds)} frames, sidecar {rds.n_rows} segment rows")
    sampler = None
    if args.sector_balance:
        import numpy as _np

        def _sector_of(txt):
            # The lane corpus says "Cruise in the left lane" / "the rightmost
            # lane", so a bare left/right test counts 40 of g5's 130 task
            # strings as direction commands and mis-weights them (2026-10-08).
            # Sector templates never contain "lane"; lane/speed sentences always
            # do — checked against all 130 tasks in g5: 40 with lane, 24 without,
            # and those 24 are exactly goto_layout.SECTOR_TEMPLATES.
            if "lane" in txt or "차선" in txt:
                return None
            if "left" in txt or "왼쪽" in txt:
                return "left"
            if "right" in txt or "오른쪽" in txt:
                return "right"
            if ("ahead" in txt or "정면" in txt or "곧장" in txt
                    or "front of you" in txt or "앞에 있는" in txt):
                return "ahead"
            return None

        tdf = ds.meta.tasks
        idx2txt = {int(v): str(k) for k, v in zip(tdf.index, tdf["task_index"])}
        ti = _np.asarray(ds.hf_dataset["task_index"]).astype(int)
        secs = _np.array([_sector_of(idx2txt.get(int(i), "")) or "" for i in ti])
        counts = {nm: int((secs == nm).sum()) for nm in ("left", "ahead", "right")}
        n_lab = sum(counts.values())
        w = _np.ones(len(secs), dtype=_np.float64)
        if n_lab:
            tgt = n_lab / 3.0
            for nm, c in counts.items():
                if c:
                    w[secs == nm] = tgt / c
        print(f"sector balance: {counts} of {len(secs)} frames -> weights "
              + ", ".join(f"{nm} x{(n_lab / 3.0 / c):.2f}" for nm, c in counts.items() if c))
        sampler = torch.utils.data.WeightedRandomSampler(
            torch.from_numpy(w), num_samples=len(rds), replacement=True)
    if args.obstacle_boost > 1.0:
        # frame-level weights from the sidecar: any frame covered by a
        # segment whose variants mention the car gets the boost
        import numpy as np
        w = np.ones(len(ds), dtype=np.float64)
        ep_starts = {}
        # LeRobotDataset maps global index -> (episode_index, frame_index)
        # via hf dataset columns; read them once
        epi = ds.hf_dataset["episode_index"]
        fri = ds.hf_dataset["frame_index"]
        # Three tiers. r8 lesson: detection is solved at 4x, phases bind at
        # 8x, but the GO TRANSITION — the ~10 frames where the demonstrator
        # commits from standstill to the pass — is still ~1e-4 of the flow
        # loss and the live policy parks forever. Those frames (the head of
        # every "has not moved" segment) get 6x the base boost (24x).
        PHASE_PAT = ("watching", "has not moved", "returning to the")
        GO_HEAD_FRAMES = 10
        for i in range(len(ds)):
            e, fidx = int(epi[i]), int(fri[i])
            for f0, f1, variants in rds.by_ep.get(e, ()):
                if f0 <= fidx <= f1:
                    joined = " ".join(variants).lower()
                    if "has not moved" in joined and \
                            fidx < f0 + GO_HEAD_FRAMES:
                        w[i] = args.obstacle_boost * 6.0
                    elif "ahead in our" in joined:
                        # the braking ramp: r9 reversal showed the live
                        # policy under-stops into body contact — these are
                        # the frames that demonstrate the stop line
                        w[i] = args.obstacle_boost * 4.0
                    elif any(p in joined for p in PHASE_PAT):
                        w[i] = args.obstacle_boost * 2.0
                    elif any(n in joined for n in OBSTACLE_NOUNS):
                        w[i] = args.obstacle_boost
                    break
        n_go = int((w == args.obstacle_boost * 6.0).sum())
        n_ramp = int((w == args.obstacle_boost * 4.0).sum())
        print(f"GO-transition frames boosted x{args.obstacle_boost * 6:.0f}:"
              f" {n_go}; braking-ramp frames "
              f"x{args.obstacle_boost * 4:.0f}: {n_ramp}")
        if args.contrast_twin_boost:
            groups = {}
            try:
                with open(os.path.join(args.dataset,
                                       "nav_vla_index.jsonl")) as f:
                    for line in f:
                        row = json.loads(line)
                        if row.get("cf_group_id") and row.get("cf_variant_id"):
                            groups.setdefault(row["cf_group_id"], {})[
                                row["cf_variant_id"]] = \
                                row["lerobot_episode_index"]
            except OSError:
                print("WARNING: no nav_vla_index.jsonl — no twin boost")
            by_ep = {}
            for i in range(len(ds)):
                by_ep.setdefault(int(epi[i]), {})[int(fri[i])] = i
            n_twin = n_pairs = 0
            twin_vs = [v.strip() for v in args.contrast_twin_variants.split(",") if v.strip()]
            for vs in groups.values():
                e1 = vs.get("v1")
                if e1 is None:
                    continue
                for tv in twin_vs:
                    e0 = vs.get(tv)
                    if e0 is None:
                        continue
                    n_pairs += 1
                    f0map = by_ep.get(e0, {})
                    for fidx, i1 in by_ep.get(e1, {}).items():
                        i0 = f0map.get(fidx)
                        if i0 is not None and w[i1] > 1.0 and w[i0] == 1.0:
                            w[i0] = w[i1]
                            n_twin += 1
            print(f"contrast twin boost: {n_twin} {'/'.join(twin_vs)} frames matched to "
                  f"their v1 sibling's weight ({n_pairs} twin/v1 pairs)")
            # sampled share per variant after all weighting (2026-10-02: the
            # r43 corpus looked "balanced" but v1 got ~20 % of samples)
            ep_var = {}
            for vs in groups.values():
                for v, e in vs.items():
                    ep_var[e] = v
            tot = float(w.sum())
            share = {}
            for i in range(len(ds)):
                v = ep_var.get(int(epi[i]), "other")
                share[v] = share.get(v, 0.0) + float(w[i])
            print("sampled share by variant: " + ", ".join(
                f"{v} {100 * x / tot:.1f}%" for v, x in sorted(share.items())))
        n_boost = int((w > 1.0).sum())
        print(f"obstacle boost x{args.obstacle_boost}: "
              f"{n_boost}/{len(ds)} frames (target={args.boost_target})")
        if args.boost_target == "resample-comp":
            # r15: r11-style weighted RESAMPLING gives the language head
            # its full exposure to the rare frames (the r11 recipe that
            # reached 100% obstacle mention; CE-only weighting starved it
            # to 2% once the FOV gate shrank the pool). The action loss
            # gets the INVERSE weight, so resampling cancels out and the
            # expert still effectively trains on the natural distribution
            # (importance reweighting) — times the per-episode v9 damping
            # the r4 probe justified.
            sampler = torch.utils.data.WeightedRandomSampler(
                torch.from_numpy(w), num_samples=len(ds), replacement=True)
            aw = 1.0 / w
            v9_eps = set()
            v3y_cruise_eps = set()
            try:
                with open(os.path.join(args.dataset,
                                       "nav_vla_index.jsonl")) as f:
                    for line in f:
                        row = json.loads(line)
                        # v9 collection sessions are 2026-09-04..09; the
                        # v10 speed-invariance corpus (09-14+) must NOT be
                        # damped — its whole point is clean action data.
                        if "session_2026090" in row["packed_episode"]:
                            v9_eps.add(row["lerobot_episode_index"])
                        elif (row.get("intent_id") == "cruise"
                              and "session_20260" in row["packed_episode"]
                              and "session_2026091"
                              not in row["packed_episode"]
                              and "session_20260917"
                              not in row["packed_episode"]
                              and "session_20260918"
                              not in row["packed_episode"]  # Stanley/signal kept
                              and not _multiobj_avoid(row)):
                            # v3y-era (July/Aug) cruise: the OTHER teacher's
                            # line for the same sentences (r18 mode-mix fix).
                            # Multi-object v0/v2 (2026-09-22+, pure-pursuit
                            # cruise, no obstacle in our lane) land here too
                            # and are damped like v3y cruise; the v1
                            # avoidance demos get --action-multiobj-weight.
                            v3y_cruise_eps.add(row["lerobot_episode_index"])
            except OSError:
                print("WARNING: no nav_vla_index.jsonl — v9 damping off")
            v10_eps = set()
            v10p_eps = set()
            signal_eps = set()
            multiobj_eps = set()
            try:
                with open(os.path.join(args.dataset,
                                       "nav_vla_index.jsonl")) as f:
                    for line in f:
                        row = json.loads(line)
                        name = row["packed_episode"]
                        if "session_2026091" in name:
                            v10_eps.add(row["lerobot_episode_index"])
                        # v10p recovery demos (jittered-start, 2026-09-15):
                        # the rare correction signal r22 proved works but was
                        # diluted at 10%. r23 boosts them in the action loss.
                        if "session_20260918" in name:
                            signal_eps.add(row["lerobot_episode_index"])
                        if _multiobj_avoid(row):
                            multiobj_eps.add(row["lerobot_episode_index"])
                        if "session_20260915" in name:
                            v10p_eps.add(row["lerobot_episode_index"])
            except OSError:
                pass
            n_damp = n_cruise = n_nonv10 = n_v10 = n_v10p = n_signal = 0
            n_multiobj = 0
            for i in range(len(ds)):
                e = int(epi[i])
                if args.action_multiobj_weight != 1.0 and e in multiobj_eps:
                    # ABSOLUTE, not compounded with the 1/w resample
                    # compensation: those frames carry w = 4..24 from the
                    # obstacle boost, so "x4" on top of 1/w netted 0.17..1.0
                    # (r29 used the multiplier form; see docs/experiments/avoidance/20260922_2113).
                    aw[i] = args.action_multiobj_weight
                    n_multiobj += 1
                    continue
                if args.action_signal_weight != 1.0 and e in signal_eps:
                    aw[i] *= args.action_signal_weight
                    n_signal += 1
                    continue
                if args.action_v10p_weight != 1.0 and e in v10p_eps:
                    aw[i] *= args.action_v10p_weight
                    n_v10p += 1
                    continue
                if args.action_non_v10_weight != 1.0 and e not in v10_eps:
                    aw[i] *= args.action_non_v10_weight
                    n_nonv10 += 1
                    continue
                if args.action_v10_weight != 1.0 and e in v10_eps:
                    aw[i] *= args.action_v10_weight
                    n_v10 += 1
                    continue
                if args.action_v9_weight != 1.0 and e in v9_eps:
                    aw[i] *= args.action_v9_weight
                    n_damp += 1
                elif (args.action_v3y_cruise_weight != 1.0
                      and e in v3y_cruise_eps):
                    aw[i] *= args.action_v3y_cruise_weight
                    n_cruise += 1
            if args.action_multiobj_weight != 1.0:
                print(f"MULTIOBJ-AVOID action x{args.action_multiobj_weight} "
                      f"on {n_multiobj} frames ({len(multiobj_eps)} avoidance "
                      "episodes)")
            if args.action_signal_weight != 1.0:
                print(f"SIGNAL-STOP action x{args.action_signal_weight} on "
                      f"{n_signal} frames ({len(signal_eps)} signal episodes)")
            if args.action_v10p_weight != 1.0:
                print(f"v10p RECOVERY action x{args.action_v10p_weight} on "
                      f"{n_v10p} frames ({len(v10p_eps)} v10p episodes)")
            if args.action_v10_weight != 1.0:
                print(f"v10 action x{args.action_v10_weight} on "
                      f"{n_v10} frames ({len(v10_eps)} v10 episodes)")
            if args.action_non_v10_weight != 1.0:
                print(f"non-v10 action x{args.action_non_v10_weight} on "
                      f"{n_nonv10} frames ({len(v10_eps)} v10 episodes "
                      "keep full weight)")
            if args.action_crossing_weight != 1.0:
                try:
                    cut = {int(k): v for k, v in json.load(open(
                        os.path.join(args.dataset,
                                     "crossing_cut.json"))).items()}
                except OSError:
                    cut = {}
                    print("WARNING: crossing_cut.json missing — no cut")
                n_cut = 0
                for i in range(len(ds)):
                    c = cut.get(int(epi[i]))
                    if c is not None and int(fri[i]) < c:
                        aw[i] *= args.action_crossing_weight
                        n_cut += 1
                print(f"crossing action x{args.action_crossing_weight} on "
                      f"{n_cut} pre-convergence v10 frames")
            if args.action_v3y_cruise_weight != 1.0:
                print(f"v3y-cruise action x{args.action_v3y_cruise_weight} "
                      f"on {n_cruise} frames "
                      f"({len(v3y_cruise_eps)} episodes)")
            rds.action_weights = aw
            print(f"resample-comp: sampler on, action 1/w compensation; "
                  f"v9 damp x{args.action_v9_weight} on {n_damp} frames "
                  f"({len(v9_eps)} v9-era episodes)")
        elif args.boost_target == "language":
            rds.frame_weights = w
            if args.action_obstacle_weight != 1.0:
                aw = np.where(w > 1.0, args.action_obstacle_weight, 1.0)
                # r14: r13 (phase frames only at 0.2) still probed 0.57 m
                # median vs v3y/r4 0.25 — the v1 avoidance episodes bend
                # cruising even through their non-phase frames, while r4
                # (v3y-only co-training) is clean. Damp the ENTIRE v1
                # episode in the action loss; v0/v2 stay full weight.
                V1_PAT = ("ahead in our", "watching whether",
                          "has not moved", "returning to the")
                v1_eps = {e for e, segs in rds.by_ep.items()
                          if any(any(p in " ".join(v).lower()
                                     for p in V1_PAT)
                                 for _f0, _f1, v in segs)}
                for i in range(len(ds)):
                    if int(epi[i]) in v1_eps:
                        aw[i] = args.action_obstacle_weight
                rds.action_weights = aw
                print(f"action loss x{args.action_obstacle_weight} on "
                      f"{int((aw != 1.0).sum())} frames "
                      f"({len(v1_eps)} v1 episodes fully damped)")
        else:
            sampler = torch.utils.data.WeightedRandomSampler(
                torch.from_numpy(w), num_samples=len(ds), replacement=True)
    if args.goto_early_boost > 1.0 and sampler is None:
        import numpy as np
        goto_eps = set()
        with open(os.path.join(args.dataset, "nav_vla_index.jsonl")) as f:
            for line in f:
                row = json.loads(line)
                if row.get("intent_id") == "goto_object":
                    goto_eps.add(row["lerobot_episode_index"])
        epi = ds.hf_dataset["episode_index"]
        fri = ds.hf_dataset["frame_index"]
        w = np.ones(len(ds), dtype=np.float64)
        for i in range(len(ds)):
            if int(epi[i]) in goto_eps and int(fri[i]) < args.goto_early_frames:
                w[i] = args.goto_early_boost
        n_b = int((w > 1.0).sum())
        print(f"goto early boost x{args.goto_early_boost}: {n_b} frames "
              f"(first {args.goto_early_frames} of {len(goto_eps)} goto episodes), "
              f"sampled share {100 * float(w[w > 1.0].sum()) / float(w.sum()):.1f}%")
        sampler = torch.utils.data.WeightedRandomSampler(
            torch.from_numpy(w), num_samples=len(ds), replacement=True)
    if args.cf_sidecar and args.cf_boost > 1.0 and sampler is None:
        import numpy as np
        epi = ds.hf_dataset["episode_index"]
        fri = ds.hf_dataset["frame_index"]
        w = np.ones(len(ds), dtype=np.float64)
        for i in range(len(ds)):
            if (int(epi[i]), int(fri[i])) in rds.cf:
                w[i] = args.cf_boost
        n_b = int((w > 1.0).sum())
        print(f"cf boost x{args.cf_boost}: {n_b} frames, sampled share "
              f"{100 * float(w[w > 1.0].sum()) / float(w.sum()):.1f}% "
              f"(x cf_share {args.cf_share} swapped)")
        sampler = torch.utils.data.WeightedRandomSampler(
            torch.from_numpy(w), num_samples=len(ds), replacement=True)
    mirror_eps = set()
    if args.goto_mirror > 0.0:
        with open(os.path.join(args.dataset, "nav_vla_index.jsonl")) as f:
            for line in f:
                row = json.loads(line)
                if row.get("intent_id") == "goto_object":
                    mirror_eps.add(row["lerobot_episode_index"])
        print(f"goto mirror p={args.goto_mirror} over {len(mirror_eps)} goto episodes")
    _swap = {"left": "right", "right": "left", "Left": "Right", "Right": "Left",
             "왼쪽": "오른쪽", "오른쪽": "왼쪽"}
    _swap_re = re.compile(r"left|right|Left|Right|왼쪽|오른쪽")

    def mirror_text(t):
        return _swap_re.sub(lambda m: _swap[m.group(0)], t)

    dl = torch.utils.data.DataLoader(
        rds, batch_size=args.batch_size,
        shuffle=(sampler is None), sampler=sampler,
        num_workers=args.num_workers, collate_fn=collate_with_text,
        pin_memory=True, drop_last=True, persistent_workers=True)

    # State-dim adaptation (r8): the v9r4 dataset appends standstill_s, so
    # observation.state is wider than the base checkpoint's config. SmolVLA
    # pads state to max_state_dim (32) before projecting, so the WEIGHTS
    # are unaffected — only the config feature shape and the normalizer
    # stats must follow the dataset (mirrors lerobot_train's
    # preprocessor_overrides when resuming from a pretrained path).
    ds_state_shape = tuple(ds.meta.stats["observation.state"]["mean"].shape)
    cfg_state = policy.config.input_features["observation.state"]
    overrides = {}
    if tuple(cfg_state.shape) != ds_state_shape:
        from lerobot.configs.types import FeatureType, PolicyFeature
        policy.config.input_features["observation.state"] = PolicyFeature(
            type=FeatureType.STATE, shape=ds_state_shape)
        print(f"state feature {tuple(cfg_state.shape)} -> {ds_state_shape} "
              "(dataset carries extra channels)")
    # always normalize with THIS dataset's stats, like lerobot-train
    overrides = {"preprocessor_overrides": {
            "normalizer_processor": {
                "stats": ds.meta.stats,
                "features": {**policy.config.input_features,
                             **policy.config.output_features},
                "norm_map": policy.config.normalization_mapping,
            }},
        # 2026-10-05: the UNnormalizer must use the same stats. Before this only
        # the preprocessor was overridden and the postprocessor files were
        # copied from the base, so serving decoded actions with an older
        # dataset's stats (goto r50-r54: constant ~0.6 m left drift in 3 s,
        # ~3x speed). code/fix_postproc_stats.py repairs old checkpoints.
        "postprocessor_overrides": {
            "unnormalizer_processor": {
                "stats": ds.meta.stats,
                "features": dict(policy.config.output_features),
                "norm_map": policy.config.normalization_mapping,
            }}}
    # The processor pipeline (not just the config) has to come from
    # --base-config: r26's preprocessor carries
    # rename_map {observation.images.front -> observation.images.camera1},
    # which is how a single-camera dataset feeds a three-camera policy. Stock
    # smolvla_base has no such rename, so s3 died at the first batch with
    # "All image features are missing from the batch" (2026-10-08).
    preproc, postproc = make_pre_post_processors(policy.config,
                                          args.base_config or args.base_checkpoint,
                                          **overrides)

    head_params = list(policy.reasoning_head.parameters())
    head_ids = {id(p) for p in head_params}
    trunk_params = [p for p in policy.parameters()
                    if p.requires_grad and id(p) not in head_ids]
    opt = torch.optim.AdamW(
        [{"params": trunk_params, "lr": args.lr_trunk},
         {"params": head_params, "lr": args.lr_head}],
        weight_decay=1e-10, betas=(0.9, 0.95))

    def lr_scale(step):
        if step < args.warmup:
            return step / max(1, args.warmup)
        p = (step - args.warmup) / max(1, args.steps - args.warmup)
        return 0.1 + 0.45 * (1 + math.cos(math.pi * p))

    # snapshot the base checkpoint's extra files now: rp2 (2026-10-05) died at
    # its first save because the base (rp1) was deleted mid-run
    base_files = {f: open(os.path.join(args.base_checkpoint, f), "rb").read()
                  for f in os.listdir(args.base_checkpoint)
                  if f not in ("model.safetensors", "config.json")
                  and os.path.isfile(os.path.join(args.base_checkpoint, f))}

    def save(step):
        d = os.path.join(args.out, "checkpoints", f"{step:06d}",
                         "pretrained_model")
        os.makedirs(d, exist_ok=True)
        policy.save_pretrained(d)
        # serving needs the processor/normalizer files next to the model.
        # Save the LIVE preprocessor (it may carry dataset-stats overrides —
        # copying the base checkpoint's files shipped 3-dim stats with the
        # 4-dim r8 model, 2026-09-08); base files only fill anything the
        # pipeline save does not produce.
        for f, b in base_files.items():
            with open(os.path.join(d, f), "wb") as fh:
                fh.write(b)
        try:
            preproc.save_pretrained(d)
            postproc.save_pretrained(d)
        except Exception as e:                              # noqa: BLE001
            print(f"processor save failed ({e}) — base copies remain")
        link = os.path.join(args.out, "checkpoints", "last")
        if os.path.islink(link):
            os.remove(link)
        os.symlink(f"{step:06d}", link)
        print(f"saved {d}")

    drop_dims = [int(d) for d in args.state_dropout_dims.split(",") if d]
    if args.state_dropout > 0.0:
        print(f"state dropout p={args.state_dropout} on normalized dims "
              f"{drop_dims}")
    if args.situation_prompt:
        print("situation prompt: task += situation_of(skeleton)")
    step, t0, t_log = 0, time.time(), time.time()
    it = iter(dl)
    sample_batch = None
    while step < args.steps:
        try:
            batch = next(it)
        except StopIteration:
            it = iter(dl)
            batch = next(it)
        reasoning = batch.pop("reasoning")
        situation = batch.pop("situation", None)
        ce_weight = batch.pop("reasoning_weight", None)
        act_weight = batch.pop("action_weight", None)
        if mirror_eps:
            flip = [int(e) in mirror_eps and random.random() < args.goto_mirror
                    for e in batch["episode_index"]]
            if any(flip):
                fi = torch.tensor(flip)
                for k in list(batch):
                    if k.startswith("observation.images."):
                        batch[k] = batch[k].clone()
                        batch[k][fi] = batch[k][fi].flip(-1)
                st = batch["observation.state"].clone()
                st[fi, 1:3] = -st[fi, 1:3]          # yaw rate, steer
                batch["observation.state"] = st
                ac = batch["action"].clone()
                ac[fi, ..., 1:3] = -ac[fi, ..., 1:3]   # dy, dyaw
                batch["action"] = ac
                batch["task"] = [mirror_text(t) if f else t for t, f in zip(batch["task"], flip)]
                reasoning = [mirror_text(t) if f else t for t, f in zip(reasoning, flip)]
                if situation is not None:
                    situation = [mirror_text(t) if f else t for t, f in zip(situation, flip)]
        raw_lang = None
        if args.situation_prompt and situation is not None:
            # the reasoning pass must see the RAW task (see
            # reasoning_policy.REASONING_LANG_TOKENS); tokenize it separately
            # clone: never let a second preproc pass touch the tensors the
            # real (action) pass normalizes below
            raw = preproc({k: (v.clone() if torch.is_tensor(v) else
                               list(v) if isinstance(v, list) else v)
                           for k, v in batch.items()})
            raw_lang = (raw[OBS_LANGUAGE_TOKENS],
                        raw[OBS_LANGUAGE_ATTENTION_MASK])
            batch["task"] = [f"{t} {sit}" for t, sit in
                             zip(batch["task"], situation)]
        batch = preproc(batch)
        if raw_lang is not None:
            batch[REASONING_LANG_TOKENS], batch[REASONING_LANG_MASK] = raw_lang
        batch = {k: (v.to(device, non_blocking=True)
                     if torch.is_tensor(v) else v)
                 for k, v in batch.items()}
        if args.state_dropout > 0.0:
            st = batch["observation.state"]
            drop = torch.rand(st.shape[0], device=st.device) \
                < args.state_dropout
            st = st.clone()
            for d in drop_dims:
                st[drop, d] = 0.0
            batch["observation.state"] = st
        batch["reasoning"] = reasoning
        if ce_weight is not None:
            batch["reasoning_weight"] = ce_weight.to(device).float()
        if act_weight is not None:
            batch["action_weight"] = act_weight.to(device).float()
        if sample_batch is None and args.sample_decode:
            sample_batch = {}
            for k, v in batch.items():
                if torch.is_tensor(v):
                    sample_batch[k] = v[:2].clone()
                elif isinstance(v, (list, tuple)):
                    sample_batch[k] = v[:2]
                else:
                    sample_batch[k] = v

        for g, base in zip(opt.param_groups,
                           (args.lr_trunk, args.lr_head)):
            g["lr"] = base * lr_scale(step)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss, ld = policy.forward(batch)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(
            [p for p in policy.parameters() if p.requires_grad],
            args.grad_clip)
        opt.step()
        step += 1

        if step % args.log_freq == 0:
            dt = (time.time() - t_log) / args.log_freq
            t_log = time.time()
            eta_h = dt * (args.steps - step) / 3600
            print(f"step {step:6d}  loss {ld['loss']:.4f}  "
                  f"action {ld.get('action_loss', 0):.4f}  "
                  f"ce {ld.get('reasoning_ce', 0):.3f}  "
                  f"{dt:.3f}s/step  eta {eta_h:.2f}h", flush=True)
        if step % args.save_freq == 0 or step == args.steps:
            save(step)
            if args.sample_decode and sample_batch is not None:
                policy.eval()
                try:
                    for s in policy.generate_reasoning(sample_batch):
                        print(f"  decode: {s}")
                finally:
                    policy.train()

    print(f"done in {(time.time() - t0) / 3600:.2f}h")


if __name__ == "__main__":
    main()
