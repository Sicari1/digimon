# -*- coding: utf-8 -*-
"""대화형 TUI — digimon 한 번 실행하면 전체화면 앱. 키 하나로 탭 이동/구매/미니게임.

외부 라이브러리 없이 ANSI + termios(raw 입력)로 구현. 트루컬러 스프라이트 그대로 사용.
화면: 홈 / 상점 / 가방 / 도감 / 미니게임(실루엣·배틀·트레이닝).
"""
import sys, os, json, termios, tty, select, random
from pathlib import Path
from . import usage, game, limits as limmod, sprite, lines, render, sixel

_CFG = Path(__file__).resolve().parent.parent / "config.json"


def _load_cfg():
    try:
        return json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cfg(c):
    try:
        _CFG.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass

R = render.RESET
B = render.BOLD
D = render.DIM
G = render.GOLD
C = render.CYAN
GR = render.GRAY
GRN = render.GREEN
PUR = render.PURPLE
RED = render.RED
fmt = render.fmt
bar = render.bar


# ── 터미널 제어 ──────────────────────────────────────────────────────────
class Raw:
    def __enter__(self):
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        sys.stdout.write("\x1b[?1049h\x1b[?25l")  # 대체 화면 + 커서 숨김
        sys.stdout.flush()
        return self

    def __exit__(self, *a):
        sys.stdout.write("\x1b[?25h\x1b[?1049l")  # 복구
        sys.stdout.flush()
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


_ARROWS = {"[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT",
           "OA": "UP", "OB": "DOWN", "OC": "RIGHT", "OD": "LEFT"}


def read_key(timeout=None):
    # os.read(fd) 로 raw 바이트 직접 읽기 — sys.stdin 텍스트버퍼가 뒤 바이트를 미리
    # 삼켜서 select 와 어긋나는 문제(화살표=ESC 오인)를 피한다.
    fd = sys.stdin.fileno()
    if timeout is not None:
        if not select.select([fd], [], [], timeout)[0]:
            return None
    try:
        b = os.read(fd, 1)
    except OSError:
        return None
    if not b:
        return None
    if b != b"\x1b":
        try:
            return b.decode("utf-8", "ignore") or "OTHER"
        except Exception:
            return "OTHER"
    # ESC: 뒤따르는 시퀀스가 있으면(화살표/마우스) 한 번에 읽는다
    if not select.select([fd], [], [], 0.06)[0]:
        return "ESC"                       # 진짜 Escape
    seq = os.read(fd, 32).decode("latin1")
    if seq[:2] in _ARROWS:
        return _ARROWS[seq[:2]]
    if seq.startswith("[<") or seq.startswith("[M"):
        return "MOUSE"                     # 마우스 이벤트 — 무시
    return "OTHER"


def draw(lines_):
    sys.stdout.write("\x1b[2J\x1b[H" + "\n".join(lines_) + R)
    sys.stdout.flush()


def _sprite_lines(node, h=12, shiny=False, silhouette=False):
    if not node:
        return sprite.placeholder(h)
    p = sprite.fetch(node)
    if not p:
        return sprite.placeholder(h)
    out = sprite.render(p, height=h, shiny=shiny, silhouette=silhouette)
    return out or sprite.placeholder(h)


