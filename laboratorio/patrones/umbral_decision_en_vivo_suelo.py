"""
Espejo de `umbral_decision_en_vivo.py` para el suelo: dado
`probabilidad_en_vivo_suelo.py` (la confianza que sube dia a dia mientras
se forma el doble suelo), ¿a partir de que nivel de confianza merece la
pena abrir el long, en vez de esperar a la confirmacion completa del dia 3?

Misma metodologia (no absolutos): rango de umbrales de confianza, nunca
uno solo; para cada uno, el retorno real desde el PRIMER dia en que la
confianza en vivo alcanza ese umbral, medido a DIAS_EXITO dias vista.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_suelo_flexible
from laboratorio.patrones.probabilidad_en_vivo_suelo import calcular_en_vivo

UMBRALES_CONFIANZA = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
DIAS_EXITO = vcp.DIAS_EXITO


def _trayectorias(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_rebote, peso_tiempo, peso_altura = pesos
    candidatos = doble_suelo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    filas = []
    for c in candidatos:
        trayectoria = {}
        for dia in range(4):
            r = calcular_en_vivo(df, c.idx_fondo2, dia)
            trayectoria[dia] = r.probabilidad_en_vivo if r is not None else None
        filas.append({"idx_fondo2": c.idx_fondo2, "trayectoria": trayectoria})
    return filas


def _resultado_umbral(df: pd.DataFrame, filas: list[dict], umbral: float, desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    n = len(df)
    fechas = df["open_time"]
    retornos = []
    dias_entrada = []
    for f in filas:
        fecha2 = fechas.iloc[f["idx_fondo2"]]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        dia_entrada = None
        for dia in range(4):
            p = f["trayectoria"][dia]
            if p is not None and p >= umbral:
                dia_entrada = dia
                break
        if dia_entrada is None:
            continue
        idx_entrada = f["idx_fondo2"] + dia_entrada
        fin = idx_entrada + DIAS_EXITO
        if fin >= n:
            continue
        precio0 = df["close"].iloc[idx_entrada]
        retorno = (df["close"].iloc[fin] - precio0) / precio0 * 100
        retornos.append(retorno)
        dias_entrada.append(dia_entrada)

    if not retornos:
        return {"n": 0, "dia_entrada_medio": None, "acierto_pct_medio": None, "acierto_pct_rango": None, "retorno_medio_pct": None}
    arr = np.array(retornos)
    aciertos_por_umbral_exito = []
    for u in UMBRALES_EXITO_PCT:
        acierto = arr >= u  # exito de un long = precio sube
        aciertos_por_umbral_exito.append(float(acierto.mean() * 100))
    return {
        "n": len(arr),
        "dia_entrada_medio": round(float(np.mean(dias_entrada)), 2),
        "acierto_pct_medio": round(float(np.mean(aciertos_por_umbral_exito)), 1),
        "acierto_pct_rango": [round(min(aciertos_por_umbral_exito), 1), round(max(aciertos_por_umbral_exito), 1)],
        "retorno_medio_pct": round(float(arr.mean()), 2),
    }


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="umbral_decision_en_vivo_suelo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="umbral_decision_en_vivo_suelo_btc")

    resultados_suelo = []
    for pesos in vcp.PESOS_SUELO:
        filas = vcp._entradas_confirmadas_suelo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, True)
        resultados_suelo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_suelo)["pesos"]
    print(f"Pesos de forma congelados (en ETH-ajuste): {mejor_pesos}\n")

    print("Calculando trayectorias en vivo (dia 0-3) para todos los candidatos...")
    trayectorias_eth = _trayectorias(df_eth, mejor_pesos)
    trayectorias_btc = _trayectorias(df_btc, mejor_pesos)
    print(f"  ETH: {len(trayectorias_eth)} candidatos, BTC: {len(trayectorias_btc)} candidatos\n")

    cortes = [
        ("ETH ajuste (2021-2023)", df_eth, trayectorias_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN),
        ("ETH tiempo (2023-2025, nunca visto)", df_eth, trayectorias_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN),
        ("BTC completo (moneda nunca vista)", df_btc, trayectorias_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN),
    ]

    for nombre, df, filas, desde, hasta in cortes:
        print(f"=== {nombre} ===")
        for umbral in UMBRALES_CONFIANZA:
            res = _resultado_umbral(df, filas, umbral, desde, hasta)
            print(f"  confianza >= {int(umbral*100)}%: {json.dumps(res)}")
        print()
