"""SmolVLA-only object finder for goal_from_scene_node (2026-10-13, L5).

Frozen SmolVLA VLM (smolvla_base, 16 text layers, policy text "Target.") gives 48 image tokens;
a small trained location head (server/code/course/l5_train.py, Head) reads them together with the
name's 16-layer text feature and returns P(not visible) and the image column x (px, 640 wide).
Result (docs/experiments/goto_object/20261013_2054_l5-location-head.md): trained names 99 % within
5 deg on held-out layouts; names never used as a query in training (horse, blue cone, dinosaur, ...)
answer "not visible" — the node then asks the user instead of guessing.
"""
import math
import re

import numpy as np

MID = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
# names the head was trained to find (l5_train.py: not RARE, not NEW)
TRAINED = ("red cone", "yellow cone", "white cone", "fire hydrant", "chair", "trash can", "dog",
           "barrel", "box", "barrier")
# head_name_all.pt (L5_TAG=_all, 10-13 22:00): horse and blue cone were also training queries — a demo
# head, not a generalisation result (held-out episodes: horse 99.8 %, blue cone 99.8 %)
TRAINED_ALL = TRAINED + ("horse", "blue cone")
# head_color_all.pt (L7, 10-14): colour phrases learned as queries — server/code/course/l7_color.py
COLOR_PHRASES = ("red object", "blue object", "black object", "yellow object", "white object", "brown object")
CONES = ("red cone", "yellow cone", "white cone", "blue cone", "green cone")
# Korean words -> English names (the head's vocabulary is the corpus nouns). Longer phrases first.
KO2EN = (
    (r"빨간\s*(?:색\s*)?(?:꼬깔|고깔|콘|라바콘)", ("red cone",)),
    (r"노란\s*(?:색\s*)?(?:꼬깔|고깔|콘|라바콘)", ("yellow cone",)),
    (r"(?:흰|하얀)\s*(?:색\s*)?(?:꼬깔|고깔|콘|라바콘)", ("white cone",)),
    (r"파란\s*(?:색\s*)?(?:꼬깔|고깔|콘|라바콘)", ("blue cone",)),
    (r"(?:초록|녹색)\s*(?:색\s*)?(?:꼬깔|고깔|콘|라바콘)", ("green cone",)),
    (r"꼬깔|고깔|라바콘|콘(?!센트)", CONES),
    # bare colour words ("파란색 물체로 가봐"); a colour right before an object name stays part of that name
    (r"(?:빨간|빨강)\s*색?(?:\s*(?:물체|물건|것|거|건))?", ("red object",)),
    (r"(?:파란|파랑)\s*색?(?:\s*(?:물체|물건|것|거|건))?", ("blue object",)),
    (r"(?:검은|검정|까만|까망)\s*색?(?:\s*(?:물체|물건|것|거|건))?", ("black object",)),
    (r"(?:노란|노랑)\s*색?(?:\s*(?:물체|물건|것|거|건))?", ("yellow object",)),
    (r"(?:흰|하얀)\s*색?(?:\s*(?:물체|물건|것|거|건))?", ("white object",)),
    (r"갈색(?:\s*(?:물체|물건|것|거|건))?", ("brown object",)),
    (r"소화전", ("fire hydrant",)),
    (r"의자", ("chair",)),
    (r"쓰레기통|휴지통", ("trash can",)),
    (r"강아지|강이지|강아쥐|강쥐|멍멍이|개(?=[와과랑로에한까쪽\s]|$)", ("dog",)),   # 10-13: "강이지" typo went unmatched
    (r"드럼통|배럴|통(?=[으로에까쪽\s]|$)", ("barrel",)),
    (r"상자|박스", ("box",)),
    (r"바리케이[드트]|바리게이[드트]|방벽", ("barrier",)),
    (r"(?<![가-힣])말(?=[로에한까쪽\s]|$)", ("horse",)),
    (r"공룡", ("dinosaur",)),
    (r"로봇", ("robot",)),
    (r"사람", ("person",)),
)
EN2KO = {"red cone": "빨간 꼬깔", "yellow cone": "노란 꼬깔", "white cone": "흰 꼬깔", "blue cone": "파란 꼬깔",
         "green cone": "초록 꼬깔", "fire hydrant": "소화전", "chair": "의자", "trash can": "쓰레기통", "dog": "강아지",
         "barrel": "드럼통", "box": "상자", "barrier": "바리케이드", "horse": "말", "dinosaur": "공룡",
         "robot": "로봇", "person": "사람", "red object": "빨간색 물체", "blue object": "파란색 물체",
         "black object": "검은색 물체", "yellow object": "노란색 물체", "white object": "흰색 물체",
         "brown object": "갈색 물체"}


