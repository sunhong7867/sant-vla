"""Figures for 03_생성모델_Diffusion_FlowMatching.md"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *
import numpy as np

rng = np.random.default_rng(3)


def two_modes(n):
    """Toy 'demonstrations': half swerve left (-2 m), half right (+2 m)."""
    side = rng.choice([-1, 1], n)
    return np.stack([side * 2.0 + rng.normal(0, 0.35, n), rng.normal(0, 0.35, n)], 1)


def multimodal_mean():
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.15, 1]})
    # left: top-down paths
    ax = axes[0]
    t = np.linspace(0, 1, 60)
    for k in range(14):
        side = -1 if k % 2 == 0 else 1
        amp = 2.0 + rng.normal(0, 0.2)
        x = side * amp * np.sin(np.pi * t) ** 1.5
        ax.plot(x, t * 20, color=SERIES[0] if side < 0 else SERIES[1], lw=1.2, alpha=0.55)
    ax.plot(np.zeros_like(t), t * 20, color=ROLE["bad"], lw=2.5, label="MSE 평균 (정면 충돌)")
    ax.add_patch(plt.Rectangle((-0.7, 9), 1.4, 2, fc=tint(INK2, 0.6), ec=INK2, lw=1.2, zorder=3))
    ax.text(0, 10, "장애물", ha="center", va="center", fontsize=9.5, color=INK, zorder=4)
    ax.text(-2.6, 14.5, "왼쪽 회피 시연", color=INK, fontsize=10, ha="center")
    ax.text(2.6, 14.5, "오른쪽 회피 시연", color=INK, fontsize=10, ha="center")
    ax.set_xlim(-4, 4); ax.set_ylim(0, 20)
    ax.set_xlabel("횡 위치 (m)"); ax.set_ylabel("진행 거리 (m)")
    ax.set_title("시연 경로 (예시) — 정답이 두 갈래")
    ax.legend(loc="lower right")
    # right: density of lateral action at obstacle
    ax = axes[1]
    xs = np.linspace(-4, 4, 400)
    dens = 0.5 * np.exp(-(xs - 2) ** 2 / (2 * 0.35 ** 2)) + 0.5 * np.exp(-(xs + 2) ** 2 / (2 * 0.35 ** 2))
    dens /= np.trapz(dens, xs)
    ax.fill_between(xs, dens, color=tint(SERIES[0], 0.7), lw=0)
    ax.plot(xs, dens, color=SERIES[0], label="정답 분포 p(a | o)")
    ax.axvline(0, color=ROLE["bad"], lw=2.5, label="회귀 출력 = 평균")
    ax.text(0.15, dens.max() * 1.12, "어느 시연에도 없는 행동", color=INK, fontsize=10)
    ax.set_ylim(0, dens.max() * 1.45)
    ax.set_xlabel("장애물 옆 횡 이동 (m)"); ax.set_ylabel("밀도")
    ax.set_title("분포로 보면 — 평균은 골짜기에 떨어진다")
    ax.legend(loc="upper center", ncol=2)
    fig.tight_layout()
    save(fig, "03_multimodal_mean")


def diffusion_strip():
    x0 = two_modes(400)
    abar = [1.0, 0.8, 0.5, 0.2, 0.0]
    fig, axes = plt.subplots(1, 5, figsize=(13, 3.3), sharex=True, sharey=True)
    eps = rng.normal(0, 1, x0.shape)
    for i, (ax, a) in enumerate(zip(axes, abar)):
        xt = np.sqrt(a) * x0 / 2 + np.sqrt(1 - a) * eps  # data scaled to ~unit size
        ax.scatter(xt[:, 0], xt[:, 1], s=6, color=SERIES[0], alpha=0.6, lw=0)
        ax.set_title(["x₀ (데이터)", "조금 노이즈", "절반", "거의 노이즈", "x_T (순수 노이즈)"][i], fontsize=11)
        ax.set_xlim(-3.2, 3.2); ax.set_ylim(-3.2, 3.2); ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(0, -2.9, f"ᾱ = {a}", ha="center", fontsize=9.5, color=INK2)
    fig.suptitle("Diffusion 전방 과정 (예시) — 왼쪽→오른쪽: 노이즈를 더함 (고정)  ·  오른쪽→왼쪽: 노이즈를 걷어냄 (학습)",
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold")
    fig.tight_layout()
    save(fig, "03_diffusion_strip")


def flow_paths():
    """Straight noise→data pairs and a 10-step Euler sample with the exact marginal velocity."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    data = two_modes(300) / 1.0
    noise = rng.normal(0, 1, data.shape)
    ax = axes[0]
    for k in range(40):
        ax.plot([noise[k, 0], data[k, 0]], [noise[k, 1], data[k, 1]], color=MUTED, lw=0.8, alpha=0.7)
    ax.scatter(noise[:, 0], noise[:, 1], s=8, color=SERIES[0], alpha=0.6, lw=0, label="노이즈 x₀ ~ N(0, I)")
    ax.scatter(data[:, 0], data[:, 1], s=8, color=SERIES[1], alpha=0.6, lw=0, label="데이터 x₁ (행동)")
    ax.set_title("학습: 노이즈와 데이터를 직선으로 잇고\n그 위의 속도 (x₁ − x₀) 를 맞힌다")
    ax.set_aspect("equal"); ax.set_xlim(-4, 4); ax.set_ylim(-3.5, 3.5)
    ax.legend(loc="lower left", fontsize=9.5)

    # sampling with the true marginal velocity field of this toy (mixture of two gaussians)
    ax = axes[1]
    mus = np.array([[-2.0, 0.0], [2.0, 0.0]]); s = 0.35

    def v(x, t):
        # x_t = (1-t) x0 + t x1, x0~N(0,I), x1~mixture -> E[x1 - x0 | x_t]
        var = (1 - t) ** 2 + (t * s) ** 2
        w = np.stack([np.exp(-np.sum((x - t * m) ** 2, 1) / (2 * var)) for m in mus], 1)
        w /= w.sum(1, keepdims=True) + 1e-12
        out = np.zeros_like(x)
        for j, m in enumerate(mus):
            ex1 = t * m + 0  # placeholder
            # posterior mean of x1 given x_t under component j
            k1 = (t * s ** 2) / var
            mean_x1 = m + k1 * (x - t * m)
            mean_x0 = ((1 - t) / var) * (x - t * m)
            out += w[:, [j]] * (mean_x1 - mean_x0)
        return out

    starts = rng.normal(0, 1, (12, 2))
    for k, x in enumerate(starts):
        traj = [x.copy()]
        xx = x[None].copy()
        for i in range(10):
            t = i / 10
            xx = xx + 0.1 * v(xx, t)
            traj.append(xx[0].copy())
        traj = np.array(traj)
        ax.plot(traj[:, 0], traj[:, 1], color=SERIES[0], lw=1.4, alpha=0.8)
        ax.scatter(traj[:, 0], traj[:, 1], s=10, color=SERIES[0], zorder=3, lw=0)
        ax.scatter(traj[-1, 0], traj[-1, 1], s=40, color=SERIES[1], zorder=4, lw=0)
    ax.scatter(data[:, 0], data[:, 1], s=6, color=tint(SERIES[1], 0.6), lw=0, zorder=1)
    ax.set_title("추론: 노이즈에서 출발해 예측 속도를 따라\n오일러 10스텝 (점 하나 = 한 스텝)")
    ax.text(0, -2.6, "각 출발점은 왼쪽 또는 오른쪽 한 갈래로 간다\n— 평균(가운데)으로 가지 않는다",
            ha="center", fontsize=9.5, color=INK2)
    ax.set_aspect("equal"); ax.set_xlim(-4, 4); ax.set_ylim(-3.5, 3.5)
    fig.suptitle("Flow Matching (예시, 2차원 장난감 문제)", x=0.01, ha="left", fontsize=13, fontweight="bold")
    fig.tight_layout()
    save(fig, "03_flow_paths")


