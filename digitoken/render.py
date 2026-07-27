# -*- coding: utf-8 -*-
"""터미널 렌더 — 공식 5시간/7일 사용 한도만 표시. ANSI 직접(의존성 없음)."""
from . import limits as limmod

DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"
GOLD = "\x1b[38;2;235;190;70m"
CYAN = "\x1b[38;2;120;200;220m"
RED = "\x1b[38;2;220;110;110m"


def bar(frac, width=16):
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


def _util_color(u):
    return RED if u >= 85 else (GOLD if u >= 60 else CYAN)


def render_card(agg=None, limits_data=None, cfg=None, account=None):
    """공식 5시간/7일 사용 한도 카드."""
    info = []
    if limits_data and limits_data.get("accounts"):
        acc, r, _ = limmod.current(limits_data, account)
        if r and "error" not in r:
            fh, sd = r.get("five_hour", {}), r.get("seven_day", {})
            u5 = fh.get("util") or 0
            fc = limmod.forecast_5h(acc, limits_data)
            fcs = f"  {DIM}~{fc:.1f}h후 100%{RESET}" if fc is not None else ""
            c5 = _util_color(u5)
            info.append(f"{DIM}계정{limmod.account_index(acc)}{RESET} 5시간 {c5}{bar(u5/100,16)}{RESET} {u5:>3.0f}%  {DIM}리셋 {limmod.reset_delta_str(fh.get('resets_at'))}{RESET}{fcs}")
            u7 = sd.get("util") or 0
            c7 = _util_color(u7)
            info.append(f"{DIM}    {RESET} 7일   {c7}{bar(u7/100,16)}{RESET} {u7:>3.0f}%  {DIM}리셋 {limmod.reset_delta_str(sd.get('resets_at'))}{RESET}")
        else:
            info.append(f"{DIM}현재 계정 한도 조회 실패{RESET}")
        # 계정별 5h 요약
        parts = []
        for i, a in enumerate(limmod.ACCOUNTS):
            rr = limits_data["accounts"].get(a)
            if rr and "error" not in rr:
                uu = (rr.get("five_hour") or {}).get("util") or 0
                mark = "*" if a == acc else " "
                parts.append(f"{mark}{i+1}:{uu:.0f}")
        if parts:
            info.append(f"{DIM}계정별5h {' '.join(parts)}{RESET}")
    else:
        info.append(f"{DIM}공식 한도 API 미응답{RESET}")

    header = f"{DIM}┌─ {RESET}{BOLD}Claude Code 사용 한도{RESET} {DIM}───────────────┐{RESET}"
    footer = f"{DIM}└{'─'*40}┘{RESET}"
    out = ["", header, ""] + ["  " + line for line in info] + ["", footer, ""]
    return "\n".join(out)


def render_statusline(agg=None, limits_data=None, account=None):
    """상태줄 한 줄 — 공식 5시간/7일 사용률만."""
    if limits_data and limits_data.get("accounts"):
        acc, r, _ = limmod.current(limits_data, account)
        n = limmod.account_index(acc)
        if r and "error" not in r:
            fh = r.get("five_hour") or {}
            sd = r.get("seven_day") or {}
            u5 = fh.get("util") or 0
            u7 = sd.get("util") or 0
            r5 = limmod.reset_delta_str(fh.get("resets_at")) if fh.get("resets_at") else ""
            r7 = limmod.reset_delta_str(sd.get("resets_at")) if sd.get("resets_at") else ""
            s5 = f"5시간 {u5:.0f}%" + (f" (리셋 {r5})" if r5 else "")
            s7 = f"7일 {u7:.0f}%" + (f" (리셋 {r7})" if r7 else "")
            return f"계정{n}  │  {s5}  │  {s7}"
        return f"계정{n}  │  한도 조회 실패"
    return "한도 조회중…"
