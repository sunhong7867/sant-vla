"""L5 step 1: cache frozen SmolVLA 16-layer image tokens (policy text "Target.") + labels for every visible/invisible object.

Prereg: docs/experiments/goto_object/20261013_2054_l5-location-head.md
out/feat.f16 (N,48,960) memmap, out/labels.jsonl (one line per frame), out/names.npz (name -> 960 vec), out/bench_*.
usage: python3 -P l5_extract.py <data_course_multiobj> <bench_frame_dir> <out_dir>
"""
import glob, json, math, os, sys, time
import numpy as np, torch
from PIL import Image
from safetensors import safe_open
from transformers import AutoModelForImageTextToText, AutoTokenizer

DATA, BENCH, OUT = sys.argv[1:4]
CORPORA = ['packed_gv2b', 'packed_sec', 'packed_sec1', 'packed_sec2', 'packed_gpilot', 'packed_gprobe']
STRIDE = 6
CKPT = '/home/sh/ROS2_project/ros2_vla/models/smolvla_base/model.safetensors'
MID = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
F_PX = 320 / math.tan(1.0856 / 2)
HALF = math.radians(29.0)
NOUN_FIX = {'go_triceratops': 'robot'}                     # Fuel "triceratops toy" is an android robot
EXTRA_NAMES = ['dinosaur', 'robot', 'horse', 'blue cone', 'dog', 'trash can', 'chair', 'red cone', 'animal']
BS = 16


def load():
    m = AutoModelForImageTextToText.from_pretrained(MID, dtype=torch.float32, attn_implementation='sdpa')
    m.model.text_model.layers = m.model.text_model.layers[:16]
    sd = {}
    with safe_open(CKPT, 'pt') as f:
        for k in f.keys():
            if k.startswith('model.vlm_with_expert.vlm.'):
                sd[k[len('model.vlm_with_expert.vlm.'):]] = f.get_tensor(k).float()
    miss, unexp = m.load_state_dict(sd, strict=False)
    assert not unexp, unexp
    return m.to('cuda').eval()


def prep(img):
    w, h = img.size; r = max(w / 512, h / 512); nw, nh = int(w / r), int(h / r)
    out = Image.new('RGB', (512, 512)); out.paste(img.resize((nw, nh), Image.BILINEAR), (0, 0))
    return torch.from_numpy(np.array(out)).permute(2, 0, 1).float() / 255.0 * 2 - 1


@torch.no_grad()
def img_tokens(m, lang, imgs):
    x = torch.stack([prep(i) for i in imgs]).to('cuda')
    with torch.autocast('cuda', dtype=torch.bfloat16):
        vis = m.model.vision_model(pixel_values=x).last_hidden_state
        im = m.model.connector(vis)
    im = im.float(); d = im.shape[-1]; n = im.shape[1]; B = im.shape[0]
    le = m.model.text_model.get_input_embeddings()(lang.expand(B, -1)) * math.sqrt(d)
    emb = torch.cat([im * math.sqrt(d), le], 1); L = emb.shape[1]
    mask = torch.zeros(B, 1, L, L, device='cuda')
    with torch.autocast('cuda', dtype=torch.bfloat16):
        h = m.model.text_model(inputs_embeds=emb, attention_mask=mask).last_hidden_state   # after 16 layers + final norm
    return h[:, :n].float().reshape(B, 8, 8, d)[:, :6].reshape(B, 48, d).cpu().numpy().astype(np.float16)


@torch.no_grad()
def name_vec(m, tok, name):
    ids = tok(f'Go to the {name}.\n', return_tensors='pt').input_ids[0].tolist()
    wid = tok(' ' + name, add_special_tokens=False).input_ids
    pos = next(i for i in range(len(ids)) if ids[i:i + len(wid)] == wid)
    t = torch.tensor([ids], device='cuda')
    d = m.model.text_model.config.hidden_size
    emb = m.model.text_model.get_input_embeddings()(t) * math.sqrt(d)
    L = emb.shape[1]; mask = torch.zeros(1, 1, L, L, device='cuda')
    h = m.model.text_model(inputs_embeds=emb, attention_mask=mask).last_hidden_state
    return h[0, pos:pos + len(wid)].mean(0).float().cpu().numpy()


def frames():
    for c in CORPORA:
        for e in sorted(glob.glob(f'{DATA}/{c}/*/meta.json')):
            meta = json.load(open(e)); g = (meta.get('intent_slots') or {}).get('goto')
            if not g:
                continue
            ep = os.path.dirname(e); rows = [json.loads(l) for l in open(f'{ep}/resampled_10hz.jsonl')]
            for r in rows[::STRIDE]:
                objs = []
                for o in g['objects']:
                    dx, dy = o['x'] - r['x'], o['y'] - r['y']
                    b = math.atan2(dy, dx) - r['heading']; b = (b + math.pi) % (2 * math.pi) - math.pi
                    dist = math.hypot(dx, dy); vis = abs(b) < HALF and dist * math.cos(b) > 1.5
                    objs.append(dict(name=NOUN_FIX.get(o['model'], o['noun']), model=o['model'], b=b, dist=dist,
                                     x=320 - F_PX * math.tan(b) if vis else None, vis=vis))
                yield dict(corpus=c, ep=os.path.basename(ep), frame=f"{ep}/{r['frame']}", objs=objs)


def main():
    os.makedirs(OUT, exist_ok=True)
    m = load(); tok = AutoTokenizer.from_pretrained(MID)
    lang = tok('Target.\n', return_tensors='pt').input_ids.to('cuda')
    labs = list(frames()); N = len(labs); print(N, 'frames', flush=True)
    names = sorted({o['name'] for l in labs for o in l['objs']} | set(EXTRA_NAMES))
    np.savez(f'{OUT}/names.npz', **{n: name_vec(m, tok, n) for n in names})
    with open(f'{OUT}/labels.jsonl', 'w') as f:
        for l in labs:
            f.write(json.dumps(l) + '\n')
    feat = np.lib.format.open_memmap(f'{OUT}/feat.npy', mode='w+', dtype=np.float16, shape=(N, 48, 960))
    t0 = time.time()
    for i in range(0, N, BS):
        chunk = labs[i:i + BS]
        feat[i:i + len(chunk)] = img_tokens(m, lang, [Image.open(l['frame']).convert('RGB') for l in chunk])
        if i % (BS * 100) == 0:
            print(f'{i}/{N} {time.time() - t0:.0f}s', flush=True)
    feat.flush()
    bf = sorted(glob.glob(f'{BENCH}/multi_[ABC].png') + glob.glob(f'{BENCH}/far_go_*.png'))
    np.save(f'{OUT}/bench_feat.npy', np.concatenate([img_tokens(m, lang, [Image.open(p).convert('RGB') for p in bf[i:i + BS]])
                                                     for i in range(0, len(bf), BS)]))
    json.dump([os.path.basename(p)[:-4] for p in bf], open(f'{OUT}/bench_names.json', 'w'))
    print('done', N, len(bf), f'{time.time() - t0:.0f}s', flush=True)


main()
