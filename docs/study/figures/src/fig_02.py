"""Figures for 02_LLM과_VLM.md"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *
import numpy as np


def training_stages():
    fig, ax = canvas(12.4, 4.6, "LLM 학습 3단계 — 사전학습 → 지시 튜닝 → 선호 학습")
    stages = [
        ("① 사전학습", "인터넷 텍스트 · 수조 토큰", "다음 토큰 예측", "base 모델", "문서를 이어 쓴다", "neutral"),
        ("② 지시 튜닝 (SFT)", "(지시, 좋은 답) 쌍 · 수만~수십만", "다음 토큰 예측", "instruct 모델", "지시를 따른다", "language"),
        ("③ 선호 학습 (RLHF / DPO)", "(질문, 좋은 답, 나쁜 답) · 수만", "선호를 반영", "chat 모델", "도움되고 안전한 답", "action"),
    ]
    x, w, gap = 0.4, 3.6, 0.5
    prev = None
    for title, data, obj, out, desc, role in stages:
        b = box(ax, x, 1.8, w, 1.9, "", role=role)
        note(ax, x + w / 2, 3.35, title, ha="center", bold=True, color=INK, fontsize=11.5)
        note(ax, x + w / 2, 2.75, "데이터: " + data, ha="center", fontsize=9.5)
        note(ax, x + w / 2, 2.3, "목표: " + obj, ha="center", fontsize=9.5)
        o = box(ax, x + 0.5, 0.35, w - 1.0, 0.9, out, role=role, fill=False, bold=True, sub=desc, fontsize=10.5)
        arrow(ax, bottom(b), top(o))
        if prev:
            arrow(ax, right(prev), left(b))
        prev = b
        x += w + gap
    save(fig, "02_training_stages")


def temperature():
    logit = np.array([2.0, 1.0, 0.1])
    Ts = [0.5, 1.0, 2.0]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True)
    for ax, T in zip(axes, Ts):
        p = np.exp(logit / T); p /= p.sum()
        bars = ax.bar(["토큰 A", "토큰 B", "토큰 C"], p, color=SERIES[0], width=0.55)
        for b, v in zip(bars, p):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", fontsize=10, color=INK)
        ax.set_title(f"T = {T}", fontsize=12)
        ax.set_ylim(0, 1)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("뽑힐 확률")
    fig.suptitle("Temperature 효과 (예시, logit = [2.0, 1.0, 0.1]) — T 가 작을수록 1등에 몰린다",
                 x=0.01, ha="left", fontsize=13, fontweight="bold")
    fig.tight_layout()
    save(fig, "02_temperature")


def kv_cache():
    n = np.arange(0, 2049, 16)
    # SmolVLM2 text-model numbers from the doc: KV heads 5, head_dim 64, BF16
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    for i, L in enumerate([16, 32]):
        mb = 2 * L * 5 * 64 * n * 2 / 1e6
        ax.plot(n, mb, color=SERIES[i], label=f"{L}층")
        ax.text(n[-1] + 30, mb[-1], f"{L}층  {mb[-1]:.0f} MB", va="center", color=INK, fontsize=10)
    ax.axvline(200, color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(230, 50, "우리 prefix 약 200 토큰\n16층 → 약 4 MB", fontsize=9.5, color=INK2)
    ax.set_xlabel("시퀀스 길이 (토큰)")
    ax.set_ylabel("KV 캐시 (MB, BF16, 배치 1)")
    ax.set_title("KV 캐시는 시퀀스 길이에 비례해 커진다 (KV 헤드 5, head_dim 64)")
    ax.set_xlim(0, 2500)
    ax.legend(loc="lower right")
    save(fig, "02_kv_cache")


def clip_matrix():
    rng = np.random.default_rng(0)
    S = rng.uniform(0.05, 0.35, (5, 5))
    np.fill_diagonal(S, rng.uniform(0.8, 0.95, 5))
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    im = ax.imshow(S, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(5), [f"글 T{i+1}" for i in range(5)])
    ax.set_yticks(range(5), [f"그림 I{i+1}" for i in range(5)])
    ax.grid(False)
    for i in range(5):
        for j in range(5):
            ax.text(j, i, f"{S[i,j]:.2f}", ha="center", va="center", fontsize=9.5,
                    color="white" if S[i, j] > 0.6 else INK)
    ax.set_title("CLIP 유사도 행렬 (예시) — 대각선 = 짝, 가깝게\n나머지 = 짝 아님, 멀게", fontsize=12)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "02_clip_matrix")


def vlm_structure():
    fig, ax = canvas(12.6, 3.9, "LLaVA 식 VLM 구조 — 비전 인코더 → 프로젝터 → LLM")
    img = box(ax, 0.3, 1.5, 1.3, 1.2, "이미지", role="vision")
    enc = box(ax, 2.5, 1.5, 2.2, 1.2, "비전 인코더", role="vision", sub="CLIP / SigLIP ViT")
    proj = box(ax, 5.6, 1.5, 1.9, 1.2, "프로젝터", role="model", sub="LLM 차원으로 맞춤")
    it = box(ax, 8.1, 2.25, 1.7, 0.6, "이미지 토큰 N개", role="vision", fontsize=9.5)
    tt = box(ax, 8.1, 1.35, 1.7, 0.6, "텍스트 토큰", role="language", fontsize=9.5)
    llm = box(ax, 10.4, 1.5, 1.4, 1.2, "LLM", role="language", bold=True, sub="decoder")
    arrow(ax, right(img), left(enc))
    arrow(ax, right(enc), left(proj), label="패치 특징 N개", label_offset=(0, 0.12))
    arrow(ax, right(proj), left(it))
    arrow(ax, right(it), (10.4, 2.3))
    arrow(ax, right(tt), (10.4, 1.9))
    arrow(ax, right(llm), (12.4, 2.1))
    note(ax, 12.45, 2.1, "답", ha="left")
    note(ax, 0.3, 0.7, "이미지 토큰을 텍스트 토큰 앞에 나란히 놓으면, LLM 은 둘을 같은 방식으로 읽는다.", fontsize=10)
    save(fig, "02_vlm_structure")


def pixel_shuffle():
    fig, ax = canvas(12.0, 3.9, "Pixel Shuffle — 이웃 패치를 채널로 접어 토큰 수를 줄인다")
    # left grid 4x4 (stands for 32x32)
    cols = [SERIES[0], SERIES[1], SERIES[2], SERIES[3]]
    s, x0, y0 = 0.42, 0.6, 1.0
    for i in range(4):
        for j in range(4):
            k = (i % 2) * 2 + (j % 2)
            ax.add_patch(plt.Rectangle((x0 + j * s, y0 + (3 - i) * s), s * 0.92, s * 0.92,
                                       fc=tint(cols[k], 0.55), ec=cols[k], lw=1.2))
    note(ax, x0 + 2 * s, y0 - 0.35, "패치 격자 (예: 4×4)\n실제는 32×32 = 1,024", ha="center", fontsize=9.5)
    arrow(ax, (x0 + 4 * s + 0.3, y0 + 2 * s), (3.4, y0 + 2 * s), label="2×2 묶기")
    # right: 2x2 tokens each a stacked bar of 4 channels
    xs = 3.7
    for i in range(2):
        for j in range(2):
            bx, by = xs + j * 1.3, y0 + (1 - i) * 1.0
            for k in range(4):
                ax.add_patch(plt.Rectangle((bx + k * 0.25, by), 0.23, 0.8, fc=tint(cols[k], 0.55), ec=cols[k], lw=1.0))
    note(ax, xs + 1.25, y0 - 0.35, "토큰 4개 (1/4)\n각 토큰 채널 ×4", ha="center", fontsize=9.5)
    arrow(ax, (xs + 2.6, y0 + 0.9), (7.0, y0 + 0.9), label="프로젝터")
    box(ax, 7.1, y0 + 0.4, 1.9, 1.0, "LLM 차원\n(960)", role="language", fontsize=10)
    group(ax, 9.4, 0.95, 2.45, 1.95, "SmolVLM2 실제 값", role="neutral")
    note(ax, 9.55, 1.75, "배율 r = 4\n32×32 = 1,024 패치\n→ 8×8 = 64 토큰 (1/16)\n채널 768 → 12,288\n→ 프로젝터 → 960", fontsize=9.5)
    save(fig, "02_pixel_shuffle")


def smolvlm2():
    fig, ax = canvas(12.2, 3.0, "SmolVLM2-500M-Video-Instruct 구조 (실측 약 507.5M)")
    a = box(ax, 0.4, 0.4, 3.4, 1.7, "비전 인코더 (SigLIP ViT)", role="vision", bold=True,
            sub="86.4M · hidden 768\n512×512 → 1,024 패치")
    b = box(ax, 4.5, 0.4, 3.0, 1.7, "connector", role="model", bold=True,
            sub="pixel shuffle ×4\n1,024 → 64 토큰 (960차원)")
    c = box(ax, 8.2, 0.4, 3.6, 1.7, "텍스트 모델 (Llama 계열)", role="language", bold=True,
            sub="hidden 960 · 32층 · 409.3M\nSmolVLA 는 앞 16층만 사용")
    arrow(ax, right(a), left(b))
    arrow(ax, right(b), left(c))
    save(fig, "02_smolvlm2")


if __name__ == "__main__":
    training_stages(); temperature(); kv_cache(); clip_matrix(); vlm_structure(); pixel_shuffle(); smolvlm2()
