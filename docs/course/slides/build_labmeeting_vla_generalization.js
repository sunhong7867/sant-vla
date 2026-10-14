const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/home/sh/.config/Claude/local-agent-mode-sessions/skills-plugin/8963f022-f39c-4a07-9096-3d09ccd635ba/5e42d03c-c0ca-4478-a91c-80a8dd2c1b12/skills/pptx/scripts/apply_theme.js");

const OUT = process.argv[2] || "labmeeting_vla_generalization.pptx";

const THEME = {
  name: "nav-vla labmeeting",
  headFontFace: "Noto Sans CJK KR",
  bodyFontFace: "Noto Sans CJK KR",
  colors: {
    dk1: "1B2228", lt1: "FFFFFF", dk2: "3D4A54", lt2: "EEF1F3",
    accent1: "E8712B", accent2: "1A9E8C", accent3: "C9A227",
    accent4: "7A8C99", accent5: "B23A3A", accent6: "5B7FA6",
    hlink: "1A9E8C", folHlink: "7A8C99",
  },
};
const HX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "sunhong";
pres.title = "VLA 주행 정책의 일반화: 되는 것과 안 되는 것";
const C = pres.SchemeColor;
const W = 13.33, H = 7.5, M = 0.6;

pres.defineSlideMaster({
  title: "DARK",
  background: { color: HX.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.1, w: W - 2 * M, h: 1.7, fontSize: 36, bold: true, color: C.background1, valign: "bottom", margin: 0 } } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.0, w: W - 2 * M, h: 1.6, fontSize: 18, color: C.background2, valign: "top", margin: 0 } } },
  ],
});
pres.defineSlideMaster({
  title: "LIGHT",
  background: { color: HX.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.38, w: W - 2 * M, h: 0.8, fontSize: 26, bold: true, color: C.text1, valign: "middle", margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.6, y: H - 0.5, w: 0.6, h: 0.3, fontSize: 10, color: HX.accent4, align: "right" },
});
pres.defineSlideMaster({
  title: "DIVIDER",
  background: { color: HX.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.6, w: W - 2 * M, h: 1.2, fontSize: 34, bold: true, color: C.background1, valign: "bottom", margin: 0 } } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 3.95, w: W - 2 * M, h: 1.2, fontSize: 16, color: C.background2, valign: "top", margin: 0 } } },
  ],
});

// ---------- helpers ----------
function shadow() { return { type: "outer", color: HX.dk1, blur: 6, offset: 2, angle: 90, opacity: 0.12 }; }
function card(s, x, y, w, h, o = {}) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.12, fill: { color: o.fill || C.background2 }, line: { color: o.line || o.fill || C.background2, width: 0.75 }, shadow: shadow(), objectName: o.name || "card" });
}
function tag(s, x, y, text, kind, w = 1.3) {
  const color = kind === "in" ? C.accent2 : kind === "out" ? C.accent1 : kind === "warn" ? C.accent5 : kind === "blue" ? C.accent6 : kind === "amber" ? C.accent3 : C.accent4;
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h: 0.32, rectRadius: 0.16, fill: { color }, line: { color }, objectName: "tag" });
  s.addText(text, { x, y, w, h: 0.32, fontSize: 11, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "tag-text" });
}
function circ(s, x, y, n, color, d = 0.5) {
  s.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color }, line: { color }, objectName: "num" });
  s.addText(String(n), { x, y, w: d, h: d, fontSize: d >= 0.5 ? 16 : 12, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "num-text" });
}
function txt(s, text, o) { s.addText(text, Object.assign({ fontSize: 14, color: C.text2, margin: 0, isTextBox: true, valign: "top", objectName: "text" }, o)); }
function bullets(s, items, o) {
  const arr = items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 6 } }));
  s.addText(arr, Object.assign({ fontSize: 14, color: C.text2, margin: 0, isTextBox: true, valign: "top", objectName: "bullets" }, o));
}
function heading(s, text, o) { s.addText(text, Object.assign({ fontSize: 16, bold: true, color: C.text1, margin: 0, isTextBox: true, valign: "top", objectName: "heading" }, o)); }
function ref(s, text) { s.addText(text, { x: M, y: H - 0.52, w: W - 2 * M - 0.8, h: 0.36, fontSize: 9.5, color: C.accent4, margin: 0, isTextBox: true, valign: "bottom", objectName: "reference" }); }
function cap(s, text, x, y, w) { txt(s, text, { x, y, w, h: 0.35, fontSize: 10.5, color: C.accent4 }); }
function tableOpts(extra) {
  return Object.assign({ fontSize: 12, color: HX.dk2, fontFace: THEME.bodyFontFace, border: { type: "solid", color: "D5DAE0", pt: 0.5 }, valign: "middle", margin: 0.06, autoPage: false }, extra);
}
function th(t) { return { text: t, options: { bold: true, color: HX.lt1, fill: { color: HX.dk2 }, fontSize: 12 } }; }
function td(t, o) { return { text: t, options: Object.assign({ fontSize: 12 }, o || {}) }; }
function chartBase(extra) {
  return Object.assign({
    barDir: "bar", showLegend: false, showTitle: false,
    catAxisLabelColor: HX.dk2, valAxisLabelColor: HX.accent4, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 10, dataLabelFontFace: "+mn-lt", dataLabelFontSize: 11, dataLabelColor: HX.dk2,
    valGridLine: { color: "E3E7EB", size: 0.5 }, catGridLine: { style: "none" }, showValue: true, dataLabelPosition: "outEnd",
    catAxisLineShow: false, valAxisLineShow: false, legendFontFace: "+mn-lt", legendFontSize: 11, legendColor: HX.dk2,
  }, extra);
}
// small road panel used in the composition slide
function roadPanel(s, sx, sy, sw, sh, variant, col) {
  s.addShape(pres.ShapeType.rect, { x: sx, y: sy, w: sw, h: sh, fill: { color: HX.lt1 }, line: { color: "D5DAE0", width: 0.75 }, objectName: "panel" });
  s.addShape(pres.ShapeType.rect, { x: sx + 0.12, y: sy + 0.12, w: sw - 0.24, h: sh - 0.24, fill: { color: "3D4A54" }, line: { color: "3D4A54" }, objectName: "road" });
  s.addShape(pres.ShapeType.line, { x: sx + 0.12, y: sy + sh / 2, w: sw - 0.24, h: 0, line: { color: "FFFFFF", width: 1, dashType: "dash" }, objectName: "lane" });
  const carY = sy + sh * 0.62;
  s.addShape(pres.ShapeType.roundRect, { x: sx + 0.22, y: carY, w: 0.36, h: 0.2, rectRadius: 0.05, fill: { color: col }, line: { color: col }, objectName: "car" });
  const ax = sx + 0.58, ay = carY + 0.1;
  if (variant === "A") {
    s.addShape(pres.ShapeType.line, { x: ax, y: ay - sh * 0.4, w: sw - 0.95, h: sh * 0.4, line: { color: col, width: 2, endArrowType: "triangle" }, flipV: true, objectName: "arrow" });
  } else if (variant === "B") {
    s.addShape(pres.ShapeType.line, { x: ax, y: ay, w: sw - 1.25, h: 0, line: { color: col, width: 2, endArrowType: "triangle" }, objectName: "arrow" });
    s.addShape(pres.ShapeType.rect, { x: sx + sw - 0.5, y: carY - 0.05, w: 0.28, h: 0.3, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "box" });
  } else if (variant === "SEQ") {
    // lane change, then straight, then swerve around box and return
    s.addShape(pres.ShapeType.line, { x: ax, y: ay - sh * 0.36, w: sw * 0.22, h: sh * 0.36, line: { color: col, width: 2 }, flipV: true, objectName: "arrow" });
    s.addShape(pres.ShapeType.line, { x: ax + sw * 0.22, y: ay - sh * 0.36, w: sw * 0.18, h: 0, line: { color: col, width: 2 }, objectName: "arrow" });
    s.addShape(pres.ShapeType.line, { x: ax + sw * 0.40, y: ay - sh * 0.36, w: sw * 0.12, h: sh * 0.2, line: { color: col, width: 2, dashType: "dash" }, objectName: "arrow" });
    s.addShape(pres.ShapeType.line, { x: ax + sw * 0.52, y: ay - sh * 0.16, w: sw * 0.12, h: 0, line: { color: col, width: 2, dashType: "dash" }, objectName: "arrow" });
    s.addShape(pres.ShapeType.line, { x: ax + sw * 0.64, y: ay - sh * 0.36, w: sw * 0.12, h: sh * 0.2, line: { color: col, width: 2, dashType: "dash", endArrowType: "triangle" }, flipV: true, objectName: "arrow" });
    s.addShape(pres.ShapeType.rect, { x: ax + sw * 0.5, y: ay - sh * 0.36 - 0.13, w: 0.24, h: 0.24, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "box" });
  } else if (variant === "OVL") {
    s.addShape(pres.ShapeType.rect, { x: sx + sw - 0.95, y: sy + 0.18, w: 0.26, h: 0.4, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "box" });
    s.addShape(pres.ShapeType.rect, { x: sx + sw - 0.45, y: sy + 0.18, w: 0.26, h: 0.4, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "box" });
    s.addShape(pres.ShapeType.line, { x: ax, y: ay - sh * 0.42, w: sw - 1.4, h: sh * 0.42, line: { color: col, width: 2, dashType: "dash", endArrowType: "triangle" }, flipV: true, objectName: "arrow" });
  }
}

