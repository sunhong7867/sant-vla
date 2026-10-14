# 정답 상황 문구(좌표 오라클) 폐루프 — 1단계 중간 기록, 랩서버 연결 끊김으로 중단 (2026-09-30 21:07)

YOLO 도입 계획의 1단계. 질문: **인식이 완벽하면(정답 문구) r40 의 동작이 문구를 따르는가** — 우리 차선 장애물엔
"ahead" 로 피하고, 옆 차선 장애물엔 "clear" 로 차선을 유지하는가. 통과하면 YOLO 를 문구 공급원으로 붙이고,
실패하면 동작 쪽 코퍼스(위치 다양화 + v2)를 먼저 고친다. 맥락:
[20260930_1953](20260930_1953_curv-boost-and-negative-control.md)(해설 문구로는 옆 차선 대조에서 위치 prior 로 충돌).

**결론은 아직 없다.** 핵심인 옆 차선 대조를 돌리기 전에 20:03 부터 랩서버(115.145.211.157)가 핑·SSH 모두
무응답(인터넷은 정상, 21:07 까지 1 시간 이상).

## 바꾼 것

| 파일 | 변경 |
|---|---|
| `tools/eval/avoidance_trial.py` | `--oracle-situation`: 좌표로 `label_reasoning.obstacle_phase` 규칙(우리 차선 호 거리 0–14 m = ahead, 옆 차선에 있는 동안 passing, 2 m 지나면 past, 옆 차선 장애물 = clear)을 계산해 지시문 뒤에 문구를 붙이고 단계가 바뀔 때마다 재발행. 매번 노드를 만드는 `pub_instruction`(최대 10 s 대기) 대신 상주 퍼블리셔 `InstructionPublisher`. TRACE 행에 문구 추가 |
| `tools/eval/trace_view.py` | TRACE 에 기록된 오라클 문구를 우선 표시 |
| `tools/eval/multiobj_heldout_eval.sh` | `TRIAL_EXTRA` (avoidance_trial 추가 인자) |
| `tools/eval/r40_bridge_variants.sh` | `ORACLE=1` → `--oracle-situation` + 서버 문구 끔(`NAVVLA_SITUATION=0`, 중복 방지) |

오라클 동작 확인: 브리지 로그에 `'… slowly. Situation: road clear.'` → 호 거리 13.8 m 에서
`'… Situation: obstacle ahead in our lane.'` 수신(큐 리셋 후 새 청크).

## 결과 (r40, 박스, 저속 지시문)

| 조건 | 결과 | 궤적 (오프셋 @ 14 / 10 / 6 m, 문구) |
|---|---|---|
| 우리 차선, curv_boost_slow 0.85 | 충돌 2/2 (최근접 오프셋 0.98, 0.94 m) | +0.30 clear / +0.50 ahead / +0.87 ahead — 1 m 에서 멈춤 |
| 우리 차선, curv_boost_slow 1.0 #1 | **장애물 통과 후 gz 정리 단계 예외** (보고서·TRACE 유실) | 오라클 로그: ahead(호 13.8 m, +0.50) → passing(9.8 m, +1.65) → past(−2.2 m, +2.91) |
| 우리 차선, curv_boost_slow 1.0 #2 | 무효 — 시작 시 `/world/default/remove` 타임아웃(gz 서비스 wedge) | — |
| 옆 차선, 0.85 / 1.0 | **미실행** — BRINGUP_FAIL, 랩서버 SSH 타임아웃 | — |

읽는 법:

