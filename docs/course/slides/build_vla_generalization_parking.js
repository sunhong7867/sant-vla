const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/home/sh/.config/Claude/local-agent-mode-sessions/skills-plugin/8963f022-f39c-4a07-9096-3d09ccd635ba/5e42d03c-c0ca-4478-a91c-80a8dd2c1b12/skills/pptx/scripts/apply_theme.js");

const OUT = process.argv[2] || "vla_generalization_parking.pptx";

const THEME = {
  name: "nav-vla boundary",
  headFontFace: "Noto Sans CJK KR",
  bodyFontFace: "Noto Sans CJK KR",
  colors: {
    dk1: "1B2228", lt1: "FFFFFF", dk2: "3D4A54", lt2: "EEF1F3",
    accent1: "E8712B", // 분포 밖 / 경계 (orange)
    accent2: "1A9E8C", // 분포 안 (teal)
    accent3: "C9A227", // amber
    accent4: "7A8C99", // muted slate
    accent5: "B23A3A", // 실패/빨강
    accent6: "5B7FA6", // 보조 파랑
    hlink: "1A9E8C", folHlink: "7A8C99",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "sunhong";
pres.title = "우리 트랙에서 VLA 일반화는 왜 어려운가";
const C = pres.SchemeColor;

const W = 13.33, H = 7.5, M = 0.6;
const FOOT = "nav-vla · 연구 경과 2026-10-03 ~ 10-09 기준";

// ---------- layouts ----------
pres.defineSlideMaster({
  title: "DARK",
  background: { color: THEME.colors.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.2, w: W - 2 * M, h: 1.6, fontSize: 38, bold: true, color: C.background1, valign: "bottom", margin: 0 } } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.0, w: W - 2 * M, h: 1.6, fontSize: 18, color: C.background2, valign: "top", margin: 0 } } },
  ],
});
pres.defineSlideMaster({
  title: "LIGHT",
  background: { color: THEME.colors.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.4, w: W - 2 * M, h: 0.85, fontSize: 28, bold: true, color: C.text1, valign: "middle", margin: 0 } } },
    { text: { text: FOOT, options: { x: M, y: H - 0.45, w: 8, h: 0.3, fontSize: 10, color: C.accent4, margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.6, y: H - 0.45, w: 0.6, h: 0.3, fontSize: 10, color: THEME.colors.accent4, align: "right" },
});

// ---------- helpers ----------
function shadow() { return { type: "outer", color: THEME.colors.dk1, blur: 6, offset: 2, angle: 90, opacity: 0.12 }; }
function card(slide, x, y, w, h, opts = {}) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.12,
    fill: { color: opts.fill || C.background2 },
    line: { color: opts.line || C.background2, width: 0.75 },
    shadow: shadow(), objectName: opts.name || "card",
  });
}
function tag(slide, x, y, text, kind, w = 1.25) {
  const color = kind === "in" ? C.accent2 : kind === "out" ? C.accent1 : kind === "warn" ? C.accent5 : C.accent4;
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h: 0.32, rectRadius: 0.16, fill: { color }, line: { color }, objectName: "tag" });
  slide.addText(text, { x, y, w, h: 0.32, fontSize: 11, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "tag-text" });
}
function numCircle(slide, x, y, n, color) {
  slide.addShape(pres.ShapeType.ellipse, { x, y, w: 0.5, h: 0.5, fill: { color: color || C.accent1 }, line: { color: color || C.accent1 }, objectName: "num" });
  slide.addText(String(n), { x, y, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "num-text" });
}
function txt(slide, text, o) {
  slide.addText(text, Object.assign({ fontSize: 14, color: C.text2, margin: 0, isTextBox: true, valign: "top", objectName: "text" }, o));
}
function bullets(slide, items, o) {
  const arr = items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 6 } }));
  slide.addText(arr, Object.assign({ fontSize: 14, color: C.text2, margin: 0, isTextBox: true, valign: "top", objectName: "bullets" }, o));
}
function heading(slide, text, o) {
  slide.addText(text, Object.assign({ fontSize: 16, bold: true, color: C.text1, margin: 0, isTextBox: true, valign: "top", objectName: "heading" }, o));
}
function tableOpts(extra) {
  return Object.assign({
    fontSize: 12, color: THEME.colors.dk2, fontFace: THEME.bodyFontFace,
    border: { type: "solid", color: "D5DAE0", pt: 0.5 }, valign: "middle", margin: 0.06,
    autoPage: false,
  }, extra);
}
function th(t) { return { text: t, options: { bold: true, color: THEME.colors.lt1, fill: { color: THEME.colors.dk2 }, fontSize: 12 } }; }
function td(t, o) { return { text: t, options: Object.assign({ fontSize: 12 }, o || {}) }; }

// =====================================================================
pres.addSection({ title: "도입" });

// ---- 1. 제목 ----
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "도입" });
  s.addText("우리 트랙에서 VLA 일반화는 왜 어려운가", { placeholder: "title" });
  s.addText([
    { text: "\"일반주행·차선변경·회피만 배우고 주차가 되는가\"에 대한 답과,\n", options: {} },
    { text: "\"학습하지 않은 상황\"을 보여 줄 실습 제안", options: {} },
  ], { placeholder: "body" });
  txt(s, "SmolVLA 주행 정책 · Gazebo 시뮬 트랙 · 2026-10-09", { x: M, y: 6.4, w: 8, h: 0.4, fontSize: 12, color: C.accent4 });
  // motif: 분포 안/밖 두 알약
  tag(s, W - M - 2.7, 6.4, "분포 안", "in", 1.25);
  tag(s, W - M - 1.25, 6.4, "분포 밖", "out", 1.25);
  s.addNotes("교수님 질문(2축인데 왜 안 되나)에 대한 답과 실습 제안. 모든 수치는 10-03~10-09 연구 경과 보고서와 회피 홀드아웃 기록에서 가져옴.");
}

