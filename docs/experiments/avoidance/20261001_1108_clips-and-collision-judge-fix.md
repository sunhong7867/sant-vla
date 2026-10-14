# 회피 영상 정리 + 충돌 판정 버그 수정(중심거리 2 m 규칙) (2026-10-01 11:08)

사용자 요청으로 회피 영상을 추가·정리하다가, 평가 하네스의 충돌 판정이 **옆으로 비켜 지나가는 차를 충돌로 판정해 세우는**
버그를 찾았다. r41 의 인덱스 70 "충돌" 결과([20260930_2302](20260930_2302_div-corpus-pose-stream-and-clips.md))
일부가 이 버그일 수 있다.

## 1. 충돌 판정 버그

`tools/eval/avoidance_trial.py`: `if d < COLLIDE_D or hit_geometric(pose, s)` — 주석은 "차량용 옛 규칙"인데 실제로는 **모든
물체에** 중심거리 2.0 m 규칙이 걸렸다. 옆으로 1.9 m 비켜 지나가도 중심거리가 2 m 밑으로 내려가는 순간 COLLISION 으로
기록하고 차를 세운다.

발견: r41 + 사람(ob_person, 반폭 0.3 m) 트라이얼이 횡 오프셋 1.94 m(필요한 값은 0.95 + 0.3 = 1.25 m)에서 COLLISION.
마지막 프레임을 보니 차는 사람 옆에 떨어져 서 있었다. 해치백도 같은 모습.

수정: 크기를 아는 물체(`OBJ_EXTENT`, hatchback, prius)는 차체 사각형 겹침(`hit_geometric`)만으로 판정, 중심거리 규칙은 크기
모르는 물체에만.

영향:
- 횡 오프셋이 1.5 m 미만인 과거 충돌(r36~r40 대부분)은 실제 겹침이라 그대로.
- **r41 인덱스 70 박스 2 회**: (d 1.95 m, lat 1.94) 는 중심거리 규칙으로 판정된 것 → 재평가 필요. (d 2.15, lat 1.91) 은 2 m
  초과라 기하 판정으로 걸린 것 → 실제 접촉 가능성.
- r41 인덱스 70 해치백·사람 첫 녹화(10:51~10:56)도 이 버그로 멈춤. 원본은 `eval_out/course/clips/old_idx70_judge/`.

## 2. 수정 후 r41 결과 (인덱스 70, 좌표 정답 문구, curv_boost_slow 1.0, 1 회씩)

| 장애물 | 결과 | 최근접 오프셋 | 비고 |
|---|---|---|---|
| 콘 (학습) | 회피 성공 | 2.13 m | |
| 사람 (미학습) | 회피 성공 | 1.82 m | 문구는 오라클 — 해설 검출 아님 |
| 해치백 (학습) | **STUCK** | 1.94 m | 옆을 지나간 뒤 "past"(장애물 중심 2 m 지남)에서 바로 복귀 → 4.4 m 길이 해치백 앞부분에 걸려 멈춤 |
| 박스, 옆 차선 | 차선 유지 | 0.47 m | |

해치백 STUCK 은 **복귀가 이른 것**: 라벨은 장애물 중심을 2 m 지나면 "past"(복귀) 문구지만, 실제 시연은 장애물 6.3 m 뒤에서
복귀를 시작한다(`avoid_return behind_m 6.3`). 짧은 물체에선 문제없고 차량처럼 긴 물체에서 드러난다.

## 3. 영상 (`eval_out/course/clips/`, 글자 없음, 차가 화면에 들어오는 순간부터)

| 파일 | 모델 | 내용 | 길이 |
|---|---|---|---|
| `r40_box_avoid.mp4` | r40 | 우리 차선 박스 회피 | 20 s |
| `r40_box_lane1_crash.mp4` | r40 | 옆 차선 박스인데 차선 변경 → 충돌 | 12 s |
| `r41_cone_avoid.mp4` | r41 | 학습한 다른 물체(콘) 회피 | 18.5 s |
| `r41_person_avoid.mp4` | r41 | 학습 안 한 물체(사람) 회피 | 19.6 s |
| `r41_box_lane1_straight.mp4` | r41 | 옆 차선 박스, 꺾지 않고 직진 | 16.8 s |
| `r41_hatchback_pass_then_stuck.mp4` | r41 | 해치백 옆을 지나간 뒤 복귀하다 걸림 | 17.3 s |

모두 정답 문구 + curv_boost_slow 1.0 + 저속, 인덱스 70 위 15 m 수직 하향 카메라. 자막판(`*_zoom.mp4`, `compare_stacked.mp4`)과
긴 원본(`avoid.mp4`, `crash.mp4`)은 사용자 요청으로 삭제. 프레임 폴더(`frames_*`)는 남겨 둠.

## 바꾼 것

| 파일 | 변경 |
|---|---|
| `tools/eval/avoidance_trial.py` | 중심거리 충돌 규칙을 크기 모르는 물체로 한정 |
| `tools/eval/record_clip.sh` | `CLIPS` 세 번째 칸 = 장애물 모델 |
| `tools/eval/trim_clip.py` (신규) | 연속 움직임 구간(차가 들어옴 ~ 나감/멈춤 + 1.5 s)만 잘라 크롭·1.5 배, 글자 없이 인코딩 |

## 재현

```bash
CKPT=runs/course/navvla_reasoning_r41/checkpoints/last/pretrained_model CURV_BOOST_SLOW=1.0 \
CLIPS="lane2:r41_cone_avoid:ob_cone lane2:r41_person_avoid:ob_person lane1:r41_box_lane1_straight:ob_box" \
  bash tools/eval/record_clip.sh
cd eval_out/course/clips && python3 ../../../tools/eval/trim_clip.py frames_r41_cone_avoid r41_cone_avoid.mp4
```

## 미해결

1. r41 인덱스 70·142 오라클 폐루프를 수정된 판정으로 재평가(특히 인덱스 70 박스).
2. 복귀 시점: "past" 문구 기준(중심 2 m 지남)과 시연 복귀(6.3 m 뒤)의 불일치 — 라벨 규칙을 시연에 맞추거나, 오라클
   문구를 차체 길이를 고려해 바꾸기.
