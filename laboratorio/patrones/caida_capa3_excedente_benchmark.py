"""15-sept-2026: caida_recuperacion.py nunca recibio una Capa 3 de
contexto de mercado -- solo se probo su Capa 1 (forma, 7 dimensiones), que
colapso al corregir con exceso sobre benchmark (igual que canal). El
usuario señalo, con razon, que eso no es motivo suficiente para
descartarla: a canal SI se le probo una Capa 3 (regimen+ATH,
`canal_capa3_contexto.py`) antes de descartarla, y aqui no. Este script
cierra esa asimetria.

caida_recuperacion es estructuralmente mas parecida a doble suelo que a
canal: un `idx_fondo` tras una caida, patron alcista de continuacion. Se
prueban aqui EXACTAMENTE los mismos dos factores que si sobrevivieron para
doble suelo (`doble_suelo_motor_v2.py`): regimen ALCISTA solo, y regimen
BAJISTA + lejos del ATH -- construidos con exceso sobre benchmark desde el
principio, nunca retorno bruto, y sobre las mismas 5 monedas
(BTC/ETH/XRP/SOL/BNB) para poder comparar en igualdad de condiciones con
el resultado ya obtenido para suelo.

Pesos de forma: se usa el "mejor" ya encontrado hoy con retorno bruto
((0.1, 0.1, 0.1, 0.2, 0.15, 0.15, 0.2)) solo para DETECTAR candidatos --
igual que se hizo para techo/suelo/canal, la Capa 3 se prueba encima de
una deteccion ya fijada, no se reabre el grid de forma aqui.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from datos.cargar import cargar_ohlcv
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import caida_recuperacion, regimen_mercado
from laboratorio.patrones.regimen_mercado import TipoRegimen

PESOS_CAIDA = (0.30, 0.30, 0.20, 0.15, 0.05)  # config "equilibrado" del grid causal nuevo (default de detectar())
DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
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


def _candidatos_caida(df: pd.DataFrame) -> list[dict]:
    (peso_caida, peso_velocidad, peso_mecha, peso_desaceleracion, peso_arranque) = PESOS_CAIDA
    candidatos = caida_recuperacion.detectar(
        df, peso_caida=peso_caida, peso_velocidad=peso_velocidad,
        peso_mecha=peso_mecha, peso_desaceleracion=peso_desaceleracion,
        peso_arranque=peso_arranque,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    n = len(df)
    filas = []
    for c in candidatos:
        tipo, _score = regimen_mercado.clasificar(df, c.idx_fondo, sma200)
        fin = c.idx_fondo + DIAS_EXITO
        if fin >= n:
            continue
        precio0 = close[c.idx_fondo]
        retorno = (close[fin] - precio0) / precio0 * 100
        dist_ath = (ath_hasta[c.idx_fondo] - close[c.idx_fondo]) / ath_hasta[c.idx_fondo] * 100
        filas.append({"tipo": tipo, "dist_ath": dist_ath, "retorno": retorno})
    return filas


def _monte_carlo(excesos: np.ndarray, umbral: float, rng: np.random.default_rng) -> float:
    aciertos_reales = (excesos >= umbral).mean()
    centrado = excesos - excesos.mean()
    n = len(excesos)
    resultados = np.array([
        (rng.choice(centrado, size=n, replace=True) >= umbral).mean() for _ in range(N_SIMULACIONES)
    ])
    return float((resultados >= aciertos_reales).mean())


def _reporte(nombre: str, excesos: np.ndarray, rng: np.random.default_rng) -> None:
    if len(excesos) == 0:
        print(f"{nombre}: sin candidatos"); return
    print(f"--- {nombre} (n={len(excesos)}) ---")
    print(f"  exceso medio: {excesos.mean():.2f}%  (mediana {np.median(excesos):.2f}%)")
    for umbral in UMBRALES_EXITO_PCT:
        acierto = (excesos >= umbral).mean() * 100
        p = _monte_carlo(excesos, umbral, rng)
        print(f"  subir al menos {umbral}% (exceso): acierta {acierto:.0f}%  p={p:.4f}")
    print()


if __name__ == "__main__":
    print("Cargando 5 monedas (ETH/BTC diario, XRP/SOL/BNB resampleadas de 4h)...\n")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="caida_capa3_excedente_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="caida_capa3_excedente_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }
    benchmarks = {n: _benchmark_incondicional(df) for n, df in monedas.items()}
    print(f"Benchmarks incondicionales ({DIAS_EXITO} dias) por moneda:", {k: round(v, 2) for k, v in benchmarks.items()}, "\n")

    rng = np.random.default_rng(20260915)

    print("=" * 70)
    print("CAIDA_RECUPERACION -- regimen ALCISTA solo (mismo factor que sobrevivio en suelo)")
    print("=" * 70)
    excesos_a = []
    for nombre, df in monedas.items():
        filas = _candidatos_caida(df)
        bm = benchmarks[nombre]
        grupo = [f for f in filas if f["tipo"] == TipoRegimen.ALCISTA]
        excesos = [f["retorno"] - bm for f in grupo]
        excesos_a.extend(excesos)
        print(f"  {nombre}: n={len(excesos)}" + (f" exceso medio={np.mean(excesos):.2f}%" if excesos else " (sin candidatos)"))
    print()
    _reporte("CONJUNTO 5 MONEDAS (caida, alcista solo)", np.array(excesos_a), rng)

    print("=" * 70)
    print("CAIDA_RECUPERACION -- regimen BAJISTA + lejos del ATH (mismo factor que sobrevivio en suelo)")
    print("=" * 70)
    excesos_b = []
    for nombre, df in monedas.items():
        filas = _candidatos_caida(df)
        bm = benchmarks[nombre]
        grupo = [f for f in filas if f["tipo"] == TipoRegimen.BAJISTA]
        mediana = np.median([f["dist_ath"] for f in grupo]) if grupo else 0
        lejos = [f for f in grupo if f["dist_ath"] > mediana]
        excesos = [f["retorno"] - bm for f in lejos]
        excesos_b.extend(excesos)
        print(f"  {nombre}: n={len(excesos)}" + (f" exceso medio={np.mean(excesos):.2f}%" if excesos else " (sin candidatos)"))
    print()
    _reporte("CONJUNTO 5 MONEDAS (caida, bajista+lejos ATH)", np.array(excesos_b), rng)

    print("=" * 70)
    print("CAIDA_RECUPERACION -- regimen NEUTRO (referencia, sin hipotesis)")
    print("=" * 70)
    excesos_n = []
    for nombre, df in monedas.items():
        filas = _candidatos_caida(df)
        bm = benchmarks[nombre]
        grupo = [f for f in filas if f["tipo"] == TipoRegimen.NEUTRO]
        excesos = [f["retorno"] - bm for f in grupo]
        excesos_n.extend(excesos)
        print(f"  {nombre}: n={len(excesos)}" + (f" exceso medio={np.mean(excesos):.2f}%" if excesos else " (sin candidatos)"))
    print()
    _reporte("CONJUNTO 5 MONEDAS (caida, neutro)", np.array(excesos_n), rng)
