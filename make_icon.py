"""Generate the Live Karaoke app icon.

Draws a microphone with radiating sound arcs on a dark rounded-square tile with
the app's dimmed-green accent, then exports a multi-resolution .ico and a .png.
Run:  python make_icon.py
"""
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
os.makedirs(ASSETS, exist_ok=True)

# palette (matches theme.py: true-black tile, dimmed-green accent + brighter companion)
BG1 = (14, 16, 14)
BG2 = (4, 8, 4)
ACC = (2, 130, 42)        # a touch brighter than #025500 so it reads at small sizes
ACC2 = (4, 200, 60)
INK = (235, 240, 235)
DIM = (150, 165, 150)

S = 1024                   # supersampled master size


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def rounded_rect_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def make_master():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # --- background tile: vertical gradient, rounded ---
    grad = Image.new("RGB", (1, S))
    gd = grad.load()
    for y in range(S):
        gd[0, y] = _lerp(BG1, BG2, y / (S - 1))
    grad = grad.resize((S, S))
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile.paste(grad, (0, 0))
    mask = rounded_rect_mask(S, int(S * 0.22))
    img.paste(tile, (0, 0), mask)

    # thin accent inner border for a crisp edge
    bd = ImageDraw.Draw(img)
    inset = int(S * 0.045)
    bd.rounded_rectangle(
        [inset, inset, S - inset, S - inset],
        radius=int(S * 0.18), outline=(*ACC, 90), width=max(2, S // 220),
    )

    cx = S * 0.5

    # --- radiating sound arcs (left & right of the mic) ---
    arc_c = (S * 0.5, S * 0.44)
    for i, r in enumerate((0.20, 0.28, 0.36)):
        rad = S * r
        col = _lerp(ACC2, ACC, i / 2.0)
        alpha = 235 - i * 55
        w = max(3, int(S * (0.020 - i * 0.004)))
        box = [arc_c[0] - rad, arc_c[1] - rad, arc_c[0] + rad, arc_c[1] + rad]
        d.arc(box, start=205, end=245, fill=(*col, alpha), width=w)   # left
        d.arc(box, start=-65, end=-25, fill=(*col, alpha), width=w)   # right

    # --- microphone capsule ---
    mic_w = S * 0.30
    mic_h = S * 0.46
    mx0 = cx - mic_w / 2
    my0 = S * 0.16
    mx1 = cx + mic_w / 2
    my1 = my0 + mic_h
    # body
    d.rounded_rectangle([mx0, my0, mx1, my1], radius=mic_w / 2,
                        fill=(*ACC, 255), outline=(*ACC2, 255), width=max(2, S // 180))
    # soft inner glow dot near the top of the capsule
    gcy = my0 + mic_h * 0.24
    gr = mic_w * 0.15
    d.ellipse([cx - gr, gcy - gr, cx + gr, gcy + gr],
              fill=(*_lerp(ACC2, INK, 0.55), 220))
    # evenly spaced grille lines below the dot
    line_col = (*_lerp(ACC2, INK, 0.22), 220)
    for i in range(3):
        yy = my0 + mic_h * (0.44 + i * 0.15)
        pad = mic_w * 0.22
        d.line([mx0 + pad, yy, mx1 - pad, yy], fill=line_col, width=max(2, S // 320))

    # --- stand: yoke arc + stem + base ---
    yoke_r = mic_w * 0.92
    yc = (cx, my1 - mic_w * 0.10)
    d.arc([yc[0] - yoke_r, yc[1] - yoke_r, yc[0] + yoke_r, yc[1] + yoke_r],
          start=20, end=160, fill=(*INK, 235), width=max(3, int(S * 0.022)))
    stem_top = yc[1] + yoke_r
    stem_bot = S * 0.90
    d.line([cx, stem_top, cx, stem_bot], fill=(*INK, 235), width=max(3, int(S * 0.026)))
    base_w = S * 0.26
    d.line([cx - base_w / 2, stem_bot, cx + base_w / 2, stem_bot],
           fill=(*INK, 235), width=max(3, int(S * 0.030)))

    return img


def main():
    master = make_master()
    png_path = os.path.join(ASSETS, "icon.png")
    master.resize((512, 512), Image.LANCZOS).save(png_path)

    ico_path = os.path.join(ASSETS, "icon.ico")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    master.save(ico_path, format="ICO",
                sizes=[(s, s) for s in sizes])
    print("wrote", png_path)
    print("wrote", ico_path, "sizes", sizes)


if __name__ == "__main__":
    main()
