#!/usr/bin/env python3
"""Qwen2.5-VL-3B on the lab server (2026-10-03): the System-2 half of the
go-to-object practice. The laptop's Ollama could not load the VL models next
to the simulator (8.4 GiB system-memory check), so it runs here.

  naming probe:  qwen_vl.py probe QUESTIONS.jsonl IMG_ROOT
                 (questions from tools/eval/backbone_probe.py --describe --dump;
                  description -> ask the object's name, score against synonyms)
  rewrite:       qwen_vl.py rewrite IMG "Go to an extinct animal."
                 -> prints one line: Go to the <name>.
"""
import json
import math
import os
import re
import sys
import time

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

MID = "Qwen/Qwen2.5-VL-3B-Instruct"
SYN = {"dinosaur": ["dinosaur", "dino", "t-rex", "trex", "tyrannosaur", "triceratops",
                    "styracosaur", "raptor"],
       "person": ["person", "man", "woman", "human", "mannequin", "pedestrian", "figure"],
       "green cone": ["green cone", "green traffic cone", "green"],
       "robot": ["robot", "android"]}

_model = _proc = None


def load():
    global _model, _proc
    if _model is None:
        _proc = AutoProcessor.from_pretrained(MID, max_pixels=640 * 480)
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            MID, torch_dtype=torch.bfloat16).to("cuda").eval()
    return _model, _proc


def ask(img_path, text, max_new=12):
    return ask_full(img_path, text, max_new)[0]


def ask_full(img_path, text, max_new=12):
    """-> (reply, W, H) where W x H is the resized image Qwen saw (bbox space)."""
    model, proc = load()
    msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": text}]}]
    prompt = proc.apply_chat_template(msgs, add_generation_prompt=True)
    inp = proc(text=[prompt], images=[Image.open(img_path).convert("RGB")],
               return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=max_new, do_sample=False)
    _t, gh, gw = [int(v) for v in inp["image_grid_thw"][0]]
    txt = proc.batch_decode(out[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip()
    return txt.lower(), gw * 14, gh * 14


HALF_FOV = math.radians(62.2 / 2)
SIDE_EN = {"left": "on the left", "right": "on the right", "ahead": "straight ahead"}


def boxes(txt):
    out = []
    for m in re.finditer(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*"
                         r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]", txt):
        out.append([float(v) for v in m.groups()])
    return out


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def rewrite_pos(img, sentence):
    """System 2 -> the positional words the r52 policy was trained on
    (code/course/relabel_goto_pos.py): Qwen boxes the referred object and every
    object, the box centre gives the side (+-10 deg), the box bottom ranks
    nearer / farther when two share a side. Only words go to SmolVLA."""
    ref, W, H = ask_full(img, f"Instruction for a car: \"{sentence}\". Find the one visible object "
                              "the instruction refers to and output its bounding box as JSON "
                              "[{\"bbox_2d\": [x1, y1, x2, y2], \"label\": \"name\"}].", max_new=60)
    allb, _, _ = ask_full(img, "Detect every separate object standing on the ground (cones, boxes, "
                               "barrels, barriers, cars, animals, people, robots, furniture, bins). "
                               "Output JSON [{\"bbox_2d\": [x1, y1, x2, y2], \"label\": \"name\"}, ...].",
                          max_new=400)
    rb = boxes(ref)
    if not rb:
        return None, ref
    t = rb[0]
    f = (W / 2) / math.tan(HALF_FOV)

    def side(b):
        d = math.degrees(math.atan(((W / 2) - (b[0] + b[2]) / 2) / f))
        return "left" if d > 10 else "right" if d < -10 else "ahead"
    s = side(t)
    others = [b for b in boxes(allb) if iou(b, t) < 0.5 and side(b) == s]
    rank = ""
    if others:
        rank = "nearer" if t[3] >= max(b[3] for b in others) else "farther"
    phrase = f"the {rank + ' ' if rank else ''}object {SIDE_EN[s]}"
    lane = re.search(r"\blane\b|차선", sentence, re.I) is not None
    return (f"Follow the lane to {phrase}." if lane else f"Go to {phrase}."), ref


def name_prompt(phrase):
    return (f"Look at this car camera image. Which visible object is {phrase}? "
            "Reply with only the object's common name in lowercase English (one or two words).")


def main():
    mode = sys.argv[1]
    if mode == "rewrite_pos":
        img, sentence = sys.argv[2], sys.argv[3]
        t0 = time.monotonic()
        to, raw = rewrite_pos(img, sentence)
        print(json.dumps({"to": to or sentence, "raw": raw[:60], "ok": to is not None,
                          "sec": round(time.monotonic() - t0, 1)}, ensure_ascii=False))
        return
    if mode == "rewrite":
        img, sentence = sys.argv[2], sys.argv[3]
        t0 = time.monotonic()
        txt = ask(img, "You control a car. Look at the camera image and the instruction. "
                       f"Instruction: \"{sentence}\"\nWhich visible object does the instruction "
                       "refer to? Reply with only the object's common name in lowercase English "
                       "(one or two words), nothing else.")
        name = re.sub(r"[^a-z ]", "", txt).strip()[:30] or "object"
        print(json.dumps({"to": f"Go to the {name}.", "raw": txt[:60],
                          "sec": round(time.monotonic() - t0, 1)}))
        return
    qpath, root = sys.argv[2], sys.argv[3]
    rows = []
    for line in open(qpath):
        q = json.loads(line)
        if q["kind"] != "desc":
            continue
        ep = os.path.basename(os.path.dirname(os.path.dirname(q["image"])))
        img = os.path.join(root, ep, os.path.basename(q["image"]))
        t0 = time.monotonic()
        txt = ask(img, name_prompt(q["phrase"]))
        ok = any(w in txt for w in SYN.get(q["noun"], [q["noun"]]))
        rows.append(ok)
        print(f"{q['phrase']:36s} target {q['noun']:10s} reply {txt[:28]!r:30s} "
              f"{'OK' if ok else '--'} {time.monotonic() - t0:4.1f}s", flush=True)
    print(f"== Qwen2.5-VL-3B naming from description: {sum(rows)}/{len(rows)}")


if __name__ == "__main__":
    main()