// ---- 2. 한 장 요약 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "도입" });
  s.addText("한 장 요약", { placeholder: "title" });
  const y = 1.55, h = 4.3, w = (W - 2 * M - 0.8) / 3;
  const cols = [
    { head: "질문 (교수님)", color: C.accent4, body: [
      "이미지·명령·차량 상태로 일반주행, 차선변경, 장애물 회피를 학습한 정책이 주차(차량 사이 무충돌 진입)를 해내는가",
      "조향과 가감속, 사실상 2축인데 안 될 이유가 있는가",
      "학생에게 \"이게 VLA구나\"를 보여 줄 실습이 되는가",
    ] },
    { head: "답", color: C.accent1, body: [
      "안 된다. 주차는 학습 분포 밖의 관측과 궤적을 요구하고, 모방학습 정책은 그 밖에서 정의되지 않는다",
      "\"2축\"은 차가 할 수 있다는 제어가능성 명제. 정책의 난이도는 출력 차원이 아니라 관측·궤적 분포로 정해진다",
      "우리 실측: 학습한 박스조차 폐루프 회피 실패, 문장 유무로 행동 구별 안 됨 (22/42 vs 23/42)",
    ] },
    { head: "제안", color: C.accent2, body: [
      "동작은 분포 안에, 상황은 분포 밖에 두는 실습: 미학습 물체 → 배치 → 조합 → 동작 순서의 사다리",
      "주차는 \"안 되는 것을 먼저 측정\"하고, 소량 시연 추가로 붙는 곡선을 보여 준다",
      "모든 실험에 사전 기각선과 상수 문장 대조군을 붙인다",
    ] },
  ];
  cols.forEach((c, i) => {
    const x = M + i * (w + 0.4);
    card(s, x, y, w, h);
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.3, y: y + 0.3, w: 0.28, h: 0.28, fill: { color: c.color }, line: { color: c.color }, objectName: "dot" });
    heading(s, c.head, { x: x + 0.7, y: y + 0.25, w: w - 1.0, h: 0.4, fontSize: 18 });
    bullets(s, c.body, { x: x + 0.3, y: y + 0.9, w: w - 0.6, h: h - 1.1, fontSize: 14 });
  });
  s.addNotes("세 칸: 질문, 답, 제안. 답의 핵심은 '2축'이 제어가능성 명제라는 것.");
}

// =====================================================================
pres.addSection({ title: "왜 안 되는가" });

// ---- 3. 질문 분해 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "왜 안 되는가" });
  s.addText("\"주차 일반화\"는 세 종류의 일반화가 섞인 질문이다", { placeholder: "title" });
  const y = 1.55, h = 4.3, w = (W - 2 * M - 0.8) / 3;
  const cols = [
    { head: "의미 일반화", sub: "무엇을 · 어느 것을", kind: "in", tagText: "VLA가 넓히는 축",
      body: ["처음 보는 물체, 처음 듣는 표현을 사전학습 VLM 지식으로 잇는다", "RT-2: \"멸종한 동물\" → 공룡 장난감 (로봇 데이터에 공룡 없음)", "주차에서는 \"저 두 차 사이\"를 고르는 부분"] },
    { head: "조합 일반화", sub: "배운 기동을 새 순서로", kind: "out", tagText: "문헌: 대부분 실패",
      body: ["차선변경 + 장애물 사이 정지 = 전진 사선 주차", "LIBERO-PRO: 물체 위치만 바꿔도 π0·OpenVLA 0 %, π0.5 96.9 → 39.7 %", "ACT-VLA: 조합 OOD 35.5 % → 합성 조합 시연을 넣어야 88.2 %"] },
    { head: "새 동작 일반화", sub: "시연에 없던 궤적", kind: "out", tagText: "문헌: 안 됨",
      body: ["저속 대조향, 정확한 지점 정지, 후진", "RT-2 저자: 운동 스킬은 로봇 데이터 분포 안에 머문다", "우리 액션 공간은 전진 속도 티어뿐 → 후진은 일반화가 아니라 표현 불가"] },
  ];
  cols.forEach((c, i) => {
    const x = M + i * (w + 0.4);
    card(s, x, y, w, h);
    heading(s, c.head, { x: x + 0.3, y: y + 0.25, w: w - 0.6, h: 0.4, fontSize: 18 });
    txt(s, c.sub, { x: x + 0.3, y: y + 0.68, w: w - 0.6, h: 0.3, fontSize: 12, color: C.accent4, italic: true });
    tag(s, x + 0.3, y + 1.05, c.tagText, c.kind, 1.9);
    bullets(s, c.body, { x: x + 0.3, y: y + 1.55, w: w - 0.6, h: h - 1.8, fontSize: 14 });
  });
  card(s, M, 6.1, W - 2 * M, 0.7, { fill: C.text1 });
  txt(s, "교수님 질문에서 실제로 \"일반화\"가 작동할 수 있는 부분은 의미 축 하나다. 나머지 둘은 시연 데이터가 능력의 경계다.", { x: M + 0.3, y: 6.1, w: W - 2 * M - 0.6, h: 0.7, fontSize: 14, bold: true, color: C.background1, valign: "middle" });
  s.addNotes("일반화를 세 축으로 나눠 설명. 교수님은 세 축을 하나로 묶어 물으셨다. 문헌 수치: LIBERO-PRO(2510.03827), ACT-VLA(2607.00351), RT-2(2307.15818).");
}

