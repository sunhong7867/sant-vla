"""Figures for 04_로봇학습_모방학습과_강화학습.md"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *
import numpy as np


def mdp_loop():
    fig, ax = canvas(10, 4.6, "MDP — 정책과 환경이 주고받는 고리")
    ag = box(ax, 0.6, 1.4, 3.0, 1.9, "에이전트 (정책 π)", role="action", bold=True,
             sub="관측 o_t 를 보고\n행동 a_t 를 고른다")
    env = box(ax, 6.4, 1.4, 3.0, 1.9, "환경", role="neutral", bold=True,
              sub="전이 P(s' | s, a)\n보상 R(s, a)")
    arrow(ax, (3.6, 2.95), (6.4, 2.95), label="행동 a_t  (조향·속도)", color=ROLE["action"])
    arrow(ax, (6.4, 2.25), (3.6, 2.25), label="다음 관측 o_{t+1}  (카메라·state)",
          color=ROLE["vision"])
    arrow(ax, (6.4, 1.55), (3.6, 1.55), label="보상 r_t  (RL 에서만)", color=ROLE["state"],
          dashed=True)
    note(ax, 0.6, 0.6, "모방학습은 보상 대신 교사의 정답 행동을 받는다. "
         "실제 로봇은 상태 s 를 직접 모르고 관측 o 만 받는다 (POMDP).", fontsize=10)
    save(fig, "04_mdp_loop")


def open_vs_closed():
    fig, ax = canvas(12, 4.6, "개루프 평가 vs 폐루프 평가")
    group(ax, 0.3, 0.5, 5.4, 3.5, "개루프 — 기록된 장면으로 채점", role="neutral")
    d = box(ax, 0.6, 2.2, 1.9, 1.1, "기록 데이터\n(교사 주행)", role="state", fontsize=10)
    m = box(ax, 3.4, 2.2, 1.9, 1.1, "모델", role="action", fontsize=10)
    s = box(ax, 3.4, 0.8, 1.9, 0.9, "정답과 비교\n→ 오차", role="neutral", fontsize=10)
    arrow(ax, right(d), left(m), label="장면")
    arrow(ax, bottom(m), top(s))
    note(ax, 0.6, 1.2, "모델 출력이\n다음 입력을\n바꾸지 않는다", fontsize=9.5)

    group(ax, 6.3, 0.5, 5.4, 3.5, "폐루프 — 모델이 직접 운전", role="neutral")
    m2 = box(ax, 6.7, 2.2, 1.9, 1.1, "모델", role="action", fontsize=10)
    w = box(ax, 9.4, 2.2, 1.9, 1.1, "시뮬 / 실차", role="neutral", fontsize=10)
    arrow(ax, (8.6, 3.0), (9.4, 3.0), label="행동", color=ROLE["action"])
    arrow(ax, (9.4, 2.5), (8.6, 2.5), label="새 장면", color=ROLE["vision"], label_offset=(0, -0.4))
    note(ax, 6.7, 1.2, "작은 오차가 다음 장면을 바꾸고 쌓인다\n→ 개루프에서 좋아도 폐루프에서 무너질 수 있다",
         fontsize=9.5)
    save(fig, "04_open_vs_closed")


def compounding():
    fig = plt.figure(figsize=(12, 4.4))
    a1 = fig.add_axes([0.05, 0.13, 0.43, 0.7])
    a2 = fig.add_axes([0.58, 0.13, 0.39, 0.7])
    fig.text(0.05, 0.95, "오차 복리 — 한 번 벗어나면 본 적 없는 장면이 이어진다 (예시)",
             fontsize=14, fontweight="bold", color=INK, va="top")
    # left: band + student path
    x = np.linspace(0, 10, 200)
    a1.fill_between(x, -0.5, 0.5, color=tint(ROLE["state"], 0.8), lw=0)
    a1.plot(x, 0 * x, color=ROLE["state"], lw=2, label="교사 경로")
    stu = np.where(x < 3, 0.03 * x, 0.09 + 0.02 * np.clip(x - 3, 0, None) ** 2.2)
    a1.plot(x, stu, color=ROLE["action"], lw=2, label="학생 경로")
    a1.axvline(3, color=MUTED, lw=1, ls=(0, (4, 3)))
    a1.text(3.1, 1.9, "첫 실수", color=INK2, fontsize=9.5)
    a1.text(0.2, -0.85, "교사 데이터가 있는 띠", color=INK2, fontsize=9.5)
    a1.text(6.2, 2.4, "데이터 밖 → 오차 증가", color=INK2, fontsize=9.5)
    a1.set_ylim(-1.1, 3.2)
    a1.set_xlabel("주행 거리")
    a1.set_ylabel("교사 경로에서 벗어난 정도")
    a1.set_xticks([]); a1.set_yticks([])
    a1.legend(loc="upper left")
    # right: error growth
    T = np.arange(0, 51)
    eps = 0.02
    a2.plot(T, eps * T, color=SERIES[0], label="DAgger: O(εT)")
    a2.plot(T, eps * T ** 2 / 2, color=SERIES[1], label="행동복제 최악: O(εT²)")
    a2.text(50, eps * 50 ** 2 / 2, "  εT²/2", color=INK2, fontsize=9.5, va="center")
    a2.text(50, eps * 50, "  εT", color=INK2, fontsize=9.5, va="center")
    a2.set_xlim(0, 58)
    a2.set_xlabel("스텝 수 T")
    a2.set_ylabel("누적 비용 상한")
    a2.set_title("ε = 0.02 로 그린 예시", fontsize=11, fontweight="normal", color=INK2)
    a2.legend(loc="upper left")
    save(fig, "04_compounding_error")


def dagger():
    fig, ax = canvas(11, 4.4, "DAgger — 학생이 간 곳에서 교사에게 정답을 묻는다")
    b1 = box(ax, 0.5, 1.6, 2.1, 1.2, "데이터 D\n(교사 시연)", role="state")
    b2 = box(ax, 3.3, 1.6, 2.1, 1.2, "학습\nπ_i ← D", role="model")
    b3 = box(ax, 6.1, 1.6, 2.1, 1.2, "학생 π_i 로\n주행", role="action")
    b4 = box(ax, 8.6, 1.6, 2.1, 1.2, "방문한 상태에\n교사 정답 붙이기", role="state", fontsize=10)
    arrow(ax, right(b1), left(b2))
    arrow(ax, right(b2), left(b3))
    arrow(ax, right(b3), left(b4))
    arrow(ax, bottom(b4), bottom(b1), rad=-0.25, label="D ← D ∪ 새 데이터, 반복",
          label_offset=(0, -1.25))
    note(ax, 0.5, 3.5, "결과: 학습 분포 = 학생의 실제 방문 분포 → 누적 오차 O(εT²) 에서 O(εT) 로", fontsize=10)
    save(fig, "04_dagger_loop")


def chunk_timeline():
    fig = plt.figure(figsize=(12, 4.6))
    a1 = fig.add_axes([0.06, 0.14, 0.58, 0.68])
    a2 = fig.add_axes([0.72, 0.14, 0.26, 0.68])
    fig.text(0.06, 0.96, "행동 청크 실행 — 30개 받아 21개 쓰고 다시 묻는다",
             fontsize=14, fontweight="bold", color=INK, va="top")
    # queue length: 30 at t=0, pop 1 per 0.1 s; refill when < 9 (after 21 pops = 2.1 s)
    t, q = [], []
    tt, qq = 0.0, 30
    for _ in range(3):
        for k in range(22):
            t.append(tt + 0.1 * k); q.append(30 - k)
        tt += 2.15
    t = np.array(t); q = np.array(q)
    a1.step(t, q, where="post", color=SERIES[0], lw=2)
    a1.axhline(9, color=SERIES[1], lw=1.5, ls=(0, (4, 3)))
    a1.text(3.0, 6.6, "refill 기준: 9개 미만이면 재추론 (30 × 0.3)", color=INK2, fontsize=9.5, ha="left")
    for k in range(1, 3):
        x0 = 2.15 * k
        a1.annotate("새 청크 도착\n→ 30개", xy=(x0, 30), xytext=(x0 - 0.75, 33.5),
                    fontsize=9, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED))
    a1.axvspan(0, 2.1, color=tint(SERIES[0], 0.9), lw=0)
    a1.text(1.05, 3, "약 2.1 초 커밋\n(새 화면 반영 안 함)", ha="center", fontsize=9.5, color=INK2)
    a1.set_ylim(0, 37)
    a1.set_xlim(0, 6.6)
    a1.set_xlabel("시간 (초) — 10 Hz 로 1개씩 꺼냄")
    a1.set_ylabel("큐에 남은 행동 수")
    # crossfade weights
    i = np.arange(5)
    w = (i + 1) / 6
    a2.bar(i - 0.18, 1 - w, width=0.34, color=SERIES[2], label="기존 큐")
    a2.bar(i + 0.18, w, width=0.34, color=SERIES[0], label="새 청크")
    a2.set_xticks(i, [f"{k+1}" for k in i])
    a2.set_xlabel("새 청크의 앞 5스텝")
    a2.set_ylabel("섞는 비율")
    a2.set_ylim(0, 1.15)
    a2.set_title("splice: w = (i+1)/6", fontsize=11, fontweight="normal", color=INK2)
    a2.legend(loc="upper left", ncol=2, fontsize=9)
    save(fig, "04_chunk_timeline")


def _road(ax, x0, x1, y0):
    # two lanes, width 1 each
    ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, 2, fc=tint(C["gray"], 0.9), ec="none", zorder=0))
    ax.plot([x0, x1], [y0, y0], color=MUTED, lw=1.5)
    ax.plot([x0, x1], [y0 + 2, y0 + 2], color=MUTED, lw=1.5)
    ax.plot([x0, x1], [y0 + 1, y0 + 1], color=MUTED, lw=1, ls=(0, (6, 5)))


def _swerve(x0, xs, x1, y, up=1.0):
    x = np.linspace(x0, x1, 200)
    yy = y + up * (1 / (1 + np.exp(-(x - (xs - 0.6)) * 5)) - 1 / (1 + np.exp(-(x - (xs + 0.9)) * 5)))
    return x, yy


def shortcut():
    fig, ax = canvas(12.6, 7.0, "지름길 학습 — 장애물 대신 '자리'를 외운다")
    spot = 3.2
    rows = [3.55, 0.95]            # road bottoms (each road: 2 lanes x 1.0)

    def panel(off, title, top_obst, top_txt, bot_swerve, bot_txt, bot_col):
        note(ax, off, 6.15, title, bold=True, color=INK)
        for y in rows:
            _road(ax, off, off + 5.7, y)
            ax.plot([off + spot, off + spot], [y - 0.1, y + 2.1], color=MUTED, lw=1, ls=(0, (2, 3)))
        # top: demo with obstacle in lower lane
        y = rows[0]
        if top_obst:
            box(ax, off + spot - 0.22, y + 0.28, 0.44, 0.44, "", role="bad", radius=0.05)
        x, yy = _swerve(off + 0.1, off + spot, off + 5.6, y + 0.5, up=1.0)
        ax.plot(x, yy, color=ROLE["state"], lw=2.2)
        note(ax, off + 0.1, y + 2.3, top_txt, fontsize=9.5)
        # bottom: no obstacle
        y = rows[1]
        if bot_swerve:
            x, yy = _swerve(off + 0.1, off + spot, off + 5.6, y + 0.5, up=1.0)
        else:
            x = np.linspace(off + 0.1, off + 5.6, 50); yy = 0 * x + y + 0.5
        ax.plot(x, yy, color=bot_col, lw=2.2)
        note(ax, off + 0.1, y + 2.3, bot_txt, fontsize=9.5, color=bot_col)

    panel(0.4, "① 장애물이 늘 같은 자리인 시연만 있을 때", True, "학습 시연: 장애물을 보고 차선 변경",
          True, "시험: 빈 도로인데도 같은 자리에서 꺾음  (r44 빈 차선 10/20)", ROLE["bad"])
    panel(6.6, "② 같은 자리에 '직진' 짝 시연을 넣으면", True, "짝 1: 장애물 있음 → 차선 변경",
          False, "짝 2: 같은 자리, 장애물 없음 → 직진  (r43 빈 차선 0/100)", ROLE["good"])
    note(ax, 0.4, 0.45, "점선 = 트랙의 같은 자리.  자리만으로는 행동을 맞힐 수 없게 만들어야 모델이 장애물을 본다.",
         fontsize=10, color=INK)
    save(fig, "04_shortcut_learning")


def rl_loop():
    fig, ax = canvas(11, 4.4, "강화학습 — 정답 대신 보상으로 배운다")
    pol = box(ax, 0.5, 1.6, 2.4, 1.3, "정책 π_θ", role="action", bold=True, sub="행동 선택")
    env = box(ax, 4.3, 1.6, 2.4, 1.3, "환경", role="neutral", bold=True, sub="시뮬 / 실제")
    val = box(ax, 8.1, 1.6, 2.4, 1.3, "가치 추정 V(s)", role="model", bold=True, sub="평균보다 나은가?")
    arrow(ax, (2.9, 2.55), (4.3, 2.55), label="행동 a", color=ROLE["action"])
    arrow(ax, (6.7, 2.55), (8.1, 2.55), label="보상 r, 다음 상태 s'", color=ROLE["state"])
    arrow(ax, bottom(val), bottom(pol), rad=-0.3, label="이점 A = Q − V 로 정책 갱신 (PPO 등)",
          color=ROLE["model"], label_offset=(0, -1.35))
    note(ax, 0.5, 3.65, "목표: 할인된 보상의 합 J(π) = E[Σ γ^t r_t] 최대화", fontsize=10)
    save(fig, "04_rl_loop")


def sim2real():
    fig, ax = canvas(12, 5.6, "Sim2Real — 시뮬과 현실의 차이와 대응")
    s = box(ax, 0.4, 2.0, 2.4, 2.0, "시뮬레이터", role="vision", bold=True, sub="정책을 학습한 곳")
    r = box(ax, 9.2, 2.0, 2.4, 2.0, "실제 트랙·차량", role="state", bold=True, sub="정책을 쓰는 곳")
    gaps = [("시각", "질감·조명·카메라"), ("동역학", "마찰·지연·응답"),
            ("센서", "노이즈·장착 위치"), ("기하", "차 크기·차선 폭")]
    note(ax, 3.6, 4.6, "현실 격차 (reality gap)", bold=True, color=INK)
    y = 4.0
    for g, d in gaps:
        box(ax, 3.6, y - 0.5, 1.7, 0.5, g, role="bad", fontsize=10)
        note(ax, 5.45, y - 0.25, d, fontsize=9.5)
        y -= 0.62
    arrow(ax, right(s), (3.6, 3.0))
    arrow(ax, (7.6, 3.0), left(r))
    note(ax, 0.4, 1.15, "대응: 도메인 랜덤화 · 시스템 식별 · 실데이터 파인튜닝 · 중간 표현 · 사전학습 백본", fontsize=10, color=INK)
    note(ax, 0.4, 0.65, "우리: 시뮬 차량만 0.85배 축소(폭 1.75 → 1.49 m), 카메라 위치는 유지 → curv_boost 1.1 → 0.95 재보정",
         fontsize=10)
    save(fig, "04_sim2real")


if __name__ == "__main__":
    mdp_loop(); open_vs_closed(); compounding(); dagger(); chunk_timeline()
    shortcut(); rl_loop(); sim2real()
