import json, os, glob, math, sys, collections
import numpy as np, torch
from PIL import Image
sys.path.insert(0, "code")
from reasoning_vla import ReasoningSmolVLAPolicy
from lerobot.policies.factory import make_pre_post_processors
dev = torch.device("cuda")
ck = sys.argv[1]
p = ReasoningSmolVLAPolicy.from_pretrained(ck).to(dev).eval()
pre, post = make_pre_post_processors(p.config, ck)
cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
want = p.config.input_features["observation.state"].shape[0]
def lat(ch):
    x = y = yaw = 0.0
    for dx, dy, dyaw in ch:
        x += math.cos(yaw)*dx - math.sin(yaw)*dy; y += math.sin(yaw)*dx + math.cos(yaw)*dy; yaw += dyaw
    return y
res = collections.defaultdict(list)
eps = sorted(glob.glob("data/course/packed_sec/session_*/meta.json"))[:90]
for m in eps:
    d = json.load(open(m)); ep = os.path.dirname(m)
    sec = d["intent_slots"]["goto"]["sector"]
    L = [json.loads(l) for l in open(ep + "/resampled_10hz.jsonl")]
    k = 3
    demo = [r["action"][:3] for r in L[k:k+30]]
    st = list(L[k]["state"]) + [0.0]*(want - len(L[k]["state"]))
    img = np.asarray(Image.open(os.path.join(ep, L[k]["frame"])).convert("RGB").resize((640, 480)))
    t = (torch.from_numpy(img).permute(2,0,1).float()/255.0).unsqueeze(0)
    preds = []
    for sd in (1, 2, 3):
        b = {cam: t, "observation.state": torch.tensor(st, dtype=torch.float32).unsqueeze(0), "task": [d["instruction"]]}
        b = {kk: (v.to(dev) if torch.is_tensor(v) else v) for kk, v in pre(b).items()}
        torch.manual_seed(sd)
        with torch.inference_mode():
            preds.append(lat(post(p.predict_action_chunk(b))[0].float().cpu().numpy()[:, :3]))
    res[sec].append((lat(demo), float(np.mean(preds))))
for sec in ("left", "ahead", "right"):
    a = np.array(res[sec])
    print(f"{sec:6} n={len(a):3d} demo lateral mean {a[:,0].mean():+.2f} m | model {a[:,1].mean():+.2f} m | model on demo side {(np.sign(a[:,1])==np.sign(a[:,0])).sum()}/{len(a)}")
