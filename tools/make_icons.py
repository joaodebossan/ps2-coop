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
    bg = gradient(C, (45, 48, 57), (21, 22, 27)).convert("RGBA")
    mask = rounded_mask(C, int(C * 0.21))
    canvas.paste(bg, (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    unit = C / 1024

    def box(values: list[float]) -> list[int]:
        return [int(value * unit) for value in values]

    # brilho suave no canto superior esquerdo
    glow = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(box([-220, -300, 620, 480]), fill=(46, 155, 255, 28))
    canvas.alpha_composite(glow)

    # borda interna
    draw.rounded_rectangle(box([10, 10, 1014, 1014]), radius=int(205 * unit), outline=(112, 120, 136, 160), width=int(5 * unit))

    # arcos de rede no canto superior direito
    for i, (r, alpha) in enumerate([(92, 210), (150, 170), (208, 120)]):
        draw.arc(
            box([1014 - r * 2, 34, 1014 + r * 0.9, 34 + r * 2]),
            start=198,
            end=342,
            fill=(80, 170, 255, alpha),
            width=int(15 * unit),
        )

    # alças do controle
    silver_top = (243, 246, 250, 255)
    silver_bottom = (154, 162, 176, 255)
    body = gradient(C, silver_top[:3], silver_bottom[:3]).convert("RGBA")
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
    draw.rounded_rectangle(box([188, 344, 836, 690]), radius=int(155 * unit), outline=(55, 62, 76, 255), width=int(7 * unit))

    # sombra interna na parte de baixo do corpo
    shade = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.ellipse(box([190, 610, 834, 760]), fill=(35, 42, 55, 30))
    canvas.alpha_composite(shade)
    draw = ImageDraw.Draw(canvas)

    dark = (27, 30, 37, 255)
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
        draw.ellipse(box([cx - 34, cy - 34, cx + 34, cy + 34]), fill=color, outline=(28, 32, 40, 255), width=int(5 * unit))
    # analógicos
    for cx in (446, 548):
        draw.ellipse(box([cx - 45, 575, cx + 45, 665]), fill=(38, 43, 53, 255), outline=(24, 27, 34, 255), width=int(5 * unit))
        draw.ellipse(box([cx - 24, 596, cx + 24, 644]), fill=(110, 119, 133, 255))
    # select/start
    draw.rounded_rectangle(box([430, 704, 500, 726]), radius=int(11 * unit), fill=dark)
    draw.rounded_rectangle(box([524, 704, 594, 726]), radius=int(11 * unit), fill=dark)

    # pequeno selo PS2 no topo esquerdo
    draw.rounded_rectangle(box([110, 92, 330, 196]), radius=int(26 * unit), fill=(19, 21, 27, 235), outline=(46, 155, 255, 235), width=int(4 * unit))
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
    # texto PS2 com degradê azul, como o logo do console
    text_mask = Image.new("L", (C, C), 0)
    ImageDraw.Draw(text_mask).text((int(142 * unit), int(106 * unit)), "PS2", font=font, fill=255)
    blue = gradient(C, (12, 58, 150), (106, 205, 255)).convert("RGBA")
    canvas.paste(blue, (0, 0), text_mask)

    return canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    icon = draw_icon()
    assets = ROOT / "assets"
    web = ROOT / "web"
    assets.mkdir(exist_ok=True)
    web.mkdir(exist_ok=True)
    icon.save(assets / "icon.png")
    icon.save(web / "icon.png")
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(assets / "icon-256.png")
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(web / "icon-256.png")
    icon.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Ícones gerados em assets/ e web/.")


if __name__ == "__main__":
    main()
