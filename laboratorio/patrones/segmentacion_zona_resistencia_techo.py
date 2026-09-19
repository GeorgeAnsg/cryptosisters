"""
Idea del usuario (11-sept-2026): si el nivel de precio del doble techo ya
habia sido tocado/rechazado ANTES de que se formara el propio techo1 (no
solo las 2 veces del patron en si), es una zona de resistencia mas real,
mas "testeada" -- deberia confirmar la rotura con mas fiabilidad que un
doble techo en un nivel de precio nuevo, sin historial previo.

Se cuenta cuantos maximos locales (mismo detector causal que el resto del
proyecto) cayeron dentro de una tolerancia de precio del nivel del techo,
en una ventana de tiempo ANTES de techo1 (no se mira nunca hacia el
futuro del propio patron). Se segmenta por si hubo 0, o 1+, toques
previos.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible
from laboratorio.patrones.doble_techo_flexible import _detectar_techos_simple

DIAS_VENTANA_HISTORICA = 180
TOLERANCIA_NIVEL_PCT = 5.0


def _candidatos_confirmados_con_zona(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close = df["close"].to_numpy()
    todos_techos = _detectar_techos_simple(close)
    n = len(df)
    filas = []
    for c in candidatos:
        nivel = close[c.idx_techo1]
        inicio_ventana = max(0, c.idx_techo1 - DIAS_VENTANA_HISTORICA)
        # toques previos: maximos locales ANTES de techo1 (nunca se mira el
        # futuro del propio patron), dentro de la tolerancia de nivel.
        toques_previos = sum(
            1 for t in todos_techos
            if inicio_ventana <= t < c.idx_techo1 and abs(close[t] - nivel) / nivel * 100 <= TOLERANCIA_NIVEL_PCT
        )
        minimo_intermedio = df["close"].iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + vcp.DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_techo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf < minimo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        filas.append({
            "idx_techo2": c.idx_techo2, "idx_confirmacion": idx_confirmacion,
            "toques_previos": toques_previos, "zona_testeada": toques_previos >= 1,
        })
    return filas


def _resumen_segmento(df: pd.DataFrame, filas: list[dict], desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    filas_planas = [(f["idx_techo2"], f["idx_confirmacion"]) for f in filas]
    return vcp._resumen(df, filas_planas, desde, hasta, exito_es_subida=False)["con_confirmacion"]


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_zona_resistencia_techo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_zona_resistencia_techo_btc")

    resultados_techo = []
    for pesos in vcp.PESOS_TECHO:
        filas = vcp._entradas_confirmadas_techo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
        resultados_techo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_techo)["pesos"]
    print(f"Pesos congelados: {mejor_pesos}\n")

    cortes = [
        ("ETH 2017-2021 (nunca usado en el ajuste)", df_eth, df_eth["open_time"].min(), vcp.CORTE),
        ("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN),
        ("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN),
        ("BTC completo (moneda nunca vista)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN),
    ]

    for nombre, df, desde, hasta in cortes:
        print(f"=== {nombre} ===")
        filas = _candidatos_confirmados_con_zona(df, mejor_pesos)
        testeada = [f for f in filas if f["zona_testeada"]]
        fresca = [f for f in filas if not f["zona_testeada"]]
        r_test = _resumen_segmento(df, testeada, desde, hasta)
        r_fresca = _resumen_segmento(df, fresca, desde, hasta)
        print(f"  zona testeada (1+ toque previo en {DIAS_VENTANA_HISTORICA}d): {json.dumps(r_test, default=str)}")
        print(f"  zona fresca (sin toques previos): {json.dumps(r_fresca, default=str)}")
        print()
