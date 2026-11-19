#!/usr/bin/env python3
"""
Estilo DINÂMICO de corte (diferenciação do canal Cortizadas).

Pipeline:
  1. Jump cuts: remove silêncios/tempo morto (mantém fala e momentos de áudio alto)
  2. Base (FFmpeg): gameplay em tela cheia 9:16, zoom alternado a cada corte, punch-in + tremida no pico,
     câmera do streamer numa bolha com borda roxa que CRESCE na hora da reação
  3. Motion graphics (HyperFrames): card de gancho animado, legendas com palavra-chave roxa em pop,
     emojis nas palavras de hype, barra de progresso — renderizado com fundo transparente
  4. Composição final + áudio normalizado (-14 LUFS)

Uso:
  python3 scripts/dinamico.py trabalho/<live>/cortes.json --ids c01 --cam 14:39:274:176
  python3 scripts/dinamico.py trabalho/<live>/cortes.json --ids c01 --cam 14:39:274:176 --storyboard   # só o storyboard
"""
import argparse
import html
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analisar import HYPE_RE, sem_acento  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
MOTION = RAIZ / "motion"
W, H, FPS = 1080, 1920, 30
ROXO = "#B44CFF"

EMOJIS = [  # (regex sem acento, emoji)
    (r"\bmeu deus\b|\bnossa\b|\bnao acredito\b|\bque isso\b", "😱"),
    (r"\bdinheiro\b|\bgrana\b|\brico\b|\bpaga\w*", "💰"),
    (r"\bk{3,}|\bhaha|\brindo\b|\bengracad\w*", "😂"),
    (r"\bpolicia\w*|\bpreso\b|\bviatura\b|\bcana\b", "🚓"),
    (r"\bexplod\w*|\bfogo\b|\bbomba\b", "💥"),
    (r"\bmorr\w*|\bmatar\w*|\bmatou\b|\bmatei\b", "💀"),
    (r"\bcorre+\b|\bfoge\b|\bfuga\b|\bvai vai\b", "🏃"),
    (r"\bcaralh\w*|\bporra\b|\bpqp\b|\binsano\b|\bsurreal\b", "🤯"),
    (r"\bcarro\b|\bmoto\b|\bdirig\w*", "🚗"),
    (r"\bbriga\w*|\bsoco\b|\bluta\w*|\bporrada\b", "🥊"),
]
EMOJI_RE = [(re.compile(p), e) for p, e in EMOJIS]


def run(cmd, **kw):
    kw.setdefault("text", True)
    r = subprocess.run(cmd, capture_output=True, **kw)
    if r.returncode:
        err = r.stderr if isinstance(r.stderr, str) else r.stderr.decode(errors="ignore")
        out = r.stdout if isinstance(r.stdout, str) else ""
        sys.exit(f"Erro em {' '.join(map(str, cmd[:3]))}...\n{err[-3000:]}{out[-2000:]}")
    return r


