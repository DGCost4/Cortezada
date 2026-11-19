#!/usr/bin/env bash
# Pipeline completo: descompacta (zip/rar/7z) -> analisa -> renderiza os cortes.
# Uso: bash scripts/processar.sh entrada/live.zip [--modelo small] [--max-cortes N] [--marca @canal] [--layout blur|cheio]
set -euo pipefail
cd "$(dirname "$0")/.."
ARQ="$1"; shift
MODELO="small"; EXTRA_EDIT=(); EXTRA_AN=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --modelo) MODELO="$2"; shift 2;;
    --max-cortes|--min|--max|--antes|--depois) EXTRA_AN+=("$1" "$2"); shift 2;;
    *) EXTRA_EDIT+=("$1"); shift;;
  esac
done
NOME="$(basename "${ARQ%.*}")"
case "${ARQ,,}" in
  *.zip|*.rar|*.7z)
    DEST="entrada/$NOME"; mkdir -p "$DEST"
    7z x -y -o"$DEST" "$ARQ" >/dev/null
    mapfile -t VIDEOS < <(find "$DEST" -type f \( -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.webm' -o -iname '*.mov' -o -iname '*.ts' -o -iname '*.flv' \) | sort);;
  *) VIDEOS=("$ARQ");;
esac
[[ ${#VIDEOS[@]} -gt 0 ]] || { echo "Nenhum vídeo encontrado em $ARQ"; exit 1; }
for V in "${VIDEOS[@]}"; do
  echo "=== Analisando: $V"
  python3 scripts/analisar.py "$V" --modelo "$MODELO" "${EXTRA_AN[@]}"
  STEM="$(basename "${V%.*}")"
  echo "=== Editando cortes de: $STEM"
  python3 scripts/editar.py "trabalho/$STEM/cortes.json" "${EXTRA_EDIT[@]}"
done
