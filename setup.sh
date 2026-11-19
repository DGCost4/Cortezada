#!/usr/bin/env bash
# Instala dependências (Linux/Debian/Ubuntu ou ambiente de nuvem do Claude Code)
set -e
cd "$(dirname "$0")"
if command -v apt-get >/dev/null; then
  apt-get install -y -q ffmpeg p7zip-full fonts-roboto >/dev/null 2>&1 || \
    (apt-get update -q && apt-get install -y -q ffmpeg p7zip-full fonts-roboto)
fi
pip install -q -r requirements.txt
mkdir -p entrada trabalho saida credenciais
echo "Pronto!"
