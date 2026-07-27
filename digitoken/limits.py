# -*- coding: utf-8 -*-
"""공식 5시간/7일 사용 한도 — Claude OAuth usage API 에서 자동 취득(상한 입력 불필요).

- 소스: GET https://api.anthropic.com/api/oauth/usage (계정별 .credentials.json 의 accessToken).
  응답: five_hour.utilization(%), five_hour.resets_at, seven_day.* .
- 6계정 각각 조회. 현재 계정(~/.claude-current-index)을 대표로 보여준다.
- 번인 예측: utilization 표본을 캐시에 남겨 증가율(%/h)로 100% 도달 시각을 추정.
- 캐시 TTL 로 API 호출을 제한(상태줄이 자주 불러도 부담 없게).
"""
import json, time, os, re
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
HOME = Path.home()
ACCOUNTS = [".claude", ".claude-2", ".claude-3", ".claude-4", ".claude-5", ".claude-6"]
INDEX_FILE = HOME / ".claude-current-index"
CACHE = Path(__file__).resolve().parent.parent / "cache" / "limits_cache.json"
TTL = 180  # 초 — 한도는 천천히 변하고, usage API 가 429(레이트리밋)를 걸어서 과호출 금지.


def _now():
    return time.time()


def _token(acc):
    """계정 accessToken (없거나 만료 임박이면 그래도 반환 — 호출해보고 실패시 처리)."""
    for name in (".credentials.json", ".oauth-token"):
        p = HOME / acc / name
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(d, dict):
            oa = d.get("claudeAiOauth") or d
            tok = oa.get("accessToken") or oa.get("access_token")
            if tok:
                return tok
        if isinstance(d, str):
            return d
    return None


def current_index():
    try:
        return int(INDEX_FILE.read_text().strip())
    except Exception:
        return 0


def _fetch_one(acc):
    import requests
    tok = _token(acc)
    if not tok:
        return None
    try:
        r = requests.get(ENDPOINT, timeout=6, headers={
            "Authorization": f"Bearer {tok}",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-version": "2023-06-01",
            "User-Agent": "digitoken",
        })
        if r.status_code != 200:
            return {"error": r.status_code}
        d = r.json()
        return {
            "five_hour": {"util": d.get("five_hour", {}).get("utilization"),
                          "resets_at": d.get("five_hour", {}).get("resets_at")},
            "seven_day": {"util": d.get("seven_day", {}).get("utilization"),
                          "resets_at": d.get("seven_day", {}).get("resets_at")},
        }
    except Exception as e:
        return {"error": str(e)}


def _load_cache():
    try:
        return json.loads(CACHE.read_text())
    except Exception:
        return {}


def _save_cache(c):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(c))
    except Exception:
        pass


def fetch_all(force=False):
    """계정별 한도 + 번인 예측. TTL 캐시. 6계정 동시 요청(최악 ~6s).
    {accounts:{acc:{five_hour,seven_day}}, samples:..., ts:...}"""
    cache = _load_cache()
    if not force and cache.get("ts") and (_now() - cache["ts"] < TTL):
        return cache
    targets = [a for a in ACCOUNTS if (HOME / a / "projects").is_dir()]
    prev = cache.get("accounts", {})

    def _merge(acc, res):
        # 조회 실패(429/네트워크 등)면 직전 정상값 유지 → 표시가 '한도?'로 깜빡이지 않게.
        if (res is None or "error" in res) and acc in prev and "error" not in prev[acc]:
            return dict(prev[acc], stale=True)
        return res

    accounts = {}
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(targets) or 1) as ex:
            for acc, res in zip(targets, ex.map(_fetch_one, targets)):
                res = _merge(acc, res)
                if res is not None:
                    accounts[acc] = res
    except Exception:
        for acc in targets:
            res = _merge(acc, _fetch_one(acc))
            if res is not None:
                accounts[acc] = res
    # 번인 표본 갱신(계정별 five_hour util)
    samples = cache.get("samples", {})
    now = _now()
    for acc, r in accounts.items():
        u = (r.get("five_hour") or {}).get("util")
        if u is None:
            continue
        prev = samples.get(acc)
        samples[acc] = {"u": u, "t": now,
                        "pu": (prev or {}).get("u"), "pt": (prev or {}).get("t")}
    out = {"ts": now, "accounts": accounts, "samples": samples}
    _save_cache(out)
    return out


