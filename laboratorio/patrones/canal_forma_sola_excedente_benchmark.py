"""15-sept-2026: pregunta del usuario que reencuadra todo lo probado hasta
ahora sobre canal -- "confirmado/no confirmado" solo se sabe DIAS DESPUES
de que el canal termine (hay que esperar a ver si el precio rompe la
proyeccion). Para decidir si apostar por un canal EN EL MOMENTO en que se
detecta (idx_pico2), lo unico que se conoce es `probabilidad_forma`
(Capa 1) y el contexto (regimen, dist_ath). Nunca se probo si la forma
SOLA, sin esperar confirmacion, ya predice algo -- solo se probo
confirmado-vs-no (util para entender si el patron tiene validez real,
pero no necesariamente la regla de entrada correcta, porque para cuando
"confirma" ya paso buena parte del movimiento, ver motores/canal_descendente.py).

Esta prueba separa por probabilidad_forma alta/baja (mediana por moneda,
igual mecanismo que el resto de Capa 3 de hoy), midiendo el retorno
SIEMPRE desde idx_pico2 -- exactamente el momento en que se podria entrar,
sin esperar nada mas. Si la forma sola ya discrimina, esa es la regla de
entrada real (dia 0, igual que se establecio para doble techo/suelo). Si
no discrimina, "confirmado" seria util solo para VALIDAR el patron o para
una regla de entrada mas lenta (esperar y entrar tarde), no para decidir
al momento.
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


def _candidatos(df: pd.DataFrame, motor) -> list[dict]:
    """TODOS los candidatos (confirmado o no -- aqui no importa), con su
    probabilidad_forma y retorno desde idx_pico2 (el momento real de
    poder entrar)."""
    close = df["close"].to_numpy(); n = len(df)
    filas = []
    for c in motor.calcular(df):
        fin = c.idx_pico2 + DIAS_EXITO
        if fin >= n:
            continue
        retorno = (close[fin] - close[c.idx_pico2]) / close[c.idx_pico2] * 100
        filas.append({"prob": c.probabilidad_forma, "retorno": retorno})
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
    print(f"=== {nombre} -- forma sola (TODOS los candidatos, sin mirar confirmacion) ===")
    alta_todos, baja_todos = [], []
    for moneda, df in monedas.items():
        filas = _candidatos(df, motor)
        bm = benchmarks[moneda]
        if not filas:
            print(f"  {moneda}: sin candidatos"); continue
        mediana = float(np.median([f["prob"] for f in filas]))
        alta = [f["retorno"] - bm for f in filas if f["prob"] >= mediana]
        baja = [f["retorno"] - bm for f in filas if f["prob"] < mediana]
        alta_todos.extend(alta); baja_todos.extend(baja)
        print(f"  {moneda}: mediana_prob={mediana:.2f}  alta(n={len(alta)}) exceso={np.mean(alta):.2f}%   baja(n={len(baja)}) exceso={np.mean(baja):.2f}%")
    alta_todos, baja_todos = np.array(alta_todos), np.array(baja_todos)
    p = _monte_carlo_diferencia(alta_todos, baja_todos, rng)
    print(f"  CONJUNTO: alta(n={len(alta_todos)}) exceso={alta_todos.mean():.2f}%   baja(n={len(baja_todos)}) exceso={baja_todos.mean():.2f}%   p(diferencia)={p:.4f}")
    print()


if __name__ == "__main__":
    print("Cargando 5 monedas (ETH/BTC diario, XRP/SOL/BNB resampleadas de 4h)...\n")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_forma_sola_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_forma_sola_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }
    benchmarks = {n: _benchmark_incondicional(df) for n, df in monedas.items()}
    print("Benchmarks incondicionales por moneda:", {k: round(v, 2) for k, v in benchmarks.items()}, "\n")

    rng = np.random.default_rng(20260915)
    _reporte("CANAL ASCENDENTE", canal_ascendente, monedas, benchmarks, rng)
    _reporte("CANAL DESCENDENTE", canal_descendente, monedas, benchmarks, rng)
