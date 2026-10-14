# 폐루프를 막던 브리지 감쇠(curv_boost_slow)와 부정 대조 — "회피 성공"은 위치 prior (2026-09-30 19:53)

[20260930_1601](20260930_1601_situation-conditioned-action-design.md) 의 r40(상황 문구 조건화) 폐루프가 8/8 충돌,
"ahead" 문구가 켜져도 1 m 안팎에서 멈춘 원인을 찾으려고 궤적을 기록하고 브리지 후처리를 바꿔 봤다. 실험은
19:15~19:44. 그 전 맥락: [20260930_1530](20260930_1530_ramp70-relocation-result.md)(r38/r39, 위치 prior 발견).

## 한 줄 결과

- 1 m 에서 막던 건 브리지 `curv_boost_slow 0.85`. 1.0 이면 r38·r40 모두 우리 차선 장애물 앞에서 차선변경을 끝낸다.
- 그러나 장애물을 **옆 차선**에 둬도 같은 궤적으로 넘어가 부딪힌다 → 장애물 회피가 아니라 인덱스 70 의 위치 prior.
- 스윕 시작 조건은 미통과. 시작 조건에 부정 대조(옆 차선·빈 차선에서 차선 유지)를 추가한다.

## 바꾼 것

| 파일 | 변경 |
|---|---|
| `tools/eval/avoidance_trial.py` | 루프마다 `[wall t, 첫 장애물까지 거리, 차선 오프셋]` 을 모아 `TRACE [...]` 한 줄 출력(기존 보고서 JSON 은 그대로) |
| `server/code/vla_policy_server.py` (+ `src/sant_vla_pkg/scripts/` 사본) | 상황 로그 행에 `"t"`(wall time) |
| `tools/eval/trace_view.py` (신규) | 트라이얼 로그 TRACE + 서버 상황 로그 → 거리별 오프셋과 그 시각의 서빙 문구 |
| `tools/eval/r40_bridge_variants.sh` (신규) | `RUN`, `SITUATION`, `VARIANTS`(base/refill06/cbs10), `SPOT`, `MODELS`, `TAGX` |
| `smolvla_demo.sh` | `curv_boost_slow` 를 `CURV_BOOST_SLOW` env 로(기본 0.85 유지) |

서버·로컬 시계 차이 5 ms(19:15 확인) — 궤적과 서빙 문구를 wall time 으로 맞출 수 있다.

## 결과


| 모델 | 문구 | 브리지 | 장애물 | 결과 | 오프셋 10 m / 6 m / 최근접 |
|---|---|---|---|---|---|
| r40 | on | 기본 (refill 0.3, curv_boost_slow 0.85) | lane2 박스 | 충돌 2/2 | +1.00, +0.59 / +1.17, +0.93 / 1.0 m |
| r40 | on | refill 0.6 | lane2 박스 | 충돌 2/2 | +0.43~0.53 → 되돌아옴 / 0.15~0.25 m |
| r40 | on | **curv_boost_slow 1.0** | lane2 박스 | **성공 2/2** | +1.6 / +3.3 |
| r40 | on | curv_boost_slow 1.0 | lane2 해치백·사람·드럼통 | 성공 6/6 | 전부 +3.0~3.2 |
| r38 (문구 없음) | off | curv_boost_slow 1.0 | lane2 박스 | 성공 2/2 | +1.9 / +3.3 |
| **r40** | on | curv_boost_slow 1.0 | **lane1(옆 차선) 박스** | **충돌 2/2** | +1.8 / +3.1 → 옆 차선 박스에 충돌 |
| **r38** | off | curv_boost_slow 1.0 | **lane1 박스** | **충돌 2/2** | +2.0 / +3.2 |

(r38 행의 서빙 문구 열은 의미 없음 — 문구 없이 돌렸고 서버 로그에 남은 r40 문구가 찍힌다.)

판정:

