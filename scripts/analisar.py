#!/usr/bin/env python3
"""
Analisa uma live (vídeo) e encontra os momentos com maior potencial de viralizar.

Sinais combinados (linha do tempo em blocos de 0,5 s):
  1. Picos de volume  -> gritos, explosões, risadas altas (comparado com o "normal" da live)
  2. Palavras de hype  -> "caralho", "meu deus", "não acredito", "kkkk", "olha isso"...
  3. Fala acelerada    -> streamer reagindo rápido / narrando ação
Depois escolhe os melhores picos, monta janelas de 15-59 s alinhadas com o
início/fim das frases (o corte precisa fazer sentido sozinho) e salva em JSON.

Uso:
  python3 scripts/analisar.py entrada/live.mp4 [--modelo small] [--max-cortes 10]
Saída:
  trabalho/<nome>/transcricao.json   (cache: não transcreve de novo)
  trabalho/<nome>/cortes.json        (lista de cortes sugeridos, editável à mão)
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
BLOCO = 0.5  # segundos por bloco de análise
SR = 16000

# Palavras/expressões de hype em PT-BR (peso). Comparação sem acento e em minúsculas.
HYPE = {
    r"\bcaralh\w*": 3, r"\bporra\b": 2.5, r"\bputa que pariu\b": 3.5, r"\bpqp\b": 3,
    r"\bmeu deus\b": 3, r"\bnao acredito\b": 3, r"\bque isso\b": 2.5, r"\bolha isso\b": 2.5,
    r"\bolha\b": 1, r"\bnossa\b": 1.5, r"\bmano\b": 1, r"\bvei\b|\bvelho\b": 1,
    r"\bk{3,}\b|\b(ha){2,}\b|\bkk+\b": 3, r"\brs+\b": 1,
    r"\bmorri\b|\bmorreu\b|\bmataram\b|\bmatei\b": 2, r"\bexplod\w*": 2,
    r"\bcorre+\b|\bfoge\b|\bsocorro\b": 2, r"\bnao+\b": 0.5, r"\bvai+\b": 0.7,
    r"\bclip(a|ou)?\b|\bcorta\b|\bmanda (pro|pra) corte\b": 4, r"\bsurreal\b|\binsano\b|\bbizarro\b": 2.5,
    r"\bque jogada\b|\bque bala\b|\bfoi lindo\b|\blendari\w*": 3, r"\brecorde\b|\bprimeira vez\b": 2,
    r"\bgta\b|\bpolicia\b|\bfuga\b|\bperseguicao\b": 1, r"\bbug\w*\b|\bglitch\b": 2,
    r"\bdesgraca\b|\bfdp\b|\bfilho da puta\b": 2.5, r"\bsimplesmente\b": 1, r"\bgente\b": 0.7,
}
HYPE_RE = [(re.compile(p), w) for p, w in HYPE.items()]


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def duracao(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(video)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def extrair_audio(video: Path, wav: Path):
    if wav.exists():
        return
    print("[1/4] Extraindo áudio...", flush=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(SR),
                    "-c:a", "pcm_s16le", str(wav)], check=True)


def ler_wav(wav: Path) -> np.ndarray:
    data = np.fromfile(wav, dtype=np.int16, offset=44).astype(np.float32) / 32768.0
    return data


def energia_db(audio: np.ndarray, nblocos: int) -> np.ndarray:
    n = int(BLOCO * SR)
    audio = audio[: nblocos * n]
    if len(audio) < nblocos * n:
        audio = np.pad(audio, (0, nblocos * n - len(audio)))
    rms = np.sqrt(np.mean(audio.reshape(nblocos, n) ** 2, axis=1) + 1e-10)
    return 20 * np.log10(rms)


def media_movel(x: np.ndarray, janela: int) -> np.ndarray:
    if janela <= 1:
        return x
    k = np.ones(janela) / janela
    return np.convolve(x, k, mode="same")


def mediana_movel(x: np.ndarray, janela: int) -> np.ndarray:
    # mediana aproximada por sub-amostragem (rápido para lives longas)
    passo = max(1, janela // 8)
    idx = np.arange(0, len(x), passo)
    meds = np.array([np.median(x[max(0, i - janela // 2): i + janela // 2 + 1]) for i in idx])
    return np.interp(np.arange(len(x)), idx, meds)


def zrobusto(x: np.ndarray) -> np.ndarray:
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826 + 1e-6
    return (x - med) / mad


def transcrever(wav: Path, cache: Path, modelo: str, idioma: str):
    if cache.exists():
        print("[2/4] Transcrição já existe (cache), reaproveitando.", flush=True)
        return json.loads(cache.read_text(encoding="utf-8"))
    print(f"[2/4] Transcrevendo com Whisper '{modelo}' (pode demorar em lives longas)...", flush=True)
    from faster_whisper import WhisperModel
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, info = m.transcribe(ler_wav(wav), language=idioma, word_timestamps=True, vad_filter=True,
                              condition_on_previous_text=False)
    resultado = {"idioma": info.language, "segmentos": []}
    for s in segs:
        resultado["segmentos"].append({
            "inicio": round(s.start, 2), "fim": round(s.end, 2), "texto": s.text.strip(),
            "palavras": [{"inicio": round(w.start, 2), "fim": round(w.end, 2), "p": w.word.strip()}
                         for w in (s.words or [])],
        })
        print(f"   {s.start:8.1f}s  {s.text.strip()[:90]}", flush=True)
    cache.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    return resultado


def sinais_texto(transc, nblocos: int):
    hype = np.zeros(nblocos)
    fala = np.zeros(nblocos)
    for seg in transc["segmentos"]:
        texto = sem_acento(seg["texto"])
        b0, b1 = int(seg["inicio"] / BLOCO), max(int(seg["inicio"] / BLOCO) + 1, int(seg["fim"] / BLOCO))
        peso = sum(w * len(r.findall(texto)) for r, w in HYPE_RE)
        peso += 0.8 * seg["texto"].count("!") + 0.5 * seg["texto"].count("?")
        if peso:
            hype[b0:b1] += peso / max(1, (b1 - b0) ** 0.5)
        for w in seg["palavras"]:
            b = int(w["inicio"] / BLOCO)
            if b < nblocos:
                fala[b] += 1
    return hype, fala


def montar_cortes(score, transc, dur, max_cortes, min_s, max_s, pre, pos):
    segs = transc["segmentos"]
    # usa o tempo real da 1ª/última palavra (o Whisper às vezes inclui silêncio no segmento)
    inicios = np.array([s["palavras"][0]["inicio"] if s["palavras"] else s["inicio"] for s in segs])
    fins = np.array([s["palavras"][-1]["fim"] if s["palavras"] else s["fim"] for s in segs])
    tw = np.array([(w["inicio"], w["fim"]) for s in segs for w in s["palavras"]]).reshape(-1, 2)
    usados = np.zeros(len(score), dtype=bool)
    cortes = []
    ordem = np.argsort(-score)
    for b in ordem:
        if len(cortes) >= max_cortes or score[b] <= 0:
            break
        if usados[b]:
            continue
        pico = b * BLOCO
        ini, fim = max(0.0, pico - pre), min(dur, pico + pos)
        # alinha com começo/fim de frases para o corte fazer sentido sozinho
        if len(inicios):
            cand = inicios[(inicios <= ini + 1.0) & (inicios >= ini - 8)]
            if len(cand):
                ini = float(cand.min()) if pico - cand.min() <= max_s - 5 else float(cand.max())
            cand = fins[(fins >= fim - 1.0) & (fins <= fim + 8)]
            if len(cand):
                fim = float(cand.min())
        # corta "tempo morto" no começo e no fim (mata a retenção)
        if len(tw):
            dentro = tw[(tw[:, 0] >= ini) & (tw[:, 1] <= fim)]
            if len(dentro):
                if dentro[0, 0] - ini > 1.5 and dentro[0, 0] < pico:
                    ini = float(dentro[0, 0])
                if fim - dentro[-1, 1] > 2.5 and dentro[-1, 1] > pico:
                    fim = float(dentro[-1, 1]) + 1.0
        ini = max(0.0, ini - 0.3)
        fim = min(dur, fim + 0.4)
        if fim - ini > max_s:
            fim = ini + max_s
        if fim - ini < min_s:
            falta = min_s - (fim - ini)
            ini, fim = max(0.0, ini - falta / 2), min(dur, fim + falta / 2)
        bi, bf = int(ini / BLOCO), int(fim / BLOCO) + 1
        if usados[bi:bf].mean() > 0.2:
            continue
        usados[max(0, bi - 20):bf + 20] = True  # evita cortes colados um no outro
        texto = " ".join(s["texto"] for s in segs if s["fim"] > ini and s["inicio"] < fim)
        cortes.append({"inicio": round(ini, 2), "fim": round(fim, 2), "pico": round(pico, 2),
                       "score": round(float(score[b]), 2), "texto": texto})
    cortes.sort(key=lambda c: -c["score"])
    for i, c in enumerate(cortes, 1):
        c["id"] = f"c{i:02d}"
    return cortes


def motivos(c, z_audio, hype, fala_z):
    b0, b1 = int(c["inicio"] / BLOCO), int(c["fim"] / BLOCO) + 1
    m = []
    if z_audio[b0:b1].max() > 3:
        m.append("pico de volume (grito/explosão/risada)")
    if hype[b0:b1].sum() > 3:
        m.append("palavras de hype")
    if fala_z[b0:b1].max() > 2:
        m.append("fala acelerada / reação")
    return m or ["destaque geral"]


def titulo_sugerido(texto: str) -> str:
    frases = [f.strip() for f in re.split(r"[.!?]", texto) if len(f.strip()) > 8]
    if not frases:
        return "VOCÊ NÃO VAI ACREDITAR NISSO"
    melhor = max(frases, key=lambda f: sum(w for r, w in HYPE_RE if r.search(sem_acento(f))) + 0.01 * len(f))
    t, out = melhor.upper().strip(" ,"), ""
    for p in t.split():  # título curto (até ~40 caracteres), cortado em palavra inteira
        if len(out) + len(p) + 1 > 40:
            break
        out = (out + " " + p).strip()
    return out.rstrip(",;:") or t[:40]


def main():
    ap = argparse.ArgumentParser(description="Encontra os momentos virais de uma live.")
    ap.add_argument("video")
    ap.add_argument("--modelo", default="small", help="tiny/base/small/medium/large-v3 (maior = melhor e mais lento)")
    ap.add_argument("--idioma", default="pt")
    ap.add_argument("--max-cortes", type=int, default=0, help="0 = automático (~1 a cada 8 min)")
    ap.add_argument("--min", type=float, default=15, help="duração mínima do corte (s)")
    ap.add_argument("--max", type=float, default=58, help="duração máxima do corte (s) — Shorts < 60 s")
    ap.add_argument("--antes", type=float, default=20, help="segundos de contexto antes do pico")
    ap.add_argument("--depois", type=float, default=12, help="segundos depois do pico (reação)")
    a = ap.parse_args()

    video = Path(a.video).resolve()
    if not video.exists():
        sys.exit(f"Vídeo não encontrado: {video}")
    pasta = RAIZ / "trabalho" / video.stem
    pasta.mkdir(parents=True, exist_ok=True)

    dur = duracao(video)
    nblocos = int(dur / BLOCO) + 1
    wav = pasta / "audio.wav"
    extrair_audio(video, wav)
    transc = transcrever(wav, pasta / "transcricao.json", a.modelo, a.idioma)

    print("[3/4] Calculando picos...", flush=True)
    db = energia_db(ler_wav(wav), nblocos)
    base = mediana_movel(db, int(90 / BLOCO))                   # "normal" dos últimos ~90 s
    z_audio = np.clip(zrobusto(media_movel(db - base, 3)), 0, 10)
    hype, fala = sinais_texto(transc, nblocos)
    fala_z = np.clip(zrobusto(media_movel(fala, int(4 / BLOCO))), 0, 8)
    hype_s = media_movel(hype, int(6 / BLOCO))
    hype_n = hype_s / (np.percentile(hype_s[hype_s > 0], 95) + 1e-6) * 4 if (hype_s > 0).any() else hype_s
    score = media_movel(0.5 * z_audio + 0.35 * np.clip(hype_n, 0, 8) + 0.15 * fala_z, int(4 / BLOCO))
    score[: int(30 / BLOCO)] *= 0.3  # começo da live costuma ser "tela de espera"

    n = a.max_cortes or max(3, min(30, int(dur / 480)))
    cortes = montar_cortes(score, transc, dur, n, a.min, a.max, a.antes, a.depois)
    for c in cortes:
        c["motivos"] = motivos(c, z_audio, hype, fala_z)
        c["titulo"] = titulo_sugerido(c["texto"])
        c["aprovado"] = True

    saida = {"video": str(video), "duracao": round(dur, 1), "cortes": cortes}
    (pasta / "cortes.json").write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    # curva de score para debug/gráfico
    np.save(pasta / "score.npy", score.astype(np.float32))

    print(f"[4/4] {len(cortes)} cortes sugeridos -> {pasta / 'cortes.json'}\n")
    for c in cortes:
        mm = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"
        print(f"  {c['id']}  {mm(c['inicio'])} -> {mm(c['fim'])}  ({c['fim'] - c['inicio']:.0f}s)  "
              f"score {c['score']:.1f}  [{', '.join(c['motivos'])}]")
        print(f"       \"{c['texto'][:110]}\"")


if __name__ == "__main__":
    main()
