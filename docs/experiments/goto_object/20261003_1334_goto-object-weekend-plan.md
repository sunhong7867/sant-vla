# 주말 계획 — 말로 지정한 물체로 가기 (2026-10-03 13:34)


## Context

- 교수님 피드백(10-03): 장애물 회피는 YOLO·라이다로도 되니 강좌 실습이 될 수 없다. **VLA 로만 되는 것**을 1 시간이라도 보여 줄 것.
  "공룡 인형을 두고 '멸종한 생물로 가' → 공룡 앞으로" 구상을 마음에 들어 하심.
- 강좌 계획은 이미 개정됨: `docs/course/단기강좌.md` 5페이지 (① 학습 물체 지정 ② 차선 따라 / 곧장 ③ 학습 안 한 물체 이름 ④ 설명 지정, ④는 SmolVLA 단독 vs Qwen-VL+SmolVLA 계층형).
  회피 연구는 `docs/experiments/avoidance/` 로 분리됨.
- 사용자는 주말 동안 자리에 없음 → **중간 질문 없이 아래 결정 규칙대로 진행**하고 월요일에 결과 문서로 보고.
- 사용자 허락(10-03): 수집 중 performance 프로필(끝나면 balanced), Ollama 에 qwen2.5vl 3B·7B 받기, 공개 3D 모델 내려받기,
  **이번 주말 생성물만** 서버 자동 정리. 명령은 영어 위주 + 한국어 일부.
- 학습 안 한 물체 후보(사용자): 공룡, 캐릭터 인형(짱구·치이카와 등). 결과가 나쁘면 **색 꼬깔(빨강·노랑·초록…)** 으로 대체 시험.

확인된 사실: 시뮬 물체 = cone, ob_box/barrel/barrier/cone/person, hatchback 5 색, prius. 공룡·동물·의자 없음.
route_oracle 은 lane/zone/cruise/stop 만 있음(점 목표 없음, 09-19 꼬깔 servoing 설계 TODO 상태). 09-19 설계는 잔디 주행 미검증으로 잔디 제외.
서버: GPU0 4070 Ti SUPER 16 G, GPU1 3090 24 G, 여유 22 G, SmolVLM2-500M·smolvla_base 캐시 있음. 로컬 Ollama 에 VL 모델 없음.
SmolVLA 이미지 = 512×512 → 64 토큰(토큰당 가로 약 64 px), 카메라 시야각 62°.

## 단계와 결정 규칙

### P0. 백본 확인 + 자산 (토 오후, 약 4 h)

1. **물체 자산** (`src/simulation_pkg/models/`)
   - 색 꼬깔 5 종(빨강·노랑·초록·파랑·흰색): 기존 `cone` SDF 복제 + material 만 변경. 크기는 1.0~1.4 m(토큰 1~2 개 확보).
   - Gazebo Fuel 등 공개 라이선스 모델 검색·다운로드: 공룡, 동물 2~3 종, 의자·소화전·쓰레기통 등 생활 물체, 캐릭터풍 인형(있으면).
     라이선스·출처는 `models/<name>/SOURCE.md` 에 기록. 크기는 1.0~1.8 m 로 스케일.
   - 결정: 공룡을 못 구하면 구한 모델 중 하나(동물 우선)를 학습 제외 물체로 지정. 공룡·캐릭터는 실제 트랙 인형으로 넘김.
2. **잔디·주차 영역 주행 확인**: 오라클 직선 주행으로 잔디 위 이동·충돌·뒤집힘 확인. 안 되면 **아스팔트 + 주차 영역만** 배치(09-19 설계 범위).
3. **백본 확인 (G0)** — `tools/eval/backbone_probe.py` (신규)
   - 시뮬에서 물체 3~4 개가 보이는 장면 20 장 캡처(기존 `tools/eval/record_clip.sh`·스폰 헬퍼 재사용).
   - 질문: "Which object is the {noun / color / description}? Answer left, center or right." — 이름·색·설명(예: "an extinct animal", "an animal").
   - 모델: SmolVLM2-500M(서버 transformers), qwen2.5vl 3B·7B(로컬 Ollama, **CPU 시간도 측정**).
   - 이 노트북에서 SmolVLA CPU 추론 1 회 시간 측정(GPU 끄고).
   - 결정: Qwen 이 설명 지정을 맞히면 ④ 계층형 진행. 아무도 못 맞히면 ④는 색·이름 단계까지로 축소하고 문서에 기록.