# ---------------------------------------------------------------- 1. jump cuts
def segmentos_mantidos(video, corte, palavras, gap_max=0.55, pad=0.12):
    """Mantém trechos com fala; remove pausas longas, a não ser que o áudio esteja alto (ação do jogo)."""
    ini, fim = corte["inicio"], corte["fim"]
    pcm = run(["ffmpeg", "-v", "error", "-ss", f"{ini}", "-t", f"{fim - ini}", "-i", str(video),
               "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], text=False).stdout
    a = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    bloco = 1600  # 0,1 s
    n = len(a) // bloco
    rms = 20 * np.log10(np.sqrt((a[: n * bloco].reshape(n, bloco) ** 2).mean(1)) + 1e-9)
    alto = rms > np.percentile(rms, 70)
    falado = np.zeros(n, bool)
    for w in palavras:
        falado[max(0, int((w["inicio"] - pad) * 10)): int((w["fim"] + pad) * 10) + 1] = True
    pk = corte.get("pico", ini) - ini
    falado[max(0, int((pk - 1.5) * 10)): int((pk + 2.0) * 10)] = True  # o pico fica sempre
    manter = falado | alto
    # fecha buracos curtos (não picotar demais)
    i = 0
    while i < n:
        if not manter[i]:
            j = i
            while j < n and not manter[j]:
                j += 1
            if (j - i) / 10 < gap_max:
                manter[i:j] = True
            i = j
        else:
            i += 1
    segs, i = [], 0
    while i < n:
        if manter[i]:
            j = i
            while j < n and manter[j]:
                j += 1
            if (j - i) / 10 >= 0.4:
                segs.append((round(i / 10, 2), round(j / 10, 2)))
            i = j
        else:
            i += 1
    return segs or [(0.0, round(fim - ini, 2))]


def mapear(t, segs):
    """tempo relativo ao corte -> tempo no vídeo editado (None se caiu num trecho removido)."""
    off = 0.0
    for s0, s1 in segs:
        if s0 <= t <= s1:
            return off + (t - s0)
        off += s1 - s0
    return None


# ---------------------------------------------------------------- 2. base FFmpeg
def mascara_bolha(w, h, raio, borda, caminho_mask, caminho_borda):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), raio, fill=255)
    m.save(caminho_mask)
    b = Image.new("RGBA", (w + 2 * borda, h + 2 * borda), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    d.rounded_rectangle((0, 0, w + 2 * borda - 1, h + 2 * borda - 1), raio + borda, fill=(180, 76, 255, 255))
    d.rounded_rectangle((borda, borda, w + borda - 1, h + borda - 1), raio, fill=(0, 0, 0, 0))
    b.save(caminho_borda)


def render_base(video, corte, segs, cam, pico_out, tmp: Path, src_w, src_h):
    ini = corte["inicio"]
    dur_out = sum(b - a for a, b in segs)
    sel = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in segs)
    # passo 1: aplica os jump cuts
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.2f}", "-t", f"{segs[-1][1] + 0.1:.2f}", "-i", str(video),
         "-vf", f"fps={FPS},select='{sel}',setpts=N/{FPS}/TB", "-af", f"aselect='{sel}',asetpts=N/SR/TB",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-c:a", "pcm_s16le", str(tmp / "cut.mkv")])

    # zoom alternado por segmento + punch-in no pico
    niveis = [1.0, 1.12, 1.05, 1.18]
    expr, off = "1", 0.0
    for i, (a, b) in enumerate(segs):
        d = b - a
        expr = f"if(between(it,{off:.2f},{off + d:.2f}),{niveis[i % len(niveis)]},{expr})"
        off += d
    p0, p1 = pico_out - 0.1, pico_out + 0.9
    z = f"if(between(it,{p0:.2f},{p1:.2f}),1.32,{expr})"
    tremida = f"if(between(it,{p0:.2f},{p0 + 0.5:.2f}),18*sin(it*75),0)"

    # recorte 9:16 central do gameplay (fora da área da câmera)
    gw = int(src_h * 9 / 16) // 2 * 2
    gx = (src_w - gw) // 2
    cx, cy, cw, ch = cam
    bp, bg = (440, int(440 * ch / cw)), (760, int(760 * ch / cw))  # bolha normal / grande
    borda = 8
    for nome, (bw, bh) in (("p", bp), ("g", bg)):
        mascara_bolha(bw, bh, 36, borda, tmp / f"mask_{nome}.png", tmp / f"borda_{nome}.png")
    yb, xb = 110, 40  # bolha no canto superior esquerdo (cresce a partir do canto)
    filtro = (
        f"[0:v]split=3[g][c1][c2];"
        f"[g]crop={gw}:{src_h}:{gx}:0,scale={W}:{H}:flags=lanczos,setsar=1,"
        f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)+{tremida}':y='ih/2-(ih/zoom/2)+{tremida}':s={W}x{H}:fps={FPS},"
        f"eq=saturation=1.12:contrast=1.04[game];"
        f"[c1]crop={cw}:{ch}:{cx}:{cy},scale={bp[0]}:{bp[1]},format=rgba[cp0];[cp0][2:v]alphamerge[cp];"
        f"[c2]crop={cw}:{ch}:{cx}:{cy},scale={bg[0]}:{bg[1]},format=rgba[cg0];[cg0][3:v]alphamerge[cgb];"
        f"[game][4:v]overlay=x={xb - borda}:y={yb - borda}:enable='not(between(t,{p0:.2f},{p1 + 0.6:.2f}))'[v1];"
        f"[v1][cp]overlay=x={xb}:y={yb}:enable='not(between(t,{p0:.2f},{p1 + 0.6:.2f}))'[v2];"
        f"[v2][5:v]overlay=x={xb - borda}:y={yb - borda}:enable='between(t,{p0:.2f},{p1 + 0.6:.2f})'[v3];"
        f"[v3][cgb]overlay=x={xb}:y={yb}:enable='between(t,{p0:.2f},{p1 + 0.6:.2f})'[base]"
    )
    run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp / "cut.mkv"),
         "-loop", "1", "-i", str(tmp / "mask_p.png"), "-loop", "1", "-i", str(tmp / "mask_p.png"),
         "-loop", "1", "-i", str(tmp / "mask_g.png"), "-loop", "1", "-i", str(tmp / "borda_p.png"),
         "-loop", "1", "-i", str(tmp / "borda_g.png"),
         "-filter_complex", filtro.replace("[2:v]alphamerge[cp]", "[1:v]alphamerge[cp]")
                                  .replace("[3:v]alphamerge[cgb]", "[3:v]alphamerge[cgb]"),
         "-map", "[base]", "-map", "0:a", "-t", f"{dur_out:.2f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-c:a", "pcm_s16le", str(tmp / "base.mkv")])
    return dur_out


