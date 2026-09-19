"""
Doble suelo, 12-sept-2026 -- espejo METODOLOGICO (no literal) del hallazgo
de doble techo, tras confirmar (`segmentacion_regimen_suelo.py`, corrido
hoy) que el espejo NAIVE ("regimen alcista ya confirmado = encima+subiendo
media200") NO replica: funciona en ETH-ajuste pero se invierte en
ETH-tiempo y BTC (30.5% y 27.6% de acierto, peor que el resto).

Hipotesis nueva a comprobar, sin darla por buena: en doble techo el
regimen que funcionaba era BAJISTA -- un techo que aparece DENTRO de una
caida ya confirmada, cerca todavia del ATH, reconfirma la continuacion de
la caida. El espejo conceptual (no el espejo de "cambiar alcista por
bajista" sin mas) para un suelo seria: un suelo que aparece DENTRO de esa
misma caida ya confirmada (regimen BAJISTA, no alcista), cerca ya del
minimo de esa caida (no del ATH), con el nivel de soporte ya tocado antes
-- el equivalente a "nivel repetido" para techos.

Se usa el modulo compartido `regimen_mercado.py` (extraido hoy mismo,
correccion arquitectonica del usuario) en vez de reimplementar la
clasificacion de regimen aqui.

"Distancia al minimo de la caida actual" = analogo de "distancia al ATH":
en vez de running max, se usa el minimo desde el ULTIMO ATH (el suelo mas
bajo tocado dentro del actual episodio de caida). dist=0 significa "estamos
ahora mismo en el punto mas bajo de la caida hasta la fecha".

Se prueban AMBOS regimenes por separado -- no se asume cual gana.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_suelo_flexible, regimen_mercado
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
from laboratorio.patrones.regimen_mercado import TipoRegimen

DIAS_EXITO = vcp.DIAS_EXITO


def _minimo_desde_ultimo_ath(close: np.ndarray) -> np.ndarray:
    """Para cada dia, el minimo tocado desde el ATH mas reciente hasta
    ese dia (el 'fondo' del episodio de caida en curso)."""
    ath_hasta = np.maximum.accumulate(close)
    n = len(close)
    minimo = np.empty(n)
    ultimo_ath_idx = 0
    corriendo_min = close[0]
    for i in range(n):
        if close[i] >= ath_hasta[i] - 1e-9:  # nuevo ATH -> reinicia el episodio
            ultimo_ath_idx = i
            corriendo_min = close[i]
        else:
            corriendo_min = min(corriendo_min, close[i])
        minimo[i] = corriendo_min
    return minimo


def _candidatos_con_regimen_y_minimo(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_rebote, peso_tiempo, peso_altura = pesos
    candidatos = doble_suelo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    minimo_caida = _minimo_desde_ultimo_ath(close)

    ordenados = sorted(candidatos, key=lambda c: c.idx_fondo2)
    niveles_previos: list[tuple[int, float]] = []
    filas = []
    for c in ordenados:
        tipo, score_regimen = regimen_mercado.clasificar(df, c.idx_fondo2, sma200)
        dist_min = (close[c.idx_fondo2] - minimo_caida[c.idx_fondo2]) / minimo_caida[c.idx_fondo2] * 100

        nivel_actual = (close[c.idx_fondo1] + close[c.idx_fondo2]) / 2
        patron_previo = any(
            idx2p < c.idx_fondo1 - 3 and abs(nivp - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2p, nivp in niveles_previos
        )
        niveles_previos.append((c.idx_fondo2, nivel_actual))

        filas.append({
            "idx_fondo2": c.idx_fondo2, "tipo_regimen": tipo, "score_regimen": score_regimen,
            "dist_min": dist_min, "patron_previo": patron_previo,
        })
    return filas


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _analizar(nombre: str, df: pd.DataFrame, desde, hasta, pesos: tuple):
    print(f"=== {nombre} ===")
    fechas = df["open_time"]
    filas = _candidatos_con_regimen_y_minimo(df, pesos)

    grupos = {
        "TODOS (sin segmentar, referencia)": lambda f: True,
        "regimen BAJISTA": lambda f: f["tipo_regimen"] == TipoRegimen.BAJISTA,
        "regimen ALCISTA": lambda f: f["tipo_regimen"] == TipoRegimen.ALCISTA,
        "regimen NEUTRO": lambda f: f["tipo_regimen"] == TipoRegimen.NEUTRO,
    }

    for nombre_grupo, filtro in grupos.items():
        dist, ret, prev = [], [], []
        for f in filas:
            fecha2 = fechas.iloc[f["idx_fondo2"]]
            if fecha2 < desde or fecha2 >= hasta or not filtro(f):
                continue
            r = _retorno_directo(df, f["idx_fondo2"])
            if r is None:
                continue
            dist.append(f["dist_min"]); ret.append(r); prev.append(f["patron_previo"])
        if len(dist) < 8:
            print(f"  {nombre_grupo}: muestra insuficiente (n={len(dist)})")
            continue
        dist_arr, ret_arr, prev_arr = np.array(dist), np.array(ret), np.array(prev)
        rho, p = spearmanr(dist_arr, ret_arr)
        mediana = np.median(dist_arr)
        cerca = ret_arr[dist_arr <= mediana]
        lejos = ret_arr[dist_arr > mediana]
        con_prev = ret_arr[prev_arr]
        sin_prev = ret_arr[~prev_arr]
        print(f"  {nombre_grupo} (n={len(dist)}): dist_min rho={rho:.3f} p={p:.3f} | "
              f"cerca_min->retorno {cerca.mean():.2f}% | lejos_min->retorno {lejos.mean():.2f}%")
        print(f"    soporte_repetido (n={len(con_prev)}): retorno medio {con_prev.mean():.2f}%"
              if len(con_prev) else "    soporte_repetido: n=0",
              f" | sin_repetido (n={len(sin_prev)}): retorno medio {sin_prev.mean():.2f}%"
              if len(sin_prev) else "sin_repetido: n=0")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_minimo_regimen_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_minimo_regimen_btc")

    # Pesos de FORMA congelados SOLO en ETH-ajuste (mismo proceso que
    # segmentacion_regimen_suelo.py, corrido hoy: (0.2, 0.2, 0.1, 0.5)).
    resultados_grid = []
    for pesos in vcp.PESOS_SUELO:
        filas = vcp._entradas_confirmadas_suelo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, True)
        resultados_grid.append({"pesos": pesos, "ajuste": r})
    pesos_congelados = vcp._mejor(resultados_grid)["pesos"]
    print(f"Pesos de forma congelados (elegidos SOLO en ETH-ajuste): {pesos_congelados}\n")

    _analizar("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, pesos_congelados)
    _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, pesos_congelados)
    _analizar("BTC completo (nunca visto)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, pesos_congelados)
    _analizar("ETH 2017-2021 (nunca usado en ajuste)", df_eth, df_eth["open_time"].min(), vcp.CORTE, pesos_congelados)
