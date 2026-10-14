# 말로 지정한 물체로 가기 — P0/P1 결과: 자산·점 목표 오라클·수집기·백본 확인 (2026-10-03 14:42)

계획: [20261003_1334](20261003_1334_goto-object-weekend-plan.md).

## 1. 물체 자산

| 종류 | 모델 | 비고 |
|---|---|---|
| 색 꼬깔 | go_cone_{red,yellow,green,blue,white} | 1.3 m, 기존 cone 프리미티브 색만 변경 |
| 스캔 장난감 (Google Scanned Objects, CC-BY 4.0) | go_dino_3(T-rex), go_dino_trex(실제 styracosaurus), go_dino_5(triceratops), go_dog(봉제 강아지), go_horse, go_triceratops(**실제 안드로이드 로봇 피규어**) | Fuel 이름이 틀린 것이 있어 썸네일로 확인 후 명사 수정. 테디베어는 누운 스캔이라 제외 |
| 생활 물체 (OpenRobotics) | go_hydrant(CC0), go_chair, go_trashbin | |

생성: `python3 tools/make_goto_models.py` (가장 긴 변 0.9~1.5 m 로 스케일, 바닥 z=0, `models/<name>/SOURCE.md` 에 출처·라이선스).
트랙은 텍스처를 입힌 평면 하나라 **잔디·주차 영역도 아스팔트와 같은 물리**(별도 잔디 충돌체 없음) — 잔디 배치 허용.
쓰지 않는 물체는 지하 30 m 로 숨김(원래 주차 위치가 수평선 위 점으로 보였음).

학습 플릿 14 종: 꼬깔 4 색(빨·노·파·흰), 박스·드럼통·바리케이드, 빨간·파란 해치백, 강아지·말·소화전·의자·쓰레기통.
학습 제외: 초록 꼬깔(색), 공룡 3 종(물체), 안드로이드 로봇(캐릭터), 사람·초록 해치백.

## 2. 오라클·수집기

- `route_oracle_node.py`: `{"goal":"point",x,y,standoff_m}`(점까지 pure pursuit, standoff 에서 정지), `{"goal":"lane_point",lane,...}`(차선 따라가다 목표 앞 정지).
- `sant_vla_pkg/goto_layout.py`: 배치 샘플러(시야 ±25° 안 3~4 개, 5~12.5 m, 경로 간섭은 **오라클이 실제로 그리는 원호** 기준 검사), 명령 템플릿(영어 8 + 한국어 3, 차선 따라 4 + 1).
- `collect_corpus.py --goto-groups`: 배치당 같은 출발·다른 목표 짝 2 개, 차선 위 목표는 "곧장 / 차선 따라" 짝(30 %).
- `label_reasoning.py`: "Heading to the red cone ahead on the left." / "Following the inner lane to the dog." / "Stopping in front of the chair." (옛 데이터 라벨은 바이트 단위 동일 확인)
- `verify_corpus.py`: goto 축 등록, 직선 구간 "곧장/차선 따라" 짝은 경로 차이 게이트 면제.
- 수집 정리 스크립트가 **모든 gz 를 죽이던 것을 같은 파티션만** 정리하도록 변경(`tools/kill_partition_stack.sh`) — 다른 세션(도메인 32)의 gz 가 떠 있었음.

시범(gpilot 10 배치 = 20 ep): 출발 yaw 부호 버그(전 에피소드 반대 방향) 수정 후 **19/20 성공**, 1 건은 원호가 다른 꼬깔 1.99 m 를 지나 충돌 → 원호 기준 간섭 검사로 수정.
라벨 문제: 목표가 가까우면 첫 프레임부터 "Stopping" → 목표를 정지 거리 + 2.5 m 이상에 두고 "Stopping" 은 마지막 1.2 m 로.

## 3. 백본 확인 (G0)

질문 장면: 학습 제외 물체가 섞인 시범 배치 13 개(gprobe, 학습 미사용).

| 모델 | 위치 질문(이름) | 설명 → 이름 | 비고 |
|---|---|---|---|
| SmolVLM2-500M (32 층 전체, 서버) | 10/26 (38 %, 우연 33 %) | 위치 질문 0/14 | SmolVLA 는 이 중 16 층만 씀 |
| Qwen2.5-VL-3B (로컬 Ollama) | 18/26 (69 %) | 위치 질문 3/14 | "가운데" 판정이 모호해 위치 질문 형식 자체가 약함 |
| **Qwen2.5-VL-3B (서버 transformers)** | – | **이름 대기 8/11**: "an extinct animal"·"a prehistoric creature" → **"dinosaur" 4/4**, 초록 꼬깔 2/2, 사람 1/2, 안드로이드 1/3 | 질문당 약 0.2 s (3090) |

- 로컬 Ollama 는 시뮬과 같이 띄우면 "8.4 GiB 시스템 메모리 부족"으로 VL 모델을 못 올림 → Qwen 은 서버에서(`server/code/course/qwen_vl.py`), 평가 중 재작성은 ssh 로 프레임을 보내 받음.
- qwen2.5vl:7b 는 로컬 메모리로 못 올림, 서버는 디스크 여유 때문에 3B 만 받음.
- 결정(계획 G0 규칙): **Qwen 이 설명을 이름으로 바꾸므로 ④ 계층형 진행.** SmolVLM2 단독은 설명 지정이 어려울 것으로 예상(T4 단독은 낮을 것).
- SmolVLA 의 노트북 CPU 추론 시간은 미측정(로컬에 lerobot 없음, 설치는 허락 범위 밖).

## 4. 진행

- 본 수집 `TAG=goto NGOTO=700` (약 1 400 ep) 14:31 시작, 약 150 ep/h → 자정 전후 종료.
- `tools/goto_weekend_chain.sh`: 수집 종료 → 서버 변환 g1 → r50 학습 30k(10k 마다 저장) → 체크포인트마다 T1·T2 평가(각 30 회).
- 평가 도구: `tools/eval/goto_trial.py`(단계 T1/T2/T3a/T3b/T3c/T4, `--rewrite qwen`), `goto_stat_eval.sh`, `goto_analyze.py`(Wilson 구간·우연 기준).
