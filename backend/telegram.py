import json
import os
import urllib.request

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def enviar(texto):
    # ponytail: una llamada HTTP directa a la Bot API basta para solo-enviar;
    # no hace falta la libreria de bot completa (comandos, polling) porque
    # el front ya gestiona "a quien sigo", no necesitamos /watch por Telegram.
    if not TOKEN or not CHAT_ID:
        print("Telegram no configurado, me salto el aviso:", texto)
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": texto, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("fallo enviando a telegram:", e)
