# -*- coding: utf-8 -*-
"""원본 digi-api 이미지 vs 터미널 도트(반블록) 렌더 비교 문서(비교.html) 생성.

- 원본: digi-api 스프라이트(배경 키아웃 후 크롭).
- 도트: 터미널이 실제로 그리는 그리드(높이 13행=26px, 반블록)로 다운스케일 → 크게 확대(nearest).
  즉 터미널에서 보이는 그 픽셀을 그대로 확대한 것.
둘 다 base64 로 HTML 에 박아 넣어 오프라인 단독 파일로 연다.
"""
import sys, io, base64
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from digitoken import lines, sprite

OUT = Path(__file__).resolve().parent.parent / "비교.html"

# 보여줄 디지몬 (라인, 경로 끝 이름) — 다양하게
PICKS = [
    ("agumon", "Agumon"), ("agumon", "War Greymon"), ("agumon", "Skull Greymon"),
    ("patamon", "Seraphimon"), ("renamon", "Sakuyamon"),
    ("veemon", "Imperialdramon(Fighter Mode)"), ("guilmon", "Megalo Growmon"),
    ("gomamon", "Zudomon"),
]


def find_node(line_key, name):
    L = lines.get_line(line_key)
    found = [None]
    def walk(n):
        if n["name"] == name:
            found[0] = n
        for c in n["c"]:
            walk(c)
    walk(L["tree"])
    return found[0]


def keyed_crop(path):
    im = Image.open(path).convert("RGBA")
    c = im.getpixel((0, 0))[:3]
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < 40 or abs(r - c[0]) + abs(g - c[1]) + abs(b - c[2]) <= 36:
                px[x, y] = (0, 0, 0, 0)
    bb = im.getbbox()
    return im.crop(bb) if bb else im


def b64(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def dot_version(cropped, rows=13):
    """터미널 그리드(높이 rows*2 px)로 다운스케일 → nearest 확대."""
    th = rows * 2
    aspect = cropped.width / cropped.height
    tw = max(2, min(42, round(th * aspect)))
    grid = cropped.resize((tw, th), Image.NEAREST)
    return grid.resize((tw * 9, th * 9), Image.NEAREST)


def orig_version(cropped, target_h=234):
    aspect = cropped.width / cropped.height
    return cropped.resize((max(2, round(target_h * aspect)), target_h), Image.NEAREST)


def main():
    cards = []
    for key, name in PICKS:
        node = find_node(key, name)
        if not node:
            continue
        p = sprite.fetch(node)
        if not p:
            continue
        cropped = keyed_crop(p)
        orig = b64(orig_version(cropped))
        dot = b64(dot_version(cropped))
        cards.append((node["name"], node["stage"], orig, dot))

    rows_html = "\n".join(f"""
    <div class="card">
      <div class="name">{n} <span class="stage">{s}</span></div>
      <div class="pair">
        <figure><img src="{o}"><figcaption>원본 (digi-api)</figcaption></figure>
        <figure><img class="dot" src="{d}"><figcaption>터미널 도트 렌더</figcaption></figure>
      </div>
    </div>""" for n, s, o, d in cards)

    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>DigiTokenBar 렌더 비교</title>
<style>
  body{{background:#12141a;color:#e1e3e8;font-family:'Malgun Gothic',sans-serif;margin:0;padding:32px}}
  h1{{font-size:22px;margin:0 0 4px}}
  .sub{{color:#8a8f98;font-size:14px;margin-bottom:24px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:20px}}
  .card{{background:#1b1e26;border:1px solid #2a2e38;border-radius:10px;padding:16px}}
  .name{{font-weight:700;font-size:16px;margin-bottom:12px}}
  .stage{{color:#8a8f98;font-weight:400;font-size:13px}}
  .pair{{display:flex;gap:14px;align-items:flex-end;justify-content:center}}
  figure{{margin:0;text-align:center}}
  img{{height:200px;image-rendering:auto;background:#0d0f14;border-radius:6px;padding:6px}}
  img.dot{{image-rendering:pixelated}}
  figcaption{{color:#8a8f98;font-size:12px;margin-top:6px}}
</style></head><body>
  <h1>DigiTokenBar — 원본 vs 터미널 도트 렌더</h1>
  <div class="sub">왼쪽은 digi-api 원본 스프라이트, 오른쪽은 터미널이 트루컬러 반블록(▀)으로 그리는 실제 모습(약 28×26 픽셀 그리드를 확대).</div>
  <div class="grid">{rows_html}</div>
</body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(OUT, f"({len(cards)}종)")


if __name__ == "__main__":
    main()
