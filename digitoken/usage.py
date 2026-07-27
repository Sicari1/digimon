# -*- coding: utf-8 -*-
"""Claude Code 로컬 사용 로그(6개 계정)를 파싱해 토큰/비용을 집계한다.

- 소스: ~/.claude, ~/.claude-2 … ~/.claude-6 의 projects/**/*.jsonl 중 type=="assistant" 라인.
  message.usage(4종 토큰), message.model, message.id + 최상위 requestId, timestamp.
- dedup: 세션 재개/sidechain 으로 같은 (message.id, requestId) 가 여러 파일에 중복 → total 최대인 것만.
- 성능: 파일별 (mtime,size) 캐시(cache/usage_cache.json). 안 바뀐 파일은 재파싱 생략.
- 로컬 날짜는 Asia/Seoul 기준.
"""
import os, json, glob
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Seoul")
except Exception:
    TZ = timezone(timedelta(hours=9))

from . import pricing

HOME = Path.home()
CACHE_PATH = Path(__file__).resolve().parent.parent / "cache" / "usage_cache.json"


ACCOUNTS = [".claude", ".claude-2", ".claude-3", ".claude-4", ".claude-5", ".claude-6"]


def account_dirs(account=None):
    """계정 projects 디렉터리 목록. account 지정 시 그 계정만."""
    names = [account] if account else ACCOUNTS
    dirs = []
    for name in names:
        p = HOME / name / "projects"
        if p.is_dir():
            dirs.append(p)
    return dirs


def _parse_file(path):
    """파일 1개 → 엔트리 리스트 [[id, rid, epoch, model, i, o, cw, cr], ...]."""
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"assistant"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "assistant":
                    continue
                msg = o.get("message") or {}
                u = msg.get("usage") or {}
                if not u:
                    continue
                ts = o.get("timestamp")
                if not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    continue
                mid = msg.get("id") or ""
                rid = o.get("requestId") or ""
                out.append([
                    mid, rid, dt.timestamp(), msg.get("model") or "",
                    int(u.get("input_tokens", 0) or 0),
                    int(u.get("output_tokens", 0) or 0),
                    int(u.get("cache_creation_input_tokens", 0) or 0),
                    int(u.get("cache_read_input_tokens", 0) or 0),
                ])
    except Exception:
        pass
    return out


def _load_cache():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass


class Aggregate:
    """집계 결과. dedup 된 엔트리(epoch, model, i,o,cw,cr) 리스트를 들고 시간구간 합을 계산."""

    def __init__(self, entries):
        # entries: list of (epoch, model, i, o, cw, cr)
        self.entries = entries
        self.now = datetime.now(TZ)

    def _sum(self, pred):
        tok = 0
        cost = 0.0
        for ep, model, i, o, cw, cr in self.entries:
            if pred(ep):
                tok += i + o + cw + cr
                cost += pricing.cost(model, i, o, cw, cr)
        return tok, cost

    def today(self):
        d = self.now.date()
        return self._sum(lambda ep: datetime.fromtimestamp(ep, TZ).date() == d)

    def last_hours(self, hours):
        cutoff = self.now.timestamp() - hours * 3600
        return self._sum(lambda ep: ep >= cutoff)

    def last_days(self, days):
        cutoff = self.now.timestamp() - days * 86400
        return self._sum(lambda ep: ep >= cutoff)

    def grand_total(self):
        tok = sum(i + o + cw + cr for _, _, i, o, cw, cr in self.entries)
        return tok

    def today_by_model(self):
        """오늘 모델별 (모델, 토큰, 비용) — 토큰 내림차순."""
        d = self.now.date()
        agg = {}
        for ep, model, i, o, cw, cr in self.entries:
            if datetime.fromtimestamp(ep, TZ).date() == d:
                a = agg.setdefault(model or "?", [0, 0.0])
                a[0] += i + o + cw + cr
                a[1] += pricing.cost(model, i, o, cw, cr)
        return sorted(([m, t, c] for m, (t, c) in agg.items()), key=lambda x: -x[1])


def collect(use_cache=True, account=None):
    """로그 → dedup 된 Aggregate. account 지정 시 그 계정만 집계(계정별 펫용)."""
    cache = _load_cache() if use_cache else {}
    # 캐시는 파일 경로 기준이라 다른 계정 스캔분을 지우지 않도록 기존 것을 이어받아 갱신.
    new_cache = dict(cache)
    # (id,rid) → (total, entry) — total 최대만 유지
    best = {}

    for pdir in account_dirs(account):
        for path in glob.glob(str(pdir / "**" / "*.jsonl"), recursive=True):
            try:
                st = os.stat(path)
            except OSError:
                continue
            key = path
            sig = [int(st.st_mtime), st.st_size]
            cached = cache.get(key)
            if cached and cached.get("sig") == sig:
                rows = cached["rows"]
            else:
                rows = _parse_file(path)
            new_cache[key] = {"sig": sig, "rows": rows}
            for mid, rid, ep, model, i, o, cw, cr in rows:
                dk = mid + "\x1f" + rid
                total = i + o + cw + cr
                prev = best.get(dk)
                if prev is None or total > prev[0]:
                    best[dk] = (total, (ep, model, i, o, cw, cr))

    if use_cache:
        _save_cache(new_cache)

    entries = [v[1] for v in best.values()]
    return Aggregate(entries)