const REF = {
  rt2: "RT-2 (Zitkovich et al., CoRL 2023, arXiv:2307.15818)",
  pro: "LIBERO-PRO (2025, arXiv:2510.03827)",
  act: "ACT-VLA: Action Compositional Training (2026, arXiv:2607.00351)",
  agn: "AGNOSTOS (Zhou et al., NeurIPS 2025, arXiv:2505.15660)",
  int: "INT-ACT: From Intention to Execution (Fang et al., 2025, arXiv:2506.09930)",
  park: "ParkingE2E (Li et al., IROS 2024, arXiv:2408.02061) · E2E Parking Dataset (Gao et al., 2025, arXiv:2504.10812)",
  lin: "Data Scaling Laws in Imitation Learning for Robotic Manipulation (Lin et al., 2024, arXiv:2410.18647)",
  drvscale: "Data Scaling Laws for Imitation Learning-Based End-to-End Autonomous Driving (2024, arXiv:2412.02689)",
  fail: "Fail2Drive: Benchmarking Closed-Loop Driving Generalization (Gerstenecker, Geiger, Renz, 2026, arXiv:2604.08535)",
  simlingo: "SimLingo (Renz et al., CVPR 2025)",
  autovla: "AutoVLA (2025, arXiv:2506.13757)",
  odvla: "OpenDriveVLA (AAAI 2026)",
  drivemoe: "DriveMoE (2025, arXiv:2505.16278)",
  lingo2: "LINGO-2 (Wayve, 2024, wayve.ai/thinking/lingo-2-driving-with-language)",
  emma: "EMMA (Waymo, 2024, arXiv:2410.23262)",
  survey: "VLA Models for Autonomous Driving: Past, Present, and Future (survey, arXiv:2512.16760)",
  hirobot: "Hi Robot (Physical Intelligence, 2025, arXiv:2502.19417)",
  rth: "RT-H: Action Hierarchies Using Language (Belkhale et al., 2024, arXiv:2403.01823)",
  dagger: "DAgger (Ross, Gordon, Bagnell, AISTATS 2011)",
  rep: "docs/experiments/reports/research_report_20261003_20261008.md",
  avo: "docs/experiments/avoidance/20261002_1354_avoidance-models-summary.md · 20260922_2113_multiobj-avoidance-holdout.md",
  gen: "docs/experiments/reports/generalization_limits_and_questions.md (2026-08-06 관찰)",
  gui: "docs/experiments/goto_object/20261008_2238_gui-goto-video-review.md",
  course: "docs/course/단기강좌.md · docs/course/학습하지않은상황_종류와_대응.md",
};

// =====================================================================
pres.addSection({ title: "질문" });

// ---- 1. 제목 ----
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "질문" });
  s.addText("VLA 주행 정책의 일반화: 되는 것과 안 되는 것", { placeholder: "title" });
  s.addText("\"일반주행·차선변경·회피를 배운 정책이 주차를 할 수 있는가\"에 대한 답, 자율주행 VLA 연구와의 비교, 단기강좌 실습 설계", { placeholder: "body" });
  txt(s, "랩미팅 · 2026-10-09 · SmolVLA 주행 정책 / Gazebo 시뮬 트랙", { x: M, y: 6.4, w: 8, h: 0.4, fontSize: 12, color: C.accent4 });
  tag(s, W - M - 2.75, 6.4, "분포 안", "in", 1.3);
  tag(s, W - M - 1.3, 6.4, "분포 밖", "out", 1.3);
  s.addNotes("교수님 질문(2축뿐인데 왜 안 되나)에 대한 답. 일반화를 세 종류로 나눠 실제 사례로 답하고, 자율주행 VLA 문헌이 무엇을 재는지 비교한 뒤, 강좌 실습 설계로 연결한다.");
}

// ---- 2. 질문과 한 줄 답 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "질문" });
  s.addText("이번 주 질문과 한 줄 답", { placeholder: "title" });
  const y = 1.45, h = 3.0, w = (W - 2 * M - 0.4) / 2;
  card(s, M, y, w, h);
  s.addShape(pres.ShapeType.ellipse, { x: M + 0.3, y: y + 0.3, w: 0.28, h: 0.28, fill: { color: C.accent4 }, line: { color: C.accent4 }, objectName: "dot" });
  heading(s, "질문 (교수님)", { x: M + 0.7, y: y + 0.25, w: w - 1, h: 0.4, fontSize: 18 });
  bullets(s, [
    "이미지·명령·차량 상태로 일반주행, 차선변경, 장애물 회피를 학습한 정책이 차량 사이에 충돌 없이 들어갈 수 있는가",
    "조향과 가감속, 사실상 2축인데 안 될 이유가 있는가",
    "오라클 대신 학생 수동 주행으로 학습하면 달라지는가",
    "자율주행 VLA 연구는 이 질문에 뭐라고 하는가",
  ], { x: M + 0.3, y: y + 0.85, w: w - 0.6, h: h - 1.0, fontSize: 13.5 });
  const x2 = M + w + 0.4;
  card(s, x2, y, w, h, { fill: C.text1 });
  s.addShape(pres.ShapeType.ellipse, { x: x2 + 0.3, y: y + 0.3, w: 0.28, h: 0.28, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "dot" });
  heading(s, "답", { x: x2 + 0.7, y: y + 0.25, w: w - 1, h: 0.4, fontSize: 18, color: C.background1 });
  bullets(s, [
    "일반화는 세 종류다. 의미 축은 넓어지지만, 조합과 새 동작은 시연이 능력의 경계다. 주차는 뒤의 둘에 속한다",
    "\"2축\"은 제어가능성 명제다. 정책의 난이도는 관측과 궤적이 시연 분포 안에 있는지로 정해진다",
    "수동 주행의 다양성은 자리 외우기를 지우지만 새 동작을 만들지 않는다",
    "주행 VLA 문헌은 새 환경·물체·지시문 축을 재고, 조합·새 기동은 시험하지 않는다. 주차는 늘 주차 데이터로 푼다",
  ], { x: x2 + 0.3, y: y + 0.85, w: w - 0.6, h: h - 1.0, fontSize: 13.5, color: C.background2 });
  const sy = 4.8, sw = (W - 2 * M - 0.8) / 3;
  const stats = [
    { v: "22/42 vs 23/42", l: "이름 문장 b1 vs 상수 문장 b0 — 문장 유무로 행동이 구별되지 않음 (n=42)" },
    { v: "0.35 ×", l: "차선변경 시연 횡이동 대비 정책 반응의 천장 (r33~r35)" },
    { v: "0 / 20", l: "학습한 박스의 폐루프 회피 성공 (r46). 주차 이전에 회피가 안 붙는다" },
  ];
  stats.forEach((st, i) => {
    const x = M + i * (sw + 0.4);
    card(s, x, sy, sw, 1.9);
    txt(s, st.v, { x: x + 0.3, y: sy + 0.2, w: sw - 0.6, h: 0.8, fontSize: i === 0 ? 26 : 30, bold: true, color: C.accent1, valign: "middle" });
    txt(s, st.l, { x: x + 0.3, y: sy + 1.0, w: sw - 0.6, h: 0.8, fontSize: 11.5 });
  });
  ref(s, REF.rep + " §0, §4.7 · " + REF.avo);
  s.addNotes("세 숫자가 이번 덱의 근거. 자세한 건 실측 장.");
}

// =====================================================================
pres.addSection({ title: "일반화 세 종류" });

// ---- 3. 일반화 세 종류 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "일반화 세 종류" });
  s.addText("\"일반화\"는 한 가지가 아니다 — 세 종류와 가르는 기준", { placeholder: "title" });
  const y = 1.45, h = 4.75, w = (W - 2 * M - 0.8) / 3;
  const cols = [
    { head: "① 의미 일반화", sub: "같은 동작을 새 대상에게", kind: "in", tagText: "사전학습 VLM이 넓힌다", ico: "V·L",
      rows: [["새로운 것", "대상. 처음 보는 물체, 처음 듣는 표현"], ["문헌 시험", "RT-2: \"멸종한 동물을 집어\" → 공룡 장난감. 로봇 데이터엔 공룡이 없었다"], ["우리 트랙", "\"삼각형 모양의 물체로 가줘\" → VLM이 파란 꼬깔로 해석 (5장)"], ["궤적", "접근·정지 그대로 → 시연 안"]] },
    { head: "② 조합 일반화", sub: "배운 동작들을 새 순서로", kind: "amber", tagText: "조합 시연 없이는 실패, 넣으면 회복", ico: "A+B",
      rows: [["새로운 것", "순서와 이음새. 조각은 다 봤다"], ["문헌 시험", "ACT-VLA: 학습에 없는 (물체, 위치) 짝만 시험 → 35.5 %, 조합 시연 추가 → 88.2 %"], ["우리 트랙", "순차: 2차선 이동 후 회피·복귀. 중첩: 꺾으면서 틈에 맞춰 서기 = 사선 주차 (6장)"], ["궤적", "조각은 안, 이음새는 밖"]] },
    { head: "③ 새 동작 일반화", sub: "새 궤적 모양", kind: "out", tagText: "그 동작의 시연이 필요", ico: "A'",
      rows: [["새로운 것", "궤적 모양 자체. 쪼개도 조각이 시연에 없다"], ["문헌 시험", "RT-2 저자가 한계로 명시: 운동 스킬은 로봇 데이터 분포 안에 머문다"], ["우리 트랙", "역방향 주행 → 좌회전만 하다 이탈 (7장). 저속 대조향, 후진"], ["궤적", "밖. 액션 공간 밖이면 표현 불가"]] },
  ];
  cols.forEach((c, i) => {
    const x = M + i * (w + 0.4);
    card(s, x, y, w, h);
    const icoCol = c.kind === "in" ? C.accent2 : c.kind === "amber" ? C.accent3 : C.accent1;
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.3, y: y + 0.25, w: 0.62, h: 0.62, fill: { color: icoCol }, line: { color: icoCol }, objectName: "icon" });
    txt(s, c.ico, { x: x + 0.3, y: y + 0.25, w: 0.62, h: 0.62, fontSize: 12, bold: true, color: C.background1, align: "center", valign: "middle" });
    heading(s, c.head, { x: x + 1.05, y: y + 0.22, w: w - 1.3, h: 0.4, fontSize: 17 });
    txt(s, c.sub, { x: x + 1.05, y: y + 0.6, w: w - 1.3, h: 0.3, fontSize: 11.5, color: C.accent4, italic: true });
    tag(s, x + 0.3, y + 1.05, c.tagText, c.kind, w - 0.6);
    const rows = c.rows.map(r => [td(r[0], { bold: true, color: HX.dk1, fontSize: 11.5 }), td(r[1], { fontSize: 11.5 })]);
    s.addTable(rows, tableOpts({ x: x + 0.3, y: y + 1.55, w: w - 0.6, colW: [1.0, w - 1.6], rowH: [0.55, 0.85, 0.85, 0.55], border: { type: "none" }, fill: { color: HX.lt2 }, valign: "top", margin: 0.04 }));
  });
  card(s, M, 6.35, W - 2 * M, 0.55, { fill: C.text1 });
  txt(s, "단서: ②③의 문헌 수치는 모두 탁자 위 조작 로봇 벤치마크다. 주행에서 같은 시험을 한 논문은 찾지 못했다(10장). 주행 적용은 추정이고, 우리 트랙 실측(역방향·회피)이 그 추정을 뒷받침한다.", { x: M + 0.3, y: 6.35, w: W - 2 * M - 0.6, h: 0.55, fontSize: 11.5, bold: true, color: C.background1, valign: "middle" });
  ref(s, REF.rt2 + " · " + REF.act + " · " + REF.pro);
  s.addNotes("'대부분 실패'는 VLA 연구가 실패했다는 뜻이 아니다. 조합 시연 없이 제로샷으로 새 조합을 시키면 무너지고, 조합 시연을 넣으면 회복된다는 뜻. 수치가 무엇을 재는지는 다음 장.");
}

