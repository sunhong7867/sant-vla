#!/usr/bin/env python3
"""Measure a packed pilot: phase lag, jerk, det_std, centre offset, touch.
Usage: measure_teacher_pilot.py <packed_dir>"""
import glob, json, math, os, statistics as st, sys
REPO="/home/sh/ROS2_project/sant-vla"
TP=json.load(open(REPO+'/src/sant_vla_pkg/config/track_paths.json'))
LANES={k:[tuple(p) for p in TP[k]] for k in ('lane1','lane2')}
W=3; KTHR=0.06
def pc(xs,ys,i):
    a,b,c=(xs[i-W],ys[i-W]),(xs[i],ys[i]),(xs[i+W],ys[i+W])
    v1=(b[0]-a[0],b[1]-a[1]); v2=(c[0]-b[0],c[1]-b[1]); l1=math.hypot(*v1); l2=math.hypot(*v2)
    if l1<1e-6 or l2<1e-6: return 0.0
    ang=math.atan2(v2[1],v2[0])-math.atan2(v1[1],v1[0]); ang=(ang+math.pi)%(2*math.pi)-math.pi
    return ang/((l1+l2)/2)
def analyze(pdir):
    phases=[]; jerks=[]; dets=[]; offs=[]; touch=0; ntot=0
    for d in sorted(glob.glob(pdir+'/*__ep_*/')):
        rj=d+'resampled_10hz.jsonl'; mj=d+'meta.json'
        if not (os.path.exists(rj) and os.path.exists(mj)): continue
        meta=json.load(open(mj)); lane=(meta.get('intent_slots') or {}).get('lane') or 'lane2'
        rows=[json.loads(l) for l in open(rj)]
        if len(rows)<2*W+10: continue
        xs=[r['x'] for r in rows]; ys=[r['y'] for r in rows]; cs=[]; kp=[]
        for i in range(W,len(rows)-W):
            a=rows[i].get('action')
            if not a: continue
            ds=math.hypot(a[0],a[1]); p=pc(xs,ys,i)
            o=min(math.hypot(px-xs[i],py-ys[i]) for px,py in LANES[lane]); offs.append(o); ntot+=1
            if o>0.68: touch+=1
            if ds>1e-3 and abs(p)>KTHR: cs.append(a[2]/ds); kp.append(p)
        if len(cs)<12: continue
        jerks.append(st.mean(abs(cs[i]-cs[i-1]) for i in range(1,len(cs))))
        bins={}
        for a,p in zip(cs,kp): bins.setdefault(round(p,2),[]).append(a)
        bs=[st.pstdev(v) for v in bins.values() if len(v)>=4]
        if bs: dets.append(st.mean(bs))
        m=st.mean(cs); dd=[v-m for v in cs]; mp=st.mean(kp); dp=[v-mp for v in kp]
        best,blag=-9,0
        for lag in range(-4,5):
            num=cnt=0
            for i in range(len(dd)):
                j=i-lag
                if 0<=j<len(dp): num+=dd[i]*dp[j]; cnt+=1
            c=num/cnt if cnt else 0
            if c>best: best,blag=c,lag
        phases.append(blag)
    off=sorted(offs)
    return dict(eps=len(phases), phase=round(st.mean(phases),2), jerk=round(st.mean(jerks),4),
               det=round(st.mean(dets),4), med_off=round(off[len(off)//2],3),
               p95_off=round(off[int(len(off)*.95)],3), max_off=round(off[-1],3), touch=round(touch/ntot,3))
print(analyze(sys.argv[1]))
