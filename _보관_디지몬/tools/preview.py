# -*- coding: utf-8 -*-
"""터미널 카드를 PNG 로 미리보기 렌더(스크린샷 대용). 실제 사용량 + 데모 개체로 그린다."""
import sys, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from digitoken import usage, game, lines, render, sprite, limits as limmod

REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
BLK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
OUT = Path(__file__).resolve().parent.parent / "cache" / "preview.png"

BG = (18, 20, 26)
FG = (225, 227, 232)
GRAY = (150, 150, 150)
GREEN = (120, 200, 140)
GOLD = (235, 190, 70)
CYAN = (120, 200, 220)
RCOL = {"common": (170, 170, 170), "uncommon": (120, 200, 140),
        "rare": (110, 170, 230), "legendary": (220, 170, 70)}
RKO = {"common": "커먼", "uncommon": "언커먼", "rare": "레어", "legendary": "레전더리"}


def font(sz, bold=False):
    return ImageFont.truetype(BLK if bold else REG, sz)


def load_sprite(node, target_h=210):
    im = Image.open(sprite.fetch(node)).convert("RGBA")
    c = im.getpixel((0, 0))[:3]
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < 40 or abs(r - c[0]) + abs(g - c[1]) + abs(b - c[2]) <= 36:
                px[x, y] = (0, 0, 0, 0)
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    scale = target_h / im.height
    im = im.resize((int(im.width * scale), target_h), Image.NEAREST)
    return im


def main(line_key="agumon", stage_target=4, shiny=False, state=None):
    agg = usage.collect()
    tt, tc = agg.today()
    h5, _ = agg.last_hours(5)
    wk, wc = agg.last_days(7)

    if state is not None:
        st = state
    else:
        # 데모 개체: 지정 라인을 stage_target 까지 (분기는 랜덤이지만 시드 고정)
        st = game.default_state()
        rng = random.Random(1)
        st["install_baseline_set"] = True
        st["last_cumulative"] = 0
        L = lines.get_line(line_key)
        st["pending_line"] = line_key
        st["pending_shiny"] = shiny
        st["pending_nature"] = "brave"
        game._hatch(st, [], rng)
        for _ in range(stage_target):
            node = lines.node_at_path(L["tree"], st["active"]["path"])
            nxt = lines.next_branch(node, rng)
            if not nxt:
                break
            st["active"]["path"].append(nxt["id"])
            st["active"]["stage_index"] += 1
        st["active"]["used_at_stage"] = int(game.next_threshold(st) * 0.62)
        st["used_since_install"] = 1_080_000_000
        st["collected"] = ["x"]

    d = render.display(st)
    node = d["node"]
    spr = load_sprite(node)

    W, H = 780, 384
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)

    # 헤더
    dr.text((28, 18), "DigiTokenBar", font=font(22, True), fill=FG)
    dr.text((190, 24), "· Claude Code 토큰 → 디지몬", font=font(15), fill=GRAY)
    dr.line((28, 54, W - 28, 54), fill=(45, 48, 56), width=1)

    # 스프라이트
    sx, sy = 40, 75
    img.paste(spr, (sx, sy), spr)

    # 정보
    tx = 300
    y = 78
    PURPLE = (180, 130, 220)
    namecol = PURPLE if d.get("dark") else FG
    dr.text((tx, y), d["name"], font=font(24, True), fill=namecol)
    nw = dr.textlength(d["name"], font=font(24, True))
    dr.text((tx + nw + 14, y + 6), d["stage"], font=font(16), fill=GRAY)
    bx = tx + nw + 14 + dr.textlength(d["stage"], font=font(16)) + 12
    if d["shiny"]:
        dr.text((bx, y + 6), "★ SHINY", font=font(16, True), fill=GOLD)
    elif d.get("dark"):
        dr.text((bx, y + 6), "◆ DARK", font=font(16, True), fill=PURPLE)
    y += 40
    dr.text((tx, y), RKO[d["rarity"]], font=font(16, True), fill=RCOL[d["rarity"]])
    dr.text((tx + 70, y), f"성격 {game.NATURE_KO.get(d['nature'],'?')}", font=font(16), fill=GRAY)
    dr.text((tx + 200, y), f"단계 {d['stage_index']+1}/{d['total_forms']}", font=font(16), fill=GRAY)
    y += 44

    frac = d["cur"] / d["need"]
    dr.text((tx, y), "다음 진화까지", font=font(16), fill=FG)
    dr.text((tx + 130, y), f"{frac*100:.1f}%", font=font(16, True), fill=FG)
    y += 26
    bw, bh = 330, 16
    dr.rounded_rectangle((tx, y, tx + bw, y + bh), 4, fill=(40, 44, 52))
    dr.rounded_rectangle((tx, y, tx + int(bw * frac), y + bh), 4, fill=GREEN)
    dr.text((tx + bw + 12, y - 1), f"{render.fmt(d['cur'])}/{render.fmt(d['need'])}",
            font=font(13), fill=GRAY)
    y += 40

    def row(lbl, val, sub="", vcol=FG):
        dr.text((tx, y), lbl, font=font(16), fill=GRAY)
        dr.text((tx + 90, y), val, font=font(16, True), fill=vcol)
        if sub:
            dr.text((tx + 90 + dr.textlength(val, font=font(16, True)) + 14, y), sub,
                    font=font(14), fill=GRAY)

    row("오늘", f"{render.fmt(tt)} tok", f"${tc:,.2f}"); y += 30

    # 공식 한도 바(현재 계정, 실측)
    ld = limmod.fetch_all()
    acc, r, _ = limmod.current(ld)
    def limbar(lbl, util, resets):
        col = (220, 110, 110) if util >= 85 else ((235, 190, 70) if util >= 60 else CYAN)
        dr.text((tx, y), lbl, font=font(15), fill=GRAY)
        bx = tx + 66
        dr.rounded_rectangle((bx, y + 2, bx + 150, y + 14), 3, fill=(40, 44, 52))
        dr.rounded_rectangle((bx, y + 2, bx + int(150 * min(1, util / 100)), y + 14), 3, fill=col)
        dr.text((bx + 160, y), f"{util:.0f}%", font=font(15, True), fill=FG)
        dr.text((bx + 200, y), f"리셋 {limmod.reset_delta_str(resets)}", font=font(13), fill=GRAY)
    if r and "error" not in r:
        fh, sd = r["five_hour"], r["seven_day"]
        limbar("5시간", fh["util"] or 0, fh["resets_at"]); y += 28
        limbar("7일", sd["util"] or 0, sd["resets_at"]); y += 32
    else:
        y += 4
    dr.text((tx, y), f"재화 {render.fmt(game.currency(st))}   ·   🍬 x2   ·   도감 1종",
            font=font(14), fill=GOLD if game.currency(st) else GRAY); y += 24
    dr.text((tx, y), f"누적 {render.fmt(st['used_since_install'])} 성장",
            font=font(13), fill=GRAY)

    # 하단 이벤트
    dr.text((40, H - 34), f"▸▸ 진화! → {d['name']} ({d['stage']})", font=font(15), fill=CYAN)

    img.save(OUT)
    print(OUT)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "state":
        main(state=game.load_state())          # 저장된 실제 개체를 렌더
    else:
        key = sys.argv[1] if len(sys.argv) > 1 else "agumon"
        stg = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        sh = len(sys.argv) > 3 and sys.argv[3] == "shiny"
        main(key, stg, sh)
