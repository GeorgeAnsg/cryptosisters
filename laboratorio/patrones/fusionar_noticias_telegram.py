"""18-sept-2026: fusiona las dos fuentes de Telegram ya enriquecidas
(Cointelegraph + Tree News, ver procesar_telegram_cointelegraph.py y
procesar_telegram_treenews.py) en una sola linea temporal -- ver memoria
persistente project_corvus4_mecanismo_noticias.

Solo se conservan los mensajes marcados "interesante" (categoria de alto
impacto + no-digest, ver docstring de procesar_telegram_cointelegraph.py):
el resto es ruido de precio/analisis/spam de exchanges que el propio bot
ya sabe por su feed de precios, no aporta señal nueva."""
from __future__ import annotations

import json

RUTAS = [
    "/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/telegram_cointelegraph_2021_2024_enriquecido.json",
    "/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/telegram_treenews_2021_2024_enriquecido.json",
]
RUTA_SALIDA = "/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/telegram_noticias_2021_2024_combinado.json"


def main() -> None:
    todos = []
    for r in RUTAS:
        with open(r) as f:
            todos.extend(json.load(f))

    interesantes = [m for m in todos if m["interesante"]]
    interesantes.sort(key=lambda m: (m["fecha"], m["hora"]))

    with open(RUTA_SALIDA, "w") as f:
        json.dump(interesantes, f, ensure_ascii=False, indent=2)

    print(f"total combinado: {len(todos)} | interesantes: {len(interesantes)} -> {RUTA_SALIDA}")
    from collections import Counter
    print("por fuente:", Counter(m["fuente"] for m in interesantes))
    print("por alcance:", Counter(m["alcance"] for m in interesantes))


if __name__ == "__main__":
    main()
