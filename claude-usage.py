#!/usr/bin/env python3
"""Claude 사용량 표시 도구.

모드 두 가지:
  --statusline : Claude Code statusLine 용. stdin으로 오는 세션 JSON만 사용(네트워크 X).
  --box        : 터미널 시작/`cusage` 용. OAuth usage API를 호출해 상태 박스를 그린다.

usage API 응답은 이 스크립트가 놓인 계정 디렉터리의 usage-cache.json 에 60초 캐시한다.
"""

from __future__ import annotations

import json
import os
import sys
import time
import unicodedata
from datetime import datetime, timezone

# 글리프 정책: Consolas / Cascadia Mono / Malgun 폴백에서 전부 1칸으로 그려지는
# 문자만 쓴다. 확인 결과 Consolas에는 ▰ ▱ ◆ ↺ ⚡ 글리프가 없어서 Malgun(2칸)으로
# 폴백되며 줄이 밀린다. 안전 집합: █ ░ ● ○ · 와 박스 드로잉 ─ │ ┌ ┐ └ ┘ ├ ┤
# 그래도 깨지는 터미널이면 CLAUDE_USAGE_ASCII=1 — 바와 박스 프레임까지 전부 ASCII로
# 바꾼다. (위 문자들은 모두 East Asian Width = Ambiguous 라서, 이걸 2칸으로 그리는
# 터미널에서는 프레임 자체가 2배 폭이 되어 패딩 계산으로는 못 고친다.)
ASCII_ONLY = os.environ.get("CLAUDE_USAGE_ASCII") == "1"

# 박스 프레임: 좌상 우상 좌하 우하 가로 세로 좌T 우T
F_TL, F_TR, F_BL, F_BR, F_H, F_V, F_LT, F_RT = (
    ("+", "+", "+", "+", "-", "|", "+", "+") if ASCII_ONLY else ("┌", "┐", "└", "┘", "─", "│", "├", "┤")
)
DOT_ON, DOT_OFF, MID = ("*", "o", "|") if ASCII_ONLY else ("●", "○", "·")

# 이 스크립트가 놓인 계정 디렉터리(~/.claude, ~/.claude-2 ...)를 기준으로 잡는다.
# 그래야 계정마다 복사해도 각자의 자격증명·캐시를 쓴다.
BASE = os.path.dirname(os.path.abspath(__file__))
CRED = os.path.join(BASE, ".credentials.json")
CACHE = os.path.join(BASE, "usage-cache.json")
CACHE_TTL = 60  # 초

R = "\033[0m"
B = "\033[1m"
DIM = "\033[2m"
CY = "\033[38;5;80m"
GR = "\033[38;5;114m"
YL = "\033[38;5;179m"
RD = "\033[38;5;174m"
OR = "\033[38;5;173m"  # Claude 오렌지
GY = "\033[38;5;245m"


# ── 공통 ──────────────────────────────────────────────────────────────────────
def dwidth(s: str) -> int:
    """ANSI 코드를 제외한 터미널 표시 폭(한글 2칸)."""
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            j = s.find("m", i)
            i = len(s) if j < 0 else j + 1
            continue
        out += 2 if unicodedata.east_asian_width(s[i]) in "WF" else 1
        i += 1
    return out


def _bar(pct: float, width: int) -> tuple[str, str, str]:
    pct = max(0.0, min(100.0, pct))
    fill = int(round(pct / 100 * width))
    on, off = ("#", "-") if ASCII_ONLY else ("█", "░")
    col = GR if pct < 50 else (YL if pct < 80 else RD)
    return col, on * fill, off * (width - fill)


def bar(pct: float, width: int = 18) -> str:
    col, on, off = _bar(pct, width)
    return f"{col}{on}{R}{DIM}{off}{R}"


def minibar(pct: float, width: int = 10) -> str:
    col, on, off = _bar(pct, width)
    return f"{col}{on}{R}{DIM}{off}{R}"


def fmt_left(ts: float) -> str:
    """남은 시간을 2h13m / 34m 형태로."""
    sec = int(ts - time.time())
    if sec <= 0:
        return "곧"
    h, m = sec // 3600, (sec % 3600) // 60
    if h >= 48:
        return f"{h // 24}d{h % 24}h"
    return f"{h}h{m:02d}m" if h else f"{m}m"


# ── usage API ────────────────────────────────────────────────────────────────
OAUTH = os.path.join(BASE, ".oauth-token")


def token() -> str | None:
    env = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    try:
        with open(CRED) as f:
            return json.load(f)["claudeAiOauth"]["accessToken"]
    except Exception:
        pass
    # 5번 계정처럼 .credentials.json 없이 .oauth-token(setup-token)만 있는 경우
    try:
        with open(OAUTH) as f:
            t = f.read().strip()
            if t:
                return t
    except Exception:
        pass
    return env


def fetch_usage(force: bool = False) -> dict | None:
    if not force:
        try:
            st = os.stat(CACHE)
            if time.time() - st.st_mtime < CACHE_TTL:
                with open(CACHE) as f:
                    return json.load(f)
        except Exception:
            pass

    tok = token()
    if not tok:
        return None
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {tok}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
    except Exception:
        try:  # 실패 시 오래된 캐시라도 재활용
            with open(CACHE) as f:
                return json.load(f)
        except Exception:
            return None
    try:
        tmp = CACHE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, CACHE)
    except Exception:
        pass
    return data


