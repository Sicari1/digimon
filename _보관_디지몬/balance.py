# -*- coding: utf-8 -*-
"""토큰 경제·게임 밸런스 상수. 원본 PokeTokenBar 의 PokemonBalance 를 그대로 이식.

실측 평균(~200~250M tok/일) 기준. 졸업 총량 T 는 같은 희귀도면 진화 단계 수와 무관하게 동일하고,
k개 형태 라인에서 i번째(1-based) 형태 성장 비용 = T·i / (k(k+1)/2) → 합 = T (단계 오를수록 비쌈).
"""

# 알 부화 임계 — 이만큼 토큰을 써야 알이 깨진다(즉시 부화 대신 기대감). 초과분은 부화체 성장에 이월.
EGG_HATCH_THRESHOLD = 5_000_000

# 희귀도별 졸업 총량(토큰). heavy use 기준 대략 common ≈3일 … rare/legendary 는 훨씬 길게.
GRADUATION_TOTAL = {
    "common":    750_000_000,
    "uncommon":  1_875_000_000,
    "rare":      3_000_000_000,
    "legendary": 6_000_000_000,
}

# 부화 희귀도 가중치(라인 뽑기). 흔한 게 자주, 귀한 게 드물게.
RARITY_WEIGHT = {
    "common": 100,
    "uncommon": 40,
    "rare": 12,
    "legendary": 3,
}

# 이로치(shiny) 부화 확률 분모 — 1/64 기본. 데이터 부적 보유 시 1/48로 상승.
SHINY_DENOMINATOR = 64
SHINY_DENOMINATOR_CHARM = 48

# 암흑진화(다크 에볼루션) 확률 분모 — 진화 시 1/40 확률로 정규 분기 대신 다크 폼으로.
# 디지몬 원작(아구몬→스컬그레이몬 강제 다크진화) 오마주. 메타몽 대체.
DARK_EVOLUTION_DENOMINATOR = 40

# ── 경제 ────────────────────────────────────────────────────────────────
# 재화 = 설치 이후 쓴 토큰 − 상점 지출(spent_tokens). 성장 미터(used_since_install)는 불변.
CANDY_XP = 100_000_000          # 이상한 사탕 1개가 주입하는 성장 토큰
PRICE_RARE_CANDY = 500_000_000  # 사탕 값어치(100M)보다 비싸게 — 무료 획득이 항상 이득
PRICE_MINT = 100_000_000        # 성격 재추첨(코스메틱)
PRICE_CHARM = 3_000_000_000     # 데이터 부적(영구 이로치 확률↑)

# 한도 100% 도달 보상 사탕 수 (세션=1, 주간=5)
CANDY_GRANT_SESSION = 1
CANDY_GRANT_WEEKLY = 5


def graduation_total(rarity: str) -> int:
    return GRADUATION_TOTAL.get(rarity, GRADUATION_TOTAL["common"])


def phase_threshold(rarity: str, total_forms: int, stage_index: int) -> int:
    """stage_index(0-based) 형태에서 다음 단계/졸업까지 필요한 토큰."""
    k = max(1, total_forms)
    i = stage_index + 1                      # 1-based
    total = graduation_total(rarity)
    denom = k * (k + 1) / 2.0
    return round(total * i / denom)
