"""15-sept-2026: idea del usuario tras el fracaso de canal_flexible.py y
caida_recuperacion.py como motores nuevos: no construir un detector de
canal desde cero -- COMPONER los dos motores YA GRADUADOS (doble techo,
doble suelo). Cero deteccion geometrica nueva -- solo un filtro de
contexto adicional sobre `motores/doble_techo.py` y `motores/doble_suelo.py`.

Primer intento (naive, DESCARTADO): "hubo un candidato del tipo contrario
en los ultimos N dias" -- no discrimina nada, porque techo/suelo disparan
tan seguido (~1 candidato cada 10 dias en ETH) que con N>=20 el grupo
"sin" se queda vacio (n=0). No era un filtro real.

Segundo intento (este script): la firma real de un canal horizontal no es
"algo contrario paso cerca", es que EL PROPIO NIVEL SE REPITE (mismo
techo, mismo suelo, una y otra vez) CON UN CRUCE REAL entre medio -- si el
nivel se repite pero nunca hubo un candidato del tipo contrario entre las
dos repeticiones, es una resistencia/soporte que aguanta sin rebote
confirmado en medio, no un canal. Se reusa `TOLERANCIA_NIVEL_PATRON_PREVIO_PCT`
y `GAP_MINIMO_VELAS_NIVEL_PREVIO` (ya validados en motores/doble_techo.py)
para "mismo nivel", sin inventar una tolerancia nueva.

Metodologia: exceso sobre benchmark incondicional; seleccion SOLO en
ETH-ajuste (aqui no hay pesos que barrer, solo el pool de candidatos
crece o no segun el filtro -- no hay grid que congelar, se reporta
directo); confirmacion sin tocar nada en ETH-tiempo y BTC completo.
Retorno medido desde el propio idx_techo2/idx_fondo2 -- igual que
`validacion_capa3_excedente_benchmark.py`.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from motores.doble_techo import GAP_MINIMO_VELAS_NIVEL_PREVIO as GAP_MINIMO_VELAS
from motores.doble_techo import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
from motores import doble_suelo, doble_techo

DIAS_EXITO = vcp.DIAS_EXITO


def _benchmark_incondicional(df: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp) -> float:
    fechas = df["open_time"]; close = df["close"].to_numpy(); n = len(close)
    rs = [(close[i + DIAS_EXITO] - close[i]) / close[i] * 100 for i in range(n)
          if desde <= fechas.iloc[i] < hasta and i + DIAS_EXITO < n]
    return float(np.mean(rs)) if rs else 0.0


def _candidatos_con_nivel(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    close = df["close"].to_numpy()
    n = len(df)
    techos = sorted(doble_techo.calcular(df), key=lambda r: r.candidato.idx_techo2)
    suelos = sorted(doble_suelo.calcular(df), key=lambda r: r.candidato.idx_fondo2)

    filas_t, filas_s = [], []
    for r in techos:
        c = r.candidato
        idx2 = c.idx_techo2
        if idx2 + DIAS_EXITO >= n:
            continue
        nivel = (close[c.idx_techo1] + close[c.idx_techo2]) / 2
        retorno = (close[idx2 + DIAS_EXITO] - close[idx2]) / close[idx2] * 100
        filas_t.append({"idx2": idx2, "nivel": nivel, "retorno": retorno})
    for r in suelos:
        c = r.candidato
        idx2 = c.idx_fondo2
        if idx2 + DIAS_EXITO >= n:
            continue
        nivel = (close[c.idx_fondo1] + close[c.idx_fondo2]) / 2
        retorno = (close[idx2 + DIAS_EXITO] - close[idx2]) / close[idx2] * 100
        filas_s.append({"idx2": idx2, "nivel": nivel, "retorno": retorno})
    return filas_t, filas_s


def _es_canal_confirmado(idx2: int, nivel: int, filas_mismo_tipo: list[dict], filas_tipo_contrario: list[dict]) -> bool:
    """Canal = el propio nivel ya se repitio antes (causal, solo mirando
    atras) Y hubo al menos un candidato del tipo CONTRARIO entre esa
    repeticion anterior y la actual (el "cruce" real, no solo dos techos
    seguidos sin rebote en medio)."""
    previos_mismo_nivel = [
        f["idx2"] for f in filas_mismo_tipo
        if f["idx2"] < idx2 - GAP_MINIMO_VELAS and abs(f["nivel"] - nivel) / nivel * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
    ]
    if not previos_mismo_nivel:
        return False
    idx_nivel_previo = max(previos_mismo_nivel)  # el mas reciente de los que repiten nivel
    return any(idx_nivel_previo < f["idx2"] < idx2 for f in filas_tipo_contrario)


def _stats_exceso(retornos: list[float], bm: float) -> dict:
    if not retornos:
        return {"n": 0, "exceso_medio_pct": None}
    arr = np.array(retornos) - bm
    return {"n": len(arr), "exceso_medio_pct": round(float(arr.mean()), 2)}


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_via_alternancia_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_via_alternancia_btc")

    bm_ajuste = _benchmark_incondicional(df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN)
    bm_tiempo = _benchmark_incondicional(df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    bm_btc = _benchmark_incondicional(df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)

    techos_eth, suelos_eth = _candidatos_con_nivel(df_eth)
    techos_btc, suelos_btc = _candidatos_con_nivel(df_btc)
    fechas_eth = df_eth["open_time"]; fechas_btc = df_btc["open_time"]

    def reporte(nombre, filas, desde, hasta, fechas, filas_contrario_completo, bm):
        idx_en_tramo = {f["idx2"] for f in filas if desde <= fechas.iloc[f["idx2"]] < hasta}
        con_tr = [f["retorno"] for f in filas if f["idx2"] in idx_en_tramo and _es_canal_confirmado(f["idx2"], f["nivel"], filas, filas_contrario_completo)]
        sin_tr = [f["retorno"] for f in filas if f["idx2"] in idx_en_tramo and not _es_canal_confirmado(f["idx2"], f["nivel"], filas, filas_contrario_completo)]
        print(f"{nombre}: con_canal={_stats_exceso(con_tr, bm)}  sin_canal={_stats_exceso(sin_tr, bm)}")

    print(f"Benchmarks: ajuste={bm_ajuste:.2f}% tiempo={bm_tiempo:.2f}% btc={bm_btc:.2f}%\n")

    print("=== ETH-ajuste (2021-2023) ===")
    reporte("TECHO", techos_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, fechas_eth, suelos_eth, bm_ajuste)
    reporte("SUELO", suelos_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, fechas_eth, techos_eth, bm_ajuste)

    print("\n=== CONFIRMACION 1: ETH-tiempo (2023-2025, nunca visto) ===")
    reporte("TECHO", techos_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, fechas_eth, suelos_eth, bm_tiempo)
    reporte("SUELO", suelos_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, fechas_eth, techos_eth, bm_tiempo)

    print("\n=== CONFIRMACION 2: BTC completo (nunca visto) ===")
    reporte("TECHO", techos_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, fechas_btc, suelos_btc, bm_btc)
    reporte("SUELO", suelos_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, fechas_btc, techos_btc, bm_btc)