// ---- 4. 2축이면 왜 안 되나 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "왜 안 되는가" });
  s.addText("\"2축뿐인데 왜 안 되나\" — 플래너와 모방학습 정책은 다른 문제를 푼다", { placeholder: "title" });
  const y = 1.55, h = 3.9, w = (W - 2 * M - 0.5) / 2;
  const cols = [
    { head: "오라클 주행기 (policy_node.py)", kind: "in", tagText: "처음 보는 자리도 주차", rows: [
      ["입력", "목표 자세 + 자차 위치·방향"],
      ["내부 모델", "자전거 운동학 (yaw_rate = v·tanδ / L)"],
      ["방법", "기하 계산 + 목표 역산 (후진 진입 판단 포함)"],
      ["새 자리", "식이 같으니 어디서든 성립"],
    ] },
    { head: "VLA 정책 (SmolVLA, 약 450M)", kind: "out", tagText: "본 장면·본 궤적 밖은 미정의", rows: [
      ["입력", "카메라 픽셀 + 문장 (좌표·목표 없음)"],
      ["내부 모델", "없음 — 관측 → 행동 반사"],
      ["방법", "시연에서 본 (장면, 궤적) 짝을 재현"],
      ["새 자리", "외삽이 아니라 임의 출력"],
    ] },
  ];
  cols.forEach((c, i) => {
    const x = M + i * (w + 0.5);
    card(s, x, y, w, h);
    heading(s, c.head, { x: x + 0.3, y: y + 0.25, w: w - 0.6, h: 0.4, fontSize: 17 });
    tag(s, x + 0.3, y + 0.75, c.tagText, c.kind, 2.6);
    const rows = c.rows.map(r => [td(r[0], { bold: true, color: THEME.colors.dk1 }), td(r[1])]);
    s.addTable(rows, tableOpts({ x: x + 0.3, y: y + 1.3, w: w - 0.6, colW: [1.3, w - 1.9], rowH: 0.55, fontSize: 13, border: { type: "none" }, fill: { color: THEME.colors.lt2 } }));
  });
  card(s, M, 5.7, W - 2 * M, 1.1, { fill: C.text1 });
  txt(s, "\"2축이라 쉽다\"는 차가 그 기동을 물리적으로 할 수 있다는 말이고, 그것은 맞다. 모방학습 정책의 난이도는 출력이 몇 축인지가 아니라, 관측이 학습 분포 안에 있는지와 요구되는 궤적 모양이 시연 분포 안에 있는지로 정해진다.", { x: M + 0.3, y: 5.75, w: W - 2 * M - 0.6, h: 1.0, fontSize: 14, bold: true, color: C.background1, valign: "middle" });
  s.addNotes("고속도로만 탄 사람이 처음 주차를 해내는 건 머릿속에서 차 기하를 시뮬레이션하기 때문. 이 모델엔 그 시뮬레이터가 없다. 오라클 주행기는 src/sant_vla_pkg/sant_vla_pkg/policy_node.py의 direct_reverse 로직.");
}

// ---- 5. 네 가지 이유 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "왜 안 되는가" });
  s.addText("학습 없이 주차가 안 되는 네 가지 이유", { placeholder: "title" });
  const items = [
    { n: 1, head: "입력이 분포 밖이다", body: "차 두 대 사이로 코를 들이민 장면, 범퍼 앞 1 m에 차체가 꽉 찬 장면은 학습 이미지에 없다. 정책은 본 장면 근처에서만 정의된다. 실측: 학습한 박스조차 폐루프에서 충돌 (r29~r32)." },
    { n: 2, head: "출력은 숫자 2개가 아니라 5초 궤적의 모양이다", body: "정책은 10 Hz 청크로 (속도, 요각 변화) 50 스텝을 내고 브리지가 경로로 적분한다. 주행 궤적 = 작은 곡률 + 순항, 주차 궤적 = 저속 대조향 + 지점 정지. 정지조차 규칙이 아니라 시연의 감속 램프에서 배운 행동이다." },
    { n: 3, head: "\"저 사이로\"가 행동에 닿을 통로가 없다", body: "ParkingE2E도 목표 슬롯 좌표를 명시 입력으로 받는다. 우리 정책의 유일한 목표 입력은 문장인데, 문장 유무로 행동이 구별되지 않았다 (b1 22/42 vs b0 23/42, n=42)." },
    { n: 4, head: "운동학도 탐색도 없고, 오차는 복리로 쌓인다", body: "모델 안에 차 기하도 \"이렇게 틀면 어디로 가나\"를 따져 볼 장치도 없다. 주차는 좁아지는 공간으로 들어가므로 첫 오차가 더 생소한 상태로 밀어 넣고, 복구 시연이 없다." },
  ];
  const w = (W - 2 * M - 0.4) / 2, h = 2.45;
  items.forEach((it, i) => {
    const x = M + (i % 2) * (w + 0.4), y = 1.5 + Math.floor(i / 2) * (h + 0.3);
    card(s, x, y, w, h);
    numCircle(s, x + 0.3, y + 0.3, it.n, i < 2 ? C.accent1 : C.accent5);
    heading(s, it.head, { x: x + 0.95, y: y + 0.3, w: w - 1.25, h: 0.5, fontSize: 16, valign: "middle" });
    txt(s, it.body, { x: x + 0.3, y: y + 0.95, w: w - 0.6, h: h - 1.1, fontSize: 14 });
  });
  s.addNotes("브리지 주석(vla_bridge_node.py): 'Stopping at a goal is not a rule here — it has to be learned behaviour, present in the demonstrations as a deceleration ramp.'");
}