1. **`curv_boost_slow 0.85` 가 폐루프 회피를 1 m 안팎에서 막고 있었다.** 끄면 r38·r40 모두 차선변경을 끝낸다.
2. **그러나 그것은 장애물 회피가 아니다.** 장애물을 옆 차선(lane1)에 두면 두 모델 모두 같은 궤적으로 lane1 으로
   넘어가 부딪힌다. 22→14 m 궤적(0.01, 0.03, 0.10, 0.30, 0.45)이 물체·문구·차선과 무관하게 같다 — **인덱스 70 의
   위치 prior 가 감쇠가 풀리자 완전한 차선변경으로 굴러간 것**이다. 문구가 없는 r38 이 오히려 더 빨리 꺾는다.
3. r40 의 해설은 옆 차선 박스도 "ahead in our lane" 이라 한다 — 학습 데이터에 옆 차선 장애물(v2)이 없어 차선을
   구분하지 못한다. 사람은 이 설정에선 12~14 m 에서 AHEAD 가 떴지만(기본 설정에선 0회), 그 전에 이미 옆으로
   흐르는 중이어서 영상이 바뀐 탓일 수 있다.
4. 기본 설정에서 학습 물체 1.1 m vs 사람 0.3 m 차이(r38)도 이 감쇠 아래에서의 수치라, 장애물 인식 근거로 쓰지 않는다.
5. **스윕 시작 조건은 통과하지 않았다.** 이 실험 이후 시작 조건은 "lane2 장애물은 피하고, lane1(옆 차선)·빈 차선
   대조에선 차선을 유지" 로 바꾼다 — 부정 대조 없는 "회피 성공"은 위치 암기와 구분되지 않는다.

다음 후보:

- 위치 prior 를 끊는 코퍼스: 장애물 위치를 에피소드마다 바꾸고 **v2(옆 차선 장애물, 차선 유지)** 를 다시 넣는다.
  문구 조건화가 의미를 가지려면 해설이 "우리 차선 / 옆 차선"을 구분해야 한다.
- `curv_boost_slow` 는 순항 곡선 진동 때문에 넣은 값이다(20260916_1945 문서). 1.0 으로 바꿀지는 순항 회귀를 따로 봐야 함.

## 재현

```bash
# 변형 비교 (r40, 박스 × 2, 변형마다 스택 재기동, 약 10 분)
bash tools/eval/r40_bridge_variants.sh ; tail -f eval_out/course/r40_variants.log
# 대조군: 옆 차선 장애물 / 문구 없는 r38
RUN=r40 SITUATION=1 VARIANTS=cbs10 SPOT=lane1:0.1725 TAGX=_lane1 bash tools/eval/r40_bridge_variants.sh
RUN=r38 SITUATION=0 VARIANTS=cbs10 SPOT=lane1:0.1725 TAGX=_lane1 bash tools/eval/r40_bridge_variants.sh
# 궤적 보기
scp autolab_sw@115.145.211.157:~/sunhong/nav-vla/logs/situation_serve.jsonl /tmp/sit.jsonl
python3 tools/eval/trace_view.py --situation /tmp/sit.jsonl eval_out/course/multiobj_eval/trials/r40_cbs10_*.log
```

결과 파일: `eval_out/course/multiobj_eval/r40_{base,refill06,cbs10,cbs10_others,cbs10_lane1}.jsonl`,
`r38_{cbs10,cbs10_lane1}.jsonl`, 트라이얼 로그 `eval_out/course/multiobj_eval/trials/`, 실행 로그
`eval_out/course/r40_controls.log`, `r40_lane1.log`.

## 미해결

1. 위치 prior 를 끊는 코퍼스: 장애물 위치 에피소드마다 변경 + **v2(옆 차선 장애물, 차선 유지)** 재도입.
2. 해설의 차선 구분: 옆 차선 박스도 "ahead in our lane" — v2 라벨("A {noun} … in the inner lane — keeping our
   outer lane")이 학습에 있어야 문구 조건화가 의미를 가진다.
3. `curv_boost_slow` 기본값: 순항 곡선 진동 때문에 넣은 값(20260916_1945). 1.0 으로 바꿀지는 순항 회귀 확인 후.
4. 부정 대조를 평가 스크립트 기본에 넣기(`ramp70_eval.sh` 가 lane2 만 돈다).