// ---- 4. 문헌 수치가 재는 것 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "일반화 세 종류" });
  s.addText("문헌 수치가 실제로 재는 것 — 숫자 뒤의 시험 설정", { placeholder: "title" });
  const rows = [
    [th("논문"), th("시험 설정"), th("수치"), th("뜻")],
    [td("LIBERO-PRO (2025)"), td("탁자 위 조작 벤치마크 LIBERO. 표준 시험은 학습과 같은 배치·같은 지시문. PRO는 두 물체 자리를 맞바꾸거나(Swap) 지시문을 바꿈(Task)"), td("π0.5: 표준 96.9 % → 자리 바꿈 39.7 %, 지시문 바꿈 30.1 %\nOpenVLA·π0: 두 교란 모두 0 %"), td("표준 점수는 배치와 궤적을 외운 결과였다. 엄밀히는 '기억'을 재는 시험이고, 지시문 바꾸기가 조합에 가장 가깝다")],
    [td("ACT-VLA (2026)"), td("LIBERO에서 (물체, 위치)·(물체, 목표) 짝 중 학습에 없는 짝만 모아 시험. 각 조각은 학습에 있음"), td("조합 시연 없이 35.5 % / 46.6 %\n합성 조합 시연 추가 후 88.2 % / 95.6 %"), td("조각을 다 배워도 새 짝은 안 되고, 그 짝의 시연을 넣으면 된다")],
    [td("AGNOSTOS (NeurIPS 2025)"), td("18개 학습 과제, 23개 미학습 과제. 1단계는 물체나 동작을 일부 공유, 2단계는 완전히 새 상황"), td("현행 VLA 전부 낮음. 가장 나은 방법(X-ICM)도 π0 대비 +6.0 %p"), td("미학습 과제 제로샷은 분야 전체가 미해결")],
    [td("INT-ACT (2025)"), td("50개 과제에서 '무엇을 할지'(의도)와 '해냈는지'(실행)를 따로 채점"), td("의도 80~100 %, 실행 성공률은 분포 이동에서 크게 하락"), td("VLM이 준 '좋은 의도'가 실행으로 안 이어진다. 우리 5장과 같은 모양")],
    [td("RT-2 (CoRL 2023)"), td("웹 지식 + 로봇 시연 공동 학습. 새 물체·새 표현·간단 추론 평가"), td("새 물체·새 표현 성공. 저자: \"새 운동 스킬은 생기지 않는다\""), td("의미 축은 넓어지고 운동 축은 시연 안")],
  ];
  s.addTable(rows, tableOpts({ x: M, y: 1.45, w: W - 2 * M, colW: [1.9, 4.0, 2.9, 3.33], rowH: [0.4, 1.0, 0.85, 0.75, 0.75, 0.75], fontSize: 11, valign: "top", margin: 0.07 }));
  txt(s, "다섯 편 모두 조작 로봇(팔)이다. 주행에서 조합·새 기동을 같은 방식으로 시험한 논문은 10장에서 보듯 찾지 못했다.", { x: M, y: 6.45, w: W - 2 * M, h: 0.35, fontSize: 11.5, color: C.accent4 });
  ref(s, REF.pro + " · " + REF.act + " · " + REF.agn + " · " + REF.int + " · " + REF.rt2);
  s.addNotes("3장 숫자의 출처와 뜻. LIBERO-PRO는 기억 시험, ACT-VLA가 조합 시험에 가장 가깝다.");
}

// ---- 5. 예시 ① 의미 일반화 (실제 GUI) ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "일반화 세 종류" });
  s.addText("예시 ① 의미 일반화 — VLM은 새 표현을 잇지만, 실행은 따로다", { placeholder: "title" });
  const iw = 7.9, ih = iw * 904 / 1600;
  s.addImage({ path: "20261008_gui_goto_t022.jpg", x: M, y: 1.4, w: iw, h: ih, objectName: "GUI 화면 10-08 0:22" });
  s.addShape(pres.ShapeType.rect, { x: M + iw * 0.503, y: 1.4 + ih * 0.33, w: iw * 0.49, h: ih * 0.3, fill: { type: "none" }, line: { color: C.accent1, width: 2 }, objectName: "callout-chat" });
  s.addShape(pres.ShapeType.rect, { x: M + iw * 0.235, y: 1.4 + ih * 0.245, w: iw * 0.07, h: ih * 0.07, fill: { type: "none" }, line: { color: C.accent1, width: 2 }, objectName: "callout-car" });
  cap(s, "강좌 GUI 시험 영상 0:22 (2026-10-08). 정책 s1, VLM Qwen2.5-VL 7B. 주황 테두리 = 대화 창과 차량 위치", M, 1.4 + ih + 0.08, iw);
  const x = M + iw + 0.35, w = W - M - x;
  const steps = [
    { t: "입력", b: "\"삼각형 모양의 물체로 가줘\" — 학습 문장에 없는 표현", col: C.accent4 },
    { t: "VLM (인지)", b: "'삼각형 모양의 물체'는 화면 center · 1.1초 → 파란 꼬깔", col: C.accent2 },
    { t: "정책에 보낸 문장", b: "\"Go to the object straight ahead.\"", col: C.accent6 },
    { t: "VLA (실행)", b: "차는 오른쪽으로 꺾기 시작. 폐루프 선택 8/30 (우연 33 %)", col: C.accent1 },
  ];
  steps.forEach((st, i) => {
    const y = 1.4 + i * 1.02;
    s.addShape(pres.ShapeType.roundRect, { x, y, w, h: 0.86, rectRadius: 0.1, fill: { color: st.col }, line: { color: st.col }, objectName: "step" });
    txt(s, st.t, { x: x + 0.2, y: y + 0.08, w: w - 0.4, h: 0.3, fontSize: 12, bold: true, color: C.background1 });
    txt(s, st.b, { x: x + 0.2, y: y + 0.38, w: w - 0.4, h: 0.46, fontSize: 11.5, color: C.background1 });
    if (i < 3) s.addShape(pres.ShapeType.line, { x: x + w / 2, y: y + 0.86, w: 0, h: 0.16, line: { color: C.accent4, width: 1.5, endArrowType: "triangle" }, objectName: "arrow" });
  });
  card(s, x, 5.6, w, 1.15);
  txt(s, "의미 축은 사전학습 VLM이 넓힌다. 실행 축은 정책이 못 따라온다. INT-ACT가 보고한 \"의도 80~100 %, 실행은 분포 이동에서 붕괴\"와 같은 모양이다.", { x: x + 0.2, y: 5.68, w: w - 0.4, h: 1.0, fontSize: 12, bold: true, color: C.text1 });
  ref(s, REF.int + " · " + REF.rt2 + " · " + REF.gui);
  s.addNotes("의미 일반화의 실물 사례. VLM 방향은 영상에서 2/2 맞았고, 정책은 문장과 상관없이 오른쪽으로 꺾었다. 10-08 결정: 인지는 VLM, 이동은 VLA.");
}

// ---- 6. 예시 ② 조합 일반화 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "일반화 세 종류" });
  s.addText("예시 ② 조합 일반화 — 순차는 가능성이 있고, 중첩은 이음새 시연이 필요하다", { placeholder: "title" });
  const px = M, py = 1.45, pw = 6.6;
  card(s, px, py, pw, 5.25);
  const sw = (pw - 0.6 - 0.25) / 2, sh = 1.35;
  const panels = [
    { v: "A", label: "배운 것 A: 차선변경", sub: "횡 1.8 m, 순항 속도", kind: "in" },
    { v: "B", label: "배운 것 B: 장애물 앞 정지", sub: "차선 중앙 직진 → 감속", kind: "in" },
    { v: "SEQ", label: "순차 조합: 2차선 이동 → 회피·복귀", sub: "A가 끝난 상태 = B의 출발 상태. 이음새가 깨끗", kind: "amber" },
    { v: "OVL", label: "중첩 조합: 꺾으면서 틈에 맞춰 서기", sub: "A와 B가 동시. 그 순간의 화면·궤적은 어디에도 없음", kind: "out" },
  ];
  panels.forEach((p, i) => {
    const sx = px + 0.3 + (i % 2) * (sw + 0.25), sy = py + 0.3 + Math.floor(i / 2) * (sh + 0.85);
    const col = p.kind === "in" ? C.accent2 : p.kind === "amber" ? C.accent3 : C.accent1;
    roadPanel(s, sx, sy, sw, sh, p.v, col);
    txt(s, p.label, { x: sx, y: sy + sh + 0.05, w: sw, h: 0.3, fontSize: 12, bold: true, color: C.text1 });
    txt(s, p.sub, { x: sx, y: sy + sh + 0.33, w: sw, h: 0.45, fontSize: 10.5, color: col });
  });
  txt(s, "사용자 예시(\"2차선으로 가\" 뒤 2차선 장애물)는 순차 조합이다. 실패한다면 조합 때문이 아니라 회피가 자리를 외웠기 때문일 가능성이 크다(인덱스 142). 사선 주차는 중첩 조합이라 이음새 시연이 필요하다.", { x: px + 0.3, y: py + 4.55, w: pw - 0.6, h: 0.65, fontSize: 11, color: C.text2 });
  const cx = px + pw + 0.35, cw = W - M - cx;
  card(s, cx, py, cw, 5.25);
  heading(s, "문헌: 조합 시연을 넣기 전과 후 (성공률 %)", { x: cx + 0.3, y: py + 0.2, w: cw - 0.6, h: 0.35, fontSize: 14 });
  s.addChart(pres.ChartType.bar, [
    { name: "조합 시연 없음 / 교란", labels: ["ACT-VLA\nSpatial-OOD", "ACT-VLA\nGoal-OOD", "LIBERO-PRO\nπ0.5 위치 교란", "LIBERO-PRO\nπ0.5 지시문 교란"], values: [35.5, 46.6, 39.7, 30.1] },
    { name: "조합 시연 추가 / 표준", labels: ["ACT-VLA\nSpatial-OOD", "ACT-VLA\nGoal-OOD", "LIBERO-PRO\nπ0.5 위치 교란", "LIBERO-PRO\nπ0.5 지시문 교란"], values: [88.2, 95.6, 96.9, 96.9] },
  ], chartBase({ x: cx + 0.2, y: py + 0.6, w: cw - 0.4, h: 3.5, barDir: "col", barGrouping: "clustered", chartColors: [HX.accent1, HX.accent2], showLegend: true, legendPos: "b", valAxisMaxVal: 100, valAxisMinVal: 0, catAxisLabelFontSize: 9.5, dataLabelFontSize: 10 }));
  txt(s, "ACT-VLA: 같은 서브스킬의 새 조합에서 35.5 → 88.2 %는 합성 조합 시연을 학습에 넣은 결과. LIBERO-PRO: 표준 96.9 %인 π0.5가 배치·지시문 교란에서 39.7 / 30.1 %. 둘 다 조작 로봇이고, 요점은 \"조합은 공짜가 아니다\".", { x: cx + 0.3, y: py + 4.2, w: cw - 0.6, h: 1.0, fontSize: 11 });
  ref(s, REF.act + " · " + REF.pro + " · " + REF.avo);
  s.addNotes("순차 조합과 중첩 조합을 구분해서 말한다. 사용자 예시는 순차. 주차는 중첩. 회피 자체가 폐루프에서 안 붙었으므로 순차 조합 시험도 그게 먼저다.");
}

