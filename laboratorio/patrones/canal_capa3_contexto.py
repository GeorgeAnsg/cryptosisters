"""15-sept-2026: replicando para canal el proceso real que se uso para
graduar doble techo/suelo (12-sept-2026) -- ver motores/doble_techo.py y
laboratorio/patrones/doble_techo_motor_v2.py. Ahi la puntuacion de FORMA
sola nunca fue lo que predijo el resultado -- lo que de verdad discrimino
fue una CAPA 3 de contexto de mercado (regimen + cercania al ATH),
probada como una lista de candidatos aparte y validada con el mismo cruce
de moneda/tiempo, descartando lo que no pasara.

Con canal llevamos toda la sesion intentando que `probabilidad_forma`
(pura geometria) prediga el resultado ella sola -- nunca se probo un
factor de contexto de mercado aparte, que es justo lo que funciono para
techo/suelo. Este script prueba los dos primeros candidatos obvios,
reusando el clasificador YA VALIDADO `motores.regimen_mercado.clasificar`
(no se reimplementa) mas la distancia al ATH:

  - Tipo de regimen (BAJISTA/ALCISTA/NEUTRO) en el momento del pico2.
  - Distancia al ATH en el momento del pico2 (igual que la pieza que mas
    aporto en techo bajista).

Metodologia corregida desde el principio (a diferencia de los intentos
anteriores con canal en esta misma sesion): exceso sobre benchmark
incondicional del mismo tramo, nunca retorno bruto.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json

import numpy as np
import pandas as pd

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.canal_flexible import detectar_ascendente, PESOS_FORMA as PESOS_CANAL
from laboratorio.patrones.validacion_cruzada_pesos import CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, DIAS_EXITO
from motores import regimen_mercado
from motores.regimen_mercado import TipoRegimen

INICIO_AMPLIO = pd.Timestamp("2000-01-01", tz="UTC")
PESOS_SUBE = (0.55, 0.1, 0.15, 0.1, 0.1)  # el mismo usado en las graficas -- pendiente dominante
FRACCION_CONF = 0.35


def _benchmark(df, desde, hasta):
    fechas = df["open_time"]; close = df["close"].to_numpy(); n = len(df)
    rs = [(close[i+DIAS_EXITO]-close[i])/close[i]*100 for i in range(n)
          if desde <= fechas.iloc[i] < hasta and i+DIAS_EXITO < n]
    return float(np.mean(rs)) if rs else 0.0


def _candidatos_con_contexto(df, desde, hasta):
    fechas = df["open_time"]
    close = df["close"].to_numpy()
    sma200 = df["close"].rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    n = len(df)

    cands = detectar_ascendente(df, peso_pendiente=PESOS_SUBE[0], peso_paralelismo=PESOS_SUBE[1],
                                 peso_ancho=PESOS_SUBE[2], peso_consistencia=PESOS_SUBE[3], peso_contencion=PESOS_SUBE[4])
    filas = []
    for c in cands:
        fecha2 = fechas.iloc[c.idx_pico2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        tipo, score_regimen = regimen_mercado.clasificar(df, c.idx_pico2, sma200)
        dist_ath_pct = (ath_hasta[c.idx_pico2] - c.precio_pico2) / ath_hasta[c.idx_pico2] * 100

        dias_conf = max(DIAS_EXITO, round(FRACCION_CONF * c.dias_total))
        fin_conf = min(c.idx_pico2 + 1 + int(dias_conf), n)
        idx_confirmacion = None
        slope = (c.precio_pico2 - c.precio_pico1) / (c.idx_pico2 - c.idx_pico1)
        for x in range(c.idx_pico2 + 1, fin_conf):
            if close[x] > c.precio_pico2 + slope * (x - c.idx_pico2):
                idx_confirmacion = x
                break
        if idx_confirmacion is None or idx_confirmacion + DIAS_EXITO >= n:
            continue
        precio0 = close[idx_confirmacion]
        retorno = (close[idx_confirmacion + DIAS_EXITO] - precio0) / precio0 * 100

        filas.append({
            "idx_pico2": c.idx_pico2, "fecha": str(fecha2.date()), "retorno": retorno,
            "tipo_regimen": tipo.value, "dist_ath_pct": round(float(dist_ath_pct), 1),
            "probabilidad_forma": c.probabilidad_forma,
        })
    return filas


def _reporte(filas, bm, etiqueta):
    print(f"\n--- {etiqueta} (benchmark {bm:.2f}%, n_total={len(filas)}) ---")
    for tipo in ["bajista", "alcista", "neutro"]:
        grupo = [f for f in filas if f["tipo_regimen"] == tipo]
        if not grupo:
            print(f"  {tipo}: sin datos")
            continue
        arr = np.array([f["retorno"] for f in grupo]) - bm
        print(f"  {tipo}: n={len(arr)} exceso_medio={arr.mean():.2f}%")

    # distancia al ATH: dividir en cerca (<50%) vs lejos (>=50%), umbral
    # exploratorio -- si esto separa bien, se barre un rango de verdad despues.
    cerca = [f for f in filas if f["dist_ath_pct"] < 50]
    lejos = [f for f in filas if f["dist_ath_pct"] >= 50]
    for nombre, grupo in [("cerca ATH (<50%)", cerca), ("lejos ATH (>=50%)", lejos)]:
        if not grupo:
            print(f"  {nombre}: sin datos"); continue
        arr = np.array([f["retorno"] for f in grupo]) - bm
        print(f"  {nombre}: n={len(arr)} exceso_medio={arr.mean():.2f}%")


UMBRAL_ATH_GRID = [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]


def _exceso_bajo_umbral(filas, bm, umbral, n_min=8):
    grupo = [f for f in filas if f["dist_ath_pct"] < umbral]
    if len(grupo) < n_min:
        return None
    arr = np.array([f["retorno"] for f in grupo]) - bm
    return {"n": len(arr), "exceso_medio_pct": round(float(arr.mean()), 2)}


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_capa3_contexto")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_capa3_contexto")

    bm_ajuste = _benchmark(df_eth, INICIO_AMPLIO, CORTE_AJUSTE_FIN)
    bm_tiempo = _benchmark(df_eth, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN)
    bm_btc = _benchmark(df_btc, INICIO_AMPLIO, CORTE_DESARROLLO_FIN)

    filas_ajuste = _candidatos_con_contexto(df_eth, INICIO_AMPLIO, CORTE_AJUSTE_FIN)
    _reporte(filas_ajuste, bm_ajuste, "ETH AJUSTE (todo el historico <2023)")

    filas_tiempo = _candidatos_con_contexto(df_eth, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN)
    _reporte(filas_tiempo, bm_tiempo, "ETH CONFIRMACION TIEMPO (2023-2025, nunca visto)")

    filas_btc = _candidatos_con_contexto(df_btc, INICIO_AMPLIO, CORTE_DESARROLLO_FIN)
    _reporte(filas_btc, bm_btc, "BTC CONFIRMACION MONEDA (completo, nunca visto)")

    print("\n=== BARRIDO de umbral de distancia al ATH (elegido SOLO en ETH-ajuste) ===")
    for umbral in UMBRAL_ATH_GRID:
        r_ajuste = _exceso_bajo_umbral(filas_ajuste, bm_ajuste, umbral)
        r_tiempo = _exceso_bajo_umbral(filas_tiempo, bm_tiempo, umbral, n_min=1)
        r_btc = _exceso_bajo_umbral(filas_btc, bm_btc, umbral, n_min=1)
        print(json.dumps({"umbral_ath_pct": umbral, "ajuste": r_ajuste, "confirmacion_tiempo": r_tiempo, "confirmacion_btc": r_btc}))
