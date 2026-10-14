# 서버 정리 · 연구 모델 노트북 백업 (2026-09-23 10:50)

밤샘 다중물체 실험(docs/experiments/avoidance/20260922_2113)으로 랩서버 디스크가 100% 에 닿아 정리.
사용자 결정: 실패 런 삭제, 필요한 연구 모델은 노트북에 백업 후 서버에는 서빙·학습에
필요한 것만 남긴다.

## 삭제 (서버 `~/sunhong/nav-vla`)

| 항목 | 용량 | 비고 |
|---|---|---|
| `runs/course/navvla_reasoning_r29~r32` | 4.4 GB | 강좌 실험, 전부 실패. 로그·프로브는 `logs/course/` 보존 |
| `runs/navvla_reasoning_r19~r22` | 8.4 GB | 중간 실험 런 (백업 안 함 — r23~r25 처럼 레시피 이력만 문서에) |
| `runs/navvla_reasoning_r4, r11, r16, r17, r18` | 6.5 GB | **노트북 백업 후** 삭제 |
| `runs/navvla_reasoning_r26/27/28` 의 `012500` | 3.3 GB | 중간 체크포인트, `last`(025000) 만 유지 |
| `data/archive_june_stage_a`, `data/packed_v2` | 4.6 GB | 6월 초기 코퍼스 |
| `data/lerobot/v29r`, 스테이징 링크 | 0.4 GB | v32r 이 상위집합 |
| `~/.cache/pip` | 3.3 GB | 캐시 |
| `logs/ollama_serve.log` | 1.5 GB | truncate |

디스크: 100%(2.1 GB) → 96%(42 GB 여유). `runs/` 24 GB → 5.4 GB.

## 서버에 남은 것

- `runs/navvla_reasoning_r26` (데모 기본 서빙), `r27`, `r28`, `navvla_smolvla_v3y` (베이스) — 각 last 만.
- `data/`: 주행 코퍼스(packed_v3y·v9*·stanley·signal·v10*), `lerobot/` 데이터셋들, `course/`.
- 큰 미확인 파일 2개는 그대로: `~/resnet18-training.zip` 73 GB, `~/control_noised_images.zip` 20 GB
  (2025-05, 소유자 미상). 다른 계정 `/home/autolab` (~700 GB) 은 권한 없음.
- `raw_*_30hz` 20 GB 는 노트북 원본 유무 확인 전까지 유지.

## 노트북 백업 (`models/server/`, gitignore)

r4, r11, r16, r17, r18, r26, r27, r28 의 `checkpoints/last/` + v3y last. safetensors
바이트 크기를 서버와 대조해 일치 확인 후 서버 삭제. 목록과 용도는
`models/server/README.md`.
