"""Go-to-object layouts and instructions (2026-10-03, weekend plan P1).

One layout = an ego start pose anywhere on the track plane (lanes, infield,
parking lot) plus 2-4 objects inside the camera's field of view. The task is
"go to the <named object>" — lanes ignored ("direct") or along the lane
("lane", only when the target sits on the ego's lane ahead).

Shared by the collector (scripts/collect_corpus.py --goto-groups), the
closed-loop evaluation (tools/eval/goto_trial.py) and the backbone probe.

Shortcut guards (lessons of the avoidance work, docs/experiments/avoidance):
  * the target is the nearest object only ~1/3 of the time, and left / centre /
    right are balanced — position alone must not predict the target;
  * a layout yields TWO variants with different targets from the same start,
    so the instruction is the only difference between them;
  * the straight path to the target is kept clear of the other objects.
"""
import math

# Camera: 62.2 deg horizontal FOV (prius_hybrid model.sdf). Objects are kept
# a few degrees inside it so they never sit half outside the frame.
CAM_HALF_FOV = math.radians(62.2) / 2.0
FOV_MARGIN = math.radians(6.0)
# Drivable plane (track texture 58 x 44 m, lanes span x +-18.4, y +-24.6).
X_LIM, Y_LIM = 17.5, 23.5
EGO_HALF_LEN = 2.3          # TEACHER constant: prius origin -> nose, kept at the
                            # historical value so new collections stay comparable
                            # with every corpus packed before 2026-10-12.
# MEASURED 2026-10-12 from prius_hybrid/model.sdf: the frontmost COLLISION
# element (chassis/front_bumper, pose y -1.7, box y 0.408) reaches y = -1.904.
# EGO_HALF_LEN is 0.396 m beyond that - it sits near the visual mesh nose
# (y = -2.24 per the SDF comment), not the contact surface. Evaluation metrics
# that ask "how much clearance is left" must use this one, or they understate
# the gap by 0.396 m and report a clean stop as an overshoot.
EGO_COLLIDE_LEN = 1.904
# bumper -> object surface at the stop. 0.9 for the 10-03 corpus (r50-r54);
# 1.2 from the 2026-10-05 v2 corpus ("stop a fixed distance in front").
STOP_GAP = 1.2
YAW_OFFSET = -math.pi / 2.0  # gz model yaw = heading - YAW_OFFSET (same constant as collect_corpus.py / route_oracle)

# model -> (noun phrase, footprint radius m, split). Nouns are what the
# instruction and the reasoning label call the object.
FLEET = {
    "go_cone_red": ("red cone", 0.45, "train"),
    "go_cone_yellow": ("yellow cone", 0.45, "train"),
    "go_cone_blue": ("blue cone", 0.45, "train"),
    "go_cone_white": ("white cone", 0.45, "train"),
    "ob_box": ("box", 0.8, "train"),
    "ob_barrel": ("barrel", 0.5, "train"),
    "ob_barrier": ("barrier", 0.9, "train"),
    "hatchback_red": ("red car", 2.2, "train"),
    "hatchback_blue": ("blue car", 2.2, "train"),
    "go_dog": ("dog", 0.55, "train"),
    "go_horse": ("horse", 0.7, "train"),
    "go_hydrant": ("fire hydrant", 0.3, "train"),
    "go_chair": ("chair", 0.4, "train"),
    "go_trashbin": ("trash can", 0.45, "train"),
    # held out of training: colour, object category, existing holdouts
    "go_cone_green": ("green cone", 0.45, "heldout"),
    # Dinosaurs enlarged 1.5 -> 2.4 m (r 0.75 -> 1.2) on 2026-10-08 for the
    # lecture GUI; T3b/T4 results before that date used the 1.5 m models.
    # Google Scanned Objects toys (tools/make_goto_models.py). Fuel names lie:
    # dino_3 = T-rex (go_dino_3), dino_4 = styracosaurus (go_dino_trex),
    # dino_5 = triceratops (go_dino_5), and "Great_Dinos_Triceratops_Toy" is
    # actually the green Android robot figure (go_triceratops) — checked on the
    # Fuel thumbnails 2026-10-03; it serves as the held-out character toy.
    "go_dino_3": ("dinosaur", 1.2, "heldout"),
    "go_dino_trex": ("dinosaur", 1.2, "heldout"),
    "go_dino_5": ("dinosaur", 1.2, "heldout"),
    "go_triceratops": ("robot", 0.6, "heldout"),
    "ob_person": ("person", 0.4, "heldout"),
    "hatchback_green": ("green car", 2.2, "heldout"),
    # primitive shapes (tools/make_goto_models.py shapes), point-goal practice P4 (2026-10-12)
    "go_shape_ball": ("ball", 0.55, "heldout"),
    "go_shape_cube": ("cube", 0.5, "heldout"),
    "go_shape_prism": ("triangular prism", 0.5, "heldout"),
}

