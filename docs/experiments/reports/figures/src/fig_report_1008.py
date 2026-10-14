"""Figures for research_report_20261003_20261008.md (style shared with docs/study)."""
import os, sys
MY_DIR = os.path.dirname(os.path.abspath(__file__))  # style also exports HERE
sys.path.insert(0, os.path.join(MY_DIR, "../../../../study/figures/src"))
import style
from style import *
OUT_DIR = os.path.dirname(MY_DIR)  # docs/experiments/reports/figures


def save(fig, name, dpi=200):
    for a in fig.axes:
        for t in a.texts:
            t.set_clip_on(False)
    path = os.path.join(OUT_DIR, name + ".png")
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("wrote", path)


def probe_chart():
    """Language counterfactual probe across runs: share moved toward the instructed side."""
    # (label, toward, n, ratio pred/demo or None, group)
    rows = [
        ("r50 · 이름 문장 20k", 21, 42, None, "name"),
        ("r51 · 이름 + 초반 가중 30k", 18, 42, None, "name"),
        ("rp3 · 이름 + 합성 반사실 라벨", 22, 42, 0.03, "name"),
        ("b1 · 이름 문장 10k", 22, 42, 0.01, "name"),
        ("b0 · 상수 문장 'Drive.' (대조군)", 23, 42, 0.03, "name"),
        ("r52 · 방향 단어 30k", 34, 42, 0.09, "dir"),
        ("r54 · 방향 단어 + 좌우 반전", 30, 42, 0.10, "dir"),
        ("r26 · 베이스, 섹터 미학습 (대조군)", 49, 55, 0.82, "sec"),
        ("s1 · 섹터 문장 10k", 49, 55, 0.86, "sec"),
        ("s0 · 상수 문장 'Drive.' (대조군)", 50, 55, 1.02, "sec"),
    ]
    col = {"name": SERIES[0], "dir": SERIES[1], "sec": SERIES[2]}
    fig = plt.figure(figsize=(12.5, 6.6))
    ax = fig.add_axes([0.33, 0.13, 0.40, 0.70])
    ax2 = fig.add_axes([0.76, 0.13, 0.20, 0.70], sharey=ax)
    fig.text(0.02, 0.95, "언어 반사실 프로브 — 같은 화면·상태·노이즈에서 문장만 바꿨을 때",
             fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.02, 0.905, "왼쪽: 예측 경로가 지시한 쪽으로 기운 비율 (우연 50 %)   오른쪽: 경로 차이 크기 / 시연 차이",
             fontsize=10, color=INK2, va="top")
    ys = list(range(len(rows)))[::-1]
    for y, (lab, k, n, r, g) in zip(ys, rows):
        dashed = "대조군" in lab
        ax.barh(y, k / n * 100, height=0.62, color=tint(col[g], 0.55) if dashed else col[g],
                edgecolor=col[g], linewidth=1.4, hatch="//" if dashed else None)
        ax.text(k / n * 100 + 1.2, y, f"{k}/{n}", va="center", fontsize=9.5, color=INK)
        if r is not None:
            ax2.barh(y, r, height=0.62, color=tint(col[g], 0.55) if dashed else col[g],
                     edgecolor=col[g], linewidth=1.4, hatch="//" if dashed else None)
            ax2.text(r + 0.03, y, f"{r:.2f}", va="center", fontsize=9.5, color=INK)
        else:
            ax2.text(0.03, y, "보정 전 값이라 생략", va="center", fontsize=8.5, color=MUTED)
    ax.axvline(50, color=INK2, lw=1.2, ls=(0, (4, 3)))
    ax.text(49, len(rows) - 0.45, "우연 50 %", ha="right", fontsize=9, color=INK2)
    ax.axvline(64, color=C["red"], lw=1.0, ls=(0, (2, 2)))
    ax.text(65, len(rows) - 0.45, "유의 하한 ≈64 %\n(27/42 · 35/55)", ha="left", fontsize=8.5, color=INK2)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=10)
    ax.set_xlim(0, 105)
    ax.set_xlabel("지시한 쪽으로 이동 (%)")
    ax.grid(axis="y", visible=False)
    ax2.tick_params(axis="y", left=False, labelleft=False); ax2.set_xlim(0, 1.25)
    ax.set_ylim(-0.6, len(rows) - 0.1)
    ax2.set_xlabel("예측 횡 차이 / 시연")
    ax2.grid(axis="y", visible=False)
    ax2.spines["left"].set_visible(False)
    # group legend
    from matplotlib.patches import Patch
    hs = [Patch(fc=col["name"], ec=col["name"], label="이름 코퍼스 g1 (물체 이름)"),
          Patch(fc=col["dir"], ec=col["dir"], label="이름 코퍼스 → 방향 단어 재라벨"),
          Patch(fc=col["sec"], ec=col["sec"], label="섹터 코퍼스 (왼쪽·정면·오른쪽)"),
          Patch(fc=SURFACE, ec=INK2, hatch="//", label="대조군 (문장 학습 없음)")]
    fig.legend(handles=hs, loc="lower left", ncol=4, fontsize=9.5, bbox_to_anchor=(0.02, 0.0))
    save(fig, "probe_across_runs")


