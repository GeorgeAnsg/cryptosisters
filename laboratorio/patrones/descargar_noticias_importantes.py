"""
18-sept-2026: el usuario pregunto si se pueden descargar noticias reales de
"este año" quedandose solo con las importantes (no ruido) -- comprobado que
YA existe la pieza clave en OTRO proyecto del propio usuario, sin migrar:
`~/Desktop/tr/v6/core/bot_sentiment.py` usa GDELT (api.gdeltproject.org,
publica, sin clave) filtrado a dominios cripto serios (Coindesk,
Cointelegraph, Decrypt, The Block, Bitcoin Magazine, NewsBTC) y ya trae una
lista `HIGH_IMPACT_KEYWORDS` (Fed/tipos, SEC, hackeos, ETF, guerras,
FTX/Celsius/Tether, crashes) para separar noticia con peso real de ruido.

Prueba de cobertura historica (18-sept-2026): GDELT SI tiene indexadas
noticias reales de mayo-2022 (incluido el desplome de Terra/Luna) -- esto
resuelve el bloqueo de datos que dejo sin cerrar
`momentum_tras_noticia_proxy_precio_volumen` (17-sept-2026, ver
registro/intentos.jsonl): en aquel intento no habia noticias reales con
cobertura 2021-2024, solo proxies de precio/volumen que no generalizaron.

Este script reutiliza fetch_gdelt_articles/HIGH_IMPACT_KEYWORDS de
bot_sentiment.py (no los reimplementa) para descargar, por tramos de 14
dias (limite practico de maxrecords=250 de GDELT sin perder cobertura),
solo las noticias reales que mencionan al menos una HIGH_IMPACT_KEYWORD --
el resto (ruido diario tipo "3 razones para que suba/baje") se descarta en
el propio filtro, no se guarda.

Rate limit real de GDELT observado: primeras 1-2 llamadas devuelven 429,
hay que reintentar con espera -- fetch_gdelt_articles ya trae ese retry.

18-sept-2026: el usuario pregunto si los tramos que devolvieron "0
articulos" eran de verdad tramos sin noticias o un fallo de la llamada
disfrazado de vacio. Diagnostico (ver
`registro/intentos.jsonl`, intento `descarga_noticias_ventanas_vacias_429`):
9 de 10 tramos "vacios" de la descarga BTC-2022 eran HTTP 429 (limite de
tasa de GDELT) agotando los 6 reintentos de `fetch_gdelt_articles` antes de
que el limite se levantara -- incluida la ventana del colapso de FTX
(5-18 nov 2022), que al reintentar a mano SI trajo 136 articulos. `0
articulos` NO es de fiar como "no hubo noticias esa quincena": es
indistinguible de un fallo silencioso. Por eso `descargar_rango` ahora
RELANZA automaticamente, en pasadas sucesivas con mas espera, cualquier
tramo que haya devuelto 0 articulos -- ver `_reintentar_vacios`."""
import sys
import time
import json
import datetime

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/tr")

from v6.core.bot_sentiment import (
    CRYPTO_NEWS_DOMAINS, HIGH_IMPACT_KEYWORDS, TICKER_TO_NAME,
    fetch_gdelt_articles, analyze_headline_sentiment,
)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DIAS_POR_TRAMO = 14


def _es_alto_impacto(titulo: str) -> bool:
    t = titulo.lower()
    return any(kw in t for kw in HIGH_IMPACT_KEYWORDS)


def _construir_query(ticker: str) -> str:
    domain_filter = " OR ".join(f"domainis:{d}" for d in CRYPTO_NEWS_DOMAINS)
    nombre = TICKER_TO_NAME.get(ticker.upper(), ticker.lower())
    return f"{nombre} ({domain_filter})"


def _procesar(articulos: list) -> list:
    importantes = [a for a in articulos if _es_alto_impacto(a.get("title", ""))]
    out = []
    for a in importantes:
        val = analyze_headline_sentiment(a["title"])
        out.append({
            "fecha": a["date"], "fuente": a.get("source", ""),
            "titulo": a["title"], "sentiment": "+" if val > 0 else ("-" if val < 0 else "="),
        })
    return out


