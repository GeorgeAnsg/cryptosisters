"""15-sept-2026: el usuario dudo, con razon, de la definicion de
"confirmado" en canal (mezcla "did revertir" con "did seguir sin
acelerar" en un solo "no confirmado"). El hallazgo de cercania al ATH
(canal_capa3_contexto.py) se probo SOLO sobre el subconjunto "confirmado"
-- antes de aceptarlo, se comprueba aqui si aguanta con una definicion de
exito mucho mas simple y sin ambiguedad: el retorno desde el propio pico2
(no desde la confirmacion de ruptura), sobre TODOS los candidatos
detectados, no solo los que confirman. Si "cerca del ATH" sigue
discriminando aqui, es una señal real independiente de como se defina
"confirmado". Si desaparece, la señal de antes dependia del artefacto de
definicion.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json

import numpy as np
import pandas as pd

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.canal_flexible import detectar_ascendente
from laboratorio.patrones.validacion_cruzada_pesos import CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, DIAS_EXITO
from motores import regimen_mercado

INICIO_AMPLIO = pd.Timestamp("2000-01-01", tz="UTC")
PESOS_SUBE = (0.55, 0.1, 0.15, 0.1, 0.1)
UMBRAL_ATH_GRID = [20, 30, 40, 50, 60, 70]


def _benchmark(df, desde, hasta):
    fechas = df["open_time"]; close = df["close"].to_numpy(); n = len(df)
    rs = [(close[i+DIAS_EXITO]-close[i])/close[i]*100 for i in range(n)
          if desde <= fechas.iloc[i] < hasta and i+DIAS_EXITO < n]
    return float(np.mean(rs)) if rs else 0.0


def _candidatos_simple(df, desde, hasta):
    """Retorno medido DESDE EL PROPIO idx_pico2 -- sin ninguna nocion de
    'confirmacion de ruptura'. TODOS los candidatos entran, no solo los
    que rompen la proyeccion."""
    fechas = df["open_time"]
    close = df["close"].to_numpy()
    sma200 = df["close"].rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    n = len(df)

    cands = detectar_ascendente(df, peso_pendiente=PESOS_SUBE[0], peso_paralelismo=PESOS_SUBE[1],
                                 peso_ancho=PESOS_SUBE[2], peso_consistencia=PESOS_SUBE[3], peso_contencion=PESOS_SUBE[4])
    filas = []
    for c in cands:
        fecha2 = fechas.iloc[c.idx_pico2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        if c.idx_pico2 + DIAS_EXITO >= n:
            continue
        retorno = (close[c.idx_pico2 + DIAS_EXITO] - c.precio_pico2) / c.precio_pico2 * 100
        dist_ath_pct = (ath_hasta[c.idx_pico2] - c.precio_pico2) / ath_hasta[c.idx_pico2] * 100
        filas.append({"idx_pico2": c.idx_pico2, "retorno": retorno, "dist_ath_pct": float(dist_ath_pct)})
    return filas


def _exceso_bajo_umbral(filas, bm, umbral, n_min=1):
    grupo = [f for f in filas if f["dist_ath_pct"] < umbral]
    resto = [f for f in filas if f["dist_ath_pct"] >= umbral]
    if len(grupo) < n_min:
        return None
    arr = np.array([f["retorno"] for f in grupo]) - bm
    arr_resto = np.array([f["retorno"] for f in resto]) - bm if resto else None
    return {
        "n_cerca": len(arr), "exceso_cerca_pct": round(float(arr.mean()), 2),
        "n_lejos": len(arr_resto) if arr_resto is not None else 0,
        "exceso_lejos_pct": round(float(arr_resto.mean()), 2) if arr_resto is not None and len(arr_resto) else None,
    }


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_ath_definicion_simple")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_ath_definicion_simple")

    bm_ajuste = _benchmark(df_eth, INICIO_AMPLIO, CORTE_AJUSTE_FIN)
    bm_tiempo = _benchmark(df_eth, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN)
    bm_btc = _benchmark(df_btc, INICIO_AMPLIO, CORTE_DESARROLLO_FIN)

    filas_ajuste = _candidatos_simple(df_eth, INICIO_AMPLIO, CORTE_AJUSTE_FIN)
    filas_tiempo = _candidatos_simple(df_eth, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN)
    filas_btc = _candidatos_simple(df_btc, INICIO_AMPLIO, CORTE_DESARROLLO_FIN)

    print(f"Total candidatos (TODOS, no solo confirmados): ajuste={len(filas_ajuste)} tiempo={len(filas_tiempo)} btc={len(filas_btc)}\n")

    for umbral in UMBRAL_ATH_GRID:
        r_ajuste = _exceso_bajo_umbral(filas_ajuste, bm_ajuste, umbral)
        r_tiempo = _exceso_bajo_umbral(filas_tiempo, bm_tiempo, umbral)
        r_btc = _exceso_bajo_umbral(filas_btc, bm_btc, umbral)
        print(json.dumps({"umbral_ath_pct": umbral, "ajuste": r_ajuste, "tiempo": r_tiempo, "btc": r_btc}))
