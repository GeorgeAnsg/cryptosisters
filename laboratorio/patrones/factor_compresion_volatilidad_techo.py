"""
Idea nueva (12-sept-2026): antes de un giro fuerte, a veces el mercado se
mueve con velas cada vez mas pequenas (duda, volumen bajo, indecision)
justo antes de formar el segundo pico. Se mide como la RATIO entre la
volatilidad de los ultimos K dias antes de techo2 y la volatilidad de los
K dias anteriores a esos -- si esa ratio es baja, la volatilidad se
comprimio justo antes del pico.

Definicion continua: ATR%(K dias justo antes de techo2) / ATR%(K dias
anteriores a esos) -- rango de K, nunca un solo numero.
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
VENTANAS_K = [5, 10, 15]


def _atr_pct_simple(df: pd.DataFrame, idx_fin: int, k: int) -> float | None:
    """ATR%% simplificado: media del rango (high-low)/close en los k dias
    hasta idx_fin (excluido)."""
    if idx_fin - k < 0:
        return None
    tramo = df.iloc[idx_fin - k: idx_fin]
    rango_pct = (tramo["high"] - tramo["low"]) / tramo["close"] * 100
    return float(rango_pct.mean())


def _candidatos(df: pd.DataFrame, pesos: tuple) -> list:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    return doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )


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
    candidatos = _candidatos(df, PESOS_FORMA)

    for k in VENTANAS_K:
        ratios, retornos = [], []
        for c in candidatos:
            fecha2 = fechas.iloc[c.idx_techo2]
            if fecha2 < desde or fecha2 >= hasta:
                continue
            atr_reciente = _atr_pct_simple(df, c.idx_techo2 + 1, k)
            atr_previo = _atr_pct_simple(df, c.idx_techo2 + 1 - k, k)
            if atr_reciente is None or atr_previo is None or atr_previo == 0:
                continue
            r = _retorno_directo(df, c.idx_techo2)
            if r is None:
                continue
            ratios.append(atr_reciente / atr_previo)
            retornos.append(r)

        if len(ratios) < 5:
            print(f"  K={k}d: muestra insuficiente (n={len(ratios)})")
            continue
        ratios_arr, retornos_arr = np.array(ratios), np.array(retornos)
        rho, p = spearmanr(ratios_arr, retornos_arr)
        mediana = np.median(ratios_arr)
        comprimido = retornos_arr[ratios_arr <= mediana]
        expandido = retornos_arr[ratios_arr > mediana]
        print(f"  K={k}d (n={len(ratios)}): rho={rho:.3f} p={p:.3f} | volatilidad COMPRIMIDA->retorno {comprimido.mean():.2f}% (n={len(comprimido)}) | EXPANDIDA->retorno {expandido.mean():.2f}% (n={len(expandido)})")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_compresion_vol_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_compresion_vol_btc")

    _analizar("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN)
    _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    _analizar("BTC completo (nunca visto)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