def _spawn_bg_refresh():
    """한도 캐시를 백그라운드에서 갱신(상태줄을 막지 않도록)."""
    import subprocess
    root = str(Path(__file__).resolve().parent.parent)
    code = ("import sys;sys.path.insert(0,%r);"
            "from digitoken import limits;limits.fetch_all(force=True)" % root)
    try:
        subprocess.Popen([__import__("sys").executable, "-c", code],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL)
    except Exception:
        pass


def fetch_for_statusline():
    """상태줄용 — 절대 네트워크로 블록하지 않는다. 캐시(나이 무관) 즉시 반환하고,
    오래됐으면 백그라운드로 갱신 트리거. 캐시가 아예 없을 때만 1회 동기 조회."""
    cache = _load_cache()
    if cache.get("accounts"):
        if _now() - cache.get("ts", 0) > TTL:
            _spawn_bg_refresh()
        return cache
    return fetch_all(force=True)


def forecast_5h(acc, data):
    """현재 five_hour 증가율로 100% 도달까지 남은 시간(시간 단위). 못 구하면 None."""
    s = data.get("samples", {}).get(acc)
    if not s or s.get("pu") is None or s.get("pt") is None:
        return None
    du = s["u"] - s["pu"]
    dt = (s["t"] - s["pt"]) / 3600.0
    if dt <= 0 or du <= 0:
        return None
    rate = du / dt  # %/시간
    remaining = max(0.0, 100.0 - s["u"])
    return remaining / rate if rate > 0 else None


def reset_delta_str(resets_at):
    """resets_at ISO → '1h42m' 남은 문자열."""
    if not resets_at:
        return "?"
    try:
        dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
    except Exception:
        return "?"
    sec = (dt - datetime.now(timezone.utc)).total_seconds()
    if sec <= 0:
        return "곧"
    d = int(sec // 86400)
    h = int((sec % 86400) // 3600)
    m = int((sec % 3600) // 60)
    if d:
        return f"{d}d{h}h"
    return (f"{h}h{m:02d}m" if h else f"{m}m")


def account_index(acc):
    """계정 디렉터리명(.claude / .claude-4) → 표시용 번호(1~6)."""
    try:
        return ACCOUNTS.index(acc) + 1
    except ValueError:
        return 0


def detect_account(stdin_json=None):
    """이 실행이 어느 계정 소속인지 판별.
    1) 상태줄 stdin 의 transcript_path (창별 정확) → 2) CLAUDE_CONFIG_DIR env →
    3) 전역 current-index(폴백)."""
    # 1) transcript_path 에서 .claude / .claude-N 추출
    if stdin_json:
        tp = stdin_json.get("transcript_path") or stdin_json.get("transcriptPath") or ""
        m = re.search(r"/(\.claude(?:-\d)?)/", tp)
        if m:
            return m.group(1)
    # 2) 환경변수
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg:
        base = os.path.basename(cfg.rstrip("/"))
        if base.startswith(".claude"):
            return base
    # 3) 폴백
    idx = current_index()
    return ACCOUNTS[idx] if 0 <= idx < len(ACCOUNTS) else ".claude"


def current(data=None, account=None):
    """지정(또는 감지된) 계정의 한도 요약. account 미지정이면 전역 current-index."""
    data = data or fetch_all()
    if account is None:
        idx = current_index()
        account = ACCOUNTS[idx] if 0 <= idx < len(ACCOUNTS) else ".claude"
    r = data.get("accounts", {}).get(account)
    return account, r, data
