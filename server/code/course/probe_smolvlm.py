#!/usr/bin/env python3
"""Backbone probe G0, server side (2026-10-03): SmolVLM2-500M on the same
left/centre/right questions as tools/eval/backbone_probe.py (--dump).

This is the FULL SmolVLM2-500M (32 language layers). SmolVLA keeps only the
first 16, so this is an upper bound on what the policy's backbone can know.

  ./venv/bin/python code/course/probe_smolvlm.py questions.jsonl IMG_ROOT
"""
import json
import os
import re
import sys
import time

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

MID = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"


def main():
    qpath, root = sys.argv[1], sys.argv[2]
    proc = AutoProcessor.from_pretrained(MID)
    model = AutoModelForImageTextToText.from_pretrained(
        MID, torch_dtype=torch.bfloat16).to("cuda").eval()
    rows = []
    for line in open(qpath):
        q = json.loads(line)
        img = Image.open(os.path.join(root, os.path.basename(os.path.dirname(os.path.dirname(q["image"]))),
                                      os.path.basename(q["image"]))).convert("RGB")
        ph = q["phrase"] if q["phrase"].startswith(("a ", "an ", "the ")) else "the " + q["phrase"]
        msgs = [{"role": "user", "content": [
            {"type": "image"},
            {"type": "text", "text": f"This is a car's front camera image. Which object is {ph}? "
                                     "Answer with exactly one word: left, center, or right."}]}]
        prompt = proc.apply_chat_template(msgs, add_generation_prompt=True)
        inp = proc(text=prompt, images=[img], return_tensors="pt").to("cuda", torch.bfloat16)
        t0 = time.monotonic()
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=8, do_sample=False)
        dt = time.monotonic() - t0
        txt = proc.batch_decode(out[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0].lower()
        m = re.search(r"\b(left|center|centre|middle|right)\b", txt)
        ans = {"centre": "center", "middle": "center"}.get(m.group(1), m.group(1)) if m else "?"
        rows.append((q["kind"], ans == q["answer"]))
        print(f"{q['kind']:4s} {q['phrase']:34s} gt {q['answer']:6s} pred {ans:6s} "
              f"{'OK ' if ans == q['answer'] else 'BAD'} {dt:4.2f}s  {txt.strip()[:30]!r}", flush=True)
        q.update(pred=ans, ok=ans == q["answer"])
    for kind in ("name", "desc"):
        ok = [r for k, r in rows if k == kind]
        if ok:
            print(f"== SmolVLM2-500M (full 32 layers) {kind}: {sum(ok)}/{len(ok)} = "
                  f"{sum(ok) / len(ok):.0%} (chance ~33%)")


if __name__ == "__main__":
    main()
