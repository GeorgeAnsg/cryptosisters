import json
import os
import urllib.request

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def _post(metodo, payload):
    if not TOKEN:
        print(f"Telegram no configurado, me salto {metodo}:", payload)
        return None
    url = f"https://api.telegram.org/bot{TOKEN}/{metodo}"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"fallo llamando a telegram.{metodo}:", e)
        return None


def enviar(texto, boton_abrir_alerta_id=None):
    """boton_abrir_alerta_id: si se da, añade un boton inline 'Abrir' debajo
    del mensaje con ese id de alerta en el callback_data -- lo gestiona
    telegram_bot.py (ver manejar_callback)."""
    if not TOKEN or not CHAT_ID:
        print("Telegram no configurado, me salto el aviso:", texto)
        return
    payload = {"chat_id": CHAT_ID, "text": texto, "parse_mode": "HTML"}
    if boton_abrir_alerta_id:
        payload["reply_markup"] = {"inline_keyboard": [[
            {"text": "Abrir", "callback_data": f"abrir:{boton_abrir_alerta_id}"}
        ]]}
    _post("sendMessage", payload)