def cmi_chart():
    rows = [("g1 이름 코퍼스\n(rp·b 학습 데이터)", 0.785, 3.81, SERIES[0]),
            ("gv2b 이름 코퍼스 v2", 0.909, 3.81, SERIES[0]),
            ("sec1 섹터 파일럿\n(35 ep)", 1.203, 1.58, SERIES[2]),
            ("sec 섹터 본 수집\n(292 ep)", 0.907, 1.58, SERIES[2])]
    fig = plt.figure(figsize=(10, 4.6))
    ax = fig.add_axes([0.25, 0.16, 0.70, 0.66])
    fig.text(0.02, 0.95, "시연 데이터의 언어 의존도 — CMI 디바이어스 중앙값 / 축 상한",
             fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.02, 0.88, "같은 관측 안에서 문장이 교사 행동의 불확실성을 얼마나 줄이나. 데이터 성질이며 정책 성능이 아니다.",
             fontsize=10, color=INK2, va="top")
    ys = list(range(len(rows)))[::-1]
    for y, (lab, v, cap, c) in zip(ys, rows):
        ax.barh(y, v / cap * 100, height=0.6, color=c)
        ax.text(v / cap * 100 + 1, y, f"{v / cap * 100:.0f} %  ({v:.3f} b / {cap} b)", va="center", fontsize=9.5, color=INK)
    ax.set_yticks(ys); ax.set_yticklabels([r[0] for r in rows], fontsize=10)
    ax.set_xlim(0, 100); ax.set_xlabel("상한 대비 (%)")
    ax.grid(axis="y", visible=False)
    save(fig, "cmi_ceiling")


def flow():
    fig, ax = canvas(14, 8.7, "10-03 ~ 10-08 흐름 — 시도, 결과, 해석 (위에서 아래로)")
    W, H = 4.2, 1.25
    col1, col2, col3 = 0.3, 4.9, 9.5
    steps = [
        ("이름 문장으로 학습\nr50 (g1, 30k)", "T1 47 % (우연 29 %)\n가장 가까운 물체로 감", "이름을 못 붙인다", "bad"),
        ("초반 프레임 가중 r51\n방향 단어 재라벨 r52", "r51 방향 우연\nr52 오프라인 34/42", "폐루프는 전부 같은 물체", "bad"),
        ("왼쪽 쏠림 추적", "postprocessor 통계 복사 버그\n(r26 부터)", "교정 후 단어 효과 0.09 배", "bad"),
        ("합성 반사실 라벨 rp3\n좌우 반전 r54", "rp3 22/42 · r54 30/42\n정렬 검증 불일치 0", "데이터 문제인가?", "bad"),
        ("CMI 로 데이터 검사\n(축 이름 버그 수정)", "g1 0.743 b · gv2b 0.965 b\nGATE PASS", "데이터에는 정보가 있다", "good"),
        ("상수 문장 기준선\nb1 vs b0", "22/42 vs 23/42", "언어 효과 반증 → 과제 재설계", "bad"),
        ("섹터 3분류 + Qwen 분업\ns1 vs s0 vs r26", "오프라인 49 · 50 · 49 / 55", "베이스에 이미 있던 반응\n폐루프 8/30 (우연) · 오른쪽 쏠림", "bad"),
    ]
    y = 8.7 - 0.95
    ax.text(col1 + W / 2, y + 0.15, "한 것 (왜)", ha="center", fontsize=11, fontweight="bold", color=INK)
    ax.text(col2 + W / 2, y + 0.15, "결과", ha="center", fontsize=11, fontweight="bold", color=INK)
    ax.text(col3 + W / 2, y + 0.15, "해석 → 다음", ha="center", fontsize=11, fontweight="bold", color=INK)
    prev = None
    for i, (a, b, c, r) in enumerate(steps):
        yy = y - 0.35 - (i + 1) * (H - 0.08) + 0.0 - i * 0.0
        yy = 8.7 - 1.3 - i * 1.08 - H + 0.25
        b1 = box(ax, col1, yy, W, H - 0.25, a, role="model", fontsize=10)
        b2 = box(ax, col2, yy, W, H - 0.25, b, role="neutral", fill=False, fontsize=10)
        b3 = box(ax, col3, yy, W, H - 0.25, c, role=r, fontsize=10)
        arrow(ax, right(b1), left(b2)); arrow(ax, right(b2), left(b3))
        prev = (0, yy)
    save(fig, "flow_1003_1008")


if __name__ == "__main__":
    probe_chart(); cmi_chart(); flow()
