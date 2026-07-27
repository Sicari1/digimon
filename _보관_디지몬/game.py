# -*- coding: utf-8 -*-
"""게임 상태 + 진행 로직 — 부화/진화(분기 랜덤)/졸업/도감. 원본 CompanionStore.applyUsage 이식.

- 성장 재화 = 설치 이후 누적 사용 토큰(used_since_install). 매 실행마다 전체 누적 토큰을 다시 재서
  지난 실행 대비 증가분(delta)만 게임에 주입한다(로그가 지워져 줄면 0 처리).
- 알은 EGG_HATCH 만큼 써야 부화. 부화체는 단계별 임계(phase_threshold)를 넘을 때마다 진화하며,
  진화 방향은 그 형태의 정통 분기 중 랜덤. 최종체 임계 도달 시 졸업 → 도감 등록 + 새 알.
- 상태는 state.json(프로젝트 폴더)에 저장. 하위호환 위해 없는 키는 기본값.
"""
import json, random, datetime
from pathlib import Path
from . import balance, lines

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
# 구버전 단일 상태 파일(계정 도입 전). 남아있어도 무시.
STATE_PATH = Path(__file__).resolve().parent.parent / "state.json"


def state_path(account=None):
    """계정별 상태 파일 경로. account 없으면 공유(구)."""
    if account:
        return STATE_DIR / f"{account.lstrip('.') or 'default'}.json"
    return STATE_PATH

# 성격 25종 (key, 한국어명) — 부화 시 확정, 능력치 무관(아이덴티티).
NATURES = [
    ("hardy", "노력"), ("lonely", "외로움"), ("brave", "용감"), ("adamant", "고집"),
    ("naughty", "개구쟁이"), ("bold", "대담"), ("docile", "온순"), ("relaxed", "무사태평"),
    ("impish", "장난꾸러기"), ("lax", "촐랑"), ("timid", "겁쟁이"), ("hasty", "성급"),
    ("serious", "성실"), ("jolly", "명랑"), ("naive", "천진난만"), ("modest", "조심"),
    ("mild", "의젓"), ("quiet", "냉정"), ("bashful", "수줍음"), ("rash", "덜렁"),
    ("calm", "차분"), ("gentle", "얌전"), ("sassy", "건방"), ("careful", "신중"),
    ("quirky", "변덕"),
]
NATURE_KO = dict(NATURES)


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ── 전역 수집 도감(계정 공통) ─────────────────────────────────────────────
COLLECTION_PATH = STATE_DIR / "collection.json"


def load_collection():
    try:
        c = json.loads(COLLECTION_PATH.read_text(encoding="utf-8"))
    except Exception:
        c = {}
    c.setdefault("seen", {})     # id(str) → {name, stage, shiny?}
    c.setdefault("caught", {})   # id(str) → 졸업 횟수
    return c


def _save_collection(c):
    try:
        COLLECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
        COLLECTION_PATH.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def mark_seen(node, shiny=False):
    c = load_collection()
    sid = str(node["id"])
    e = c["seen"].get(sid, {})
    e["name"] = node.get("name")
    e["stage"] = node.get("stage")
    if shiny:
        e["shiny"] = True
    c["seen"][sid] = e
    _save_collection(c)


def mark_caught(node):
    c = load_collection()
    sid = str(node["id"])
    c["caught"][sid] = c["caught"].get(sid, 0) + 1
    e = c["seen"].get(sid, {})
    e["name"] = node.get("name")
    e["stage"] = node.get("stage")
    c["seen"][sid] = e
    _save_collection(c)


def default_state():
    return {
        "version": 1,
        "install_baseline_set": False,
        "last_cumulative": 0,
        "used_since_install": 0,
        "egg_usage": 0,
        "pending_line": None, "pending_shiny": False, "pending_nature": None,
        "active": None,
        "dex": [],
        "collected": [],
        # 경제
        "spent_tokens": 0,              # 상점 지출 누적(재화 = used_since_install − spent_tokens)
        "inventory": {},               # 아이템 → 개수 (예: rare_candy)
        "charm_owned": False,          # 데이터 부적(영구 이로치 확률↑)
        "limit_tier": {},              # 한도창 key → 마지막 지급 리셋시각(중복 지급 방지)
        "created_at": now_iso(), "last_run": None,
        "events": [],
    }


