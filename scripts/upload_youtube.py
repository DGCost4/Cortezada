#!/usr/bin/env python3
"""
Publica (ou agenda) um corte no YouTube como Short, via YouTube Data API v3.

Configuração (uma vez só, no SEU computador — precisa de navegador para o login):
  1. https://console.cloud.google.com -> crie um projeto -> ative "YouTube Data API v3"
  2. Tela de consentimento OAuth (tipo "Externo", adicione seu e-mail como usuário de teste)
  3. Credenciais -> "ID do cliente OAuth" -> tipo "App para computador" -> baixe o JSON
  4. Salve como  credenciais/client_secret.json  (essa pasta NÃO vai pro Git)
  5. pip install google-api-python-client google-auth-oauthlib

Uso:
  python3 scripts/upload_youtube.py saida/<live>/c01.mp4                 # usa o c01.txt ao lado
  python3 scripts/upload_youtube.py saida/<live>/c01.mp4 --agendar 2026-11-20T18:00:00-03:00
  python3 scripts/upload_youtube.py saida/<live>/c01.mp4 --privado        # sobe como privado p/ revisar

Obs.: a cota grátis da API permite ~6 uploads/dia por projeto.
"""
import argparse
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CRED = RAIZ / "credenciais"
ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload"]


def autenticar():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    tok = CRED / "token_youtube.json"
    creds = Credentials.from_authorized_user_file(str(tok), ESCOPOS) if tok.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED / "client_secret.json"), ESCOPOS)
            creds = flow.run_local_server(port=0)
        tok.write_text(creds.to_json())
    return creds


def ler_metadados(txt: Path):
    s = txt.read_text(encoding="utf-8")
    titulo = re.search(r"TÍTULO[^\n]*\n(.+)", s).group(1).strip()[:100]
    desc = re.search(r"DESCRIÇÃO:\n(.*?)\n\nFALA DO TRECHO", s, re.S).group(1).strip()
    tags = [t.lstrip("#") for t in re.findall(r"#\w+", desc)]
    return titulo, desc, tags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--agendar", help="data/hora ISO 8601 com fuso, ex.: 2026-11-20T18:00:00-03:00")
    ap.add_argument("--privado", action="store_true")
    a = ap.parse_args()
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    video = Path(a.video)
    titulo, desc, tags = ler_metadados(video.with_suffix(".txt"))
    status = {"privacyStatus": "private" if (a.privado or a.agendar) else "public",
              "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": False}
    if a.agendar:
        status["publishAt"] = a.agendar
    yt = build("youtube", "v3", credentials=autenticar())
    req = yt.videos().insert(part="snippet,status", body={
        "snippet": {"title": titulo, "description": desc, "tags": tags, "categoryId": "20",  # 20 = Jogos
                    "defaultLanguage": "pt-BR", "defaultAudioLanguage": "pt-BR"},
        "status": status}, media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    print(f"Publicado: https://youtube.com/shorts/{resp['id']}  ({status['privacyStatus']})")


if __name__ == "__main__":
    main()
