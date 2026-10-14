"""L4: does an object name in SmolVLA's 16-layer VLM point at that object in the image (no training)?

Prereg: docs/experiments/goto_object/20261013_2045_l4-word-image-alignment.md
Prefix replicated as in l2_vlm_layer_probe.py (resize_with_pad 512, x*2-1, vision->connector, *sqrt(d), full attention).
Image tokens are an 8x8 row-major grid; rows 0-5 hold the 640x480 frame (bottom rows are padding).
M1 = attention from name tokens to image tokens (head mean, layer 1-16 mean)  <- primary
M2 = cosine(name hidden, image hidden) layer mean; M3 = logit lens of h16 image tokens on the first name token.
usage: python3 l4_word_image_align.py <frame_dir> <out.json>
"""
import json, math, os, sys
import numpy as np, torch
from PIL import Image
from safetensors import safe_open
from transformers import AutoModelForImageTextToText, AutoTokenizer

FR = sys.argv[1]; OUT = sys.argv[2]
CKPT = '/home/sh/ROS2_project/ros2_vla/models/smolvla_base/model.safetensors'
MID = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
EN = {'강아지': 'dog', '말': 'horse', '공룡': 'dinosaur', '파란 꼬깔': 'blue cone', '쓰레기통': 'trash can',
      '의자': 'chair', '빨간 꼬깔': 'red cone'}
F_PX = 320 / math.tan(1.0856 / 2)          # 530 px
TOL = 46                                    # ~5 deg


def cases():
    main = [('multi_A', '강아지', 412), ('multi_A', '말', 264), ('multi_B', '공룡', 282), ('multi_B', '파란 꼬깔', 350),
            ('multi_B', '강아지', 175), ('multi_B', '쓰레기통', 380), ('multi_C', '말', 380), ('multi_C', '공룡', 280)]
    out = [dict(img=f, name=n, x=x, set='main', multi=True) for f, n, x in main]
    for m, n in (('go_horse', '말'), ('go_dog', '강아지'), ('go_dino_5', '공룡')):
        for v in ('-2s', '-2'):
            for d in (12, 18, 25):
                if (m, v, d) == ('go_horse', '-2s', 12):
                    continue                       # contaminated: shows the dog
                out.append(dict(img=f'far_{m}_{v}_{d}', name=n, x=320 + F_PX * 2 / d, set='main', multi=False))
    for f, n in (('multi_A', '의자'), ('multi_B', '말'), ('multi_C', '강아지')):
        out.append(dict(img=f, name=n, x=None, set='absent', multi=True))
    for d in (18, 25):
        out += [dict(img=f'far_go_cone_yellow_-2_{d}', name='의자', x=None, set='absent', multi=False),
                dict(img=f'far_go_trashbin_-2_{d}', name='강아지', x=None, set='absent', multi=False),
                dict(img=f'far_go_dog_-2s_{d}', name='말', x=None, set='absent', multi=False)]
    for d in (8, 12, 16, 20, 25, 30, 35):
        out.append(dict(img=f'far_go_cone_red_+0_{d}', name='빨간 꼬깔', x=320, set='center', multi=False))
    for m, n in (('go_dog', '강아지'), ('go_horse', '말'), ('go_dino_5', '공룡'), ('go_dino_3', '공룡')):
        for y in ('y0', 'y180'):
            for d in (5, 6, 8, 10, 12):
                out.append(dict(img=f'far_{m}_+0{y}_{d}', name=n, x=320, set='center', multi=False))
    return out


def resize_with_pad(img, W=512, H=512):
    w, h = img.size; r = max(w / W, h / H); nw, nh = int(w / r), int(h / r)
    out = Image.new('RGB', (W, H), (0, 0, 0)); out.paste(img.resize((nw, nh), Image.BILINEAR), (0, 0))
    return out


def load():
    m = AutoModelForImageTextToText.from_pretrained(MID, torch_dtype=torch.float32, attn_implementation='eager')
    m.model.text_model.layers = m.model.text_model.layers[:16]
    sd = {}
    with safe_open(CKPT, 'pt') as f:
        for k in f.keys():
            if k.startswith('model.vlm_with_expert.vlm.'):
                sd[k[len('model.vlm_with_expert.vlm.'):]] = f.get_tensor(k).float()
    miss, unexp = m.load_state_dict(sd, strict=False)
    print('missing', len(miss), miss[:3], 'unexpected', len(unexp), flush=True)
    return m.to('cuda').eval()


