"""
Idea del usuario (12-sept-2026), distinta de `factor_subida_previa_techo.py`
(que ya se descarto por no replicar fuera del tramo de ajuste): no es solo
CUANTO subio el precio antes del primer pico, sino a que VELOCIDAD --
misma subida en 5 dias que en 50 dias es una situacion de mercado muy
distinta (una es un impulso brusco, la otra una subida lenta y sostenida).

Definicion continua: se busca el minimo local mas reciente antes de
techo1 (usando una ventana de busqueda de retroceso), y se mide:
  magnitud_pct = subida % desde ese minimo hasta techo1
  dias         = dias que tardo esa subida
  velocidad_pct_dia = magnitud_pct / dias

Aplicando la leccion de hoy (segmentar primero por regimen, no mezclar
todos los casos): se prueba DENTRO del grupo ya validado (regimen bajista
+ nivel repetido) ademas de en todos los candidatos, en los mismos 4
cortes de siempre.
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
PESOS_FORMA = (0.35, 0.25, 0.1, 0.3)
VENTANAS_BUSQUEDA_MINIMO = [20, 40, 60]  # hasta donde mirar hacia atras para encontrar el minimo


def _candidatos_completos(df: pd.DataFrame, pesos: tuple) -> list:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    ordenados = sorted(candidatos, key=lambda c: c.idx_techo2)
    niveles_previos = []
    filas = []
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
        filas.append({"c": c, "debajo_y_cayendo": debajo_y_cayendo, "patron_previo": patron_previo})
    return filas


def _velocidad_subida(df: pd.DataFrame, idx_techo1: int, ventana: int) -> tuple[float, int] | None:
    close = df["close"].to_numpy()
    inicio = max(0, idx_techo1 - ventana)
    tramo = close[inicio: idx_techo1 + 1]
    if len(tramo) < 3:
        return None
    idx_min_rel = int(np.argmin(tramo))
    idx_min = inicio + idx_min_rel
    dias = idx_techo1 - idx_min
    if dias < 2:
        return None
    precio_min = close[idx_min]
    if precio_min <= 0:
        return None
    magnitud_pct = (close[idx_techo1] - precio_min) / precio_min * 100
    return magnitud_pct, dias


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _analizar(nombre: str, df: pd.DataFrame, desde, hasta, solo_validados: bool):
    print(f"=== {nombre} ({'grupo validado' if solo_validados else 'todos'}) ===")
    fechas = df["open_time"]
    filas = _candidatos_completos(df, PESOS_FORMA)

    for ventana in VENTANAS_BUSQUEDA_MINIMO:
        velocidades, magnitudes, retornos = [], [], []
        for f in filas:
            c = f["c"]
            if solo_validados and not (f["debajo_y_cayendo"] and f["patron_previo"]):
                continue
            fecha2 = fechas.iloc[c.idx_techo2]
            if fecha2 < desde or fecha2 >= hasta:
                continue
            vel_info = _velocidad_subida(df, c.idx_techo1, ventana)
            if vel_info is None:
                continue
            magnitud_pct, dias = vel_info
            r = _retorno_directo(df, c.idx_techo2)
            if r is None:
                continue
            velocidades.append(magnitud_pct / dias)
            magnitudes.append(magnitud_pct)
            retornos.append(r)

        if len(velocidades) < 6:
            print(f"  ventana busqueda={ventana}d: muestra insuficiente (n={len(velocidades)})")
            continue
        vel_arr, ret_arr = np.array(velocidades), np.array(retornos)
        rho, p = spearmanr(vel_arr, ret_arr)
        mediana = np.median(vel_arr)
        lenta = ret_arr[vel_arr <= mediana]
        rapida = ret_arr[vel_arr > mediana]
        print(f"  ventana busqueda={ventana}d (n={len(velocidades)}): rho={rho:.3f} p={p:.3f} | subida LENTA->retorno {lenta.mean():.2f}% | subida RAPIDA->retorno {rapida.mean():.2f}%")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_velocidad_subida_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_velocidad_subida_btc")

    for solo_validados in (True, False):
        _analizar("ETH 2017-2021", df_eth, df_eth["open_time"].min(), vcp.CORTE, solo_validados)
        _analizar("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, solo_validados)
        _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, solo_validados)
        _analizar("BTC (nunca visto)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, solo_validados)
