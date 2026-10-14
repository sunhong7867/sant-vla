# SANT-VLA 이름 변경 · 2026-09-15

SANT-VLA = Shared-backbone Action–Narration Training.
이전 연구 이름은 NAV-VLA입니다.

| 대상 | 현재 이름 |
| --- | --- |
| 연구 이름 | SANT-VLA |
| 로컬 워크스페이스 | /home/sh/ROS2_project/sant-vla |
| GitHub | https://github.com/sunhong7867/sant-vla |
| ROS/Python 패키지 | sant_vla_pkg |

기존 로컬 워크스페이스 경로는 새 폴더로 연결되는 심볼릭 링크로 유지합니다.
과거 일지, 체크포인트 이름, 데이터 파일 이름, nav_vla_index.jsonl, IPC 소켓은 원래 식별자를 유지합니다.
원격 학습 서버의 ~/sunhong/nav-vla 경로는 해당 서버를 이전하지 않았으므로 유지합니다.
NAV_VLA_WHISPER_MODEL 환경변수도 호환되며 새 이름 SANT_VLA_WHISPER_MODEL이 우선합니다.

새 체크아웃에서는 source /opt/ros/jazzy/setup.bash 후 colcon build --symlink-install을 실행합니다.
이름 변경은 모델 가중치, 학습 목적함수 또는 성능 결과의 변경을 뜻하지 않습니다.
