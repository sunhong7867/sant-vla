"""L5 step 2: train the small location head on frozen SmolVLA features (name-conditioned and name-blind), evaluate A-D.

Prereg: docs/experiments/goto_object/20261013_2054_l5-location-head.md
usage: python3 l5_train.py <l5_dir>
"""
import hashlib, json, math, sys
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F

D = sys.argv[1]
RARE = {'green car', 'red car', 'blue car', 'person', 'green cone', 'robot', 'dinosaur'}
import os
NEW = set(filter(None, os.environ.get('L5_NEW', 'horse,blue cone').split(',')))   # names never used as a training query
TAG = os.environ.get('L5_TAG', '')            # '_all' -> demo head trained on every corpus name
TOL = 46.0
XC = torch.tensor([(j % 8 + 0.5) * 80.0 for j in range(48)])
COL = torch.tensor([j % 8 for j in range(48)])
torch.manual_seed(0); np.random.seed(0)


def test_ep(ep):
    return int(hashlib.md5(f'0:{ep}'.encode()).hexdigest(), 16) % 5 == 0


class Head(nn.Module):
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
        sc = s.score(z)[..., 0]                                     # (B,48)
        dx = torch.tanh(s.dx(z)[..., 0]) * 40.0
        none = s.none(z.mean(1))                                    # (B,1)
        col = torch.stack([torch.logsumexp(sc[:, COL == c], 1) for c in range(8)], 1)
        x = (torch.softmax(sc, 1) * (XC.to(sc.device) + dx)).sum(1)
        return torch.cat([col, none], 1), x


def queries(labs, names, split):
    q = []
    for i, l in enumerate(labs):
        if test_ep(l['ep']) != (split == 'test'):
            continue
        nvis = sum(o['vis'] for o in l['objs'])
        seen = set()
        for o in l['objs']:
            n = o['name']
            if n in RARE or n in seen:
                continue
            seen.add(n)
            if split == 'train' and n in NEW:
                continue
            q.append((i, n, o['x'] if o['vis'] else -1.0, nvis))
    return q


def batches(feat, names, q, bs, shuffle):
    idx = np.random.permutation(len(q)) if shuffle else np.arange(len(q))
    for s in range(0, len(q), bs):
        b = [q[j] for j in idx[s:s + bs]]
        fi = np.array([x[0] for x in b]); o = np.argsort(fi)
        f = torch.from_numpy(np.asarray(feat[fi[o]], dtype=np.float32))[np.argsort(o)]
        nv = torch.from_numpy(np.stack([names[x[1]] for x in b])).float()
        x = torch.tensor([x[2] for x in b])
        yield f.cuda(), nv.cuda(), x.cuda(), b


def train(use_name, feat, names, qtr, epochs=6):
    m = Head(use_name).cuda(); opt = torch.optim.AdamW(m.parameters(), 3e-4, weight_decay=0.01)
    steps = epochs * math.ceil(len(qtr) / 256); sch = torch.optim.lr_scheduler.OneCycleLR(opt, 1e-3, total_steps=steps)
    for ep in range(epochs):
        m.train(); tot = 0; n = 0
        for f, nv, x, _ in batches(feat, names, qtr, 256, True):
            logit, xp = m(f, nv)
            vis = x >= 0
            tgt = torch.where(vis, (x.clamp(0, 639) // 80).long(), torch.full_like(x, 8).long())
            loss = F.cross_entropy(logit, tgt) + (F.l1_loss(xp[vis], x[vis]) / 80.0 if vis.any() else 0)
            opt.zero_grad(); loss.backward(); opt.step(); sch.step()
            tot += loss.item() * len(x); n += len(x)
        print(f'  {"name" if use_name else "blind"} epoch {ep} loss {tot / n:.3f}', flush=True)
    return m.eval()


@torch.no_grad()
def predict(m, feat, names, q):
    out = []
    for f, nv, x, b in batches(feat, names, q, 512, False):
        logit, xp = m(f, nv)
        pn = torch.softmax(logit, 1)[:, 8]
        out += list(zip(pn.cpu().numpy(), xp.cpu().numpy()))
    return out


def score(q, pred, sel):
    hit = n = 0
    for (i, nm, x, nvis), (pn, xp) in zip(q, pred):
        if not sel(nm, x, nvis):
            continue
        n += 1; hit += (pn < 0.5) and abs(xp - x) < TOL
    return hit, n


def main():
    labs = [json.loads(l) for l in open(f'{D}/labels.jsonl')]
    feat = np.load(f'{D}/feat.npy', mmap_mode='r')
    names = dict(np.load(f'{D}/names.npz'))
    qtr, qte = queries(labs, names, 'train'), queries(labs, names, 'test')
    print('queries train', len(qtr), 'test', len(qte), flush=True)
    bfeat = np.load(f'{D}/bench_feat.npy'); bnames = json.load(open(f'{D}/bench_names.json'))
    sys.path.insert(0, '/home/sh/ROS2_project/sant-vla/server/code/course')
    bench = json.load(open(f'{D}/bench_cases.json'))
    res = {}
    for use_name in ((True,) if TAG else (True, False)):
        m = train(use_name, feat, names, qtr)
        torch.save(m.state_dict(), f'{D}/head_{"name" if use_name else "blind"}{TAG}.pt')
        pr = predict(m, feat, names, qte); tag = 'name' if use_name else 'blind'
        res[f'{tag}/A'] = score(qte, pr, lambda nm, x, nv: nm not in NEW and x >= 0 and nv >= 2)
        res[f'{tag}/A_single'] = score(qte, pr, lambda nm, x, nv: nm not in NEW and x >= 0 and nv == 1)
        res[f'{tag}/B'] = score(qte, pr, lambda nm, x, nv: nm in NEW and x >= 0 and nv >= 2)
        for nn_ in sorted(NEW | {'horse', 'blue cone'}):
            res[f'{tag}/name_{nn_}'] = score(qte, pr, lambda nm, x, nv, k=nn_: nm == k and x >= 0 and nv >= 2)
        cv = [(p < 0.5) for (i, nm, x, nv), (p, _) in zip(qte, pr) if x >= 0]
        ci = [(p >= 0.5) for (i, nm, x, nv), (p, _) in zip(qte, pr) if x < 0]
        res[f'{tag}/C_vis_said_vis'] = (int(sum(cv)), len(cv)); res[f'{tag}/C_invis_said_none'] = (int(sum(ci)), len(ci))
        # D: lecture-scene bench frames
        bq = [(bnames.index(c['img']), c['en'], c['x'], 2 if c['multi'] else 1) for c in bench]
        bp = predict(m, bfeat, names, bq)
        res[f'{tag}/D'] = score(bq, bp, lambda nm, x, nv: True)
        res[f'{tag}/D_multi'] = score(bq, bp, lambda nm, x, nv: nv == 2)
        res[f'{tag}/D_detail'] = [(c['img'], c['en'], round(c['x']), round(float(xp)), round(float(p), 2)) for c, (p, xp) in zip(bench, bp)]
        for k, v in res.items():
            if k.startswith(tag) and 'detail' not in k:
                print(k, v, f'{v[0] / max(v[1], 1):.3f}', flush=True)
    json.dump(res, open(f'{D}/l5_result{TAG}.json', 'w'), indent=1, ensure_ascii=False, default=float)


main()