// ---- 7. 예시 ③ 새 동작 일반화 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "일반화 세 종류" });
  s.addText("예시 ③ 새 동작 일반화 — 시연에 없던 궤적은 나오지 않는다", { placeholder: "title" });
  const iw = 5.9, ih = iw * 885 / 1181;
  s.addImage({ path: "track.png", x: M, y: 1.45, w: iw, h: ih, objectName: "트랙 지도" });
  s.addShape(pres.ShapeType.leftArrow, { x: M + iw * 0.3, y: 1.45 + ih * 0.1, w: 1.6, h: 0.42, fill: { color: C.accent2 }, line: { color: C.accent2 }, objectName: "ccw" });
  txt(s, "학습: 반시계", { x: M + iw * 0.3, y: 1.45 + ih * 0.1, w: 1.6, h: 0.42, fontSize: 10.5, bold: true, color: C.background1, align: "center", valign: "middle" });
  s.addShape(pres.ShapeType.leftArrow, { x: M + iw * 0.33, y: 1.45 + ih * 0.845, w: 1.9, h: 0.42, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "cw" });
  txt(s, "시험: 180° 돌려놓음", { x: M + iw * 0.33, y: 1.45 + ih * 0.845, w: 1.9, h: 0.42, fontSize: 10.5, bold: true, color: C.background1, align: "center", valign: "middle" });
  cap(s, "우리 트랙 (실물 트랙 도면). 시계방향 시연 0건", M, 1.45 + ih + 0.08, iw);
  const x = M + iw + 0.35, w = W - M - x;
  card(s, x, 1.45, w, 2.45);
  tag(s, x + 0.3, 1.7, "우리 트랙 실측 2026-08-06", "out", 2.4);
  heading(s, "역방향 주행", { x: x + 0.3, y: 2.1, w: w - 0.6, h: 0.35 });
  txt(s, "차를 180° 돌려놓자 정책은 계속 좌회전만 명령해 트랙 밖으로 나갔다. 낯선 화면을 가장 비슷한 학습 경험(반시계 = 결국 왼쪽으로 감김)에 패턴매칭한 결과. \"오른쪽으로 돌면 된다\"는 목표 역산이 모델 안에 없다.", { x: x + 0.3, y: 2.5, w: w - 0.6, h: 1.35, fontSize: 12.5 });
  card(s, x, 4.1, w, 2.6);
  tag(s, x + 0.3, 4.35, "주차", "out", 1.0);
  heading(s, "같은 종류의 요구", { x: x + 1.45, y: 4.35, w: w - 1.75, h: 0.35 });
  bullets(s, [
    "저속에서 큰 조향 + 정확한 지점 정지. 주행 시연의 궤적은 작은 곡률 + 순항",
    "정지도 규칙이 아니라 시연의 감속 램프에서 배운 행동이다 (브리지 설계 원칙)",
    "후진은 액션 공간(전진 속도 티어)에 없다 → 일반화가 아니라 표현 불가",
    "RT-2도 명시: 웹 지식은 의미·시각 개념을 옮기고, 운동 스킬은 로봇 데이터 분포 안",
  ], { x: x + 0.3, y: 4.8, w: w - 0.6, h: 1.85, fontSize: 12 });
  ref(s, REF.rt2 + " · " + REF.gen);
  s.addNotes("역방향 사례는 8월 사용자 실험. 새 동작은 다양성·데이터 양과 무관하게 시연이 있어야 한다.");
}

// ---- 8. 2축인데 왜 안 되나 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "일반화 세 종류" });
  s.addText("\"2축뿐인데 왜 안 되나\" — 플래너와 모방학습 정책은 다른 문제를 푼다", { placeholder: "title" });
  const y = 1.45, h = 3.75, w = (W - 2 * M - 0.5) / 2;
  const cols = [
    { head: "오라클 주행기 (policy_node.py)", kind: "in", tagText: "처음 보는 자리도 주차", rows: [["입력", "목표 자세 + 자차 위치·방향"], ["내부 모델", "자전거 운동학 (yaw_rate = v·tanδ / L)"], ["방법", "기하 계산 + 목표 역산 (후진 진입 판단 포함)"], ["새 자리", "식이 같으니 어디서든 성립"]] },
    { head: "VLA 정책 (SmolVLA, 약 450M)", kind: "out", tagText: "본 장면·본 궤적 밖은 미정의", rows: [["입력", "카메라 픽셀 + 문장 (좌표·목표 없음)"], ["내부 모델", "없음 — 관측 → 5초 궤적 반사"], ["방법", "시연에서 본 (장면, 궤적) 짝을 재현"], ["새 자리", "외삽이 아니라 임의 출력"]] },
  ];
  cols.forEach((c, i) => {
    const x = M + i * (w + 0.5);
    card(s, x, y, w, h);
    heading(s, c.head, { x: x + 0.3, y: y + 0.25, w: w - 0.6, h: 0.4, fontSize: 17 });
    tag(s, x + 0.3, y + 0.72, c.tagText, c.kind, 2.6);
    const rows = c.rows.map(r => [td(r[0], { bold: true, color: HX.dk1, fontSize: 13 }), td(r[1], { fontSize: 13 })]);
    s.addTable(rows, tableOpts({ x: x + 0.3, y: y + 1.25, w: w - 0.6, colW: [1.3, w - 1.9], rowH: 0.55, border: { type: "none" }, fill: { color: HX.lt2 } }));
  });
  card(s, M, 5.45, W - 2 * M, 1.25, { fill: C.text1 });
  txt(s, "\"2축이라 쉽다\"는 차가 그 기동을 물리적으로 할 수 있다는 말이고, 맞다. 정책의 출력은 숫자 2개가 아니라 10 Hz × 50 스텝의 궤적 모양이고, 그 모양과 그때의 관측이 시연 분포 안에 있어야 정의된다. 고속도로만 탄 사람이 처음 주차를 해내는 건 머릿속에 차 기하 시뮬레이터가 있어서다. 이 모델엔 없다.", { x: M + 0.3, y: 5.5, w: W - 2 * M - 0.6, h: 1.15, fontSize: 13.5, bold: true, color: C.background1, valign: "middle" });
  ref(s, REF.dagger + " · src/sant_vla_pkg/sant_vla_pkg/policy_node.py (direct_reverse) · vla_bridge_node.py");
  s.addNotes("오차 복리(DAgger 논의)도 여기 속한다: 주차는 좁아지는 공간이라 첫 오차가 바로 분포 밖 장면으로 이어지고 복구 시연이 없다.");
}

// =====================================================================
pres.addSection({ title: "자율주행 VLA 연구" });

// ---- 9. 자율주행 VLA 지형 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "자율주행 VLA 연구" });
  s.addText("자율주행 VLA 연구는 많다 — 무엇을 넣고, 무엇을 내고, 어디서 재는가", { placeholder: "title" });
  const rows = [
    [th("모델"), th("기관 · 연도"), th("입력 → 출력"), th("평가"), th("언어의 역할")],
    [td("LINGO-2"), td("Wayve 2024"), td("카메라 → 궤적 + 해설"), td("실도로 폐루프 (공개도로 첫 VLA 주행)"), td("\"다음 회전에서 감속\" 같은 지시 프롬프트, 실시간 주행 해설")],
    [td("EMMA"), td("Waymo 2024"), td("카메라 → 궤적(텍스트) + 사고 과정"), td("nuScenes·WOD 개루프"), td("Gemini 기반. 계획을 글로 풀어 쓰며 예측")],
    [td("SimLingo"), td("Tübingen, CVPR 2025"), td("카메라 → 궤적"), td("CARLA Leaderboard 2.0·Bench2Drive 폐루프, 카메라만으로 SOTA"), td("VQA·해설 + 지시 따르기(Action Dreaming). 합성 지시 81 % 성공")],
    [td("AutoVLA"), td("2025"), td("카메라 → 행동 토큰"), td("개루프(nuPlan 등) + CARLA 폐루프"), td("적응형 사고 과정, 강화학습 미세조정")],
    [td("OpenDriveVLA · DriveMoE"), td("AAAI 2026 · 2025"), td("카메라 → 궤적 / 행동"), td("nuScenes 개루프 / Bench2Drive"), td("장면 이해 토큰 / 장면·스킬별 전문가 혼합")],
    [td("ParkingE2E · E2E Parking"), td("SJTU IROS 2024 · 2025"), td("서라운드 카메라 + 목표 슬롯 → 경로 / 제어"), td("실차 4개 주차장 87.8 % / CARLA 85.2 %"), td("언어 없음. 목표 슬롯 좌표가 명시 입력")],
    [td("우리 (nav-vla)", { bold: true, color: HX.dk1 }), td("SmolVLA 450M"), td("전방 카메라 + 문장 → 5초 궤적"), td("Gazebo 폐루프, 실물 트랙 예정"), td("2 차선 × 3 속도 모드 + 섹터 3분류. 열린 표현은 VLM(Qwen)이 분해")],
  ];
  s.addTable(rows, tableOpts({ x: M, y: 1.45, w: W - 2 * M, colW: [1.9, 1.7, 2.6, 2.9, 3.03], rowH: [0.4, 0.62, 0.62, 0.72, 0.62, 0.62, 0.62, 0.62], fontSize: 11 }));
  txt(s, "공통점: 입력은 카메라, 출력은 궤적이고 언어는 지시·해설·추론에 쓰인다. 차이는 규모(실도로·수백만 시연)와 우리(단일 트랙·수십만 프레임)의 거리다.", { x: M, y: 6.45, w: W - 2 * M, h: 0.35, fontSize: 11.5, color: C.accent4 });
  ref(s, REF.lingo2 + " · " + REF.emma + " · " + REF.simlingo + " · " + REF.autovla + " · " + REF.odvla + " · " + REF.drivemoe + " · " + REF.park);
  s.addNotes("주행 VLA가 없는 게 아니다. 우리와 같은 구조(카메라→궤적, 언어 조건)이고 규모만 다르다. 다음 장: 이들이 재는 일반화 축.");
}

