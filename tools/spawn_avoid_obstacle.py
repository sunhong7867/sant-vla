#!/usr/bin/env python3
"""Spawn (or remove) a stationary blocker car on a ring lane for the
avoidance demo.

The car is placed ON a lane waypoint from track_paths.json, oriented along
the travel direction, so best_cap.pt sees it as lane1_car / lane2_car — the
classes the chat GUI's avoidance supervisor keys on.

Usage (sim must be running):
    python3 tools/spawn_avoid_obstacle.py --lane lane2 --frac 0.25
    python3 tools/spawn_avoid_obstacle.py --lane lane2 --x -9.2 --y -20.3
    python3 tools/spawn_avoid_obstacle.py --remove

--frac is the position along the lane path (0..1). With --x/--y the nearest
waypoint is used instead. Run from a shell with the workspace sourced (needs
ros_gz_sim and simulation_pkg importable).
"""
import argparse
import json
import math
from pathlib import Path

TRACK_PATHS = Path(__file__).resolve().parent.parent / \
    "src/sant_vla_pkg/config/track_paths.json"
# chat_gui's avoidance supervisor reads this registry to resolve WHICH lane
# a VLM-sighted obstacle occupies (matches its avoid_obstacle_file default).
REGISTRY = Path(__file__).resolve().parent.parent / \
    "eval_out/demo/obstacles.json"
ENTITY = "avoid_obstacle_car"


def update_registry(entity, model=None, pose=None, lane=None, remove=False):
    entries = []
    if REGISTRY.is_file():
        try:
            entries = json.loads(REGISTRY.read_text())
        except json.JSONDecodeError:
            entries = []
    entries = [e for e in entries if e.get("entity") != entity]
    if not remove:
        entries.append({"entity": entity, "model": model,
                        "x": pose[0], "y": pose[1], "lane": lane})
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(entries, indent=1))


def pick_pose(lane, frac, x, y):
    pts = json.loads(TRACK_PATHS.read_text())[lane]
    if x is not None and y is not None:
        i = min(range(len(pts)),
                key=lambda k: (pts[k][0] - x) ** 2 + (pts[k][1] - y) ** 2)
    else:
        i = max(0, min(len(pts) - 1, int(frac * len(pts))))
    px, py = pts[i]
    nx, ny = pts[(i + 1) % len(pts)]
    yaw = math.atan2(ny - py, nx - px)
    return px, py, 0.0, 0.0, 0.0, yaw


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lane", choices=["lane1", "lane2"], default="lane2")
    ap.add_argument("--frac", type=float, default=0.25,
                    help="position along the lane path, 0..1 (default 0.25)")
    ap.add_argument("--x", type=float, help="snap to waypoint nearest this x")
    ap.add_argument("--y", type=float, help="snap to waypoint nearest this y")
    ap.add_argument("--model", default="hatchback_yellow",
                    help="simulation_pkg model dir name (default "
                         "hatchback_yellow; also e.g. hatchback_red, "
                         "prius_hybrid_ob1)")
    ap.add_argument("--entity", default=ENTITY)
    ap.add_argument("--remove", action="store_true",
                    help="remove the spawned blocker instead")
    args = ap.parse_args()

    from simulation_pkg import basic  # needs the sourced workspace

    if args.remove:
        basic.remove_model(args.entity)
        update_registry(args.entity, remove=True)
        print(f"removed {args.entity}")
        return

    pose = pick_pose(args.lane, args.frac, args.x, args.y)
    print(f"spawning {args.model} as {args.entity} on {args.lane} at "
          f"x={pose[0]:.2f} y={pose[1]:.2f} yaw={pose[5]:.2f}")
    basic.load_model(args.entity, args.model, pose, skip_if_exists=False)
    update_registry(args.entity, args.model, pose, args.lane)


if __name__ == "__main__":
    main()