// ---- 6. 오차 복리 그림 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "왜 안 되는가" });
  s.addText("한 번 벗어나면 본 적 없는 장면이 이어진다 — 주차가 바로 그 조건이다", { placeholder: "title" });
  const iw = 7.9, ih = iw * 874 / 2319;
  s.addImage({ path: "04_compounding_error.png", x: M, y: 1.6, w: iw, h: ih, objectName: "오차 복리 그림" });
  txt(s, "행동복제의 누적 오차 상한 O(εT²) vs DAgger O(εT). 그림은 ε = 0.02 예시.", { x: M, y: 1.6 + ih + 0.1, w: iw, h: 0.4, fontSize: 11, color: C.accent4 });
  {
    const cy = 1.6 + ih + 0.65, cw = (iw - 0.3) / 2;
    card(s, M, cy, cw, 1.0, { fill: C.accent2 });
    txt(s, "주행 중", { x: M + 0.25, y: cy + 0.12, w: cw - 0.5, h: 0.3, fontSize: 12, bold: true, color: C.background1 });
    txt(s, "차선 폭만큼 여유. 교사 데이터가 있는 띠가 넓다", { x: M + 0.25, y: cy + 0.45, w: cw - 0.5, h: 0.5, fontSize: 12, color: C.background1 });
    card(s, M + cw + 0.3, cy, cw, 1.0, { fill: C.accent1 });
    txt(s, "주차 중", { x: M + cw + 0.55, y: cy + 0.12, w: cw - 0.5, h: 0.3, fontSize: 12, bold: true, color: C.background1 });
    txt(s, "차체 좌우 수십 cm. 띠가 얇아 첫 오차가 곧 분포 밖", { x: M + cw + 0.55, y: cy + 0.45, w: cw - 0.5, h: 0.5, fontSize: 12, color: C.background1 });
  }
  const x = M + iw + 0.4, w = W - M - x;
  card(s, x, 1.6, w, 4.5);
  heading(s, "주차에서 특히 나쁜 이유", { x: x + 0.3, y: 1.85, w: w - 0.6, h: 0.4 });
  bullets(s, [
    "공간이 좁아질수록 \"교사 데이터가 있는 띠\"가 얇아진다. 주행 중엔 차선 폭만큼 여유가 있지만 차 사이에서는 수십 cm다",
    "첫 오차 뒤의 장면(차체가 비스듬히 가까이 보이는 화면)은 시연에 0건이라 복구 행동을 배운 적이 없다",
    "청크 커밋 구간은 개루프다. 추론 지연 때문에 수 초 단위로 시각 보정 없이 실행되므로 좁은 공간에서 오차가 바로 접촉으로 이어진다",
    "우리 폐루프 회피 실측에서도 횡 이동 0.1~0.3 m에서 박스에 접촉했다 (r33~r35)",
  ], { x: x + 0.3, y: 2.35, w: w - 0.6, h: 3.6, fontSize: 13 });
  s.addNotes("그림: docs/study/figures/04_compounding_error.png (DAgger 비교 예시). 청크 커밋 개루프 문제는 generalization_limits_and_questions.md 4절.");
}

// =====================================================================
pres.addSection({ title: "우리 트랙 실측" });

// ---- 7. 실측 1: 회피 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "우리 트랙 실측" });
  s.addText("실측 1 — 회피: 학습한 박스조차 폐루프에서 피하지 못했다", { placeholder: "title" });
  const rows = [
    [th("런"), th("시연 형태"), th("장애물 고유 반응 (반사실)"), th("비교 기준"), th("폐루프")],
    [td("r29~r32"), td("장애물 앞 정지 시연 (가중·sampler·강한 제동 변형)"), td("−0.04 m — 반응 없음", { color: THEME.colors.accent5, bold: true }), td("—"), td("충돌, 제동 없음")],
    [td("r33~r35"), td("8 m 앞에서 바로 차선변경 (packed_swerve 72 ep)"), td("0.5 m (8~11 m 구간)"), td("시연 1.36 m → 약 35 %"), td("충돌, 횡 0.1~0.3 m")],
    [td("r46"), td("같은 자리 직진 짝 시연 137쌍"), td("+0.14 ~ 0.27 m"), td("차선변경 1.8 m"), td("회피 0/20")],
    [td("r47"), td("짝 286쌍 · 물체 5종으로 확대"), td("+0.14 m — 줄어듦", { color: THEME.colors.accent5, bold: true }), td("빈 차선 쏠림 +1.10 m"), td("—")],
  ];
  s.addTable(rows, tableOpts({ x: M, y: 1.5, w: 8.1, colW: [0.9, 2.7, 1.9, 1.4, 1.2], rowH: 0.62 }));
  txt(s, "반사실 = 같은 차량 상태에서 빈 차선 프레임과 장애물 프레임의 예측 경로 차이. 스텝 2배·부스트 2배·순항 제거 모두 같은 천장.", { x: M, y: 4.75, w: 8.1, h: 0.6, fontSize: 11, color: C.accent4 });
  const x = M + 8.1 + 0.4, w = W - M - x;
  card(s, x, 1.5, w, 2.3, { fill: C.text1 });
  txt(s, "0.35 ×", { x: x + 0.3, y: 1.6, w: w - 0.6, h: 1.1, fontSize: 54, bold: true, color: C.accent1, valign: "middle" });
  txt(s, "시연 횡이동 대비 정책 반응의 천장 (r33~r35). 주차는 이보다 큰 횡이동과 정지의 조합을 요구한다.", { x: x + 0.3, y: 2.7, w: w - 0.6, h: 1.0, fontSize: 12, color: C.background2 });
  card(s, x, 4.0, w, 2.7);
  heading(s, "함의", { x: x + 0.3, y: 4.2, w: w - 0.6, h: 0.4 });
  bullets(s, [
    "회피가 폐루프로 안 되는 모델 위에 \"차량 사이 진입\"을 기대하는 것은 기각선이 이미 넘어간 실험이다",
    "가중치·시연 강도·노출·혼합은 원인이 아니었고, 시연 형태만 효과가 있었다",
  ], { x: x + 0.3, y: 4.65, w: w - 0.6, h: 2.0, fontSize: 13 });
  s.addNotes("출처: multiobj-avoidance-holdout 기록(2026-09-22~28), 회피 모델 종합표(20261002_1354). r44: 빈 차선에서도 같은 자리에서 꺾음 = 트랙 자리 기억.");
}

