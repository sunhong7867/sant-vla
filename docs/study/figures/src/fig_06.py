"""Figures for 06_자율주행_패러다임_인지판단제어에서_월드액션모델까지.md"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style import *

STAGES = ["모듈러", "E2E", "VLA", "월드 모델", "월드 액션 모델"]


def overview():
    fig, ax = canvas(14, 8.2, "자율주행 접근의 다섯 단계 — 한눈에 보기")
    rows = [
        ("단계 0  모듈러", [("센서", "vision")],
         [("인지", "vision"), ("예측", "model"), ("계획", "model"), ("제어", "action")],
         ("조향·가감속", "action"), "사람이 정한 인터페이스(박스·차선·경로)로 연결, 규칙과 최적화"),
        ("단계 1  E2E", [("센서", "vision")], [("하나의 신경망", "model")],
         ("조향·궤적", "action"), "시연 데이터로 통째로 학습"),
        ("단계 2  VLA", [("센서", "vision"), ("문장", "language")],
         [("사전학습 VLM + 행동 출력", "model")], ("궤적 + 설명", "action"),
         "웹 상식과 언어를 행동에 연결"),
        ("단계 3  월드 모델", [("장면", "vision"), ("행동", "action")],
         [("미래 장면 예측기", "model")], ("다음 장면들", "vision"),
         "데이터 생성 · 신경 시뮬레이터 · 상상 속 계획"),
        ("단계 4  월드 액션 모델", [("장면", "vision"), ("지시", "language")],
         [("하나의 모델", "model")], ("미래 장면 + 행동", "action"),
         "\"무엇이 일어날지\" 예측하는 능력을 \"무엇을 할지\"의 근거로"),
    ]
    y = 6.75
    for label, ins, mids, out, desc in rows:
        note(ax, 0.3, y + 0.32, label, bold=True, color=INK, fontsize=11)
        # inputs stacked into one cell
        ih = 0.62 / len(ins) - (0.04 if len(ins) > 1 else 0)
        for k, (t, r) in enumerate(ins):
            box(ax, 2.6, y + 0.62 - (k + 1) * (ih + 0.06) + 0.03, 1.3, ih, t, role=r, fontsize=9)
        x = 4.3
        mw = (5.6 - 0.25 * (len(mids) - 1)) / len(mids)
        prev = (3.9, y + 0.31)
        for t, r in mids:
            b = box(ax, x, y, mw, 0.62, t, role=r, fontsize=9.5)
            arrow(ax, prev, left(b))
            prev = right(b)
            x += mw + 0.25
        o = box(ax, 10.2, y, 1.6, 0.62, out[0], role=out[1], fontsize=9.5)
        arrow(ax, prev, left(o), color=ROLE["action"])
        note(ax, 4.3, y - 0.2, desc, fontsize=9)
        y -= 1.45
    save(fig, "06_overview")


def modular():
    fig, ax = canvas(14.4, 5.4, "단계 0 — 모듈러 파이프라인 (인지 → 예측 → 판단·계획 → 제어)")
    sens = box(ax, 0.3, 1.0, 1.6, 3.2, "", role="vision")
    note(ax, 1.1, 3.9, "센서", ha="center", bold=True, color=INK)
    note(ax, 1.1, 2.5, "카메라\n라이다\n레이더\nGPS / IMU", ha="center", fontsize=9.5, color=INK)
    cols = [
        ("인지", "Perception", "vision", "물체 검출 (YOLO 등)\n추적 (tracking)\n차선·신호등 인식\n자기 위치 추정\nHD 지도 매칭"),
        ("예측", "Prediction", "model", "주변 차·사람의\n미래 궤적"),
        ("판단·계획", "Planning", "model", "행동 결정 (FSM·규칙)\n차선 유지/변경/정지\n경로 생성 (최적화)"),
        ("제어", "Control", "action", "경로 추종\nPID · pure pursuit\nStanley · MPC"),
    ]
    x = 2.5
    prev = sens
    for name, en, role, items in cols:
        b = box(ax, x, 1.0, 2.35, 3.2, "", role=role)
        note(ax, x + 1.175, 3.9, name, ha="center", bold=True, color=INK)
        note(ax, x + 1.175, 3.55, en, ha="center", fontsize=9)
        note(ax, x + 1.175, 2.2, items, ha="center", fontsize=9.5, color=INK)
        arrow(ax, right(prev), left(b))
        prev = b
        x += 2.85
    out = box(ax, x, 2.05, 1.3, 1.1, "조향\n가속", role="action", bold=True)
    arrow(ax, right(prev), left(out), color=ROLE["action"])
    note(ax, 2.5, 0.55, "각 화살표 = 사람이 정의한 인터페이스 (박스 좌표, 차선 다항식, 경로 점열 …).  "
         "우리 저장소의 예: YOLO 차선 스택 → motion_planner → pure pursuit (simple_track_driver)",
         fontsize=9.5)
    save(fig, "06_modular")


def e2e_forms():
    fig, ax = canvas(13.4, 7.0, "단계 1 — E2E 의 세 가지 형태")
    # simple
    note(ax, 0.3, 6.15, "가장 단순한 형태  (ALVINN, PilotNet)", bold=True, color=INK)
    c = box(ax, 0.6, 5.0, 1.6, 0.7, "카메라", role="vision")
    n = box(ax, 3.0, 5.0, 1.8, 0.7, "CNN", role="model")
    o = box(ax, 5.6, 5.0, 1.6, 0.7, "조향각", role="action")
    arrow(ax, right(c), left(n)); arrow(ax, right(n), left(o), color=ROLE["action"])
    # conditional
    note(ax, 0.3, 4.4, "조건부 형태  (CIL: 명령에 따라 다른 출력 헤드)", bold=True, color=INK)
    c = box(ax, 0.6, 3.2, 1.6, 0.6, "카메라", role="vision")
    cmd = box(ax, 0.6, 2.4, 1.6, 0.6, "명령", role="language")
    n = box(ax, 3.0, 2.4, 1.8, 1.4, "CNN", role="model")
    arrow(ax, right(c), (3.0, 3.5)); arrow(ax, right(cmd), (3.0, 2.7), color=ROLE["language"])
    for k, t in enumerate(["좌회전 헤드", "직진 헤드", "우회전 헤드"]):
        yy = 3.45 - k * 0.6
        h = box(ax, 5.6, yy - 0.22, 1.8, 0.45, t, role="action", fontsize=9.5, fill=(k == 1),
                dashed=(k != 1))
        arrow(ax, (4.8, 3.1), left(h))
    out = box(ax, 8.2, 2.85, 1.7, 0.5, "조향 · 가속", role="action", fontsize=9.5)
    arrow(ax, right((5.6, 2.63, 1.8, 0.45)), left(out), color=ROLE["action"])
    note(ax, 10.1, 3.1, "명령이 고른 헤드만 사용\n(그림: \"직진\")", fontsize=9)
    # planning oriented
    note(ax, 0.3, 1.6, "현대 형태 — 계획 지향 E2E  (UniAD)", bold=True, color=INK)
    seq = [("다중 카메라", "vision", 1.6), ("BEV 인코더", "model", 1.7),
           ("검출·추적·지도·예측\n쿼리", "model", 2.4), ("계획 쿼리", "model", 1.6), ("궤적", "action", 1.2)]
    x = 0.6
    prev = None
    for t, r, w in seq:
        b = box(ax, x, 0.35, w, 0.85, t, role=r, fontsize=9.5)
        if prev:
            arrow(ax, right(prev), left(b), color=ROLE["action"] if r == "action" else None)
        prev = b
        x += w + 0.5
    note(ax, x - 0.2, 0.78, "중간 과제도 함께 학습하지만\n최종 손실은 계획", fontsize=9)
    save(fig, "06_e2e_forms")


def vlm_coupling():
    fig, ax = canvas(13, 5.6, "단계 2 — VLM 을 주행에 붙이는 두 가지 방식")
    note(ax, 0.3, 4.85, "(가) VLM 보조 — 이중 구조  (예: DriveVLM-Dual)", bold=True, color=INK)
    cam = box(ax, 0.6, 3.55, 1.6, 0.7, "카메라", role="vision")
    vlm = box(ax, 2.9, 3.45, 2.6, 0.9, "VLM", role="language", bold=True, sub="느림")
    hint = box(ax, 6.2, 3.45, 3.0, 0.9, "상황 설명 · 고수준 판단\n대략 궤적", role="language", fill=False,
               fontsize=9.5)
    sen = box(ax, 0.6, 2.0, 1.6, 0.7, "센서", role="vision")
    fast = box(ax, 2.9, 1.9, 2.6, 0.9, "기존 E2E / 모듈러", role="model", bold=True, sub="빠름")
    fin = box(ax, 6.2, 1.9, 3.0, 0.9, "최종 궤적", role="action", bold=True)
    ctl = box(ax, 10.0, 1.9, 1.4, 0.9, "제어", role="action")
    arrow(ax, right(cam), left(vlm)); arrow(ax, right(vlm), left(hint), color=ROLE["language"])
    arrow(ax, right(sen), left(fast)); arrow(ax, right(fast), left(fin), color=ROLE["action"])
    arrow(ax, bottom(hint), top(fin), color=ROLE["language"], dashed=True, label="참고", label_offset=(0.35, -0.12))
    arrow(ax, right(fin), left(ctl), color=ROLE["action"])

    note(ax, 0.3, 1.25, "(나) VLA — 통합  (예: EMMA, SimLingo, Alpamayo-R1, 우리 SmolVLA)", bold=True, color=INK)
    ins = box(ax, 0.6, 0.15, 2.6, 0.75, "카메라 + 문장 + 상태", role="vision", fontsize=9.5)
    v = box(ax, 3.9, 0.15, 3.0, 0.75, "VLM 백본 + 행동 출력", role="model", bold=True, fontsize=10)
    o = box(ax, 7.6, 0.15, 2.6, 0.75, "궤적 (+ 설명 문장)", role="action", fontsize=10)
    arrow(ax, right(ins), left(v)); arrow(ax, right(v), left(o), color=ROLE["action"])
    save(fig, "06_vlm_coupling")


def world_model():
    fig, ax = canvas(14, 5.6, "단계 3 — 월드 모델: 행동하면 다음 장면이 어떻게 될까")
    o = box(ax, 0.3, 3.0, 1.3, 0.8, "o_t\n현재 장면", role="vision", fontsize=9.5)
    enc = box(ax, 2.1, 3.0, 1.4, 0.8, "인코더", role="model")
    z = box(ax, 4.0, 3.0, 1.0, 0.8, "z_t", role="model", fontsize=10)
    a = box(ax, 5.55, 4.45, 1.5, 0.6, "a_t (조향 왼쪽)", role="action", fontsize=9)
    dyn = box(ax, 5.5, 3.0, 1.6, 0.8, "동역학 모델", role="model", bold=True, fontsize=10)
    z1 = box(ax, 7.6, 3.0, 1.0, 0.8, "ẑ_{t+1}", role="model", fontsize=10)
    dec = box(ax, 9.1, 3.0, 1.4, 0.8, "디코더", role="model")
    o1 = box(ax, 11.0, 3.0, 2.4, 0.8, "ô_{t+1}\n왼쪽으로 꺾인 다음 장면", role="vision", fontsize=9)
    for p, q in [(o, enc), (enc, z), (z, dyn), (dyn, z1), (z1, dec), (dec, o1)]:
        arrow(ax, right(p), left(q))
    arrow(ax, bottom(a), top(dyn), color=ROLE["action"])
    arrow(ax, bottom(z1), (6.3, 3.0), rad=-0.6, dashed=True, color=ROLE["model"])
    note(ax, 7.0, 2.25, "다시 넣어 반복", fontsize=9, ha="center")

    # imagined rollouts
    note(ax, 0.3, 1.65, "상상 속 롤아웃 — 행동 후보마다 미래를 굴려 보고 좋은 쪽을 고른다", bold=True, color=INK)
    cands = [("왼쪽", C["blue"]), ("직진", C["gray"]), ("오른쪽", C["orange"])]
    for k, (name, col) in enumerate(cands):
        yy = 1.05 - k * 0.38
        note(ax, 0.6, yy, f"후보 {name}", fontsize=9)
        x = 2.0
        for s in range(5):
            box(ax, x, yy - 0.14, 0.7, 0.28, "", role=col)
            if s:
                arrow(ax, (x - 0.25, yy), (x, yy), lw=1.2)
            x += 0.95
        res = ["차선 유지", "장애물에 근접", "차선 이탈"][k]
        note(ax, x + 0.1, yy, f"→ 예측 결과: {res}", fontsize=9)
    note(ax, 9.6, 0.65, "용도: 드문 장면 데이터 생성 · 평가용 신경 시뮬레이터\n· 상상 속 계획 · 표현 학습", fontsize=9.5)
    save(fig, "06_world_model")


def wam_types():
    fig, ax = canvas(15, 7.6, "단계 4 — 월드 액션 모델의 구조 유형 (용어 정의는 아직 굳지 않았다)")
    W, H = 7.15, 3.25
    panels = [(0.3, 3.75), (7.65, 3.75), (0.3, 0.2), (7.65, 0.2)]
    titles = ["유형 A — 비디오 예측 사전학습 → 행동 디코딩", "유형 B — 비디오 정책 (계획 = 영상 생성)",
              "유형 C — 비디오·행동 공동 생성", "유형 D — 잠재 공간 예측 + 계획"]
    for (px, py), t in zip(panels, titles):
        group(ax, px, py, W, H, None)
        note(ax, px + 0.2, py + H - 0.3, t, bold=True, color=INK, fontsize=11)
    # A
    px, py = panels[0]
    s1 = box(ax, px + 0.3, py + 1.55, 3.0, 0.8, "대량 영상으로\n다음 프레임 예측 사전학습", role="vision", fontsize=9.5)
    s2 = box(ax, px + 3.9, py + 1.55, 2.9, 0.8, "로봇·주행 시연으로\n행동 헤드 추가 학습", role="action", fontsize=9.5)
    arrow(ax, right(s1), left(s2))
    note(ax, px + 0.3, py + 0.75, "실행: 현재 영상 + 지시 → 미래 프레임 예측 + 행동을 함께 출력", fontsize=9.5)
    note(ax, px + 0.3, py + 0.35, "예: GR-1 / GR-2", fontsize=9)
    # B
    px, py = panels[1]
    i = box(ax, px + 0.3, py + 1.55, 1.7, 0.8, "지시 +\n현재 영상", role="language", fontsize=9.5)
    g = box(ax, px + 2.5, py + 1.55, 1.9, 0.8, "영상 생성 모델", role="model", fontsize=9.5)
    fut = box(ax, px + 4.9, py + 1.55, 1.9, 0.8, "과제를 수행하는\n미래 영상", role="vision", fontsize=9)
    inv = box(ax, px + 4.9, py + 0.35, 1.9, 0.75, "역동역학 모델", role="model", fontsize=9.5)
    act = box(ax, px + 2.5, py + 0.35, 1.9, 0.75, "행동", role="action", fontsize=10)
    arrow(ax, right(i), left(g)); arrow(ax, right(g), left(fut))
    arrow(ax, bottom(fut), top(inv))
    arrow(ax, left(inv), right(act), color=ROLE["action"])
    note(ax, px + 0.3, py + 0.72, "예: UniPi\n(연속 프레임 → 행동)", fontsize=9)
    # C
    px, py = panels[2]
    i = box(ax, px + 0.3, py + 1.3, 1.8, 0.85, "현재 영상\n+ 지시", role="language", fontsize=9.5)
    g = box(ax, px + 2.6, py + 1.3, 2.1, 0.85, "하나의\ndiffusion / flow 모델", role="model", fontsize=9.5)
    f = box(ax, px + 5.2, py + 1.75, 1.7, 0.6, "미래 영상", role="vision", fontsize=9.5)
    a = box(ax, px + 5.2, py + 1.05, 1.7, 0.6, "행동", role="action", fontsize=9.5)
    arrow(ax, right(i), left(g)); arrow(ax, right(g), left(f)); arrow(ax, right(g), left(a), color=ROLE["action"])
    note(ax, px + 0.3, py + 0.45, "두 출력을 같은 노이즈 제거 과정에서 함께 생성", fontsize=9.5)
    # D
    px, py = panels[3]
    s1 = box(ax, px + 0.3, py + 1.6, 2.0, 0.8, "영상으로 잠재 표현·\n예측기 학습", role="vision", fontsize=9)
    s2 = box(ax, px + 2.75, py + 1.6, 2.0, 0.8, "소량 행동 데이터로\n행동 조건 예측기", role="action", fontsize=9)
    s3 = box(ax, px + 5.2, py + 1.6, 1.7, 0.8, "행동열 최적화\n(MPC 식)", role="model", fontsize=9)
    arrow(ax, right(s1), left(s2)); arrow(ax, right(s2), left(s3))
    note(ax, px + 0.3, py + 0.95, "픽셀을 생성하지 않는다. 목표 이미지의 잠재 표현에\n가까워지는 행동열을 고른다", fontsize=9.5)
    note(ax, px + 0.3, py + 0.35, "예: V-JEPA 2-AC", fontsize=9)
    save(fig, "06_wam_types")


def bottleneck():
    fig, ax = canvas(14.6, 4.8, "왜 이 순서로 바뀌나 — 병목의 이동")
    roles = ["neutral"] * 5
    nexts = ["데이터로 대체하자", "웹에서 배운 VLM 을 쓰자", "세상이 어떻게 변하는지\n예측·생성하자",
             "한 모델에서 함께 배우자", "(현재 진행형)"]
    bots = ["사람이 쓰는 규칙과\n튜닝", "주행 데이터에 없는\n상식·언어", "행동 데이터·드문 상황·\n물리 이해",
            "예측과 행동이\n따로 논다", "계산량 · 검증"]
    x = 0.3
    w = 2.55
    prev = None
    for k in range(5):
        b = box(ax, x, 2.9, w, 0.85, f"단계 {k}  {STAGES[k]}", role=roles[k], bold=True, fontsize=10)
        bb = box(ax, x, 1.45, w, 1.0, bots[k], role="bad", fill=False, fontsize=9.5)
        note(ax, x + 0.08, 2.62, "병목", fontsize=8.5, color=ROLE["bad"], bold=True)
        if prev:
            arrow(ax, right(prev), left(b), lw=2.0)
        if k < 4:
            note(ax, x + w + 0.2, 0.95, "→ " + nexts[k], fontsize=9, ha="left")
            arrow(ax, (x + w / 2, 1.45), (x + w + 0.15, 0.95), rad=0.25, color=MUTED, lw=1.2)
        prev = b
        x += w + 0.3
    note(ax, 0.3, 3.95, "각 단계는 앞 단계에서 가장 비싼 것을 줄이는 방향으로 움직였다", fontsize=10)
    save(fig, "06_bottleneck")


def our_position():
    fig, ax = canvas(13, 3.6, "우리 연구의 위치")
    x = 0.4
    w = 2.2
    centers = []
    for k, s in enumerate(STAGES):
        hl = (k == 2)
        b = box(ax, x, 2.0, w, 0.7, s, role="action" if hl else "neutral", fill=hl, bold=hl,
                dashed=not hl and k > 2, fontsize=10)
        if centers:
            arrow(ax, (x - 0.35, 2.35), (x, 2.35), color=MUTED)
        centers.append(center(b))
        x += w + 0.35
    cx = centers[2][0]
    arrow(ax, (cx, 1.35), (cx, 2.0), color=ROLE["action"])
    note(ax, cx, 0.95, "SANT-VLA: 소형 VLA (SmolVLA 약 450M) + 해설 헤드 co-training", ha="center",
         fontsize=10, color=INK, bold=True)
    note(ax, cx, 0.55, "시뮬 단일 트랙 · 학습한 정본 문장으로 차선·속도 전환", ha="center", fontsize=9.5)
    cx0 = centers[0][0]
    arrow(ax, (cx0, 1.35), (cx0, 2.0), color=MUTED, dashed=True)
    note(ax, cx0, 0.95, "교사(시연 생성)", ha="center", fontsize=9.5, color=INK)
    note(ax, cx0, 0.55, "YOLO 차선 스택 · pure pursuit 오라클", ha="center", fontsize=9)
    save(fig, "06_our_position")


if __name__ == "__main__":
    overview()
    modular()
    e2e_forms()
    vlm_coupling()
    world_model()
    wam_types()
    bottleneck()
    our_position()
