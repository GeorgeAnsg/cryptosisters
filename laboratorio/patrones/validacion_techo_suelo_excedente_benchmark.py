"""15-sept-2026: doble techo y doble suelo se graduaron a `motores/` el
12-sept-2026 usando `validacion_cruzada_pesos.py`, que elige pesos y mide
exito por RETORNO BRUTO. El 14-sept se descubrio (obs. 0013 del log de
task-observer) que un retorno bruto sin restar el benchmark incondicional
del mismo tramo puede parecer senal cuando solo es deriva alcista de
fondo -- y hoy, 15-sept, se ha repetido el mismo patron con canal y con
caida_recuperacion (ambos: excelente en retorno bruto, se hunden o se
vuelven negativos al medir exceso). Este riesgo quedo anotado como
pendiente para techo/suelo pero nunca comprobado -- este script lo cierra.

Reusa la deteccion y confirmacion YA EXISTENTES de
`validacion_cruzada_pesos.py` (`_entradas_confirmadas_suelo`,
`_entradas_confirmadas_techo`) sin duplicarlas. Unico cambio: la seleccion
de pesos y el reporte de resultados usan EXCESO sobre el benchmark
incondicional del mismo tramo exacto, nunca retorno bruto -- misma
metodologia que `validacion_canal_excedente_benchmark.py`.

IMPORTANTE: esto NO reabre el grid de tolerancias de deteccion (Etapa 1),
solo el grid de PESOS_SUELO/PESOS_TECHO ya existente en
doble_suelo_consenso.py/doble_techo_consenso.py, igual que hizo el script
original -- no se gasta presupuesto de intentos de mas.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json

import numpy as np
import pandas as pd

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.doble_suelo_consenso import PESOS_FORMA as PESOS_SUELO
from laboratorio.patrones.doble_techo_consenso import PESOS_FORMA as PESOS_TECHO
from laboratorio.patrones.validacion_cruzada_pesos import (
    CORTE, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, DIAS_EXITO, UMBRALES_EXITO_PCT,
    _entradas_confirmadas_suelo, _entradas_confirmadas_techo,
)


def _benchmark_incondicional(df: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp) -> float:
    fechas = df["open_time"]
    close = df["close"].to_numpy()
    n = len(df)
    retornos = []
    for i in range(n):
        if fechas.iloc[i] < desde or fechas.iloc[i] >= hasta:
            continue
        if i + DIAS_EXITO >= n:
            continue
        retornos.append((close[i + DIAS_EXITO] - close[i]) / close[i] * 100)
    return float(np.mean(retornos)) if retornos else 0.0


def _resumen_excedente(
    df: pd.DataFrame, filas: list, desde: pd.Timestamp, hasta: pd.Timestamp,
    exito_es_subida: bool, benchmark_pct: float,
) -> dict:
    n = len(df)
    fechas = df["open_time"]
    con, sin = [], []
    for idx2, idx_conf in filas:
        fecha2 = fechas.iloc[idx2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        if idx_conf is not None:
            fin_exito = idx_conf + DIAS_EXITO
            if fin_exito >= n:
                continue
            precio0 = df["close"].iloc[idx_conf]
            retorno = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
            con.append(retorno)
        else:
            fin_exito = idx2 + DIAS_EXITO
            if fin_exito >= n:
                continue
            precio0 = df["close"].iloc[idx2]
            retorno = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
            sin.append(retorno)

    def stats(retornos):
        if not retornos:
            return {"n": 0, "exceso_medio_pct": None, "acierto_exceso_pct_rango": None}
        arr = np.array(retornos) - benchmark_pct  # EXCESO, no retorno bruto
        aciertos = []
        for umbral in UMBRALES_EXITO_PCT:
            acierto = (arr >= umbral) if exito_es_subida else (arr <= -umbral)
            aciertos.append(float(acierto.mean() * 100))
        return {
            "n": len(arr),
            "exceso_medio_pct": round(float(arr.mean()), 2),
            "acierto_exceso_pct_rango": [round(min(aciertos), 1), round(max(aciertos), 1)],
        }

    return {"con_confirmacion": stats(con), "sin_confirmacion": stats(sin)}


def _mejor(resultados: list[dict]) -> dict:
    con_datos = [r for r in resultados if r["ajuste"]["con_confirmacion"]["n"] >= 5]
    universo = con_datos if con_datos else resultados
    return max(universo, key=lambda r: (r["ajuste"]["con_confirmacion"]["exceso_medio_pct"] or -999))


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="validacion_techo_suelo_excedente_benchmark")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="validacion_techo_suelo_excedente_benchmark")

    bm_ajuste = _benchmark_incondicional(df_eth, CORTE, CORTE_AJUSTE_FIN)
    bm_tiempo = _benchmark_incondicional(df_eth, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN)
    bm_btc = _benchmark_incondicional(df_btc, CORTE, CORTE_DESARROLLO_FIN)
    print(f"Benchmarks incondicionales ({DIAS_EXITO}d): ajuste={bm_ajuste:.2f}%  tiempo={bm_tiempo:.2f}%  btc={bm_btc:.2f}%\n")

    patrones = [
        ("SUELO", PESOS_SUELO, _entradas_confirmadas_suelo, True),
        ("TECHO", PESOS_TECHO, _entradas_confirmadas_techo, False),
    ]

    for nombre, grid_pesos, fn_entradas, exito_sube in patrones:
        print(f"=== DOBLE {nombre} -- seleccion de pesos por EXCESO sobre benchmark, solo ETH-ajuste ===")
        resultados = []
        for pesos in grid_pesos:
            filas = fn_entradas(df_eth, pesos)
            r_ajuste = _resumen_excedente(df_eth, filas, CORTE, CORTE_AJUSTE_FIN, exito_sube, bm_ajuste)
            resultados.append({"pesos": pesos, "ajuste": r_ajuste})
            print(json.dumps({"pesos": pesos, "ajuste": r_ajuste}, default=str))
        mejor = _mejor(resultados)
        print(f"-> MEJOR combo {nombre} (por exceso, congelado):", mejor["pesos"], mejor["ajuste"])

        filas_frozen = fn_entradas(df_eth, mejor["pesos"])
        conf_tiempo = _resumen_excedente(df_eth, filas_frozen, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, exito_sube, bm_tiempo)
        print(f"\n=== CONFIRMACION 1 ({nombre}): ETH tramo nunca visto -- exceso sobre benchmark({bm_tiempo:.2f}%) ===")
        print(json.dumps(conf_tiempo, default=str))

        filas_btc = fn_entradas(df_btc, mejor["pesos"])
        conf_btc = _resumen_excedente(df_btc, filas_btc, CORTE, CORTE_DESARROLLO_FIN, exito_sube, bm_btc)
        print(f"\n=== CONFIRMACION 2 ({nombre}): BTC completo, pesos congelados -- exceso sobre benchmark({bm_btc:.2f}%) ===")
        print(json.dumps(conf_btc, default=str))
        print()