// ---- 8. 실측 2: 언어 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "우리 트랙 실측" });
  s.addText("실측 2 — 언어: 문장을 상수로 바꿔도 행동이 같다", { placeholder: "title" });
  const iw = 7.6, ih = iw * 1300 / 2439;
  s.addImage({ path: "probe_across_runs.png", x: M, y: 1.5, w: iw, h: ih, objectName: "언어 반사실 프로브" });
  txt(s, "같은 화면·상태·노이즈에서 문장만 바꿨을 때 지시한 쪽으로 기운 비율(우연 50 %)과 경로 차이 크기 / 시연 차이. 빗금 = 문장 학습 없는 대조군.", { x: M, y: 1.5 + ih + 0.1, w: iw, h: 0.6, fontSize: 11, color: C.accent4 });
  const x = M + iw + 0.4, w = W - M - x;
  card(s, x, 1.5, w, 5.2);
  heading(s, "읽는 법", { x: x + 0.3, y: 1.7, w: w - 0.6, h: 0.4 });
  bullets(s, [
    "이름 문장 b1 22/42 vs 상수 문장 b0 23/42 (n=42). b0는 문장을 본 적이 없으므로 23/42가 노이즈 하한이고, b1은 정확히 그 위에 있다",
    "방향 단어로 바꾸면(r52) 오프라인 34/42로 방향은 맞추지만 반응 크기가 시연의 0.09 배라 폐루프 결과를 못 바꾼다",
    "섹터 학습 s1은 대조군 s0·베이스 r26과 같다(49·50·49 /55). 방향 반응은 차선 주행 때 이미 배운 것",
    "데이터 자체엔 문장 정보가 있다(CMI 0.743 bit). 모델이 그것을 쓸 이유를 학습 목표가 주지 않았다",
  ], { x: x + 0.3, y: 2.2, w: w - 0.6, h: 4.4, fontSize: 12.5 });
  s.addNotes("그림: docs/experiments/reports/figures/probe_across_runs.png. 주차 질문과의 연결: '저 사이로'라는 목표가 행동에 닿는 유일한 통로가 문장인데 그 통로가 닫혀 있다.");
}

// ---- 9. 실측 3: 더 모으면 된다? ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "우리 트랙 실측" });
  s.addText("실측 3 — \"데이터를 더 모으면 붙는다\"는 한 번도 관측되지 않았다", { placeholder: "title" });
  const rows = [
    [th("데이터를 늘리거나 바꾼 실험"), th("고유 반응 (대조군과의 차이)"), th("대조군 쪽 변화")],
    [td("회피 스윕, 박스 5 → 80개 (10-01)"), td("+0.5 ~ 0.7 m에 머묾"), td("빈 차선 위치 습관이 2.3 m로 커짐")],
    [td("r46 → r47, 짝 137 → 286, 물체 5종 (10-03)"), td("+0.27 → +0.14 m로 줄어듦", { color: THEME.colors.accent5, bold: true }), td("빈 차선 쏠림 +0.42 → +1.10 m")],
    [td("r43, 같은 자리 직진 짝 (10-02)"), td("회피 3/97"), td("빈 차선 꺾음 0/100 — 습관과 함께 회피도 사라짐")],
    [td("g1 이름 문장 b1 vs 상수 b0 (10-07)"), td("22/42 vs 23/42 — 차이 없음"), td("—")],
    [td("섹터 본 수집 s1 vs s0 vs r26 (10-08)"), td("49 vs 50 vs 49 /55 — 차이 없음"), td("폐루프 s1 8/30, 오른쪽 20/30")],
  ];
  s.addTable(rows, tableOpts({ x: M, y: 1.5, w: W - 2 * M, colW: [4.0, 3.6, 4.53], rowH: 0.55 }));
  const y = 5.05;
  card(s, M, y, 5.9, 1.7, { fill: C.text1 });
  heading(s, "관측된 패턴", { x: M + 0.3, y: y + 0.15, w: 5.3, h: 0.35, color: C.background1 });
  txt(s, "고유 반응은 그대로거나 줄고, 장애물·문장과 무관한 쏠림(화면 자리·방향 사전확률)이 커진다. 손실을 줄이는 가장 싼 길이 지름길이면 모델은 그 길로 간다.", { x: M + 0.3, y: y + 0.55, w: 5.3, h: 1.1, fontSize: 12.5, color: C.background2 });
  card(s, M + 6.2, y, W - 2 * M - 6.2, 1.7);
  heading(s, "그래서 사전 기각선을 먼저 적는다", { x: M + 6.5, y: y + 0.15, w: 5.6, h: 0.35 });
  txt(s, "같은 설정에서 N/4 · N/2 · N을 b1/b0 짝으로 재고, 가장 큰 N에서 b1 < 27/42 이거나 b1 − b0가 시드 차이보다 크지 않거나 N에 따른 추세가 없으면 \"더 모으기\"는 근거 없음으로 기각. 주차 실험도 같은 규칙을 적용한다.", { x: M + 6.5, y: y + 0.55, w: 5.6, h: 1.1, fontSize: 12 });
  s.addNotes("출처: 연구 경과 보고서 7.1절. 단서: 시험한 규모는 g1 185,635 프레임까지이므로 '충분히 크면 된다'가 엄밀히 반증된 것은 아니다. 그래서 기각선을 둔다.");
}

// =====================================================================
pres.addSection({ title: "문헌" });