# ---------------------------------------------------------------- 3. motion graphics (HyperFrames)
def grupos_legenda(palavras_out, max_pal=3):
    grupos, atual = [], []
    for w in palavras_out:
        if atual and (len(atual) >= max_pal or w["inicio"] - atual[-1]["fim"] > 0.4
                      or re.search(r"[.!?]$", atual[-1]["p"])):
            grupos.append(atual)
            atual = []
        atual.append(w)
    if atual:
        grupos.append(atual)
    return grupos


def eh_hype(txt, peso_min=1.5):
    t = sem_acento(txt)
    return any(r.search(t) for r, w in HYPE_RE if w >= peso_min)


def hype_por_palavra(grupo, todas, idx0):
    """Marca palavras que fazem parte de uma expressão de hype (inclui expressões de 2-3 palavras)."""
    marc = []
    for k in range(len(grupo)):
        i = idx0 + k
        janela = [todas[j]["p"] for j in range(max(0, i - 2), min(len(todas), i + 3))]
        alvo = sem_acento(re.sub(r"[^\w\s]", "", grupo[k]["p"]))
        ok = False
        for r, w in HYPE_RE:
            if w < 1.5:
                continue
            for m in r.finditer(sem_acento(re.sub(r"[^\w\s]", "", " ".join(janela)))):
                if alvo and alvo in m.group(0).split():
                    ok = True
        marc.append(ok)
    return marc


def emoji_de(txt):
    t = sem_acento(txt)
    for r, e in EMOJI_RE:
        if r.search(t):
            return e
    return None


def gerar_html(titulo, palavras_out, dur, marca, pasta: Path):
    grupos = grupos_legenda(palavras_out)
    els, anims = [], []
    # card de gancho
    els.append(f'<div id="hook"><span>{html.escape(titulo)}</span></div>')
    anims.append('tl.fromTo("#hook",{scale:0.3,opacity:0,rotation:-6},{scale:1,opacity:1,rotation:-2,duration:0.35,ease:"back.out(2.2)"},0.05);'
                 'tl.to("#hook",{scale:1.04,duration:0.12,yoyo:true,repeat:3},0.5);'
                 'tl.to("#hook",{y:-260,opacity:0,scale:0.6,duration:0.3,ease:"power2.in"},2.3);')
    usados_emoji = 0.0
    for gi, g in enumerate(grupos):
        g0 = g[0]["inicio"]
        prox = grupos[gi + 1][0]["inicio"] if gi + 1 < len(grupos) else dur
        g1 = min(g[-1]["fim"] + 1.0, prox)  # fica na tela até a próxima frase (máx. +1 s)
        if g0 < 2.4:  # não briga com o card de gancho
            g0 = max(g0, 2.45)
            if g0 >= g1:
                continue
        spans = []
        idx0 = sum(len(x) for x in grupos[:gi])
        marc = hype_por_palavra(g, palavras_out, idx0)
        for wi, w in enumerate(g):
            txt = re.sub(r"[.,;:]", "", w["p"]).lower()
            cls = "w hype" if marc[wi] else "w"
            spans.append(f'<span class="{cls}" id="w{gi}_{wi}">{html.escape(txt)}</span>')
            anims.append(f'tl.fromTo("#w{gi}_{wi}",{{scale:0.5,opacity:0,y:30}},'
                         f'{{scale:1,opacity:1,y:0,duration:0.14,ease:"back.out(3)"}},{max(g0, w["inicio"]):.2f});')
        els.append(f'<div class="cap" id="g{gi}">{" ".join(spans)}</div>')
        anims.append(f'tl.set("#g{gi}",{{opacity:1}},{g0:.2f});tl.set("#g{gi}",{{opacity:0}},{g1:.2f});')
        em = emoji_de(" ".join(w["p"] for w in g))
        if em and g0 - usados_emoji > 1.5:
            usados_emoji = g0
            lado = 1 if gi % 2 else -1
            els.append(f'<div class="emoji" id="e{gi}">{em}</div>')
            anims.append(f'tl.fromTo("#e{gi}",{{opacity:0,scale:0,rotation:{-30 * lado}}},'
                         f'{{opacity:1,scale:1.15,rotation:{12 * lado},duration:0.25,ease:"back.out(3)"}},{g0:.2f});'
                         f'tl.to("#e{gi}",{{y:-60,opacity:0,duration:0.35}},{min(g0 + 1.3, dur - 0.1):.2f});')
            els[-1] = els[-1].replace('class="emoji"', f'class="emoji" style="left:{540 + lado * 330 - 90}px"')
    anims.append(f'tl.fromTo("#bar",{{scaleX:0}},{{scaleX:1,duration:{dur:.2f},ease:"none"}},0);')
    doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
