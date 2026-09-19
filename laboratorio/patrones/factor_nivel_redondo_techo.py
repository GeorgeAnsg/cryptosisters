"""
Idea nueva (12-sept-2026): si el precio del segundo pico (techo2) cae muy
cerca de un numero "redondo" / psicologico (30.000, 50.000, 100.000 ...),
deberia ser mas probable que actue de resistencia real -- mucha gente
vigila y coloca ordenes de venta justo en esos niveles.

Definicion continua de "redondo": para cada orden de magnitud se generan
los niveles candidatos 1, 2, 5, 10, 20, 50 (x10^n) -- son los numeros que
la gente realmente usa como referencia mental, no solo las potencias de
10. Se mide la distancia porcentual del precio del techo2 al nivel
redondo mas cercano. Cuanto MENOR la distancia, mas "redondo" es el pico.

Se prueba como dimension continua (correlacion + terciles) y con un rango
de tolerancias, nunca un corte binario.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible

DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
PESOS_FORMA = (0.35, 0.25, 0.1, 0.3)


def _distancia_pct_nivel_redondo(precio: float) -> float:
    """Distancia porcentual al nivel redondo (1/2/5 x 10^n) mas cercano."""
    if precio <= 0:
        return 100.0
    exp = np.floor(np.log10(precio))
    candidatos = []
    for e in (exp - 1, exp, exp + 1):
        for base in (1, 2, 5, 10):
            candidatos.append(base * 10 ** e)
    candidatos = np.array(candidatos)
    mas_cercano = candidatos[np.argmin(np.abs(candidatos - precio))]
    return abs(precio - mas_cercano) / precio * 100


def _candidatos(df: pd.DataFrame, pesos: tuple) -> list:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    return doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _analizar(nombre: str, df: pd.DataFrame, desde, hasta):
    print(f"=== {nombre} ===")
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    candidatos = _candidatos(df, PESOS_FORMA)

    distancias, retornos = [], []
    for c in candidatos:
        fecha2 = fechas.iloc[c.idx_techo2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        r = _retorno_directo(df, c.idx_techo2)
        if r is None:
            continue
        distancias.append(_distancia_pct_nivel_redondo(close[c.idx_techo2]))
        retornos.append(r)

    if len(distancias) < 5:
        print("  muestra insuficiente")
        return
    distancias_arr, retornos_arr = np.array(distancias), np.array(retornos)
    rho, p = spearmanr(distancias_arr, retornos_arr)
    print(f"  n={len(distancias)}  correlacion distancia-al-redondo vs retorno: rho={rho:.3f} p={p:.3f}")
    print("  (si la idea es correcta: MENOS distancia -> MAS bajada -> rho POSITIVO)")

    terciles = np.quantile(distancias_arr, [1 / 3, 2 / 3])
    cerca = retornos_arr[distancias_arr <= terciles[0]]
    medio = retornos_arr[(distancias_arr > terciles[0]) & (distancias_arr <= terciles[1])]
    lejos = retornos_arr[distancias_arr > terciles[1]]

    def resumen(nombre_grupo, arr):
        if len(arr) == 0:
            print(f"    {nombre_grupo}: sin datos")
            return
        aciertos = [float((arr <= -u).mean() * 100) for u in UMBRALES_EXITO_PCT]
        print(f"    {nombre_grupo} (n={len(arr)}): retorno medio={arr.mean():.2f}%, acierto medio={np.mean(aciertos):.1f}%")

    resumen("MUY CERCA de nivel redondo", cerca)
    resumen("distancia media", medio)
    resumen("LEJOS de cualquier nivel redondo", lejos)
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_nivel_redondo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_nivel_redondo_btc")

    _analizar("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN)
    _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    _analizar("BTC completo (nunca visto)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