1. 0.85 에선 정답 문구로도 해설 문구 때와 같이 1 m 에서 멈춘다 — 멈춤은 검출 문제가 아니라 브리지 감쇠(1953 문서와 일치).
2. 1.0 에선 정답 문구로 박스를 지나갔다(#1). 그러나 1953 문서에서 문구 없는 r38 도 1.0 에선 지나갔으므로, **이것만으로는
   문구를 따른 건지 위치 prior 인지 구분되지 않는다.**
3. 문구가 clear 인 14 m 지점까지 이미 +0.30 m 흘러 있다(두 트라이얼 모두). 옆 차선 대조에서 "clear" 가 이 흐름을 잡아
   차선을 유지하는지가 1단계의 판정 기준이다 — 아직 미측정.

## 재개 방법 (서버 복구 후)

```bash
# 확인
ssh autolab_sw@115.145.211.157 'nvidia-smi --query-gpu=index,memory.used --format=csv,noheader'
# 남은 조건: 우리 차선 1.0 × 2, 옆 차선 0.85/1.0 × 2 (스택당 트라이얼 수를 줄여 gz wedge 회피: N=2)
RUN=r40 ORACLE=1 VARIANTS="cbs10" MODELS=ob_box SPOT=lane2:0.1725 TAGX=_oracle bash tools/eval/r40_bridge_variants.sh
RUN=r40 ORACLE=1 VARIANTS="base cbs10" MODELS=ob_box SPOT=lane1:0.1725 TAGX=_oracle_lane1 bash tools/eval/r40_bridge_variants.sh
python3 tools/eval/trace_view.py eval_out/course/multiobj_eval/trials/r40_*_oracle*_ob_box_*.log
```

판정 기준: 우리 차선 박스 회피 2/2 **그리고** 옆 차선 차선 유지 2/2(curv_boost_slow 1.0). 통과 → YOLO 연동(2단계a),
실패 → 위치 다양화 + v2 코퍼스로 r41(2단계b).

## 미해결

1. 위 재개.
2. (해결, 21:10) `avoidance_trial.py` 끝의 `remove_model` 을 try 로 감쌌다 — 정리 단계 예외가 보고서·TRACE 를 삼키지 않는다.
   시작 단계의 정리 실패(#2 트라이얼)는 그대로 예외 = 무효 트라이얼로 둔다.
3. gz 서비스 wedge 가 이번엔 스택당 3~4 번째 트라이얼에서 났다(기존 추정 약 8). 트라이얼 사이 간격 또는 스택 재기동 주기 재조정.

## 재개 결과 (2026-09-30 21:59~22:10) — 1단계 판정: 미통과

랩서버는 21:59 복구(uptime 267 일 — 재부팅이 아니라 네트워크 단절). 남은 조건을 같은 방식으로 실행.

| 조건 (r40, 박스, 오라클 문구) | 결과 | 오프셋 @ 14 / 10 / 6 m (문구) |
|---|---|---|
| 우리 차선, 0.85 (앞 절) | 충돌 2/2, 0.94~0.98 m | +0.30 clear / +0.50 ahead / +0.87 ahead |
| **우리 차선, 1.0** | **회피 2/2**, 최근접 오프셋 2.61~2.65 m | +0.44 clear / +1.46 ahead / +2.70 passing |
| **옆 차선, 0.85** | **차선 유지 2/2**, 0.24~0.25 m | +0.30 / +0.21 / +0.21 (전부 clear) |
| 옆 차선, 1.0 | **충돌 2/2**, 2.47~2.48 m 넘어감 | +0.49 / +0.98 / +1.88 (전부 clear) |

판정 기준(우리 차선 회피 2/2 **그리고** 옆 차선 유지 2/2)을 **어느 설정도 통과하지 못했다.**

읽는 법:

1. **0.85**: 문구가 동작을 가른다 — clear 면 14 m 이후 오프셋이 +0.30 → +0.21 로 돌아오고, ahead 면 +0.87 까지 나간다.
   그러나 ahead 의 양이 모자라 충돌.
2. **1.0**: ahead 면 피한다. 그러나 **clear 여도 옆 차선으로 넘어간다.** 문구 없는 r38(1953 문서, 10 m +2.02)보다 느리다
   (+0.98) — 문구가 쏠림을 줄이지만 막지 못한다.
3. 두 설정 모두 22→14 m 구간은 문구·차선과 무관하게 같은 궤적(+0.01, +0.04, +0.13, +0.29~0.34, +0.30~0.50)이다.
   인덱스 70 의 위치 쏠림이 폐루프에서 되먹임으로 커지는지(1.0) 멈추는지(0.85)가 곡률 15% 차이로 갈린다 — 경계에
   걸린 상태. 브리지 파라미터로 맞출 문제가 아니라 **동작 모델의 위치 쏠림을 없애야 한다.**

결정: **2단계b** — 장애물 위치를 에피소드마다 바꾸고 **v2(옆 차선 장애물, 차선 유지)** 시연을 넣은 코퍼스로 상황 문구
조건화 재학습(r41). YOLO 연동(2단계a)은 r41 이 이 오라클 시험을 통과한 뒤.

재현(재개 부분):

```bash
RUN=r40 ORACLE=1 VARIANTS="cbs10" MODELS=ob_box SPOT=lane2:0.1725 TAGX=_oracle bash tools/eval/r40_bridge_variants.sh
RUN=r40 ORACLE=1 VARIANTS="base cbs10" MODELS=ob_box SPOT=lane1:0.1725 TAGX=_oracle_lane1 bash tools/eval/r40_bridge_variants.sh
python3 tools/eval/trace_view.py eval_out/course/multiobj_eval/trials/r40_*oracle*_ob_box_*.log
```

결과 파일: `eval_out/course/multiobj_eval/r40_{cbs10_oracle,base_oracle_lane1,cbs10_oracle_lane1}.jsonl`, 실행 로그
`eval_out/course/r40_oracle2.log`. 트라이얼 정리 단계 예외는 이번 6 회에서 0 회(try 수정 이후).
