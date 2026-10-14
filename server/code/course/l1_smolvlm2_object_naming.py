"""L1: does the SmolVLM2-500M backbone (all 32 layers, its own LM head) name these objects?
Q1 open naming; Q2 yes/no on the true label; Q3 yes/no on a distractor (yes-bias control)."""
import json, sys, random, torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForImageTextToText
MID = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
items = json.load(open(sys.argv[1])); outp = sys.argv[2]
proc = AutoProcessor.from_pretrained(MID)
model = AutoModelForImageTextToText.from_pretrained(MID, torch_dtype=torch.bfloat16).to('cuda').eval()
labels = sorted({x['label'] for x in items}); rnd = random.Random(0)
def ask(img, q, n=20):
    msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": q}]}]
    prompt = proc.apply_chat_template(msgs, add_generation_prompt=True)
    inp = proc(text=prompt, images=[img], return_tensors='pt').to('cuda', torch.bfloat16)
    with torch.no_grad():
        o = model.generate(**inp, max_new_tokens=n, do_sample=False)
    return proc.batch_decode(o[:, inp['input_ids'].shape[1]:], skip_special_tokens=True)[0].strip()
res = []
for x in items:
    img = Image.open(x['path']).convert('RGB')
    distract = rnd.choice([l for l in labels if l != x['label']])
    r = dict(x, distractor=distract,
             name=ask(img, 'What is the main object in this image? Answer in a few words.'),
             yes_true=ask(img, f'Is there a {x["label"]} in this image? Answer yes or no.', 3),
             yes_distr=ask(img, f'Is there a {distract} in this image? Answer yes or no.', 3))
    res.append(r); print(f"{x['name']:34s} [{x['label']}] -> {r['name']!r} | {x['label']}:{r['yes_true']} | {distract}:{r['yes_distr']}", flush=True)
json.dump(res, open(outp, 'w'), indent=1, ensure_ascii=False)
