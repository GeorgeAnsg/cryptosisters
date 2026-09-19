"""15-sept-2026: el usuario, mirando el grafico interactivo de canales
(`laboratorio/patrones/canales_detectados.html`... ver artifact), noto a
ojo que los candidatos de probabilidad>=0.62 se veian "bastante bien
detectados". La comprobacion numerica sobre solo ETH 2021-2024 (n=18-26
por grupo, `validacion_canal_excedente_benchmark.py`) no habia mostrado
correlacion -- pero esa muestra resulto ser demasiado pequeña: al ampliar
al historico completo de ETH (desde 2017, cargado sin querer en el grafico
que se le enseño), la relacion probabilidad->exceso SI aparece (n=14 vs 55
en confirmados, +6.02% vs +2.86% de exceso). Esto añade el UMBRAL DE
PROBABILIDAD MINIMA como una dimension mas del barrido cruzado -- elegido
solo en ETH-ajuste (ahora ampliado a TODO el historico ETH anterior a
2023, no solo 2021-2023, para tener mas datos de los que se aprendio la
leccion de arriba), confirmado en ETH-tiempo (2023-2025, nunca visto) y en
BTC completo (moneda nunca vista). Nunca un umbral fijo elegido a ojo
sin barrer -- UMBRAL_PROB_GRID es un rango, igual que el resto de "no
absolutos" del proyecto.

Reusa `_entradas_confirmadas_canal` y el benchmark de
`validacion_canal_excedente_benchmark.py` -- no se duplica logica de
deteccion/confirmacion.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json

import numpy as np
import pandas as pd

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.canal_flexible import PESOS_FORMA as PESOS_CANAL
from laboratorio.patrones.validacion_cruzada_pesos import (
    CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, DIAS_EXITO,
    FRACCIONES_CONFIRMACION_CANAL, UMBRALES_EXITO_PCT,
    _entradas_confirmadas_canal,
)
from laboratorio.patrones.canal_flexible import detectar_ascendente

# Ajuste ampliado: TODO el historico ETH anterior a CORTE_AJUSTE_FIN, no
# solo desde 2021 -- mas datos, menos ruido de muestra pequeña (la leccion
# que motivo este script).
INICIO_AJUSTE_AMPLIO = pd.Timestamp("2000-01-01", tz="UTC")

UMBRAL_PROB_GRID = [0.0, 0.3, 0.45, 0.55, 0.62, 0.70, 0.75, 0.80, 0.85, 0.90]


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


def _entradas_confirmadas_canal_con_prob(df, pesos, direccion, fraccion_confirmacion):
    """Como _entradas_confirmadas_canal pero devolviendo tambien
    probabilidad_forma por candidato, para poder filtrar por umbral
    despues sin re-detectar en cada punto del grid de umbral."""
    fn = detectar_ascendente
    peso_pendiente, peso_paralelismo, peso_ancho, peso_consistencia, peso_contencion = pesos
    candidatos = fn(
        df, peso_pendiente=peso_pendiente, peso_paralelismo=peso_paralelismo, peso_ancho=peso_ancho,
        peso_consistencia=peso_consistencia, peso_contencion=peso_contencion,
    )
    # nota: se recalcula aqui en vez de reusar _entradas_confirmadas_canal
    # porque esa funcion no expone probabilidad_forma en su retorno.
    close = df["close"].to_numpy()
    n = len(df)
    filas = []
    for c in candidatos:
        dias_confirmacion = max(DIAS_EXITO, round(fraccion_confirmacion * c.dias_total))
        fin_conf = min(c.idx_pico2 + 1 + int(dias_confirmacion), n)
        idx_confirmacion = None
        slope_abs = (c.precio_pico2 - c.precio_pico1) / (c.idx_pico2 - c.idx_pico1)
        for x in range(c.idx_pico2 + 1, fin_conf):
            proyeccion = c.precio_pico2 + slope_abs * (x - c.idx_pico2)
            if close[x] > proyeccion:
                idx_confirmacion = x
                break
        filas.append((c.idx_pico2, idx_confirmacion, c.probabilidad_forma))
    return filas


def _resumen_excedente_prob(df, filas, desde, hasta, benchmark_pct, umbral_prob):
    n = len(df)
    fechas = df["open_time"]
    con = []
    for idx2, idx_conf, prob in filas:
        if prob < umbral_prob:
            continue
        fecha2 = fechas.iloc[idx2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        if idx_conf is None:
            continue
        fin_exito = idx_conf + DIAS_EXITO
        if fin_exito >= n:
            continue
        precio0 = df["close"].iloc[idx_conf]
        retorno = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
        con.append(retorno)
    if not con:
        return {"n": 0, "exceso_medio_pct": None}
    arr = np.array(con) - benchmark_pct
    return {"n": len(arr), "exceso_medio_pct": round(float(arr.mean()), 2)}


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="validacion_canal_umbral_probabilidad")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="validacion_canal_umbral_probabilidad")

    bm_ajuste = _benchmark_incondicional(df_eth, INICIO_AJUSTE_AMPLIO, CORTE_AJUSTE_FIN)
    bm_tiempo = _benchmark_incondicional(df_eth, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN)
    bm_btc = _benchmark_incondicional(df_btc, INICIO_AJUSTE_AMPLIO, CORTE_DESARROLLO_FIN)
    print(f"Benchmarks: ajuste(ETH<2023, todo el historico)={bm_ajuste:.2f}%  "
          f"tiempo(ETH 2023-25)={bm_tiempo:.2f}%  btc(completo)={bm_btc:.2f}%\n")

    resultados = []
    for pesos in PESOS_CANAL:
        for fraccion in FRACCIONES_CONFIRMACION_CANAL:
            filas = _entradas_confirmadas_canal_con_prob(df_eth, pesos, "subida", fraccion)
            for umbral_prob in UMBRAL_PROB_GRID:
                r = _resumen_excedente_prob(df_eth, filas, INICIO_AJUSTE_AMPLIO, CORTE_AJUSTE_FIN, bm_ajuste, umbral_prob)
                resultados.append({"pesos": pesos, "fraccion": fraccion, "umbral_prob": umbral_prob, "ajuste": r, "_filas": filas})

    con_datos = [r for r in resultados if r["ajuste"]["n"] >= 8]
    universo = con_datos if con_datos else resultados
    print("=== TOP 10 combinaciones por exceso en ajuste (n>=8), CON su confirmacion en los 2 tramos nunca vistos ===")
    top10 = sorted(con_datos, key=lambda r: -(r["ajuste"]["exceso_medio_pct"] or -999))[:10]
    for r in top10:
        filas_tiempo = _entradas_confirmadas_canal_con_prob(df_eth, r["pesos"], "subida", r["fraccion"])
        conf_tiempo = _resumen_excedente_prob(df_eth, filas_tiempo, CORTE_AJUSTE_FIN, CORTE_DESARROLLO_FIN, bm_tiempo, r["umbral_prob"])
        filas_btc = _entradas_confirmadas_canal_con_prob(df_btc, r["pesos"], "subida", r["fraccion"])
        conf_btc = _resumen_excedente_prob(df_btc, filas_btc, INICIO_AJUSTE_AMPLIO, CORTE_DESARROLLO_FIN, bm_btc, r["umbral_prob"])
        print(json.dumps({
            "pesos": r["pesos"], "fraccion": r["fraccion"], "umbral_prob": r["umbral_prob"],
            "ajuste": r["ajuste"], "confirmacion_tiempo": conf_tiempo, "confirmacion_btc": conf_btc,
        }))
