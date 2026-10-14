"""Figures for 08_내연구_핵심개념.md"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *


def system_map():
    fig, ax = canvas(12, 6.6, "SANT-VLA 실행 구조와 학습 데이터 흐름")
    # run-time loop
    group(ax, 0.3, 2.75, 11.4, 3.1, "주행 (10 Hz 폐루프)", role="neutral")
    sim = box(ax, 0.6, 3.3, 2.0, 1.9, "Gazebo 트랙\n시뮬레이터", role="neutral", sub="카메라 640×480 · 차량 상태")
    br = box(ax, 4.0, 3.1, 2.8, 2.3, "vla_bridge_node", role="state", bold=True,
             sub="관측 수집 · 행동 큐 · splice\n워치독 · action → Twist")
    sv = box(ax, 8.6, 3.1, 2.9, 2.3, "vla_policy_server", role="model", bold=True,
             sub="SmolVLA 추론 (랩서버 GPU)\n행동 청크 30 × [dx, dy, dyaw]")
    arrow(ax, (2.6, 4.6), (4.0, 4.6), label="이미지\nstate")
    arrow(ax, (4.0, 3.7), (2.6, 3.7), label="/cmd_vel\n10 Hz", color=ROLE["action"])
    arrow(ax, (6.8, 4.75), (8.6, 4.75), label="jpeg · state\ntask · seed")
    arrow(ax, (8.6, 3.75), (6.8, 3.75), label="행동 청크", color=ROLE["action"])

    # data pipeline
    group(ax, 0.3, 0.25, 11.4, 2.15, "학습 데이터 만들기", role="neutral")
    steps = [("교사\nroute_oracle · YOLO", "action"), ("episode_recorder\n30 Hz 기록", "state"),
             ("collect_corpus\n반사실 그룹", "state"), ("verify_corpus\nCMI 게이트", "state"),
             ("resample · to_lerobot\n30→10 Hz", "state"), ("train_reasoning.py\n서버 학습", "model")]
    w, gap, x = 1.62, 0.25, 0.55
    prev = None
    for t, r in steps:
        b = box(ax, x, 0.6, w, 1.2, t, role=r, fontsize=9.5)
        if prev:
            arrow(ax, right(prev), left(b))
        prev = b
        x += w + gap
    arrow(ax, top(prev), (9.8, 3.1), label="체크포인트", dashed=True, label_offset=(0.55, -0.1))
    save(fig, "08_system_map")


def prefix_suffix():
    fig, ax = canvas(13.4, 5.2, "SmolVLA 입력 조립 — prefix(관측)와 suffix(행동)")
    # prefix tokens
    y = 3.0
    toks = [("이미지\n64 토큰", "vision", 2.0), ("빈 카메라\n64×2 (mask 0)", "neutral", 2.2),
            ("지시 문장\n≤ 48 토큰", "language", 1.9), ("state\n1 토큰", "state", 1.2)]
    x = 0.4
    pb = []
    for t, r, w in toks:
        pb.append(box(ax, x, y, w, 1.0, t, role=r, dashed=(r == "neutral"), fontsize=10))
        x += w + 0.1
    note(ax, 0.4, 4.35, "prefix — VLM 16층이 읽는다 (관측끼리는 서로 본다)", bold=True, color=INK)
    # suffix
    sx = x + 0.9
    sb = box(ax, sx, y, 2.6, 1.0, "노이즈 행동 30개\n+ 시간 t", role="action", fontsize=10)
    note(ax, sx, 4.35, "suffix — action expert", bold=True, color=INK)
    # expert + output
    vlm = box(ax, 0.4, 1.0, 7.6, 1.0, "VLM 16층  →  층마다 K/V", role="model")
    ex = box(ax, sx, 1.0, 2.6, 1.0, "action expert 16층\n(폭 0.75)", role="action")
    out = box(ax, sx + 3.4, 1.0, 2.0, 1.0, "30 × [dx, dy, dyaw]", role="action", fontsize=10, bold=True)
    for b in pb:
        arrow(ax, bottom(b), (center(b)[0], 2.0))
    arrow(ax, bottom(sb), top(ex))
    arrow(ax, right(vlm), left(ex), color=ROLE["language"])
    note(ax, (right(vlm)[0]+left(ex)[0])/2, 2.35, "짝수층 joint attention\n홀수층 cross-attention", ha="center", fontsize=9)
    arrow(ax, right(ex), left(out), label="10번 반복", label_offset=(0, 0.12))
    note(ax, 0.4, 0.45, "관측은 행동을 볼 수 없다 · 행동은 관측 전체를 본다 · 행동끼리는 앞쪽만 본다(causal)\n"
         "→ 문장이 행동에 닿는 유일한 통로는 action expert 가 prefix 의 K/V 를 보는 어텐션이다.",
         fontsize=10)
    save(fig, "08_prefix_suffix")


if __name__ == "__main__":
    system_map()
    prefix_suffix()
