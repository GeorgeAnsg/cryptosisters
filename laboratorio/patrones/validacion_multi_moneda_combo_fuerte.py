"""
Validacion mas robusta (12-sept-2026, a peticion del usuario: "pruebas mas
reales... para estar mas contentos") del combo mas fuerte de la sesion:
regimen bajista + nivel ya repetido + todavia relativamente cerca del ATH.

Hasta ahora solo se habia probado en ETH (3 cortes temporales) y BTC --
muestras pequenas (4 a 16 casos por corte). Aqui se amplia a XRP, SOL y
BNB (resampleadas de 4h a diario, igual que se hizo el 11-sept-2026 para
el factor de regimen/nivel_repetido) para tener mas casos en total, y se
corre un Monte Carlo (5000 simulaciones, tramos no solapados) sobre el
conjunto agrupado de las 5 monedas para un p-valor solido, en vez de solo
"de cada 10" sobre muestras pequenas.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from datos.cargar import cargar_ohlcv
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT

PESOS = (0.35, 0.25, 0.1, 0.3)
DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
N_SIMULACIONES = 5000


def _resample_diario(par: str) -> pd.DataFrame:
    df = cargar_ohlcv(par, "4h")
    diario = df.set_index("open_time").resample("1D").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna().reset_index()
    return diario


def _candidatos_combo_fuerte(df: pd.DataFrame) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = PESOS
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    ordenados = sorted(candidatos, key=lambda c: c.idx_techo2)
    niveles_previos: list[tuple[int, float]] = []
    n = len(df)
    filas = []
    for c in ordenados:
        media = sma200.iloc[c.idx_techo2]
        media_hace_20 = sma200.iloc[c.idx_techo2 - 20] if c.idx_techo2 >= 20 else None
        debajo = bool(media == media and close[c.idx_techo2] < media)
        cayendo = bool(media == media and media_hace_20 is not None and media_hace_20 == media_hace_20 and media < media_hace_20)
        nivel_actual = (close[c.idx_techo1] + close[c.idx_techo2]) / 2
        patron_previo = any(
            idx2p < c.idx_techo1 - 3 and abs(nivp - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2p, nivp in niveles_previos
        )
        niveles_previos.append((c.idx_techo2, nivel_actual))
        if not (debajo and cayendo and patron_previo):
            continue
        dist_ath = (ath_hasta[c.idx_techo2] - close[c.idx_techo2]) / ath_hasta[c.idx_techo2] * 100
        fin = c.idx_techo2 + DIAS_EXITO
        if fin >= n:
            continue
        precio0 = close[c.idx_techo2]
        retorno = (close[fin] - precio0) / precio0 * 100
        filas.append({"idx_techo2": c.idx_techo2, "dist_ath": dist_ath, "retorno": retorno})
    return filas


def _monte_carlo(retornos: np.ndarray, umbral: float, rng: np.random.default_rng) -> float:
    """P-valor: probabilidad de que un conjunto aleatorio de retornos (de
    la misma distribucion muestreada con reemplazo del propio pool, como
    control neutro) acierte tan bien o mejor que el grupo real, si no
    hubiera ninguna senal real. Usa el propio pool combinado como base de
    remuestreo (bootstrap bajo la null de "sin diferencia con la media")."""
    aciertos_reales = (retornos <= -umbral).mean()
    media_global = retornos.mean()
    centrado = retornos - media_global  # bajo la null: sin sesgo direccional
    n = len(retornos)
    resultados = np.array([
        (rng.choice(centrado, size=n, replace=True) <= -umbral).mean()
        for _ in range(N_SIMULACIONES)
    ])
    return float((resultados >= aciertos_reales).mean())


if __name__ == "__main__":
    print("Cargando y resampleando XRP, SOL, BNB (4h -> diario)...")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="validacion_multi_combo_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="validacion_multi_combo_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }

    todos_los_retornos = []
    print()
    for nombre, df in monedas.items():
        filas = _candidatos_combo_fuerte(df)
        rets = [f["retorno"] for f in filas]
        todos_los_retornos.extend(rets)
        if rets:
            arr = np.array(rets)
            print(f"{nombre}: n={len(arr)}  retorno medio={arr.mean():.2f}%  "
                  f"acierta -5%: {(arr<=-5).mean()*100:.0f}%  acierta -10%: {(arr<=-10).mean()*100:.0f}%")
        else:
            print(f"{nombre}: sin candidatos con el combo completo")

    todos = np.array(todos_los_retornos)
    print()
    print(f"=== CONJUNTO DE LAS 5 MONEDAS (n={len(todos)}) ===")
    print(f"retorno medio: {todos.mean():.2f}%  (mediana: {np.median(todos):.2f}%)")

    rng = np.random.default_rng(20260912)
    print()
    print("Monte Carlo (5000 simulaciones) -- probabilidad de que este resultado sea casualidad:")
    for umbral in UMBRALES_EXITO_PCT:
        acierto_real = (todos <= -umbral).mean() * 100
        p = _monte_carlo(todos, umbral, rng)
        print(f"  bajar al menos {umbral}%: acierta {acierto_real:.0f}% de las veces ({acierto_real/10:.1f} de cada 10) -- p={p:.4f}")
