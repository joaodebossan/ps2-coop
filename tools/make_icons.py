#!/usr/bin/env python3
"""Gera assets/icon.png, assets/icon.ico e web/icon.png.

Ferramenta de build (usa Pillow). O app em si não depende de Pillow.
Execute na raiz do projeto: python3 tools/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SIZE = 1024
SS = 2
C = SIZE * SS


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (size, size), top)
    draw = ImageDraw.Draw(image)
    for y in range(size):
        t = y / max(1, size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=(lerp(top[0], bottom[0], t), lerp(top[1], bottom[1], t), lerp(top[2], bottom[2], t)),
        )
    return image


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def draw_icon() -> Image.Image:
    canvas = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    bg = gradient(C, (53, 55, 65), (31, 32, 39)).convert("RGBA")
    mask = rounded_mask(C, int(C * 0.21))
    canvas.paste(bg, (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    unit = C / 1024

    def box(values: list[float]) -> list[int]:
        return [int(value * unit) for value in values]

    # brilho suave no canto superior esquerdo
    glow = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(box([-220, -300, 620, 480]), fill=(255, 220, 150, 22))
    canvas.alpha_composite(glow)

    # borda interna
    draw.rounded_rectangle(box([10, 10, 1014, 1014]), radius=int(205 * unit), outline=(92, 95, 112, 150), width=int(5 * unit))

    # arcos de rede no canto superior direito
    for i, (r, alpha) in enumerate([(92, 210), (150, 170), (208, 120)]):
        draw.arc(
            box([1014 - r * 2, 34, 1014 + r * 0.9, 34 + r * 2]),
            start=198,
            end=342,
            fill=(126, 220, 166, alpha),
            width=int(15 * unit),
        )

    # alças do controle
    gold_top = (243, 210, 136, 255)
    gold_bottom = (209, 158, 63, 255)
    body = gradient(C, gold_top[:3], gold_bottom[:3]).convert("RGBA")
    grip_mask = Image.new("L", (C, C), 0)
    gm = ImageDraw.Draw(grip_mask)
    gm.rounded_rectangle(box([142, 452, 432, 846]), radius=int(142 * unit), fill=255)
    gm.rounded_rectangle(box([592, 452, 882, 846]), radius=int(142 * unit), fill=255)
    canvas.paste(body, (0, 0), grip_mask)
    draw = ImageDraw.Draw(canvas)

    # corpo principal
    body_mask = Image.new("L", (C, C), 0)
    bm = ImageDraw.Draw(body_mask)
    bm.rounded_rectangle(box([188, 344, 836, 690]), radius=int(155 * unit), fill=255)
    canvas.paste(body, (0, 0), body_mask)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box([188, 344, 836, 690]), radius=int(155 * unit), outline=(92, 60, 12, 255), width=int(7 * unit))

    # sombra interna na parte de baixo do corpo
    shade = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.ellipse(box([190, 610, 834, 760]), fill=(92, 60, 12, 28))
    canvas.alpha_composite(shade)
    draw = ImageDraw.Draw(canvas)

    dark = (39, 30, 18, 255)
    # d-pad
    draw.rounded_rectangle(box([288, 420, 354, 612]), radius=int(18 * unit), fill=dark)
    draw.rounded_rectangle(box([234, 486, 408, 546]), radius=int(18 * unit), fill=dark)
    # botões frontais
    buttons = [
        ([700, 430], (112, 214, 157, 255)),
        ([770, 493], (244, 128, 128, 255)),
        ([700, 556], (128, 168, 244, 255)),
        ([630, 493], (200, 159, 244, 255)),
    ]
    for (cx, cy), color in buttons:
        draw.ellipse(box([cx - 34, cy - 34, cx + 34, cy + 34]), fill=color, outline=(55, 35, 12, 255), width=int(5 * unit))
    # analógicos
    for cx in (446, 548):
        draw.ellipse(box([cx - 45, 575, cx + 45, 665]), fill=(63, 48, 27, 255), outline=(34, 25, 13, 255), width=int(5 * unit))
        draw.ellipse(box([cx - 24, 596, cx + 24, 644]), fill=(125, 95, 45, 255))
    # select/start
    draw.rounded_rectangle(box([430, 704, 500, 726]), radius=int(11 * unit), fill=dark)
    draw.rounded_rectangle(box([524, 704, 594, 726]), radius=int(11 * unit), fill=dark)

    # pequeno selo PS2 no topo esquerdo
    draw.rounded_rectangle(box([110, 92, 330, 196]), radius=int(26 * unit), fill=(32, 33, 40, 210), outline=(120, 96, 52, 220), width=int(4 * unit))
    font = None
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        try:
            font = ImageFont.truetype(candidate, int(58 * unit))
            break
        except OSError:
            continue
    draw.text((int(142 * unit), int(106 * unit)), "PS2", font=font, fill=(235, 203, 130, 255))

    return canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    icon = draw_icon()
    assets = ROOT / "assets"
    web = ROOT / "web"
    assets.mkdir(exist_ok=True)
    web.mkdir(exist_ok=True)
    icon.save(assets / "icon.png")
    icon.save(web / "icon.png")
    icon.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Ícones gerados em assets/ e web/.")


if __name__ == "__main__":
    main()