# Descriptions for the semantic tier (T4): only used at evaluation time.
DESCRIPTIONS = {
    "dinosaur": ["an extinct animal", "a prehistoric creature"],
    "person": ["a human"],
    "green cone": ["the cone that is the colour of grass"],
    "robot": ["the Android mascot"],
}

TEMPLATES = {
    "direct": [
        "Go to the {noun}.",
        "Drive straight to the {noun}.",
        "Head over to the {noun} and stop in front of it.",
        "Take me to the {noun}.",
        "Go directly to the {noun}, ignore the lanes.",
        "Drive up to the {noun}.",
        "Move to the {noun}.",
        "Stop in front of the {noun}.",
        "{noun_ko_ro} 가.",
        "{noun_ko} 앞으로 곧장 가줘.",
        "{noun_ko}까지 가서 멈춰.",
    ],
    "lane": [
        "Follow the lane to the {noun}.",
        "Stay in your lane and drive to the {noun}.",
        "Drive along the lane until the {noun}.",
        "Keep to the lane and stop at the {noun}.",
        "차선을 따라 {noun_ko}까지 가줘.",
    ],
}
# Three-way direction practice (2026-10-07). The sentence names the SECTOR,
# never the object — the target is whatever stands in that sector, so the
# policy maps a word to one of three behaviours instead of grounding a noun on
# a specific object (which measured at chance: b1 22/42 vs constant-sentence
# baseline b0 23/42). "ahead" needs its own phrasings, so these are per sector
# rather than one template with a substituted direction word.
SECTOR_TEMPLATES = {
    "left": [
        "Go to the object on the left.",
        "Drive to the one on your left and stop in front of it.",
        "Head to the left object and stop in front of it.",
        "Take the left one.",
        "Stop in front of the object on the left.",
        "왼쪽 물체로 가줘.",
        "왼쪽에 있는 것 앞으로 가서 멈춰.",
        "왼쪽으로 가서 그 앞에 멈춰.",
    ],
    "ahead": [
        "Go to the object straight ahead.",
        "Drive to the one in front of you and stop in front of it.",
        "Head straight to the object ahead.",
        "Take the one directly ahead.",
        "Stop in front of the object straight ahead.",
        "정면 물체로 가줘.",
        "앞에 있는 것 앞으로 가서 멈춰.",
        "곧장 가서 그 앞에 멈춰.",
    ],
    "right": [
        "Go to the object on the right.",
        "Drive to the one on your right and stop in front of it.",
        "Head to the right object and stop in front of it.",
        "Take the right one.",
        "Stop in front of the object on the right.",
        "오른쪽 물체로 가줘.",
        "오른쪽에 있는 것 앞으로 가서 멈춰.",
        "오른쪽으로 가서 그 앞에 멈춰.",
    ],
}


def render_sector(sector, rng, template=None):
    """(text, template_index) for the three-way direction practice."""
    pool = SECTOR_TEMPLATES[sector]
    k = rng.randrange(len(pool)) if template is None else template
    return pool[k], k


NOUN_KO = {
    "red cone": "빨간 꼬깔", "yellow cone": "노란 꼬깔", "blue cone": "파란 꼬깔",
    "white cone": "흰 꼬깔", "green cone": "초록 꼬깔", "box": "상자",
    "barrel": "드럼통", "barrier": "바리케이드", "red car": "빨간 차",
    "blue car": "파란 차", "green car": "초록 차", "dog": "강아지", "horse": "말",
    "fire hydrant": "소화전", "chair": "의자", "trash can": "쓰레기통",
    "dinosaur": "공룡", "person": "사람", "robot": "로봇",
}


def noun(model):
    return FLEET[model][0]


def render(mode, model, rng, template=None):
    """(text, template_index). Korean templates use the Korean noun."""
    pool = TEMPLATES[mode]
    k = rng.randrange(len(pool)) if template is None else template
    n = noun(model)
    ko = NOUN_KO.get(n, n)
    return pool[k].format(noun=n, noun_ko=ko, noun_ko_ro=ko + _ro(ko)), k