// ---- 10. 자율주행 VLA가 재는 일반화 축 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "자율주행 VLA 연구" });
  s.addText("주행 VLA가 재는 일반화 축 — 우리 질문(조합·새 기동)은 비어 있다", { placeholder: "title" });
  const y = 1.45, h = 3.3, w = (W - 2 * M - 0.8) / 3;
  const cols = [
    { head: "새 환경·물체·행동 교란", src: "Fail2Drive (2026)", kind: "in", body: [
      "CARLA 200개 짝 루트, 17개 미학습 시나리오(외관·배치·행동·강건성). 각 교란 루트에 분포 안 쌍을 붙여 차이를 잼",
      "SOTA 모델들 성공률 평균 −22.8 %p. LiDAR에 뻔히 보이는 물체를 무시하고 '빈 공간/점유 공간' 개념을 못 배운 실패",
      "= 의미·시각 축. 우리 L1·L2에 해당",
    ] },
    { head: "같은 과제, 새 지역, 데이터 양", src: "주행 데이터 스케일링 (2024)", kind: "in", body: [
      "실도로 약 400만 시연, 23개 시나리오, 3만 시간 이상. 학습·시험 지역을 지리적으로 분리",
      "데이터와 모델을 함께 키워야 하고, 차선 유지·차선 변경·회전은 스케일링 곡선이 서로 다름",
      "= 다양성·양 축. 새 기동이 생기는지는 묻지 않음",
    ] },
    { head: "지시 따르기", src: "SimLingo · LINGO-2", kind: "in", body: [
      "\"차선 바꿔\", \"속도 줄여\", \"장애물 피해\" 같은 합성 지시를 궤적으로 (SimLingo 81 %)",
      "LINGO-2는 실도로에서 프롬프트로 주행 성향을 바꾸고 해설을 냄",
      "= 언어 → 학습한 기동 선택. 우리 2 차선 × 3 속도 모드와 같은 종류",
    ] },
  ];
  cols.forEach((c, i) => {
    const x = M + i * (w + 0.4);
    card(s, x, y, w, h);
    tag(s, x + 0.3, y + 0.25, "시험함", "in", 1.0);
    heading(s, c.head, { x: x + 1.45, y: y + 0.22, w: w - 1.75, h: 0.4, fontSize: 14 });
    txt(s, c.src, { x: x + 0.3, y: y + 0.68, w: w - 0.6, h: 0.3, fontSize: 11, color: C.accent4, italic: true });
    bullets(s, c.body, { x: x + 0.3, y: y + 1.05, w: w - 0.6, h: h - 1.2, fontSize: 11.5 });
  });
  const by = y + h + 0.3;
  card(s, M, by, W - 2 * M, 6.6 - by, { fill: C.text1 });
  tag(s, M + 0.3, by + 0.22, "시험하지 않음", "out", 1.5);
  heading(s, "\"차선변경·회피를 배우고 주차\" 같은 조합·새 기동 시험", { x: M + 2.0, y: by + 0.2, w: W - 2 * M - 2.3, h: 0.4, color: C.background1, fontSize: 15 });
  bullets(s, [
    "Bench2Drive의 44개 시나리오는 모두 학습 분포 안이고, 주차는 어느 주행 VLA 벤치마크에도 없다. 주차 논문(ParkingE2E, E2E Parking)은 주차 데이터와 목표 슬롯 입력으로 따로 푼다",
    "그래서 조합·새 동작 판단은 조작 로봇 결과(4장)를 주행에 옮긴 추정이다. 우리 트랙 실측(역방향·회피)이 그 추정과 같은 방향을 가리키고, 간격 폭 스윕(16장)이 주행에서 직접 재는 첫 시험이 된다",
  ], { x: M + 0.3, y: by + 0.65, w: W - 2 * M - 0.6, h: 6.6 - by - 0.7, fontSize: 11, color: C.background2 });
  ref(s, REF.fail + " · " + REF.drvscale + " · " + REF.simlingo + " · LINGO-2 (Wayve, 2024) · " + REF.park);
  s.addNotes("주행 문헌이 재는 세 축과 재지 않는 한 축. 우리 질문은 비어 있는 칸에 있다. 그래서 '추정'이라고 쓴다.");
}

// =====================================================================
pres.addSection({ title: "우리 트랙 실측" });

// ---- 11. 회피 실험 설정 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "우리 트랙 실측" });
  s.addText("실측 1 — 회피 홀드아웃: 학습 물체 7종, 미학습 물체 3종", { placeholder: "title" });
  const rw = 7.7, rh = rw * (320 * 0.6) / 2000;
  tag(s, M, 1.45, "학습 물체 7종", "in", 1.5);
  s.addImage({ path: "objects_trained_row_c.png", x: M, y: 1.85, w: rw, h: rh, objectName: "학습 물체" });
  tag(s, M, 1.85 + rh + 0.2, "미학습 물체 3종 (사람·원기둥·초록 차)", "out", 3.2);
  s.addImage({ path: "objects_heldout_row_c.png", x: M, y: 1.85 + rh + 0.6, w: rw, h: rh, objectName: "미학습 물체" });
  const fy = 1.85 + 2 * rh + 0.95;
  const fw = 3.0, fh = fw * 480 / 640;
  s.addImage({ path: "r37_front_box.jpg", x: M, y: fy, w: fw, h: fh, objectName: "전방 카메라 박스" });
  cap(s, "정책 입력: 전방 카메라 (r37 폐루프, 박스 접근)", M, fy + fh + 0.05, fw + 0.5);
  card(s, M + fw + 0.3, fy, rw - fw - 0.3, fh + 0.4);
  bullets(s, [
    "질문: 여러 물체로 회피를 배우면 학습 안 한 물체(사람)도 피하는가",
    "판정: 폐루프 접촉 여부, 반사실(같은 상태에서 빈 차선 vs 장애물 프레임) 경로 차",
    "출발·장애물 위치는 오라클 수집과 같은 고정 인덱스 (70, 142)",
  ], { x: M + fw + 0.55, y: fy + 0.15, w: rw - fw - 0.8, h: fh + 0.1, fontSize: 11.5 });
  const mx = M + rw + 0.35, mw = W - M - mx, mh = mw * 800 / 650;
  s.addImage({ path: "track_map_idx70_142.png", x: mx, y: 1.45, w: mw, h: Math.min(mh, 5.2), objectName: "평가 위치" });
  ref(s, REF.avo + " · eval_out/course/clips");
  s.addNotes("홀드아웃 설계. 결과는 다음 장. 미학습 물체 질문 이전에 학습 물체부터 실패했다는 게 요점.");
}

// ---- 12. 회피 결과 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "우리 트랙 실측" });
  s.addText("실측 1 결과 — 학습한 박스조차 폐루프에서 피하지 못했다", { placeholder: "title" });
  const sw = W - 2 * M, sh = sw * 380 / 2920;
  s.addImage({ path: "r40_strip.png", x: M, y: 1.4, w: sw, h: sh, objectName: "r40 폐루프 클립" });
  cap(s, "r40 폐루프 클립 8 s → 12 s → 16 s: 차선 유지 후 박스 쪽으로 진입, 접촉. 회피 시연을 학습한 모델", M, 1.4 + sh + 0.05, sw);
  const cy = 1.4 + sh + 0.5, cw = 7.0, ch = H - 0.65 - cy;
  card(s, M, cy, cw, ch);
  heading(s, "장애물 고유 반응 — 반사실 경로 차 (m)", { x: M + 0.3, y: cy + 0.15, w: cw - 0.6, h: 0.35, fontSize: 14 });
  s.addChart(pres.ChartType.bar, [{
    name: "횡 경로 차 (m)",
    labels: ["차선변경 시연 (기준)", "직접 회피 시연 (기준)", "r33~r35 직접 회피 학습", "r46 짝 137쌍", "r47 짝 286쌍·5종", "r29~r32 정지 시연 (−0.04)"],
    values: [1.8, 1.36, 0.5, 0.27, 0.14, 0.0],
  }], chartBase({ x: M + 0.2, y: cy + 0.5, w: cw - 0.4, h: ch - 0.6, chartColors: [HX.accent1], valAxisMinVal: 0, valAxisMaxVal: 2.0, catAxisLabelFontSize: 10, dataLabelFormatCode: "0.00" }));
  const tx = M + cw + 0.35, tw = W - M - tx;
  card(s, tx, cy, tw, ch);
  bullets(s, [
    "정지 시연(r29~r32): 반응 −0.04 m. 가중·sampler·강한 제동 변형 전부 같음. 장애물 시각 정보가 액션 경로로 흐르지 않음",
    "8 m 앞 직접 차선변경 시연(r33~r35): 처음으로 반응 0.5 m. 그러나 시연 1.36 m의 35 %에서 천장. 스텝 2배·부스트 2배·순항 제거 모두 같은 값",
    "폐루프: 횡 0.1~0.3 m에서 박스 접촉. r46 회피 0/20",
    "함의: 회피가 안 붙는 모델 위에 \"차량 사이 진입\"은 기각선을 이미 넘은 실험",
  ], { x: tx + 0.3, y: cy + 0.2, w: tw - 0.6, h: ch - 0.4, fontSize: 12 });
  ref(s, REF.avo + " · docs/experiments/avoidance/20261001_1029_avoidance-problem-solving-summary.md");
  s.addNotes("차트: 기준 두 막대는 시연 자체의 횡이동. 나머지는 모델이 장애물 유무로 바꾼 양. r29~r32는 음수라 0으로 그리고 괄호에 적음.");
}

