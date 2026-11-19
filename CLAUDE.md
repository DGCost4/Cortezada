# Canal Dark de Cortes de Lives (GTA 6 e jogos em geral)

**Idioma: responda SEMPRE em português do Brasil.**

## O que este projeto faz
O usuário manda lives de jogos (vídeo, geralmente compactado em .zip/.rar/.7z).
O Claude analisa, encontra os momentos com potencial viral, edita em formato vertical
e entrega cortes prontos para YouTube Shorts / TikTok / Reels, com título e descrição.

## Fluxo de trabalho (sempre nesta ordem)
1. **Receber** o arquivo -> colocar em `entrada/` (ou baixar do Google Drive, pasta "Cortes Lives/01 - Lives brutas").
2. **Analisar**: `python3 scripts/analisar.py entrada/<video>` (modelo `small` por padrão; `base` se a live for muito longa e precisar de rapidez).
   Gera `trabalho/<nome>/transcricao.json` (cache) e `trabalho/<nome>/cortes.json`.
3. **Curadoria (obrigatória, feita pelo Claude)**: ler `cortes.json` + a transcrição e, para cada corte:
   - checar se ele se sustenta SOZINHO (quem nunca viu a live entende?) — senão ajustar `inicio`/`fim` ou marcar `"aprovado": false`;
   - garantir que os **primeiros 2 s já têm ação/fala forte** (gancho); se não, mover o `inicio`;
   - terminar logo após a reação/punchline (não deixar "rabo" morto);
   - reescrever `titulo` (texto que aparece no topo do vídeo): curto (≤ 40 caracteres), em CAIXA ALTA, curiosidade/emoção, sem spoiler do final. Ex.: "ELE NÃO ESPERAVA ISSO...", "A POLÍCIA FICOU SEM ENTENDER".
   - corrigir palavras erradas da transcrição que vão aparecer na legenda.
   - procurar também momentos que o algoritmo não pegou (piada, plot twist, bug engraçado, rage) e adicionar.
4. **Renderizar**: `python3 scripts/editar.py trabalho/<nome>/cortes.json --marca "@CANAL"` (layout `blur` padrão; `--layout cheio` para gameplay em tela cheia).
5. **Revisar** frames do vídeo final (ffmpeg -ss X -frames:v 1) antes de entregar.
6. **Metadados**: reescrever `saida/<nome>/<id>.txt` com título de publicação (≤ 70 caracteres + #shorts), descrição com crédito ao streamer e 3–5 hashtags.
7. **Salvar na nuvem**: cortes prontos -> Google Drive "Cortes Lives/03 - Cortes prontos/<nome da live>"; código -> commit + push no GitHub.
8. **Publicar**: YouTube via `scripts/upload_youtube.py` (no PC do usuário) ou manual; TikTok manual (app/TikTok Studio).

Atalho para tudo de uma vez: `bash scripts/processar.sh entrada/live.zip --marca "@CANAL"`.

## Critérios de viralização (framework CLIP)
- **C – Cortar no momento**: o score do algoritmo é uma *dica*, não um veredito. ~70% dos cortes automáticos precisam de ajuste humano.
- **L – Layout vertical**: 9:16, assunto dentro da zona segura (nada importante nos 15% de cima/baixo cobertos pela interface).
- **I – Inscrever legendas**: palavra por palavra, 1–2 linhas, revisadas (muita gente assiste sem som).
- **P – Polir e publicar limpo**: sem marca d'água de outra plataforma (o algoritmo pune), declarar edição com IA quando aplicável.
- Melhores momentos: reações exageradas, fails, clutch/jogada absurda, bugs engraçados, perseguição policial, rage, piada do streamer, interação com chat/doação.
- Duração ideal: 20–45 s (máx. 59 s para Shorts). Loop: final que conecta com o início ajuda o replay.
- Nunca inventar métricas nem prometer viralização.

## Direitos autorais (importante)
Cortes de lives de terceiros só com **autorização do streamer** (muitos têm programa oficial de cortes). Dar crédito sempre.
O YouTube pode negar monetização por "conteúdo reutilizado" se não houver transformação: título-gancho, legendas, edição, contexto.

## Estrutura
- `scripts/` código | `assets/fonts/` fonte Roboto Black (Apache 2.0)
- `entrada/`, `trabalho/`, `saida/`, `credenciais/` -> **fora do Git** (vídeos grandes ficam no Google Drive)