def _ro(word):
    """Korean directional particle: 로 after a vowel or ㄹ final, else 으로."""
    c = ord(word[-1]) - 0xAC00
    if not 0 <= c < 11172:
        return "로"
    final = c % 28
    return "로" if final in (0, 8) else "으로"


def _in_plane(x, y, pad=0.0):
    return abs(x) <= X_LIM - pad and abs(y) <= Y_LIM - pad


def standoff(model):
    """Centre-to-centre stop distance for the teacher."""
    return EGO_HALF_LEN + STOP_GAP + FLEET[model][1]


def _seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L = vx * vx + vy * vy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def arc_points(ex, ey, heading, tx, ty, step=0.25):
    """The teacher's path: pure pursuit at a fixed point is a circular arc
    tangent to the start heading through the target (route_oracle point mode).
    Returns points from the start to the target."""
    dx, dy = tx - ex, ty - ey
    c, s = math.cos(heading), math.sin(heading)
    lx, ly = dx * c + dy * s, -dx * s + dy * c
    d2 = lx * lx + ly * ly
    k = 2.0 * ly / max(d2, 1e-6)
    length = math.sqrt(d2) if abs(k) < 1e-4 else abs(2.0 / k * math.asin(min(1.0, abs(k) * math.sqrt(d2) / 2.0)))
    if lx < 0:      # target behind: arc longer than half a circle
        length = abs(2 * math.pi / k) - length if abs(k) > 1e-4 else length
    pts, n = [], max(2, int(length / step))
    for i in range(n + 1):
        u = length * i / n
        if abs(k) < 1e-4:
            px, py = u, 0.0
        else:
            px, py = math.sin(k * u) / k, (1 - math.cos(k * u)) / k
        pts.append((ex + px * c - py * s, ey + px * s + py * c))
    return pts


def sample_layout(rng, paths, models, n_obj=(3, 4), dist=(5.0, 12.5),
                  lane_start_p=0.5, tries=400, min_sep_deg=0.0, all_usable=False,
                  pool_offset=None):
    """Return a layout dict or None.

    models: candidate fleet for this split (distinct nouns are enforced).
    The ego starts on a lane (heading along travel) with prob lane_start_p,
    otherwise anywhere on the plane with a random heading.
    """
    lanes = ("lane1", "lane2")
    for _ in range(tries):
        lane = None
        if rng.random() < lane_start_p:
            lane = rng.choice(lanes)
            pts = paths[lane]
            i = rng.randrange(len(pts))
            ex, ey = pts[i]
            nx, ny = pts[(i + 1) % len(pts)]
            heading = math.atan2(ny - ey, nx - ex) + math.radians(rng.uniform(-5, 5))
            lane_index = i
        else:
            ex, ey = rng.uniform(-X_LIM + 3, X_LIM - 3), rng.uniform(-Y_LIM + 3, Y_LIM - 3)
            heading = rng.uniform(-math.pi, math.pi)
            lane_index = None
        k = rng.randint(*n_obj)
        # pool_offset (2026-10-05): rotate the candidate order instead of
        # shuffling. A shuffled pool let goal frequency drift to 10x in the
        # gv2pilot run — large models lose the placement retry more often, so
        # 'red car' landed 1 episode and 'blue car' none. Rotating by the group
        # index gives every model its turn.
        pool = list(models)
        if pool_offset is None:
            rng.shuffle(pool)
        else:
            o = pool_offset % len(pool)
            pool = pool[o:] + pool[:o]
        chosen, nouns = [], set()
        for m in pool:
            if noun(m) not in nouns:
                chosen.append(m)
                nouns.add(noun(m))
            if len(chosen) == k:
                break
        if len(chosen) < 2:
            return None
        objs = []
        ok = True
        for m in chosen:
            placed = False
            for _ in range(40):
                d = rng.uniform(*dist)
                b = rng.uniform(-(CAM_HALF_FOV - FOV_MARGIN), CAM_HALF_FOV - FOV_MARGIN)
                ox = ex + d * math.cos(heading + b)
                oy = ey + d * math.sin(heading + b)
                r = FLEET[m][1]
                if not _in_plane(ox, oy, r + 0.5):
                    continue
                if any(math.hypot(ox - o["x"], oy - o["y"]) < r + o["r"] + 1.8 for o in objs):
                    continue
                # v2 (2026-10-05): distinct image tokens — 512 px / 8 tokens
                # across 62.2 deg = 7.8 deg per token
                if any(abs(b - o["bearing"]) < math.radians(min_sep_deg) for o in objs):
                    continue
                objs.append({"model": m, "entity": f"v9_{m}", "noun": noun(m),
                             "x": ox, "y": oy, "yaw": rng.uniform(-math.pi, math.pi),
                             "r": r, "dist": d, "bearing": b, "present": True,
                             "in_our_lane": False})
                placed = True
                break
            if not placed:
                ok = False
                break
        if not ok:
            continue
        # a target is usable when the straight path to its stop point is clear
        usable = []
        for t, o in enumerate(objs):
            sd = standoff(o["model"])
            if o["dist"] < sd + 2.5:      # room to start, steer and brake
                continue
            ux, uy = (o["x"] - ex) / o["dist"], (o["y"] - ey) / o["dist"]
            sx, sy = o["x"] - ux * sd, o["y"] - uy * sd
            if not _in_plane(sx, sy, 1.0):
                continue
            # clearance along the ARC the teacher drives (a chord check let a
            # cone 1.99 m from the swung-out path through, pilot 2026-10-03);
            # 1.0 m ego half-width + 0.9 m margin
            arc = arc_points(ex, ey, heading, sx, sy)
            clear = all(min(math.hypot(q["x"] - px, q["y"] - py) for px, py in arc) > q["r"] + 1.9
                        for j, q in enumerate(objs) if j != t)
            if clear:
                usable.append(t)
        if len(usable) < 2 or (all_usable and len(usable) < len(objs)):
            continue
        return {"ego": {"x": ex, "y": ey, "heading": heading,
                        "model_yaw": heading - YAW_OFFSET,
                        "lane": lane, "lane_index": lane_index},
                "objects": objs, "usable": usable}
    return None


