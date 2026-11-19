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


def gerar_ass(corte, palavras, marca, layout) -> str:
    dur = corte["fim"] - corte["inicio"]
    leg_y = FG_Y + FG_H + 230 if layout == "blur" else 1350
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Titulo,{FONTE},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,7,4,8,60,60,150,1
Style: Leg,{FONTE},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,8,5,5,50,50,0,1
Style: Marca,{FONTE},42,&H60FFFFFF,&H60FFFFFF,&H60000000,&H00000000,0,0,0,0,100,100,1,0,1,3,0,2,40,40,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    titulo = quebrar_titulo(esc(corte.get("titulo", "")))
    if titulo:
        # entra com "pop" e fica o vídeo inteiro
        ev.append(f"Dialogue: 2,{ts(0)},{ts(dur)},Titulo,,0,0,0,,"
                  r"{\fscx60\fscy60\t(0,180,\fscx108\fscy108)\t(180,300,\fscx100\fscy100)}"
                  r"{\1c&H00FFFFFF&}" + titulo)
    if marca:
        ev.append(f"Dialogue: 1,{ts(0)},{ts(dur)},Marca,,0,0,0,,{esc(marca)}")

    # agrupa palavras em blocos de até 3 palavras / ~16 caracteres
    blocos, atual = [], []
    for w in palavras:
        txt = w["p"].strip()
        if not txt:
            continue
        if atual and (len(atual) >= 3 or sum(len(x["p"]) for x in atual) + len(txt) > 16
                      or w["inicio"] - atual[-1]["fim"] > 0.7):
            blocos.append(atual)
            atual = []
        atual.append(w)
    if atual:
        blocos.append(atual)

    for bi, bl in enumerate(blocos):
        fim_bloco = bl[-1]["fim"]
        if bi + 1 < len(blocos):
            fim_bloco = min(max(fim_bloco, bl[-1]["fim"] + 0.3), blocos[bi + 1][0]["inicio"])
        for i, w in enumerate(bl):
            ini = w["inicio"]
            fim = bl[i + 1]["inicio"] if i + 1 < len(bl) else fim_bloco
            if fim <= ini:
                continue
            partes = []
            for j, x in enumerate(bl):
                t = esc(x["p"].upper())
                if j == i:
                    partes.append(r"{\1c&H0000F0FF&\fscx112\fscy112\t(0,90,\fscx122\fscy122)\t(90,170,\fscx112\fscy112)}"
                                  + t + r"{\1c&H00FFFFFF&\fscx100\fscy100}")
                else:
                    partes.append(t)
            ev.append(f"Dialogue: 3,{ts(ini)},{ts(fim)},Leg,,0,0,0,,"
                      + r"{\an5\pos(" + f"{W // 2},{leg_y}" + ")}" + " ".join(partes))
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


def render(video: Path, corte, transc, destino: Path, layout: str, marca: str, fps: int):
    ini, fim = corte["inicio"], corte["fim"]
    dur = fim - ini
    pk = max(0.0, corte.get("pico", ini + dur / 2) - ini)
    z0, z1 = max(0.0, pk - 0.3), min(dur, pk + 2.2)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "leg.ass").write_text(gerar_ass(corte, palavras_do_corte(transc, ini, fim), marca, layout),
                                     encoding="utf-8")
        zoom = (f"zoompan=z='if(between(it,{z0:.2f},{z1:.2f}),min(zoom+0.025,1.18),max(zoom-0.025,1))'"
                f":d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'")
        if layout == "cheio":
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
    ap.add_argument("--layout", choices=["blur", "cheio"], default="blur")
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
        dest = pasta / f"{c['id']}.mp4"
        print(f"\n>> Renderizando {c['id']} ({c['fim'] - c['inicio']:.0f}s): {c.get('titulo', '')}", flush=True)
        render(video, c, transc, dest, a.layout, a.marca, a.fps)
        metadados(c, cj.parent.name, pasta / f"{c['id']}.txt")
        print(f"   ok -> {dest}")
    print(f"\nPronto: {len(cortes)} cortes em {pasta}")


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("Instale o ffmpeg primeiro.")
    main()