// ---- 10. 문헌 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "문헌" });
  s.addText("문헌도 같은 방향을 가리킨다", { placeholder: "title" });
  const rows = [
    [th("논문"), th("설정"), th("결과"), th("우리 질문에 대한 함의")],
    [td("RT-2 (CoRL 2023)"), td("웹 지식 + 로봇 시연"), td("새 물체·새 표현은 되지만 새 운동 스킬은 생기지 않는다고 저자가 명시"), td("의미 축만 넓어진다")],
    [td("LIBERO-PRO (2025)"), td("물체 위치·지시문·환경 교란"), td("표준 96.9 %인 π0.5가 위치 교란 39.7 %, 지시문 교란 30.1 %. OpenVLA·π0는 0 %"), td("높은 점수는 배치 기억일 수 있다")],
    [td("ACT-VLA (2026)"), td("같은 서브스킬의 새 조합"), td("조합 OOD 35.5 % → 합성 조합 시연 학습 후 88.2 %"), td("조합은 '일반화'가 아니라 학습이 필요")],
    [td("AGNOSTOS (NeurIPS 2025)"), td("23개 미학습 조작 과제"), td("현행 VLA 전부 저조. 시연을 문맥에 넣는 X-ICM이 π0보다 +6.0 %p"), td("미학습 과제 제로샷은 분야 미해결")],
    [td("INT-ACT (2025)"), td("의도 정확도 vs 실행 성공률"), td("의도 80~100 %인데 실행은 분포 이동에서 무너짐"), td("\"무엇을\"은 알아도 \"어떻게\"가 실패")],
    [td("ParkingE2E (IROS 2024) · E2E Parking Dataset (2025)"), td("주차 전용 E2E"), td("실차 4곳 87.8 % · CARLA 85.2 %. 둘 다 목표 슬롯 입력 + 주차 데이터 학습"), td("주차는 주차 데이터와 목표 입력으로 푼다")],
    [td("SimLingo (CVPR 2025) · AutoVLA · OpenDriveVLA"), td("주행 VLA, Bench2Drive"), td("날씨·물체·명령 표현 축의 일반화. 새 기동 축은 평가 대상 아님"), td("주행 VLA도 새 기동은 주장하지 않는다")],
  ];
  s.addTable(rows, tableOpts({ x: M, y: 1.45, w: W - 2 * M, colW: [2.5, 2.3, 4.3, 3.03], rowH: 0.6, fontSize: 11.5 }));
  txt(s, "일반주행 데이터에서 주차가 창발했다는 논문은 찾지 못했다. 논문 식별자는 마지막 장.", { x: M, y: 6.6, w: W - 2 * M, h: 0.35, fontSize: 11, color: C.accent4 });
  s.addNotes("각 논문의 arXiv 번호는 참고문헌 슬라이드. ACT-VLA 수치는 LIBERO-Spatial-OOD 기준.");
}

// =====================================================================
pres.addSection({ title: "실습 제안" });

// ---- 11. 일반화 사다리 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "실습 제안" });
  s.addText("\"학습하지 않은 상황\" 사다리 — 동작은 분포 안에, 상황은 분포 밖에", { placeholder: "title" });
  const rows = [
    { n: "L1", head: "미학습 물체 · 표현", kind: "in", tagText: "동작 분포 안", ex: "공룡 앞 정지, \"멸종한 생물로 가\"", pred: "문헌상 가장 가능성 높음 (의미 축). 현재 goto 기준선·s3 학습이 이 축", stat: "진행 중" },
    { n: "L2", head: "미학습 배치", kind: "in", tagText: "동작 분포 안", ex: "학습 띠 밖 출발 위치, 횡오차 주입", pred: "실물 트랙 조건상 필수. 배치 띠 안/밖 따로 집계", stat: "수집 확대 필요" },
    { n: "L3", head: "미학습 조합", kind: "out", tagText: "조합 분포 밖", ex: "\"오른쪽으로 바꾸고 물체 앞에 서\" (각각만 학습)", pred: "교수님 질문의 정직한 버전. 문헌은 실패를 예측 → 경계 수업", stat: "회피 폐루프 선행" },
    { n: "L4", head: "미학습 동작 (주차)", kind: "out", tagText: "동작 분포 밖", ex: "두 박스 사이 전진 사선 진입 후 정지", pred: "실패 확인 → 시연 10·20·40개 추가 → 성공률 곡선 (few-shot 전이)", stat: "오라클 주차 경로 필요" },
  ];
  const y0 = 1.5, rh = 1.1, gap = 0.12;
  rows.forEach((r, i) => {
    const y = y0 + i * (rh + gap);
    card(s, M, y, W - 2 * M, rh);
    numCircle(s, M + 0.25, y + 0.35, r.n, r.kind === "in" ? C.accent2 : C.accent1);
    heading(s, r.head, { x: M + 0.95, y: y + 0.2, w: 2.6, h: 0.4, fontSize: 15 });
    tag(s, M + 0.95, y + 0.65, r.tagText, r.kind, 1.5);
    txt(s, "예: " + r.ex, { x: M + 3.8, y: y + 0.2, w: 3.6, h: 0.85, fontSize: 12.5 });
    txt(s, r.pred, { x: M + 7.6, y: y + 0.2, w: 3.5, h: 0.85, fontSize: 12.5 });
    txt(s, r.stat, { x: M + 11.25, y: y + 0.2, w: 0.9, h: 0.85, fontSize: 11, color: C.accent4, italic: true });
  });
  txt(s, "VLA가 실제로 일반화하는 축은 의미와 시각이고, 운동은 아니다. L1·L2는 강점 수업, L3·L4는 경계 수업으로 역할을 나눈다.", { x: M, y: 6.45, w: W - 2 * M, h: 0.35, fontSize: 12, color: C.accent4 });
  s.addNotes("10-03 교수님 방향(말로 지정한 물체로 가기)은 L1. 10-09 주차 질문은 L3·L4. 둘 다 한 사다리 안에 넣어 설명한다.");
}

