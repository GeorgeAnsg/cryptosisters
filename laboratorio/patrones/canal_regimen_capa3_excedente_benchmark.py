"""15-sept-2026: Capa 3 (contexto de mercado) para los dos motores de
canal ya graduados (`motores/canal_ascendente.py`, `canal_descendente.py`).
Mismo mecanismo ya validado para doble techo/suelo: regimen_mercado.py
(BAJISTA/ALCISTA/NEUTRO, clasificador compartido) se usa DENTRO del motor,
no como filtro externo (ver motores/README.md).

Se prueba solo sobre el grupo `confirmado=True` -- ahi es donde vive la
ventaja ya demostrada (ver canal_confirmacion_5monedas_montecarlo.py);
"confirmado=False" no tiene ventaja conocida y anadirle regimen encima no
tendria sentido todavia. Retorno medido SIEMPRE desde idx_pico2 (fix de
hoy, ver docstring de motores/canal_descendente.py).

Metodologia identica al resto del dia: exceso sobre benchmark
incondicional; seleccion SOLO en ETH-ajuste (2021-2023), congelar,
confirmar sin tocar nada en ETH-tiempo (2023-2025) y BTC completo.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from datos.cargar import cargar_ohlcv
from laboratorio.datos_lab import cargar_ohlcv_lab
from motores import canal_ascendente, canal_descendente, regimen_mercado
from motores.regimen_mercado import TipoRegimen

DIAS_EXITO = vcp.DIAS_EXITO


def _resample_diario(par: str) -> pd.DataFrame:
    df = cargar_ohlcv(par, "4h")
    return df.set_index("open_time").resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna().reset_index()


def _benchmark_incondicional(df: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp) -> float:
    fechas = df["open_time"]; close = df["close"].to_numpy(); n = len(close)
    rs = [(close[i + DIAS_EXITO] - close[i]) / close[i] * 100 for i in range(n)
          if desde <= fechas.iloc[i] < hasta and i + DIAS_EXITO < n]
    return float(np.mean(rs)) if rs else 0.0


def _candidatos_confirmados(df: pd.DataFrame, motor) -> list[dict]:
    close = df["close"].to_numpy(); n = len(df)
    sma200 = df["close"].rolling(200).mean()
    filas = []
    for c in motor.calcular(df):
        if not c.confirmado:
            continue
        fin = c.idx_pico2 + DIAS_EXITO
        if fin >= n:
            continue
        tipo, _score = regimen_mercado.clasificar(df, c.idx_pico2, sma200)
        retorno = (close[fin] - close[c.idx_pico2]) / close[c.idx_pico2] * 100
        filas.append({"idx2": c.idx_pico2, "tipo": tipo, "retorno": retorno})
    return filas


def _stats(retornos: list[float], bm: float) -> dict:
    if not retornos:
        return {"n": 0, "exceso_medio_pct": None}
    arr = np.array(retornos) - bm
    return {"n": len(arr), "exceso_medio_pct": round(float(arr.mean()), 2)}


N_SIMULACIONES = 5000


def _monte_carlo_diferencia(grupo: np.ndarray, resto: np.ndarray, rng: np.random.default_rng) -> float:
    diff_obs = grupo.mean() - resto.mean()
    todos = np.concatenate([grupo, resto])
    n_grupo = len(grupo)
    diffs = np.empty(N_SIMULACIONES)
    for i in range(N_SIMULACIONES):
        perm = rng.permutation(todos)
        diffs[i] = perm[:n_grupo].mean() - perm[n_grupo:].mean()
    if diff_obs < 0:
        return float((diffs <= diff_obs).mean())
    return float((diffs >= diff_obs).mean())


def _reporte(nombre: str, motor, monedas: dict[str, pd.DataFrame], benchmarks: dict[str, float], rng) -> None:
    print(f"=== {nombre} (solo confirmado=True, retorno desde idx_pico2) ===")
    por_tipo: dict[TipoRegimen, list[float]] = {t: [] for t in TipoRegimen}
    todos: list[float] = []
    for moneda, df in monedas.items():
        filas = _candidatos_confirmados(df, motor)
        bm = benchmarks[moneda]
        for f in filas:
            por_tipo[f["tipo"]].append(f["retorno"] - bm)
            todos.append(f["retorno"] - bm)
    for tipo in TipoRegimen:
        grupo = np.array(por_tipo[tipo])
        resto = np.array([r for t, rs in por_tipo.items() if t != tipo for r in rs])
        if len(grupo) >= 5 and len(resto) >= 5:
            p = _monte_carlo_diferencia(grupo, resto, rng)
            print(f"  {tipo}: n={len(grupo)} exceso={grupo.mean():.2f}%   (resto: n={len(resto)} exceso={resto.mean():.2f}%)   p(diferencia)={p:.4f}")
        else:
            print(f"  {tipo}: n={len(grupo)} exceso={grupo.mean():.2f}% -- muestra insuficiente para Monte Carlo" if len(grupo) else f"  {tipo}: sin candidatos")
    print(f"  TODOS (sin regimen, referencia de hoy): n={len(todos)} exceso={np.mean(todos):.2f}%")
    print()


if __name__ == "__main__":
    print("Cargando 5 monedas (ETH/BTC diario, XRP/SOL/BNB resampleadas de 4h)...\n")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_regimen_capa3_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_regimen_capa3_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }
    benchmarks = {n: _benchmark_incondicional(df, df["open_time"].min(), df["open_time"].max()) for n, df in monedas.items()}
    print("Benchmarks incondicionales por moneda:", {k: round(v, 2) for k, v in benchmarks.items()}, "\n")

    rng = np.random.default_rng(20260915)
    _reporte("CANAL ASCENDENTE", canal_ascendente, monedas, benchmarks, rng)
    _reporte("CANAL DESCENDENTE", canal_descendente, monedas, benchmarks, rng)
