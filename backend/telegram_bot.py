"""Bot de Telegram con polling para poder abrir una posicion directamente
desde el aviso de 'Nueva posicion' (boton 'Abrir' -> pregunta cuantos $ ->
abre). Reusa telegram.TOKEN/CHAT_ID y el mismo efecto que el boton 'Abrir'
de la web (db.abrir_posicion) -- la diferencia es solo el punto de entrada.

ponytail: nada de python-telegram-bot -- solo necesitamos un boton y una
respuesta de texto, asi que getUpdates por polling con urllib (igual que
telegram.enviar) basta, sin dependencia nueva ni webhook."""
import json
import threading
import time
import traceback
import urllib.request

import db
import hyperliquid
import telegram

INTERVALO_POLL_SEGUNDOS = 2

# direccion que esta esperando que le respondas con un $ para esta alerta --
# en memoria porque solo hay un usuario (CHAT_ID) y un proceso
pendientes = {}  # chat_id -> alerta_id


def _get_updates(offset):
    url = f"https://api.telegram.org/bot{telegram.TOKEN}/getUpdates?timeout=20&offset={offset}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def _responder(chat_id, texto):
    telegram._post("sendMessage", {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"})


def _responder_callback(callback_query_id, texto=""):
    telegram._post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": texto})


def manejar_callback(cq):
    chat_id = cq["message"]["chat"]["id"]
    data = cq.get("data", "")
    if not data.startswith("abrir:"):
        return
    alerta_id = data[len("abrir:"):]
    conn = db.conectar()
    fila = conn.execute("SELECT * FROM alertas WHERE id=?", (alerta_id,)).fetchone()
    conn.close()
    if fila is None:
        _responder_callback(cq["id"], "Esa alerta ya no existe")
        return
    if fila["estado"] == "hecho":
        _responder_callback(cq["id"], "Ya se abrió antes")
        return
    pendientes[chat_id] = alerta_id
    _responder_callback(cq["id"])
    etiqueta = f"{fila['lado']} {fila['coin']}" if fila["tipo"] == "trading" else fila["coin"]
    _responder(chat_id, f"¿Cuántos $ quieres invertir en {etiqueta}? Responde solo con el número.")


def manejar_mensaje(msg):
    chat_id = msg["chat"]["id"]
    if str(chat_id) != str(telegram.CHAT_ID):
        return  # solo el usuario configurado puede operar el bot
    alerta_id = pendientes.get(chat_id)
    if not alerta_id:
        return
    texto = (msg.get("text") or "").strip().replace(",", ".").replace("$", "")
    try:
        monto = float(texto)
        if monto <= 0:
            raise ValueError
    except ValueError:
        _responder(chat_id, "No te he entendido -- responde solo con un número, por ejemplo 250")
        return

    conn = db.conectar()
    fila = conn.execute("SELECT * FROM alertas WHERE id=?", (alerta_id,)).fetchone()
    if fila is None or fila["estado"] == "hecho":
        _responder(chat_id, "Esa alerta ya no está disponible")
        pendientes.pop(chat_id, None)
        conn.close()
        return

    precio = hyperliquid.precio_actual(fila["coin"], fila["tipo"]) or fila["precio"]
    if not precio:
        _responder(chat_id, "No he podido consultar el precio actual, inténtalo desde la web")
        conn.close()
        return

    tamaño = monto / precio
    db.abrir_posicion(
        conn, f"{alerta_id}_{int(time.time()*1000)}", fila["addr"], fila["tipo"], fila["coin"],
        fila["lado"], alerta_id, tamaño, precio, fila["tamaño"],
    )
    conn.close()
    pendientes.pop(chat_id, None)
    _responder(chat_id, f"Abierto: ${monto:,.0f} ({tamaño:.6f} {fila['coin']}) a ${precio}")


def ciclo_bot():
    if not telegram.TOKEN:
        print("telegram_bot: TELEGRAM_TOKEN no configurado, no arranco el polling")
        return
    offset = 0
    while True:
        try:
            resp = _get_updates(offset)
            for u in resp.get("result", []):
                offset = u["update_id"] + 1
                if "callback_query" in u:
                    manejar_callback(u["callback_query"])
                elif "message" in u:
                    manejar_mensaje(u["message"])
        except Exception:
            traceback.print_exc()
            time.sleep(INTERVALO_POLL_SEGUNDOS)


def arrancar_en_segundo_plano():
    threading.Thread(target=ciclo_bot, daemon=True).start()