html,body{{margin:0;background:transparent}}
#root{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:transparent;font-family:'Open Sans',sans-serif}}
#hook{{position:absolute;left:70px;right:70px;top:820px;text-align:center;opacity:0}}
#hook span{{display:inline;font-weight:800;font-size:84px;line-height:1.25;color:#fff;background:{ROXO};
  padding:6px 22px;-webkit-box-decoration-break:clone;box-decoration-break:clone;border-radius:14px;
  box-shadow:0 10px 0 #2a0b46}}
.cap{{position:absolute;left:40px;right:40px;top:1240px;text-align:center;opacity:0}}
.w{{display:inline-block;font-weight:800;font-size:82px;color:#fff;margin:0 8px;opacity:0;
  text-shadow:0 0 2px #000,0 5px 0 #000,0 0 18px rgba(0,0,0,.7);-webkit-text-stroke:3px #000;paint-order:stroke fill}}
.w.hype{{color:{ROXO};font-size:100px}}
.emoji{{position:absolute;top:1040px;width:180px;font-size:150px;text-align:center;opacity:0;
  font-family:'Noto Color Emoji'}}
#bar{{position:absolute;left:0;top:0;width:{W}px;height:12px;background:{ROXO};transform-origin:0 50%}}
#marca{{position:absolute;right:34px;bottom:300px;font-weight:700;font-size:36px;color:rgba(255,255,255,.75);
  text-shadow:0 2px 6px #000}}
</style></head>
<body>
<div id="root" data-composition-id="root" data-width="{W}" data-height="{H}" data-start="0" data-duration="{dur:.2f}">
<div id="bar"></div>
{chr(10).join(els)}
<div id="marca">{html.escape(marca)}</div>
</div>
<script src="gsap.min.js"></script>
<script>
const tl = gsap.timeline({{paused:true}});
{chr(10).join(anims)}
window.__timelines = window.__timelines || {{}}; window.__timelines["root"] = tl;
</script>
</body></html>"""
    pasta.mkdir(parents=True, exist_ok=True)
    shutil.copy(MOTION / "node_modules" / "gsap" / "dist" / "gsap.min.js", pasta / "gsap.min.js")
    (pasta / "index.html").write_text(doc, encoding="utf-8")
    return grupos


def render_overlay(pasta: Path, saida: Path):
    run(["npx", "hyperframes", "render", str(pasta), "-o", str(saida), "--format", "mov", "-q", "standard",
         "-w", "4"], cwd=MOTION)


# ---------------------------------------------------------------- storyboard
def storyboard(corte, segs, palavras_out, grupos, pico_out, dur, video, cam, dest: Path):
    linhas = [f"# Storyboard — {corte['id']}: {corte.get('titulo', '')}", "",
              f"- Trecho original: {corte['inicio']:.1f}s → {corte['fim']:.1f}s ({corte['fim'] - corte['inicio']:.0f}s)",
              f"- Depois dos jump cuts: **{dur:.1f}s** ({len(segs)} cortes, {corte['fim'] - corte['inicio'] - dur:.1f}s de tempo morto removidos)",
              f"- Pico (zoom 1.32x + tremida + bolha da câmera cresce): **{pico_out:.1f}s**", "",
              "| Tempo | Visual | Texto na tela |", "|---|---|---|",
              f"| 0.0–2.4s | card de gancho roxo entra com pop | **{corte.get('titulo', '')}** |"]
    for g in grupos:
        txt = " ".join(w["p"] for w in g)
        extra = []
        if eh_hype(txt):
            extra.append("palavra roxa")
        if emoji_de(txt):
            extra.append(f"emoji {emoji_de(txt)}")
        if g[0]["inicio"] <= pico_out <= g[-1]["fim"] + 0.5:
            extra.append("**PICO**")
        linhas.append(f"| {g[0]['inicio']:.1f}s | {', '.join(extra) or '—'} | {txt} |")
    dest.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Corte no estilo DINÂMICO.")
    ap.add_argument("cortes_json")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--cam", required=True, help="x:y:largura:altura da câmera do streamer no vídeo original")
    ap.add_argument("--marca", default="@Cortez4d4")
    ap.add_argument("--storyboard", action="store_true", help="só gera o storyboard (sem renderizar)")
    a = ap.parse_args()
    cj = Path(a.cortes_json).resolve()
    dados = json.loads(cj.read_text(encoding="utf-8"))
    transc = json.loads((cj.parent / "transcricao.json").read_text(encoding="utf-8"))
    video = Path(dados["video"])
    cam = tuple(int(v) for v in a.cam.split(":"))
    src_w, src_h = map(int, run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height", "-of", "csv=p=0", str(video)]).stdout.strip().split(","))
    saida = RAIZ / "saida" / cj.parent.name / "dinamico"
    saida.mkdir(parents=True, exist_ok=True)
    for c in dados["cortes"]:
        if a.ids and c["id"] not in a.ids or not c.get("aprovado", True):
            continue
        ini, fim = c["inicio"], c["fim"]
        pal = [{"p": w["p"], "inicio": w["inicio"] - ini, "fim": w["fim"] - ini}
               for s in transc["segmentos"] for w in s["palavras"] if ini - 0.05 <= w["inicio"] and w["fim"] <= fim + 0.3]
        segs = segmentos_mantidos(video, c, pal)
        pal_out = []
        for w in pal:
            t0 = mapear(w["inicio"], segs)
            if t0 is not None:
                pal_out.append({"p": w["p"], "inicio": round(t0, 2), "fim": round(t0 + (w["fim"] - w["inicio"]), 2)})
        dur = sum(b - x for x, b in segs)
        pk = mapear(c.get("pico", ini) - ini, segs) or dur / 2
        print(f">> {c['id']}: {fim - ini:.0f}s -> {dur:.1f}s após jump cuts ({len(segs)} trechos), pico em {pk:.1f}s", flush=True)
        comp = MOTION / "comps" / f"{cj.parent.name}_{c['id']}"
        grupos = gerar_html(c.get("titulo", ""), pal_out, dur, a.marca, comp)
        storyboard(c, segs, pal_out, grupos, pk, dur, video, cam, saida / f"{c['id']}_storyboard.md")
        if a.storyboard:
            print(f"   storyboard -> {saida / (c['id'] + '_storyboard.md')}")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            print("   [1/3] base (jump cuts, zooms, bolha da câmera)...", flush=True)
            render_base(video, c, segs, cam, pk, tmp, src_w, src_h)
            print("   [2/3] motion graphics (HyperFrames)...", flush=True)
            render_overlay(comp, tmp / "overlay.mov")
            print("   [3/3] composição final...", flush=True)
            dest = saida / f"{c['id']}.mp4"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp / "base.mkv"), "-i", str(tmp / "overlay.mov"),
                 "-filter_complex", "[1:v]format=rgba[o];[0:v][o]overlay=0:0:shortest=1,format=yuv420p[v];"
                                    "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]",
                 "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                 "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dest)])
            print(f"   ok -> {dest}")


if __name__ == "__main__":
    main()
