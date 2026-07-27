# -*- coding: utf-8 -*-
"""digi-api 스프라이트 PNG → 터미널 트루컬러 반블록(▀) 아트.

- 반블록 기법: 한 글자에 위/아래 두 픽셀을 담는다(fg=위, bg=아래, 글자='▀'). 세로 해상도 2배.
- 이로치(shiny): 색상(hue)을 회전해 다른 팔레트로.
- 다운로드는 digi-api(Cloudflare) 라 UA 헤더 필수. cache/sprites/{id}.png 로 캐시.
"""
import colorsys
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "sprites"

RESET = "\x1b[0m"


def _session():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (digitoken)"
    return s


def fetch(node):
    """노드 스프라이트 로컬 경로(없으면 다운로드). 실패 시 None."""
    img = node.get("image")
    if not img:
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".png"
    dst = CACHE_DIR / f"{node['id']}{ext}"
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    try:
        r = _session().get(img, timeout=20)
        r.raise_for_status()
        dst.write_bytes(r.content)
        return dst
    except Exception:
        return None


def _shift_hue(rgb, deg):
    r, g, b = [c / 255.0 for c in rgb]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + deg / 360.0) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


def render(path, height=14, shiny=False, max_width=120, silhouette=False):
    """PNG → ANSI 문자열 리스트(각 원소 = 한 줄). 실패 시 None."""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None

    # digi-api 스프라이트는 투명이 아니라 흰 배경이 많다 → 코너 색을 배경으로 감지해 키아웃.
    corners = [im.getpixel((0, 0)), im.getpixel((im.width - 1, 0)),
               im.getpixel((0, im.height - 1)), im.getpixel((im.width - 1, im.height - 1))]
    opaque = [c for c in corners if c[3] >= 16]
    bg = opaque[0][:3] if opaque else None            # 전부 투명이면 알파만으로 판정

    def _off(r, g, b, a):
        if a < 40:
            return True
        if bg is not None:
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) <= 36:
                return True
        return False

    # 배경 키아웃 후 콘텐츠 bbox 로 크롭
    mask = Image.new("L", im.size, 0)
    mpx = mask.load()
    ipx = im.load()
    for yy in range(im.height):
        for xx in range(im.width):
            r, g, b, a = ipx[xx, yy]
            mpx[xx, yy] = 0 if _off(r, g, b, a) else 255
    bbox = mask.getbbox()
    if bbox:
        im = im.crop(bbox)

    # 반블록: 세로 픽셀 = height*2. 가로는 종횡비 유지(글자 2:1 보정 위해 가로 확대).
    target_h = max(2, height * 2)
    aspect = im.width / im.height
    target_w = int(round(target_h * aspect))          # 픽셀 폭
    target_w = min(target_w, max_width)
    target_w = max(2, target_w)
    im = im.resize((target_w, target_h), Image.NEAREST)
    px = im.load()
    W, H = im.size

    A = 96  # 알파 임계(이하 = 투명)
    lines = []
    for y in range(0, H - 1, 2):
        buf = []
        cur = None  # (fg, bg) 마지막 상태 — 같은 색 연속이면 escape 재사용 생략
        for x in range(W):
            tr, tg, tb, ta = px[x, y]
            br, bg_, bb, ba = px[x, y + 1]
            top_on = not _off(tr, tg, tb, ta)
            bot_on = not _off(br, bg_, bb, ba)
            if silhouette:
                # 실루엣: 켜진 픽셀을 전부 어두운 단색으로(누구야! 게임용)
                if top_on:
                    tr, tg, tb = 45, 45, 58
                if bot_on:
                    br, bg_, bb = 45, 45, 58
            elif shiny:
                if top_on:
                    tr, tg, tb = _shift_hue((tr, tg, tb), 150)
                if bot_on:
                    br, bg_, bb = _shift_hue((br, bg_, bb), 150)
            if not top_on and not bot_on:
                buf.append(RESET + " ")
                cur = None
            elif top_on and bot_on:
                buf.append(f"\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg_};{bb}m▀")
            elif top_on:
                buf.append(f"\x1b[0m\x1b[38;2;{tr};{tg};{tb}m▀")
            else:  # bottom only
                buf.append(f"\x1b[0m\x1b[38;2;{br};{bg_};{bb}m▄")
        lines.append("".join(buf) + RESET)
    return lines


def placeholder(height=14):
    """스프라이트를 못 받았을 때의 알/실루엣 대체(간단 ASCII)."""
    egg = ["   ___   ", "  /   \\  ", " | ° ° | ", " |  ▿  | ", "  \\___/  "]
    return egg
