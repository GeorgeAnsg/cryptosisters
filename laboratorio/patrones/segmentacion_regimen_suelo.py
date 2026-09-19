"""
Espejo alcista exacto de `segmentacion_regimen_techo.py` -- mismo hallazgo
a comprobar pero en la direccion contraria: un doble suelo formado con el
precio ya por ENCIMA de su media de 200 dias Y esa media SUBIENDO
(tendencia de fondo ya recuperandose) deberia confirmar la reversion
alcista con mas fiabilidad que uno formado en plena tendencia bajista de
fondo (donde romper el pico intermedio hacia arriba puede ser solo un
rebote dentro de una caida mas grande -- un "dead cat bounce").
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_suelo_flexible


def _candidatos_confirmados_con_regimen(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_rebote, peso_tiempo, peso_altura = pesos
    candidatos = doble_suelo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close = df["close"]
    sma200 = close.rolling(200).mean()
    n = len(df)
    filas = []
    for c in candidatos:
        maximo_intermedio = close.iloc[c.idx_fondo1: c.idx_fondo2 + 1].max()
        fin_conf = min(c.idx_fondo2 + 1 + vcp.DIAS_CONFIRMACION, n)
        tramo_conf = close.iloc[c.idx_fondo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf > maximo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        media = sma200.iloc[c.idx_fondo2]
        media_hace_20 = sma200.iloc[c.idx_fondo2 - 20] if c.idx_fondo2 >= 20 else None
        encima_media = bool(media == media and close.iloc[c.idx_fondo2] > media)
        media_subiendo = bool(
            media == media and media_hace_20 is not None and media_hace_20 == media_hace_20 and media > media_hace_20
        )
        filas.append({
            "idx_fondo2": c.idx_fondo2, "idx_confirmacion": idx_confirmacion,
            "encima_media200": encima_media, "media_subiendo": media_subiendo,
            "encima_y_subiendo": encima_media and media_subiendo,
        })
    return filas


def _resumen_segmento(df: pd.DataFrame, filas: list[dict], desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    filas_planas = [(f["idx_fondo2"], f["idx_confirmacion"]) for f in filas]
    return vcp._resumen(df, filas_planas, desde, hasta, exito_es_subida=True)["con_confirmacion"]


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_regimen_suelo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_regimen_suelo_btc")

    resultados_suelo = []
    for pesos in vcp.PESOS_SUELO:
        filas = vcp._entradas_confirmadas_suelo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, True)
        resultados_suelo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_suelo)["pesos"]
    print(f"Pesos congelados (elegidos SOLO en ETH-ajuste): {mejor_pesos}\n")

    cortes = [
        ("ETH 2017-2021 (nunca usado en el ajuste)", df_eth, df_eth["open_time"].min(), vcp.CORTE),
        ("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN),
        ("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN),
        ("BTC completo (moneda nunca vista)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN),
    ]

    for nombre, df, desde, hasta in cortes:
        print(f"=== {nombre} ===")
        filas = _candidatos_confirmados_con_regimen(df, mejor_pesos)
        eyc = [f for f in filas if f["encima_y_subiendo"]]
        resto = [f for f in filas if not f["encima_y_subiendo"]]
        r_eyc = _resumen_segmento(df, eyc, desde, hasta)
        r_resto = _resumen_segmento(df, resto, desde, hasta)
        print(f"  encima Y SUBIENDO (tendencia fondo recuperandose): {json.dumps(r_eyc, default=str)}")
        print(f"  resto: {json.dumps(r_resto, default=str)}")
        print()
