"""Figures for 01_딥러닝_기초_MLP_CNN_Transformer.md"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *  # noqa: E402,F401,F403
import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402


# ---------------------------------------------------------------- charts
def activations():
    z = np.linspace(-4, 4, 400)
    sig = 1 / (1 + np.exp(-z))
    tanh = np.tanh(z)
    relu = np.maximum(0, z)
    gelu = 0.5 * z * (1 + np.vectorize(math.erf)(z / math.sqrt(2)))
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    curves = [("ReLU", relu), ("GELU", gelu), ("Sigmoid", sig), ("Tanh", tanh)]
    for (name, y), col in zip(curves, SERIES):
        ax.plot(z, y, color=col, label=name)
    # direct labels next to each curve
    ax.text(2.35, 1.45, "ReLU · GELU\n(양수에서는 거의 같다)", fontsize=10, color=INK)
    ax.text(-2.95, -0.52, "GELU 는 음수에서\n살짝 내려갔다 0 으로", fontsize=9.5, color=INK2)
    ax.text(-3.9, 0.12, "Sigmoid (0 ~ 1)", fontsize=10, color=INK)
    ax.text(-3.9, -0.88, "Tanh (−1 ~ 1)", fontsize=10, color=INK)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_xlim(-4, 4.2)
    ax.set_ylim(-1.3, 4.1)
    ax.set_xlabel("입력 z")
    ax.set_ylabel("출력 f(z)")
    ax.set_title("활성함수 네 가지")
    ax.legend(loc="upper left")
    fig.text(0.08, -0.02, "Sigmoid·Tanh 는 양 끝에서 평평해져 기울기가 0 에 가까워진다 (기울기 소실)",
             fontsize=9.5, color=INK2)
    save(fig, "01_activation_functions")


def gd_1d():
    th = np.linspace(-0.5, 4.5, 300)
    L = (th - 3) ** 2
    steps = [0.0]
    for _ in range(8):
        steps.append(steps[-1] - 0.1 * 2 * (steps[-1] - 3))
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    ax.plot(th, L, color=SERIES[0], label="손실 L(θ) = (θ − 3)²")
    sx = np.array(steps)
    sy = (sx - 3) ** 2
    ax.plot(sx, sy, color=SERIES[1], lw=1.2, ls="--")
    ax.scatter(sx, sy, s=60, color=SERIES[1], zorder=3, edgecolor=SURFACE, linewidth=2,
               label="경사하강 스텝 (η = 0.1)")
    for i in range(4):
        ax.annotate(f"θ={sx[i]:.2f}", (sx[i], sy[i]), xytext=(8, 6), textcoords="offset points",
                    fontsize=9.5, color=INK)
    ax.annotate("최솟값 θ = 3", (3, 0), xytext=(3.3, 2.0), fontsize=10, color=INK,
                arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1))
    ax.set_xlabel("파라미터 θ")
    ax.set_ylabel("손실")
    ax.set_title("경사하강 — 기울기 반대 방향으로 조금씩 이동")
    ax.legend(loc="upper right")
    ax.set_ylim(-0.5, 12.5)
    save(fig, "01_gradient_descent_1d")


def gd_2d():
    """Plain GD vs momentum on an elongated bowl."""
    a, b = 1.0, 12.0

    def grad(p):
        return np.array([2 * a * p[0], 2 * b * p[1]])

    def run(momentum, lr, n=20):
        p = np.array([-4.0, 1.6])
        v = np.zeros(2)
        path = [p.copy()]
        for _ in range(n):
            g = grad(p)
            v = momentum * v + g
            p = p - lr * v
            path.append(p.copy())
        return np.array(path)

    x = np.linspace(-4.6, 1.2, 300)
    y = np.linspace(-2.0, 2.0, 300)
    X, Y = np.meshgrid(x, y)
    Z = a * X ** 2 + b * Y ** 2
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    ax.contour(X, Y, Z, levels=[0.5, 2, 5, 10, 18, 28, 40], colors=MUTED, linewidths=0.8)
    p1 = run(0.0, 0.075)
    p2 = run(0.5, 0.05)
    ax.plot(p1[:, 0], p1[:, 1], "-o", color=SERIES[0], ms=4, lw=1.6, label="SGD (모멘텀 없음, η = 0.075)")
    ax.plot(p2[:, 0], p2[:, 1], "-o", color=SERIES[1], ms=4, lw=1.6, label="모멘텀 β = 0.5 (η = 0.05)")
    ax.scatter([0], [0], marker="*", s=180, color=INK, zorder=4)
    ax.text(0.12, 0.12, "최솟값", fontsize=10, color=INK)
    ax.set_xlabel("θ₁ (완만한 방향)")
    ax.set_ylabel("θ₂ (가파른 방향)")
    ax.set_title("같은 20 스텝 — 모멘텀은 진동이 줄고 더 빨리 도착 (예시)")
    ax.legend(loc="lower right")
    ax.grid(False)
    ax.set_aspect("equal")
    save(fig, "01_gradient_descent_2d")


def lr_schedule():
    peak, floor, warm, decay = 1e-4, 2.5e-6, 1000, 30000
    s = np.arange(0, 40001)
    lr = np.where(
        s < warm,
        peak * (s + 1) / (warm + 1),
        floor + (peak - floor) * 0.5 * (1 + np.cos(np.pi * np.minimum(s - warm, decay - warm) / (decay - warm))),
    )
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ax.plot(s, lr * 1e4, color=SERIES[0])
    ax.axvspan(0, warm, color=tint(SERIES[0], 0.85), lw=0)
    ax.annotate("warmup 1,000 스텝\n0 → 1e-4 직선 증가", (500, 0.5), xytext=(3000, 0.3),
                fontsize=9.5, color=INK, arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1))
    ax.annotate("cosine decay\n30,000 스텝까지", (15000, 0.55), xytext=(20000, 0.75),
                fontsize=9.5, color=INK, arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1))
    ax.annotate("이후 2.5e-6 유지", (35000, 0.025), xytext=(32000, 0.3),
                fontsize=9.5, color=INK, arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1))
    ax.set_xlabel("학습 스텝")
    ax.set_ylabel("학습률 (× 1e-4)")
    ax.set_title("학습률 스케줄 — v3y 학습 설정 (warmup 1000, decay 30000, 총 40k 스텝)")
    ax.set_xlim(0, 40000)
    ax.set_ylim(0, 1.1)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v/1000)}k"))
    save(fig, "01_lr_schedule")


def overfitting():
    s = np.linspace(0, 100, 300)
    train = 0.08 + 1.4 * np.exp(-s / 18)
    val = 0.35 + 1.15 * np.exp(-s / 16) + 0.0055 * np.maximum(0, s - 38) ** 1.25 / 3
    best = s[np.argmin(val)]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    ax.plot(s, train, color=SERIES[0], label="학습 손실")
    ax.plot(s, val, color=SERIES[1], label="검증 손실")
    ax.axvline(best, color=MUTED, lw=1, ls="--")
    ax.text(best + 1.5, 1.35, "검증 손실 최저점\n(early stopping 지점)", fontsize=9.5, color=INK)
    ax.text(70, 0.22, "학습 손실은 계속 내려감", fontsize=9.5, color=INK)
    ax.text(62, 0.74, "검증 손실은 다시 오름 → 과적합", fontsize=9.5, color=INK)
    ax.set_xlabel("학습 진행 (에폭)")
    ax.set_ylabel("손실")
    ax.set_title("과적합 — 학습 손실과 검증 손실이 갈라지는 지점 (예시)")
    ax.set_xticks([])
    ax.legend(loc="upper right")
    ax.set_ylim(0, 1.6)
    save(fig, "01_overfitting")


def attention_heatmap():
    Q = np.array([[1, 0], [0, 1], [1, 1]], float)
    K = Q.copy()
    S = Q @ K.T / np.sqrt(2)
    W = np.exp(S) / np.exp(S).sum(1, keepdims=True)
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    base = SERIES[0]
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", [tint(base, 0.95), base])
    ax.imshow(W, cmap=cmap, vmin=0, vmax=0.6)
    for i in range(3):
        for j in range(3):
            ax.text(j, i, f"{W[i, j]:.3f}", ha="center", va="center", fontsize=12,
                    color="#ffffff" if W[i, j] > 0.4 else INK)
    labels = ["토큰1", "토큰2", "토큰3"]
    ax.set_xticks(range(3), labels)
    ax.set_yticks(range(3), labels)
    ax.set_xlabel("어디를 보나 (키)")
    ax.set_ylabel("누가 보나 (쿼리)")
    ax.set_title("어텐션 가중치 — 10.4절 예시")
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)
    save(fig, "01_attention_weights")


def param_breakdown():
    parts = [("어텐션 W_Q", 0.9216), ("어텐션 W_K", 0.3072), ("어텐션 W_V", 0.3072),
             ("어텐션 W_O", 0.9216), ("FFN W1", 2.4576), ("FFN W3", 2.4576), ("FFN W2", 2.4576)]
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    names = [p[0] for p in parts][::-1]
    vals = [p[1] for p in parts][::-1]
    cols = [SERIES[1] if n.startswith("FFN") else SERIES[0] for n in names]
    ax.barh(names, vals, color=cols, height=0.6)
    for n, v in zip(names, vals):
        ax.text(v + 0.04, n, f"{v:.2f}M", va="center", fontsize=9.5, color=INK)
    ax.set_xlabel("파라미터 수 (백만)")
    ax.set_title("트랜스포머 층 하나 (d = 960) — 어텐션 약 2.46M, FFN 약 7.37M")
    ax.set_xlim(0, 3.4)
    ax.grid(axis="y", visible=False)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=SERIES[0], label="어텐션"), Patch(color=SERIES[1], label="FFN")],
              loc="upper right")
    save(fig, "01_param_breakdown")


# ---------------------------------------------------------------- diagrams
def mlp():
    fig, ax = canvas(11, 4.6, "MLP 예시 — 28×28 손글씨 숫자 분류")
    layers = [("입력", "784", "vision", 9), ("은닉층 1", "256 · ReLU", "model", 7),
              ("은닉층 2", "128 · ReLU", "model", 5), ("출력", "10 · Softmax", "action", 4)]
    xs = [1.2, 4.0, 6.8, 9.4]
    centers = []
    for (name, sub, role, n), x in zip(layers, xs):
        col = ROLE[role]
        ys = np.linspace(1.0, 3.3, n)
        pts = []
        for yy in ys:
            ax.add_patch(plt.Circle((x, yy), 0.13, facecolor=tint(col, 0.75), edgecolor=col, lw=1.4,
                                    zorder=3, clip_on=False))
            pts.append((x, yy))
        centers.append(pts)
        ax.text(x, 3.75, name, ha="center", fontsize=11, color=INK, fontweight="bold")
        ax.text(x, 0.5, sub, ha="center", fontsize=10, color=INK2)
    for a, b in zip(centers[:-1], centers[1:]):
        for p in a:
            for q in b:
                ax.plot([p[0], q[0]], [p[1], q[1]], color=INK, lw=0.7, zorder=1)
    for x0, x1 in zip(xs[:-1], xs[1:]):
        note(ax, (x0 + x1) / 2, 0.5, "Linear", ha="center", fontsize=9, color=INK2)
    note(ax, 0.25, 0.12, "원은 일부만 그렸다. 모든 점이 다음 층의 모든 점과 연결된다(완전 연결).", fontsize=9.5)
    save(fig, "01_mlp_structure")


def backprop_graph():
    fig, ax = canvas(12, 4.4, "역전파 — 3.2절 숫자 예시 (x = 2, w = 0.5, b = 1, 정답 y = 3)")
    xb = box(ax, 0.4, 2.6, 1.3, 0.8, "x = 2.0", role="state")
    wb = box(ax, 0.4, 1.4, 1.3, 0.8, "w = 0.5", role="model")
    bb = box(ax, 3.2, 0.6, 1.3, 0.8, "b = 1.0", role="model")
    mul = box(ax, 2.4, 2.0, 1.4, 0.9, "곱하기\nw·x = 1.0", role="neutral", fontsize=10)
    add = box(ax, 5.0, 2.0, 1.5, 0.9, "더하기\nz = ŷ = 2.0", role="neutral", fontsize=10)
    loss = box(ax, 7.9, 2.0, 1.7, 0.9, "손실\nL = (ŷ−3)² = 1", role="bad", fontsize=10)
    arrow(ax, right(xb), (2.4, 2.65))
    arrow(ax, right(wb), (2.4, 2.25))
    arrow(ax, right(mul), left(add))
    arrow(ax, top(bb), (5.4, 2.0))
    arrow(ax, right(add), left(loss))
    # backward annotations
    red = ROLE["action"]
    note(ax, 9.9, 2.45, "∂L/∂ŷ = −2", color=red, bold=True)
    note(ax, 6.55, 3.2, "∂L/∂z = −2 (덧셈은 그대로 전달)", color=red)
    note(ax, 0.4, 1.1, "∂L/∂w = −2 × x = −4.0", color=red, bold=True)
    note(ax, 4.65, 0.95, "∂L/∂b = −2.0", color=red, bold=True)
    arrow(ax, (7.85, 2.75), (6.55, 2.75), color=red, dashed=True)
    arrow(ax, (4.95, 2.75), (3.85, 2.75), color=red, dashed=True)
    note(ax, 6.0, 0.75, "검은 화살표 = 순전파(값 계산)   주황 점선 = 역전파(기울기 전달)\n"
         "갱신(η = 0.1): w ← 0.5 + 0.4 = 0.9,  b ← 1.0 + 0.2 = 1.2", fontsize=10)
    save(fig, "01_backprop_graph")


def norm_axes():
    fig, axs = plt.subplots(1, 2, figsize=(9.5, 4.0))
    for ax, kind in zip(axs, ["BatchNorm", "LayerNorm"]):
        N, Cn = 4, 6
        for i in range(N):
            for j in range(Cn):
                hl = (j == 2) if kind == "BatchNorm" else (i == 1)
                col = SERIES[0] if kind == "BatchNorm" else SERIES[1]
                ax.add_patch(Rectangle((j, N - 1 - i), 0.92, 0.92,
                                       facecolor=tint(col, 0.35) if hl else tint(MUTED, 0.85),
                                       edgecolor=SURFACE, lw=2))
        ax.set_xlim(-0.2, Cn)
        ax.set_ylim(-0.2, N)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.text(Cn / 2, -0.55, "특징 C →", ha="center", fontsize=10, color=INK2)
        ax.text(-0.5, N / 2, "배치 N →", rotation=90, va="center", ha="center", fontsize=10, color=INK2)
        desc = ("같은 특징을 배치 방향으로 모아 평균\n→ 특징마다 평균 하나 (배치 크기에 의존)"
                if kind == "BatchNorm" else
                "한 샘플의 특징 전체로 평균\n→ 샘플마다 평균 하나 (배치 1 에서도 같음)")
        ax.set_title(kind, loc="center")
        ax.text(Cn / 2, -1.35, desc, ha="center", fontsize=9.5, color=INK, linespacing=1.4)
    fig.suptitle("정규화층이 평균을 내는 방향", x=0.05, ha="left", fontsize=14, fontweight="bold")
    fig.subplots_adjust(bottom=0.25, top=0.82)
    save(fig, "01_batchnorm_vs_layernorm")


def residual_block():
    fig, ax = canvas(8, 3.2, "잔차연결 — y = x + F(x)")
    xin = box(ax, 0.4, 1.2, 1.2, 0.8, "x", role="state", bold=True)
    f = box(ax, 3.0, 1.8, 2.0, 0.9, "층 F\n(Norm → 계산)", role="model", fontsize=10)
    plus = box(ax, 5.9, 1.2, 0.8, 0.8, "+", role="neutral", bold=True, fontsize=14)
    out = box(ax, 7.2, 1.2, 0.7, 0.8, "y", role="action", bold=True)
    arrow(ax, right(xin), left(f), rad=-0.2)
    arrow(ax, right(f), (6.3, 2.0), rad=-0.2)
    arrow(ax, right(xin), left(plus), label="지름길: x 를 그대로", label_offset=(0, -0.45))
    arrow(ax, right(plus), left(out))
    note(ax, 0.4, 0.35, "F 는 '얼마나 바꿀지'만 배우면 된다. 역전파 때 기울기가 지름길로 그대로 흐른다.", fontsize=9.5)
    save(fig, "01_residual_block")


def grid(ax, x0, y0, M, cell=0.42, hl=None, hl_col=None, title=None):
    M = np.array(M)
    r, c = M.shape
    for i in range(r):
        for j in range(c):
            on = hl is not None and hl[0] <= i < hl[0] + hl[2] and hl[1] <= j < hl[1] + hl[3]
            ax.add_patch(Rectangle((x0 + j * cell, y0 + (r - 1 - i) * cell), cell, cell,
                                   facecolor=tint(hl_col, 0.7) if on else tint(MUTED, 0.9),
                                   edgecolor=SURFACE, lw=1.5, clip_on=False))
            ax.text(x0 + j * cell + cell / 2, y0 + (r - 1 - i) * cell + cell / 2, f"{M[i, j]:g}",
                    ha="center", va="center", fontsize=10.5, color=INK)
    if title:
        ax.text(x0 + c * cell / 2, y0 + r * cell + 0.18, title, ha="center", fontsize=10.5,
                color=INK, fontweight="bold")


def conv_example():
    I = [[1, 1, 1, 0, 0], [0, 1, 1, 1, 0], [0, 0, 1, 1, 1], [0, 0, 1, 1, 0], [0, 1, 1, 0, 0]]
    Kf = [[1, 0, 1], [0, 1, 0], [1, 0, 1]]
    O = [[4, 3, 4], [2, 4, 3], [2, 3, 4]]
    fig, ax = canvas(10, 3.6, "합성곱 — 3×3 필터를 미끄러뜨리며 곱해서 더한다")
    grid(ax, 0.4, 0.5, I, hl=(0, 0, 3, 3), hl_col=SERIES[0], title="입력 5×5")
    note(ax, 2.75, 1.55, "⊛", fontsize=20, color=INK, ha="center")
    grid(ax, 3.2, 0.92, Kf, hl=(0, 0, 3, 3), hl_col=SERIES[1], title="필터 3×3")
    note(ax, 4.95, 1.55, "=", fontsize=20, color=INK, ha="center")
    grid(ax, 5.4, 0.92, O, hl=(0, 0, 1, 1), hl_col=SERIES[2], title="출력 3×3")
    note(ax, 7.0, 2.0, "파란 영역 × 필터\n= 1+1+1+1 = 4\n→ 출력 왼쪽 위 칸", fontsize=10)
    note(ax, 7.0, 0.95, "필터를 한 칸씩 옮기며\n같은 계산을 반복한다", fontsize=10)
    save(fig, "01_conv_example")


def maxpool():
    I = [[1, 3, 2, 1], [5, 6, 1, 0], [7, 2, 8, 3], [1, 0, 4, 2]]
    fig, ax = canvas(7.2, 3.7, "Max pooling 2×2, stride 2")
    cols = [SERIES[0], SERIES[1], SERIES[2], SERIES[3]]
    cell = 0.5
    for i in range(4):
        for j in range(4):
            q = (i // 2) * 2 + (j // 2)
            ax.add_patch(Rectangle((0.5 + j * cell, 0.4 + (3 - i) * cell), cell, cell,
                                   facecolor=tint(cols[q], 0.75), edgecolor=SURFACE, lw=2))
            ax.text(0.5 + j * cell + cell / 2, 0.4 + (3 - i) * cell + cell / 2, str(I[i][j]),
                    ha="center", va="center", fontsize=11, color=INK,
                    fontweight="bold" if I[i][j] == max(I[(i // 2) * 2 + a][(j // 2) * 2 + b]
                                                        for a in (0, 1) for b in (0, 1)) else "normal")
    out = [[6, 2], [7, 8]]
    for i in range(2):
        for j in range(2):
            q = i * 2 + j
            ax.add_patch(Rectangle((4.6 + j * cell, 0.9 + (1 - i) * cell), cell, cell,
                                   facecolor=tint(cols[q], 0.6), edgecolor=SURFACE, lw=2))
            ax.text(4.6 + j * cell + cell / 2, 0.9 + (1 - i) * cell + cell / 2, str(out[i][j]),
                    ha="center", va="center", fontsize=12, color=INK, fontweight="bold")
    arrow(ax, (2.7, 1.4), (4.4, 1.4), label="각 2×2 칸의 최댓값")
    note(ax, 0.5, 2.62, "입력 4×4", bold=True, color=INK)
    note(ax, 4.6, 2.15, "출력 2×2", bold=True, color=INK)
    save(fig, "01_maxpool")


def receptive_field():
    fig, ax = canvas(9.5, 3.8, "수용 영역 — 3×3 합성곱을 쌓을수록 넓어진다")
    cell = 0.32
    n = 7
    x0, y0 = 0.6, 0.45
    for i in range(n):
        for j in range(n):
            d = max(abs(i - 3), abs(j - 3))
            col = SERIES[0] if d == 0 else (SERIES[1] if d == 1 else (SERIES[2] if d == 2 else SERIES[3]))
            ax.add_patch(Rectangle((x0 + j * cell, y0 + i * cell), cell, cell,
                                   facecolor=tint(col, 0.55 + 0.1 * d), edgecolor=SURFACE, lw=1.5))
    rows = [(SERIES[0], "출력 1칸"), (SERIES[1], "1층 뒤: 3×3 영역"), (SERIES[2], "2층 뒤: 5×5 영역"),
            (SERIES[3], "3층 뒤: 7×7 영역")]
    for k, (col, t) in enumerate(rows):
        yy = 2.7 - k * 0.55
        ax.add_patch(Rectangle((4.0, yy - 0.15), 0.3, 0.3, facecolor=tint(col, 0.5), edgecolor=col))
        note(ax, 4.45, yy, t, fontsize=10.5, color=INK)
    note(ax, 4.0, 0.45, "stride 2 나 풀링이 끼면 더 빨리 넓어진다.\n화면 양 끝을 잇으려면 층을 많이 쌓아야 한다(트랜스포머는 한 층).",
         fontsize=9.5)
    save(fig, "01_receptive_field")


def resnet18():
    fig, ax = canvas(13, 3.6, "ResNet18 구조 (입력 224×224)")
    stages = [("conv 7×7\n64, stride 2", "112×112", "vision"), ("maxpool\n3×3, stride 2", "56×56", "neutral"),
              ("[3×3 conv, 64]\n× 2 블록", "56×56", "model"), ("[3×3 conv, 128]\n× 2 블록", "28×28", "model"),
              ("[3×3 conv, 256]\n× 2 블록", "14×14", "model"), ("[3×3 conv, 512]\n× 2 블록", "7×7", "model"),
              ("global\navg pool", "512 벡터", "neutral"), ("fc", "1000 클래스", "action")]
    w, gap, x = 1.35, 0.25, 0.4
    prev = None
    for t, size, role in stages:
        b = box(ax, x, 1.3, w, 1.3, t, role=role, fontsize=9.5)
        note(ax, x + w / 2, 0.95, size, ha="center", fontsize=9.5)
        if prev:
            arrow(ax, right(prev), left(b))
        prev = b
        x += w + gap
    note(ax, 0.4, 0.35, "가운데 네 단계의 블록마다 잔차연결이 있다. stage_a 는 마지막 fc 를 떼고 512 벡터를 MLP 에 넣어 cmd 를 냈다.",
         fontsize=9.5)
    save(fig, "01_resnet18")


def transformer_flow():
    fig, ax = canvas(10, 6.7, "트랜스포머 전체 흐름 (Pre-LN, 아래에서 위로)")
    tok = box(ax, 3.0, 0.3, 4.0, 0.7, "입력 토큰 ID 열", role="language")
    emb = box(ax, 3.0, 1.35, 4.0, 0.75, "임베딩 (ID → d 차원 벡터) + 위치 정보", role="language", fontsize=10)
    group(ax, 1.6, 2.45, 6.8, 2.1, "트랜스포머 층 × L", role="model")
    a = box(ax, 2.2, 2.6, 5.6, 0.7, "① x = x + Attention(Norm(x))", role="model", fontsize=10.5)
    f = box(ax, 2.2, 3.4, 5.6, 0.7, "② x = x + FFN(Norm(x))", role="model", fontsize=10.5)
    head = box(ax, 3.0, 5.0, 4.0, 0.75, "최종 Norm → 출력 머리\n(다음 토큰 확률 · 분류 · 회귀)", role="action", fontsize=10)
    arrow(ax, top(tok), bottom(emb))
    arrow(ax, top(emb), (5.0, 2.6))
    arrow(ax, (5.0, 4.1), bottom(head))
    note(ax, 8.6, 3.5, "같은 층을\nL 번 반복", fontsize=10)
    save(fig, "01_transformer_flow")


def causal_mask():
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    n = 4
    for i in range(n):
        for j in range(n):
            ok = j <= i
            ax.add_patch(Rectangle((j, n - 1 - i), 0.94, 0.94,
                                   facecolor=tint(SERIES[0], 0.45) if ok else tint(MUTED, 0.85),
                                   edgecolor=SURFACE, lw=2))
            ax.text(j + 0.47, n - 1 - i + 0.47, "볼 수 있음" if ok else "가림", ha="center", va="center",
                    fontsize=9.5, color=INK if ok else MUTED)
    ax.set_xlim(0, n)
    ax.set_ylim(0, n)
    ax.set_xticks([k + 0.47 for k in range(n)], [f"토큰{k+1}" for k in range(n)])
    ax.set_yticks([n - 1 - k + 0.47 for k in range(n)], [f"토큰{k+1}" for k in range(n)])
    ax.set_xlabel("볼 대상 (키)")
    ax.set_ylabel("보는 토큰 (쿼리)")
    ax.set_title("Causal mask — 자기와 앞쪽만 본다")
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)
    save(fig, "01_causal_mask")


def vit():
    fig, ax = canvas(12, 3.6, "ViT — 이미지를 패치로 잘라 토큰으로 쓴다")
    cell = 0.45
    for i in range(4):
        for j in range(4):
            ax.add_patch(Rectangle((0.4 + j * cell, 0.7 + i * cell), cell, cell,
                                   facecolor=tint(SERIES[0], 0.55 + 0.08 * ((i + j) % 3)),
                                   edgecolor=SURFACE, lw=2))
    note(ax, 0.4 + 2 * cell, 0.42, "이미지 H×W×3\nP×P 패치로 자름", ha="center", fontsize=9.5)
    emb = box(ax, 3.0, 1.0, 2.0, 1.2, "패치 임베딩\n(선형층)\n+ 위치 임베딩", role="vision", fontsize=9.5)
    tr = box(ax, 6.0, 1.0, 2.4, 1.2, "트랜스포머\nencoder × L", role="model", fontsize=10.5)
    out = box(ax, 9.3, 1.0, 2.3, 1.2, "패치별 출력 벡터\nN = (H/P)·(W/P) 개", role="vision", fontsize=9.5)
    arrow(ax, (2.3, 1.6), left(emb), label="N 개 패치")
    arrow(ax, right(emb), left(tr))
    arrow(ax, right(tr), left(out))
    note(ax, 3.0, 0.45, "SigLIP: 512×512, P = 16 → 1024 패치", fontsize=9.5)
    save(fig, "01_vit")


if __name__ == "__main__":
    for f in [activations, gd_1d, gd_2d, lr_schedule, overfitting, attention_heatmap, param_breakdown,
              mlp, backprop_graph, norm_axes, residual_block, conv_example, maxpool, receptive_field,
              resnet18, transformer_flow, causal_mask, vit]:
        f()
