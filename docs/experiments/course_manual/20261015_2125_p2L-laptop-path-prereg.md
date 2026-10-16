# p2L 사전 등록 — 노트북 경로 (연구실 서버 없이) (2026-10-15 21:25)

## 왜
사용자(21:20): "단기강좌 실습용은 연구실 서버 안 쓴다고 하지 않았나". p2 19/20 은 정책 실행 · VLM 이 모두 연구실 서버(3090)였다.
강좌 학생 경로 = 노트북에서 시뮬 + 정책 서버 + VLM. 이 경로에서 같은 성능이 나오는지, 노트북 자원으로 돌아가는지 잰다.

## 조건
- 정책: p2 체크포인트 그대로 (`ros2_vla/data/models/p2/pretrained_model`), **노트북 RTX 4060 8 GB** 의 `scripts/serve.sh` (.venv-policy, lerobot 0.4.4).
- VLM: **노트북 ollama** — L3 = `qwen2.5vl:3b` (3.2 GB), L7 = `qwen2.5vl:7b` (6.0 GB). 각 P 20 회, p2 와 같은 시드·장면.
- 순서: L3 먼저 (메모리 여유가 큰 쪽). L7 은 L3 가 끝나고 GPU·RAM 기록을 본 뒤.
- 기록: 5 초마다 nvidia-smi (GPU 메모리·사용률), free (RAM·스왑), ollama ps (VLM 이 GPU/CPU 어디에 있는지).
- 시작 조건: 가용 RAM ≥ 6 GB (사용자가 브라우저·ChatGPT 를 닫은 뒤). 스왑이 다 찬 상태로는 시작하지 않는다 (08-28 프리즈).
- 노트북 사양: MSI Thin A15 B7VF, DDR5 16 GB, RTX 4060 Laptop 8 GB. **학생 노트북은 더 낮을 수 있다.**

## 기각선
1. **L3 P < 14/20 → "노트북 3B 로는 부족"**. L7 P < 14/20 → "노트북 7B 로도 부족".
2. 실행 중 가용 RAM < 1 GB 또는 스왑 가득 + 화면 멈춤 → **"이 사양으로 시뮬 + 정책 + VLM 동시 실행 불가"** (점수와 별개로 기각).
3. 정책 추론 지연(policy_node latency_ms) 중앙값 > 300 ms → 10 Hz 제어에 못 맞춤으로 따로 적는다.

예상(적어 둠): L3 는 박스가 덜 정확해 15~18/20, L7 은 GPU 8 GB 를 넘어 ollama 가 일부 CPU 로 내려가 VLM 응답이 수 초로 느려짐.

## 결과 (21:23~21:35) — **기각선 2: 이 노트북에서 시뮬 + 정책 + VLM(ollama) 동시 실행 불가**

- 정책 서버(노트북 4060): 22 s 에 적재, 데우기 추론 211 ms (서버 3090 88 ms). 돌아가는 데는 문제 없음. GPU 약 1.1 GB.
- L3 첫 두 시행(P0 · P1): goal_node 의 VLM 요청이 전부 HTTP 500 → 차 안 움직임. 체인 중단.
- ollama 0.19 로그: `model requires more system memory (9.0 GiB) than is available (9.0 GiB)` — GPU 여유 5.5 GiB(시뮬 + 정책 1.7 GB 사용)라
  모델을 GPU 에 다 못 올리고 나머지를 RAM 에 두려다 실패. ollama 의 qwen2.5vl 전체 메모리 추정이 3B ≈ 9~10 GiB, 7B ≈ 9.6 GiB 이상.
- 정책 서버를 내리고(시뮬만) 다시: **3B 는 GPU 를 안 쓰고 100 % CPU 로 적재(10 GB RAM), 첫 답 82 s**. **7B 는 적재 실패**(9.6 > 9.5 GiB).
- 결론: 이 노트북(16 GB RAM · 4060 8 GB, 브라우저·ChatGPT 닫은 상태)에서도 ollama Qwen2.5-VL 은 강좌 경로로 못 쓴다. 학생 노트북은 더 낮을 수 있다.
- 정책 실행 자체는 노트북에서 된다 — 막히는 것은 VLM.
- 미측정 대안: VLM 을 팀 Colab(T4 16 GB)에서 돌리고 터널 / transformers 4-bit + 작은 입력 영상 / 더 작은 인지 모델.
