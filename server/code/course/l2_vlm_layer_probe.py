"""L2: is object identity linearly decodable from SmolVLA's 16-layer VLM features, and did fine-tuning (g5d) erase it?

Images: Fuel thumbnails (object masked from white bg) pasted onto policy-camera road frames (g5d eval frames)
at three sizes (object height in the 512x512 SmolVLA input: L ~200 px, M ~80 px, S ~35 px).
Split: train = thumbnail view 1 on P2 frames, test = view 3 on P3b frames (unseen view AND unseen background).
Prefix replicated from lerobot SmolVLA embed_prefix: resize_with_pad 512 (pad 0), x*2-1, vision->connector,
img_emb*sqrt(d), lang "Target." emb*sqrt(d), full (bidirectional) attention over the prefix, 16 text layers.
Feature = mean over image tokens of hidden_states[k], k in {0,4,8,12,16}. Probe = multinomial logistic regression.
Models: hf = HF SmolVLM2-500M truncated to 16 layers, base = smolvla_base VLM, g5d = g5d/015000 VLM.
"""
import glob, json, math, os, random, sys
import numpy as np, torch
from PIL import Image
from safetensors import safe_open
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from transformers import AutoModelForImageTextToText, AutoTokenizer

L1 = sys.argv[1]; OUT = sys.argv[2]; FR = sys.argv[3]
CKPT = {'base': '/home/sh/ROS2_project/ros2_vla/models/smolvla_base/model.safetensors', 'g5d': sys.argv[4]}
MID = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
CLASSES = {'lovable_huggable_cuddly_': 'teddy bear', 'dog': 'plush toy', 'dino_3': 'dinosaur', 'dino_4': 'dinosaur',
           'dino_5': 'dinosaur', 'breyer_horse_of_the_year': 'horse', 'great_dinos_triceratops_': 'robot',
           'fire_hydrant': 'fire hydrant', 'trashbin': 'trash can', 'visitorchair': 'chair',
           'banana_for_scale': 'banana', 'orange': 'orange'}
SIZES = {'L': 200, 'M': 80, 'S': 35}
N_PER = 12
LAYERS = [0, 4, 8, 12, 16]

def cutout(p):
    a = np.asarray(Image.open(p).convert('RGB')).astype(np.int16)
    bg = a[2, 2]; m = (np.abs(a - bg).max(-1) > 18)
    ys, xs = np.where(m); a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]; m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    rgba = np.dstack([a.astype(np.uint8), (m * 255).astype(np.uint8)])
    return Image.fromarray(rgba, 'RGBA')

def compose(obj, bg, h512, rnd):
    bg = bg.copy(); W, H = bg.size                     # 640x480 -> 512x384 after pad-resize, scale 0.8
    h = max(8, int(h512 / 0.8 * rnd.uniform(0.85, 1.15))); w = max(4, int(obj.width * h / obj.height))
    o = obj.resize((w, h), Image.BILINEAR)
    if rnd.random() < 0.5: o = o.transpose(Image.FLIP_LEFT_RIGHT)
    x = rnd.randint(0, max(0, W - w)); y = rnd.randint(int(H * 0.45), max(int(H * 0.45), H - h))   # on the road half
    bg.paste(o, (x, min(y, H - h)), o); return bg

def build():
    th = sorted(glob.glob(f'{L1}/thumb_*_v[13].png')); rnd = random.Random(0); items = []
    bgs = {'train': sorted(glob.glob(f'{FR}/g5d_015000_P2_frames/*.jpg')), 'test': sorted(glob.glob(f'{FR}/g5d_015000_P3b_frames/*.jpg'))}
    for p in th:
        stem = os.path.basename(p)[6:-7]; lab = CLASSES.get(stem)
        if lab is None: continue
        split = 'train' if p.endswith('_v1.png') else 'test'; obj = cutout(p)
        for s, h in SIZES.items():
            for i in range(N_PER):
                bg = Image.open(rnd.choice(bgs[split])).convert('RGB')
                items.append(dict(img=compose(obj, bg, h, rnd), label=lab, split=split, size=s, src=stem))
    return items

def resize_with_pad(img, W=512, H=512):
    w, h = img.size; r = max(w / W, h / H); nw, nh = int(w / r), int(h / r)
    out = Image.new('RGB', (W, H), (0, 0, 0)); out.paste(img.resize((nw, nh), Image.BILINEAR), (0, 0))   # lerobot pads right/bottom
    return out