def descargar_rango(ticker: str, fecha_ini: str, fecha_fin: str, pausa_seg: float = 6.0,
                     max_pasadas_reintento: int = 3, pausa_reintento_seg: float = 30.0) -> list:
    """Descarga por tramos de DIAS_POR_TRAMO dias entre fecha_ini y fecha_fin
    (formato 'YYYY-MM-DD'), filtra a HIGH_IMPACT_KEYWORDS, devuelve lista de
    dicts {fecha, fuente, titulo, sentiment}.

    `0 articulos` en un tramo es indistinguible, sin mirar el codigo HTTP, de
    un fallo de la llamada (ver docstring del modulo) -- por eso, tras la
    pasada normal, cualquier tramo que haya quedado en 0 se relanza solo,
    con mas espera entre reintentos que el resto (`pausa_reintento_seg`,
    mayor que `pausa_seg`), hasta `max_pasadas_reintento` veces o hasta que
    ya no quede ningun tramo en 0."""
    query = _construir_query(ticker)
    ini = datetime.date.fromisoformat(fecha_ini)
    fin = datetime.date.fromisoformat(fecha_fin)
    tramos = []
    cursor = ini
    while cursor <= fin:
        tramo_fin = min(cursor + datetime.timedelta(days=DIAS_POR_TRAMO - 1), fin)
        tramos.append((cursor, tramo_fin))
        cursor = tramo_fin + datetime.timedelta(days=1)

    resultado_por_tramo = {}
    for cursor, tramo_fin in tramos:
        start = cursor.strftime("%Y%m%d000000")
        end = (tramo_fin + datetime.timedelta(days=1)).strftime("%Y%m%d000000")
        articulos = fetch_gdelt_articles(query, start=start, end=end, maxrecords=250, retries=6)
        resultado_por_tramo[(cursor, tramo_fin)] = articulos
        print(f"  [{ticker}] {cursor} -> {tramo_fin}: {len(articulos)} articulos, "
              f"{len(_procesar(articulos))} de alto impacto")
        time.sleep(pausa_seg)

    for pasada in range(1, max_pasadas_reintento + 1):
        vacios = [t for t, arts in resultado_por_tramo.items() if len(arts) == 0]
        if not vacios:
            break
        print(f"  [{ticker}] pasada de reintento {pasada}/{max_pasadas_reintento}: "
              f"{len(vacios)} tramo(s) en 0 articulos, relanzando...")
        for cursor, tramo_fin in vacios:
            start = cursor.strftime("%Y%m%d000000")
            end = (tramo_fin + datetime.timedelta(days=1)).strftime("%Y%m%d000000")
            time.sleep(pausa_reintento_seg)
            articulos = fetch_gdelt_articles(query, start=start, end=end, maxrecords=250, retries=6)
            resultado_por_tramo[(cursor, tramo_fin)] = articulos
            print(f"    [{ticker}] reintento {cursor} -> {tramo_fin}: {len(articulos)} articulos, "
                  f"{len(_procesar(articulos))} de alto impacto")

    vacios_finales = [t for t, arts in resultado_por_tramo.items() if len(arts) == 0]
    if vacios_finales:
        print(f"  [{ticker}] tramos que siguen en 0 tras {max_pasadas_reintento} reintentos "
              f"(posible vacio real, no fallo): {[f'{a}->{b}' for a, b in vacios_finales]}")

    resultado = []
    n_tramos = 0
    for cursor, tramo_fin in tramos:
        n_tramos += 1
        resultado.extend(_procesar(resultado_por_tramo[(cursor, tramo_fin)]))
    print(f"-> {ticker} {fecha_ini}..{fecha_fin}: {n_tramos} tramos, {len(resultado)} noticias de alto impacto guardadas")
    return resultado


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="BTC")
    p.add_argument("--inicio", default="2022-01-01")
    p.add_argument("--fin", default="2022-12-31")
    p.add_argument("--salida", default=None)
    args = p.parse_args()

    salida = args.salida or f"/private/tmp/claude-501/-Users-jorgeansotegui-Desktop-tr/e3884417-1986-415a-bdd2-35a04103dd15/scratchpad/noticias_{args.ticker.lower()}_{args.inicio}_{args.fin}.json"
    noticias = descargar_rango(args.ticker, args.inicio, args.fin)
    with open(salida, "w") as f:
        json.dump(noticias, f, ensure_ascii=False, indent=2)
    print(f"guardado: {salida}")
