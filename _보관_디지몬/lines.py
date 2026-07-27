# -*- coding: utf-8 -*-
"""디지몬 진화 라인(정통 분기 트리) 로드 + 랜덤 부화 + 분기 선택.

linedata.json 은 tools/build_lines.py 가 digi-api 로 구운 것. 각 라인:
  {"key","rarity","tree": {"id","name","stage","image","c":[자식 노드...]}}
진화는 고정이 아니라 그 노드의 자식(정통 분기) 중 랜덤으로 하나 선택된다.
"""
import json, random
from pathlib import Path
from . import balance

DATA = Path(__file__).resolve().parent / "linedata.json"
DARK = Path(__file__).resolve().parent / "darkdata.json"

_lines = None
_dark = None


def dark_forms():
    """{line_key: dark_node} 맵. 정통 다크폼이 있는 라인만 포함."""
    global _dark
    if _dark is None:
        try:
            _dark = json.loads(DARK.read_text(encoding="utf-8"))
        except Exception:
            _dark = {}
    return _dark


def dark_form_for(line_key):
    """해당 라인의 정통 다크폼 노드(없으면 None) — 라인 무관 랜덤 금지."""
    d = dark_forms().get(line_key)
    return dict(d) if d else None


def all_lines():
    global _lines
    if _lines is None:
        _lines = json.loads(DATA.read_text(encoding="utf-8"))
    return _lines


def get_line(key):
    for L in all_lines():
        if L["key"] == key:
            return L
    return None


def tree_depth(node):
    return 1 + max([tree_depth(c) for c in node["c"]], default=0)


def hatch_line(rng=random):
    """희귀도 가중으로 라인 하나 선택 → (line, root_node)."""
    lines = all_lines()
    weights = [balance.RARITY_WEIGHT.get(L["rarity"], 1) for L in lines]
    L = rng.choices(lines, weights=weights, k=1)[0]
    return L, L["tree"]


def node_at_path(tree, path_ids):
    """path_ids(부화체부터 현재까지 id 순서)를 따라 내려간 현재 노드."""
    node = tree
    for want in path_ids[1:]:            # path_ids[0] == root
        nxt = None
        for c in node["c"]:
            if c["id"] == want:
                nxt = c
                break
        if nxt is None:
            return node                  # 손상 시 마지막 유효 노드
        node = nxt
    return node


def next_branch(node, rng=random):
    """현재 노드에서 진화할 다음 노드(정통 분기 랜덤). 없으면 None(최종체)."""
    if not node["c"]:
        return None
    return rng.choice(node["c"])


_species = None


def all_species():
    """전체 종 색인(도감용). 모든 라인의 모든 노드 + 다크폼, id 중복 제거, id 정렬 → 번호순.
    각 원소: {id, name, stage, image, rarity, line, dark?}"""
    global _species
    if _species is not None:
        return _species
    seen = {}
    for L in all_lines():
        rar = L["rarity"]

        def walk(n):
            if n["id"] not in seen:
                seen[n["id"]] = {"id": n["id"], "name": n["name"], "stage": n["stage"],
                                 "image": n["image"], "rarity": rar, "line": L["key"]}
            for c in n["c"]:
                walk(c)
        walk(L["tree"])
    for key, dk in dark_forms().items():
        if dk["id"] not in seen:
            seen[dk["id"]] = {"id": dk["id"], "name": dk["name"], "stage": dk["stage"],
                              "image": dk["image"], "rarity": "dark", "line": key, "dark": True}
    _species = sorted(seen.values(), key=lambda x: x["id"])
    return _species


def _walk_nodes(tree):
    out = []
    def w(n):
        out.append(n)
        for c in n["c"]:
            w(c)
    w(tree)
    return out


def neighbors(line_key, node_id):
    """(이전 형태 이름 or None, [다음 형태 이름들]) — 도감 상세의 진화 계열 표시용."""
    L = get_line(line_key)
    if not L:
        return None, []
    prev = None
    nxts = []
    def w(n, parent):
        nonlocal prev, nxts
        if n["id"] == node_id:
            prev = parent["name"] if parent else None
            nxts = [c["name"] for c in n["c"]]
        for c in n["c"]:
            w(c, n)
    w(L["tree"], None)
    return prev, nxts
