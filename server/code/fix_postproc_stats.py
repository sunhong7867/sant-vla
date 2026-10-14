#!/usr/bin/env python3
"""Make a checkpoint's action UNnormalizer use the stats it was trained with (2026-10-05).

train_reasoning.py saved the live PREprocessor (dataset stats) but copied the
POSTprocessor from the base checkpoint, so serving un-normalized actions with
an older dataset's stats. For the go-to corpus (g2: dx mean 0.052, dy mean
0.0019, std 0.0096) against the inherited ones (dx 0.173, dy 0.0128, std
0.0207) that is a constant +0.013 m/step left drift (~0.6 m in 3 s with the
yaw term) and ~3x speed — on every frame, every sentence, every seed.

Copies every `action.*` tensor from the preprocessor normalizer into the
postprocessor unnormalizer; the original is kept as *.orig.

    ./venv/bin/python code/fix_postproc_stats.py <ckpt/pretrained_model> [...]
"""
import glob, os, shutil, sys
from safetensors import safe_open
from safetensors.torch import save_file

for ck in sys.argv[1:]:
    pre = glob.glob(os.path.join(ck, "*preprocessor*normalizer*.safetensors"))
    post = glob.glob(os.path.join(ck, "*postprocessor*unnormalizer*.safetensors"))
    if len(pre) != 1 or len(post) != 1:
        print(f"skip {ck}: pre {len(pre)} post {len(post)}"); continue
    with safe_open(pre[0], "pt") as f:
        act = {k: f.get_tensor(k) for k in f.keys() if k.startswith("action.")}
    with safe_open(post[0], "pt") as f:
        old = {k: f.get_tensor(k) for k in f.keys()}
    if all(k in old and old[k].shape == v.shape and bool((old[k] == v).all()) for k, v in act.items()):
        print(f"ok   {ck} (already consistent)"); continue
    if not os.path.exists(post[0] + ".orig"):
        shutil.copy2(post[0], post[0] + ".orig")
    new = dict(old); new.update(act)
    save_file(new, post[0])
    print(f"fix  {ck}: action mean {old['action.mean'].tolist()} -> {act['action.mean'].tolist()}")