### P1. 수집 파이프라인 구현 (토 저녁, 약 4 h)

| 파일 | 변경 |
|---|---|
| `src/sant_vla_pkg/sant_vla_pkg/route_oracle_node.py` | **점 목표 모드** `{"goal":"point","x","y","standoff_m","target_speed"}`: 점까지 직선 pure pursuit, standoff 에서 부드럽게 정지(기존 slew). 차선 따라 가기는 기존 cruise 사용 |
| `src/sant_vla_pkg/scripts/collect_corpus.py` | `--goto-groups`: 무작위 출발(차선·잔디·주차), 물체 2~4 개를 시야(±27°) 안 4~12 m(시뮬 크기 기준, 토큰 1 개 이상)에 배치, 경로 간섭 검사. **같은 배치에서 목표만 바꾼 짝 2 개**, 목표가 차선 위·앞쪽이면 "곧장" + "차선 따라" 짝 추가. 목표 선택: 가장 가까운 것 1/3, 아닌 것 2/3, 좌·중·우 균형. 물체 동시 배치는 다장애물 때 만든 `_set_obstacle(list)` 재사용. 오프링 가드 예외, 비목표 물체 2 m 접근 = 실패 |
| `src/sant_vla_pkg/config/instructions.json` | 새 intent `goto_object` (곧장 / 차선 따라), 영어 템플릿 8 개 + 한국어 3 개, 슬롯 {noun, color} |
| `src/sant_vla_pkg/scripts/label_reasoning.py` | 목표 사실(방위·거리) + 문장 "Heading to the red cone ahead-left." / "Following the lane to the cone." |
| `tools/goto_chain.sh` (신규, `tools/multi_chain.sh` 패턴) | 시범/본 수집 → balanced → 라벨 → 서버 전송·개수 확인. `tools/sim_log_janitor.sh` 동반 |
| `tools/eval/goto_trial.py` + `tools/eval/goto_stat_eval.sh` (신규, `avoidance_trial.py`·`stat_eval.sh` 패턴) | 시드 고정 무작위 배치 × 단계별 30 회. 지표: 맞는 물체 도달률(우연 기준 = 1/물체 수), 최종 거리, 비목표 접근, 차선 따라/곧장 경로의 차선 이탈량 |

학습 물체: 박스·드럼통·바리케이드·콘(주황)·색 꼬깔 빨강·노랑·파랑·흰색·해치백 빨강·파랑·노랑·내려받은 생활 물체·동물 일부.
**학습 제외**: 초록 꼬깔(색 일반화), 공룡 또는 대체 동물(물체 일반화), 사람·초록 해치백(기존 홀드아웃).

### P2. 수집 (토 밤 → 일 새벽)

- 시범 10 배치(약 30 ep) → 결정: 통과율 ≥ 70 %, 정지 위치 오차 < 0.5 m, 비목표 접근 0 이면 본 수집. 아니면 원인 수정 후 시범 재실행(최대 3 회).
- 본 수집: 에피소드가 5~15 s 로 짧으므로 **약 1 500 ep 목표**(밤새). 수집 중만 performance.
- 수집 속도 감시: 다장애물 때 첫 43 분 8 ep 로 느렸던 원인(리셋·레코더 대기 추정)을 시범에서 측정, 리셋 오버헤드가 크면 배치당 짝을 늘려 출발 리셋 횟수를 줄임.

### P3. 학습 (일 오전~오후, 서버 GPU1 3090)

- 데이터: goto 묶음 + Stanley 순항(일반 주행 유지). 베이스 `runs/navvla_reasoning_r26`. 서버 스크립트 `server/code/course/convert_goto.sh`, `launch_goto.sh` (`convert_mrun.sh`·`launch_mrun.sh` 패턴).
- **30 000 step, 10 000 마다 저장** (주말이라 길게). 가중: 목표 문장 구간 부스트, 짝 부스트(`--contrast-twin-boost`, 같은 배치 다른 목표).
- 서버 정리: 평가 끝난 이번 주말 중간 체크포인트만 삭제(허락 범위).

