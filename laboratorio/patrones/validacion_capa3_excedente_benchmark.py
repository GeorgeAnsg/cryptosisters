"""15-sept-2026: la Capa 3 (contexto de mercado) de doble techo y doble
suelo -- la pieza que de verdad aporta la señal, no la forma geometrica
sola -- se selecciono y valido con RETORNO BRUTO (ver
`segmentacion_ath_por_regimen.py`, `validacion_multi_moneda_combo_fuerte.py`
para techo y `doble_suelo_motor_v2.py` para suelo). Igual que con canal y
caida_recuperacion hoy mismo, esto puede confundir deriva alcista de fondo
del mercado con señal real. Este script repite EXACTAMENTE los mismos
combos ya graduados a `motores/doble_techo.py` / `motores/doble_suelo.py`
(mismo filtro de regimen, mismos candidatos, mismas 5 monedas), pero
restando el benchmark incondicional (retorno medio a DIAS_EXITO dias de
CUALQUIER dia de esa misma moneda, sin condicionar en ninguna señal) antes
de medir "acierto" o promediar.

Combos probados (los 4 que existen hoy en produccion):
  TECHO bajista + nivel_repetido + cerca ATH  (el mas fuerte de la sesion)
  TECHO alcista + cerca ATH                    (mas debil, descontado x0.42)
  SUELO alcista solo (sin pieza extra)
  SUELO bajista + lejos del ATH

No se reabre el grid de pesos de forma (Capa 1) -- se usan los mismos
PESOS=(0.35, 0.25, 0.1, 0.3) que las validaciones originales de Capa 3.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from datos.cargar import cargar_ohlcv
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_suelo_flexible, doble_techo_flexible, regimen_mercado
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
from laboratorio.patrones.regimen_mercado import TipoRegimen

PESOS = (0.35, 0.25, 0.1, 0.3)
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


def _candidatos_techo(df: pd.DataFrame) -> list[dict]:
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
        tipo, _score = regimen_mercado.clasificar(df, c.idx_techo2, sma200)
        nivel_actual = (close[c.idx_techo1] + close[c.idx_techo2]) / 2
        patron_previo = any(
            idx2p < c.idx_techo1 - 3 and abs(nivp - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2p, nivp in niveles_previos
        )
        niveles_previos.append((c.idx_techo2, nivel_actual))
        fin = c.idx_techo2 + DIAS_EXITO
        if fin >= n:
            continue
        precio0 = close[c.idx_techo2]
        retorno = (close[fin] - precio0) / precio0 * 100
        dist_ath = (ath_hasta[c.idx_techo2] - close[c.idx_techo2]) / ath_hasta[c.idx_techo2] * 100
        filas.append({"tipo": tipo, "patron_previo": patron_previo, "dist_ath": dist_ath, "retorno": retorno})
    return filas


def _candidatos_suelo(df: pd.DataFrame) -> list[dict]:
    peso_nivel, peso_rebote, peso_tiempo, peso_altura = PESOS
    candidatos = doble_suelo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    n = len(df)
    filas = []
    for c in candidatos:
        tipo, _score = regimen_mercado.clasificar(df, c.idx_fondo2, sma200)
        fin = c.idx_fondo2 + DIAS_EXITO
        if fin >= n:
            continue
        precio0 = close[c.idx_fondo2]
        retorno = (close[fin] - precio0) / precio0 * 100
        dist_ath = (ath_hasta[c.idx_fondo2] - close[c.idx_fondo2]) / ath_hasta[c.idx_fondo2] * 100
        filas.append({"tipo": tipo, "dist_ath": dist_ath, "retorno": retorno})
    return filas


def _monte_carlo(excesos: np.ndarray, umbral: float, rng: np.random.default_rng, sube: bool) -> float:
    aciertos_reales = (excesos >= umbral).mean() if sube else (excesos <= -umbral).mean()
    centrado = excesos - excesos.mean()
    n = len(excesos)
    resultados = np.array([
        ((rng.choice(centrado, size=n, replace=True) >= umbral).mean() if sube
         else (rng.choice(centrado, size=n, replace=True) <= -umbral).mean())
        for _ in range(N_SIMULACIONES)
    ])
    return float((resultados >= aciertos_reales).mean())


def _reporte(nombre: str, excesos: np.ndarray, sube: bool, rng: np.random.default_rng) -> None:
    if len(excesos) == 0:
        print(f"{nombre}: sin candidatos"); return
    print(f"--- {nombre} (n={len(excesos)}) ---")
    print(f"  exceso medio: {excesos.mean():.2f}%  (mediana {np.median(excesos):.2f}%)")
    for umbral in UMBRALES_EXITO_PCT:
        acierto = (excesos >= umbral).mean()*100 if sube else (excesos <= -umbral).mean()*100
        p = _monte_carlo(excesos, umbral, rng, sube)
        direccion = "subir" if sube else "bajar"
        print(f"  {direccion} al menos {umbral}% (exceso): acierta {acierto:.0f}%  p={p:.4f}")
    print()


if __name__ == "__main__":
    print("Cargando 5 monedas (ETH/BTC diario, XRP/SOL/BNB resampleadas de 4h)...\n")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="validacion_capa3_excedente_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="validacion_capa3_excedente_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }
    benchmarks = {n: _benchmark_incondicional(df) for n, df in monedas.items()}
    print("Benchmarks incondicionales (%s dias) por moneda: %s\n" % (DIAS_EXITO, {k: round(v,2) for k,v in benchmarks.items()}))

    rng = np.random.default_rng(20260915)

    print("=" * 70)
    print("DOBLE TECHO -- bajista + nivel_repetido + cerca ATH (combo mas fuerte)")
    print("=" * 70)
    excesos_bt = []
    for nombre, df in monedas.items():
        filas = _candidatos_techo(df)
        bm = benchmarks[nombre]
        grupo = [f for f in filas if f["tipo"] == TipoRegimen.BAJISTA and f["patron_previo"]]
        excesos = [f["retorno"] - bm for f in grupo]
        excesos_bt.extend(excesos)
        if excesos:
            print(f"  {nombre}: n={len(excesos)} exceso medio={np.mean(excesos):.2f}%")
        else:
            print(f"  {nombre}: sin candidatos")
    print()
    _reporte("CONJUNTO 5 MONEDAS (techo bajista+nivel+ATH)", np.array(excesos_bt), sube=False, rng=rng)

    print("=" * 70)
    print("DOBLE TECHO -- alcista + cerca ATH (combo debil, descontado)")
    print("=" * 70)
    excesos_at = []
    for nombre, df in monedas.items():
        filas = _candidatos_techo(df)
        bm = benchmarks[nombre]
        grupo = [f for f in filas if f["tipo"] == TipoRegimen.ALCISTA]
        mediana = np.median([f["dist_ath"] for f in grupo]) if grupo else 0
        cerca = [f for f in grupo if f["dist_ath"] <= mediana]
        excesos = [f["retorno"] - bm for f in cerca]
        excesos_at.extend(excesos)
        if excesos:
            print(f"  {nombre}: n={len(excesos)} exceso medio={np.mean(excesos):.2f}%")
    print()
    _reporte("CONJUNTO 5 MONEDAS (techo alcista+cerca ATH)", np.array(excesos_at), sube=False, rng=rng)

    print("=" * 70)
    print("DOBLE SUELO -- alcista solo (sin pieza extra)")
    print("=" * 70)
    excesos_sa = []
    for nombre, df in monedas.items():
        filas = _candidatos_suelo(df)
        bm = benchmarks[nombre]
        grupo = [f for f in filas if f["tipo"] == TipoRegimen.ALCISTA]
        excesos = [f["retorno"] - bm for f in grupo]
        excesos_sa.extend(excesos)
        if excesos:
            print(f"  {nombre}: n={len(excesos)} exceso medio={np.mean(excesos):.2f}%")
    print()
    _reporte("CONJUNTO 5 MONEDAS (suelo alcista solo)", np.array(excesos_sa), sube=True, rng=rng)

    print("=" * 70)
    print("DOBLE SUELO -- bajista + lejos del ATH")
    print("=" * 70)
    excesos_sb = []
    for nombre, df in monedas.items():
        filas = _candidatos_suelo(df)
        bm = benchmarks[nombre]
        grupo = [f for f in filas if f["tipo"] == TipoRegimen.BAJISTA]
        mediana = np.median([f["dist_ath"] for f in grupo]) if grupo else 0
        lejos = [f for f in grupo if f["dist_ath"] > mediana]
        excesos = [f["retorno"] - bm for f in lejos]
        excesos_sb.extend(excesos)
        if excesos:
            print(f"  {nombre}: n={len(excesos)} exceso medio={np.mean(excesos):.2f}%")
    print()
    _reporte("CONJUNTO 5 MONEDAS (suelo bajista+lejos ATH)", np.array(excesos_sb), sube=True, rng=rng)
