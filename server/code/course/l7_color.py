"""L7: teach the L5 location head colour phrases ("blue object") and test colour -> unseen-member transfer.

Prereg: docs/experiments/goto_object/20261014_1522_l7-color-phrase-head.md
usage: python3 -P l7_color.py <l5_dir> <smolvla_base model.safetensors>
env L7_MODE=exp (hold out red->fire hydrant, blue->barrel, black->trash can) | all (demo head, nothing held out)
"""
import hashlib, json, math, os, sys
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F

D, CKPT = sys.argv[1], sys.argv[2]
MODE = os.environ.get('L7_MODE', 'exp')
MID = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
COLOR = {'red': ['red cone', 'fire hydrant'], 'blue': ['blue cone', 'barrel'], 'black': ['chair', 'trash can'],
         'yellow': ['yellow cone'], 'white': ['white cone'], 'brown': ['box']}
HELD = {'red': 'fire hydrant', 'blue': 'barrel', 'black': 'trash can'} if MODE == 'exp' else {}
RARE = {'green car', 'red car', 'blue car', 'person', 'green cone', 'robot', 'dinosaur'}
NEG_KEEP = 0.3
TOL = 46.0
XC = torch.tensor([(j % 8 + 0.5) * 80.0 for j in range(48)])
COL = torch.tensor([j % 8 for j in range(48)])
torch.manual_seed(0); np.random.seed(0)


def phrase(c):
    return f'{c} object'


def test_ep(ep):
    return int(hashlib.md5(f'0:{ep}'.encode()).hexdigest(), 16) % 5 == 0


@torch.no_grad()
def phrase_vecs():
    path = f'{D}/colors.npz'
    if os.path.exists(path):
        return dict(np.load(path))
    from safetensors import safe_open
    from transformers import AutoModelForImageTextToText, AutoTokenizer
    m = AutoModelForImageTextToText.from_pretrained(MID, dtype=torch.float32, attn_implementation='sdpa')
    m.model.text_model.layers = m.model.text_model.layers[:16]
    sd = {}
    with safe_open(CKPT, 'pt') as f:
        for k in f.keys():
            if k.startswith('model.vlm_with_expert.vlm.'):
                sd[k[len('model.vlm_with_expert.vlm.'):]] = f.get_tensor(k).float()
    m.load_state_dict(sd, strict=False); m = m.to('cuda').eval()
    tok = AutoTokenizer.from_pretrained(MID)
    out = {}
    for c in COLOR:                                   # identical to l5_extract.name_vec
        name = phrase(c)
        ids = tok(f'Go to the {name}.\n', return_tensors='pt').input_ids[0].tolist()
        wid = tok(' ' + name, add_special_tokens=False).input_ids
        pos = next(i for i in range(len(ids)) if ids[i:i + len(wid)] == wid)
        t = torch.tensor([ids], device='cuda'); d = m.model.text_model.config.hidden_size
        emb = m.model.text_model.get_input_embeddings()(t) * math.sqrt(d)
        L = emb.shape[1]
        h = m.model.text_model(inputs_embeds=emb, attention_mask=torch.zeros(1, 1, L, L, device='cuda')).last_hidden_state
        out[name] = h[0, pos:pos + len(wid)].mean(0).float().cpu().numpy()
    np.savez(path, **out)
    del m; torch.cuda.empty_cache()
    return out


class Head(nn.Module):                                # identical to l5_train.Head
    def __init__(s, use_name, d=960, h=256):
        super().__init__()
        s.use_name = use_name
        s.ti = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, h))
        s.qn = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, h))
        s.const = nn.Parameter(torch.randn(h) * 0.1)
        s.pos = nn.Parameter(torch.zeros(48, h))
        s.mix = nn.Sequential(nn.Linear(3 * h, h), nn.GELU(), nn.Linear(h, h))
        s.enc = nn.TransformerEncoderLayer(h, 4, 2 * h, dropout=0.1, batch_first=True)
        s.score = nn.Linear(h, 1); s.dx = nn.Linear(h, 1); s.none = nn.Linear(h, 1)

    def forward(s, feat, name):
        t = s.ti(feat) + s.pos
        q = s.qn(name) if s.use_name else s.const.expand(feat.shape[0], -1)
        q = q[:, None].expand_as(t)
        z = s.enc(s.mix(torch.cat([t, q, t * q], -1)))
        sc = s.score(z)[..., 0]
        dx = torch.tanh(s.dx(z)[..., 0]) * 40.0
        none = s.none(z.mean(1))
        col = torch.stack([torch.logsumexp(sc[:, COL == c], 1) for c in range(8)], 1)
        x = (torch.softmax(sc, 1) * (XC.to(sc.device) + dx)).sum(1)
        return torch.cat([col, none], 1), x


