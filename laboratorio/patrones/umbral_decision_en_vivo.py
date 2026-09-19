"""
Pregunta del usuario (11-sept-2026): dado `probabilidad_en_vivo_techo.py`
(la confianza que sube dia a dia mientras se forma el doble techo), ?a
partir de que nivel de confianza merece la pena abrir el short, EN VEZ DE
esperar a la confirmacion completa del dia 3?

Metodologia (regla del propio proyecto -- "no absolutos"): no se elige un
umbral a dedo. Se prueba un RANGO de umbrales de confianza (30%, 40%...
90%) y, para cada uno, se mide con datos reales que habria pasado si se
hubiera abierto el short justo el primer dia en que la confianza en vivo
alcanzo ese nivel -- nunca un unico numero.

Para cada candidato de doble techo detectado:
  1. Se calcula probabilidad_en_vivo en los dias 0, 1, 2, 3 (retroactivo,
     usando `probabilidad_en_vivo_techo.calcular_en_vivo`).
  2. Para cada umbral del rango, se busca el PRIMER dia en que la
     confianza alcanza ese umbral.
  3. Si lo alcanza, se mide el retorno real desde ESE dia (no desde la
     confirmacion final) a DIAS_EXITO dias vista -- igual que el resto
     del proyecto mide "exito" (rango de umbrales de exito, nunca uno).

Igual que en el resto de Fase B: pesos ajustados SOLO en ETH-ajuste,
confirmados sin tocar nada en ETH-tiempo (nunca visto) y BTC (moneda
nunca vista).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible
from laboratorio.patrones.probabilidad_en_vivo_techo import calcular_en_vivo

UMBRALES_CONFIANZA = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT  # [2, 3, 5, 7, 10] -- mismo rango que el resto del proyecto
DIAS_EXITO = vcp.DIAS_EXITO  # 15


def _trayectorias(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    """Para cada candidato de doble techo, calcula probabilidad_en_vivo en
    los dias 0-3 y guarda el idx real (para poder medir retorno despues)."""
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    filas = []
    for c in candidatos:
        trayectoria = {}
        for dia in range(4):
            r = calcular_en_vivo(df, c.idx_techo2, dia)
            trayectoria[dia] = r.probabilidad_en_vivo if r is not None else None
        filas.append({"idx_techo2": c.idx_techo2, "trayectoria": trayectoria})
    return filas


def _resultado_umbral(df: pd.DataFrame, filas: list[dict], umbral: float, desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    n = len(df)
    fechas = df["open_time"]
    retornos = []
    dias_entrada = []
    for f in filas:
        fecha2 = fechas.iloc[f["idx_techo2"]]
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
        idx_entrada = f["idx_techo2"] + dia_entrada
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
        acierto = arr <= -u  # exito de un short = precio baja
        aciertos_por_umbral_exito.append(float(acierto.mean() * 100))
    return {
        "n": len(arr),
        "dia_entrada_medio": round(float(np.mean(dias_entrada)), 2),
        "acierto_pct_medio": round(float(np.mean(aciertos_por_umbral_exito)), 1),
        "acierto_pct_rango": [round(min(aciertos_por_umbral_exito), 1), round(max(aciertos_por_umbral_exito), 1)],
        "retorno_medio_pct": round(float(arr.mean()), 2),
    }


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="umbral_decision_en_vivo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="umbral_decision_en_vivo_btc")

    # pesos de forma congelados en ETH-ajuste, igual que en el resto de Fase B
    resultados_techo = []
    for pesos in vcp.PESOS_TECHO:
        filas = vcp._entradas_confirmadas_techo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
        resultados_techo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_techo)["pesos"]
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
