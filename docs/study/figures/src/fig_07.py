"""Figures for 07_Physical_AI.md"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *


def components():
    fig, ax = canvas(13, 7.6, "Physical AI 시스템의 구성요소")
    group(ax, 0.3, 3.4, 12.4, 3.6, "실행 고리 (실시간 폐루프)", role="neutral")
    y, h, w = 3.75, 1.35, 2.5
    s = box(ax, 0.7, y, w, h, "센서·인지", role="vision", bold=True, sub="카메라 · 라이다 · IMU")
    m = box(ax, 3.75, y, w, h, "상황 이해", role="model", bold=True, sub="월드 모델 · 상태 추정")
    p = box(ax, 6.8, y, w, h, "정책 (행동 결정)", role="action", bold=True, sub="VLA · 플래너")
    a = box(ax, 9.85, y, w, h, "제어·구동", role="action", bold=True, sub="모터 · 조향")
    for b1, b2 in [(s, m), (m, p), (p, a)]:
        arrow(ax, right(b1), left(b2))
    # physical world return path, over the top
    arrow(ax, top(a), top(s), rad=0.22, color=ROLE["neutral"])
    note(ax, 6.5, 6.35, "물리 세계 — 행동이 환경을 바꾸고, 바뀐 환경이 다시 센서로 들어온다",
         ha="center", fontsize=9.5)

    group(ax, 0.3, 0.3, 6.0, 2.6, "학습 쪽", role="neutral")
    box(ax, 0.6, 0.65, 1.75, 1.6, "시뮬레이터\n디지털 트윈", role="vision", fontsize=10)
    box(ax, 2.5, 0.65, 1.75, 1.6, "데이터\n플라이휠", role="state", fontsize=10)
    box(ax, 4.4, 0.65, 1.75, 1.6, "학습 인프라\nGPU 클러스터", role="model", fontsize=10)
    group(ax, 6.7, 0.3, 6.0, 2.6, "배포 쪽", role="neutral")
    box(ax, 7.0, 0.65, 1.75, 1.6, "엣지 컴퓨터\nJetson Orin·Thor", role="model", fontsize=10)
    box(ax, 8.9, 0.65, 1.75, 1.6, "경량화\n양자화·프루닝", role="model", fontsize=10)
    box(ax, 10.8, 0.65, 1.75, 1.6, "실시간 미들웨어\nROS 2", role="neutral", fontsize=10)
    arrow(ax, (5.3, 2.9), (7.5, 3.75), dashed=True)
    note(ax, 5.2, 3.15, "학습된 정책", fontsize=9.5, ha="right")
    arrow(ax, (9.7, 2.9), (8.7, 3.75), dashed=True)
    note(ax, 9.55, 3.15, "탑재·실행", fontsize=9.5)
    save(fig, "07_components")


def flywheel():
    fig, ax = canvas(9.0, 7.2, "데이터 플라이휠")
    cx, cy, r = 4.5, 3.4, 2.45
    steps = [("배포", "model"), ("실패·드문 상황\n수집", "state"), ("선별·라벨링", "state"),
             ("재학습", "model"), ("검증", "neutral")]
    pts = []
    for i, (t, role) in enumerate(steps):
        ang = math.pi / 2 - i * 2 * math.pi / len(steps)
        x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
        box(ax, x - 0.85, y - 0.4, 1.7, 0.8, t, role=role, fontsize=10)
        pts.append((x, y))
    for i in range(len(pts)):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
        p0 = (x0 + 0.37 * (x1 - x0), y0 + 0.37 * (y1 - y0))
        p1 = (x0 + 0.63 * (x1 - x0), y0 + 0.63 * (y1 - y0))
        arrow(ax, p0, p1, rad=-0.2, lw=1.8)
    note(ax, cx, cy, "돌수록 데이터가\n실제 분포에\n가까워진다", ha="center", fontsize=10, color=INK)
    note(ax, 0.3, 0.3, "우리 연구의 DAgger 사이클이 작은 규모의 플라이휠이다.", fontsize=9.5)
    save(fig, "07_data_flywheel")


def strategies():
    fig = plt.figure(figsize=(10.5, 6.2))
    ax = fig.add_axes([0.09, 0.12, 0.86, 0.72])
    fig.text(0.09, 0.95, "데이터 확보 전략 — 규모와 현실성의 맞교환 (개념 배치, 정량 아님)",
             fontsize=14, fontweight="bold", color=INK, va="top")
    items = [  # (name, scale, realism, colour, ha, dx, dy)
        ("텔레오퍼레이션", 1.2, 4.6, SERIES[0], "left", 0.18, 0),
        ("시뮬 + 전문가 정책\n(우리 route_oracle·YOLO 선생)", 4.0, 2.4, SERIES[1], "left", 0.18, 0),
        ("강화학습 (시뮬)", 3.6, 1.6, SERIES[2], "left", 0.18, 0),
        ("사람 영상", 4.6, 1.0, SERIES[3], "right", -0.18, 0),
        ("합성 데이터 / 월드 모델", 4.1, 3.2, SERIES[4], "right", -0.18, 0),
        ("배포 데이터 (플라이휠)", 2.8, 4.3, SERIES[5], "left", 0.18, 0),
    ]
    for n, x, y, c, ha, dx, dy in items:
        ax.scatter([x], [y], s=150, color=SERIES[0], edgecolor=SURFACE, linewidth=2, zorder=3)  # identity is the label, not colour
        ax.text(x + dx, y + dy, n, ha=ha, va="center", fontsize=10, color=INK)
    ax.set_xlim(0.5, 5.3)
    ax.set_ylim(0.4, 5.2)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_xlabel("확보 규모  (적음 → 많음, 자동화 쉬움)")
    ax.set_ylabel("실제 로봇과의 일치  (낮음 → 높음)")
    ax.text(0.6, 0.55, "실제로는 섞어 쓴다: 대규모 사전학습 → 소량 텔레옵 파인튜닝 → 시뮬·합성으로 드문 상황 보강",
            fontsize=9.5, color=INK2)
    save(fig, "07_data_strategies")


def ai_stages():
    """NVIDIA CES 2025 framing: Perception → Generative → Agentic → Physical AI."""
    fig, ax = canvas(14, 6.7, "AI 발전 4단계 — 앞 단계가 다음 단계의 부품이 된다 (NVIDIA 의 설명 틀)")
    stages = [
        ("Perception AI", "인지 AI", "보고 듣고 알아본다", "이미지 분류 · 음성 인식\n추천 · 의료 영상",
         "GPU + 딥러닝\n+ 라벨 데이터", "vision"),
        ("Generative AI", "생성형 AI", "글 · 그림 · 코드를 만든다", "ChatGPT\n이미지 생성 모델",
         "트랜스포머\n+ 인터넷 규모 사전학습", "language"),
        ("Agentic AI", "에이전틱 AI", "계획을 세우고\n도구를 써서 일을 처리한다", "코딩 에이전트\n고객 응대 에이전트",
         "LLM 추론\n+ 도구 사용", "model"),
        ("Physical AI", "물리 AI", "물리 세계를 이해하고\n몸으로 움직인다", "자율주행 · 로봇\n휴머노이드",
         "앞 단계 전부 + 시뮬레이션\n· 월드 모델 · 엣지 컴퓨팅", "action"),
    ]
    w, gap, x0 = 3.05, 0.42, 0.3
    heads = []
    for i, (en, ko, does, ex, base, role) in enumerate(stages):
        x = x0 + i * (w + gap)
        h = box(ax, x, 4.55, w, 1.05, en, role=role, bold=True, fontsize=13, sub=ko)
        heads.append(h)
        box(ax, x, 3.35, w, 1.0, does, role=role, fill=False, fontsize=10.5)
        note(ax, x + 0.1, 2.95, "대표 예", bold=True, color=INK)
        note(ax, x + 0.1, 2.5, ex, fontsize=10)
        note(ax, x + 0.1, 2.0, "가능하게 한 것", bold=True, color=INK)
        note(ax, x + 0.1, 1.55, base, fontsize=10)
        if i:
            arrow(ax, right(heads[i - 1]), left(h), lw=2.0)
    # time hints
    for i, t in enumerate(["2012년 무렵~", "2022년 무렵~", "", ""]):
        if t:
            note(ax, x0 + i * (w + gap) + w - 0.1, 5.8, t, ha="right", fontsize=9.5)
    # our research mapping band
    group(ax, 0.3, 0.1, 13.6, 0.95, "우리 연구에 대응시키면", role="neutral")
    maps = ["YOLO 차선 인식", "flow matching 행동 생성 · 해설", "Qwen 이 자유 문장을 정본 지시로",
            "그것으로 실제 차를 움직임"]
    for i, m in enumerate(maps):
        note(ax, x0 + i * (w + gap) + w / 2, 0.4, m, ha="center", fontsize=10.5, color=INK)
    save(fig, "07_ai_stages")


if __name__ == "__main__":
    components(); flywheel(); strategies(); ai_stages()