// ---- 13. 데이터를 늘리면 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "우리 트랙 실측" });
  s.addText("실측 2 — 데이터를 늘리면 고유 반응은 줄고, 장애물과 무관한 쏠림만 커졌다", { placeholder: "title" });
  const cw = 6.6, cy = 1.45, ch = 4.2;
  card(s, M, cy, cw, ch);
  heading(s, "짝 시연 137 → 286쌍, 물체 1 → 5종 (r46 → r47), 단위 m", { x: M + 0.3, y: cy + 0.15, w: cw - 0.6, h: 0.35, fontSize: 14 });
  s.addChart(pres.ChartType.bar, [
    { name: "장애물 고유 반응", labels: ["r46 (137쌍, 1종)", "r47 (286쌍, 5종)"], values: [0.27, 0.14] },
    { name: "빈 차선 쏠림 (장애물 없음)", labels: ["r46 (137쌍, 1종)", "r47 (286쌍, 5종)"], values: [0.42, 1.10] },
  ], chartBase({ x: M + 0.2, y: cy + 0.55, w: cw - 0.4, h: ch - 0.7, barDir: "col", barGrouping: "clustered", chartColors: [HX.accent2, HX.accent1], showLegend: true, legendPos: "b", valAxisMinVal: 0, valAxisMaxVal: 1.3, dataLabelFormatCode: "0.00" }));
  const tx = M + cw + 0.35, tw = W - M - tx;
  const rows = [
    [th("데이터를 늘리거나 바꾼 실험"), th("고유 반응"), th("대조군 쪽")],
    [td("박스 5 → 80개 스윕 (10-01)"), td("+0.5 ~ 0.7 m 정체"), td("빈 차선 위치 습관 2.3 m")],
    [td("r46 → r47 (10-03)"), td("+0.27 → +0.14 m", { color: HX.accent5, bold: true }), td("쏠림 +0.42 → +1.10 m")],
    [td("r43 같은 자리 직진 짝 (10-02)"), td("회피 3/97"), td("빈 차선 꺾음 0/100")],
    [td("g1 이름 문장 b1 vs b0 (10-07)"), td("22/42 vs 23/42"), td("—")],
    [td("섹터 s1 vs s0 vs r26 (10-08)"), td("49 vs 50 vs 49 /55"), td("폐루프 8/30, 오른쪽 20/30")],
  ];
  s.addTable(rows, tableOpts({ x: tx, y: cy, w: tw, colW: [2.3, 1.6, tw - 3.9], rowH: 0.52, fontSize: 11 }));
  card(s, tx, cy + 3.3, tw, 0.9, { fill: C.text1 });
  txt(s, "손실을 줄이는 가장 싼 길이 화면 자리·방향 사전확률이면 모델은 그 길로 간다. 문장·장애물을 읽어야만 손실이 줄어드는 목표를 준 적이 없다.", { x: tx + 0.25, y: cy + 3.35, w: tw - 0.5, h: 0.8, fontSize: 11.5, bold: true, color: C.background1, valign: "middle" });
  card(s, M, 5.85, W - 2 * M, 0.85);
  txt(s, "그래서 사전 기각선: 같은 설정에서 N/4 · N/2 · N을 b1/b0 짝으로 재고, 가장 큰 N에서 b1 < 27/42 이거나 b1 − b0가 시드 차이보다 크지 않거나 N에 따른 추세가 없으면 \"더 모으기\"는 근거 없음. 주차·수동 수집 실험에도 같은 규칙.", { x: M + 0.3, y: 5.9, w: W - 2 * M - 0.6, h: 0.75, fontSize: 12, valign: "middle" });
  ref(s, REF.rep + " §7.1 · docs/experiments/avoidance/20261001_2226_box-demo-scaling-sweep.md");
  s.addNotes("단서: 시험한 규모는 g1 185,635 프레임까지. '충분히 크면 된다'가 엄밀히 반증된 건 아니라서 기각선을 둔다.");
}

// ---- 14. 언어 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "우리 트랙 실측" });
  s.addText("실측 3 — 문장을 상수로 바꿔도 행동이 같다 (목표가 행동에 닿을 통로가 없다)", { placeholder: "title" });
  const iw = 7.7, ih = iw * 1300 / 2439;
  s.addImage({ path: "probe_across_runs.png", x: M, y: 1.4, w: iw, h: ih, objectName: "언어 반사실 프로브" });
  cap(s, "같은 화면·상태·노이즈에서 문장만 바꿨을 때. 왼쪽: 지시한 쪽으로 기운 비율(우연 50 %), 오른쪽: 경로 차 / 시연 차. 빗금 = 문장 학습 없는 대조군", M, 1.4 + ih + 0.05, iw);
  const x = M + iw + 0.35, w = W - M - x;
  card(s, x, 1.4, w, 5.3);
  bullets(s, [
    "이름 문장 b1 22/42 vs 상수 문장 b0 23/42 (n=42). b0는 문장을 본 적이 없으니 23/42가 노이즈 하한. b1은 정확히 그 위",
    "방향 단어(r52) 34/42로 방향은 맞추지만 크기 0.09배 → 폐루프 결과를 못 바꿈",
    "섹터 s1 = 대조군 s0 = 베이스 r26 (49·50·49 /55). 방향 반응은 차선 주행 때 이미 배운 것",
    "데이터엔 문장 정보가 있다(CMI 0.743 bit). 모델이 쓸 이유가 없었다",
    "LIBERO-PRO도 같은 보고: 지시문을 무의미한 문자열로 바꿔도 같은 행동",
    "주차와의 연결: \"저 사이로\"를 행동에 잇는 유일한 통로가 문장인데 닫혀 있다. ParkingE2E는 슬롯 좌표를 명시 입력으로 받는다",
  ], { x: x + 0.3, y: 1.6, w: w - 0.6, h: 5.0, fontSize: 11.5 });
  ref(s, REF.pro + " · " + REF.park + " · " + REF.rep + " §4.7");
  s.addNotes("그림: docs/experiments/reports/figures/probe_across_runs.png");
}

// =====================================================================
pres.addSection({ title: "수동 주행과 실습" });

// ---- 15. 오라클 vs 수동 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "수동 주행과 실습" });
  s.addText("수동 주행으로 학습하면? — 다양성은 가짜를 지우지만 진짜를 만들지 않는다", { placeholder: "title" });
  const y = 1.45, h = 3.0, w = (W - 2 * M - 0.4) / 2;
  card(s, M, y, w, h);
  tag(s, M + 0.3, y + 0.25, "맞는 부분", "in", 1.3);
  bullets(s, [
    "오라클 데이터는 규칙적이었다: r33~r35는 장애물 인덱스 142 하나. r44는 빈 차선에서도 같은 자리에서 꺾음 = 자리 외우기",
    "같은 자리 직진 짝을 넣자 자리 습관 0/20 (r43·r45·r46). 배치 다양성은 지름길을 지운다",
    "문헌: 환경·물체 다양성이 시연 개수보다 중요. 32개 환경·물체 조합 × 50개면 미학습 환경에서 약 90 %",
  ], { x: M + 0.3, y: y + 0.7, w: w - 0.6, h: h - 0.85, fontSize: 12 });
  const x2 = M + w + 0.4;
  card(s, x2, y, w, h);
  tag(s, x2 + 0.3, y + 0.25, "바뀌지 않는 부분", "out", 1.7);
  bullets(s, [
    "그 90 %는 같은 스킬을 새 환경·물체에서 한 것. 새 스킬이 생긴 게 아니다",
    "자리 습관을 지운 뒤 남은 장애물 고유 반응은 +0.14~0.27 m였다. 가짜를 지워도 진짜가 저절로 커지지 않았다",
    "수동의 비용: 양(오라클 19 h에 825 ep), 운전자마다 다른 조작(다봉성), 언어 무시 문제는 그대로. 시뮬 키보드 텔레옵(WASD)은 계단식 조향이라 부적합",
  ], { x: x2 + 0.3, y: y + 0.7, w: w - 0.6, h: h - 0.85, fontSize: 12 });
  const ty = y + h + 0.3;
  card(s, M, ty, W - 2 * M, H - 0.7 - ty, { fill: C.text1 });
  heading(s, "먼저 분리해서 재자 — \"다양성\"과 \"수동\"은 다른 변수다", { x: M + 0.3, y: ty + 0.15, w: W - 2 * M - 0.6, h: 0.35, color: C.background1 });
  const rows = [
    [th("바꾸는 것"), th("대조군"), th("측정"), th("기각")],
    [td("오라클 그대로, 출발 위치·장애물 인덱스·차선을 무작위화. 모델·스텝·ep 수는 r33~r35와 동일"), td("고정 배치 r33~r35 · 빈 차선 동일 명령"), td("반사실 반응 / 시연 횡이동 · 폐루프 무충돌 N/20 · 빈 차선 쏠림"), td("반응비가 0.35에서 유의하게 오르지 않거나 폐루프가 대조군과 같으면 \"다양성이 원인\" 기각. 쏠림만 줄면 \"가짜만 지운 것\"으로 기록")],
  ];
  s.addTable(rows, tableOpts({ x: M + 0.3, y: ty + 0.6, w: W - 2 * M - 0.6, colW: [3.3, 2.2, 2.6, 3.43], rowH: [0.35, 0.85], fontSize: 10.5, color: HX.dk1, fill: { color: HX.lt2 } }));
  ref(s, REF.lin + " · " + REF.pro + " · docs/experiments/avoidance/20261002_1414_shortcut-learning.md");
  s.addNotes("사용자 가설(10-09): 수동이면 매번 다르니 맞춰 주지 않을까. 절반 맞음. 무작위화 오라클로 다양성만 분리해 먼저 재는 게 싸다. 통과해도 주차는 별도 시연 필요.");
}

