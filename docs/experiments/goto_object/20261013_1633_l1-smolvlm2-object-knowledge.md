# L1: SmolVLM2-500M 백본은 물체를 아는가 (2026-10-13 16:33)

질문: SmolVLA 에 물체 지식이 있는가. 3층으로 나눠 잰다.
L1 원본 VLM(상한) / L2 SmolVLA 안 16층 특징 / L3 행동(이미 음성: b1 22/42 vs b0 23/42).
이 문서는 **L1 만**이다.

## 설정

- 모델: `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` **32층 전체 + 자체 LM 헤드**, bf16, greedy.
  SmolVLA 는 이 중 16층만 쓰고 LM 헤드가 없으므로 이 결과는 **상한**이지 SmolVLA 의 지식이 아니다.
- 이미지 37장 (`media/20261013_1633_l1_object_set.jpg`):
  - sim 렌더 크롭 10 (`eval_out/course/clips/objects_*_row.png`): 차 5, 상자 2, 꼬깔, 원기둥, 사람 모형
  - Fuel 썸네일 27 (흰 배경 근접, 모델당 2시점): 곰인형, 공룡 3종, 봉제 인형(`dog`), 말, 안드로이드 로봇, 그릇, 소화전, 쓰레기통, 의자, 공, 바나나, 오렌지
- 질문: Q1 "What is the main object…" (자유 응답), Q2 정답 라벨 예/아니오, Q3 무작위 오답 라벨 예/아니오(예-편향 대조).
- 코드: `server/code/course/l1_build_object_set.py`, `l1_smolvlm2_object_naming.py`. 원자료 `media/20261013_1633_l1_result.json`.

**Fuel 이름 함정 추가:** `googleresearch/dog` 는 개가 아니라 **베이지 봉제 인형**이다(썸네일 확인).
그래서 "teddy bear"/"stuffed animal" 응답을 정답으로 채점했다.

## 결과

| | 이름 맞힘 (Q1) | Q2 정답에 Yes | Q3 오답에 Yes |
|---|---|---|---|
| sim 렌더 | 8/10 | 7/10 | 0/10 |
| 썸네일 | 22/27 | 21/27 | 0/27 |
| **합계** | **30/37** | 28/37 | **0/37** |

- 맞힘: 차 6/6, **곰인형 2/2**, 봉제 인형 2/2("teddy bear"·"stuffed animal"), 공룡 5/6(T-Rex·Triceratops 종까지), 말·로봇·그릇·소화전·의자·바나나.
- 틀림: sim 사람 모형 → "Cylinder"(원시 도형 모형이라 정당), 상자 → "Rubber block", 공룡 1 → "Humanoid figure", 쓰레기통 1 → "Tumbler with lid", 공 → "Red circle", 오렌지 2 → "Brown egg/sphere".
- Q2/Q3: 오답에는 한 번도 Yes 를 안 했다(예-편향 없음). 대신 **보수 편향**이 있다 — 소화전·쓰레기통은 이름은 맞히면서 "Is there a fire hydrant?" 에는 No (4/4).
  예/아니오 형식은 이 모델에서 이름 질문보다 약하다. (봉제 인형에 "Is there a dog?" No 2/2 는 라벨이 틀린 것이라 오히려 맞다.)

## 해석

- **L1 양성: 원본 500M 백본은 곰인형·공룡·차·말·의자를 이름으로 안다.** "SmolVLM 이 원래 물체를 모른다"는 설명은 성립하지 않는다.
- 한계 — 이 수치를 주행 장면에 옮기면 안 된다:
  1. 전부 **화면 가운데 큰 단일 물체**다. 정책 카메라(62.2°, 640×480)에서 4~10 m 앞 물체는 수십 픽셀이고 여러 개가 함께 있다.
     이전 측정에서 SmolVLM2-500M 은 위치 질문에 ≈ 우연이었다(goto 메모 G0).
  2. 실물 사진은 없다. 썸네일은 스캔 모델 렌더다.
  3. 32층 + LM 헤드 결과다. SmolVLA 는 16층에서 끊는다.
- 다음 = **L2**: 같은 이미지(+ 정책 카메라 시점 캡처)를 `smolvla_base` 와 g5d 의 16층에 넣고 선형 프로브.
  g5d 는 `train_expert_only` 를 확인해야 한다 — v3y 설정은 `train_expert_only: false`, `freeze_vision_encoder: false` 였다(VLM 까지 학습 → 지식이 깎였을 수 있음).
  base 는 맞히고 g5d 는 못 하면 미세조정이 지운 것, 둘 다 맞히면 정보는 있는데 행동(L3)이 안 쓰는 것.