def parse_iso(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def cred_state() -> str:
    try:
        with open(CRED) as f:
            d = json.load(f)["claudeAiOauth"]
        exp = d.get("expiresAt", 0) / 1000
        plan = (d.get("subscriptionType") or "?").upper()
        if exp > time.time():
            return f"{GR}{DOT_ON}{R} {plan}  {DIM}토큰 만료 {datetime.fromtimestamp(exp):%m-%d %H:%M}{R}"
        return f"{RD}{DOT_ON}{R} {plan}  {RD}토큰 만료됨 - claude /login{R}"
    except Exception:
        pass
    # oauth-token(setup-token)만 있는 계정: 만료 정보는 없지만 로그인은 살아있다
    if os.path.exists(OAUTH):
        return f"{GR}{DOT_ON}{R} OAUTH  {DIM}setup-token{R}"
    return f"{DIM}{DOT_OFF} 로그인 정보 없음{R}"


def today_tokens() -> tuple[int, int]:
    """오늘자 세션 jsonl에서 토큰 합계와 세션 수."""
    root = os.path.join(BASE, "projects")
    today = datetime.now().strftime("%Y-%m-%d")
    total, sessions = 0, 0
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".jsonl"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                if datetime.fromtimestamp(os.stat(p).st_mtime).strftime("%Y-%m-%d") != today:
                    continue
            except OSError:
                continue
            hit = 0
            try:
                with open(p, errors="replace") as f:
                    for line in f:
                        if '"usage"' not in line or not line.startswith('{"parentUuid"') and '"assistant"' not in line:
                            continue
                        try:
                            d = json.loads(line)
                        except Exception:
                            continue
                        if not str(d.get("timestamp", "")).startswith(today):
                            continue
                        u = (d.get("message") or {}).get("usage")
                        if not isinstance(u, dict):
                            continue
                        total += (
                            u.get("input_tokens", 0)
                            + u.get("output_tokens", 0)
                            + u.get("cache_creation_input_tokens", 0)
                            + u.get("cache_read_input_tokens", 0)
                        )
                        hit = 1
            except OSError:
                continue
            sessions += hit
    return total, sessions


# ── 박스 렌더 ────────────────────────────────────────────────────────────────
INNER = 57  # 기존 Quant 박스와 같은 총폭 59


def row(content: str) -> str:
    v = f"{B}{CY}{F_V}{R}"
    pad = INNER - dwidth(content)
    if pad < 0:  # 넘치면 잘라서 테두리를 뚫지 않게 한다
        import re as _re

        plain = _re.sub(r"\033\[[0-9;]*m", "", content)
        while plain and dwidth(plain) > INNER - 1:
            plain = plain[:-1]
        content, pad = plain + "~", INNER - dwidth(plain) - 1
    return f"{v}{content}{' ' * max(0, pad)}{v}"


def sep(left: str, right: str) -> str:
    return f"{B}{CY}{left}{F_H * INNER}{right}{R}"


def render_box(force: bool = False) -> str:
    u = fetch_usage(force=force)
    L = []
    L.append("")
    L.append(sep(F_TL, F_TR))

    head_l = f"  {B}{OR}Claude Code 사용량{R}"
    head_r = f"{DIM}{datetime.now():%Y-%m-%d %H:%M}{R}  "
    gap = INNER - dwidth(head_l) - dwidth(head_r)
    v = f"{B}{CY}{F_V}{R}"
    L.append(f"{v}{head_l}{' ' * max(1, gap)}{head_r}{v}")
    L.append(sep(F_LT, F_RT))
    L.append(row(f"  {cred_state()}"))

    if not u:
        # 5번처럼 setup-token만 있는 계정은 usage 스코프가 없어 403이 난다
        if not os.path.exists(CRED) and os.path.exists(OAUTH):
            L.append(row(f"  {DIM}setup-token 계정 - 사용량 API 조회 권한 없음{R}"))
        else:
            L.append(row(f"  {RD}사용량 조회 실패{R} {DIM}(네트워크/토큰 확인){R}"))
    else:
        for key, label in (("five_hour", "5시간"), ("seven_day", "주간 "), ("seven_day_opus", "Opus "), ):
            w = u.get(key)
            if not isinstance(w, dict) or w.get("utilization") is None:
                continue
            pct = float(w["utilization"])
            reset = parse_iso(w.get("resets_at"))
            when = ""
            if reset:
                when = f"{datetime.fromtimestamp(reset):%m-%d %H:%M} ({fmt_left(reset)})"
            pcol = GR if pct < 50 else (YL if pct < 80 else RD)
            L.append(
                row(f"  {label}  {bar(pct)} {pcol}{B}{pct:5.1f}%{R}  {DIM}{when}{R}")
            )

        ex = u.get("extra_usage") or {}
        if ex.get("is_enabled"):
            used = float(ex.get("used_credits") or 0)
            lim = float(ex.get("monthly_limit") or 0) / 100
            L.append(row(f"  {DIM}추가 크레딧  ${used:,.2f} / ${lim:,.2f} (월){R}"))

    tok, sess = today_tokens()
    L.append(sep(F_LT, F_RT))
    L.append(
        row(f"  {DIM}오늘 {tok / 1_000_000:,.1f}M tok {MID} {sess}세션      다시 보기: {R}{OR}cusage{R}")
    )
    L.append(sep(F_BL, F_BR))
    L.append("")
    return "\n".join(L)


# ── statusLine 렌더 ──────────────────────────────────────────────────────────
def render_statusline() -> str:
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    return render_statusline_from(d)


def render_statusline_from(d: dict) -> str:
    model = (d.get("model") or {}).get("display_name") or "?"
    cwd = (d.get("workspace") or {}).get("current_dir") or d.get("cwd") or ""
    name = os.path.basename(cwd.rstrip("/")) or "/"
    eff = (d.get("effort") or {}).get("level")
    fast = d.get("fast_mode")
    cost = (d.get("cost") or {}).get("total_cost_usd")

    ctx = d.get("context_window") or {}
    ctx_pct = ctx.get("used_percentage")

    line1 = [f"{OR}{DOT_ON}{R} {B}{model}{R}"]
    if eff:
        line1.append(f"{GY}{eff}{R}")
    if fast:
        line1.append(f"{YL}fast{R}")
    line1.append(f"{CY}{name}{R}")
    ws = d.get("workspace") or {}
    if ws.get("git_worktree"):
        line1.append(f"{DIM}wt:{ws['git_worktree']}{R}")
    if isinstance(cost, (int, float)) and cost > 0:
        line1.append(f"{DIM}${cost:.2f}{R}")

    line2 = []
    if isinstance(ctx_pct, (int, float)):
        p = float(ctx_pct)
        col = GR if p < 60 else (YL if p < 85 else RD)
        line2.append(f"{DIM}ctx{R} {minibar(p)} {col}{p:.0f}%{R}")

    rl = d.get("rate_limits") or {}
    for key, label in (("five_hour", "5h"), ("seven_day", "week")):
        w = rl.get(key)
        if not isinstance(w, dict):
            continue
        p = w.get("used_percentage")
        if p is None:
            continue
        p = float(p)
        col = GR if p < 50 else (YL if p < 80 else RD)
        left = f" {DIM}~{fmt_left(w['resets_at'])}{R}" if w.get("resets_at") else ""
        line2.append(f"{DIM}{label}{R} {minibar(p)} {col}{p:.0f}%{R}{left}")

    out = f" {DIM}{MID}{R} ".join(line1)
    if line2:
        out += "\n" + "   ".join(line2)
    return out


# ── 자체 점검 ────────────────────────────────────────────────────────────────
# 안전 문자: Consolas / Cascadia Mono / Malgun 모두 1칸으로 그리는 것만 허용
SAFE_GLYPHS = set("█░●○·─│┌┐└┘├┤┬┴")


def self_check() -> int:
    import re as _re

    strip = lambda s: _re.sub(r"\033\[[0-9;]*m", "", s)
    bad = 0

    print(f"── 박스 줄 폭 점검 (기대: {INNER + 2}) ──")
    for i, line in enumerate(render_box().split("\n")):
        if not line.strip():
            continue
        plain = strip(line)
        w = dwidth(line)
        ok = w == INNER + 2
        if not ok:
            bad += 1
        print(f"  {'OK ' if ok else 'BAD'} 폭={w:3d}  {plain[:40]}")

    print("\n── 위험 글리프 점검 ──")
    sample = (
        render_box()
        + "\n"
        + render_statusline_from(
            {
                "model": {"display_name": "Opus 5"},
                "workspace": {"current_dir": "/x/y"},
                "effort": {"level": "high"},
                "fast_mode": True,
                "cost": {"total_cost_usd": 1.2},
                "context_window": {"used_percentage": 28},
                "rate_limits": {
                    "five_hour": {"used_percentage": 23, "resets_at": time.time() + 9000},
                    "seven_day": {"used_percentage": 3, "resets_at": time.time() + 400000},
                },
            }
        )
    )
    risky = {}
    for ch in strip(sample):
        if ch.isascii() or "가" <= ch <= "힣":
            continue
        if ch in SAFE_GLYPHS:
            continue
        risky[ch] = risky.get(ch, 0) + 1
    if risky:
        bad += 1
        for ch, n in risky.items():
            print(f"  BAD {ch!r} U+{ord(ch):04X} ({unicodedata.east_asian_width(ch)}) x{n}")
    else:
        print("  OK  안전 집합 밖의 문자 없음")

    print(f"\n결과: {'모두 정상' if bad == 0 else f'문제 {bad}건'}")
    return 1 if bad else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--box"
    if mode == "--check":
        sys.exit(self_check())
    if mode == "--statusline":
        print(render_statusline())
    elif mode == "--json":
        print(json.dumps(fetch_usage(force="--force" in sys.argv), ensure_ascii=False, indent=2))
    else:
        print(render_box(force="--force" in sys.argv))
