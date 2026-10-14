"""LeRobotDataset wrapper that attaches per-frame reasoning text.

Sidecar contract (built by scripts/build_reasoning_sidecar.py): a jsonl file,
one row per (lerobot episode, frame range):

    {"episode_index": int, "f0": int, "f1": int, "variants": ["...", ...]}

``variants[0]`` is the deterministic skeleton; the rest are fact-checked
paraphrases. ``__getitem__`` samples one uniformly — a fresh draw every
epoch, which is deliberate anti-memorization augmentation. Frames not
covered by any row (should not happen) get an empty string, which the
policy treats as "no reasoning supervision for this sample".
"""

import json
import random
import re

import torch

# Situation phrase (2026-09-30, docs/experiments/log situation-conditioned-action design):
# the reasoning head sees the obstacle but the action expert never reads its
# tokens, so a fixed short phrase derived from the narration is appended to
# the task. Training derives it from the gold skeleton, serving from the
# model's own decode — both through this one function. Nouns are dropped
# (the decoded noun is nearly always "car").
SITUATION_AHEAD = "Situation: obstacle ahead in our lane."
SITUATION_PASSING = "Situation: passing the obstacle."
SITUATION_PAST = "Situation: past the obstacle."
SITUATION_CLEAR = "Situation: road clear."
_AHEAD = re.compile(r"^\s*A (stopped )?[\w ]+? ahead in our\b", re.I)
_PASSING = re.compile(r"^\s*(Passing the (?!T\d)|The [\w ]+? has not moved)", re.I)
_PAST = re.compile(r"^\s*Past the\b", re.I)


def situation_of(text):
    """Narration (label skeleton or decoded text) -> one of four fixed phrases."""
    t = text or ""
    if _AHEAD.search(t):
        return SITUATION_AHEAD
    if _PASSING.search(t):
        return SITUATION_PASSING
    if _PAST.search(t):
        return SITUATION_PAST
    return SITUATION_CLEAR


class ReasoningDataset(torch.utils.data.Dataset):
    def __init__(self, lerobot_dataset, sidecar_path, seed=0,
                 key="reasoning", blank_task=None):
        self.ds = lerobot_dataset
        self.key = key
        # blank_task (2026-10-05): replace EVERY sample's task with this one
        # constant string. This is the vision-action baseline the scope notes
        # have listed as missing since the first goto run: same images, same
        # state, same recipe, no information in the sentence. Without it a
        # claim that language conditioning causes any part of the behaviour
        # has no control to rest on.
        self.blank_task = blank_task
        # Optional per-frame CE weights (indexed like the wrapped dataset).
        # Set by the trainer for language-only boosting: sampling stays at
        # natural frequency so the ACTION loss sees the true distribution,
        # and only the reasoning CE is re-weighted (the r11 lane-centering
        # regression came from boosting both through the sampler).
        self.frame_weights = None
        # Optional per-frame ACTION-loss weights (r13): down-weight the
        # obstacle-phase demonstrations in the flow-matching loss while
        # the language head still learns them at full (boosted) weight.
        self.action_weights = None
        self.rng = random.Random(seed)
        self.by_ep = {}
        n_rows = 0
        with open(sidecar_path) as f:
            for line in f:
                r = json.loads(line)
                self.by_ep.setdefault(r["episode_index"], []).append(
                    (r["f0"], r["f1"], r["variants"]))
                n_rows += 1
        for segs in self.by_ep.values():
            segs.sort()
        self.n_rows = n_rows

    def __len__(self):
        return len(self.ds)

    def _lookup(self, ep, frame):
        for f0, f1, variants in self.by_ep.get(ep, ()):
            if f0 <= frame <= f1:
                return variants
        return None

    def __getitem__(self, idx):
        item = self.ds[idx]
        if self.blank_task is not None:
            item["task"] = self.blank_task
        ep = int(item["episode_index"])
        frame = int(item["frame_index"])
        variants = self._lookup(ep, frame)
        item[self.key] = self.rng.choice(variants) if variants else ""
        # from the deterministic skeleton, not the sampled paraphrase
        item["situation"] = situation_of(variants[0] if variants else "")
        if self.frame_weights is not None:
            item["reasoning_weight"] = float(self.frame_weights[idx])
        if self.action_weights is not None:
            item["action_weight"] = float(self.action_weights[idx])
        return item


def collate_with_text(batch, text_keys=("reasoning", "task", "situation")):
    """default_collate for tensors; plain lists for the text fields."""
    from torch.utils.data._utils.collate import default_collate
    texts = {k: [b.pop(k, "") for b in batch] for k in text_keys
             if any(k in b for b in batch)}
    out = default_collate(batch)
    out.update(texts)
    return out
