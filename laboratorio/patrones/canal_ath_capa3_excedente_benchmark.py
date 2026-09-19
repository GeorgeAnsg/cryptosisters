"""15-sept-2026: segunda idea de Capa 3 para los dos motores de canal ya
graduados, propuesta por el usuario -- distancia al ATH. Razonamiento:
en un canal ascendente cada punto sucesivo esta mas cerca del ATH (menos
recorrido por delante); uno que arranca LEJOS del ATH deberia tener mas
margen para seguir subiendo que uno ya pegado al maximo historico. Mismo
mecanismo ya usado para doble techo/suelo (`dist_ath`, con split por
mediana), aplicado aqui sobre el grupo `confirmado=True` de canal
ascendente/descendente (donde vive la ventaja ya demostrada). Retorno
medido SIEMPRE desde idx_pico2, igual que el resto de pruebas de canal de
hoy.

Metodologia identica: exceso sobre benchmark incondicional, 5 monedas,
split por mediana de dist_ath calculada POR MONEDA (no una mediana global
-- monedas distintas tienen historiales de ATH distintos), Monte Carlo
para saber si la diferencia cerca/lejos es real.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from datos.cargar import cargar_ohlcv
from laboratorio.datos_lab import cargar_ohlcv_lab
from motores import canal_ascendente, canal_descendente

DIAS_EXITO = vcp.DIAS_EXITO
N_SIMULACIONES = 5000


def _resample_diario(par: str) -> pd.DataFrame:
    df = cargar_ohlcv(par, "4h")
    return df.set_index("open_time").resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna().reset_index()


def _benchmark_incondicional(df: pd.DataFrame) -> float:
    close = df["close"].to_numpy(); n = len(close)
    rs = [(close[i + DIAS_EXITO] - close[i]) / close[i] * 100 for i in range(n) if i + DIAS_EXITO < n]
    return float(np.mean(rs)) if rs else 0.0


def _candidatos_confirmados_con_ath(df: pd.DataFrame, motor) -> list[dict]:
    close = df["close"].to_numpy(); n = len(df)
    ath_hasta = np.maximum.accumulate(close)
    filas = []
    for c in motor.calcular(df):
        if not c.confirmado:
            continue
        fin = c.idx_pico2 + DIAS_EXITO
        if fin >= n:
            continue
        dist_ath = (ath_hasta[c.idx_pico2] - close[c.idx_pico2]) / ath_hasta[c.idx_pico2] * 100
        retorno = (close[fin] - close[c.idx_pico2]) / close[c.idx_pico2] * 100
        filas.append({"dist_ath": dist_ath, "retorno": retorno})
    return filas


def _monte_carlo_diferencia(a: np.ndarray, b: np.ndarray, rng: np.random.default_rng) -> float:
    diff_obs = a.mean() - b.mean()
    todos = np.concatenate([a, b])
    n_a = len(a)
    diffs = np.empty(N_SIMULACIONES)
    for i in range(N_SIMULACIONES):
        perm = rng.permutation(todos)
        diffs[i] = perm[:n_a].mean() - perm[n_a:].mean()
    if diff_obs < 0:
        return float((diffs <= diff_obs).mean())
    return float((diffs >= diff_obs).mean())


def _reporte(nombre: str, motor, monedas: dict[str, pd.DataFrame], benchmarks: dict[str, float], rng) -> None:
    print(f"=== {nombre} (solo confirmado=True) ===")
    cerca_todos, lejos_todos = [], []
    for moneda, df in monedas.items():
        filas = _candidatos_confirmados_con_ath(df, motor)
        bm = benchmarks[moneda]
        if not filas:
            print(f"  {moneda}: sin candidatos"); continue
        mediana = float(np.median([f["dist_ath"] for f in filas]))
        cerca = [f["retorno"] - bm for f in filas if f["dist_ath"] <= mediana]
        lejos = [f["retorno"] - bm for f in filas if f["dist_ath"] > mediana]
        cerca_todos.extend(cerca); lejos_todos.extend(lejos)
        print(f"  {moneda}: mediana_dist_ath={mediana:.1f}%  cerca(n={len(cerca)}) exceso={np.mean(cerca):.2f}%   lejos(n={len(lejos)}) exceso={np.mean(lejos):.2f}%")
    cerca_todos, lejos_todos = np.array(cerca_todos), np.array(lejos_todos)
    p = _monte_carlo_diferencia(cerca_todos, lejos_todos, rng)
    print(f"  CONJUNTO: cerca(n={len(cerca_todos)}) exceso={cerca_todos.mean():.2f}%   lejos(n={len(lejos_todos)}) exceso={lejos_todos.mean():.2f}%   p(diferencia)={p:.4f}")
    print()


if __name__ == "__main__":
    print("Cargando 5 monedas (ETH/BTC diario, XRP/SOL/BNB resampleadas de 4h)...\n")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_ath_capa3_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_ath_capa3_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }
    benchmarks = {n: _benchmark_incondicional(df) for n, df in monedas.items()}
    print("Benchmarks incondicionales por moneda:", {k: round(v, 2) for k, v in benchmarks.items()}, "\n")

    rng = np.random.default_rng(20260915)
    _reporte("CANAL ASCENDENTE", canal_ascendente, monedas, benchmarks, rng)
    _reporte("CANAL DESCENDENTE", canal_descendente, monedas, benchmarks, rng)