def queries(labs, split, rng):
    """-> list of (frame idx, query string, x or -1, n visible, kind, member)"""
    q = []
    for i, l in enumerate(labs):
        if test_ep(l['ep']) != (split == 'test'):
            continue
        vis = {o['name']: o['x'] for o in l['objs'] if o['vis']}
        nvis = len(vis)
        seen = set()
        for o in l['objs']:                            # name queries, as head_name_all
            n = o['name']
            if n in RARE or n in seen:
                continue
            seen.add(n)
            q.append((i, n, o['x'] if o['vis'] else -1.0, nvis, 'name', n))
        for c, members in COLOR.items():
            v = [m for m in members if m in vis]
            if split == 'train' and HELD.get(c) in vis:
                continue                               # never teach "blue is not the barrel"
            if split == 'train':
                v = [m for m in v if m != HELD.get(c)]
            if len(v) >= 2:
                continue
            if not v:
                if split == 'test' or rng.random() < NEG_KEEP:
                    q.append((i, phrase(c), -1.0, nvis, 'neg', c))
                continue
            kind = 'held' if v[0] == HELD.get(c) else 'trained'
            q.append((i, phrase(c), vis[v[0]], nvis, kind, f'{c}:{v[0]}'))
    return q


def batches(feat, vecs, q, bs, shuffle):
    idx = np.random.permutation(len(q)) if shuffle else np.arange(len(q))
    for s in range(0, len(q), bs):
        b = [q[j] for j in idx[s:s + bs]]
        fi = np.array([x[0] for x in b]); o = np.argsort(fi)
        f = torch.from_numpy(np.asarray(feat[fi[o]], dtype=np.float32))[np.argsort(o)]
        nv = torch.from_numpy(np.stack([vecs[x[1]] for x in b])).float()
        x = torch.tensor([x[2] for x in b])
        yield f.cuda(), nv.cuda(), x.cuda()


def train(feat, vecs, qtr, epochs=6):
    m = Head(True).cuda(); opt = torch.optim.AdamW(m.parameters(), 3e-4, weight_decay=0.01)
    steps = epochs * math.ceil(len(qtr) / 256); sch = torch.optim.lr_scheduler.OneCycleLR(opt, 1e-3, total_steps=steps)
    for ep in range(epochs):
        m.train(); tot = n = 0
        for f, nv, x in batches(feat, vecs, qtr, 256, True):
            logit, xp = m(f, nv)
            vis = x >= 0
            tgt = torch.where(vis, (x.clamp(0, 639) // 80).long(), torch.full_like(x, 8).long())
            loss = F.cross_entropy(logit, tgt) + (F.l1_loss(xp[vis], x[vis]) / 80.0 if vis.any() else 0)
            opt.zero_grad(); loss.backward(); opt.step(); sch.step()
            tot += loss.item() * len(x); n += len(x)
        print(f'  epoch {ep} loss {tot / n:.3f}', flush=True)
    return m.eval()


@torch.no_grad()
def predict(m, feat, vecs, q):
    out = []
    for f, nv, x in batches(feat, vecs, q, 512, False):
        logit, xp = m(f, nv)
        out += list(zip(torch.softmax(logit, 1)[:, 8].cpu().numpy(), xp.cpu().numpy()))
    return out


def main():
    labs = [json.loads(l) for l in open(f'{D}/labels.jsonl')]
    feat = np.load(f'{D}/feat.npy', mmap_mode='r')
    vecs = dict(np.load(f'{D}/names.npz')); vecs.update(phrase_vecs())
    rng = np.random.default_rng(0)
    qtr, qte = queries(labs, 'train', rng), queries(labs, 'test', rng)
    print(MODE, 'queries train', len(qtr), 'test', len(qte),
          'colour train', sum(k != 'name' for *_, k, _ in qtr), flush=True)
    m = train(feat, vecs, qtr)
    torch.save(m.state_dict(), f'{D}/head_color_{MODE}.pt')
    pr = predict(m, feat, vecs, qte)
    res = {}

    def add(key, hit, n, chance=0.0):
        r = res.setdefault(key, [0, 0, 0.0])
        r[0] += hit; r[1] += n; r[2] += chance
    for (i, s, x, nv, kind, mem), (pn, xp) in zip(qte, pr):
        if kind == 'neg':
            add(f'E3_neg/{mem}', int(pn >= 0.5), 1)
            continue
        hit = int(pn < 0.5 and abs(xp - x) < TOL)
        if kind == 'name':
            if x >= 0 and nv >= 2:
                add('E4_name_multi', hit, 1)
            continue
        add(f'{"E1" if kind == "held" else "E2"}/{mem}', hit, 1, 1.0 / max(nv, 1))
    out = {}
    for k in sorted(res):
        h, n, ch = res[k]
        out[k] = dict(hit=h, n=n, rate=round(h / max(n, 1), 3), chance=round(ch / max(n, 1), 3))
        print(f'{k:28s} {h}/{n} = {h / max(n, 1):.3f}  chance {ch / max(n, 1):.3f}', flush=True)
    for agg in ('E1', 'E2', 'E3_neg'):
        ks = [k for k in res if k.startswith(agg + '/')]
        h = sum(res[k][0] for k in ks); n = sum(res[k][1] for k in ks)
        if n:
            out[agg] = dict(hit=h, n=n, rate=round(h / n, 3))
            print(f'== {agg}: {h}/{n} = {h / n:.3f}', flush=True)
    json.dump(out, open(f'{D}/l7_result_{MODE}.json', 'w'), indent=1)


main()
