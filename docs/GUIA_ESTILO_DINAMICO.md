# Guia de estilo DINÂMICO — Cortizadas

Objetivo: **se diferenciar** dos milhares de cortes "tela dividida + legenda" iguais.
Inspirado no método "edição com Claude" (tutorial de referência): ferramentas → guia de estilo → **storyboard** → render.

## Ferramentas (todas grátis, já instaladas no ambiente)
| Ferramenta | Função aqui |
|---|---|
| **FFmpeg** | jump cuts, recorte 9:16, zooms, tremida, bolha da câmera, mixagem |
| **Whisper** (faster-whisper) | transcrição palavra por palavra → legendas e detecção de hype |
| **HyperFrames** (HeyGen, open source) | motion graphics em HTML + GSAP: card de gancho, legendas animadas, emojis, barra de progresso — renderizado com fundo transparente |
| **yt-dlp** | baixar referências para estudo. Obs.: o YouTube bloqueia downloads vindos do servidor ("confirm you're not a bot") → mandar vídeos pelo Google Drive |

Pastas (equivalentes às do tutorial): `entrada/` = vídeos brutos · `referencias/` = referências · `saida/` = exportação.

## Regras visuais
1. **Tela cheia de gameplay** (9:16, centro do jogo). Nada de tela dividida.
2. **Jump cuts**: pausas > 0,55 s sem fala e sem som alto são removidas → ritmo acelerado (um corte de 26 s vira ~20 s).
3. **Zoom alternado** a cada jump cut (1.00 → 1.12 → 1.05 → 1.18): cada corte "pula" e prende o olho.
4. **Pico**: punch-in 1.32x + tremida de 0,5 s + **bolha da câmera cresce** (440 → 760 px, a partir do canto) para mostrar a reação.
5. **Câmera do streamer**: bolha com cantos arredondados e **borda roxa #B44CFF**, no **canto superior esquerdo**.
6. **Card de gancho** (0–2,4 s): título em bloco roxo, entra com pop e sai subindo.
7. **Legendas**: 1–3 palavras, minúsculas, Open Sans ExtraBold branca com contorno preto, centro da tela;
   palavras/expressões de hype em **roxo e maiores**; cada palavra entra com pop.
8. **Emojis** contextuais (😱 💰 😂 🚓 💥 💀 🏃 🤯 🚗 🥊), no máximo 1 a cada 1,5 s, alternando lados.
9. **Barra de progresso** roxa no topo. Marca @Cortez4d4 discreta.
10. Áudio só da live, normalizado em -14 LUFS (sem música de terceiros).

## Fluxo
1. `python3 scripts/analisar.py entrada/<live>.mp4` → candidatos
2. Curadoria pelo Claude (ver CLAUDE.md)
3. `python3 scripts/dinamico.py trabalho/<live>/cortes.json --cam X:Y:L:A --storyboard` → **storyboard para aprovação**
4. Usuário aprova/ajusta → `python3 scripts/dinamico.py ... --ids c01 c02` → `saida/<live>/dinamico/`