def load_state(account=None):
    try:
        s = json.loads(state_path(account).read_text(encoding="utf-8"))
    except Exception:
        return default_state()
    base = default_state()
    base.update(s)
    return base


def save_state(state, account=None):
    state["last_run"] = now_iso()
    p = state_path(account)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────
def _shiny_denom(state):
    return balance.SHINY_DENOMINATOR_CHARM if state.get("charm_owned") else balance.SHINY_DENOMINATOR


def _ensure_pending(state, rng):
    if state["pending_line"]:
        return
    L, root = lines.hatch_line(rng)
    state["pending_line"] = L["key"]
    state["pending_shiny"] = (rng.randint(1, _shiny_denom(state)) == 1)
    state["pending_nature"] = rng.choice(NATURES)[0]


def _hatch(state, events, rng):
    _ensure_pending(state, rng)
    L = lines.get_line(state["pending_line"])
    root = L["tree"]
    state["active"] = {
        "line": L["key"], "rarity": L["rarity"],
        "total_forms": lines.tree_depth(root),
        "path": [root["id"]], "stage_index": 0, "used_at_stage": 0,
        "is_shiny": bool(state["pending_shiny"]),
        "nature": state["pending_nature"],
        "dark": None,                  # 암흑진화 폼(정규 트리 밖). 설정되면 그게 최종체.
    }
    mark_seen(root, state["active"]["is_shiny"])
    events.append({"kind": "hatch", "name": root["name"], "stage": root["stage"],
                   "shiny": state["active"]["is_shiny"], "rarity": L["rarity"]})
    state["pending_line"] = None
    state["pending_shiny"] = False
    state["pending_nature"] = None


def _chain_nodes(mon):
    """현재 mon 의 path 를 따라 [{id,name,stage,image}...] (부화체→현재)."""
    L = lines.get_line(mon["line"])
    tree = L["tree"]
    out = []
    node = tree
    out.append({k: node[k] for k in ("id", "name", "stage", "image")})
    for want in mon["path"][1:]:
        nxt = next((c for c in node["c"] if c["id"] == want), None)
        if nxt is None:
            break
        node = nxt
        out.append({k: node[k] for k in ("id", "name", "stage", "image")})
    if mon.get("dark"):
        d = mon["dark"]
        out.append({k: d[k] for k in ("id", "name", "stage", "image")})
    return out


def _graduate(state, events, rng):
    mon = state["active"]
    chain = _chain_nodes(mon)
    final = chain[-1]
    state["dex"].append({
        "line": mon["line"], "rarity": mon["rarity"],
        "chain": chain, "final_name": final["name"],
        "is_shiny": mon["is_shiny"], "nature": mon["nature"],
        "is_dark": bool(mon.get("dark")),
        "caught_at": now_iso(),
    })
    mark_caught(final)
    tag = f'{mon["line"]}:{final["id"]}'
    if tag not in state["collected"]:
        state["collected"].append(tag)
    events.append({"kind": "graduate", "name": final["name"],
                   "shiny": mon["is_shiny"], "rarity": mon["rarity"]})
    state["active"] = None
    state["egg_usage"] = 0
    _ensure_pending(state, rng)


def current_node(state):
    """현재 형태 노드(활성 mon). 알이면 None."""
    mon = state.get("active")
    if not mon:
        return None
    chain = _chain_nodes(mon)
    return chain[-1] if chain else None


def current_total_forms(state):
    """이 개체가 실제로 밟는 분기 기준 총 형태 수(짧은 분기는 더 작게 표시)."""
    mon = state.get("active")
    if not mon:
        return 0
    if mon.get("dark"):
        return mon["stage_index"] + 1        # 다크폼은 종결
    tree = lines.get_line(mon["line"])["tree"]
    node = lines.node_at_path(tree, mon["path"])
    return mon["stage_index"] + lines.tree_depth(node)


def next_threshold(state):
    """현재 단계에서 다음 진화/졸업까지 필요한 총 토큰(단계 임계)."""
    mon = state.get("active")
    if not mon:
        return balance.EGG_HATCH_THRESHOLD
    return balance.phase_threshold(mon["rarity"], mon["total_forms"], mon["stage_index"])


