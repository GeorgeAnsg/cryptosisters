"""15-sept-2026: tercera version de "canal via composicion" (idea del
usuario). Las dos anteriores fallaron por razones distintas:

  1. canal_via_alternancia_techo_suelo.py: filtro binario "¿se repitio el
     nivel y hubo un cruce del tipo contrario en medio?" -- no calculaba
     geometria real de canal, solo presencia/ausencia. Descartado.
  2. bandera_banderin_flexible.py: usa la geometria de canal_flexible.py
     (su propia deteccion de minimos/maximos simples), NO los puntos de
     doble techo/doble suelo. Nunca se probo en rentabilidad.
  3. canal_como_filtro_contexto.py: usa canal_flexible.py como filtro de
     contexto externo -- descartado porque dispara con tanta frecuencia
     que el grupo "sin canal" queda vacio para techo, y para suelo no
     mejora sobre "no mirar nada".

Esta version es distinta a las tres: toma los 4 PUNTOS de un doble suelo
(fondo1, fondo2, ya validados como Capa 1) y un doble techo (techo1,
techo2) que ALTERNAN en el tiempo (suelo-techo-suelo-techo o
techo-suelo-techo-suelo), y les aplica EXACTAMENTE la misma formula
geometrica de canal (`_score_forma` de canal_flexible.py -- pendiente,
paralelismo, ancho, consistencia) en vez de re-detectar minimos/maximos
propios. La apuesta: los 4 puntos ya son de mejor calidad (vienen de
motores graduados) que los minimos/maximos simples que usa canal_flexible
por su cuenta.

Comparacion: candidatos de techo/suelo que SI encajan en un canal de 4
puntos (agrupados por probabilidad_forma del canal, no un umbral fijo)
frente a los que NO encajan en ningun canal -- exceso sobre benchmark
incondicional, igual metodologia que el resto de pruebas del dia.
Ajuste solo en ETH-ajuste, confirmar sin tocar nada en ETH-tiempo y BTC.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.canal_flexible import PESOS_FORMA as PESOS_CANAL
from laboratorio.patrones.canal_flexible import _score_forma
from motores import doble_suelo, doble_techo

DIAS_EXITO = vcp.DIAS_EXITO

# Tolerancias geometricas fijas (no forman parte del grid que ya se valido
# en canal_flexible.py -- ahi solo se barrieron los PESOS internos, ver
# PESOS_FORMA). Mismos valores por defecto que detectar_ascendente/descendente.
TOLERANCIAS_SCORE_FORMA = dict(
    pendiente_ideal_pct_dia=1.0, paralelismo_tolerancia_pct_dia=0.5,
    ancho_ideal_pct=8.0, ancho_tolerancia_exceso_pct=10.0,
    consistencia_tolerancia=0.5, contencion_tolerancia_pct=10.0,
)


def _probabilidad_consenso(f1, p1, f2, p2, cf1, cp1, cf2, cp2, close) -> float | None:
    """Promedio de probabilidad_forma sobre las 6 configs de PESOS_CANAL ya
    validadas para canal_flexible.py (deteccion-flexible-patrones: varios
    pesos compitiendo, no uno solo) -- devuelve None si CUALQUIER config
    invalida el canal (lineas cruzadas), igual de estricto que el requisito
    estructural original."""
    probs = []
    for peso_pendiente, peso_paralelismo, peso_ancho, peso_consistencia, peso_contencion in PESOS_CANAL:
        r = _score_forma(f1, p1, f2, p2, cf1, cp1, cf2, cp2, close, False,
                          **TOLERANCIAS_SCORE_FORMA,
                          peso_pendiente=peso_pendiente, peso_paralelismo=peso_paralelismo,
                          peso_ancho=peso_ancho, peso_consistencia=peso_consistencia,
                          peso_contencion=peso_contencion)
        if r is None:
            return None
        probs.append(r["probabilidad_forma"])
    return float(np.mean(probs))


def _benchmark_incondicional(df: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp) -> float:
    fechas = df["open_time"]; close = df["close"].to_numpy(); n = len(close)
    rs = [(close[i + DIAS_EXITO] - close[i]) / close[i] * 100 for i in range(n)
          if desde <= fechas.iloc[i] < hasta and i + DIAS_EXITO < n]
    return float(np.mean(rs)) if rs else 0.0


def _candidatos(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """(techos, suelos), cada fila con los 2 indices propios del patron y
    su retorno futuro (ya usado para exceso)."""
    close = df["close"].to_numpy(); n = len(df)
    techos, suelos = [], []
    for r in doble_techo.calcular(df):
        c = r.candidato
        if c.idx_techo2 + DIAS_EXITO >= n:
            continue
        retorno = (close[c.idx_techo2 + DIAS_EXITO] - close[c.idx_techo2]) / close[c.idx_techo2] * 100
        techos.append({"idx1": c.idx_techo1, "idx2": c.idx_techo2, "retorno": retorno})
    for r in doble_suelo.calcular(df):
        c = r.candidato
        if c.idx_fondo2 + DIAS_EXITO >= n:
            continue
        retorno = (close[c.idx_fondo2 + DIAS_EXITO] - close[c.idx_fondo2]) / close[c.idx_fondo2] * 100
        suelos.append({"idx1": c.idx_fondo1, "idx2": c.idx_fondo2, "retorno": retorno})
    return techos, suelos


def _canales_4puntos(techos: list[dict], suelos: list[dict], close: np.ndarray) -> dict[int, float]:
    """Para cada idx2 (de techo o suelo) que actua como PUNTO FINAL de un
    canal alterno de 4 puntos, la mejor probabilidad_forma (consenso de
    PESOS_CANAL) encontrada. Alternancia exigida: fondo1<techo1<fondo2<techo2
    (acaba en techo) o techo1<fondo1<techo2<fondo2 (acaba en suelo)."""
    mejor: dict[int, float] = {}
    for t in techos:
        for s in suelos:
            f1, f2 = s["idx1"], s["idx2"]
            p1, p2 = t["idx1"], t["idx2"]
            if f1 < p1 < f2 < p2:
                idx_final = p2
            elif p1 < f1 < p2 < f2:
                idx_final = f2
            else:
                continue
            prob = _probabilidad_consenso(f1, p1, f2, p2, close[f1], close[p1], close[f2], close[p2], close)
            if prob is None:
                continue
            if prob > mejor.get(idx_final, -1.0):
                mejor[idx_final] = prob
    return mejor


def _stats(retornos: list[float], bm: float) -> dict:
    if not retornos:
        return {"n": 0, "exceso_medio_pct": None}
    arr = np.array(retornos) - bm
    return {"n": len(arr), "exceso_medio_pct": round(float(arr.mean()), 2)}


def _reporte(nombre: str, filas: list[dict], canales: dict[int, float], desde, hasta, fechas, bm) -> None:
    en_tramo = [f for f in filas if desde <= fechas.iloc[f["idx2"]] < hasta]
    con = [(f["retorno"], canales[f["idx2"]]) for f in en_tramo if f["idx2"] in canales]
    sin = [f["retorno"] for f in en_tramo if f["idx2"] not in canales]
    print(f"{nombre}: sin_canal={_stats(sin, bm)}  con_canal_total={_stats([r for r,_ in con], bm)}")
    if con:
        mediana_prob = float(np.median([p for _, p in con]))
        alta = [r for r, p in con if p >= mediana_prob]
        baja = [r for r, p in con if p < mediana_prob]
        print(f"    de esos, prob_forma alta (>=mediana {mediana_prob:.2f}): {_stats(alta, bm)}   "
              f"prob_forma baja: {_stats(baja, bm)}")


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_4puntos_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_4puntos_btc")
    close_eth, close_btc = df_eth["close"].to_numpy(), df_btc["close"].to_numpy()

    bm_ajuste = _benchmark_incondicional(df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN)
    bm_tiempo = _benchmark_incondicional(df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    bm_btc = _benchmark_incondicional(df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    print(f"Benchmarks: ajuste={bm_ajuste:.2f}% tiempo={bm_tiempo:.2f}% btc={bm_btc:.2f}%\n")

    techos_eth, suelos_eth = _candidatos(df_eth)
    techos_btc, suelos_btc = _candidatos(df_btc)
    fechas_eth, fechas_btc = df_eth["open_time"], df_btc["open_time"]

    print("Buscando canales de 4 puntos (combinando todos los techo x suelo)...")
    canales_eth = _canales_4puntos(techos_eth, suelos_eth, close_eth)
    canales_btc = _canales_4puntos(techos_btc, suelos_btc, close_btc)
    print(f"  ETH: {len(canales_eth)} señales con canal detectado de {len(techos_eth)+len(suelos_eth)} totales")
    print(f"  BTC: {len(canales_btc)} señales con canal detectado de {len(techos_btc)+len(suelos_btc)} totales\n")

    print("=" * 70); print("ETH-AJUSTE (2021-2023)"); print("=" * 70)
    _reporte("TECHO", techos_eth, canales_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, fechas_eth, bm_ajuste)
    _reporte("SUELO", suelos_eth, canales_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, fechas_eth, bm_ajuste)

    print("\n" + "=" * 70); print("CONFIRMACION 1: ETH-TIEMPO (2023-2025, nunca visto)"); print("=" * 70)
    _reporte("TECHO", techos_eth, canales_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, fechas_eth, bm_tiempo)
    _reporte("SUELO", suelos_eth, canales_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, fechas_eth, bm_tiempo)

    print("\n" + "=" * 70); print("CONFIRMACION 2: BTC completo (nunca visto)"); print("=" * 70)
    _reporte("TECHO", techos_btc, canales_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, fechas_btc, bm_btc)
    _reporte("SUELO", suelos_btc, canales_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, fechas_btc, bm_btc)
