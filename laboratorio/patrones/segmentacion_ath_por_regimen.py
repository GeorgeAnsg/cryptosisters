"""
Correccion metodologica pedida por el usuario (12-sept-2026): un doble
techo en mercado ALCISTA (cerca de ATH, media 200 subiendo) y uno en
mercado BAJISTA (regimen debil, ya validado) son dos "animales" distintos
-- no tiene sentido buscar un factor que funcione igual para todos.

Se separan los candidatos en dos grupos SEGUN EL REGIMEN (no un factor
nuevo, el que ya teniamos: precio vs media200 y pendiente de la media) y
se mira, DENTRO DE CADA GRUPO por separado, si la proximidad al ATH
predice mejor el resultado.

Hipotesis a comprobar: la proximidad al ATH deberia importar en el grupo
ALCISTA (donde tiene sentido conceptual -- cerca de maximos, agotamiento
de la subida) y no en el grupo BAJISTA (donde ya casi nunca se esta cerca
del ATH de todas formas).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible

DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
PESOS_FORMA = (0.35, 0.25, 0.1, 0.3)


def _candidatos_con_regimen_y_ath(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    filas = []
    for c in candidatos:
        media = sma200.iloc[c.idx_techo2]
        media_hace_20 = sma200.iloc[c.idx_techo2 - 20] if c.idx_techo2 >= 20 else None
        debajo = bool(media == media and close[c.idx_techo2] < media)
        cayendo = bool(media == media and media_hace_20 is not None and media_hace_20 == media_hace_20 and media < media_hace_20)
        debajo_y_cayendo = debajo and cayendo
        encima_y_subiendo = bool(
            media == media and close[c.idx_techo2] > media
            and media_hace_20 is not None and media_hace_20 == media_hace_20 and media > media_hace_20
        )
        dist_ath = (ath_hasta[c.idx_techo2] - close[c.idx_techo2]) / ath_hasta[c.idx_techo2] * 100
        filas.append({
            "idx_techo2": c.idx_techo2, "debajo_y_cayendo": debajo_y_cayendo,
            "encima_y_subiendo": encima_y_subiendo, "dist_ath": dist_ath,
        })
    return filas


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _analizar(nombre: str, df: pd.DataFrame, desde, hasta):
    print(f"=== {nombre} ===")
    fechas = df["open_time"]
    filas = _candidatos_con_regimen_y_ath(df, PESOS_FORMA)

    grupos = {
        "TODOS (sin segmentar, referencia)": lambda f: True,
        "regimen ALCISTA (encima+subiendo media200)": lambda f: f["encima_y_subiendo"],
        "regimen BAJISTA (debajo+cayendo media200)": lambda f: f["debajo_y_cayendo"],
        "regimen MIXTO/neutro (ni uno ni otro)": lambda f: not f["encima_y_subiendo"] and not f["debajo_y_cayendo"],
    }

    for nombre_grupo, filtro in grupos.items():
        dist, ret = [], []
        for f in filas:
            fecha2 = fechas.iloc[f["idx_techo2"]]
            if fecha2 < desde or fecha2 >= hasta or not filtro(f):
                continue
            r = _retorno_directo(df, f["idx_techo2"])
            if r is None:
                continue
            dist.append(f["dist_ath"])
            ret.append(r)
        if len(dist) < 8:
            print(f"  {nombre_grupo}: muestra insuficiente (n={len(dist)})")
            continue
        dist_arr, ret_arr = np.array(dist), np.array(ret)
        rho, p = spearmanr(dist_arr, ret_arr)
        mediana = np.median(dist_arr)
        cerca = ret_arr[dist_arr <= mediana]
        lejos = ret_arr[dist_arr > mediana]
        print(f"  {nombre_grupo} (n={len(dist)}): rho={rho:.3f} p={p:.3f} | cerca_ATH->retorno {cerca.mean():.2f}% | lejos_ATH->retorno {lejos.mean():.2f}%")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_ath_regimen_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_ath_regimen_btc")

    _analizar("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN)
    _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    _analizar("BTC completo (nunca visto)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    _analizar("ETH 2017-2021 (nunca usado en ajuste)", df_eth, df_eth["open_time"].min(), vcp.CORTE)