def load(name):
    m = AutoModelForImageTextToText.from_pretrained(MID, torch_dtype=torch.float32)
    m.model.text_model.layers = m.model.text_model.layers[:16]
    if name != 'hf':
        sd = {}
        with safe_open(CKPT[name], 'pt') as f:
            for k in f.keys():
                if k.startswith('model.vlm_with_expert.vlm.'):
                    sd[k[len('model.vlm_with_expert.vlm.'):]] = f.get_tensor(k).float()
        miss, unexp = m.load_state_dict(sd, strict=False)
        print(name, 'missing', len(miss), miss[:3], 'unexpected', len(unexp), unexp[:3], flush=True)
    return m.to('cuda').eval()

@torch.no_grad()
def feats(m, tok, items):
    lang = tok('Target.\n', return_tensors='pt').input_ids.to('cuda')
    out = {k: [] for k in LAYERS}
    for it in items:
        x = torch.from_numpy(np.asarray(resize_with_pad(it['img']))).permute(2, 0, 1).float()[None] / 255.0
        x = (x * 2 - 1).to('cuda')
        vis = m.model.vision_model(pixel_values=x).last_hidden_state
        img = m.model.connector(vis); d = img.shape[-1]
        img = img * math.sqrt(d)
        le = m.model.text_model.get_input_embeddings()(lang) * math.sqrt(d)
        emb = torch.cat([img, le], 1); L = emb.shape[1]
        mask = torch.zeros(1, 1, L, L, device='cuda')                       # full attention over the prefix
        hs = m.model.text_model(inputs_embeds=emb, attention_mask=mask, output_hidden_states=True).hidden_states
        n = img.shape[1]
        for k in LAYERS: out[k].append(hs[k][0, :n].mean(0).cpu().numpy())
    return {k: np.stack(v) for k, v in out.items()}

def probe(F, y, tr, te, shuffle=False):
    ytr = y[tr].copy()
    if shuffle: np.random.default_rng(0).shuffle(ytr)
    sc = StandardScaler().fit(F[tr]); clf = LogisticRegression(max_iter=3000, C=0.5).fit(sc.transform(F[tr]), ytr)
    return clf.predict(sc.transform(F[te])) == y[te]

items = build(); os.makedirs(OUT, exist_ok=True)
for i in (0, 13, 26, len(items) - 1): items[i]['img'].save(f'{OUT}/example_{i}_{items[i]["label"].replace(" ", "_")}_{items[i]["size"]}.jpg')
y = np.array([it['label'] for it in items]); split = np.array([it['split'] for it in items]); size = np.array([it['size'] for it in items])
tr = split == 'train'
print(len(items), 'images,', len(set(y)), 'classes, train', tr.sum(), 'test', (~tr).sum(), flush=True)
tok = AutoTokenizer.from_pretrained(MID)
res = {}; sds = {}
for name in ('hf', 'base', 'g5d'):
    m = load(name)
    sds[name] = {k: v.detach().cpu().clone() for k, v in m.state_dict().items() if 'text_model.layers.15.' in k or 'connector' in k or 'vision_model.encoder.layers.11.' in k}
    F = feats(m, tok, items); del m; torch.cuda.empty_cache()
    for k in LAYERS:
        for s in ('L', 'M', 'S', 'all'):
            te = (~tr) & ((size == s) if s != 'all' else True)
            res[f'{name}/h{k}/{s}'] = float(probe(F[k], y, tr, te)[size[te] == size[te]].mean())
        res[f'{name}/h{k}/shuffled'] = float(probe(F[k], y, tr, ~tr, shuffle=True).mean())
        print(name, f'h{k}', {s: round(res[f"{name}/h{k}/{s}"], 3) for s in ('L', 'M', 'S', 'all', 'shuffled')}, flush=True)
for a, b in (('hf', 'base'), ('base', 'g5d')):
    diffs = {}
    for k in sds[a]:
        part = 'vision' if 'vision_model' in k else 'connector' if 'connector' in k else 'text_L15'
        diffs[part] = max(diffs.get(part, 0.0), float((sds[a][k] - sds[b][k]).abs().max()))
    res[f'weightdiff/{a}-{b}'] = diffs; print('max |w diff|', a, b, diffs)
json.dump(res, open(f'{OUT}/l2_result.json', 'w'), indent=1)