@torch.no_grad()
def maps(m, tok, img, text, word):
    """Return M1, M2, M3 score maps (6x8) for the word's tokens inside text."""
    ids = tok(text, return_tensors='pt').input_ids[0].tolist()
    for wid in (tok(' ' + word, add_special_tokens=False).input_ids, tok(word, add_special_tokens=False).input_ids):
        pos = next((i for i in range(len(ids)) if ids[i:i + len(wid)] == wid), None)
        if pos is not None:
            break
    assert pos is not None, (text, word, ids)
    wpos = list(range(pos, pos + len(wid)))
    x = torch.from_numpy(np.asarray(resize_with_pad(img))).permute(2, 0, 1).float()[None] / 255.0
    x = (x * 2 - 1).to('cuda')
    vis = m.model.vision_model(pixel_values=x).last_hidden_state
    im = m.model.connector(vis); d = im.shape[-1]; n = im.shape[1]
    le = m.model.text_model.get_input_embeddings()(torch.tensor([ids], device='cuda')) * math.sqrt(d)
    emb = torch.cat([im * math.sqrt(d), le], 1); L = emb.shape[1]
    mask = torch.zeros(1, 1, L, L, device='cuda')
    o = m.model.text_model(inputs_embeds=emb, attention_mask=mask, output_hidden_states=True, output_attentions=True)
    wq = [n + p for p in wpos]
    a = torch.stack([at[0, :, wq, :n].mean((0, 1)) for at in o.attentions]).mean(0)          # M1
    cs = []
    for h in o.hidden_states[1:]:
        hw = torch.nn.functional.normalize(h[0, wq].mean(0), dim=-1)
        cs.append(torch.nn.functional.normalize(h[0, :n], dim=-1) @ hw)
    c = torch.stack(cs).mean(0)                                                              # M2
    hn = m.model.text_model.norm(o.hidden_states[-1][0, :n])
    lg = m.lm_head(hn)[:, wid[0]]                                                            # M3
    g = lambda v: v.float().cpu().numpy().reshape(8, 8)[:6]
    return g(a), g(c), g(lg)


def locate(s):
    r, cidx = np.unravel_index(np.argmax(s), s.shape)
    cols = [j for j in (cidx - 1, cidx, cidx + 1) if 0 <= j < 8]
    w = np.array([s[r, j] for j in cols]) - s.min()
    xc = (np.array(cols) + 0.5) * 80.0
    return float((w * xc).sum() / max(w.sum(), 1e-9)), float(s.max()), int(r), int(cidx)


def main():
    m = load(); tok = AutoTokenizer.from_pretrained(MID)
    rows = []
    for c in cases():
        p = os.path.join(FR, c['img'] + '.png')
        if not os.path.exists(p):
            print('missing frame', p, flush=True); continue
        img = Image.open(p).convert('RGB'); en = EN[c['name']]
        r = dict(c)
        for tag, text, word in (('name', f'Go to the {en}.\n', en), ('target', 'Target.\n', 'Target')):
            if tag == 'target':
                ids = tok('Target.\n', add_special_tokens=False).input_ids
                word = tok.decode(ids[:1]).strip()
            M = maps(m, tok, img, text, word)
            for k, s in zip(('M1', 'M2', 'M3'), M):
                xp, peak, rr, cc = locate(s)
                r[f'{tag}_{k}'] = dict(x=xp, peak=peak, row=rr, col=cc)
                if c['x'] is not None:
                    r[f'{tag}_{k}']['hit'] = abs(xp - c['x']) < TOL
            if tag == 'name':
                r['map_M1'] = M[0].round(5).tolist()
        r['center_hit'] = c['x'] is not None and abs(320 - c['x']) < TOL
        rows.append(r)
        print(c['img'], c['name'], 'exp', None if c['x'] is None else round(c['x']),
              ' '.join(f"{k}={round(r['name_'+k]['x'])}{'*' if r['name_'+k].get('hit') else ''}" for k in ('M1', 'M2', 'M3')),
              '| Target M1', round(r['target_M1']['x']), flush=True)
    json.dump(rows, open(OUT, 'w'), indent=1, ensure_ascii=False)
    for st in ('main', 'center'):
        sub = [r for r in rows if r['set'] == st]
        print(f'== {st} n={len(sub)}', {f'{t}_{k}': sum(r[f"{t}_{k}"]["hit"] for r in sub) for t in ('name', 'target') for k in ('M1', 'M2', 'M3')},
              'center', sum(r['center_hit'] for r in sub))
    mu = [r for r in rows if r['set'] == 'main' and r['multi']]
    print(f'== multi n={len(mu)}', {f'{t}_{k}': sum(r[f"{t}_{k}"]["hit"] for r in mu) for t in ('name', 'target') for k in ('M1', 'M2', 'M3')},
          'center', sum(r['center_hit'] for r in mu))
    pres = [r['name_M1']['peak'] for r in rows if r['set'] == 'main']; ab = [r['name_M1']['peak'] for r in rows if r['set'] == 'absent']
    if pres and ab:
        auc = np.mean([[p > q for q in ab] for p in pres])
        print('== present-vs-absent peak AUC (M1)', round(float(auc), 3))


main()
