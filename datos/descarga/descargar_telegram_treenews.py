"""18-sept-2026: segunda fuente de noticias para el mecanismo de salida
informado por noticias -- ver memoria persistente
project_corvus4_mecanismo_noticias. Complementa a Cointelegraph
(descargar_telegram_cointelegraph.py): Tree News (@treenewsfeed) publica
titulares atomicos estilo teletipo (Bloomberg/Reuters), muy concisos, sin
relleno ni especulacion -- mas fuerte en macro/regulatorio/movimientos
institucionales (CPI, SEC, Saylor/Strategy) que Cointelegraph.

Existe desde el 15-jul-2020 (comprobado directamente contra Telegram con
Telethon, no por busqueda web) -- cubre de sobra 2021-2024.

Mismo mecanismo y credenciales que descargar_telegram_cointelegraph.py
(sesion ya autenticada, .telegram_credenciales.json, gitignored)."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient

RAIZ = Path(__file__).resolve().parents[2]
CREDENCIALES = json.loads((RAIZ / ".telegram_credenciales.json").read_text())
SESION = str(RAIZ / ".cointelegraph_session")  # misma sesion, misma cuenta de usuario

CANAL = "treenewsfeed"
FECHA_INI = datetime(2021, 1, 1, tzinfo=timezone.utc)
FECHA_FIN = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


async def descargar(ruta_salida: str) -> None:
    client = TelegramClient(SESION, CREDENCIALES["api_id"], CREDENCIALES["api_hash"])
    await client.start()

    entidad = await client.get_entity(CANAL)
    mensajes = []
    n = 0
    async for msg in client.iter_messages(entidad, offset_date=FECHA_INI, reverse=True):
        if msg.date > FECHA_FIN:
            break
        texto = (msg.message or "").strip()
        if not texto or len(texto) < 10:
            continue

        reacciones = {}
        if msg.reactions and msg.reactions.results:
            for r in msg.reactions.results:
                emoji = getattr(r.reaction, "emoticon", None)
                if emoji:
                    reacciones[emoji] = r.count

        mensajes.append({
            "fecha": msg.date.strftime("%Y-%m-%d"),
            "hora": msg.date.strftime("%H:%M:%S"),
            "titulo": texto.replace("\n", " ").strip(),
            "vistas": msg.views or 0,
            "reacciones": reacciones,
        })
        n += 1
        if n % 200 == 0:
            print(f"  ... {n} mensajes ({mensajes[-1]['fecha']})", flush=True)
            Path(ruta_salida).write_text(json.dumps(mensajes, ensure_ascii=False, indent=2))

    Path(ruta_salida).write_text(json.dumps(mensajes, ensure_ascii=False, indent=2))
    print(f"\nTOTAL: {n} mensajes guardados en {ruta_salida}")
    await client.disconnect()


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else str(RAIZ / "datos" / "crudo" / "telegram_treenews_2021_2024.json")
    asyncio.run(descargar(ruta))
