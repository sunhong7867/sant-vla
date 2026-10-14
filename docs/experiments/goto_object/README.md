# 말로 지정한 물체로 가기 — 실험 폴더 (2026-10-03 ~ )

2026-10-03 교수님 피드백으로 시작한 단기강좌 실습 연구다. 회피는 YOLO·라이다 규칙으로도 되므로, **VLA 로만 되는 것**
(문장으로 대상 지정, 학습 안 한 물체·설명 이해)을 보여 주는 실습을 만든다. 회피 연구는 [../avoidance/](../avoidance/README.md) 에 따로 있다.

연구 질문: **같은 화면에서 문장만 바꾸면 SmolVLA 가 지정한 물체로 가는가? 학습 안 한 물체("공룡", "멸종한 생물")도 되는가?**

종합 정리: [10-03 ~ 10-08 연구 경과 보고서](../reports/research_report_20261003_20261008.md)

---

## 1. 지금까지 결론 (요약)

| 단계 | 시도 | 결과 |
|---|---|---|
| 백본 확인 | SmolVLM2-500M·Qwen2.5-VL-3B 에 이름·설명 질문 | SmolVLM2 위치 고르기 ≈ 우연, Qwen "extinct animal" → "dinosaur" 4/4 |
| 이름 문장 (r50, r51) | 같은 배치·다른 목표 짝 시연 825 ep | 폐루프 47 %(우연 29 %)는 가장 가까운 물체 습관. 문장 반사실 21/42 = 우연 |
| 방향 단어 + Qwen (r52, r54) | 이름 → "왼쪽/정면/오른쪽" 재라벨 | 오프라인 34/42 이나 크기 0.09 배, 폐루프는 문장 무관. **왼쪽 쏠림은 postprocessor 통계 버그였음** |
| 합성 반사실 라벨 (rp3) | 운동학 교사로 모든 물체 라벨 합성 | 22/42, 라벨 정렬은 정상 |
| 데이터·기준선 (b1/b0) | CMI 측정 + 상수 문장 대조군 | 데이터 0.743 b(정보 있음), b1 22/42 = b0 23/42 → **이름 효과 반증** |
| 섹터 3분류 (s1/s0) | 섹터마다 물체 1 개, 문장은 방향만, 이름은 Qwen 담당 | 오프라인 s1 49 = s0 50 = 베이스 r26 49 /55 (반응은 베이스에서 옴), 폐루프 s1 8/30 = 27 %(우연 33 %), 오른쪽 쏠림 |
| 강좌 GUI 시험 (s1 + VLM) | 영상 2회, VLM 이 방향 고르고 s1 이 운전 | VLM 방향 2/2 맞음, **s1 은 문장과 상관없이 2회 모두 오른쪽으로 꺾음**(s1 은 섹터 미학습 = 차선 모델, 2237 정정). 이동은 VLA 로만(규칙 주행기 금지) → 밤샘 s3/s3n |

핵심 교훈: **대조군(상수 문장 모델·베이스 모델) 없이 본 효과는 두 번 다 착시였다. 오프라인 방향이 맞아도 크기가 작으면 폐루프는 안 바뀐다.**

---

## 2. 문서 (시간순)

| 날짜 | 문서 |
|---|---|
| 10-03 13:34 | [주말 계획](20261003_1334_goto-object-weekend-plan.md) |
| 10-03 14:42 | [P0/P1 — 자산·점 목표 오라클·수집기·백본 확인](20261003_1442_goto-p0-assets-oracle-backbone.md) |
| 10-04 15:34 | [r50 — 정책이 목표 이름을 무시](20261004_1534_goto-r50-language-blind.md) |
| 10-05 00:28 | [r52 — 폐루프 왼쪽 쏠림 → 통계 버그](20261005_0028_goto-r52-closed-loop-left-bias.md) |
| 10-05 21:31 | [cf-sidecar 정렬 · gv2b · CMI 축 버그](20261005_2131_cf-align-gv2b-cmi.md) |
| 10-07 10:10 | [기준선 b1/b0 + 섹터 설계·파일럿](20261007_1010_vision-action-baseline.md) |
| 10-08 10:14 | [섹터 s1/s0 — 반응은 베이스에서, 폐루프 우연](20261008_1014_sector-s1-s0-inherited-from-base.md) |
| 10-08 13:35 | [수집 FAIL 원인·우측 쏠림 정체·두 독립 고장](20261008_1335_two-independent-faults.md) |
| 10-08 22:38 | [강좌 GUI 시험 영상 검토 — 인지는 VLM, 이동은 VLA](20261008_2238_gui-goto-video-review.md) (영상: [media/](media/)) |
| 10-08 22:37 | **[g4 조용한 실패로 하루치 무효 · s2/s2n 음성 · s3 계획](20261008_2237_g4-void-s2-negative-s3-plan.md)** |
| 10-10 02:15 | **[s3/s3n 폐루프 — 최근접 15/30 vs 4/30 (p=0.00479), 시연 기준 0/10, 서빙 깨짐](20261010_0215_s3-s3n-closedloop.md)** |
| 10-12 17:55 | **[`EGO_HALF_LEN` 실측 — gap 지표 0.396 m 오차("지나쳤다"는 "닿기 직전에 섰다"), 2D 라이다 트리거 발화 0/835](20261012_1755_ego-half-len-measured.md)** |
| 10-12 18:50 | **[점 목표 원시 동작 "가리킨 곳으로 가서 서기" — 사전 등록 (g5d, P2~P4)](20261012_1850_point-goal-primitive-prereg.md)** |

새 실험 문서는 이 폴더에 `YYYYMMDD_HHMM_짧은-제목.md` 로 추가하고, 위 표와 [../log/README.md](../log/README.md) 목록에 한 줄씩 적는다.

## 3. 코드·데이터 위치

| 무엇 | 위치 |
|---|---|
| 배치·문장 템플릿 | `src/sant_vla_pkg/sant_vla_pkg/goto_layout.py` |
| 수집 | `collect_corpus.py --goto-groups / --goto-sectors`, `tools/goto_run.sh` |
| 평가 | `tools/eval/goto_trial.py`, `goto_stat_eval.sh`, `goto_analyze.py` |
| 서버 프로브·변환 | `server/code/course/probe_goto_language.py`, `convert_goto.sh`, `launch_goto.sh`, `qwen_vl.py` |
| 자율 루프 | `tools/goto_loop_chain.sh` (상태 `eval_out/course/goto_loop_state.txt`) |
| 서버 런 | `~/sunhong/nav-vla/runs/course/` (r52, rp3, b0, b1, s0, s1) |