// ---- 12. 실습 두 가지 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "실습 제안" });
  s.addText("실습 제안 — 경계를 학생이 직접 재게 한다", { placeholder: "title" });
  const w = (W - 2 * M - 0.4) / 2, y = 1.5, h = 5.2;
  // left: gap sweep
  {
    const x = M;
    card(s, x, y, w, h);
    heading(s, "① 간격 폭 스윕 — 분포 경계 측정", { x: x + 0.3, y: y + 0.25, w: w - 0.6, h: 0.4, fontSize: 17 });
    // diagram: three gap scenes
    const scenes = [
      { label: "차선 폭", sub: "직진 후 정지 = 분포 안", kind: "in", gap: 1.3 },
      { label: "중간", sub: "약간 꺾어야 함", kind: "mid", gap: 0.8 },
      { label: "좁음", sub: "사선 진입 = 분포 밖", kind: "out", gap: 0.4 },
    ];
    const sw = (w - 0.6 - 0.4) / 3, sy = y + 0.85, sh = 1.9;
    scenes.forEach((sc, i) => {
      const sx = x + 0.3 + i * (sw + 0.2);
      s.addShape(pres.ShapeType.rect, { x: sx, y: sy, w: sw, h: sh, fill: { color: THEME.colors.lt1 }, line: { color: "D5DAE0", width: 0.75 }, objectName: "scene" });
      const col = sc.kind === "in" ? C.accent2 : sc.kind === "out" ? C.accent1 : C.accent3;
      const bw = (sw - sc.gap) / 2 - 0.1;
      s.addShape(pres.ShapeType.rect, { x: sx + 0.1, y: sy + 0.25, w: bw, h: 0.7, fill: { color: C.accent4 }, line: { color: C.accent4 }, objectName: "box" });
      s.addShape(pres.ShapeType.rect, { x: sx + sw - 0.1 - bw, y: sy + 0.25, w: bw, h: 0.7, fill: { color: C.accent4 }, line: { color: C.accent4 }, objectName: "box" });
      // car
      s.addShape(pres.ShapeType.roundRect, { x: sx + sw / 2 - 0.16, y: sy + 1.2, w: 0.32, h: 0.5, rectRadius: 0.08, fill: { color: col }, line: { color: col }, objectName: "car" });
      s.addShape(pres.ShapeType.line, { x: sx + sw / 2, y: sy + 0.95, w: 0, h: 0.25, line: { color: col, width: 1.5, dashType: "dash", endArrowType: "triangle" }, objectName: "arrow" });
      txt(s, sc.label, { x: sx, y: sy + sh + 0.05, w: sw, h: 0.3, fontSize: 12, bold: true, align: "center", color: C.text1 });
      txt(s, sc.sub, { x: sx, y: sy + sh + 0.33, w: sw, h: 0.3, fontSize: 10.5, align: "center", color: col });
    });
    bullets(s, [
      "두 박스 사이 간격을 차선 폭에서 시작해 단계적으로 좁힌다. 측정값은 간격별 무충돌 진입률 (N회 반복, 빈 차선 대조군 포함)",
      "넓을 때는 \"직진 후 정지\"라 학습 분포 안이고, 사선 진입이 필요해지는 폭부터 분포 밖이다. 성공률이 꺾이는 폭이 곧 데이터 분포의 경계",
      "결과가 어느 쪽이든 수업이 된다: \"일반화 경계는 데이터 분포 경계와 일치한다\"",
    ], { x: x + 0.3, y: sy + sh + 0.75, w: w - 0.6, h: h - (sy - y) - sh - 0.9, fontSize: 12 });
  }
  // right: hierarchy
  {
    const x = M + w + 0.4;
    card(s, x, y, w, h);
    heading(s, "② 계층 분해 — 미학습 상황을 학습한 기동의 열로", { x: x + 0.3, y: y + 0.25, w: w - 0.6, h: 0.4, fontSize: 17 });
    const bx = x + 0.3, bw = w - 0.6;
    const steps = [
      { t: "\"저 두 차 사이에 세워\"", sub: "미학습 상황 · 자연어", col: C.accent4 },
      { t: "VLM (Qwen2.5-VL 7B) 이 분해", sub: "\"오른쪽 차선변경 → 박스 앞 정지\"", col: C.accent6 },
      { t: "VLA (SmolVLA) 가 실행", sub: "각 기동은 시연 분포 안", col: C.accent2 },
    ];
    steps.forEach((st, i) => {
      const by = y + 0.85 + i * 0.95;
      s.addShape(pres.ShapeType.roundRect, { x: bx, y: by, w: bw, h: 0.72, rectRadius: 0.1, fill: { color: st.col }, line: { color: st.col }, objectName: "step" });
      txt(s, st.t, { x: bx + 0.2, y: by + 0.06, w: bw - 0.4, h: 0.32, fontSize: 13, bold: true, color: C.background1 });
      txt(s, st.sub, { x: bx + 0.2, y: by + 0.38, w: bw - 0.4, h: 0.3, fontSize: 11, color: C.background1 });
      if (i < steps.length - 1) s.addShape(pres.ShapeType.line, { x: bx + bw / 2, y: by + 0.72, w: 0, h: 0.23, line: { color: C.accent4, width: 1.5, endArrowType: "triangle" }, objectName: "arrow" });
    });
    bullets(s, [
      "10-08 구조 결정과 같다: 인지는 VLM, 이동은 VLA. 규칙 주행기로 대체하지 않는다",
      "SayCan 계열이 말하는 \"미학습 상황 처리\"가 이것이다. 동작이 분포 안이므로 성공 가능성이 있다",
      "전제조건: 폐루프 회피(차선변경 후 정지)가 먼저 붙어야 한다. 지금은 충돌한다",
    ], { x: bx, y: y + 3.75, w: bw, h: 1.4, fontSize: 12 });
  }
  s.addNotes("①은 학생이 직접 측정하는 실습, ②는 VLA 고유성을 보여 주는 구조. ②는 10-08 결정(인지 VLM·이동 VLA)과 일치.");
}

