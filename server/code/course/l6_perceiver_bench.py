"""L6: can SmolVLM2 (500M / 2.2B) name what is on the road, compared with qwen2.5vl:7b?

Prereg: docs/experiments/goto_object/20261013_2247_l6-smolvlm2-perceiver-bench.md
usage: python3 -P l6_perceiver_bench.py <frame_dir> <out.json> [models...]   models: smol500 smol22 qwen
"""
import base64, io, json, os, re, sys, time
from PIL import Image

FR, OUT = sys.argv[1], sys.argv[2]
MODELS = sys.argv[3:] or ["smol500", "smol22", "qwen"]
Q = ("List every standalone object you can see on or beside the road in this image (not road markings, grass, "
     "flowers or sky). Answer with a comma-separated list of short names only.")
SYN = {"dog": r"dog|pupp|teddy|plush|stuffed", "horse": r"horse|pony|foal",
       "dinosaur": r"dinosaur|dino|t-rex|trex|tyrannosaur|triceratops|raptor",
       "cone": r"cone", "trash": r"trash|bin|garbage|waste|\bcan\b|bucket", "chair": r"chair|seat",
       "box": r"box|crate|cube|cardboard|package"}
BG = r"road|grass|flower|sky|line|lane|marking|tree|field|parking|curb|sidewalk|asphalt|street|ground|lawn|daisy|daisies|white|stripe|car park"


def frames():
    out = [("multi_A", ["horse", "cone", "dog"], "main"), ("multi_B", ["dog", "dinosaur", "cone", "trash"], "main"),
           ("multi_C", ["dinosaur", "box", "horse"], "main"), ("live_now", ["dog", "horse", "trash"], "main")]
    for m, g in (("go_horse", "horse"), ("go_dog", "dog"), ("go_dino_5", "dinosaur")):
        for v in ("-2s", "-2"):
            for d in (12, 18, 25):
                gt = "dog" if (m, v, d) == ("go_horse", "-2s", 12) else g     # contaminated frame shows the dog
                out.append((f"far_{m}_{v}_{d}", [gt], "main"))
    for m, g in (("go_cone_yellow", "cone"), ("go_trashbin", "trash"), ("go_chair", "chair"), ("ob_box", "box")):
        for d in (12, 18, 25):
            out.append((f"far_{m}_-2_{d}", [g], "main"))
    for d in (8, 12, 16, 20, 25, 30, 35):
        out.append((f"far_go_cone_red_+0_{d}", ["cone"], "near"))
    for m, g in (("go_dog", "dog"), ("go_horse", "horse"), ("go_dino_5", "dinosaur"), ("go_dino_3", "dinosaur")):
        for y in ("y0", "y180"):
            for d in (5, 6, 8, 10, 12):
                out.append((f"far_{m}_+0{y}_{d}", [g], "near"))
    return [(f, g, s) for f, g, s in out if os.path.exists(f"{FR}/{f}.png")]


def score(ans, gt):
    names = [a.strip().lower() for a in re.split(r",|\n|;| and ", ans) if a.strip()]
    hit = [g for g in gt if any(re.search(SYN[g], n) for n in names)]
    halluc = [n for n in names if not any(re.search(p, n) for p in SYN.values()) and not re.search(BG, n)]
    return hit, names, halluc


class Smol:
    def __init__(self, mid):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
        self.torch = torch
        self.proc = AutoProcessor.from_pretrained(mid)
        self.m = AutoModelForImageTextToText.from_pretrained(mid, dtype=torch.bfloat16).to("cuda").eval()

    def ask(self, img):
        msgs = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": Q}]}]
        inp = self.proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                            return_dict=True, return_tensors="pt").to("cuda", dtype=self.torch.bfloat16)
        with self.torch.no_grad():
            out = self.m.generate(**inp, do_sample=False, max_new_tokens=60)
        return self.proc.batch_decode(out[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip()


class Qwen:
    def ask(self, img):
        import urllib.request
        b = io.BytesIO(); img.save(b, "JPEG", quality=90)
        p = {"model": "qwen2.5vl:7b", "stream": False, "options": {"temperature": 0, "num_predict": 80},
             "messages": [{"role": "user", "content": Q, "images": [base64.b64encode(b.getvalue()).decode()]}]}
        r = urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:" + os.environ.get("L6_QWEN_PORT", "11502") + "/api/chat", json.dumps(p).encode(),
                                                          {"Content-Type": "application/json"}), timeout=90)
        return json.loads(r.read())["message"]["content"].strip()


def main():
    fr = frames(); res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for name in MODELS:
        model = (Smol("HuggingFaceTB/SmolVLM2-500M-Video-Instruct") if name == "smol500" else
                 Smol("HuggingFaceTB/SmolVLM2-2.2B-Instruct") if name == "smol22" else Qwen())
        rows = []; t0 = time.time()
        for f, gt, st in fr:
            ans = model.ask(Image.open(f"{FR}/{f}.png").convert("RGB"))
            hit, names, hal = score(ans, gt)
            rows.append(dict(frame=f, set=st, gt=gt, answer=ans, hit=hit, halluc=hal))
            print(f"{name:7s} {f:26s} gt={gt} hit={hit} halluc={hal} | {ans[:90]!r}", flush=True)
        res[name] = rows
        for st in ("main", "near"):
            sub = [r for r in rows if r["set"] == st]
            g = sum(len(r["gt"]) for r in sub); h = sum(len(r["hit"]) for r in sub); hl = sum(len(r["halluc"]) for r in sub)
            print(f"== {name} {st}: recall {h}/{g} = {h / max(g, 1):.2f}, halluc/frame {hl / max(len(sub), 1):.2f} "
                  f"({time.time() - t0:.0f}s)", flush=True)
        del model
        try:
            import torch; torch.cuda.empty_cache()
        except Exception:
            pass
        json.dump(res, open(OUT, "w"), indent=1, ensure_ascii=False)


main()