def _apply(state, delta, rng):
    """delta 토큰을 게임에 주입. 발생 이벤트 리스트 반환."""
    events = []
    bank = int(max(0, delta))
    guard = 0
    while bank > 0 and guard < 100000:
        guard += 1
        if state["active"] is None:
            _ensure_pending(state, rng)
            need = balance.EGG_HATCH_THRESHOLD - state["egg_usage"]
            if bank < need:
                state["egg_usage"] += bank
                bank = 0
                break
            bank -= need
            state["egg_usage"] = 0
            _hatch(state, events, rng)
        else:
            mon = state["active"]
            thr = balance.phase_threshold(mon["rarity"], mon["total_forms"], mon["stage_index"])
            need = thr - mon["used_at_stage"]
            if bank < need:
                mon["used_at_stage"] += bank
                bank = 0
                break
            bank -= need
            if mon.get("dark"):
                # 이미 다크폼 → 종결, 졸업
                _graduate(state, events, rng)
                continue
            node = lines.node_at_path(lines.get_line(mon["line"])["tree"], mon["path"])
            # 암흑진화 판정 — 이 라인의 정통 다크폼이 있을 때만, Rookie 이상에서 낮은 확률로.
            dark_form = lines.dark_form_for(mon["line"])
            dark_roll = (mon["stage_index"] >= 1 and dark_form is not None
                         and rng.randint(1, balance.DARK_EVOLUTION_DENOMINATOR) == 1)
            if dark_roll:
                dark = dark_form
                mon["dark"] = dark
                mon["stage_index"] += 1
                mon["used_at_stage"] = 0
                mark_seen(dark, mon["is_shiny"])
                events.append({"kind": "dark", "name": dark["name"], "stage": dark["stage"],
                               "shiny": mon["is_shiny"], "rarity": mon["rarity"]})
                continue
            nxt = lines.next_branch(node, rng)
            if nxt is not None:
                mon["path"].append(nxt["id"])
                mon["stage_index"] += 1
                mon["used_at_stage"] = 0
                mark_seen(nxt, mon["is_shiny"])
                events.append({"kind": "evolve", "name": nxt["name"], "stage": nxt["stage"],
                               "shiny": mon["is_shiny"], "rarity": mon["rarity"]})
            else:
                _graduate(state, events, rng)
    return events


# ── 경제 ────────────────────────────────────────────────────────────────
def currency(state):
    """쓸 수 있는 재화 = 설치 후 성장 토큰 − 상점 지출."""
    return max(0, state.get("used_since_install", 0) - state.get("spent_tokens", 0))


SHOP_ITEMS = {
    "candy": {"name": "이상한 사탕", "price": balance.PRICE_RARE_CANDY,
              "desc": "현재 디지몬에 +100M 성장 주입"},
    "mint":  {"name": "민트", "price": balance.PRICE_MINT,
              "desc": "현재 디지몬 성격 재추첨"},
    "charm": {"name": "데이터 부적", "price": balance.PRICE_CHARM,
              "desc": "영구: 이로치 부화 확률 상승(1/64→1/48)"},
}


def buy(state, item, rng=None):
    """상점 구매. (성공?, 메시지) 반환."""
    rng = rng or random
    it = SHOP_ITEMS.get(item)
    if not it:
        return False, f"알 수 없는 아이템: {item}"
    if item == "charm" and state.get("charm_owned"):
        return False, "데이터 부적은 이미 보유 중입니다."
    price = it["price"]
    if currency(state) < price:
        return False, f"재화 부족: {it['name']} {price:,} 필요, 보유 {currency(state):,}"
    state["spent_tokens"] = state.get("spent_tokens", 0) + price
    if item == "candy":
        state["inventory"]["rare_candy"] = state["inventory"].get("rare_candy", 0) + 1
        return True, f"이상한 사탕 구매 완료 (가방에 {state['inventory']['rare_candy']}개)"
    if item == "mint":
        if not state.get("active"):
            return True, "민트 구매 — 부화 후 성격이 적용됩니다."
        old = NATURE_KO.get(state["active"].get("nature"), "?")
        state["active"]["nature"] = rng.choice(NATURES)[0]
        return True, f"성격 재추첨: {old} → {NATURE_KO.get(state['active']['nature'])}"
    if item == "charm":
        state["charm_owned"] = True
        return True, "데이터 부적 장착 — 앞으로의 부화에 이로치 확률이 오릅니다."
    return False, "?"