# ── 앱 상태 ─────────────────────────────────────────────────────────────
class App:
    def __init__(self, account, force_sixel=False):
        self.accounts = [a for a in limmod.ACCOUNTS if (limmod.HOME / a / "projects").is_dir()]
        if account not in self.accounts:
            account = self.accounts[0] if self.accounts else ".claude"
        self.account = account
        self.rng = random.Random()
        try:
            self.limits = limmod.fetch_for_statusline()
        except Exception:
            self.limits = None
        # 이미지 모드: config 에 저장된 선호(sixel: true/false) 우선, 없으면 자동 감지.
        pref = _load_cfg().get("sixel")
        if pref is None:
            try:
                self.use_sixel = force_sixel or sixel.supported()
            except Exception:
                self.use_sixel = force_sixel
        else:
            self.use_sixel = bool(pref) or force_sixel
        self._sixel_cache = {}
        self.msg = ""
        self.reload()

    def _sixel_for(self, node, shiny):
        if not node:
            return None
        key = (node["id"], shiny)
        if key not in self._sixel_cache:
            p = sprite.fetch(node)
            self._sixel_cache[key] = (sixel.render(p, target_h=200) if p else None)
        return self._sixel_cache[key]

    def reload(self):
        self.state = game.load_state(self.account)
        try:
            self.agg = usage.collect(account=self.account)
            game.update(self.state, self.agg.grand_total(),
                        limits_data=self.limits, account=self.account)
            game.save_state(self.state, self.account)
        except Exception:
            self.agg = usage.Aggregate([])

    def switch(self, delta):
        if not self.accounts:
            return
        i = (self.accounts.index(self.account) + delta) % len(self.accounts)
        self.account = self.accounts[i]
        self.msg = ""
        self.reload()

    def save(self):
        game.save_state(self.state, self.account)

    # ── 홈 화면 ──────────────────────────────────────────────────────
    def _home_info(self, d):
        """스탯/메뉴 텍스트 블록(스프라이트 제외)."""
        info = []
        if d["egg"]:
            info.append(f"{B}🥚 디지타마 (알){R}")
        else:
            sh = f" {G}✨{R}" if d["shiny"] else (f" {PUR}🌑{R}" if d["dark"] else "")
            nm = PUR if d["dark"] else ""
            info.append(f"{B}{nm}{d['name']}{R} {D}{d['stage']}{R}{sh}")
            info.append(f"{render.RARITY_COLOR.get(d['rarity'],'')}{render.RARITY_KO.get(d['rarity'],'')}{R}"
                        f"  {D}성격 {game.NATURE_KO.get(d['nature'],'?')}  단계 {d['stage_index']+1}/{d['total_forms']}{R}")
        frac = d["cur"] / d["need"] if d["need"] else 0
        info.append("")
        info.append(f"{'부화까지' if d['egg'] else '다음 진화'}  {B}{frac*100:.1f}%{R}")
        info.append(f"{GRN}{bar(frac,20)}{R} {D}{fmt(d['cur'])}/{fmt(d['need'])}{R}")
        info.append("")
        tt, tc = self.agg.today()
        info.append(f"오늘 {B}{fmt(tt)}{R} {GR}${tc:,.2f}{R}")
        if self.limits:
            acc, r, _ = limmod.current(self.limits, self.account)
            if r and "error" not in r:
                u5 = (r.get("five_hour") or {}).get("util") or 0
                u7 = (r.get("seven_day") or {}).get("util") or 0
                col = RED if u5 >= 85 else (G if u5 >= 60 else C)
                info.append(f"5시간 {col}{bar(u5/100,12)}{R} {u5:.0f}%  {D}리셋 {limmod.reset_delta_str((r.get('five_hour') or {}).get('resets_at'))}{R}")
                info.append(f"7일   {C}{bar(u7/100,12)}{R} {u7:.0f}%")
        bagn = self.state.get("inventory", {}).get("rare_candy", 0)
        charm = " 🔮" if self.state.get("charm_owned") else ""
        info.append("")
        info.append(f"{G}재화 {fmt(game.currency(self.state))}{R}  {D}·{R}  🍬x{bagn}{charm}  {D}·  도감 {len(self.state.get('collected',[]))}종{R}")
        for e in render._events_lines(self.state):
            info.append(e)
        if self.msg:
            info.append(f"{G}{self.msg}{R}")
        return info

    def draw_home(self):
        d = render.display(self.state)
        n = limmod.account_index(self.account)
        title = f"{D}┌─ {R}{B}DigiTokenBar{R}  {D}계정{n} ({self.account}){R}"
        info = self._home_info(d)
        imgstate = "ON" if self.use_sixel else "off"
        menu = [f"{D}├──────────────────────────────────────────────{R}",
                f"  {B}[S]{R}상점  {B}[B]{R}가방  {B}[D]{R}도감  {B}[G]{R}미니게임",
                f"  {B}[←→]{R}계정전환  {B}[I]{R}이미지({imgstate})  {B}[R]{R}새로고침  {B}[Q]{R}나가기"]

        sx = self._sixel_for(d["node"], d["shiny"]) if (self.use_sixel and not d["egg"]) else None
        if sx:
            # 고화질 이미지 위, 스탯 아래
            out = ["\x1b[2J\x1b[H", title, "\n  "]
            sys.stdout.write("".join(out))
            sys.stdout.write(sx)
            sys.stdout.write("\n" + "\n".join("  " + x for x in info) + "\n"
                             + "\n".join(menu) + R)
            sys.stdout.flush()
        else:
            # 반블록(고해상도) 좌 + 스탯 우
            sp = _sprite_lines(d["node"] if not d["egg"] else None, 16, shiny=d["shiny"])
            spw = max((render._vlen(x) for x in sp), default=8)
            sp = [x + " " * (spw - render._vlen(x)) for x in sp]
            rows = max(len(sp), len(info))
            sp += [" " * spw] * (rows - len(sp))
            info2 = info + [""] * (rows - len(info))
            body = [title] + [f"  {sp[i]}   {info2[i]}" for i in range(rows)] + [""] + menu
            draw(body)

    def run(self):
        with Raw():
            while True:
                self.draw_home()
                k = read_key()
                if k in ("q", "Q"):        # ESC 는 홈에서 종료 아님(화살표 오인 방지)
                    break
                elif k in ("s", "S"):
                    self.shop()
                elif k in ("b", "B"):
                    self.bag()
                elif k in ("d", "D"):
                    self.dex()
                elif k in ("g", "G"):
                    self.game_menu()
                elif k in ("i", "I"):
                    self.use_sixel = not self.use_sixel
                    self._sixel_cache.clear()
                    cfg = _load_cfg(); cfg["sixel"] = self.use_sixel; _save_cfg(cfg)
                    self.msg = f"이미지 모드 {'ON(sixel)' if self.use_sixel else 'off(반블록)'} (기억됨)"
                elif k in ("r", "R"):
                    self.msg = "새로고침 완료"
                    self.reload()
                elif k in ("LEFT", "UP"):   # 화살표/휠 위 = 이전 계정
                    self.switch(-1)
                elif k in ("RIGHT", "DOWN"):  # 아래 = 다음 계정
                    self.switch(1)

    # ── 상점 ─────────────────────────────────────────────────────────
    def shop(self):
        while True:
            lines_ = ["", f"  {B}상점{R}   {D}재화 {G}{fmt(game.currency(self.state))}{R}", ""]
            keys = list(game.SHOP_ITEMS.items())
            for i, (key, it) in enumerate(keys, 1):
                own = f" {GRN}(보유중){R}" if key == "charm" and self.state.get("charm_owned") else ""
                afford = G if game.currency(self.state) >= it["price"] else GR
                lines_.append(f"  {B}[{i}]{R} {it['name']}  {afford}{fmt(it['price'])}{R}{own}")
                lines_.append(f"      {D}{it['desc']}{R}")
            lines_ += ["", f"  {B}[1-3]{R} 구매   {B}[C]{R} 사탕 사용   {B}[ESC]{R} 뒤로"]
            if self.msg:
                lines_ += ["", f"  {G}{self.msg}{R}"]
            draw(lines_)
            k = read_key()
            if k in ("ESC", "q", "Q"):
                self.msg = ""
                return
            if k in ("c", "C"):
                ok, m = game.use_candy(self.state, self.rng)
                self.msg = m
                self.save()
            elif k in ("1", "2", "3"):
                key = keys[int(k) - 1][0]
                ok, m = game.buy(self.state, key, self.rng)
                self.msg = m
                self.save()

    # ── 가방 ─────────────────────────────────────────────────────────
    def bag(self):
        while True:
            n = self.state.get("inventory", {}).get("rare_candy", 0)
            charm = "보유" if self.state.get("charm_owned") else "없음"
            lines_ = ["", f"  {B}가방{R}", "",
                      f"  🍬 이상한 사탕  x{n}",
                      f"  🔮 데이터 부적  {charm}",
                      "", f"  {B}[C]{R} 사탕 사용   {B}[ESC]{R} 뒤로"]
            if self.msg:
                lines_ += ["", f"  {G}{self.msg}{R}"]
            draw(lines_)
            k = read_key()
            if k in ("ESC", "q", "Q"):
                self.msg = ""
                return
            if k in ("c", "C"):
                ok, m = game.use_candy(self.state, self.rng)
                self.msg = m
                self.save()

    # ── 도감(필드 가이드) ─────────────────────────────────────────────
    def _rar_label(self, rar):
        if rar == "dark":
            return PUR, "다크"
        return render.RARITY_COLOR.get(rar, ""), render.RARITY_KO.get(rar, rar)

    def dex(self):
        species = lines.all_species()
        total = len(species)
        idx = 0
        PAGE = 14
        while True:
            col = game.load_collection()
            seen_n = sum(1 for s in species if str(s["id"]) in col["seen"])
            caught_n = sum(1 for s in species if str(s["id"]) in col["caught"])
            head = (f"  {B}디지몬 도감{R}   "
                    f"{G}●{R} 잡음 {caught_n}  {C}○{R} 봄 {seen_n}  {D}· 전체 {total}{R}")
            # 커서 중심 창
            half = PAGE // 2
            start = max(0, min(idx - half, total - PAGE))
            start = max(0, start)
            rows = []
            for i in range(start, min(start + PAGE, total)):
                s = species[i]
                sid = str(s["id"])
                caught = sid in col["caught"]
                seen = sid in col["seen"]
                mark = f"{G}●{R}" if caught else (f"{C}○{R}" if seen else f"{D}·{R}")
                rc, rk = self._rar_label(s["rarity"])
                if seen:
                    name = s["name"]
                    meta = f"{D}{s['stage']}{R} {rc}{rk}{R}"
                else:
                    name = f"{D}??????{R}"
                    meta = f"{D}———{R}"
                cur = idx == i
                prefix = f"{B}▶{R} " if cur else "  "
                line = f"{prefix}{D}#{i+1:03d}{R} {mark} "
                nm = f"{B}{name}{R}" if cur and seen else name
                rows.append(f"  {line}{nm}  {meta}")
            body = ["", head, ""] + rows
            body += ["", f"  {D}[↑↓]이동  [←→]페이지  [Enter]상세  [ESC]뒤로{R}"]
            draw(body)
            k = read_key()
            if k in ("ESC", "q", "Q"):
                return
            elif k == "UP":
                idx = (idx - 1) % total
            elif k == "DOWN":
                idx = (idx + 1) % total
            elif k == "LEFT":
                idx = max(0, idx - PAGE)
            elif k == "RIGHT":
                idx = min(total - 1, idx + PAGE)
            elif k in ("\r", "\n"):
                idx = self._dex_detail(species, idx)

    def _dex_detail(self, species, idx):
        total = len(species)
        while True:
            s = species[idx]
            sid = str(s["id"])
            col = game.load_collection()
            ent = col["seen"].get(sid)
            seen = ent is not None
            caught = col["caught"].get(sid, 0)
            shiny = bool(ent and ent.get("shiny"))
            node = {"id": s["id"], "name": s["name"], "stage": s["stage"], "image": s["image"]}

            rc, rk = self._rar_label(s["rarity"])
            title = f"  {D}#{idx+1:03d}/{total:03d}{R}   " + (
                f"{B}{s['name']}{R}  {D}{s['stage']}{R}  {rc}{rk}{R}"
                + (f"  {G}✨{R}" if shiny else "") + (f"  {PUR}🌑다크{R}" if s.get("dark") else "")
                if seen else f"{B}??? ???{R}  {D}(미발견){R}")

            # 스프라이트
            info = []
            prev, nxts = lines.neighbors(s["line"], s["id"])
            if seen:
                info.append(f"{D}계열{R} {s['line']} 라인")
                chain = (f"{prev} → " if prev else "") + f"{B}{s['name']}{R}"
                if nxts:
                    chain += " → " + " / ".join(nxts)
                info.append(chain)
                info.append("")
                info.append(f"{G}● 잡음{R} {caught}회" if caught else f"{C}○ 봤지만 아직 못 잡음{R}")
                if shiny:
                    info.append(f"{G}✨ 이로치 발견{R}")
            else:
                info.append(f"{D}아직 발견하지 못한 디지몬.{R}")
                info.append(f"{D}키우다 보면 만날 수 있다.{R}")

            sx = self._sixel_for(node, shiny) if (self.use_sixel and seen) else None
            if sx:
                sys.stdout.write("\x1b[2J\x1b[H" + title + "\n\n  ")
                sys.stdout.write(sx)
                sys.stdout.write("\n" + "\n".join("  " + x for x in info))
                sys.stdout.write("\n\n  " + D + "[←→]다른 디지몬  [ESC]목록" + R)
                sys.stdout.flush()
            else:
                sp = _sprite_lines(node, 14, shiny=shiny, silhouette=not seen)
                spw = max((render._vlen(x) for x in sp), default=8)
                sp = [x + " " * (spw - render._vlen(x)) for x in sp]
                rows = max(len(sp), len(info))
                sp += [" " * spw] * (rows - len(sp))
                info2 = info + [""] * (rows - len(info))
                body = ["", title, ""] + [f"  {sp[i]}   {info2[i]}" for i in range(rows)]
                body += ["", f"  {D}[←→]다른 디지몬  [ESC]목록{R}"]
                draw(body)
            k = read_key()
            if k in ("ESC", "q", "Q"):
                return idx
            elif k == "LEFT":
                idx = (idx - 1) % total
            elif k == "RIGHT":
                idx = (idx + 1) % total

    # ── 미니게임 메뉴 ─────────────────────────────────────────────────
    def game_menu(self):
        while True:
            lines_ = ["", f"  {B}미니게임{R}", "",
                      f"  {B}[1]{R} 누구야! (실루엣 맞히기)   {D}맞히면 🍬{R}",
                      f"  {B}[2]{R} 배틀 (야생 디지몬과)      {D}이기면 🍬{R}",
                      f"  {B}[3]{R} 트레이닝 (타이밍)         {D}성장 보너스{R}",
                      "", f"  {B}[ESC]{R} 뒤로"]
            if self.msg:
                lines_ += ["", f"  {G}{self.msg}{R}"]
            draw(lines_)
            k = read_key()
            if k in ("ESC", "q", "Q"):
                self.msg = ""
                return
            if k == "1":
                self.mg_silhouette()
            elif k == "2":
                self.mg_battle()
            elif k == "3":
                self.mg_training()

    def _all_final_nodes(self):
        """도감/라인의 모든 노드(이름·스프라이트) 수집 — 문제 풀."""
        out = []
        def walk(n):
            out.append(n)
            for c in n["c"]:
                walk(c)
        for L in lines.all_lines():
            walk(L["tree"])
        return out

    # 미니게임 1: 실루엣 맞히기
    def mg_silhouette(self):
        pool = self._all_final_nodes()
        answer = self.rng.choice(pool)
        opts = [answer] + self.rng.sample([n for n in pool if n["name"] != answer["name"]], 3)
        self.rng.shuffle(opts)
        sil = _sprite_lines(answer, 12, silhouette=True)
        revealed = False
        while True:
            lines_ = ["", f"  {B}누구야?!{R}", ""]
            lines_ += ["    " + x for x in (sil if not revealed else _sprite_lines(answer, 12))]
            lines_.append("")
            for i, o in enumerate(opts, 1):
                mark = ""
                if revealed:
                    mark = f"  {GRN}← 정답{R}" if o["name"] == answer["name"] else ""
                lines_.append(f"  {B}[{i}]{R} {o['name']}{mark}")
            lines_.append("")
            if self.msg:
                lines_.append(f"  {self.msg}")
            lines_.append(f"  {D}[1-4] 선택   [ESC] 뒤로{R}")
            draw(lines_)
            k = read_key()
            if k in ("ESC", "q", "Q"):
                self.msg = ""
                return
            if not revealed and k in ("1", "2", "3", "4"):
                pick = opts[int(k) - 1]
                revealed = True
                if pick["name"] == answer["name"]:
                    game.grant_candy(self.state, 1)
                    self.save()
                    self.msg = f"{GRN}정답! 🍬 +1{R}"
                else:
                    self.msg = f"{RED}땡! 정답은 {answer['name']}{R}"

    # 미니게임 2: 배틀
    def mg_battle(self):
        me = self.state.get("active")
        if not me:
            self.msg = "알 상태에선 배틀 불가(부화 후)"
            return
        my_node = game.current_node(self.state)
        wild_line = self.rng.choice(lines.all_lines())
        wild_pool = self._nodes_of(wild_line["tree"])
        wild = self.rng.choice(wild_pool)
        my_hp = mx = 100 + me["stage_index"] * 25
        w_hp = wmx = 90 + self.rng.randint(0, 60)
        log = []
        moves = [("공격", 12, 26), ("강타", 6, 40)]
        while True:
            spm = ["  " + x for x in _sprite_lines(my_node, 8, shiny=me.get("is_shiny"))]
            spw = ["  " + x for x in _sprite_lines(wild, 8)]
            lines_ = ["", f"  {B}배틀!{R}  {my_node['name']}  vs  {wild['name']}", "",
                      f"  나 {GRN}{bar(my_hp/mx,14)}{R} {my_hp}/{mx}",
                      f"  적 {RED}{bar(max(0,w_hp)/wmx,14)}{R} {max(0,w_hp)}/{wmx}", ""]
            lines_ += log[-4:]
            lines_ += ["", f"  {B}[1]{R} 공격  {B}[2]{R} 강타  {B}[ESC]{R} 도망"]
            draw(lines_)
            if w_hp <= 0:
                game.grant_candy(self.state, 2)
                self.save()
                draw(lines_ + ["", f"  {GRN}승리! 🍬 +2{R}  아무 키."])
                read_key()
                self.msg = f"{GRN}배틀 승리 🍬+2{R}"
                return
            if my_hp <= 0:
                draw(lines_ + ["", f"  {RED}패배… 아무 키.{R}"])
                read_key()
                self.msg = f"{RED}배틀 패배{R}"
                return
            k = read_key()
            if k in ("ESC", "q", "Q"):
                self.msg = "도망쳤다"
                return
            if k in ("1", "2"):
                nm, lo, hi = moves[int(k) - 1]
                dmg = self.rng.randint(lo, hi)
                w_hp -= dmg
                log.append(f"  {C}{my_node['name']}의 {nm}! {dmg}{R}")
                if w_hp > 0:
                    wd = self.rng.randint(8, 22)
                    my_hp -= wd
                    log.append(f"  {RED}{wild['name']}의 반격! {wd}{R}")

    def _nodes_of(self, tree):
        out = []
        def walk(n):
            out.append(n)
            for c in n["c"]:
                walk(c)
        walk(tree)
        return out

    # 미니게임 3: 트레이닝(타이밍)
    def mg_training(self):
        if not self.state.get("active"):
            self.msg = "알 상태에선 트레이닝 불가"
            return
        width = 30
        pos = 0
        direction = 1
        center = width // 2
        while True:
            marker = [" "] * width
            marker[center] = "|"
            marker[max(0, min(width - 1, pos))] = "▮"
            barstr = "".join(marker)
            lines_ = ["", f"  {B}트레이닝 — 가운데(|)에 맞춰 SPACE!{R}", "",
                      f"  [{C}{barstr}{R}]", "",
                      f"  {D}SPACE 정지 · ESC 취소{R}"]
            draw(lines_)
            k = read_key(timeout=0.04)
            if k == " ":
                dist = abs(pos - center)
                acc = max(0.0, 1 - dist / center)
                xp = int(30_000_000 + acc * 120_000_000)  # 30M~150M
                ev = game.grant_xp(self.state, xp, self.rng)
                self.save()
                grade = "PERFECT!" if acc > 0.9 else ("GOOD" if acc > 0.5 else "…")
                extra = ""
                names = [e["name"] for e in ev if e["kind"] in ("evolve", "dark", "graduate")]
                if names:
                    extra = "  → " + ", ".join(names)
                draw(lines_ + ["", f"  {G}{grade} 성장 +{fmt(xp)}{extra}{R}", "  아무 키."])
                read_key()
                self.msg = f"트레이닝 {grade} +{fmt(xp)}"
                return
            if k in ("ESC", "q", "Q"):
                return
            pos += direction
            if pos >= width - 1 or pos <= 0:
                direction *= -1


def run(account=None, force_sixel=False):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    App(account, force_sixel=force_sixel).run()
    return True
