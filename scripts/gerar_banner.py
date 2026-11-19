#!/usr/bin/env python3
"""Gera o banner do canal CORTIZADAS (YouTube 2560x1440). Uso: python3 scripts/gerar_banner.py

Conceito: o nome do canal "fatiado" por um corte neon, fita de filme cortada,
adesivos com reações de chat e chão neon retrô. Tudo que é essencial fica na área segura.
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
MARCA = RAIZ / "assets" / "marca"
W, H = 2560, 1440
SAFE = (507, 508, 2053, 931)  # visível em todos os aparelhos (1546x423)
F_IT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-BlackItalic.ttf"
F_BK = str(RAIZ / "assets" / "fonts" / "Roboto-Black.ttf")
MAG, CIA, AMA = (255, 43, 214), (24, 230, 255), (230, 255, 40)
ESCURO = (16, 4, 32)
random.seed(11)


def brilho(camada, raio=18, vezes=2):
    g = camada.filter(ImageFilter.GaussianBlur(raio))
    base = Image.new("RGBA", camada.size)
    for _ in range(vezes):
        base = Image.alpha_composite(base, g)
    return Image.alpha_composite(base, camada)


def colar(img, camada):
    return Image.alpha_composite(img, camada)


# ---------- 1. fundo: gradiente + meio-tom (halftone) ----------
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
d = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2))
k = np.clip(1 - d / 1.25, 0, 1)
fundo = np.stack([12 + 48 * k, 4 + 10 * k, 26 + 70 * k], -1)
img = Image.fromarray(fundo.astype(np.uint8)).convert("RGBA")

ht = Image.new("RGBA", (W, H))
dh = ImageDraw.Draw(ht)
for y in range(0, H, 26):
    for x in range(0, W, 26):
        # bolinhas maiores nos cantos (estilo HQ)
        r = 1 + 6 * min(1, max(0, (math.hypot(x - W / 2, y - H / 2) / (W / 2)) - 0.25))
        dh.ellipse((x - r, y - r, x + r, y + r), fill=MAG + (38,))
img = colar(img, ht)

# ---------- 2. chão neon retrô (visível na TV) ----------
grade = Image.new("RGBA", (W, H))
dg = ImageDraw.Draw(grade)
hor = 1040
for i in range(-14, 15):
    dg.line([(W / 2 + i * 40, hor), (W / 2 + i * 330, H + 40)], fill=CIA + (110,), width=3)
for j in range(1, 12):
    y = hor + (H - hor) * (j / 11) ** 1.8
    dg.line([(0, y), (W, y)], fill=CIA + (110,), width=3)
fade = Image.new("L", (W, H), 0)
fd = ImageDraw.Draw(fade)
for y in range(hor, H):
    fd.line([(0, y), (W, y)], fill=int(255 * min(1, (y - hor) / 260)))
grade.putalpha(ImageChops.multiply(grade.getchannel("A"), fade))
img = colar(img, brilho(grade, 8, 1))
# sol neon no horizonte (atrás da área segura, aparece na TV)
sol = Image.new("RGBA", (W, H))
ds = ImageDraw.Draw(sol)
for i, y in enumerate(range(hor - 230, hor)):
    t = i / 230
    cor = tuple(int(AMA[c] * (1 - t) + MAG[c] * t) for c in range(3))
    meia = math.sqrt(max(0, 230 ** 2 - (hor - y) ** 2))
    if (hor - y) % 34 > 6 or y < hor - 140:
        ds.line([(W / 2 - meia, y), (W / 2 + meia, y)], fill=cor + (70,))
img = colar(img, sol.filter(ImageFilter.GaussianBlur(1)))


# ---------- 3. fita de filme cortada (topo, aparece no PC/TV) ----------
def fita(compr, alt=190, cores=None):
    f = Image.new("RGBA", (compr, alt), (8, 8, 12, 255))
    df = ImageDraw.Draw(f)
    for x in range(14, compr, 52):  # furinhos
        df.rounded_rectangle((x, 12, x + 26, 34), 5, fill=(230, 230, 240, 255))
        df.rounded_rectangle((x, alt - 34, x + 26, alt - 12), 5, fill=(230, 230, 240, 255))
    for i, x in enumerate(range(18, compr - 200, 230)):  # quadros com "cenas" coloridas
        c1, c2 = cores[i % len(cores)]
        q = Image.new("RGBA", (210, alt - 92))
        dq = ImageDraw.Draw(q)
        for yy_ in range(q.height):
            t = yy_ / q.height
            dq.line([(0, yy_), (210, yy_)], fill=tuple(int(c1[c] * (1 - t) + c2[c] * t) for c in range(3)) + (255,))
        dq.polygon([(70, 25), (70, q.height - 25), (150, q.height // 2)], fill=(255, 255, 255, 200))  # play
        f.alpha_composite(q, (x, 46))
    return f


paleta = [(MAG, (90, 0, 120)), (CIA, (0, 60, 140)), (AMA, (200, 80, 0)), ((255, 90, 60), (120, 0, 60))]
filme = fita(3200, cores=paleta)
corte_x = 1500
esq = filme.crop((0, 0, corte_x, filme.height)).rotate(9, expand=True, resample=Image.BICUBIC)
dir_ = filme.crop((corte_x, 0, filme.width, filme.height)).rotate(14, expand=True, resample=Image.BICUBIC)
camf = Image.new("RGBA", (W, H))
camf.alpha_composite(esq, (-420, 30))
camf.alpha_composite(dir_, (1110 + 40, -150))
sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
sombra.putalpha(camf.getchannel("A").filter(ImageFilter.GaussianBlur(20)).point(lambda v: v * 0.7))
img = colar(img, sombra)
img = colar(img, camf)
# faíscas no ponto do corte da fita
fa = Image.new("RGBA", (W, H))
dfa = ImageDraw.Draw(fa)
cx, cy = 1130, 300
for _ in range(60):
    ang = random.uniform(0, 2 * math.pi)
    r1, r2 = random.uniform(10, 40), random.uniform(60, 190)
    cor = random.choice([AMA, AMA, CIA, MAG])
    dfa.line([(cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)),
              (cx + r2 * math.cos(ang), cy + r2 * math.sin(ang))], fill=cor + (255,), width=random.randint(2, 5))
img = colar(img, brilho(fa, 12, 2))

# ---------- 4. adesivos de reação do chat (laterais: aparecem no PC) ----------
def adesivo(txt, cor_fundo, cor_txt, tam, ang):
    f = ImageFont.truetype(F_IT, tam)
    b = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), txt, font=f)
    w_, h_ = b[2] - b[0] + 70, b[3] - b[1] + 50
    a = Image.new("RGBA", (w_ + 30, h_ + 30))
    da = ImageDraw.Draw(a)
    da.rounded_rectangle((15, 15, w_ + 15, h_ + 15), 22, fill=(255, 255, 255, 255))  # borda de adesivo
    da.rounded_rectangle((25, 25, w_ + 5, h_ + 5), 16, fill=cor_fundo + (255,))
    da.text((50 - b[0], 40 - b[1]), txt, font=f, fill=cor_txt)
    return a.rotate(ang, expand=True, resample=Image.BICUBIC)


adesivos = [("KKKKKKK", MAG, (255, 255, 255), 64, 8, (90, 560)),
            ("CLIPA!!", AMA, ESCURO, 70, -10, (150, 760)),
            ("MEU DEUS", CIA, ESCURO, 60, -6, (2110, 540)),
            ("NÃO ACREDITO", (255, 90, 60), (255, 255, 255), 50, 9, (2090, 760))]
for txt, cf, ct, tam, ang, pos in adesivos:
    a = adesivo(txt, cf, ct, tam, ang)
    s = Image.new("RGBA", (W, H))
    s.alpha_composite(a, pos)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.putalpha(s.getchannel("A").filter(ImageFilter.GaussianBlur(10)).point(lambda v: v * 0.6))
    img = colar(img, sh.transform((W, H), Image.AFFINE, (1, 0, -8, 0, 1, -10)))
    img = colar(img, s)

# ---------- 5. logo ----------
logo = Image.open(MARCA / "logo.webp").convert("RGBA")
tam = 430
logo = logo.resize((tam, tam), Image.LANCZOS)
m = Image.new("L", (tam, tam), 0)
ImageDraw.Draw(m).ellipse((24, 24, tam - 24, tam - 24), fill=255)
logo.putalpha(ImageChops.multiply(logo.getchannel("A"), m.filter(ImageFilter.GaussianBlur(26))))
lx, ly = SAFE[0] + 5, (SAFE[1] + SAFE[3]) // 2 - tam // 2
anel = Image.new("RGBA", (W, H))
ImageDraw.Draw(anel).ellipse((lx + 30, ly + 30, lx + tam - 30, ly + tam - 30), outline=CIA + (255,), width=6)
img = colar(img, brilho(anel, 16, 2))
img.alpha_composite(logo, (lx, ly))

# ---------- 6. nome FATIADO pelo corte neon ----------
tx = lx + tam + 15
tf = 240
while True:
    fonte = ImageFont.truetype(F_IT, tf)
    cx_ = ImageDraw.Draw(img).textbbox((0, 0), "CORTIZADAS", font=fonte, stroke_width=12)
    if tx + cx_[2] <= SAFE[2] - 30:
        break
    tf -= 4
ty = SAFE[1] + 36
txt = Image.new("RGBA", (W, H))
dt = ImageDraw.Draw(txt)
dt.text((tx, ty), "CORTIZADAS", font=fonte, fill=(255, 255, 255, 255), stroke_width=12, stroke_fill=ESCURO + (255,))
# preenchimento em degradê amarelo -> magenta
grad = Image.new("RGBA", (W, H))
gd = ImageDraw.Draw(grad)
y0, y1 = ty + cx_[1], ty + cx_[3]
for y in range(y0, y1 + 1):
    t = (y - y0) / max(1, y1 - y0)
    gd.line([(0, y), (W, y)], fill=tuple(int(AMA[c] * (1 - t) + MAG[c] * t) for c in range(3)) + (255,))
mk = Image.new("L", (W, H), 0)
ImageDraw.Draw(mk).text((tx, ty), "CORTIZADAS", font=fonte, fill=255)
grad.putalpha(mk)
txt = Image.alpha_composite(txt, grad)
# 3D: sombra extrudada em ciano
ext = Image.new("RGBA", (W, H))
alfa = txt.getchannel("A")
for i in range(1, 14):
    s = Image.new("RGBA", (W, H), (0, 120, 160, 255))
    s.putalpha(alfa)
    ext.alpha_composite(s.transform((W, H), Image.AFFINE, (1, 0, -i, 0, 1, -i)))
txt = Image.alpha_composite(ext, txt)
# corte diagonal: parte de cima desliza para a direita/cima
ax, ay = tx - 40, ty + cx_[3] * 0.80
bx, by = tx + cx_[2] + 40, ty + cx_[3] * 0.30
cima = Image.new("L", (W, H), 0)
ImageDraw.Draw(cima).polygon([(0, 0), (W, 0), (W, by + (W - bx) * (by - ay) / (bx - ax)),
                              (0, ay - ax * (by - ay) / (bx - ax))], fill=255)
parte_cima = txt.copy()
parte_cima.putalpha(ImageChops.multiply(txt.getchannel("A"), cima))
parte_baixo = txt.copy()
parte_baixo.putalpha(ImageChops.multiply(txt.getchannel("A"), ImageChops.invert(cima)))
dx, dy = 30, -18
nome = Image.new("RGBA", (W, H))
nome.alpha_composite(parte_baixo)
nome.alpha_composite(parte_cima.transform((W, H), Image.AFFINE, (1, 0, -dx, 0, 1, -dy)))
# brilho atrás do nome
glow = Image.new("RGBA", (W, H), MAG + (255,))
glow.putalpha(nome.getchannel("A").filter(ImageFilter.GaussianBlur(30)).point(lambda v: v * 0.55))
img = colar(img, glow)
img = colar(img, nome)
# a lâmina: linha neon do corte + faíscas nas pontas
lam = Image.new("RGBA", (W, H))
dl = ImageDraw.Draw(lam)
p0 = (ax + 10, ay - 2)
p1 = (bx - 10, by + 2)
dl.line([p0, p1], fill=(255, 255, 255, 255), width=7)
for _ in range(26):
    px_, py_ = random.choice([p0, p1])
    ang = random.uniform(0, 2 * math.pi)
    r = random.uniform(20, 70)
    dl.line([(px_, py_), (px_ + r * math.cos(ang), py_ + r * math.sin(ang))], fill=random.choice([AMA, CIA]) + (255,), width=3)
lam_glow = Image.new("RGBA", (W, H), CIA + (255,))
lam_glow.putalpha(lam.getchannel("A").filter(ImageFilter.GaussianBlur(12)))
img = colar(img, lam_glow)
img = colar(img, lam_glow)
img = colar(img, lam)

# ---------- 7. slogan com linha tracejada de "recorte" + @ ----------
f2 = ImageFont.truetype(F_BK, 50)
sy = ty + cx_[3] + 22
d = ImageDraw.Draw(img)
slogan = "SÓ A PARTE BOA DAS LIVES"
bs = d.textbbox((0, 0), slogan, font=f2)
d.rounded_rectangle((tx + 6, sy - 4, tx + bs[2] + 50, sy + bs[3] + 22), 14, fill=ESCURO + (230,))
for x in range(int(tx + 6), int(tx + bs[2] + 50), 26):  # tracejado de recorte em volta
    d.line([(x, sy - 14), (x + 13, sy - 14)], fill=(255, 255, 255, 200), width=3)
    d.line([(x, sy + bs[3] + 32), (x + 13, sy + bs[3] + 32)], fill=(255, 255, 255, 200), width=3)
d.text((tx + 28, sy + 6), slogan, font=f2, fill=(255, 255, 255, 255))
f3 = ImageFont.truetype(F_IT, 50)
ax3 = tx + bs[2] + 72
arr = Image.new("RGBA", (W, H))
ImageDraw.Draw(arr).text((ax3, sy + 4), "@Cortez4d4", font=f3, fill=AMA + (255,), stroke_width=4, stroke_fill=ESCURO + (255,))
img = colar(img, brilho(arr, 10, 1))
fim_arroba = ax3 + ImageDraw.Draw(img).textbbox((0, 0), "@Cortez4d4", font=f3)[2]

# selo "NOVO TODO DIA" carimbado sobre o canto da logo
selo = adesivo("CORTES TODO DIA", (255, 60, 90), (255, 255, 255), 34, 12)
img.alpha_composite(selo, (lx + tam - selo.width + 40, ly + tam - selo.height + 18))

saida = MARCA / "banner_youtube.png"
img.convert("RGB").save(saida, optimize=True)
prev = img.convert("RGB")
ImageDraw.Draw(prev).rectangle(SAFE, outline=(255, 0, 0), width=6)
prev.resize((1280, 720), Image.LANCZOS).save(MARCA / "banner_previa_area_segura.png")
img.convert("RGB").crop((SAFE[0], SAFE[1], SAFE[2], SAFE[3])).save(MARCA / "banner_previa_celular.png")
print(saida, f"nome até x={tx + cx_[2]}, @ até x={fim_arroba} (limite {SAFE[2]})")
