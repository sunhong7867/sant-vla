#!/usr/bin/env python3
"""Backbone probe G0 (2026-10-03, weekend plan): can a VLM pick the named object?

Before collecting a go-to-object corpus, check whether the language/vision
backbones can tell WHICH object a phrase refers to at all. If a backbone
cannot answer "which object is the dinosaur / the extinct animal?" from the
camera frame, a policy built on it will not do it either.

Frames: the first frames of go-to-object episodes (meta.json carries the
layout, so the ground-truth left / centre / right comes from the bearings).
Only objects whose direction is unambiguous (unique bucket in the frame) are
asked about.

Backends:
  ollama  qwen2.5vl:3b / qwen2.5vl:7b via http://localhost:11434 (num_gpu 0
          for the CPU-only timing: --cpu)
  (SmolVLM2-500M runs on the lab server: server/code/course/probe_smolvlm.py
   reads the same questions file written with --dump)

Usage:
  python3 tools/eval/backbone_probe.py SESSION_DIR [SESSION_DIR...] \\
      --model qwen2.5vl:3b [--cpu] [--describe] [--max 40] [--dump q.jsonl]
"""
import argparse
import base64
import glob
import json
import os
import re
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "sant_vla_pkg"))
from sant_vla_pkg import goto_layout as G  # noqa: E402

BUCKET_DEG = 8.0


def bucket(bearing_rad):
    d = bearing_rad * 57.2958
    return "left" if d > BUCKET_DEG else "right" if d < -BUCKET_DEG else "center"


def questions(sessions, describe, frame_idx=3):
    out = []
    seen = set()
    for sd in sessions:
        for ep in sorted(glob.glob(os.path.join(sd, "ep_*"))):
            try:
                meta = json.load(open(os.path.join(ep, "meta.json")))
            except OSError:
                continue
            g = (meta.get("intent_slots") or {}).get("goto")
            if not g:
                continue
            key = json.dumps([(round(o["x"], 2), round(o["y"], 2)) for o in g["objects"]])
            if key in seen:            # the two variants share one layout
                continue
            seen.add(key)
            img = os.path.join(ep, "frames", f"{frame_idx:06d}.jpg")
            if not os.path.exists(img):
                continue
            bks = [bucket(o["bearing"]) for o in g["objects"]]
            for o, b in zip(g["objects"], bks):
                if bks.count(b) != 1:
                    continue
                o = dict(o, noun=G.FLEET.get(o["model"], (o["noun"],))[0])
                phrases = [("name", o["noun"])]
                if describe:
                    phrases += [("desc", d) for d in G.DESCRIPTIONS.get(o["noun"], [])]
                for kind, ph in phrases:
                    out.append({"image": img, "phrase": ph, "kind": kind,
                                "noun": o["noun"], "answer": b,
                                "objects": [q["noun"] for q in g["objects"]]})
    return out


def ask_ollama(model, img, phrase, cpu):
    prompt = (f"This is a car's front camera image. Which object is {phrase}? "
              "Answer with exactly one word: left, center, or right.")
    if not phrase.startswith(("a ", "an ", "the ")):
        prompt = prompt.replace(f"is {phrase}?", f"is the {phrase}?")
    body = {"model": model, "prompt": prompt, "stream": False,
            "images": [base64.b64encode(open(img, "rb").read()).decode()],
            "options": {"temperature": 0, "num_ctx": 1024}}
    if cpu:
        body["options"]["num_gpu"] = 0
    req = urllib.request.Request("http://localhost:11434/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    resp = json.load(urllib.request.urlopen(req, timeout=600))
    dt = time.monotonic() - t0
    txt = resp.get("response", "").strip().lower()
    m = re.search(r"\b(left|center|centre|middle|right)\b", txt)
    ans = {"centre": "center", "middle": "center"}.get(m.group(1), m.group(1)) if m else "?"
    return ans, txt[:60], dt


SYN = {"dinosaur": ["dinosaur", "dino", "t-rex", "trex", "tyrannosaur", "triceratops",
                    "styracosaur", "raptor"],
       "person": ["person", "man", "woman", "human", "mannequin", "pedestrian", "figure"],
       "green cone": ["green cone", "green traffic cone", "green"],
       "robot": ["robot", "android"]}


def ask_name(model, img, phrase):
    prompt = (f"Look at this car camera image. Which visible object is {phrase}? "
              "Reply with only the object's common name in lowercase English (one or two words).")
    body = {"model": model, "prompt": prompt, "stream": False,
            "images": [base64.b64encode(open(img, "rb").read()).decode()],
            "options": {"temperature": 0, "num_ctx": 1024}}
    req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    txt = json.load(urllib.request.urlopen(req, timeout=600)).get("response", "").strip().lower()
    return txt[:40], time.monotonic() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--model", default="qwen2.5vl:3b")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--describe", action="store_true", help="also ask description phrases")
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--naming", action="store_true",
                    help="description -> ask for the object's NAME (System-2 rewrite form); "
                         "correct when the reply matches the target's synonyms")
    ap.add_argument("--dump", default=None, help="write the question list (for the server probe)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    qs = questions(a.sessions, a.describe)
    names = [q for q in qs if q["kind"] == "name"][:a.max]
    descs = [q for q in qs if q["kind"] == "desc"][:a.max]
    qs = names + descs
    if a.dump:
        with open(a.dump, "w") as f:
            for q in qs:
                f.write(json.dumps(q) + "\n")
        print(f"wrote {len(qs)} questions to {a.dump}")
        return 0
    rows, lat = [], []
    if a.naming:
        descs = [q for q in qs if q["kind"] == "desc"]
        for q in descs:
            txt, dt = ask_name(a.model, q["image"], q["phrase"])
            ok = any(w in txt for w in SYN.get(q["noun"], [q["noun"]]))
            rows.append({**q, "reply": txt, "ok": ok, "sec": round(dt, 1)})
            print(f"{q['phrase']:36s} target {q['noun']:10s} reply {txt!r:28s} {'OK' if ok else '--'} {dt:4.1f}s")
        k = sum(r["ok"] for r in rows)
        print(f"== {a.model} naming from description: {k}/{len(rows)}")
        if a.out:
            with open(a.out, "w") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return 0
    for q in qs:
        ans, raw, dt = ask_ollama(a.model, q["image"], q["phrase"], a.cpu)
        lat.append(dt)
        rows.append({**q, "pred": ans, "raw": raw, "sec": round(dt, 2),
                     "ok": ans == q["answer"]})
        print(f"{q['kind']:4s} {q['phrase']:34s} gt {q['answer']:6s} pred {ans:6s} "
              f"{'OK ' if ans == q['answer'] else 'BAD'} {dt:5.1f}s")
    for kind in ("name", "desc"):
        rs = [r for r in rows if r["kind"] == kind]
        if rs:
            k = sum(r["ok"] for r in rs)
            print(f"== {a.model}{' (CPU)' if a.cpu else ''} {kind}: {k}/{len(rs)} = "
                  f"{k / len(rs):.0%} (chance ~33%)")
    if lat:
        print(f"latency median {statistics.median(lat):.1f}s, max {max(lat):.1f}s")
    if a.out:
        with open(a.out, "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
