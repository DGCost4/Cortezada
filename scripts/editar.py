#!/usr/bin/env python3
"""
Renderiza os cortes aprovados em formato vertical (1080x1920) prontos para
YouTube Shorts / TikTok / Reels.

Edição aplicada em cada corte:
  - Layout 9:16: gameplay em destaque no centro + fundo desfocado (ou tela cheia com --layout cheio)
  - Título-gancho grande no topo (campo "titulo" do cortes.json)
  - Legenda animada palavra por palavra (palavra atual em amarelo, com "pop")
  - Zoom (punch-in) no momento do pico
  - Barra de progresso no rodapé (segura a retenção)
  - Áudio normalizado em -14 LUFS (padrão YouTube/TikTok)
  - Marca d'água opcional do canal (--marca "@seucanal")

Uso:
  python3 scripts/editar.py trabalho/<nome>/cortes.json [--ids c01 c03] [--layout blur|cheio] [--marca @canal]
Saída: saida/<nome>/<id>.mp4 + saida/<nome>/<id>.txt (título, descrição, hashtags para revisar)
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "assets" / "fonts"
W, H = 1080, 1920
FG_H = 778            # altura do gameplay no layout "blur"
FG_Y = 520            # posição vertical do gameplay
FONTE = "Roboto Black"
TOPO_H = 760          # altura da câmera do streamer no layout "dividido"


def ts(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def quebrar_titulo(t: str, max_linha=18) -> str:
    palavras, linhas, atual = t.split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > max_linha and atual:
            linhas.append(atual)
            atual = p
        else:
            atual = (atual + " " + p).strip()
    if atual:
        linhas.append(atual)
    return r"\N".join(linhas[:3])


# Estilos de legenda. Cores ASS em &HAABBGGRR (alfa 00 = opaco).
ESTILOS = {
    # chamativo: CAIXA ALTA, palavra atual amarela com "pop"
    "impacto": dict(fonte="Roboto Black", tam=96, contorno=8, sombra=5, borda=1, caixa_cor="&H00000000",
                    destaque="&H0000F0FF", pop=True, caixa_alta=True, max_pal=3, max_car=16,
                    tit_fonte="Roboto Black", tit_tam=86, tit_contorno=7, minusc=False),
    # minimalista: frase curta, minúsculas, branco limpo com sombra suave (estilo TikTok)
    "minimal": dict(fonte="Open Sans Semibold", tam=60, contorno=0, sombra=3, borda=1, caixa_cor="&H00000000",
                    destaque=None, pop=False, caixa_alta=False, max_pal=6, max_car=30,
                    tit_fonte="Open Sans Bold", tit_tam=66, tit_contorno=0, minusc=True),
    # minimalista com a palavra falada em amarelo suave (sem animação)
    "minimal_destaque": dict(fonte="Open Sans Bold", tam=62, contorno=2, sombra=2, borda=1, caixa_cor="&H00000000",
                             destaque="&H0070E8FF", pop=False, caixa_alta=False, max_pal=5, max_car=26,
                             tit_fonte="Open Sans Bold", tit_tam=66, tit_contorno=2, minusc=True),
    # texto branco em caixinha preta translúcida (estilo legenda de TV / Reels)
    "caixa": dict(fonte="Roboto Medium", tam=54, contorno=12, sombra=0, borda=3, caixa_cor="&H50000000",
                  destaque=None, pop=False, caixa_alta=False, max_pal=6, max_car=30,
                  tit_fonte="Roboto Medium", tit_tam=60, tit_contorno=14, minusc=False),
}


def limpar(t: str, e: dict) -> str:
    t = esc(t)
    if e["minusc"]:
        t = re.sub(r"[.,;:]", "", t).lower()
    return t.upper() if e["caixa_alta"] else t


def gerar_ass(corte, palavras, marca, layout, estilo="impacto") -> str:
    e = ESTILOS[estilo]
    dur = corte["fim"] - corte["inicio"]
    leg_y = {"blur": FG_Y + FG_H + 230, "dividido": TOPO_H}.get(layout, 1350)
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Titulo,{e['tit_fonte']},{e['tit_tam']},&H00FFFFFF,&H00FFFFFF,{e['caixa_cor']},&H96000000,0,0,0,0,100,100,1,0,{e['borda']},{e['tit_contorno']},{max(2, e['sombra'])},8,60,60,150,1
Style: Leg,{e['fonte']},{e['tam']},&H00FFFFFF,&H00FFFFFF,{e['caixa_cor']},&H90000000,0,0,0,0,100,100,1,0,{e['borda']},{e['contorno']},{e['sombra']},5,50,50,0,1
Style: Marca,{e['fonte']},40,&H60FFFFFF,&H60FFFFFF,&H60000000,&H00000000,0,0,0,0,100,100,1,0,1,2,0,2,40,40,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    titulo = quebrar_titulo(esc(corte.get("titulo", "")), 18 if e["tit_tam"] > 80 else 22)
    if titulo:
        # no layout dividido o título some após 3 s (não cobre o rosto do streamer)
        t_fim = min(dur, 3.0) if layout == "dividido" else dur
        pos_t = r"{\an8\pos(" + f"{W // 2},{TOPO_H + 110}" + ")}" if layout == "dividido" else ""
        anim = (r"{\fscx60\fscy60\t(0,180,\fscx108\fscy108)\t(180,300,\fscx100\fscy100)}" if e["pop"]
                else r"{\fad(250,250)}")
        ev.append(f"Dialogue: 2,{ts(0)},{ts(t_fim)},Titulo,,0,0,0,,{pos_t}{anim}" + titulo)
    if marca:
        pos = r"{\an9\pos(" + f"{W - 30},{TOPO_H + 30}" + ")}" if layout == "dividido" else ""
        ev.append(f"Dialogue: 1,{ts(0)},{ts(dur)},Marca,,0,0,0,,{pos}{esc(marca)}")

    # agrupa palavras em blocos curtos (pausa > 0,7 s quebra o bloco)
    blocos, atual = [], []
    for w in palavras:
        txt = w["p"].strip()
        if not txt:
            continue
        if atual and (len(atual) >= e["max_pal"] or sum(len(x["p"]) + 1 for x in atual) + len(txt) > e["max_car"]
                      or w["inicio"] - atual[-1]["fim"] > 0.7):
            blocos.append(atual)
            atual = []
        atual.append(w)
    if atual:
        blocos.append(atual)

    pos_leg = r"{\an5\pos(" + f"{W // 2},{leg_y}" + ")}"
    for bi, bl in enumerate(blocos):
        fim_bloco = bl[-1]["fim"]
        if bi + 1 < len(blocos):
            fim_bloco = min(max(fim_bloco, bl[-1]["fim"] + 0.3), blocos[bi + 1][0]["inicio"])
        if not e["destaque"]:  # frase inteira de uma vez, sem destaque
            if fim_bloco > bl[0]["inicio"]:
                ev.append(f"Dialogue: 3,{ts(bl[0]['inicio'])},{ts(fim_bloco)},Leg,,0,0,0,,{pos_leg}"
                          + " ".join(limpar(x["p"], e) for x in bl))
            continue
        for i, w in enumerate(bl):
            ini = w["inicio"]
            fim = bl[i + 1]["inicio"] if i + 1 < len(bl) else fim_bloco
            if fim <= ini:
                continue
            partes = []
            for j, x in enumerate(bl):
                t = limpar(x["p"], e)
                if j == i and e["pop"]:
                    partes.append(r"{\1c" + e["destaque"] + r"&\fscx112\fscy112\t(0,90,\fscx122\fscy122)\t(90,170,\fscx112\fscy112)}"
                                  + t + r"{\1c&H00FFFFFF&\fscx100\fscy100}")
                elif j == i:
                    partes.append(r"{\1c" + e["destaque"] + "&}" + t + r"{\1c&H00FFFFFF&}")
                else:
                    partes.append(t)
            ev.append(f"Dialogue: 3,{ts(ini)},{ts(fim)},Leg,,0,0,0,,{pos_leg}" + " ".join(partes))
    return cab + "\n".join(ev) + "\n"


def palavras_do_corte(transc, ini, fim):
    out = []
    for s in transc["segmentos"]:
        if s["fim"] < ini or s["inicio"] > fim:
            continue
        for w in s["palavras"]:
            if w["inicio"] >= ini - 0.05 and w["fim"] <= fim + 0.3:
                out.append({"p": w["p"], "inicio": w["inicio"] - ini, "fim": min(w["fim"], fim) - ini})
    return out


def render(video: Path, corte, transc, destino: Path, layout: str, marca: str, fps: int, cam=None,
           estilo: str = "impacto"):
    ini, fim = corte["inicio"], corte["fim"]
    dur = fim - ini
    pk = max(0.0, corte.get("pico", ini + dur / 2) - ini)
    z0, z1 = max(0.0, pk - 0.3), min(dur, pk + 2.2)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "leg.ass").write_text(gerar_ass(corte, palavras_do_corte(transc, ini, fim), marca, layout, estilo),
                                     encoding="utf-8")
        zoom = (f"zoompan=z='if(between(it,{z0:.2f},{z1:.2f}),min(zoom+0.025,1.18),max(zoom-0.025,1))'"
                f":d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'")
        if layout == "dividido":
            # streamer em cima (recorte da câmera), gameplay embaixo (centro do jogo, sem a câmera)
            cx, cy, cw, ch = cam
            base_h = H - TOPO_H
            ch2 = min(ch, int(cw * TOPO_H / W))           # ajusta proporção da câmera para 1080x760
            cy2 = cy  # corta só embaixo (preserva o topo da cabeça)
            filtro = (f"[0:v]fps={fps},split[a][b];"
                      f"[a]crop={cw}:{ch2}:{cx}:{cy2},scale={W}:{TOPO_H}:flags=lanczos,"
                      f"unsharp=5:5:0.8,setsar=1[topo];"
                      f"[b]crop='ih*{W}/{base_h}':ih:'(iw-ih*{W}/{base_h})/2':0,scale={W}:{base_h}:flags=lanczos,"
                      f"setsar=1,{zoom}:s={W}x{base_h}:fps={fps}[jogo];"
                      f"[topo][jogo]vstack,drawbox=x=0:y={TOPO_H - 3}:w={W}:h=6:color=black@0.9:t=fill[base];")
        elif layout == "cheio":
            fg = (f"[0:v]fps={fps},crop='min(iw,ih*9/16)':ih,scale={W}:{H}:flags=lanczos,setsar=1,"
                  f"{zoom}:s={W}x{H}:fps={fps}[base]")
            filtro = fg + ";"
        else:
            filtro = (f"[0:v]fps={fps},split[a][b];"
                      f"[a]scale=-2:{H // 4},crop={W // 4}:{H // 4},boxblur=12:3,scale={W}:{H},eq=brightness=-0.12[bg];"
                      f"[b]crop='iw*0.78':ih,scale={W}:{FG_H}:flags=lanczos,setsar=1,{zoom}:s={W}x{FG_H}:fps={fps}[fg];"
                      f"[bg][fg]overlay=0:{FG_Y}[base];")
        filtro += (f"[base]drawbox=x=0:y={H - 14}:w='iw*t/{dur:.3f}':h=14:color=0xFFD400@0.95:t=fill,"
                   f"ass=leg.ass:fontsdir={FONTES},format=yuv420p[v];"
                   f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
        cmd = ["ffmpeg", "-y", "-v", "error", "-stats", "-ss", f"{ini:.2f}", "-t", f"{dur:.2f}", "-i", str(video),
               "-filter_complex", filtro, "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high",
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destino)]
        subprocess.run(cmd, check=True, cwd=tmp)


def metadados(corte, nome_live, destino: Path):
    tags = "#shorts #gta6 #gta #games #gameplay #cortes #lives #viral"
    destino.write_text(
        f"TÍTULO (revisar, máx. 100 caracteres):\n{corte.get('titulo', '').capitalize()} 😱 #shorts\n\n"
        f"DESCRIÇÃO:\n{corte.get('titulo', '').capitalize()}\n\n"
        f"Corte da live: {nome_live}\n"
        f"Créditos ao streamer original: [@CANAL_DO_STREAMER]\n"
        f"Conteúdo editado com auxílio de IA (legendas automáticas).\n\n{tags}\n\n"
        f"FALA DO TRECHO:\n{corte.get('texto', '')}\n\n"
        f"Motivos da seleção: {', '.join(corte.get('motivos', []))} | score {corte.get('score')}\n",
        encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Renderiza cortes verticais editados.")
    ap.add_argument("cortes_json")
    ap.add_argument("--ids", nargs="*", help="só esses cortes (ex.: c01 c04)")
    ap.add_argument("--layout", choices=["blur", "cheio", "dividido"], default="blur")
    ap.add_argument("--estilo", choices=list(ESTILOS), default="impacto", help="estilo da legenda")
    ap.add_argument("--sufixo", default="", help="sufixo no nome do arquivo (para comparar versões)")
    ap.add_argument("--cam", help="layout dividido: posição da câmera do streamer no vídeo original, x:y:largura:altura (px)")
    ap.add_argument("--marca", default="", help='texto da marca d\'água, ex.: "@MeuCanalDeCortes"')
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()

    cj = Path(a.cortes_json).resolve()
    dados = json.loads(cj.read_text(encoding="utf-8"))
    transc = json.loads((cj.parent / "transcricao.json").read_text(encoding="utf-8"))
    video = Path(dados["video"])
    if not video.exists():
        sys.exit(f"Vídeo original não encontrado: {video}")
    pasta = RAIZ / "saida" / cj.parent.name
    pasta.mkdir(parents=True, exist_ok=True)

    cortes = [c for c in dados["cortes"] if c.get("aprovado", True) and (not a.ids or c["id"] in a.ids)]
    for c in cortes:
        dest = pasta / f"{c['id']}{a.sufixo}.mp4"
        print(f"\n>> Renderizando {c['id']} ({c['fim'] - c['inicio']:.0f}s): {c.get('titulo', '')}", flush=True)
        cam = tuple(int(v) for v in a.cam.split(":")) if a.cam else None
        if a.layout == "dividido" and not cam:
            sys.exit("Layout dividido precisa de --cam x:y:largura:altura")
        render(video, c, transc, dest, a.layout, a.marca, a.fps, cam, a.estilo)
        metadados(c, cj.parent.name, pasta / f"{c['id']}.txt")
        print(f"   ok -> {dest}")
    print(f"\nPronto: {len(cortes)} cortes em {pasta}")


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("Instale o ffmpeg primeiro.")
    main()
