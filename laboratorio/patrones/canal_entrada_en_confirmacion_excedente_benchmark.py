"""15-sept-2026: correccion de enfoque tras la pregunta del usuario --
"forma sola" (dia 0, en cuanto se detecta el canal) NO tiene ventaja real
(ver canal_forma_sola_excedente_benchmark.py: ascendente pierde de media,
descendente sale al reves). La ventaja de hoy (con_confirmacion vs
sin_confirmacion) se midio con el retorno SIEMPRE desde idx_pico2 para
poder comparar los dos grupos de forma justa -- valido para saber "¿la
confirmacion aporta informacion?", pero NO es la regla de entrada real,
porque si vas a operar de verdad, entras el dia que confirma
(idx_confirmacion), no antes.

Esta prueba mide la regla de entrada REAL: entre los candidatos que SI
confirman, el retorno se cuenta desde `idx_confirmacion` hacia adelante
(el dia en que de verdad podrias apostar), no desde idx_pico2. Compara ese
resultado con el benchmark incondicional del mismo tramo -- si sigue
habiendo exceso positivo, "esperar a la confirmacion" es una regla de
entrada utilizable de verdad, no solo un hallazgo retrospectivo.
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


def _retornos_desde_confirmacion(df: pd.DataFrame, motor) -> list[float]:
    close = df["close"].to_numpy(); n = len(df)
    retornos = []
    for c in motor.calcular(df):
        if not c.confirmado:
            continue
        fin = c.idx_confirmacion + DIAS_EXITO
        if fin >= n:
            continue
        retornos.append((close[fin] - close[c.idx_confirmacion]) / close[c.idx_confirmacion] * 100)
    return retornos


def _monte_carlo_vs_cero(excesos: np.ndarray, rng: np.random.default_rng) -> float:
    """p-valor de que el exceso medio observado (ya positivo o negativo)
    se deba al azar -- baraja el signo de cada exceso individual."""
    obs = excesos.mean()
    n = len(excesos)
    sims = np.empty(N_SIMULACIONES)
    for i in range(N_SIMULACIONES):
        signos = rng.choice([-1, 1], size=n)
        sims[i] = (excesos * signos).mean()
    if obs < 0:
        return float((sims <= obs).mean())
    return float((sims >= obs).mean())


def _reporte(nombre: str, motor, monedas: dict[str, pd.DataFrame], benchmarks: dict[str, float], rng) -> None:
    print(f"=== {nombre} -- entrada REAL el dia que confirma, retorno desde idx_confirmacion ===")
    todos = []
    for moneda, df in monedas.items():
        rets = _retornos_desde_confirmacion(df, motor)
        bm = benchmarks[moneda]
        if not rets:
            print(f"  {moneda}: sin candidatos confirmados"); continue
        excesos = np.array(rets) - bm
        todos.extend(excesos.tolist())
        print(f"  {moneda}: n={len(excesos)} exceso={excesos.mean():.2f}%")
    todos = np.array(todos)
    p = _monte_carlo_vs_cero(todos, rng)
    print(f"  CONJUNTO: n={len(todos)} exceso={todos.mean():.2f}%   p(exceso != 0 por azar)={p:.4f}")
    print()


if __name__ == "__main__":
    print("Cargando 5 monedas (ETH/BTC diario, XRP/SOL/BNB resampleadas de 4h)...\n")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_entrada_confirmacion_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_entrada_confirmacion_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }
    benchmarks = {n: _benchmark_incondicional(df) for n, df in monedas.items()}
    print("Benchmarks incondicionales por moneda:", {k: round(v, 2) for k, v in benchmarks.items()}, "\n")

    rng = np.random.default_rng(20260915)
    _reporte("CANAL ASCENDENTE", canal_ascendente, monedas, benchmarks, rng)
    _reporte("CANAL DESCENDENTE", canal_descendente, monedas, benchmarks, rng)
