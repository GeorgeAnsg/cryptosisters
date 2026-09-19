"""
Hipotesis del usuario (11-sept-2026): un doble techo "real" deberia llegar
al segundo techo con MENOS momentum (RSI) y MENOS volumen que el primero
-- divergencia bajista clasica. Si es asi, promediar TODOS los dobles
techo juntos (con y sin esa divergencia) puede estar tapando una señal real
detras de un promedio sin edge (ver Fase B ya medida: ~20-41% acierto,
p-valores 0.42-0.98, indistinguible del azar).

Este script NO cambia la deteccion ni la puntuacion -- usa los pesos ya
congelados en `validacion_cruzada_pesos.py` (ajustados SOLO en ETH-ajuste)
y el mismo mecanismo de confirmacion (rotura del valle intermedio en
DIAS_CONFIRMACION dias). Lo unico nuevo es que SEGMENTA los candidatos
confirmados en dos grupos, usando los campos `divergencia_rsi` y
`ratio_volumen_techos` que ahora registra `doble_techo_flexible.py` (no
usados en la puntuacion, solo medidos):

- "divergencia": rsi_techo2 < rsi_techo1 (momentum mas debil en el 2o techo)
- "sin_divergencia": el resto

Se reporta por separado en los 3 sitios ya usados en Fase B (ETH-ajuste,
ETH-tiempo nunca visto, BTC completo nunca visto) -- misma disciplina de
validacion cruzada, aplicada ahora a la segmentacion en vez de a los pesos.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible


def _candidatos_confirmados_con_divergencia(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    n = len(df)
    filas = []
    for c in candidatos:
        minimo_intermedio = df["close"].iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + vcp.DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_techo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf < minimo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        filas.append({
            "idx_techo2": c.idx_techo2, "idx_confirmacion": idx_confirmacion,
            "divergencia_rsi": c.divergencia_rsi, "ratio_volumen_techos": c.ratio_volumen_techos,
        })
    return filas


def _segmentar(filas: list[dict]) -> dict[str, list[dict]]:
    """Divide en 4 grupos: divergencia bajista completa (RSI Y volumen mas
    debiles en techo2), solo RSI, solo volumen, y ninguna divergencia."""
    grupos = {"divergencia_completa": [], "solo_rsi": [], "solo_volumen": [], "sin_divergencia": []}
    for f in filas:
        rsi_debil = f["divergencia_rsi"] is not None and f["divergencia_rsi"] < 0
        vol_debil = f["ratio_volumen_techos"] is not None and f["ratio_volumen_techos"] < 1.0
        if rsi_debil and vol_debil:
            grupos["divergencia_completa"].append(f)
        elif rsi_debil:
            grupos["solo_rsi"].append(f)
        elif vol_debil:
            grupos["solo_volumen"].append(f)
        else:
            grupos["sin_divergencia"].append(f)
    return grupos


def _resumen_segmento(df: pd.DataFrame, filas: list[dict], desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    filas_planas = [(f["idx_techo2"], f["idx_confirmacion"]) for f in filas]
    return vcp._resumen(df, filas_planas, desde, hasta, exito_es_subida=False)["con_confirmacion"]


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_divergencia_techo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_divergencia_techo_btc")

    # Pesos: reusar la busqueda ya hecha en validacion_cruzada_pesos.py (solo ETH-ajuste)
    resultados_techo = []
    for pesos in vcp.PESOS_TECHO:
        filas = vcp._entradas_confirmadas_techo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
        resultados_techo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_techo)["pesos"]
    print(f"Pesos congelados (elegidos SOLO en ETH-ajuste, sin cambios por este analisis): {mejor_pesos}\n")

    cortes = [
        ("ETH ajuste (2021-2023, mismo tramo de la busqueda)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN),
        ("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN),
        ("BTC completo (moneda nunca vista)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN),
    ]

    for nombre, df, desde, hasta in cortes:
        print(f"=== {nombre} ===")
        filas = _candidatos_confirmados_con_divergencia(df, mejor_pesos)
        grupos = _segmentar(filas)
        for etiqueta, grupo in grupos.items():
            r = _resumen_segmento(df, grupo, desde, hasta)
            print(f"  {etiqueta}: {json.dumps(r, default=str)}")
        print()