// ---- 16. 실습 사다리 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "수동 주행과 실습" });
  s.addText("강좌에서 보여 줄 \"학습하지 않은 상황\" — 동작은 분포 안에, 상황은 분포 밖에", { placeholder: "title" });
  const rows = [
    { n: "L1", head: "미학습 물체 · 표현", kind: "in", tagText: "동작 분포 안", ex: "공룡 앞 정지, \"멸종한 생물로 가\"", pred: "의미 축. 문헌상 가장 가능성 높음. 현재 goto 기준선·s3 학습이 이 축", stat: "진행 중" },
    { n: "L2", head: "미학습 배치", kind: "in", tagText: "동작 분포 안", ex: "학습 띠 밖 출발 위치, 횡오차 주입", pred: "실물 트랙은 출발 위치 고정 불가. 배치 띠 안/밖 따로 집계. Fail2Drive식 짝 시도", stat: "수집 확대 필요" },
    { n: "L3", head: "미학습 조합", kind: "amber", tagText: "순차 → 중첩", ex: "\"2차선으로 가\" 뒤 장애물 회피·복귀 (순차), 사선 주차 (중첩)", pred: "순차는 가능성 있음, 중첩은 실패 예측 → 경계 수업", stat: "회피 폐루프 선행" },
    { n: "L4", head: "미학습 동작 (주차)", kind: "out", tagText: "동작 분포 밖", ex: "두 박스 사이 전진 사선 진입 후 정지", pred: "실패 확인 → 수동 시연 10·20·40개 추가 → 성공률 곡선 (few-shot 전이)", stat: "D4 수동 시연" },
  ];
  const y0 = 1.45, rh = 1.1, gap = 0.12;
  rows.forEach((r, i) => {
    const y = y0 + i * (rh + gap);
    card(s, M, y, W - 2 * M, rh);
    circ(s, M + 0.25, y + 0.3, r.n, r.kind === "in" ? C.accent2 : r.kind === "amber" ? C.accent3 : C.accent1);
    heading(s, r.head, { x: M + 0.95, y: y + 0.18, w: 2.6, h: 0.4, fontSize: 15 });
    tag(s, M + 0.95, y + 0.62, r.tagText, r.kind, 1.5);
    txt(s, "예: " + r.ex, { x: M + 3.8, y: y + 0.18, w: 3.6, h: 0.85, fontSize: 12.5 });
    txt(s, r.pred, { x: M + 7.6, y: y + 0.18, w: 3.5, h: 0.85, fontSize: 12.5 });
    txt(s, r.stat, { x: M + 11.25, y: y + 0.18, w: 0.9, h: 0.85, fontSize: 11, color: C.accent4, italic: true });
  });
  txt(s, "L1·L2는 강점 수업(VLA가 실제로 넓히는 축), L3·L4는 경계 수업(어디서 멈추는지와 그것을 확인하는 실험).", { x: M, y: 6.4, w: W - 2 * M, h: 0.35, fontSize: 12, color: C.accent4 });
  ref(s, REF.rt2 + " · " + REF.act + " · " + REF.fail + " · " + REF.course);
  s.addNotes("10-03 교수님 방향(말로 지정한 물체로 가기)은 L1. 10-09 주차 질문은 L3·L4.");
}

// ---- 17. 실습 두 가지 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "수동 주행과 실습" });
  s.addText("핵심 실습 둘 — 경계를 학생이 직접 재고, 미학습 상황은 학습한 기동의 열로 푼다", { placeholder: "title" });
  const w = (W - 2 * M - 0.4) / 2, y = 1.45, h = 5.2;
  {
    const x = M;
    card(s, x, y, w, h);
    heading(s, "① 간격 폭 스윕 — 분포 경계 측정", { x: x + 0.3, y: y + 0.22, w: w - 0.6, h: 0.4, fontSize: 17 });
    const scenes = [
      { label: "차선 폭", sub: "직진 후 정지 = 분포 안", kind: "in", gap: 1.3 },
      { label: "중간", sub: "약간 꺾어야 함", kind: "mid", gap: 0.8 },
      { label: "좁음", sub: "사선 진입 = 분포 밖", kind: "out", gap: 0.4 },
    ];
    const sw = (w - 0.6 - 0.4) / 3, sy = y + 0.8, sh = 1.85;
    scenes.forEach((sc, i) => {
      const sx = x + 0.3 + i * (sw + 0.2);
      s.addShape(pres.ShapeType.rect, { x: sx, y: sy, w: sw, h: sh, fill: { color: HX.lt1 }, line: { color: "D5DAE0", width: 0.75 }, objectName: "scene" });
      const col = sc.kind === "in" ? C.accent2 : sc.kind === "out" ? C.accent1 : C.accent3;
      const bw = (sw - sc.gap) / 2 - 0.1;
      s.addShape(pres.ShapeType.rect, { x: sx + 0.1, y: sy + 0.25, w: bw, h: 0.7, fill: { color: C.accent4 }, line: { color: C.accent4 }, objectName: "box" });
      s.addShape(pres.ShapeType.rect, { x: sx + sw - 0.1 - bw, y: sy + 0.25, w: bw, h: 0.7, fill: { color: C.accent4 }, line: { color: C.accent4 }, objectName: "box" });
      s.addShape(pres.ShapeType.roundRect, { x: sx + sw / 2 - 0.16, y: sy + 1.2, w: 0.32, h: 0.5, rectRadius: 0.08, fill: { color: col }, line: { color: col }, objectName: "car" });
      s.addShape(pres.ShapeType.line, { x: sx + sw / 2, y: sy + 0.95, w: 0, h: 0.25, line: { color: col, width: 1.5, dashType: "dash", endArrowType: "triangle" }, objectName: "arrow" });
      txt(s, sc.label, { x: sx, y: sy + sh + 0.05, w: sw, h: 0.3, fontSize: 12, bold: true, align: "center", color: C.text1 });
      txt(s, sc.sub, { x: sx, y: sy + sh + 0.33, w: sw, h: 0.3, fontSize: 10.5, align: "center", color: col });
    });
    bullets(s, [
      "두 박스 사이 간격을 차선 폭에서 단계적으로 좁힌다. 측정값은 간격별 무충돌 진입률 (N회 반복, 빈 차선 대조군)",
      "넓으면 \"직진 후 정지\"라 분포 안, 사선 진입이 필요해지는 폭부터 분포 밖. 성공률이 꺾이는 폭 = 데이터 분포의 경계",
      "결과가 어느 쪽이든 수업: \"일반화 경계는 데이터 분포 경계와 일치한다\". 주행에서 조합·새 기동을 직접 재는 첫 시험이기도 하다",
    ], { x: x + 0.3, y: sy + sh + 0.75, w: w - 0.6, h: h - (sy - y) - sh - 0.9, fontSize: 11.5 });
  }
  {
    const x = M + w + 0.4;
    card(s, x, y, w, h);
    heading(s, "② 계층 분해 — 인지는 VLM, 이동은 VLA", { x: x + 0.3, y: y + 0.22, w: w - 0.6, h: 0.4, fontSize: 17 });
    const bx = x + 0.3, bw = w - 0.6;
    const steps = [
      { t: "\"저 두 차 사이에 세워\"", sub: "미학습 상황 · 자연어", col: C.accent4 },
      { t: "VLM (Qwen2.5-VL 7B) 이 분해", sub: "\"오른쪽 차선변경 → 박스 앞 정지\"", col: C.accent6 },
      { t: "VLA (SmolVLA) 가 실행", sub: "각 기동은 시연 분포 안", col: C.accent2 },
    ];
    steps.forEach((st, i) => {
      const by = y + 0.8 + i * 0.95;
      s.addShape(pres.ShapeType.roundRect, { x: bx, y: by, w: bw, h: 0.72, rectRadius: 0.1, fill: { color: st.col }, line: { color: st.col }, objectName: "step" });
      txt(s, st.t, { x: bx + 0.2, y: by + 0.06, w: bw - 0.4, h: 0.32, fontSize: 13, bold: true, color: C.background1 });
      txt(s, st.sub, { x: bx + 0.2, y: by + 0.38, w: bw - 0.4, h: 0.3, fontSize: 11, color: C.background1 });
      if (i < 2) s.addShape(pres.ShapeType.line, { x: bx + bw / 2, y: by + 0.72, w: 0, h: 0.23, line: { color: C.accent4, width: 1.5, endArrowType: "triangle" }, objectName: "arrow" });
    });
    bullets(s, [
      "Hi Robot(π0 위 상위 VLM)·RT-H(언어 동작 중간층)와 같은 분업. 10-08 구조 결정과 일치하고, 규칙 주행기로 대체하지 않는다",
      "성립 조건: 하위 VLA가 좁은 명령 어휘를 실제로 듣는 것. 차선 2지 모드는 0.67배로 듣고, 섹터 3분류는 s3 결과가 첫 판정",
      "전제조건: 폐루프 회피(차선변경 후 정지)가 먼저 붙어야 한다. 지금은 접촉한다",
    ], { x: bx, y: y + 3.7, w: bw, h: 1.4, fontSize: 11.5 });
  }
  ref(s, REF.hirobot + " · " + REF.rth + " · " + REF.int + " · " + REF.gui);
  s.addNotes("①은 측정 실습, ②는 VLA 고유성(언어·사전학습 지식)을 보이는 구조. ②는 Hi Robot·RT-H가 쓰는 계층 분업과 같다.");
}

// =====================================================================
pres.addSection({ title: "단기강좌 실습 설계" });

