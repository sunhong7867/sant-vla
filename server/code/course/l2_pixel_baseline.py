"""Pixel baseline for L2: same composites (same seed), probe on raw pixels / colour histogram instead of VLM features."""
import sys, numpy as np
src = open(sys.argv[1]).read().split('items = build()')[0]
sys.argv = [sys.argv[1]] + sys.argv[2:]; exec(src)
items = build()
y = np.array([it['label'] for it in items]); tr = np.array([it['split'] == 'train' for it in items]); size = np.array([it['size'] for it in items])
pix = np.stack([np.asarray(resize_with_pad(it['img']).resize((32, 32))).ravel() / 255.0 for it in items])
def hist(im):
    a = np.asarray(resize_with_pad(im)).reshape(-1, 3) // 32
    return np.bincount(a[:, 0] * 64 + a[:, 1] * 8 + a[:, 2], minlength=512) / len(a)
hs = np.stack([hist(it['img']) for it in items])
print('majority-class rate on test:', round(max((y[~tr] == c).mean() for c in set(y)), 3))
for nm, F in (('pixels32', pix), ('colourhist', hs)):
    out = {}
    for s in ('L', 'M', 'S', 'all'):
        te = (~tr) & ((size == s) if s != 'all' else True)
        out[s] = round(float(probe(F, y, tr, te).mean()), 3)
    print(nm, out)