# Three-way direction practice (2026-10-07). + bearing = left.
SECTOR_CENTRES = {"left": 20.0, "ahead": 0.0, "right": -20.0}
SECTOR_BAND = 3.0                 # +-3 deg band; max |20|+3 = 23 < 25.1 usable
SECTOR_NEAR = (7.0, 8.0)
SECTOR_FAR = (11.5, 12.5)
SECTOR_MAX_R = 0.9                # excludes the hatchbacks (r 2.2)


def sample_sector_layout(rng, paths, models, lane_start_p=0.5, tries=600,
                         band=SECTOR_BAND, near=SECTOR_NEAR, far=SECTOR_FAR,
                         max_radius=SECTOR_MAX_R):
    """Layout for the three-way direction practice: one object per sector.

    Exactly one object in each camera sector (left / ahead / right) inside a
    narrow bearing band, so every demonstration within a direction class
    follows nearly the same arc. r52 relabelled the sentence to direction
    words but kept object-exact targets, so "left" mixed a 14 deg 6 m object
    with a 25 deg 10 m one — the word named a class while the required
    trajectory stayed per-object (offline 34/42 but closed-loop 4/20 on easy
    pairs). Narrow bands collapse that within-class spread, which is the
    condition under which discrete mode words demonstrably do work here (lane
    words: 27x counterfactual separation).

    The near and far distance bands are permuted between "ahead" and the two
    sides on every draw, so distance does not predict the class. Models with
    radius > max_radius are excluded: at these bearings a 2.2 m car cannot
    hold the r + r + 1.8 m clearance from anything else (checked 2026-10-07,
    20k draws: 0 violations with r <= 0.9, worst slack +0.75 m).

    Returns the usual layout dict plus ``sectors``: {name: object index}.
    """
    lanes = ("lane1", "lane2")
    pool0 = [m for m in models if FLEET[m][1] <= max_radius]
    if len(pool0) < 3:
        return None
    for _ in range(tries):
        lane = None
        if rng.random() < lane_start_p:
            lane = rng.choice(lanes)
            pts = paths[lane]
            i = rng.randrange(len(pts))
            ex, ey = pts[i]
            nx, ny = pts[(i + 1) % len(pts)]
            heading = math.atan2(ny - ey, nx - ex) + math.radians(rng.uniform(-5, 5))
            lane_index = i
        else:
            ex, ey = rng.uniform(-X_LIM + 3, X_LIM - 3), rng.uniform(-Y_LIM + 3, Y_LIM - 3)
            heading = rng.uniform(-math.pi, math.pi)
            lane_index = None

        pool = list(pool0)
        rng.shuffle(pool)
        chosen, nouns = [], set()
        for m in pool:
            if noun(m) not in nouns:
                chosen.append(m)
                nouns.add(noun(m))
            if len(chosen) == 3:
                break
        if len(chosen) < 3:
            return None

        placed = _place_in_sectors(rng, ex, ey, heading, chosen, band, near, far)
        if placed is None:
            continue
        objs, sectors, usable, ahead_far = placed
        return {"ego": {"x": ex, "y": ey, "heading": heading,
                        "model_yaw": heading - YAW_OFFSET,
                        "lane": lane, "lane_index": lane_index},
                "objects": objs, "usable": usable, "sectors": sectors,
                "ahead_far": ahead_far}
    return None