def names_in(req):
    """Referred objects in order of appearance: [(korean word, (english candidates...)), ...]."""
    spans = []
    for rx, en in KO2EN:
        for m in re.finditer(rx, req):
            if not any(m.start() < e and s < m.end() for s, e, _, _ in spans):
                spans.append((m.start(), m.end(), m.group(0), en))
    spans.sort()
    # "파란색 드럼통": the colour only describes the next name — keep the name, drop the colour
    spans = [sp for k, sp in enumerate(spans)
             if not (sp[3][0] in COLOR_PHRASES and k + 1 < len(spans) and spans[k + 1][0] - sp[1] <= 2
                     and spans[k + 1][3][0] not in COLOR_PHRASES)]
    return [(w, en) for _, _, w, en in spans]


class SmolVLAPerceiver:
    def __init__(self, base_ckpt, head_path, names_path, device="cuda"):
        import torch
        from safetensors import safe_open
        from transformers import AutoModelForImageTextToText, AutoTokenizer
        self.torch, self.dev = torch, device
        m = AutoModelForImageTextToText.from_pretrained(MID, dtype=torch.float32, attn_implementation="sdpa")
        m.model.text_model.layers = m.model.text_model.layers[:16]
        sd = {}
        with safe_open(base_ckpt, "pt") as f:
            for k in f.keys():
                if k.startswith("model.vlm_with_expert.vlm."):
                    sd[k[len("model.vlm_with_expert.vlm."):]] = f.get_tensor(k).float()
        m.load_state_dict(sd, strict=False)
        del m.lm_head
        self.vlm = m.to(device).eval()
        tok = AutoTokenizer.from_pretrained(MID)
        self.lang = tok("Target.\n", return_tensors="pt").input_ids.to(device)
        self.names = {k: torch.from_numpy(v).float().to(device) for k, v in np.load(names_path).items()}
        import os
        colors = os.path.join(os.path.dirname(names_path), "colors.npz")
        if os.path.exists(colors):                       # L7 colour phrase vectors (same text encoding)
            self.names.update({k: torch.from_numpy(v).float().to(device) for k, v in np.load(colors).items()})
        self.head = _head_class(torch)(True).to(device).eval()
        self.head.load_state_dict(torch.load(head_path, map_location=device))

    def tokens(self, rgb):
        """rgb: HxWx3 uint8 (640x480) -> (1, 48, 960) frozen image tokens."""
        from PIL import Image
        torch = self.torch
        img = Image.fromarray(rgb)
        w, h = img.size; r = max(w / 512, h / 512)
        pad = Image.new("RGB", (512, 512)); pad.paste(img.resize((int(w / r), int(h / r)), Image.BILINEAR), (0, 0))
        x = (torch.from_numpy(np.array(pad)).permute(2, 0, 1).float() / 255.0 * 2 - 1)[None].to(self.dev)
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
            im = self.vlm.model.connector(self.vlm.model.vision_model(pixel_values=x).last_hidden_state)
            im = im.float(); d = im.shape[-1]; n = im.shape[1]
            le = self.vlm.model.text_model.get_input_embeddings()(self.lang) * math.sqrt(d)
            emb = torch.cat([im * math.sqrt(d), le], 1); L = emb.shape[1]
            hs = self.vlm.model.text_model(inputs_embeds=emb,
                                           attention_mask=torch.zeros(1, 1, L, L, device=self.dev)).last_hidden_state
        return hs[:, :n].float().reshape(1, 8, 8, d)[:, :6].reshape(1, 48, d)

    def find(self, tok, names, width=640):
        """-> {name: (p_not_visible, x_px in the original width)} for names the head has a vector for."""
        torch = self.torch
        names = [n for n in names if n in self.names]
        if not names:
            return {}
        with torch.no_grad():
            logit, x = self.head(tok.expand(len(names), -1, -1), torch.stack([self.names[n] for n in names]))
            pn = torch.softmax(logit, 1)[:, 8]
        return {n: (float(p), float(xx) * width / 640.0) for n, p, xx in zip(names, pn.cpu(), x.cpu())}


def _head_class(torch):
    nn = torch.nn
    XC = torch.tensor([(j % 8 + 0.5) * 80.0 for j in range(48)])
    COL = torch.tensor([j % 8 for j in range(48)])

    class Head(nn.Module):          # identical to server/code/course/l5_train.py Head
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
    return Head
