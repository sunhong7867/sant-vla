"""Per-class test accuracy: g5d h16 VLM features vs colour histogram (same composites)."""
import sys, numpy as np, torch
src = open(sys.argv[1]).read().split('items = build()')[0]
sys.argv = [sys.argv[1]] + sys.argv[2:]; exec(src)
exec(open(sys.argv[0]).read().split('def hist')[0].split('items = build()')[0]) if False else None
items = build()
y = np.array([it['label'] for it in items]); tr = np.array([it['split'] == 'train' for it in items]); size = np.array([it['size'] for it in items])
def hist(im):
    a = np.asarray(resize_with_pad(im)).reshape(-1, 3) // 32
    return np.bincount(a[:, 0] * 64 + a[:, 1] * 8 + a[:, 2], minlength=512) / len(a)
H = np.stack([hist(it['img']) for it in items])
tok = AutoTokenizer.from_pretrained(MID); m = load('g5d'); F = feats(m, tok, items)[16]
print(f"{'class':13s} {'VLM h16 L/M/S':>18s}   {'colour L/M/S':>16s}")
for c in sorted(set(y)):
    row = []
    for X in (F, H):
        r = []
        for s in ('L', 'M', 'S'):
            te = (~tr) & (size == s); ok = probe(X, y, tr, te); r.append(ok[y[te] == c].mean())
        row.append('/'.join(f'{v:.2f}' for v in r))
    print(f'{c:13s} {row[0]:>18s}   {row[1]:>16s}')