### P4. 평가 (일 오후~밤, 로컬 시뮬, 한 번에 하나)

| 단계 | 내용 | 통과 기준 |
|---|---|---|
| T1 | 학습 물체·학습 표현, 새 배치 | 도달률이 우연 + 30 %p 이상 |
| T2 | "차선 따라" vs "곧장" 짝 | 같은 목표에서 경로 차이(차선 이탈량)가 뚜렷 |
| T3a | 초록 꼬깔(학습 제외 색) | 우연보다 높음 |
| T3b | 공룡/대체 동물 이름 | 우연보다 높음 |
| T4 | "멸종한 생물"/"동물" 설명 — SmolVLA 단독 vs Qwen 재작성 후 SmolVLA | 두 방식 차이 |

- 체크포인트 10k / 20k / 30k 각각 T1 먼저 → 가장 좋은 것으로 T2~T4.
- 결정: T1 이 우연 수준이면 (a) 라벨·지시 정합 점검 (b) 짝 부스트·목표 부스트 확인 (c) 데이터 추가 수집 1 회(일 밤). T1 통과 시 일 밤엔 T3·T4 강화(물체 종류 추가 수집 또는 Qwen 프롬프트 개선).
- T4 계층형: `tools/demo/qwen_rewrite.py`(신규) — 장면 1 장 + 명령 → 학습 어휘 안의 정본 명령으로 재작성(허용 명사 목록 제시). 좌표·박스는 넘기지 않음.

### P5. 정리 (월 오전)

- 결과 문서 `docs/experiments/log/<date>_goto-object-weekend.md` + README 한 줄, `docs/course/단기강좌.md` 5페이지에 실측치 반영(측정 범위·표본 수 명시, vla-scope-guard 문구 규칙).
- 메모리 갱신(강좌 일정, 새 실습 결과).

## 재사용할 기존 코드

- 물체 플릿 상주 + 순간이동: `collect_corpus.py` `_set_obstacle()`(리스트 지원), `tools/collect_multiobj_avoid.sh` `spawn_fleet`.
- 격리·RAM 감시·정리: `tools/div_run.sh`, `tools/multi_run.sh`, `tools/multi_chain.sh`, `tools/sim_log_janitor.sh`, `tools/cleanup_artifacts.sh`(KEEP_TRIALS 100 000).
- 시야 판정: `label_reasoning.py` `CAM_HALF_FOV`. 평가 골격: `tools/eval/avoidance_trial.py`, `stat_eval.sh`, `stat_analyze.py`(Wilson 구간).
- 서버 체인 패턴: `tools/mrun_sweep_chain.sh`(서버 끊기면 5 분마다 재접속).

## 위험

- 잔디 주행 불가 → 아스팔트·주차 영역만.
- 공룡·캐릭터 모델 없음 → 대체 동물 / 색 꼬깔(사용자 허락 범위).
- 정지 학습: 모든 에피소드가 정지로 끝나 데이터는 충분하지만, r11 처럼 실패하면 평가는 "목표 1.5 m 안 진입"으로 판정하고 정지는 안전층 처리로 기록.
- 서버 연결 끊김(연구실 와이파이) → 체인이 재시도하며 대기, 그동안 로컬은 수집 계속.
- 시뮬은 한 번에 하나(수집·평가 순차), 기동 전 스택·RAM 확인, ROS_DOMAIN_ID/GZ_PARTITION 격리.

## 검증

- P0: 자산 스폰 화면 캡처, 잔디 주행 궤적, backbone_probe 정답률·지연 표.
- P1: 시범 수집 manifest(통과율·정지 오차·비목표 접근), 라벨 문장 샘플, 같은 배치 짝 2 개가 목표만 다른지 확인.
- P3: 학습 로그의 데이터 프레임 수·부스트 비율·sampled share.
- P4: `goto_stat_eval.sh` 단계별 표(도달률 + Wilson 구간 + 우연 기준), T2 경로 그림.
- 모든 결과는 문서에 표본 수와 함께, 시도한 것과 안 된 것을 그대로 기록.
