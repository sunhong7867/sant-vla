"""Figures for 05_VLA란_무엇인가.md"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *


def vla_function():
    fig, ax = canvas(11, 4.2, "VLA = 보고, 듣고, 움직이는 정책")
    cam = box(ax, 0.4, 2.5, 2.2, 0.75, "카메라 영상", role="vision")
    lang = box(ax, 0.4, 1.55, 2.2, 0.75, "지시 문장", role="language")
    st = box(ax, 0.4, 0.6, 2.2, 0.75, "자기 상태", role="state", sub=None)
    vla = box(ax, 4.0, 0.6, 3.2, 2.65, "VLA", role="model", bold=True, fontsize=15,
              sub="수억~수십억 파라미터")
    act = box(ax, 8.6, 1.4, 2.1, 1.05, "행동", role="action", bold=True,
              sub="한 스텝 또는 청크")
    for b in (cam, lang, st):
        arrow(ax, right(b), (4.0, center(b)[1]))
    arrow(ax, right(vla), left(act), color=ROLE["action"])
    note(ax, 4.0, 3.55, "π(a | o, l) — 관측 o 와 지시 l 이 주어졌을 때 행동 a 의 분포", fontsize=10)
    save(fig, "05_vla_function")


def knowledge_sources():
    fig, ax = canvas(11.5, 4.6, "VLA 가 기대하는 지식의 출처")
    pre = box(ax, 0.4, 2.9, 4.0, 0.95, "사전학습 (웹 그림-글)", role="vision", bold=True,
              sub="\"무엇이 무엇인지\" — 물체·색·관계·상식")
    lang = box(ax, 0.4, 1.7, 4.0, 0.95, "언어", role="language", bold=True,
               sub="둘을 잇는 다리 — \"빨간 것\", \"멸종한 동물\"")
    demo = box(ax, 0.4, 0.5, 4.0, 0.95, "로봇·차량 시연", role="action", bold=True,
               sub="\"어떻게 움직이는지\" — 궤적·조향")
    pol = box(ax, 6.6, 1.55, 2.6, 1.25, "VLA 정책", role="model", bold=True)
    arrow(ax, right(pre), (6.6, 2.55), color=ROLE["vision"])
    arrow(ax, right(lang), left(pol), color=ROLE["language"])
    arrow(ax, right(demo), (6.6, 1.8), color=ROLE["action"])
    note(ax, 9.5, 2.17, "\"공룡 앞으로 가\"\n무엇이 공룡인지 → 사전학습\n어떻게 다가가는지 → 시연", fontsize=9.5)
    save(fig, "05_knowledge_sources")


# ---- the three architecture families, drawn with one shared vocabulary ----

def _inputs(ax, x, y_top, w=1.6, h=0.55, gap=0.15):
    """camera / sentence / state stacked; returns the three boxes."""
    cam = box(ax, x, y_top - h, w, h, "카메라", role="vision", fontsize=10)
    lang = box(ax, x, y_top - 2 * h - gap, w, h, "문장", role="language", fontsize=10)
    st = box(ax, x, y_top - 3 * h - 2 * gap, w, h, "상태", role="state", fontsize=10)
    return cam, lang, st


def family_tokens(ax, x0, y0, compact=False):
    """① VLM emits action tokens like words."""
    cam, lang, st = _inputs(ax, x0, y0 + 3.4)
    vlm = box(ax, x0 + 2.2, y0 + 1.55, 1.9, 1.85, "VLM", role="model", bold=True,
              sub="언어모델 그대로")
    for b in (cam, lang, st):
        arrow(ax, right(b), (x0 + 2.2, center(b)[1]))
    tok = box(ax, x0 + 0.3, y0 + 0.2, 3.8, 0.7, "<act_137> <act_12> <act_200> …", role="action",
              fontsize=9.5)
    arrow(ax, bottom(vlm), (x0 + 3.15, y0 + 0.9), color=ROLE["action"])
    note(ax, x0 + 3.3, y0 + 1.22, "토큰을\n하나씩 생성", fontsize=9, ha="left")
    return (x0, y0)


def family_expert(ax, x0, y0, compact=False):
    """② VLM + continuous action expert (flow matching)."""
    cam, lang, st = _inputs(ax, x0, y0 + 3.4)
    vlm = box(ax, x0 + 2.2, y0 + 1.55, 1.9, 1.85, "VLM", role="model", bold=True,
              sub="내부 표현(K/V)")
    for b in (cam, lang, st):
        arrow(ax, right(b), (x0 + 2.2, center(b)[1]))
    noise = box(ax, x0, y0 + 0.2, 1.6, 0.7, "노이즈", role="neutral", fontsize=10)
    ex = box(ax, x0 + 2.2, y0 + 0.2, 1.9, 0.7, "action expert", role="action", fontsize=10,
             bold=True)
    arrow(ax, right(noise), left(ex))
    arrow(ax, bottom(vlm), top(ex), color=ROLE["language"], label="어텐션",
          label_offset=(0.42, -0.12))
    note(ax, x0 + 2.2, y0 - 0.12, "N번 반복 → 연속 행동 청크", fontsize=9, ha="left")
    return (x0, y0)


def family_hier(ax, x0, y0, compact=False):
    """③ big slow VLM above, small fast policy below."""
    lang = box(ax, x0, y0 + 2.75, 1.6, 0.65, "자유 문장", role="language", fontsize=10)
    big = box(ax, x0 + 2.2, y0 + 2.55, 1.9, 1.05, "큰 VLM", role="language", bold=True,
              sub="느림 · 1 Hz 이하")
    arrow(ax, right(lang), left(big))
    cam = box(ax, x0, y0 + 0.75, 1.6, 0.65, "카메라 + 상태", role="vision", fontsize=10)
    small = box(ax, x0 + 2.2, y0 + 0.55, 1.9, 1.05, "작은 정책", role="model", bold=True,
                sub="빠름 · 10 Hz")
    arrow(ax, right(cam), left(small))
    arrow(ax, bottom(big), top(small), color=ROLE["language"], label="정본 문장·목표",
          label_offset=(0.62, -0.12))
    act = box(ax, x0 + 2.2, y0 - 0.25, 1.9, 0.5, "행동", role="action", fontsize=10)
    arrow(ax, bottom(small), top(act), color=ROLE["action"])
    return (x0, y0)


FAMILIES = [
    ("① 행동을 토큰으로", "RT-2 · OpenVLA · FAST", family_tokens),
    ("② VLM + 연속 행동 전문가", "π0 · π0.5 · SmolVLA · GR00T N1", family_expert),
    ("③ 계층형", "SayCan · DriveVLM-Dual · 우리 Qwen + SmolVLA", family_hier),
]


def three_families():
    fig, ax = canvas(15.6, 5.6, "VLA 구조의 세 갈래")
    for i, (name, ex, fn) in enumerate(FAMILIES):
        x0 = 0.4 + i * 5.2
        group(ax, x0 - 0.15, 0.25, 4.75, 4.65, None, role="neutral")
        note(ax, x0, 4.6, name, bold=True, color=INK, fontsize=12)
        note(ax, x0, 4.25, ex, fontsize=9)
        fn(ax, x0, 0.55)
    save(fig, "05_three_families")


def single_family(i, fname):
    name, ex, fn = FAMILIES[i]
    fig, ax = canvas(5.2, 5.2, None)
    note(ax, 0.4, 4.9, name, bold=True, color=INK, fontsize=12)
    note(ax, 0.4, 4.55, ex, fontsize=9)
    fn(ax, 0.4, 0.55)
    save(fig, fname)


def chunking():
    fig, ax = canvas(12, 3.9, "한 스텝 vs 행동 청크")
    # single step row
    note(ax, 0.3, 2.95, "한 스텝", bold=True, color=INK, fontsize=11)
    x = 1.8
    for k in range(8):
        box(ax, x, 2.65, 0.32, 0.6, "", role="vision")
        box(ax, x + 0.38, 2.65, 0.6, 0.6, "a", role="action", fontsize=9)
        x += 1.2
    note(ax, 1.8, 2.35, "관측 → 행동 1개 → 실행 → 관측 … 매 스텝 모델 호출", fontsize=9.5)
    # chunk row
    note(ax, 0.3, 1.15, "청크", bold=True, color=INK, fontsize=11)
    x = 1.8
    for c in range(2):
        box(ax, x, 0.85, 0.32, 0.6, "", role="vision")
        for j in range(8):
            ex_ = j < 5
            box(ax, x + 0.4 + j * 0.5, 0.85, 0.42, 0.6, "a", role="action", fontsize=8,
                fill=ex_, dashed=not ex_)
        x += 4.9
    note(ax, 1.8, 0.5, "관측 → 행동 H개 생성 → 앞쪽 몇 개만 실행(채움) → 다시 관측  (우리: H = 30, 약 21개 실행 후 재추론)",
         fontsize=9.5)
    box(ax, 10.2, 3.35, 0.32, 0.32, "", role="vision")
    note(ax, 10.6, 3.51, "관측", fontsize=9)
    box(ax, 11.15, 3.35, 0.32, 0.32, "", role="action")
    note(ax, 11.55, 3.51, "행동", fontsize=9)
    save(fig, "05_chunking")


def training_stages():
    fig, ax = canvas(13, 4.6, "VLA 학습 레시피 — 일반적인 3단계")
    stages = [
        ("① VLM 사전학습", "웹 그림-글 · 수십억 쌍", "백본 (VLM)", "vision"),
        ("② 로봇 데이터 사전학습", "여러 로봇·과제 시연\n수십만~백만 에피소드", "기반 VLA\nSmolVLA base · π0 base", "model"),
        ("③ 과제 파인튜닝", "내 로봇·내 과제 시연\n수십~수천 에피소드", "내 VLA\n우리 v3y · r26 …", "action"),
    ]
    x = 0.4
    prev = None
    for title, data, out, role in stages:
        b = box(ax, x, 2.2, 3.6, 1.3, "", role=role)
        note(ax, x + 1.8, 3.15, title, ha="center", bold=True, color=INK, fontsize=11.5)
        note(ax, x + 1.8, 2.6, data, ha="center", fontsize=9.5)
        o = box(ax, x + 0.5, 0.35, 2.6, 0.95, out, role=role, fill=False, fontsize=9.5)
        arrow(ax, (x + 1.8, 2.2), top(o), color=ROLE[role] if role in ROLE else role)
        if prev:
            arrow(ax, right(prev), left(b))
        prev = b
        x += 4.25
    note(ax, 0.4, 3.95, "뒤 단계로 갈수록 데이터는 적어지고 내 과제에 가까워진다", fontsize=10)
    save(fig, "05_training_stages")


if __name__ == "__main__":
    vla_function()
    knowledge_sources()
    three_families()
    single_family(0, "05_family_tokens")
    single_family(1, "05_family_expert")
    single_family(2, "05_family_hierarchical")
    chunking()
    training_stages()
