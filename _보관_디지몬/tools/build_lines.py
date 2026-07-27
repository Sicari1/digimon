# -*- coding: utf-8 -*-
"""디지몬 진화 라인(정통 분기 트리)을 정의하고 digi-api 로 id·이름·스프라이트 URL 을
해석해 digitoken/linedata.json 으로 굽는 빌드 스크립트.

- 트리는 이름(name)으로만 손수 작성한다. digi-api 는 정확 검색이 UA 필요(Cloudflare 403) →
  requests 기본 UA 로 검색해 id·정식이름·이미지 href 를 채운다.
- 해석 실패한 노드는 조용히 가지치기(라인 전체가 죽지 않도록). 최소 rookie 까지는 살아야 채택.
- 한 번 구우면 런타임은 네트워크 없이 linedata.json 만 읽는다(스프라이트만 최초 1회 다운로드·캐시).

실행:  python3 tools/build_lines.py
"""
import json, sys, time, os
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests 필요: pip install --user requests", file=sys.stderr); sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "digitoken" / "linedata.json"

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (digitoken build)"
API = "https://digi-api.com/api/v1/digimon"

# digi-api 레벨 → 표시 단계(우리 사다리). 여러 레벨이 붙은 종은 첫 매칭 사용.
LEVEL_MAP = {
    "Baby I": "Fresh", "Baby II": "In-Training", "Child": "Rookie",
    "Adult": "Champion", "Perfect": "Ultimate", "Ultimate": "Mega",
    "Ultra": "Ultra", "Armor": "Armor", "Hybrid": "Hybrid",
}

# ── 정통 분기 진화 트리 (root = 부화 직후 형태) ─────────────────────────────
# n: digi-api 검색 이름, c: 분기 자식들. 분기가 있으면 진화 시 랜덤으로 하나 선택된다.
def node(n, *children):
    return {"n": n, "c": list(children)}

LINES = [
    # key, rarity, tree
    ("agumon", "common", node("Koromon", node("Agumon",
        node("Greymon",
            node("Metal Greymon", node("War Greymon")),
            node("Skull Greymon")),
        node("Tyranomon", node("Metal Tyranomon"))))),

    ("gabumon", "common", node("Tunomon", node("Gabumon",
        node("Garurumon",
            node("Were Garurumon", node("Metal Garurumon")),
            node("Garurumon (X-Antibody)"))))),

    ("biyomon", "common", node("Pyocomon", node("Piyomon",
        node("Birdramon", node("Garudamon", node("Hououmon")))))),

    ("tentomon", "common", node("Mochimon", node("Tentomon",
        node("Kabuterimon",
            node("Atlur Kabuterimon", node("Herakle Kabuterimon")),
            node("Mega Kabuterimon"))))),

    ("palmon", "common", node("Tanemon", node("Palmon",
        node("Togemon", node("Lilimon", node("Rosemon")))))),

    ("gomamon", "common", node("Pukamon", node("Gomamon",
        node("Ikkakumon", node("Zudomon", node("Vikemon")))))),

    ("patamon", "uncommon", node("Tokomon", node("Patamon",
        node("Angemon",
            node("Holy Angemon", node("Seraphimon")))))),

    ("veemon", "uncommon", node("Chibimon", node("V-mon",
        node("XV-mon",
            node("Paildramon", node("Imperialdramon(Fighter Mode)"))),
        node("Fladramon", node("Magnamon"))))),

    ("guilmon", "uncommon", node("Gigimon", node("Guilmon",
        node("Growmon", node("Megalo Growmon", node("Dukemon")))))),

    ("renamon", "rare", node("Pokomon", node("Renamon",
        node("Kyubimon", node("Taomon", node("Sakuyamon")))))),

    ("dorumon", "rare", node("Dorimon", node("DORUmon",
        node("DORUgamon", node("DORUguremon", node("Alphamon")))))),

    # ── 큐레이션 확장 (정통 라인만) ─────────────────────────────────────
    ("hawkmon", "common", node("Poromon", node("Hawkmon",
        node("Aquilamon", node("Silphymon", node("Valkyrimon")))))),
    ("armadimon", "common", node("Upamon", node("Armadimon",
        node("Ankylomon", node("Shakkoumon"))))),
    ("wormmon", "common", node("Minomon", node("Wormmon",
        node("Stingmon", node("Dinobeemon", node("Gran Kuwagamon")))))),
    ("tailmon", "uncommon", node("Nyaromon", node("Tailmon",
        node("Angewomon", node("Ofanimon"))))),
    ("terriermon", "uncommon", node("Gummymon", node("Terriermon",
        node("Gargomon", node("Rapidmon Perfect", node("Saint Galgomon")))))),
    ("lopmon", "uncommon", node("Lopmon",
        node("Turuiemon", node("Andiramon", node("Cherubimon"))))),
    ("impmon", "rare", node("Impmon",
        node("Baalmon", node("Beelzebumon")))),
    ("leomon", "uncommon", node("Leomon",
        node("Saber Leomon", node("Bancho Leomon")))),
    ("betamon", "common", node("Betamon",
        node("Seadramon", node("Mega Seadramon", node("Metal Seadramon"))))),
    ("dracomon", "rare", node("Dracomon", node("Coredramon (Blue)",
        node("Wingdramon", node("Slayerdramon", node("Examon")))))),
    ("coronamon", "common", node("Coronamon",
        node("Firamon", node("Flaremon", node("Apollomon"))))),
    ("lunamon", "common", node("Lunamon",
        node("Lekismon", node("Crescemon", node("Dianamon"))))),
    ("gaomon", "uncommon", node("Gaomon",
        node("Gaogamon", node("Mach Gaogamon", node("Mirage Gaogamon"))))),
    ("hackmon", "rare", node("Hackmon",
        node("Bao Hackmon", node("Savior Hackmon", node("Jesmon"))))),
    ("falcomon", "common", node("Falcomon",
        node("Peckmon", node("Yatagaramon", node("Ravemon"))))),
    ("kudamon", "uncommon", node("Kudamon",
        node("Reppamon", node("Sleipmon")))),
    ("lalamon", "common", node("Lalamon",
        node("Sunflowmon", node("Lilamon")))),
    ("geogreymon", "uncommon", node("Geo Greymon",
        node("Rize Greymon", node("Shine Greymon")))),
    ("kunemon", "common", node("Kunemon", node("Kuwagamon", node("Okuwamon")))),
    ("gotsumon", "common", node("Gottsumon", node("Monochromon", node("Vermillimon")))),
    ("floramon", "common", node("Floramon", node("Kiwimon", node("Blossomon")))),
]


