#!/usr/bin/env python3
"""
Notificaciones de Telegram para el paper trading -- rescatado y
simplificado de v6/core/bot_core.py:send_telegram (el bot viejo, ya
descartado, pero esa funcion en concreto funcionaba bien).

Dos usos:
  --inicio   manda un aviso una vez, al arrancar el contenedor.
  (sin args) comprueba si ya es de noche (hora Madrid) y si hoy no se ha
             mandado aun el resumen diario -- si toca, lee la ultima fila
             de cada log en logs/ y manda un mensaje con el capital
             ficticio de cada activo.

Los CSV de logs/ siguen siendo la fuente de verdad detallada (una fila por
ciclo, cada 4h, para cada activo) -- esto es solo el titular legible para
no tener que abrir los CSV cada dia. Revisa los CSV cuando quieras ver
TODAS las acciones tomadas, no solo el resumen de la noche.

Variables de entorno necesarias (si faltan, no envia nada ni falla el
contenedor -- solo lo avisa por stdout):
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_grid_papel import DIR_DATA_ROOT, DIR_LOGS

HORA_RESUMEN_MADRID = 20  # a partir de esta hora local (Europe/Madrid) se manda el resumen del dia


def enviar_telegram(mensaje: str) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[telegram] TELEGRAM_TOKEN/TELEGRAM_CHAT_ID no configurados -- no se envia nada")
        return False
    try:
        data = json.dumps({"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[telegram] fallo al enviar: {e}")
        return False


def _ultima_fila(ruta_csv: str) -> dict | None:
    if not os.path.exists(ruta_csv):
        return None
    with open(ruta_csv) as f:
        filas = list(csv.DictReader(f))
    return filas[-1] if filas else None


def construir_resumen() -> str:
    if not os.path.isdir(DIR_LOGS) or not os.listdir(DIR_LOGS):
        return "📊 Paper trading -- todavia no hay ningun log (el primer ciclo aun no ha corrido)."

    lineas = [f"📊 <b>Resumen paper trading -- {datetime.now(ZoneInfo('Europe/Madrid')).strftime('%d/%m %H:%M')}</b>"]
    for nombre in sorted(os.listdir(DIR_LOGS)):
        if not nombre.endswith(".csv"):
            continue
        fila = _ultima_fila(os.path.join(DIR_LOGS, nombre))
        if not fila:
            continue
        par = fila.get("par", nombre.replace("_paper.csv", ""))
        try:
            spot = float(fila["capital_spot"])
            mercado = float(fila["capital_futuros_mercado"])
            limite = float(fila["capital_futuros_limite"])
            n_trades = fila["n_trades"]
        except (KeyError, ValueError):
            lineas.append(f"⚠️ {par}: fila de log con formato inesperado")
            continue
        lineas.append(
            f"<b>{par}</b>: spot {spot:.1f} | mercado {mercado:.1f} | limite {limite:.1f} ({n_trades} trades)"
        )
    return "\n".join(lineas)


def resumen_diario_si_toca():
    ahora_madrid = datetime.now(ZoneInfo("Europe/Madrid"))
    if ahora_madrid.hour < HORA_RESUMEN_MADRID:
        return

    marcador = os.path.join(DIR_DATA_ROOT, "ultimo_resumen_enviado.txt")
    hoy = ahora_madrid.strftime("%Y-%m-%d")
    if os.path.exists(marcador):
        with open(marcador) as f:
            if f.read().strip() == hoy:
                return  # ya se mando hoy

    if enviar_telegram(construir_resumen()):
        os.makedirs(DIR_DATA_ROOT, exist_ok=True)
        with open(marcador, "w") as f:
            f.write(hoy)


if __name__ == "__main__":
    if "--inicio" in sys.argv:
        enviar_telegram(
            "🟢 Bot de paper trading iniciado -- corriendo cada 4h (18 activos: "
            "12 cripto + oro + 3 acciones + 2 indices), resumen diario por la noche."
        )
    else:
        resumen_diario_si_toca()