def _place_in_sectors(rng, ex, ey, heading, chosen, band=SECTOR_BAND,
                      near=SECTOR_NEAR, far=SECTOR_FAR):
    """Put chosen[0..2] into the left / ahead / right sectors as seen from
    the ego (ex, ey, heading). Returns (objs, sectors, usable, ahead_far), or
    None when a draw fails the clearance or drivability checks."""
    ahead_far = rng.random() < 0.5          # which band "ahead" gets
    objs, sectors, ok = [], {}, True
    for m, nm in zip(chosen, SECTOR_CENTRES):
        lo, hi = far if (nm == "ahead") == ahead_far else near
        r = FLEET[m][1]
        placed = False
        for _ in range(40):
            d = rng.uniform(lo, hi)
            b = math.radians(rng.uniform(SECTOR_CENTRES[nm] - band,
                                         SECTOR_CENTRES[nm] + band))
            ox = ex + d * math.cos(heading + b)
            oy = ey + d * math.sin(heading + b)
            if not _in_plane(ox, oy, r + 0.5):
                continue
            if any(math.hypot(ox - o["x"], oy - o["y"]) < r + o["r"] + 1.8 for o in objs):
                continue
            sectors[nm] = len(objs)
            objs.append({"model": m, "entity": f"v9_{m}", "noun": noun(m),
                         "x": ox, "y": oy, "yaw": rng.uniform(-math.pi, math.pi),
                         "r": r, "dist": d, "bearing": b, "present": True,
                         "in_our_lane": False, "sector": nm})
            placed = True
            break
        if not placed:
            ok = False
            break
    if not ok:
        return None

    # every sector must be drivable — the group issues all three commands
    usable = []
    for t, o in enumerate(objs):
        sd = standoff(o["model"])
        if o["dist"] < sd + 2.5:
            continue
        ux, uy = (o["x"] - ex) / o["dist"], (o["y"] - ey) / o["dist"]
        sx, sy = o["x"] - ux * sd, o["y"] - uy * sd
        if not _in_plane(sx, sy, 1.0):
            continue
        arc = arc_points(ex, ey, heading, sx, sy)
        clear = all(min(math.hypot(q["x"] - px, q["y"] - py) for px, py in arc) > q["r"] + 1.9
                    for j, q in enumerate(objs) if j != t)
        if clear:
            usable.append(t)
    if len(usable) < len(objs):
        return None
    return objs, sectors, usable, ahead_far


def sector_layout_at(rng, ex, ey, heading, chosen, tries=300):
    """Sector layout in front of a GIVEN ego pose (the lecture GUI's "spawn three
    objects ahead" button, 2026-10-08). `chosen` = three models; they are dealt
    to left / ahead / right at random and placed with the same bands and checks
    as sample_sector_layout, so the scene matches the s1 training distribution.
    Returns the layout dict, or None when the ego stands too close to the plane
    edge (or facing it) for all three to be reachable."""
    for _ in range(tries):
        order = list(chosen)
        rng.shuffle(order)
        placed = _place_in_sectors(rng, ex, ey, heading, order)
        if placed is None:
            continue
        objs, sectors, usable, ahead_far = placed
        return {"ego": {"x": ex, "y": ey, "heading": heading,
                        "model_yaw": heading - YAW_OFFSET, "lane": None, "lane_index": None},
                "objects": objs, "usable": usable, "sectors": sectors, "ahead_far": ahead_far}
    return None


def pick_targets(rng, layout, n=2):
    """Two different usable targets; nearest-object share kept near 1/3."""
    objs, usable = layout["objects"], list(layout["usable"])
    nearest = min(range(len(objs)), key=lambda j: objs[j]["dist"])
    rng.shuffle(usable)
    if nearest in usable and rng.random() > 1.0 / 3.0 and len(usable) > n:
        usable.remove(nearest)
        usable.append(nearest)        # demote, only used if needed
    return usable[:n]