// ---- 18. 설계 원칙 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "단기강좌 실습 설계" });
  s.addText("단기강좌 실습 설계 — 다른 연구에서 빌린 다섯 원칙", { placeholder: "title" });
  const items = [
    { n: 1, head: "계층 분업을 눈에 보이게", src: "Hi Robot · RT-H", body: "학생은 자연어로 말하고, GUI는 'VLM 출력'과 '정책에 보낸 문장'을 따로 찍는다. 실패를 \"VLM이 틀림\"과 \"VLA가 안 들음\"으로 나눠 기록한다. 의미 축(L1)이 여기서 보인다" },
    { n: 2, head: "교란해 보고 성공률 재기", src: "LIBERO-PRO", body: "같은 명령에서 물체 자리를 맞바꾸고, 표현을 바꾸고, 출발 위치를 띠 밖으로 옮긴다. 성공률이 떨어지는 축이 곧 \"외운 것\"이다. 학생이 교란을 설계한다" },
    { n: 3, head: "분포 안·밖을 짝으로", src: "Fail2Drive", body: "모든 분포 밖 시도에 같은 조건의 분포 안 시도를 짝 지어 차이를 잰다. 빈 차선 대조군, 상수 문장 대조군도 같은 원리다" },
    { n: 4, head: "다양성 vs 개수", src: "데이터 스케일링 (조작·주행)", body: "같은 에피소드 수로 배치 1곳 vs 여러 곳 미세조정을 비교한다. 수동 시연이 왜 여러 자리에서 필요한지 학생이 숫자로 본다" },
    { n: 5, head: "예측을 먼저 적는다", src: "사전 기각선 (10-08 규칙)", body: "돌리기 전에 \"이 숫자가 나오면 이 가설을 버린다\"를 적고, 결과 발표는 예측 대 결과로 한다. 실패가 수업이 되는 장치" },
  ];
  const w = (W - 2 * M - 0.8) / 3, h = 2.35;
  items.forEach((it, i) => {
    const x = M + (i % 3) * (w + 0.4), y = 1.45 + Math.floor(i / 3) * (h + 0.3);
    card(s, x, y, w, h);
    circ(s, x + 0.3, y + 0.3, it.n, C.accent6);
    heading(s, it.head, { x: x + 0.95, y: y + 0.3, w: w - 1.25, h: 0.5, fontSize: 15, valign: "middle" });
    txt(s, it.src, { x: x + 0.3, y: y + 0.9, w: w - 0.6, h: 0.3, fontSize: 11, color: C.accent4, italic: true });
    txt(s, it.body, { x: x + 0.3, y: y + 1.2, w: w - 0.6, h: h - 1.3, fontSize: 11.5 });
  });
  {
    const x = M + 2 * (w + 0.4), y = 1.45 + h + 0.3;
    card(s, x, y, w, h, { fill: C.text1 });
    heading(s, "첫 손대기는 use_avoidance A/B", { x: x + 0.3, y: y + 0.3, w: w - 0.6, h: 0.5, fontSize: 15, color: C.background1, valign: "middle" });
    txt(s, "플래그 하나로 두 가지 행동. 코드를 쓰기 전에 \"행동은 내가 바꿀 수 있는 것\"을 먼저 느끼게 한다. 이후 모든 실습이 이 감각의 변주다.", { x: x + 0.3, y: y + 0.9, w: w - 0.6, h: h - 1.1, fontSize: 11.5, color: C.background2 });
  }
  ref(s, REF.hirobot + " · " + REF.rth + " · " + REF.pro + " · " + REF.fail + " · " + REF.lin + " · " + REF.drvscale);
  s.addNotes("강좌 구조(온라인 3일 + 오프라인 2일, 스테이션 3개)는 고정. 원칙 1~5는 그 안에서 활동을 고르는 기준이다.");
}

// ---- 19. 5일 흐름 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "단기강좌 실습 설계" });
  s.addText("5일 흐름 — 온라인 3일(데이터·학습) + 오프라인 2일(세 스테이션)", { placeholder: "title" });
  const rows = [
    [th("날"), th("활동"), th("학생이 남기는 것"), th("빌린 연구"), th("미리 참이어야 하는 것")],
    [td("D1\n온라인", { bold: true }), td("세 종류 일반화·\"2축 논쟁\" 강의. 시뮬에서 use_avoidance A/B 토글. 명령별로 \"될까?\" 예측 적기"), td("예측 노트 (L1~L4별)"), td("RT-2, LIBERO-PRO"), td("시뮬 환경 배포 완료")],
    [td("D2\n온라인", { bold: true }), td("사전 수집 데이터셋(수동 주행, LeRobot 형식) 배포. 출발 위치·장애물 자리·문장 분포 지도 그리기 → \"이 데이터로 못 하는 것\" 적기"), td("분포 지도 + 기각선 표"), td("데이터 스케일링, 사전 기각선"), td("데이터셋 준비 완료, 상태 벡터에 전역 자세 없음 확인")],
    [td("D3\n온라인", { bold: true }), td("미세조정 두 쌍: 배치 1곳 vs 여러 곳(같은 N), 이름 문장 vs 상수 문장 Drive. 언어 반사실 프로브로 비교"), td("체크포인트 2쌍 + 프로브 표"), td("Lin et al., 우리 b1/b0"), td("랩서버 GPU 슬롯, 프로브 스크립트 배포")],
    [td("D4\n오프라인", { bold: true }), td("트랙: VLM→VLA \"말로 지정한 물체로 가기\" + 교란(자리 바꾸기·표현 바꾸기·띠 밖 출발), 분포 안/밖 짝 시도\n벤치: D3 모델을 잭 위에서 먼저\n데이터: 주차 수동 시연 10·20·40개"), td("교란 성공률 표, 주차 시연 묶음"), td("Hi Robot, LIBERO-PRO, Fail2Drive"), td("s3 명령 추종 확인, VLM 서버 지연 ≤ 1.5 s, 실차 T0/T1 검증")],
    [td("D5\n오프라인", { bold: true }), td("트랙: 간격 폭 스윕(경계 측정). 밤새 미세조정한 주차 few-shot 곡선(0·10·20·40). 예측 대 결과 발표"), td("경계 그래프 + 곡선 + 발표"), td("ACT-VLA, 우리 제안"), td("D4 수집분 밤샘 학습 완료, 벤치에서 검증")],
  ];
  s.addTable(rows, tableOpts({ x: M, y: 1.45, w: W - 2 * M, colW: [0.9, 4.6, 2.1, 1.9, 2.63], rowH: [0.4, 0.75, 0.9, 0.8, 1.15, 0.8], fontSize: 10.5, valign: "top", margin: 0.07 }));
  card(s, M, 6.4, W - 2 * M, 0.42, { fill: C.text1 });
  txt(s, "D4·D5의 L3·L4 활동은 폐루프 회피가 붙어야 성립한다. 지금은 접촉하므로, 붙지 않으면 D5는 간격 폭 스윕(경계 측정)만으로 간다. 학생 수집은 D4 이후에만 있다.", { x: M + 0.3, y: 6.4, w: W - 2 * M - 0.6, h: 0.42, fontSize: 11, bold: true, color: C.background1, valign: "middle" });
  ref(s, REF.course + " · " + REF.hirobot + " · " + REF.pro + " · " + REF.fail + " · " + REF.act);
  s.addNotes("고정 구조: 온라인 3일 → 오프라인 2일. D1~D3엔 실차 수집 없음. 오프라인은 카메라→행동 반응형 주행만(전역 자세 입력 없음). 벤치에서 먼저 검증.");
}

// ---- 20. 정리 ----
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "단기강좌 실습 설계" });
  s.addText("정리 — 교수님께 드리는 답, 기각선, 강좌 전 확인 목록", { placeholder: "title" });
  card(s, M, 1.45, W - 2 * M, 1.3, { fill: C.text1 });
  txt(s, "\"2축이라 쉬운 건 플래너 입장입니다. 모방학습 정책은 본 장면과 본 궤적 밖에서는 정의되지 않습니다. 주행 VLA 문헌도 새 환경·지시문 축은 재지만 조합·새 기동은 재지 않고, 주차는 늘 주차 데이터로 풉니다. 그래서 주차는 안 되는 것을 먼저 측정하고, 미학습 물체 → 배치 → 조합 순서로 어디까지 되는지를 실습으로 보이겠습니다.\"", { x: M + 0.35, y: 1.5, w: W - 2 * M - 0.7, h: 1.2, fontSize: 13, bold: true, color: C.background1, valign: "middle" });
  const rows = [
    [th("항목"), th("값")],
    [td("설정"), td("s3 계열(stock SmolVLA base) 위 학습. r26 위 재학습은 방향 반응을 파괴한 전례(0.82 → 0.04)")],
    [td("대조군"), td("빈 차선 동일 명령 · 상수 문장 Drive. · 베이스 모델 · 고정 배치, 모든 조건에서 같이 측정")],
    [td("측정"), td("간격별 무충돌 진입률 · 언어 반사실 프로브(n=42) · 배치 띠 안/밖 별도 집계")],
    [td("기각"), td("주차 0-shot: 빈 차선 대조군과 구별 안 되면 기각(예상). 추가 시연 40 ep에서도 같으면 few-shot 전이 주장도 기각. 무작위화: 반응비 0.35에서 안 오르면 \"다양성이 원인\" 기각")],
    [td("기각되면"), td("수집량 증가로 가지 않는다. 학습 목표·구조(VLM 분해 경로, 대조 손실)로 간다")],
  ];
  s.addTable(rows, tableOpts({ x: M, y: 2.95, w: 7.6, colW: [1.1, 6.5], rowH: 0.52, fontSize: 11 }));
  const x = M + 7.6 + 0.4, w = W - M - x;
  card(s, x, 2.95, w, 3.75);
  heading(s, "강좌 전 확인 목록", { x: x + 0.3, y: 3.1, w: w - 0.6, h: 0.4, fontSize: 14 });
  bullets(s, [
    "s3 vs s3n: 섹터 명령 추종이 상수 문장과 구별되는가",
    "폐루프 회피(차선변경 후 정지)가 접촉 없이 붙는가",
    "SmolVLA 상태 벡터에 전역 자세가 없는가",
    "수동 주행 레코더가 LeRobot 형식을 내는가",
    "실차 T0/T1 검증, VLM 서버 지연 ≤ 1.5 s",
    "시뮬 작업 마감 10-16, 이후 실물 트랙 테스트·영상, 강좌 12월",
    "후진은 넣지 않는다. 실물 트랙은 출발 위치·배치 고정 불가",
  ], { x: x + 0.3, y: 3.55, w: w - 0.6, h: 3.1, fontSize: 11.5 });
  ref(s, REF.rep + " §7.1 · " + REF.gui + " · " + REF.course);
  s.addNotes("기각선은 결과를 본 뒤 바꾸지 않는다 (10-08 규칙). 확인 목록은 강좌 스킬의 '검증 전에 가르치지 않는다' 원칙.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
