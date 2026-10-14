# L6 사전 등록: SmolVLM2 원본(500M·2.2B)을 계층형의 인지 VLM 으로 쓸 수 있는가 (2026-10-13 22:47)

배경: SmolVLA 모드에서 처음 보는 물체는 L5 위치 층이 다루지 못한다(학습한 이름만). Qwen2.5-VL 7B 는 서버가 필요하다.
SmolVLA 의 VLM 은 SmolVLM2-500M 의 앞 16층이므로, 원본 전체(32층 + LM 헤드)나 같은 계열 2.2B 를 노트북에서 "무엇이 보이는가" 담당으로 쓸 수 있는지 잰다.
위치는 재지 않는다(G0: SmolVLM2-500M 위치 질문 ≈ 우연, 위치는 L5 담당).

## 고정 (실행 전)

- 모델 3개, 같은 질문, 탐욕 생성(온도 0):
  - `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` (SmolVLA 백본의 원본)
  - `HuggingFaceTB/SmolVLM2-2.2B-Instruct`
  - 기준: `qwen2.5vl:7b` (서버 ollama)
- 질문: "List every standalone object you can see on or beside the road in this image (not road markings, grass, flowers or sky). Answer with a comma-separated list of short names only."
- 이미지: 640×480 원본 그대로.
- 프레임과 정답:
  - **주 세트**: 여러 물체 장면 multi_A(말·빨간 꼬깔·강아지 인형), multi_B(강아지 인형·공룡·파란 꼬깔·쓰레기통), multi_C(공룡·상자·말),
    오늘 GUI 화면 live_now(강아지 인형·말·쓰레기통), 오른쪽 2 m 단일 물체 12/18/25 m(말·강아지·공룡 옆/뒷모습, 노란 꼬깔·쓰레기통·의자·상자).
    `far_go_horse_-2s_12` 는 강아지가 찍힌 프레임이라 정답을 강아지로 둔다.
  - **가까운 세트**: 정면 단일 물체(빨간 꼬깔 8~35 m, 강아지·말·공룡 2종 앞/뒷모습 5~12 m).
- 채점(동의어 표, 대소문자 무시):
  강아지 = dog/puppy/teddy/plush/stuffed, 말 = horse/pony/foal, 공룡 = dinosaur/dino/t-rex/tyrannosaurus/triceratops/raptor,
  꼬깔 = cone, 쓰레기통 = trash/bin/garbage/waste/can/bucket, 의자 = chair/seat, 상자 = box/crate/cube/cardboard/package.
  - **재현율** = 정답 물체 중 이름이 나온 비율.
  - **헛것** = 정답·배경어(road, grass, flower, sky, line, lane, marking, tree, field, parking, curb, sidewalk)에 안 걸리는 이름 수.

## 기각선

1. 주 세트 재현율이 Qwen 의 절반 미만이면 그 모델은 "인지 VLM 으로 쓸 수 없음".
2. 1 을 통과해도 헛것이 프레임당 Qwen 의 2배를 넘으면 "뭐가 보여?" 답변용으로 쓰지 않는다(없는 물체를 말하므로).
3. 둘 다 통과한 모델만 노트북 대화·요청 해석 후보로 GUI 에 붙인다.

## 결과 (22:52)

코드 `server/code/course/l6_perceiver_bench.py`, 원자료 `media/20261013_l6_result.json`. 노트북 GPU(SmolVLM2 bf16), Qwen 은 서버. 프레임 81장, 모델당 약 80초.

| 모델 | 주 세트 재현율 (43) | 헛것/프레임 (사전 지표) | 가까운 세트 재현율 (47) | 판정 |
|---|---|---|---|---|
| qwen2.5vl:7b | **0.86** (37) | 0.12 | 0.38 | 기준 |
| SmolVLM2-500M | 0.60 (26) | **4.59** | 0.32 | 1 통과, **2 걸림** |
| SmolVLM2-2.2B | 0.47 (20) | **0.47** | 0.21 | 1 겨우 통과(기준 0.43), **2 걸림** |

- 기각선 1(재현율이 Qwen 의 절반 0.43 이상): 둘 다 통과. 2.2B 는 0.47 로 경계.
- **기각선 2(헛것이 Qwen 의 2배 0.24 이하): 둘 다 걸림** → 두 모델 모두 "뭐가 보여?" 답변·인지 VLM 으로 쓰지 않는다.
- 사후 확인(판정에 안 씀):
  - 500M 은 34장 중 11장에서 같은 단어를 끝없이 반복했다("horse, horse, horse, …"). 반복을 한 번으로 세도 헛것 0.65/프레임(Qwen 의 5배).
  - 두 모델 모두 없는 **자동차(car)** 를 가장 많이 지어냈다(500M 13회, 2.2B 9회, 주 세트). 2.2B 는 그 밖에 bench·truck·sheep·ant.
  - 2.2B 가 500M 보다 재현율이 낮다. 크기가 커져도 이 장면(멀리 있는 작은 장난감 물체)에서는 나아지지 않았다.
  - 가까운 세트(정면 5~12 m 앞/뒷모습 동물)는 Qwen 도 0.38 로 낮다. 동물 앞/뒷모습은 세 모델 모두 어렵다(되묻기 실험의 결론과 같음).

## 해석

- 같은 계열 원본 VLM 을 위에 붙여도 "무엇이 보이는가"를 믿고 말할 수준이 아니다. 이름은 절반가량 맞히지만 없는 물체를 Qwen 의 4~5배 지어낸다.
- 그러므로 SmolVLA 모드의 "처음 보는 물체" 문제는 SmolVLM2 로 풀리지 않는다. 처음 보는 물체·추상 지칭은 7B 급 VLM(Qwen) 계층형으로 하고, SmolVLA 모드는 "학습한 물체만"으로 둔다.
- 강의 서술: "SmolVLA 백본의 원본(500M)과 같은 계열 2.2B 를 인지 모델로 시험했지만, 없는 물체를 지어내는 비율이 Qwen 7B 의 4배 이상이라 쓰지 않았다."

## 한계

1. 질문 하나, 탐욕 생성만 썼다. 반복 억제(repetition penalty)나 다른 질문 형식은 재지 않았다(사후 조정이 되므로 따로 사전 등록 필요).
2. 정답은 사람이 사진을 보고 적었다. multi_A 의 꼬깔 뒤 의자는 일부만 보여 정답에 넣지 않았다(말해도 헛것으로 세지 않음 — 동의어 표에 chair 가 있어 맞음으로도 안 셈).
3. 장면 수가 작다(주 세트 34장).
