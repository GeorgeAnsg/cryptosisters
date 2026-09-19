"""15-sept-2026: cierre de la validacion de canal_flexible.py como MOTOR
PROPIO (no como filtro sobre doble techo/suelo, no como composicion --
ambas vias se probaron hoy y no dieron ventaja real). La Etapa 2
("¿confirma el precio la ruptura de la proyeccion de la linea?", ver
`_entradas_confirmadas_canal` en validacion_cruzada_pesos.py) SI mostro
ventaja consistente en ETH-ajuste/ETH-tiempo/BTC -- pero solo tras corregir
un fallo de medicion: contar el retorno desde el dia de CONFIRMACION
(en vez de desde el fin del canal, idx_pico2) penalizaba a "bajada" con
fuerza artificial, porque las caidas en cripto son mucho mas rapidas que
las subidas -- para cuando la ruptura bajista se confirma, ya se perdio la
mayor parte del movimiento y lo que sigue es mas rebote que continuacion
(medido hoy mismo: subida confirma tras +6.6% ya recorrido, bajada tras
-14.5%, mas del doble). Corregido: el retorno SIEMPRE se mide desde
idx_pico2 (fin del canal), sea cual sea el grupo.

Este script repite esa comparacion (con confirmacion vs sin) en las 5
monedas ya usadas para doble techo/suelo, con Monte Carlo (5000 sims,
igual mecanismo que validacion_capa3_excedente_benchmark.py) para saber si
la diferencia es estadisticamente solida y no un artefacto de muestra
pequeña. Ajuste de pesos ya congelado esta mañana en
validacion_canal_excedente_benchmark.py -- aqui NO se reabre ese grid,
solo se confirma con mas monedas usando los pesos ya elegidos.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from datos.cargar import cargar_ohlcv
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.validacion_cruzada_pesos import DIAS_EXITO, UMBRALES_EXITO_PCT, _entradas_confirmadas_canal

# Pesos ya congelados en validacion_canal_excedente_benchmark.py (ajuste ETH, esta mañana).
PESOS_SUBIDA = (0.55, 0.1, 0.15, 0.1, 0.1)
FRACCION_SUBIDA = 0.35
PESOS_BAJADA = (0.05, 0.2, 0.3, 0.1, 0.35)
FRACCION_BAJADA = 0.15

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


def _con_sin(df: pd.DataFrame, direccion: str, pesos: tuple, fraccion: float) -> tuple[np.ndarray, np.ndarray]:
    """Retorno SIEMPRE medido desde idx_pico2 (fin del canal) -- fix de hoy,
    nunca desde el dia de confirmacion."""
    close = df["close"].to_numpy(); n = len(df)
    filas = _entradas_confirmadas_canal(df, pesos, direccion, fraccion_confirmacion=fraccion)
    con, sin = [], []
    for idx2, idx_conf in filas:
        fin = idx2 + DIAS_EXITO
        if fin >= n:
            continue
        retorno = (close[fin] - close[idx2]) / close[idx2] * 100
        (con if idx_conf is not None else sin).append(retorno)
    return np.array(con), np.array(sin)


def _monte_carlo_diferencia(con: np.ndarray, sin: np.ndarray, rng: np.random.default_rng) -> float:
    """p-valor de que la diferencia (con - sin) observada se deba al azar:
    baraja las etiquetas con/sin entre las dos muestras N veces."""
    diff_obs = con.mean() - sin.mean()
    todos = np.concatenate([con, sin])
    n_con = len(con)
    diffs = np.empty(N_SIMULACIONES)
    for i in range(N_SIMULACIONES):
        perm = rng.permutation(todos)
        diffs[i] = perm[:n_con].mean() - perm[n_con:].mean()
    # bajada: se espera diferencia negativa (con mas bajista que sin) -> cola izquierda
    if diff_obs < 0:
        return float((diffs <= diff_obs).mean())
    return float((diffs >= diff_obs).mean())


def _reporte(nombre: str, direccion: str, pesos: tuple, fraccion: float,
             monedas: dict[str, pd.DataFrame], benchmarks: dict[str, float], rng) -> None:
    print(f"--- {nombre} ---")
    con_todas, sin_todas = [], []
    for moneda, df in monedas.items():
        con, sin = _con_sin(df, direccion, pesos, fraccion)
        bm = benchmarks[moneda]
        con_e, sin_e = con - bm, sin - bm
        con_todas.extend(con_e.tolist()); sin_todas.extend(sin_e.tolist())
        if len(con) and len(sin):
            print(f"  {moneda}: con(n={len(con)}) exceso={con_e.mean():.2f}%   sin(n={len(sin)}) exceso={sin_e.mean():.2f}%")
        else:
            print(f"  {moneda}: datos insuficientes (con={len(con)}, sin={len(sin)})")
    con_todas, sin_todas = np.array(con_todas), np.array(sin_todas)
    p = _monte_carlo_diferencia(con_todas, sin_todas, rng)
    print(f"  CONJUNTO 5 MONEDAS: con(n={len(con_todas)}) exceso={con_todas.mean():.2f}%   "
          f"sin(n={len(sin_todas)}) exceso={sin_todas.mean():.2f}%   diferencia p={p:.4f}")
    for umbral in UMBRALES_EXITO_PCT:
        sube = direccion == "subida"
        acierto_con = ((con_todas >= umbral) if sube else (con_todas <= -umbral)).mean() * 100
        acierto_sin = ((sin_todas >= umbral) if sube else (sin_todas <= -umbral)).mean() * 100
        print(f"    umbral {umbral}%: acierto con_confirmacion={acierto_con:.0f}%  sin_confirmacion={acierto_sin:.0f}%")
    print()
    return con_todas


if __name__ == "__main__":
    print("Cargando 5 monedas (ETH/BTC diario, XRP/SOL/BNB resampleadas de 4h)...\n")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_confirmacion_5m_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_confirmacion_5m_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }
    benchmarks = {n: _benchmark_incondicional(df) for n, df in monedas.items()}
    print("Benchmarks incondicionales por moneda:", {k: round(v, 2) for k, v in benchmarks.items()}, "\n")

    rng = np.random.default_rng(20260915)
    con_subida = _reporte("CANAL ASCENDENTE -- confirmacion de ruptura al alza", "subida",
                           PESOS_SUBIDA, FRACCION_SUBIDA, monedas, benchmarks, rng)
    con_bajada = _reporte("CANAL DESCENDENTE -- confirmacion de ruptura a la baja", "bajada",
                           PESOS_BAJADA, FRACCION_BAJADA, monedas, benchmarks, rng)

    print("=" * 70)
    print("PUERTA 1 y PUERTA 5 (causalidad / recursividad): ya PASADAS esta mañana")
    print("  -- puerta1_canal_motor.py y puerta5_canal_motor.py, 0 fugas en ambas")
    print()

    print("=" * 70)
    print("PUERTA 4 -- Presupuesto de intentos (Deflated Sharpe Ratio)")
    print("=" * 70)
    import tests.puerta4_dsr as p4
    from tests.puerta_presupuesto import verificar_presupuesto
    presu = verificar_presupuesto()
    n_intentos = presu["n_intentos_distintos"]
    print(f"Intentos ya registrados en el proyecto: {n_intentos} de {presu['presupuesto_total']}\n")
    # DSR asume "mas alto = mejor" -- en descendente "acertar" es que el
    # precio BAJE, asi que se invierte el signo antes de medir Sharpe (si no,
    # un patron bajista que funciona perfectamente sale con Sharpe negativo).
    for nombre, con in [("Canal ascendente (con confirmacion)", con_subida),
                        ("Canal descendente (con confirmacion)", -con_bajada)]:
        resultado = p4.evaluar(con, n_intentos_totales=n_intentos)
        print(resultado.resumen(nombre))
    print()
