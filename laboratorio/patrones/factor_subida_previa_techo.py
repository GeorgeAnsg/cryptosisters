"""
Idea nueva (12-sept-2026): no mirar solo la forma del doble techo en si,
sino CUANTO habia subido el mercado ANTES de llegar siquiera al primer
pico (techo1). Hipotesis: cuanto mayor y mas rapida la subida previa, mas
"cansado" esta el mercado y mas probable que el doble techo sea un techo
real, no ruido a mitad de una tendencia todavia fuerte.

Definicion continua (nunca un umbral fijo -- se prueba un RANGO de
ventanas hacia atras, regla del proyecto):
  subida_previa_pct(K) = (close[idx_techo1] - min(close[idx_techo1-K : idx_techo1])) / min(...) * 100

Se prueba primero SOLO en ETH-ajuste (disciplina de la memoria del
usuario: ajustar solo en ETH, congelar, confirmar sin tocar nada en
ETH-tiempo y BTC).
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
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT

DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
VENTANAS_DIAS = [10, 20, 30, 45, 60]
PESOS_FORMA = (0.35, 0.25, 0.1, 0.3)


def _candidatos_validados(df: pd.DataFrame, pesos: tuple) -> list:
    """Reutiliza el filtro ya validado (regimen debil + nivel repetido)."""
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    ordenados = sorted(candidatos, key=lambda c: c.idx_techo2)
    niveles_previos = []
    out = []
    for c in ordenados:
        media = sma200.iloc[c.idx_techo2]
        media_hace_20 = sma200.iloc[c.idx_techo2 - 20] if c.idx_techo2 >= 20 else None
        debajo = bool(media == media and close[c.idx_techo2] < media)
        cayendo = bool(media == media and media_hace_20 is not None and media_hace_20 == media_hace_20 and media < media_hace_20)
        debajo_y_cayendo = debajo and cayendo
        nivel_actual = (close[c.idx_techo1] + close[c.idx_techo2]) / 2
        patron_previo = any(
            idx2p < c.idx_techo1 - 3 and abs(nivp - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2p, nivp in niveles_previos
        )
        niveles_previos.append((c.idx_techo2, nivel_actual))
        out.append((c, debajo_y_cayendo and patron_previo))
    return out


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _analizar(nombre: str, df: pd.DataFrame, desde, hasta, solo_validados: bool):
    print(f"=== {nombre} ({'solo grupo validado' if solo_validados else 'todos los candidatos'}) ===")
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    candidatos_flag = _candidatos_validados(df, PESOS_FORMA)

    for K in VENTANAS_DIAS:
        subidas, retornos = [], []
        for c, valido in candidatos_flag:
            if solo_validados and not valido:
                continue
            fecha2 = fechas.iloc[c.idx_techo2]
            if fecha2 < desde or fecha2 >= hasta:
                continue
            if c.idx_techo1 < K:
                continue
            minimo = close[c.idx_techo1 - K: c.idx_techo1].min()
            if minimo <= 0:
                continue
            subida_pct = (close[c.idx_techo1] - minimo) / minimo * 100
            r = _retorno_directo(df, c.idx_techo2)
            if r is None:
                continue
            subidas.append(subida_pct)
            retornos.append(r)
        if len(subidas) < 5:
            print(f"  ventana {K}d: muestra insuficiente (n={len(subidas)})")
            continue
        subidas_arr, retornos_arr = np.array(subidas), np.array(retornos)
        rho, p = spearmanr(subidas_arr, retornos_arr)
        mediana = np.median(subidas_arr)
        bajo = retornos_arr[subidas_arr <= mediana]
        alto = retornos_arr[subidas_arr > mediana]
        print(f"  ventana {K}d (n={len(subidas)}): rho={rho:.3f} p={p:.3f} | subida baja->retorno {bajo.mean():.2f}% (n={len(bajo)}) | subida alta->retorno {alto.mean():.2f}% (n={len(alto)})")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_subida_previa_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_subida_previa_btc")

    for solo_validados in (False, True):
        _analizar("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, solo_validados)
        _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, solo_validados)
        _analizar("BTC completo (nunca visto)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, solo_validados)
