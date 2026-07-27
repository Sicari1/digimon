#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 사용 한도(5시간/7일) 터미널 표시 도구.

사용법:
  python3 digimon.py               # 한도 카드
  python3 digimon.py --statusline  # 상태줄 한 줄 (Claude Code statusLine 용)
  python3 digimon.py --account 4   # 특정 계정 지정(.claude-4)
"""
import sys, json, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from digitoken import render, limits as limmod


def main():
    ap = argparse.ArgumentParser(add_help=True, description="Claude Code 사용 한도")
    ap.add_argument("cmd", nargs="?", default="card", choices=["card", "status"],
                    help="card(기본)/status")
    ap.add_argument("--statusline", action="store_true", help="상태줄 한 줄 출력")
    ap.add_argument("--account", help="계정 지정(예: .claude-4 또는 4)")
    args = ap.parse_args()

    if args.statusline:
        args.cmd = "status"

    # 상태줄 stdin(JSON) 읽어 이 창의 계정 감지 (transcript_path 기반)
    stdin_json = None
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                stdin_json = json.loads(raw)
    except Exception:
        stdin_json = None

    # --account 수동 지정(4 → .claude-4, 1 → .claude) 우선
    if args.account:
        a = args.account
        if a.isdigit():
            a = ".claude" if a == "1" else f".claude-{a}"
        account = a
    else:
        account = limmod.detect_account(stdin_json)

    # 공식 한도(자동). 상태줄은 논블로킹(캐시 즉시 + 백그라운드 갱신).
    try:
        limits_data = (limmod.fetch_for_statusline() if args.cmd == "status"
                       else limmod.fetch_all())
    except Exception:
        limits_data = None

    if args.cmd == "status":
        print(render.render_statusline(limits_data=limits_data, account=account))
    else:
        print(render.render_card(limits_data=limits_data, account=account))


if __name__ == "__main__":
    main()
