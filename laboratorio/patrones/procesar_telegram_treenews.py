"""18-sept-2026: enriquece los mensajes de Tree News (Telegram, 2021-2024,
ver descargar_telegram_treenews.py) con alcance, categoria, sentiment e
importancia -- mismo proceso que procesar_telegram_cointelegraph.py,
reutilizado en vez de duplicado (misma funcion alcance_de/categorizar/
analyze_headline_sentiment, mismo percentil causal por bisect).

NO se aplica el filtro de digest multi-historia de Cointelegraph: Tree
News nunca publica resumenes de varias historias en un mismo mensaje (es
un teletipo, una linea por hecho) -- comprobado a ojo sobre la muestra
descargada, cero mensajes con el patron de vinetas."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from laboratorio.patrones.noticias_categorias import categorizar, es_ruido_estructural
from laboratorio.patrones.telegram_sentiment import analyze_headline_sentiment
from laboratorio.patrones.procesar_telegram_cointelegraph import (
    alcance_de,
    percentil_causal_valores,
)

RUTA_ENTRADA = "/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/telegram_treenews_2021_2024.json"
RUTA_SALIDA = "/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/telegram_treenews_2021_2024_enriquecido.json"


def main() -> None:
    with open(RUTA_ENTRADA) as f:
        mensajes = json.load(f)

    mensajes.sort(key=lambda m: (m["fecha"], m["hora"]))

    vistas = [m["vistas"] for m in mensajes]
    percentiles = percentil_causal_valores(vistas)

    enriquecidos = []
    for m, pctl in zip(mensajes, percentiles):
        cats = sorted(categorizar(m["titulo"]))
        sentiment = analyze_headline_sentiment(m["titulo"])
        ruido = es_ruido_estructural(m["titulo"])
        interesante = bool(cats) and not ruido  # sin filtro de digest, ver docstring
        enriquecidos.append({
            **m,
            "fuente": "treenews",
            "alcance": alcance_de(m["titulo"], cats),
            "categorias": cats,
            "sentiment": sentiment,
            "importancia_percentil": round(pctl, 1) if pctl is not None else None,
            "es_digest": False,
            "es_ruido_estructural": ruido,
            "interesante": interesante,
        })

    with open(RUTA_SALIDA, "w") as f:
        json.dump(enriquecidos, f, ensure_ascii=False, indent=2)

    print(f"total: {len(enriquecidos)} mensajes -> {RUTA_SALIDA}")
    from collections import Counter
    print("alcance:", Counter(e["alcance"] for e in enriquecidos))
    print("sentiment:", Counter(e["sentiment"] for e in enriquecidos))
    con_categoria = sum(1 for e in enriquecidos if e["categorias"])
    print(f"con alguna categoria de alto impacto: {con_categoria}/{len(enriquecidos)}")
    n_interesante = sum(1 for e in enriquecidos if e["interesante"])
    print(f"interesante: {n_interesante}/{len(enriquecidos)}")


if __name__ == "__main__":
    main()