def search_id(name):
    """이름 → (id, 정식이름). 정확(대소문자 무시) 일치 우선, 없으면 첫 결과."""
    try:
        d = S.get(API, params={"name": name, "pageSize": 20}, timeout=20).json()
    except Exception as e:
        print(f"  검색 실패 {name!r}: {e}", file=sys.stderr); return None
    c = d.get("content", [])
    for x in c:
        if x["name"].lower() == name.lower():
            return x["id"], x["name"]
    return (c[0]["id"], c[0]["name"]) if c else None


def detail(did):
    """id → 상세(정식이름·레벨·이미지 href)."""
    try:
        return S.get(f"{API}/{did}", timeout=20).json()
    except Exception as e:
        print(f"  상세 실패 {did}: {e}", file=sys.stderr); return None


_cache = {}  # name → resolved dict|None


def resolve(name):
    if name in _cache:
        return _cache[name]
    hit = search_id(name)
    time.sleep(0.15)  # digi-api 예의상 간격
    if not hit:
        _cache[name] = None; return None
    did, official = hit
    d = detail(did) or {}
    time.sleep(0.15)
    levels = [l["level"] for l in d.get("levels", [])]
    stage = next((LEVEL_MAP[l] for l in levels if l in LEVEL_MAP), levels[0] if levels else "?")
    imgs = [i["href"] for i in d.get("images", [])]
    res = {"id": did, "name": official, "stage": stage,
           "image": imgs[0] if imgs else None}
    _cache[name] = res
    print(f"  {name:28s} -> #{did} {official} [{stage}]")
    return res


def build_tree(src):
    """이름 트리 → 해석 트리. 해석 실패 노드는 가지치기."""
    r = resolve(src["n"])
    if not r:
        print(f"  ! 미해석 노드 제거: {src['n']}", file=sys.stderr)
        return None
    children = [build_tree(c) for c in src.get("c", [])]
    children = [c for c in children if c]
    r["c"] = children
    return r


def main():
    out = []
    for key, rarity, tree in LINES:
        print(f"[{key}] ({rarity})")
        t = build_tree(tree)
        if not t:
            print(f"  ! 라인 {key} 루트 해석 실패 — 스킵", file=sys.stderr); continue
        out.append({"key": key, "rarity": rarity, "tree": t})
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n작성: {OUT}  ({len(out)}개 라인)")


if __name__ == "__main__":
    main()