def use_candy(state, rng=None):
    """가방의 이상한 사탕 1개 사용 → 현재 디지몬에 성장 주입."""
    rng = rng or random
    n = state.get("inventory", {}).get("rare_candy", 0)
    if n <= 0:
        return False, "가방에 이상한 사탕이 없습니다."
    if not state.get("active"):
        return False, "알 상태에는 사탕을 쓸 수 없습니다(부화 후 사용)."
    state["inventory"]["rare_candy"] = n - 1
    ev = _apply(state, balance.CANDY_XP, rng)
    # 사탕으로 성장했으니 성장 미터에도 반영(재화 균형)
    state["used_since_install"] += balance.CANDY_XP
    state["events"] = ev
    grew = [e for e in ev if e["kind"] in ("evolve", "dark", "graduate", "hatch")]
    return True, ("사탕 사용 — " + ", ".join(e["name"] for e in grew) if grew else "사탕 사용 — 성장했습니다.")


def grant_candy(state, n=1):
    """미니게임 보상 등으로 사탕 지급."""
    state.setdefault("inventory", {})
    state["inventory"]["rare_candy"] = state["inventory"].get("rare_candy", 0) + n


def grant_xp(state, xp, rng=None):
    """미니게임 보상 등으로 성장 토큰 주입(진화/졸업 자동). 발생 이벤트 반환."""
    rng = rng or random
    if not state.get("active"):
        return []
    state["used_since_install"] += xp
    ev = _apply(state, xp, rng)
    state["events"] = ev
    return ev


def _grant_candy_from_limits(state, limits_data, account=None):
    """한도창(5h/7일) 100% 도달 시 이상한 사탕 지급(창 리셋 주기당 1회).
    account 지정 시 그 계정 한도만(계정별 펫)."""
    if not limits_data:
        return
    granted = 0
    for acc, r in limits_data.get("accounts", {}).items():
        if account and acc != account:
            continue
        if not isinstance(r, dict) or "error" in r:
            continue
        for win, cnt in (("five_hour", balance.CANDY_GRANT_SESSION),
                         ("seven_day", balance.CANDY_GRANT_WEEKLY)):
            w = r.get(win) or {}
            util = w.get("util")
            resets = w.get("resets_at")
            if util is None or util < 100:
                continue
            key = f"{acc}:{win}"
            if state["limit_tier"].get(key) == resets:
                continue                       # 이번 리셋 주기엔 이미 지급
            state["limit_tier"][key] = resets
            state["inventory"]["rare_candy"] = state["inventory"].get("rare_candy", 0) + cnt
            granted += cnt
    if granted:
        state.setdefault("events", []).append({"kind": "candy_grant", "count": granted})


def update(state, grand_total, rng=None, limits_data=None, account=None):
    """누적 토큰(grand_total)로 게임 진행. account 지정 시 그 계정 한도만 사탕 보상."""
    rng = rng or random
    if not state["install_baseline_set"]:
        # 최초 실행: 기준점만 잡는다(과거 사용량을 소급 주입하지 않음). 알 하나 준비.
        state["install_baseline_set"] = True
        state["last_cumulative"] = grand_total
        state["used_since_install"] = 0
        state["egg_usage"] = 0
        state["active"] = None
        _ensure_pending(state, rng)
        # 이미 100%인 한도창은 소급 지급하지 않도록 시드
        if limits_data:
            for acc, r in limits_data.get("accounts", {}).items():
                if account and acc != account:
                    continue
                if isinstance(r, dict) and "error" not in r:
                    for win in ("five_hour", "seven_day"):
                        w = r.get(win) or {}
                        if (w.get("util") or 0) >= 100:
                            state["limit_tier"][f"{acc}:{win}"] = w.get("resets_at")
        state["events"] = [{"kind": "start"}]
        return state
    delta = grand_total - state["last_cumulative"]
    if delta < 0:
        delta = 0
    state["last_cumulative"] = grand_total
    state["used_since_install"] += delta
    state["events"] = _apply(state, delta, rng)
    _grant_candy_from_limits(state, limits_data, account)
    return state
