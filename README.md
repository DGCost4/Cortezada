# 🎮 Cortes de Lives — Canal Dark (GTA 6 e jogos)

Pipeline automático que pega uma live de jogo, encontra os momentos com potencial de viralizar
e gera cortes verticais editados, prontos para **YouTube Shorts, TikTok e Reels**.

## O que a edição faz
- Detecta picos: volume (gritos, explosões, risadas), palavras de hype em PT-BR ("meu deus", "não acredito", "kkkk"...) e fala acelerada
- Corta 15–58 s alinhado com o começo/fim das frases e remove tempo morto
- Formato 9:16 (1080x1920): gameplay no centro + fundo desfocado (ou tela cheia)
- Título-gancho grande no topo · legenda animada palavra por palavra (amarelo + pop)
- Zoom no momento do pico · barra de progresso · áudio normalizado em -14 LUFS · marca d'água do canal

## Instalação
```bash
bash setup.sh
```

## Uso
```bash
# tudo de uma vez (aceita .zip, .rar, .7z ou o vídeo direto)
bash scripts/processar.sh entrada/minha_live.zip --marca "@MeuCanal"

# ou passo a passo
python3 scripts/analisar.py entrada/minha_live.mp4          # gera trabalho/minha_live/cortes.json
# (revise/edite cortes.json: inicio, fim, titulo, aprovado)
python3 scripts/editar.py trabalho/minha_live/cortes.json --marca "@MeuCanal"
python3 scripts/upload_youtube.py saida/minha_live/c01.mp4 --agendar 2026-11-20T18:00:00-03:00
```

Veja `CLAUDE.md` para o fluxo completo de curadoria e os critérios de viralização.

## Onde ficam os arquivos
| Pasta | Conteúdo | Git? |
|---|---|---|
| `scripts/` | código | ✅ |
| `entrada/` | lives brutas | ❌ (Google Drive) |
| `trabalho/` | transcrições e análises | ❌ |
| `saida/` | cortes prontos + títulos | ❌ (Google Drive) |
| `credenciais/` | chaves do YouTube | ❌ nunca |
