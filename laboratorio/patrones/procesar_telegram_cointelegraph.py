"""18-sept-2026: enriquece los 27.052 mensajes de Cointelegraph (Telegram,
2021-2024, ver descargar_telegram_cointelegraph.py) con alcance, categoria,
sentiment corregido e importancia -- ver memoria persistente
project_corvus4_mecanismo_noticias.

Sustituye a GDELT como fuente principal porque cada mensaje es UNA historia
(no un "Hodler Digest" con 3 mezcladas), lo que hace mucho mas fiable
tanto la categorizacion como el sentiment.

ALCANCE (pedido por el usuario, 18-sept-2026): Bitcoin actua de proxy del
mercado cripto en conjunto (domina ~40-60% de la capitalizacion, arrastra
al resto) -- toda noticia que mencione Bitcoin/BTC se trata como
"mercado_general", no como especifica de una sola moneda. Ethereum tiene
su propio espacio de noticias (su red, su gente) que no mueve a Bitcoin
igual -- eso es "ethereum_especifico". El resto (XRP, Dash, Stellar...)
es "otra_moneda", baja prioridad para este bot (solo opera BTC/ETH).

IMPORTANCIA: percentil CAUSAL (expanding window, sin mirar al futuro,
mismo principio que percentil_causal() en noticias_senal_rafaga.py) del
numero de vistas de cada mensaje frente a todo el historial visto hasta
ese momento -- nunca un numero de vistas fijo a mano."""
from __future__ import annotations

import bisect
import json
import re
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from laboratorio.patrones.noticias_categorias import categorizar, es_ruido_estructural
from laboratorio.patrones.telegram_sentiment import analyze_headline_sentiment

_RE_BTC = re.compile(r"\bbitcoin\b|\bbtc\b")
_RE_ETH = re.compile(r"\bethereum\b|\beth\b|\bvitalik\b")

# Cointelegraph tambien tiene sus propios posts-resumen multi-historia
# ("In Case You Missed It", "Top Gainers/Losers") -- mucho menos frecuentes
# que los "Hodler Digest" de GDELT (1.5% aqui vs bastante mas alli), pero
# igual de poco fiables para categorizar/puntuar como si fueran una sola
# noticia. Se detectan por estructura (3+ emoji de vineta en el mismo
# mensaje), no por frase -- una frase como "Missed the news" tambien
# aparecia en articulos de una sola historia (falsos positivos).
_EMOJIS_VINETA = ["📈", "📉", "🧐", "💰", "❌", "🥷", "👉", "🚨", "💪", "🔥", "⚡", "📢", "🗞"]


def es_digest_multihistoria(titulo: str) -> bool:
    return sum(titulo.count(e) for e in _EMOJIS_VINETA) >= 3

RUTA_ENTRADA = "/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/telegram_cointelegraph_2021_2024.json"
RUTA_SALIDA = "/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/telegram_cointelegraph_2021_2024_enriquecido.json"


_CATS_MERCADO_GENERAL = {"macro", "geopolitico"}


def alcance_de(titulo: str, categorias: set[str] | list[str] = ()) -> str:
    """18-sept-2026: 'macro'/'geopolitico' (tipos de la Fed, inflacion,
    guerra/sanciones...) son mercado_general aunque el titular no nombre
    Bitcoin/Ethereum -- afectan a todo el mercado igual que si lo hicieran,
    misma logica que "Bitcoin como proxy" (ver docstring del modulo),
    extendida por el usuario al ver que Tree News (mucho mas macro que
    Cointelegraph) clasificaba mal noticias como "U.S. CPI: +3.4%"."""
    if set(categorias) & _CATS_MERCADO_GENERAL:
        return "mercado_general"
    t = titulo.lower()
    if _RE_BTC.search(t):
        return "mercado_general"  # Bitcoin como proxy del mercado, ver docstring
    if _RE_ETH.search(t):
        return "ethereum_especifico"
    return "otra_moneda"


def percentil_causal_valores(valores: list[float], minimo_historia: int = 100) -> list[float | None]:
    """Percentil causal (mean rank, ver noticias_senal_rafaga.percentil_causal)
    de cada valor frente a TODO el historial visto hasta ese momento -- sin
    mirar al futuro. None mientras no haya historial suficiente.

    Implementado con una lista ordenada (bisect) en vez de recorrer el
    historial entero cada vez -- con 27k mensajes, la version O(n^2) por
    fuerza bruta tarda demasiado."""
    out: list[float | None] = []
    ordenados: list[float] = []
    for i, v in enumerate(valores):
        if i < minimo_historia:
            out.append(None)
        else:
            n = len(ordenados)
            estricto = bisect.bisect_left(ordenados, v) / n
            debil = bisect.bisect_right(ordenados, v) / n
            out.append((debil + estricto) / 2 * 100)
        bisect.insort(ordenados, v)
    return out


def main() -> None:
    with open(RUTA_ENTRADA) as f:
        mensajes = json.load(f)

    mensajes.sort(key=lambda m: (m["fecha"], m["hora"]))  # orden temporal, imprescindible para el percentil causal

    vistas = [m["vistas"] for m in mensajes]
    percentiles = percentil_causal_valores(vistas)

    enriquecidos = []
    for m, pctl in zip(mensajes, percentiles):
        cats = sorted(categorizar(m["titulo"]))
        sentiment = analyze_headline_sentiment(m["titulo"])
        digest = es_digest_multihistoria(m["titulo"])
        ruido = es_ruido_estructural(m["titulo"])
        # "Interesante" = encaja en alguna categoria de alto impacto (hackeo,
        # quiebra, regulatorio, geopolitico, macro, crash) Y no es un post-resumen
        # multi-historia Y no es ruido estructural (digest/podcast/opinion/encuesta,
        # ver es_ruido_estructural -- validado a mano contra 509 titulares reales,
        # cubre el 32% del ruido real con 7% de coste, techo real sin LLM en vivo).
        # Un titular que no encaja en ninguna categoria no tiene ningun evento
        # discreto detras -- es comentario de precio/analisis tecnico ("Bitcoin
        # sube a 60K", "3 razones por las que ETH bajo"), que el propio feed de
        # precios del bot ya conoce sin necesitar la noticia.
        interesante = bool(cats) and not digest and not ruido
        enriquecidos.append({
            **m,
            "fuente": "cointelegraph",
            "alcance": alcance_de(m["titulo"], cats),
            "categorias": cats,
            "sentiment": sentiment,
            "importancia_percentil": round(pctl, 1) if pctl is not None else None,
            "es_digest": digest,
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
    n_digest = sum(1 for e in enriquecidos if e["es_digest"])
    print(f"digest multi-historia (excluidos de interesante): {n_digest}/{len(enriquecidos)}")
    n_interesante = sum(1 for e in enriquecidos if e["interesante"])
    print(f"interesante (categoria + no-digest): {n_interesante}/{len(enriquecidos)}")
    con_pctl_alto = sum(1 for e in enriquecidos if e["importancia_percentil"] and e["importancia_percentil"] >= 90)
    print(f"con importancia (vistas) >= percentil 90: {con_pctl_alto}/{len(enriquecidos)}")


if __name__ == "__main__":
    main()
