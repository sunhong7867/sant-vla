"""Figures for 09_공부_로드맵.md"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *


def roadmap():
    fig, ax = canvas(13.2, 8.4, "공부 로드맵 — 단계와 선후 관계")
    W, H = 2.9, 0.95
    pos = {  # stage -> (x, y, text, role)
        0: (0.5, 6.6, "0. 수학·파이썬·PyTorch", "neutral"),
        1: (4.2, 6.6, "1. 딥러닝 기초\nMLP · CNN · 학습", "model"),
        2: (7.9, 6.6, "2. Transformer\nLLM · VLM", "language"),
        3: (2.3, 4.5, "3. 생성모델\ndiffusion · flow", "model"),
        4: (6.0, 4.5, "4. 로봇학습\nBC · DAgger · 청크", "action"),
        6: (9.7, 4.5, "6. 자율주행 흐름\n모듈러 → E2E → VLA → 월드모델", "vision"),
        5: (6.0, 2.5, "5. VLA", "action"),
        7: (2.3, 0.5, "7. Physical AI\n산업 · 직무", "state"),
        8: (6.0, 0.5, "8. 경량화·배포\n양자화 · 프루닝", "model"),
    }
    B = {}
    for k, (x, y, t, r) in pos.items():
        w = 3.3 if k == 6 else W
        B[k] = box(ax, x, y, w, H, t, role=r, fontsize=10, bold=(k == 5))
    # stage 9 runs alongside everything
    B[9] = box(ax, 9.7, 0.5, 3.3, 1.25, "9. 내 연구 핵심 개념 (SANT-VLA)\n처음부터 병행", role="action",
               fontsize=10, dashed=True)
    arrow(ax, right(B[0]), left(B[1]))
    arrow(ax, right(B[1]), left(B[2]))
    arrow(ax, bottom(B[2]), top(B[3]), rad=-0.1)
    arrow(ax, bottom(B[2]), top(B[4]))
    arrow(ax, bottom(B[2]), top(B[6]), rad=0.1)
    arrow(ax, bottom(B[3]), left(B[5]), rad=0.25)
    arrow(ax, bottom(B[4]), top(B[5]))
    arrow(ax, bottom(B[6]), right(B[5]), rad=-0.25)
    arrow(ax, bottom(B[5]), top(B[7]), rad=-0.15)
    arrow(ax, bottom(B[5]), top(B[8]))
    arrow(ax, bottom(B[5]), top(B[9]), rad=0.15)
    note(ax, 0.5, 0.1, "전체 약 3~4개월 · 각 상자 = study 폴더의 문서 하나 · 9 단계는 1 단계부터 같이 진행", fontsize=10)
    save(fig, "09_roadmap")


if __name__ == "__main__":
    roadmap()