// ---- 13. 교수님께 드리는 답 + 다음 단계 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "실습 제안" });
  s.addText("정리 — 교수님께 드리는 답과 다음 단계", { placeholder: "title" });
  card(s, M, 1.5, W - 2 * M, 1.45, { fill: C.text1 });
  txt(s, "\"2축이라 쉬운 건 플래너 입장입니다. 모방학습 정책은 본 장면과 본 궤적 밖에서는 정의되지 않습니다. 그래서 주차는 안 되는 것을 먼저 측정하고, 미학습 물체 → 배치 → 조합 순서로 어디까지 되는지를 실습으로 보이겠습니다.\"", { x: M + 0.35, y: 1.6, w: W - 2 * M - 0.7, h: 1.25, fontSize: 15, bold: true, color: C.background1, valign: "middle" });
  const rows = [
    [th("항목"), th("값")],
    [td("설정"), td("s3 계열(stock SmolVLA base) 위 학습. r26 위 재학습은 방향 반응을 파괴한 전례(0.82 → 0.04)가 있어 쓰지 않음")],
    [td("대조군"), td("빈 차선 동일 명령 · 상수 문장 Drive. · 베이스 모델, 모든 조건에서 같이 측정")],
    [td("측정"), td("간격별 무충돌 진입률, 언어 반사실 프로브(n=42), 배치 띠 안/밖 별도 집계")],
    [td("기각"), td("주차 0-shot: 성공률이 빈 차선 대조군과 구별되지 않으면 \"학습 없이 주차\"는 기각 (예상). 추가 시연 곡선: 40 ep에서도 대조군과 같으면 few-shot 전이 주장도 기각")],
    [td("기각되면"), td("수집량 증가로 가지 않는다. 학습 목표·구조(VLM 분해 경로, 대조 손실)로 간다")],
  ];
  s.addTable(rows, tableOpts({ x: M, y: 3.15, w: 8.3, colW: [1.2, 7.1], rowH: 0.52, fontSize: 11.5 }));
  const x = M + 8.3 + 0.4, w = W - M - x;
  card(s, x, 3.15, w, 3.55);
  heading(s, "일정과 제약", { x: x + 0.3, y: 3.35, w: w - 0.6, h: 0.4 });
  bullets(s, [
    "시뮬 작업 마감 10-16. 이후 실물 트랙 테스트·영상 촬영, 강좌는 12월",
    "필요한 것: route_oracle 전진 주차 경로, 주차 차량 자산(박스 대체 가능)",
    "후진은 넣지 않는다. 액션 공간 밖",
    "실물 트랙은 출발 위치·배치를 고정할 수 없다",
  ], { x: x + 0.3, y: 3.8, w: w - 0.6, h: 2.8, fontSize: 12.5 });
  s.addNotes("기각선은 결과를 본 뒤 바꾸지 않는다. 사전 기각선 규칙(10-08 사용자 지시).");
}

// ---- 14. 참고문헌 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "실습 제안" });
  s.addText("참고문헌", { placeholder: "title" });
  const refs = [
    "Zitkovich et al., RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control. CoRL 2023. arXiv:2307.15818",
    "LIBERO-PRO: Towards Robust and Fair Evaluation of Vision-Language-Action Models Beyond Memorization. 2025. arXiv:2510.03827",
    "Unleashing More Actions via Action Compositional Training for VLA Models (ACT-VLA). 2026. arXiv:2607.00351",
    "Zhou et al., Exploring the Limits of Vision-Language-Action Manipulation in Cross-task Generalization (AGNOSTOS). NeurIPS 2025. arXiv:2505.15660",
    "Fang et al., From Intention to Execution: Probing the Generalization Boundaries of Vision-Language-Action Models (INT-ACT). 2025. arXiv:2506.09930",
    "Li et al., ParkingE2E: Camera-based End-to-end Parking Network, from Images to Planning. IROS 2024. arXiv:2408.02061",
    "Gao et al., E2E Parking Dataset: An Open Benchmark for End-to-End Autonomous Parking. 2025. arXiv:2504.10812",
    "Renz et al., SimLingo: Vision-Only Closed-Loop Autonomous Driving with Language-Action Alignment. CVPR 2025",
    "Zhou et al., AutoVLA: A Vision-Language-Action Model for End-to-End Autonomous Driving. 2025. arXiv:2506.13757",
    "Vision-Language-Action Models for Autonomous Driving: Past, Present, and Future (survey). arXiv:2512.16760",
    "Fail2Drive: Benchmarking Closed-Loop Driving Generalization. 2026. arXiv:2604.08535",
    "Ross, Gordon, Bagnell. A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning (DAgger). AISTATS 2011",
  ];
  const arr = refs.map((t, i) => ({ text: `[${i + 1}] ${t}`, options: { breakLine: i < refs.length - 1, paraSpaceAfter: 6 } }));
  s.addText(arr, { x: M, y: 1.45, w: W - 2 * M, h: 5.2, fontSize: 12, color: C.text2, margin: 0, isTextBox: true, valign: "top", objectName: "refs" });
  txt(s, "내부 자료: docs/experiments/reports/research_report_20261003_20261008.md · docs/experiments/avoidance/20261002_1354 · docs/course/학습하지않은상황_종류와_대응.md", { x: M, y: 6.6, w: W - 2 * M, h: 0.35, fontSize: 10.5, color: C.accent4 });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
