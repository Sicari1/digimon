# -*- coding: utf-8 -*-
"""sixel 비트맵 렌더 — 터미널에 진짜 이미지를 그린다(반블록보다 훨씬 고화질).

VS Code 통합 터미널·Windows Terminal 등 sixel 지원 터미널에서 동작. 지원 여부는
DA1 질의(ESC[c 응답에 '4')로 런타임 감지하고, 미지원이면 호출부가 반블록으로 폴백한다.
라이브러리 없이 순수 파이썬 인코더(팔레트 양자화 + 6픽셀 밴드 + RLE).
"""
import sys, select, termios, tty


def _q(v):
    return v * 100 // 255


def _rle(codes):
    """sixel 문자 런렝스 압축: 같은 문자 반복을 !<count><char> 로."""
    out = []
    i = 0
    n = len(codes)
    while i < n:
        j = i
        while j < n and codes[j] == codes[i]:
            j += 1
        run = j - i
        ch = chr(codes[i])
        if run >= 4:
            out.append("!%d%s" % (run, ch))
        else:
            out.append(ch * run)
        i = j
    return "".join(out)


def keyout_resize(im, target_h, bg):
    """흰 배경 키아웃 → 크롭 → target_h 로 리사이즈 → bg 위에 합성(RGB)."""
    from PIL import Image
    im = im.convert("RGBA")
    corner = im.getpixel((0, 0))[:3]
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < 40 or abs(r - corner[0]) + abs(g - corner[1]) + abs(b - corner[2]) <= 36:
                px[x, y] = (0, 0, 0, 0)
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    aspect = im.width / im.height
    th = target_h
    tw = max(2, int(round(th * aspect)))
    im = im.resize((tw, th), Image.LANCZOS)
    canvas = Image.new("RGBA", im.size, bg + (255,))
    canvas.alpha_composite(im)
    return canvas.convert("RGB")


def encode(im_rgb):
    """PIL RGB 이미지 → sixel 문자열."""
    from PIL import Image
    im = im_rgb.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT)
    pal = im.getpalette()
    data = im.load()
    W, H = im.size

    parts = ["\x1bP0;1;0q", '"1;1;%d;%d' % (W, H)]
    used_global = set(im.getdata())
    for c in sorted(used_global):
        parts.append("#%d;2;%d;%d;%d" % (c, _q(pal[3 * c]), _q(pal[3 * c + 1]), _q(pal[3 * c + 2])))

    for top in range(0, H, 6):
        colbits = {}
        rows = min(6, H - top)
        for x in range(W):
            for dy in range(rows):
                c = data[x, top + dy]
                arr = colbits.get(c)
                if arr is None:
                    arr = colbits[c] = [0] * W
                arr[x] |= (1 << dy)
        seg = []
        for c, arr in colbits.items():
            seg.append("#%d" % c + _rle([0x3F + b for b in arr]))
        parts.append("$".join(seg) + "-")
    parts.append("\x1b\\")
    return "".join(parts)


def render(path, target_h=220, bg=(18, 20, 26)):
    """PNG 경로 → sixel 문자열(실패 시 None)."""
    try:
        from PIL import Image
        im = Image.open(path)
        return encode(keyout_resize(im, target_h, bg))
    except Exception:
        return None


def supported(timeout=0.25):
    """현재 터미널이 sixel 지원하는지 DA1(ESC[c) 질의로 감지. TTY 아니면 False."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
    except Exception:
        return False
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[c")
        sys.stdout.flush()
        buf = ""
        end_deadline = timeout
        import time as _t
        t0 = _t.monotonic()
        while _t.monotonic() - t0 < end_deadline:
            r, _, _ = select.select([sys.stdin], [], [], end_deadline)
            if not r:
                break
            buf += sys.stdin.read(1)
            if buf.endswith("c"):
                break
        # 응답 예: ESC [ ? 62;4;... c  → 파라미터에 '4' 있으면 sixel
        if "[?" in buf:
            params = buf.split("[?", 1)[1].rstrip("c").split(";")
            return "4" in params
        return False
    except Exception:
        return False
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