def lane_target_ok(paths, layout, t, min_gap=6.0, max_gap=30.0):
    """Lane variant only when the ego starts on a lane and the target sits on
    that lane ahead (within 1.2 m of the centreline). Returns arc gap or None."""
    ego = layout["ego"]
    if ego["lane"] is None:
        return None
    pts = paths[ego["lane"]]
    o = layout["objects"][t]
    j = min(range(len(pts)), key=lambda k: (pts[k][0] - o["x"]) ** 2 + (pts[k][1] - o["y"]) ** 2)
    if math.hypot(pts[j][0] - o["x"], pts[j][1] - o["y"]) > 1.2:
        return None
    n = len(pts)
    gap = ((j - ego["lane_index"]) % n) * 0.35
    return gap if min_gap <= gap <= max_gap else None


def sample_lane_layout(rng, paths, models, n_distract=(1, 3), gap=(8.0, 20.0), tries=400):
    """Layout for the "follow the lane" vs "go straight" pair.

    The ego starts on a lane heading along it; the target sits ON that lane
    gap metres ahead (index arc) and inside the camera view; distractors are
    placed in view but off the lane path up to the target. Returns a layout
    with ``lane_target`` (object index) and ``lane_gap_m``, or None.
    """
    for _ in range(tries):
        lane = rng.choice(("lane1", "lane2"))
        pts = paths[lane]
        n = len(pts)
        i = rng.randrange(n)
        ex, ey = pts[i]
        nx, ny = pts[(i + 1) % n]
        heading = math.atan2(ny - ey, nx - ex)
        g = rng.uniform(*gap)
        j = (i + int(g / 0.35)) % n
        tx, ty = pts[j]
        d = math.hypot(tx - ex, ty - ey)
        b = math.atan2(ty - ey, tx - ex) - heading
        b = (b + math.pi) % (2 * math.pi) - math.pi
        if abs(b) > CAM_HALF_FOV - FOV_MARGIN or d < 5.0:
            continue
        pool = list(models)
        rng.shuffle(pool)
        tm = pool[0]
        objs = [{"model": tm, "entity": f"v9_{tm}", "noun": noun(tm), "x": tx, "y": ty,
                 "yaw": rng.uniform(-math.pi, math.pi), "r": FLEET[tm][1], "dist": d,
                 "bearing": b, "present": True, "in_our_lane": False}]
        lane_path = [pts[(i + k) % n] for k in range(0, int(g / 0.35) + 1)]
        nouns = {noun(tm)}
        want = rng.randint(*n_distract)
        for m in pool[1:]:
            if len(objs) - 1 >= want:
                break
            if noun(m) in nouns:
                continue
            for _ in range(40):
                dd = rng.uniform(4.0, 12.0)
                bb = rng.uniform(-(CAM_HALF_FOV - FOV_MARGIN), CAM_HALF_FOV - FOV_MARGIN)
                ox, oy = ex + dd * math.cos(heading + bb), ey + dd * math.sin(heading + bb)
                r = FLEET[m][1]
                if not _in_plane(ox, oy, r + 0.5):
                    continue
                if any(math.hypot(ox - o["x"], oy - o["y"]) < r + o["r"] + 1.8 for o in objs):
                    continue
                # v2 (2026-10-05): distinct image tokens — 512 px / 8 tokens
                # across 62.2 deg = 7.8 deg per token
                if any(abs(b - o["bearing"]) < math.radians(min_sep_deg) for o in objs):
                    continue
                if min(math.hypot(ox - px, oy - py) for px, py in lane_path) < r + 2.0:
                    continue
                if _seg_dist(ox, oy, ex, ey, tx, ty) < r + 1.6:
                    continue
                objs.append({"model": m, "entity": f"v9_{m}", "noun": noun(m), "x": ox,
                             "y": oy, "yaw": rng.uniform(-math.pi, math.pi), "r": r,
                             "dist": dd, "bearing": bb, "present": True,
                             "in_our_lane": False})
                nouns.add(noun(m))
                break
        if len(objs) < 2:
            continue
        return {"ego": {"x": ex, "y": ey, "heading": heading,
                        "model_yaw": heading - YAW_OFFSET, "lane": lane, "lane_index": i},
                "objects": objs, "usable": [0], "lane_target": 0, "lane_gap_m": g}
    return None
