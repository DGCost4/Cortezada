#!/usr/bin/env python3
"""Gera o banner do canal (YouTube 2560x1440) a partir da logo. Uso: python3 scripts/gerar_banner.py"""
import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

RAIZ = Path(__file__).resolve().parent.parent
MARCA = RAIZ / "assets" / "marca"
W, H = 2560, 1440
SAFE = (507, 508, 2053, 931)  # área visível em TODOS os dispositivos (1546x423)
F_BLACK_IT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-BlackItalic.ttf"
F_BLACK = str(RAIZ / "assets" / "fonts" / "Roboto-Black.ttf")
MAGENTA, CIANO, AMARELO = (255, 43, 214), (24, 230, 255), (230, 255, 40)
random.seed(7)

# fundo: gradiente radial roxo escuro (mesmo tom da logo)
fundo = Image.new("RGB", (W, H))
px = fundo.load()
for y in range(H):
    for x in range(0, W):
        d = math.hypot((x - W / 2) / (W / 2), (y - H / 2) / (H / 2))
        k = max(0.0, 1 - d / 1.2)
        px[x, y] = (int(14 + 40 * k), int(6 + 12 * k), int(30 + 60 * k))
img = fundo.convert("RGBA")

# riscos de "corte" neon atravessando o banner (decoração, fica visível no PC/TV)
riscos = Image.new("RGBA", (W, H))
dr = ImageDraw.Draw(riscos)
for cor, y0, larg in [(MAGENTA, 300, 10), (CIANO, 1150, 8), (AMARELO, 1240, 4), (MAGENTA, 210, 4)]:
    dr.line([(-50, y0 + 260), (W + 50, y0 - 260)], fill=cor + (255,), width=larg)
for _ in range(70):  # faíscas
    x, y = random.randint(0, W), random.randint(0, H)
    if SAFE[0] - 40 < x < SAFE[2] + 40 and SAFE[1] - 40 < y < SAFE[3] + 40:
        continue
    s = random.randint(6, 22)
    cor = random.choice([MAGENTA, CIANO, AMARELO])
    dr.polygon([(x, y - s), (x + s / 3, y), (x, y + s), (x - s / 3, y)], fill=cor + (220,))
glow = riscos.filter(ImageFilter.GaussianBlur(14))
img = Image.alpha_composite(img, glow)
img = Image.alpha_composite(img, glow)
img = Image.alpha_composite(img, riscos)

# logo com borda suave (funde com o fundo)
logo = Image.open(MARCA / "logo.webp").convert("RGBA")
tam = 440
logo = logo.resize((tam, tam), Image.LANCZOS)
mask = Image.new("L", (tam, tam), 0)
ImageDraw.Draw(mask).ellipse((20, 20, tam - 20, tam - 20), fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(28))
logo.putalpha(ImageChops.multiply(logo.getchannel("A"), mask))
lx, ly = SAFE[0] - 10, (SAFE[1] + SAFE[3]) // 2 - tam // 2
img.alpha_composite(logo, (lx, ly))


def texto_neon(base, xy, txt, fonte, preenchimento, brilho, contorno=10):
    camada = Image.new("RGBA", base.size)
    d = ImageDraw.Draw(camada)
    d.text(xy, txt, font=fonte, fill=brilho + (255,), stroke_width=contorno + 8, stroke_fill=brilho + (255,))
    base = Image.alpha_composite(base, camada.filter(ImageFilter.GaussianBlur(22)))
    camada = Image.new("RGBA", base.size)
    d = ImageDraw.Draw(camada)
    d.text(xy, txt, font=fonte, fill=preenchimento, stroke_width=contorno, stroke_fill=(10, 0, 20, 255))
    return Image.alpha_composite(base, camada)


# nome do canal com gradiente amarelo -> magenta
tx = lx + tam + 10
tamf = 230
while True:  # maior fonte que cabe na área segura
    fonte = ImageFont.truetype(F_BLACK_IT, tamf)
    caixa = ImageDraw.Draw(img).textbbox((0, 0), "CORTIZADAS", font=fonte, stroke_width=10)
    if tx + caixa[2] <= SAFE[2] - 20:
        break
    tamf -= 4
tw, th = caixa[2] - caixa[0], caixa[3] - caixa[1]
ty = SAFE[1] + 30
img = texto_neon(img, (tx, ty), "CORTIZADAS", fonte, (255, 255, 255, 255), CIANO)
grad = Image.new("RGBA", (W, H))
gd = ImageDraw.Draw(grad)
for i in range(th + 60):
    k = i / (th + 60)
    cor = tuple(int(AMARELO[c] * (1 - k) + MAGENTA[c] * k) for c in range(3)) + (255,)
    gd.line([(0, ty + caixa[1] + i - 10), (W, ty + caixa[1] + i - 10)], fill=cor)
m = Image.new("L", (W, H), 0)
ImageDraw.Draw(m).text((tx, ty), "CORTIZADAS", font=fonte, fill=255)
grad.putalpha(m)
img = Image.alpha_composite(img, grad)

# slogan
f2 = ImageFont.truetype(F_BLACK, 58)
sy = ty + caixa[3] + 25
img = texto_neon(img, (tx + 12, sy), "SÓ A PARTE BOA DAS LIVES", f2, (255, 255, 255, 255), MAGENTA, contorno=5)

# selo "CORTES NOVOS TODO DIA"
f3 = ImageFont.truetype(F_BLACK, 44)
selo = "CORTES NOVOS TODO DIA"
b = ImageDraw.Draw(img).textbbox((0, 0), selo, font=f3)
px0, py0 = tx + 14, sy + 105
d = ImageDraw.Draw(img)
d.rounded_rectangle((px0, py0, px0 + b[2] + 56, py0 + b[3] + 30), radius=18, fill=AMARELO + (255,))
d.text((px0 + 28, py0 + 10), selo, font=f3, fill=(20, 5, 35, 255))
img = texto_neon(img, (px0 + b[2] + 90, py0 + 4), "@Cortez4d4", ImageFont.truetype(F_BLACK, 50),
                 (255, 255, 255, 255), CIANO, contorno=4)

tw = caixa[2]
saida = MARCA / "banner_youtube.png"
img.convert("RGB").save(saida, optimize=True)

# prévia com a área segura marcada (só para conferência)
prev = img.convert("RGB").copy()
ImageDraw.Draw(prev).rectangle(SAFE, outline=(255, 0, 0), width=6)
prev.resize((1280, 720), Image.LANCZOS).save(MARCA / "banner_previa_area_segura.png")
print(saida, f"texto termina em x={tx + tw} (área segura até {SAFE[2]})")
