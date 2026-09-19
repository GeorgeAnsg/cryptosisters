"""15-sept-2026: idea del usuario -- no usar canal_flexible.py como motor
que genera sus propios candidatos (eso ya se probo dos veces y fallo: ni
componiendo doble techo/suelo en canal_via_alternancia_techo_suelo.py, ni
como pieza de consolidacion en bandera_banderin_flexible.py, que ademas
nunca se llego a testear en rentabilidad). Aqui se usa canal_flexible.py
como una pregunta de CONTEXTO mas, exactamente con el mismo mecanismo que
ya esta confirmado como robusto en produccion: regimen de mercado y
distancia al ATH como Capa 3 sobre los candidatos YA VALIDADOS de doble
techo / doble suelo (ver validacion_capa3_excedente_benchmark.py).

Pregunta que se testea: cuando un doble techo/doble suelo aparece justo
DESPUES de que canal_flexible haya confirmado un canal (ascendente,
descendente o lateral) que acaba de terminar, ¿el exceso sobre benchmark
es distinto que cuando no hay canal reciente detras?

Causalidad: un candidato de canal solo cuenta como "contexto conocido" en
el momento idx2 (idx_techo2/idx_fondo2) si el canal ya habia TERMINADO
(idx_fin_canal) en o antes de idx2 -- nunca se usa un canal cuyo propio
fin cae despues del candidato que se esta clasificando, eso seria mirar
al futuro.

No absolutos: la ventana de "canal reciente" (cuantos dias como maximo
desde que el canal termino hasta el candidato) se prueba con un RANGO,
no un numero fijo -- VENTANAS_CONTEXTO_DIAS.

Metodologia identica al resto de pruebas del dia: exceso sobre benchmark
incondicional; ajuste SOLO en ETH-ajuste (2021-2023), congelar, confirmar
sin tocar nada en ETH-tiempo (2023-2025) y en BTC completo (nunca visto).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import canal_flexible as cf
from motores import doble_suelo, doble_techo

DIAS_EXITO = vcp.DIAS_EXITO
VENTANAS_CONTEXTO_DIAS = [3, 5, 10, 15, 20]


def _benchmark_incondicional(df: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp) -> float:
    fechas = df["open_time"]; close = df["close"].to_numpy(); n = len(close)
    rs = [(close[i + DIAS_EXITO] - close[i]) / close[i] * 100 for i in range(n)
          if desde <= fechas.iloc[i] < hasta and i + DIAS_EXITO < n]
    return float(np.mean(rs)) if rs else 0.0


def _canales(df: pd.DataFrame) -> dict[str, list[tuple[int, int]]]:
    """(idx_inicio, idx_fin) de cada canal, por tipo -- fin = el ultimo indice
    que participa en la geometria del canal (max de los 4 anclajes)."""
    out = {}
    for tipo, fn in (("ascendente", cf.detectar_ascendente),
                      ("descendente", cf.detectar_descendente),
                      ("lateral", cf.detectar_lateral)):
        candidatos = fn(df)
        out[tipo] = [
            (min(c.idx_fondo1, c.idx_pico1, c.idx_fondo2, c.idx_pico2),
             max(c.idx_fondo1, c.idx_pico1, c.idx_fondo2, c.idx_pico2))
            for c in candidatos
        ]
    return out


def _contexto_canal(idx2: int, canales: dict[str, list[tuple[int, int]]], ventana_dias: int) -> str:
    """Tipo de canal que acaba de terminar (idx_fin <= idx2) dentro de la
    ventana de dias dada; si varios tipos aplican, se queda con el mas
    reciente. 'ninguno' si no hay ningun canal reciente."""
    mejor_tipo, mejor_fin = "ninguno", -1
    for tipo, spans in canales.items():
        for _inicio, fin in spans:
            if fin <= idx2 and (idx2 - fin) <= ventana_dias and fin > mejor_fin:
                mejor_tipo, mejor_fin = tipo, fin
    return mejor_tipo


def _candidatos_techo(df: pd.DataFrame) -> list[dict]:
    close = df["close"].to_numpy(); n = len(df)
    filas = []
    for r in doble_techo.calcular(df):
        idx2 = r.candidato.idx_techo2
        if idx2 + DIAS_EXITO >= n:
            continue
        retorno = (close[idx2 + DIAS_EXITO] - close[idx2]) / close[idx2] * 100
        filas.append({"idx2": idx2, "retorno": retorno})
    return filas


def _candidatos_suelo(df: pd.DataFrame) -> list[dict]:
    close = df["close"].to_numpy(); n = len(df)
    filas = []
    for r in doble_suelo.calcular(df):
        idx2 = r.candidato.idx_fondo2
        if idx2 + DIAS_EXITO >= n:
            continue
        retorno = (close[idx2 + DIAS_EXITO] - close[idx2]) / close[idx2] * 100
        filas.append({"idx2": idx2, "retorno": retorno})
    return filas


def _stats(retornos: list[float], bm: float) -> dict:
    if not retornos:
        return {"n": 0, "exceso_medio_pct": None}
    arr = np.array(retornos) - bm
    return {"n": len(arr), "exceso_medio_pct": round(float(arr.mean()), 2)}


def _reporte(nombre: str, filas: list[dict], canales: dict, desde: pd.Timestamp, hasta: pd.Timestamp,
             fechas: pd.Series, bm: float) -> None:
    en_tramo = [f for f in filas if desde <= fechas.iloc[f["idx2"]] < hasta]
    print(f"{nombre} (n_total_tramo={len(en_tramo)}):")
    for ventana in VENTANAS_CONTEXTO_DIAS:
        por_tipo: dict[str, list[float]] = {"ascendente": [], "descendente": [], "lateral": [], "ninguno": []}
        for f in en_tramo:
            tipo = _contexto_canal(f["idx2"], canales, ventana)
            por_tipo[tipo].append(f["retorno"])
        resumen = {t: _stats(rs, bm) for t, rs in por_tipo.items()}
        print(f"  ventana={ventana}d: " + "  ".join(f"{t}={s}" for t, s in resumen.items()))
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_filtro_contexto_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_filtro_contexto_btc")

    bm_ajuste = _benchmark_incondicional(df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN)
    bm_tiempo = _benchmark_incondicional(df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    bm_btc = _benchmark_incondicional(df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    print(f"Benchmarks: ajuste={bm_ajuste:.2f}% tiempo={bm_tiempo:.2f}% btc={bm_btc:.2f}%\n")

    print("Calculando canales (ascendente/descendente/lateral) en ETH y BTC...")
    canales_eth = _canales(df_eth)
    canales_btc = _canales(df_btc)
    print({k: len(v) for k, v in canales_eth.items()}, "(ETH)")
    print({k: len(v) for k, v in canales_btc.items()}, "(BTC)\n")

    techos_eth, suelos_eth = _candidatos_techo(df_eth), _candidatos_suelo(df_eth)
    techos_btc, suelos_btc = _candidatos_techo(df_btc), _candidatos_suelo(df_btc)
    fechas_eth, fechas_btc = df_eth["open_time"], df_btc["open_time"]

    print("=" * 70); print("ETH-AJUSTE (2021-2023)"); print("=" * 70)
    _reporte("TECHO", techos_eth, canales_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, fechas_eth, bm_ajuste)
    _reporte("SUELO", suelos_eth, canales_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, fechas_eth, bm_ajuste)

    print("=" * 70); print("CONFIRMACION 1: ETH-TIEMPO (2023-2025, nunca visto)"); print("=" * 70)
    _reporte("TECHO", techos_eth, canales_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, fechas_eth, bm_tiempo)
    _reporte("SUELO", suelos_eth, canales_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, fechas_eth, bm_tiempo)

    print("=" * 70); print("CONFIRMACION 2: BTC completo (nunca visto)"); print("=" * 70)
    _reporte("TECHO", techos_btc, canales_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, fechas_btc, bm_btc)
    _reporte("SUELO", suelos_btc, canales_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, fechas_btc, bm_btc)
