"""Figures for model_compression/양자화_프루닝_개념정리.md"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *
import numpy as np

rng = np.random.default_rng(7)


def int8_grid():
    """Number line with a coarse grid (3-bit for visibility) and rounding error."""
    fig, ax = plt.subplots(figsize=(11, 3.4))
    s = 1.0 / 3  # 3-bit symmetric: q in -3..3 → visible ticks
    grid = np.arange(-3, 4) * s
    ax.hlines(0, -1.15, 1.15, color=MUTED, lw=1)
    for g in grid:
        ax.vlines(g, -0.12, 0.12, color=INK2, lw=1.5)
        ax.text(g, -0.3, f"q={round(g / s):+d}".replace("+0", "0"), ha="center", fontsize=9.5, color=INK2)
    xs = np.array([-0.83, -0.2, 0.5, 0.94])
    for i, x in enumerate(xs):
        q = np.round(x / s) * s
        ax.scatter([x], [0.45], s=60, color=SERIES[0], zorder=3)
        ax.annotate("", xy=(q, 0.14), xytext=(x, 0.4), arrowprops=dict(arrowstyle="-|>", color=SERIES[1], lw=1.6))
        ax.text(x, 0.58, f"x={x:+.2f}", ha="center", fontsize=9.5, color=INK)
        ax.text((x + q) / 2 + 0.03, 0.27, f"오차 {x - q:+.2f}", fontsize=8.5, color=INK2)
    ax.set_xlim(-1.2, 1.2); ax.set_ylim(-0.45, 0.75)
    ax.axis("off")
    ax.set_title("양자화 = 가장 가까운 눈금으로 반올림 (예시: 눈금 7개, 실제 INT8 은 256개)\n"
                 "눈금 간격이 scale s · 반올림 오차는 최대 s/2", loc="left")
    save(fig, "mc_quant_grid")


def outlier():
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.6), sharey=True)
    w = rng.normal(0, 0.25, 60)
    for ax, with_out in zip(axes, [False, True]):
        vals = w.copy()
        if with_out:
            vals = np.append(vals, 6.0)
        m = np.abs(vals).max()
        s = m / 7  # 4-bit-ish grid for visibility
        q = np.round(vals / s) * s
        ax.scatter(vals, np.full_like(vals, 0.6), s=14, color=SERIES[0], label="원래 값", lw=0)
        ax.scatter(q, np.full_like(q, 0.2), s=14, color=SERIES[1], label="양자화 후", lw=0)
        for g in np.arange(-7, 8) * s:
            ax.axvline(g, color=GRID, lw=0.8, zorder=0)
        ax.set_yticks([0.2, 0.6], ["양자화 후", "원래 값"])
        ax.set_ylim(0, 0.85); ax.grid(False)
        ax.set_xlabel("값")
        n_unique = len(np.unique(np.round(q[:60], 6)))
        ax.set_title(("outlier 없음" if not with_out else "outlier 하나 (6.0)") +
                     f" — 보통 값 60개가 눈금 {n_unique}개에 담김", fontsize=11.5)
    fig.suptitle("outlier 의 영향 (예시) — 범위를 큰 값에 맞추면 나머지 값이 몇 눈금에 뭉개진다",
                 x=0.01, ha="left", fontsize=13, fontweight="bold")
    fig.tight_layout()
    save(fig, "mc_outlier")


def sparsity():
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    n = 8
    W = rng.normal(0, 1, (n, n))
    # unstructured: drop 50% smallest |w|
    thr = np.median(np.abs(W))
    m1 = np.abs(W) >= thr
    # structured: drop 4 whole rows (channels) with smallest norm
    keep_rows = np.argsort(-np.linalg.norm(W, axis=1))[:4]
    m2 = np.zeros_like(m1); m2[keep_rows] = True
    # 2:4 : in every group of 4 along a row keep 2 largest
    m3 = np.zeros_like(m1)
    for i in range(n):
        for g in range(0, n, 4):
            idx = np.argsort(-np.abs(W[i, g:g + 4]))[:2] + g
            m3[i, idx] = True
    titles = ["비구조적 — 하나하나 지움\n일반 GPU 에서 빨라지지 않음",
              "구조적 — 채널(행) 통째로\n행렬이 실제로 작아짐",
              "2:4 반구조적 — 4개 중 2개\nAmpere 이후 GPU 가속"]
    for ax, m, t in zip(axes, [m1, m2, m3], titles):
        img = np.where(m, 1.0, 0.0)
        ax.imshow(img, cmap=matplotlib.colors.ListedColormap([tint(INK2, 0.88), SERIES[0]]), vmin=0, vmax=1)
        ax.set_xticks(np.arange(-0.5, n, 1), minor=True); ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
        ax.grid(which="minor", color=SURFACE, lw=2); ax.grid(which="major", visible=False)
        ax.tick_params(which="both", length=0); ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        if m is m3:
            for g in (3.5,):
                ax.axvline(g, color=ROLE["action"], lw=2)
        ax.set_title(t, fontsize=11.5)
    fig.suptitle("프루닝 세 갈래 (예시, 8×8 가중치 · 파랑 = 남김, 회색 = 지움, 모두 50% · 주황 선 = 4개 묶음 경계)",
                 x=0.01, ha="left", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "mc_sparsity")


def memory_bits():
    fig, ax = plt.subplots(figsize=(8, 3.8))
    names = ["FP32", "BF16 / FP16", "INT8", "INT4"]
    gb = [1.8, 0.9, 0.45, 0.23]
    bars = ax.barh(names[::-1], gb[::-1], color=SERIES[0], height=0.55)
    for b, v in zip(bars, gb[::-1]):
        ax.text(v + 0.03, b.get_y() + b.get_height() / 2, f"약 {v} GB", va="center", fontsize=10.5, color=INK)
    ax.set_xlim(0, 2.2)
    ax.set_xlabel("가중치 메모리 (GB)")
    ax.grid(axis="y", visible=False)
    ax.set_title("SmolVLA 약 450M 파라미터 — 비트 수별 가중치 메모리\n(우리 체크포인트는 BF16, model.safetensors 907 MB)")
    save(fig, "mc_memory_bits")


def smolvla_parts():
    fig, ax = canvas(12.6, 4.4, "SmolVLA 부품별로 본 양자화 관점")
    cam = box(ax, 0.3, 2.40, 1.9, 0.8, "카메라 이미지", role="vision", fontsize=10)
    txt = box(ax, 0.3, 1.40, 1.9, 0.8, "지시 문장", role="language", fontsize=10)
    st = box(ax, 0.3, 0.40, 1.9, 0.8, "state [v, ω, δ]", role="state", fontsize=10)
    enc = box(ax, 2.8, 2.40, 2.2, 0.8, "SigLIP 비전 인코더", role="vision", fontsize=10)
    emb = box(ax, 2.8, 1.40, 2.2, 0.8, "토큰 임베딩", role="language", fontsize=10)
    sp = box(ax, 2.8, 0.40, 2.2, 0.8, "state projection", role="state", fontsize=10)
    lm = box(ax, 5.8, 1.10, 2.4, 1.5, "SmolVLM2\n언어모델 16층", role="model", bold=True, fontsize=10.5)
    ex = box(ax, 9.0, 1.10, 2.0, 1.5, "action expert\n× 10스텝", role="action", bold=True, fontsize=10.5)
    out = box(ax, 11.4, 1.45, 1.0, 0.8, "행동\n30×3", role="action", fontsize=9.5)
    for a, b in [(cam, enc), (txt, emb), (st, sp)]:
        arrow(ax, right(a), left(b))
    for b in (enc, emb, sp):
        arrow(ax, right(b), left(lm))
    arrow(ax, right(lm), left(ex), label="K/V")
    arrow(ax, right(ex), left(out))
    note(ax, 2.8, 3.55, "한 번 처리 · 파라미터 큼\n→ INT8 에 비교적 강함", fontsize=9.5)
    note(ax, 5.8, 2.95, "파라미터 대부분\n→ 가중치 양자화 효과 최대", fontsize=9.5)
    note(ax, 9.0, 2.95, "10번 반복 · 연속값 출력\n→ 오차 누적·민감, BF16 유지 후보", fontsize=9.5)
    save(fig, "mc_smolvla_parts")


if __name__ == "__main__":
    int8_grid(); outlier(); sparsity(); memory_bits(); smolvla_parts()