def cfg():
    fig, ax = plt.subplots(figsize=(8, 4.6))
    null = np.array([0.0, 0.0]); cond = np.array([1.0, 0.5])
    pts = {"null (빈 조건)": null, "cond (실제 문장)": cond}
    ws = [1.0, 2.0, 3.0]
    ax.annotate("", xy=cond * 3.2, xytext=null, arrowprops=dict(arrowstyle="-", color=MUTED, ls=(0, (4, 3))))
    ax.scatter(*null, s=90, color=SERIES[0], zorder=3); ax.text(-0.1, -0.22, "v(∅)  빈 조건 출력", fontsize=10.5, color=INK)
    for w in ws:
        p = null + w * (cond - null)
        ax.scatter(*p, s=90, color=SERIES[1] if w == 1 else ROLE["action"], zorder=3,
                   marker="o" if w == 1 else "D")
        ax.text(p[0] + 0.07, p[1] - 0.17, f"w = {w:g}" + ("  (= 조건부 출력)" if w == 1 else ""), fontsize=10.5, color=INK)
    ax.annotate("", xy=cond, xytext=null, arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1.6))
    ax.text(0.35, 0.33, "조건 때문에 생긴 차이\nv(c) − v(∅)", fontsize=10, color=INK2, ha="center")
    ax.set_xlim(-0.4, 3.6); ax.set_ylim(-0.5, 1.9)
    ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Classifier-Free Guidance — 차이를 w 배로 늘려 조건 효과를 키운다\nv = v(∅) + w · (v(c) − v(∅))")
    ax.text(1.8, -0.42, "모델이 문장을 안 읽으면 v(c) ≈ v(∅) → 늘릴 차이가 없다", fontsize=10, color=INK2, ha="center")
    save(fig, "03_cfg")


if __name__ == "__main__":
    multimodal_mean(); diffusion_strip(); flow_paths(); cfg()
