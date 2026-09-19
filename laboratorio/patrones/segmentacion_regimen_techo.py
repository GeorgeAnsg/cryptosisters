"""
Idea pendiente desde el propio `doble_techo_flexible.py` (nunca probada):
"el filtro de regimen bajista (BTC por debajo de su media 200 y cayendo)
se deja FUERA por ahora". Aqui se trae de vuelta, pero como variable a
MEDIR y segmentar, no como filtro binario (misma disciplina que el resto
de este analisis -- "no absolutos").

Hipotesis: un doble techo que se forma con el precio ya por DEBAJO de su
media movil de 200 dias (tendencia de fondo ya debilitada / bajista)
deberia confirmar la rotura con mas fiabilidad que uno formado en plena
tendencia alcista de fondo (donde romper el valle intermedio puede ser
solo ruido dentro de una subida mas grande).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible


def _candidatos_confirmados_con_regimen(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close = df["close"]
    sma200 = close.rolling(200).mean()
    n = len(df)
    filas = []
    for c in candidatos:
        minimo_intermedio = close.iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + vcp.DIAS_CONFIRMACION, n)
        tramo_conf = close.iloc[c.idx_techo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf < minimo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        media = sma200.iloc[c.idx_techo2]
        media_hace_20 = sma200.iloc[c.idx_techo2 - 20] if c.idx_techo2 >= 20 else None
        debajo_media = bool(media == media and close.iloc[c.idx_techo2] < media)  # media==media descarta NaN
        media_cayendo = bool(
            media == media and media_hace_20 is not None and media_hace_20 == media_hace_20 and media < media_hace_20
        )
        filas.append({
            "idx_techo2": c.idx_techo2, "idx_confirmacion": idx_confirmacion,
            "debajo_media200": debajo_media, "media_cayendo": media_cayendo,
            "debajo_y_cayendo": debajo_media and media_cayendo,
        })
    return filas


def _resumen_segmento(df: pd.DataFrame, filas: list[dict], desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    filas_planas = [(f["idx_techo2"], f["idx_confirmacion"]) for f in filas]
    return vcp._resumen(df, filas_planas, desde, hasta, exito_es_subida=False)["con_confirmacion"]


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_regimen_techo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_regimen_techo_btc")

    resultados_techo = []
    for pesos in vcp.PESOS_TECHO:
        filas = vcp._entradas_confirmadas_techo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
        resultados_techo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_techo)["pesos"]
    print(f"Pesos congelados (elegidos SOLO en ETH-ajuste, sin cambios por este analisis): {mejor_pesos}\n")

    cortes = [
        ("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN),
        ("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN),
        ("BTC completo (moneda nunca vista)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN),
    ]

    for nombre, df, desde, hasta in cortes:
        print(f"=== {nombre} ===")
        filas = _candidatos_confirmados_con_regimen(df, mejor_pesos)
        debajo = [f for f in filas if f["debajo_media200"]]
        encima = [f for f in filas if not f["debajo_media200"]]
        debajo_y_cayendo = [f for f in filas if f["debajo_y_cayendo"]]
        resto = [f for f in filas if not f["debajo_y_cayendo"]]
        r_debajo = _resumen_segmento(df, debajo, desde, hasta)
        r_encima = _resumen_segmento(df, encima, desde, hasta)
        r_dyc = _resumen_segmento(df, debajo_y_cayendo, desde, hasta)
        r_resto = _resumen_segmento(df, resto, desde, hasta)
        print(f"  debajo media200 (tendencia fondo debil): {json.dumps(r_debajo, default=str)}")
        print(f"  encima media200 (tendencia fondo alcista): {json.dumps(r_encima, default=str)}")
        print(f"  debajo Y CAYENDO (condicion compuesta original): {json.dumps(r_dyc, default=str)}")
        print(f"  resto (no cumple la compuesta): {json.dumps(r_resto, default=str)}")
        print()
