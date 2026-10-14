"""Build the L1 image set: sim renders (crops) + Fuel model thumbnails, with ground-truth labels."""
import json, sys, os
from PIL import Image
R = '/home/sh/ROS2_project/sant-vla/eval_out/course/clips/'
F = os.path.expanduser('~/.gz/fuel/fuel.gazebosim.org/')
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
items = []
def crop(src, box, name, label, cond):
    im = Image.open(src).convert('RGB'); x0,y0,x1,y1 = box; pad = 40
    im = im.crop((max(0,x0-pad), max(0,y0-pad), min(im.width,x1+pad), min(im.height,y1+pad)))
    p = f'{out}/{name}.png'; im.save(p); items.append(dict(name=name, path=p, label=label, cond=cond))
k = 1.08
for nm, lab, x0, x1 in [('car_red','car',50,290),('car_blue','car',345,560),('car_yellow','car',630,830),
                        ('car_prius','car',880,1090),('box','box',1190,1330),('cone','traffic cone',1490,1590),('box_white','box',1730,1910)]:
    crop(R+'objects_trained_row.png', (int(x0*k),int(60*k),int(x1*k),int(200*k)), 'sim_'+nm, lab, 'sim_render')
for nm, lab, x0, x1 in [('person','person',120,230),('cylinder','cylinder',780,960),('car_green','car',1340,1900)]:
    crop(R+'objects_heldout_row.png', (x0,80,x1,330), 'sim_'+nm, lab, 'sim_render')
for d, lab in [('googleresearch/models/lovable_huggable_cuddly_boutique_teddy_bear_beige','teddy bear'),
               ('googleresearch/models/dino_3','dinosaur'),('googleresearch/models/dino_4','dinosaur'),('googleresearch/models/dino_5','dinosaur'),
               ('googleresearch/models/dog','dog'),('googleresearch/models/breyer_horse_of_the_year_2015','horse'),
               ('googleresearch/models/great_dinos_triceratops_toy','robot'),('googleresearch/models/threshold_bead_cereal_bowl_white','bowl'),
               ('openrobotics/models/fire%20hydrant','fire hydrant'),('openrobotics/models/trashbin','trash can'),
               ('openrobotics/models/visitorchair','chair'),('makerspet/models/red_ball_10in','ball'),
               ('mjcarroll/models/banana for scale','banana'),('gambit/models/orange','orange')]:
    base = F + d; ver = sorted(os.listdir(base))[-1]; th = f'{base}/{ver}/thumbnails'
    for v in ('1', '3'):
        src = next((f'{th}/{v}.{e}' for e in ('jpg','png') if os.path.exists(f'{th}/{v}.{e}')), None)
        if src:
            n = os.path.basename(d).replace('%20','_').replace(' ','_')[:24] + '_v' + v
            p = f'{out}/thumb_{n}.png'; Image.open(src).convert('RGB').save(p)
            items.append(dict(name='thumb_'+n, path=p, label=lab, cond='thumbnail'))
json.dump(items, open(f'{out}/set.json','w'), indent=1)
print(len(items), 'images')
