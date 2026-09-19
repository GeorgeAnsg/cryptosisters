"""18-sept-2026: nueva fuente de noticias para el mecanismo de salida
informado por noticias -- ver memoria persistente
project_corvus4_mecanismo_noticias. Sustituye/complementa a GDELT
(descargar_noticias_importantes.py) porque GDELT trae muchos titulares
tipo "digest" que mezclan 2-3 historias sin relacion en una sola frase
(ej. "Hodler Digest: Celsius quiebra, Su Zhu vuelve a Twitter y OpenSea
despide al 20%") -- eso hace que la categorizacion y el sentiment por
titular sean poco fiables para una parte grande del dataset.

Cointelegraph en Telegram (@cointelegraph) existe desde agosto de 2016 --
de sobra para cubrir 2021-2024 -- y publica UNA historia por mensaje,
consistentemente, con etiquetas propias de urgencia (JUST IN/BREAKING/
INSIGHT + emoji 🚨🔥⚡️) que sirven de pista adicional de importancia (juicio
editorial humano, no palabras clave nuestras).

Requiere las credenciales de la cuenta de Telegram del USUARIO
(.telegram_credenciales.json, gitignored) -- la primera vez que se ejecuta
pide interactivamente numero de telefono + codigo de un solo uso, tiene
que ejecutarse en una terminal visible para el usuario, nunca en segundo
plano sin supervision la primera vez."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

RAIZ = Path(__file__).resolve().parents[2]
CREDENCIALES = json.loads((RAIZ / ".telegram_credenciales.json").read_text())
SESION = str(RAIZ / ".cointelegraph_session")

CANAL = "cointelegraph"
FECHA_INI = datetime(2021, 1, 1, tzinfo=timezone.utc)
FECHA_FIN = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


async def descargar(ruta_salida: str) -> None:
    client = TelegramClient(SESION, CREDENCIALES["api_id"], CREDENCIALES["api_hash"])
    await client.start()  # primera vez: pide telefono + codigo por input() interactivo

    entidad = await client.get_entity(CANAL)
    mensajes = []
    n = 0
    async for msg in client.iter_messages(entidad, offset_date=FECHA_INI, reverse=True):
        if msg.date > FECHA_FIN:
            break
        texto = (msg.message or "").strip()
        if not texto or len(texto) < 15:
            continue  # sin texto util (solo foto/video sin descripcion, etc.)

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
    ruta = sys.argv[1] if len(sys.argv) > 1 else str(RAIZ / "datos" / "crudo" / "telegram_cointelegraph_2021_2024.json")
    asyncio.run(descargar(ruta))
