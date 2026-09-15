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
import json
import math
import os
import shutil
import time

import torch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--base-checkpoint", required=True)
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
    ap.add_argument("--action-v10-weight", type=float, default=1.0,
                    help="r21: action-loss multiplier for v10 sessions "
                    "(2026-09-14+). 0.0 = bank v10's language win while "
                    "the action expert keeps the proven v3y-only diet "
                    "(the v10-action oscillation is an open problem, "
                    "docs/ver/20260915_1006).")
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
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.configs.policies import PreTrainedConfig
    from safetensors.torch import load_file

    # PreTrainedConfig dispatches on the "type" field in config.json;
    # calling SmolVLAConfig.from_pretrained directly chokes on it (draccus)
    cfg = PreTrainedConfig.from_pretrained(args.base_checkpoint)
    cfg.freeze_vision_encoder = True   # already adapted in the base run
    cfg.device = "cuda"
    policy = ReasoningSmolVLAPolicy(cfg, ce_weight=args.ce_weight)
    sd = load_file(os.path.join(args.base_checkpoint, "model.safetensors"))
    missing, unexpected = policy.load_state_dict(sd, strict=False)
    # only the new head may be missing; anything else is a real mismatch
    bad = [k for k in missing if not k.startswith("reasoning_head")]
    assert not bad and not unexpected, (bad, unexpected)
    # head init from the checkpoint's lm_head (the ctor used base weights)
    with torch.no_grad():
        policy.reasoning_head.weight.copy_(
            sd["model.vlm_with_expert.vlm.lm_head.weight"])
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
    rds = ReasoningDataset(ds, sidecar, seed=args.seed)
    print(f"dataset: {len(rds)} frames, sidecar {rds.n_rows} segment rows")
    sampler = None
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
                    elif "car" in joined:
                        w[i] = args.obstacle_boost
                    break
        n_go = int((w == args.obstacle_boost * 6.0).sum())
        n_ramp = int((w == args.obstacle_boost * 4.0).sum())
        print(f"GO-transition frames boosted x{args.obstacle_boost * 6:.0f}:"
              f" {n_go}; braking-ramp frames "
              f"x{args.obstacle_boost * 4:.0f}: {n_ramp}")
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
                              not in row["packed_episode"]):
                            # v3y-era (July/Aug) cruise: the OTHER teacher's
                            # line for the same sentences (r18 mode-mix fix)
                            v3y_cruise_eps.add(row["lerobot_episode_index"])
            except OSError:
                print("WARNING: no nav_vla_index.jsonl — v9 damping off")
            v10_eps = set()
            try:
                with open(os.path.join(args.dataset,
                                       "nav_vla_index.jsonl")) as f:
                    for line in f:
                        row = json.loads(line)
                        if "session_2026091" in row["packed_episode"]:
                            v10_eps.add(row["lerobot_episode_index"])
            except OSError:
                pass
            n_damp = n_cruise = n_nonv10 = n_v10 = 0
            for i in range(len(ds)):
                e = int(epi[i])
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
            }}}
    preproc, _ = make_pre_post_processors(policy.config,
                                          args.base_checkpoint,
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
        for f in os.listdir(args.base_checkpoint):
            if f not in ("model.safetensors", "config.json") and \
                    os.path.isfile(os.path.join(args.base_checkpoint, f)):
                shutil.copy2(os.path.join(args.base_checkpoint, f),
                             os.path.join(d, f))
        try:
            preproc.save_pretrained(d)
        except Exception as e:                              # noqa: BLE001
            print(f"preprocessor save failed ({e}) — base copies remain")
        link = os.path.join(args.out, "checkpoints", "last")
        if os.path.islink(link):
            os.remove(link)
        os.symlink(f"{step:06d}", link)
        print(f"saved {d}")

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
        ce_weight = batch.pop("reasoning_weight", None)
        act_weight = batch.pop("action_weight", None)
        batch = preproc(batch)
        batch = {k: (v.to(device, non_blocking=True)
                     if torch.is_tensor(v) else v)
                 for k, v in batch.items()}
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
