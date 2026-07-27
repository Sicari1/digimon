# -*- coding: utf-8 -*-
"""모델별 토큰 단가(USD/토큰). 원본 ModelPricing 이식 — ccusage(LiteLLM 스냅샷) 단가와 일치.

가격은 USD per **million** tokens 로 선언하고 per-token 으로 변환한다.
"""

def _pm(inp, out, cw, cr):
    """USD/Mtok → (input, output, cache_write, cache_read) per-token."""
    return (inp / 1e6, out / 1e6, cw / 1e6, cr / 1e6)

ZERO = (0.0, 0.0, 0.0, 0.0)

# 정확 매칭 테이블 (USD/Mtok)
TABLE = {
    "claude-opus-4-8":           _pm(5, 25, 6.25, 0.5),
    "claude-opus-4-7":           _pm(5, 25, 6.25, 0.5),
    "claude-sonnet-4-6":         _pm(3, 15, 3.75, 0.3),
    "claude-sonnet-5":           _pm(3, 15, 3.75, 0.3),
    "claude-haiku-4-5-20251001": _pm(1, 5, 1.25, 0.1),
    "claude-fable-5":            ZERO,     # ccusage 미가격 → $0
}


def rate(model: str):
    """모델명 → (input, output, cache_write, cache_read) per-token.
    정확 매칭 우선, 없으면 패밀리(opus/sonnet/haiku) 폴백, 그래도 없으면 0."""
    if model in TABLE:
        return TABLE[model]
    m = (model or "").lower()
    if "opus" in m:   return _pm(5, 25, 6.25, 0.5)
    if "sonnet" in m: return _pm(3, 15, 3.75, 0.3)
    if "haiku" in m:  return _pm(1, 5, 1.25, 0.1)
    return ZERO


def cost(model: str, inp: int, out: int, cw: int, cr: int) -> float:
    ri, ro, rcw, rcr = rate(model)
    return inp * ri + out * ro + cw * rcw + cr * rcr
