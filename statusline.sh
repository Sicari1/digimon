#!/usr/bin/env bash
# Claude Code statusLine — 모델/디렉터리/컨텍스트 + 5시간·주간 사용량 바.
# 세션 JSON을 stdin으로 받아 그대로 넘긴다(네트워크 호출 없음).
# 자기 옆의 claude-usage.py 를 부르므로 계정 디렉터리마다 복사해도 동작한다.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "$DIR/claude-usage.py" --statusline
