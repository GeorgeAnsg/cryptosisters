"""
Doble suelo, 12-sept-2026 -- version a escala del combo espejo encontrado
en `segmentacion_minimo_por_regimen.py`: dentro de regimen ALCISTA, "lejos
del minimo" (alcista ya mas maduro/consolidado) gana a "cerca del minimo"
en LOS 4 CORTES probados (ETH-ajuste, ETH-tiempo, BTC, ETH-2017-21),
aunque no significativo por separado en ninguno (muestras pequenas).

Aqui se agrupa el combo regimen ALCISTA + soporte ya repetido antes
(patron_previo, el equivalente de "nivel repetido" del techo) en las 5
monedas (BTC/ETH/XRP/SOL/BNB, las 3 ultimas resampleadas de 4h a diario,
igual que se hizo para el techo) para un Monte Carlo solido, y se
desglosa por dist_min (cerca/lejos del minimo) DENTRO del combo para
comprobar si esa pieza extra aporta a escala.

Filtro del combo (mirror exacto de _candidatos_combo_fuerte del techo,
que usaba debajo+cayendo+patron_previo sin filtro de ATH): aqui,
encima+subiendo (via regimen_mercado.clasificar) + patron_previo. La
distancia al minimo se mide como dato continuo, no como filtro (misma
logica que "no absolutos": no cortar candidatos, solo puntuar/segmentar).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from datos.cargar import cargar_ohlcv
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_suelo_flexible, regimen_mercado
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
from laboratorio.patrones.regimen_mercado import TipoRegimen

DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
N_SIMULACIONES = 5000


def _resample_diario(par: str) -> pd.DataFrame:
    df = cargar_ohlcv(par, "4h")
    diario = df.set_index("open_time").resample("1D").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna().reset_index()
    return diario


def _minimo_desde_ultimo_ath(close: np.ndarray) -> np.ndarray:
    ath_hasta = np.maximum.accumulate(close)
    n = len(close)
    minimo = np.empty(n)
    corriendo_min = close[0]
    for i in range(n):
        if close[i] >= ath_hasta[i] - 1e-9:
            corriendo_min = close[i]
        else:
            corriendo_min = min(corriendo_min, close[i])
        minimo[i] = corriendo_min
    return minimo


def _candidatos_combo_fuerte(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_rebote, peso_tiempo, peso_altura = pesos
    candidatos = doble_suelo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    minimo_caida = _minimo_desde_ultimo_ath(close)
    ordenados = sorted(candidatos, key=lambda c: c.idx_fondo2)
    niveles_previos: list[tuple[int, float]] = []
    n = len(df)
    filas = []
    for c in ordenados:
        tipo, _score_regimen = regimen_mercado.clasificar(df, c.idx_fondo2, sma200)
        nivel_actual = (close[c.idx_fondo1] + close[c.idx_fondo2]) / 2
        patron_previo = any(
            idx2p < c.idx_fondo1 - 3 and abs(nivp - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2p, nivp in niveles_previos
        )
        niveles_previos.append((c.idx_fondo2, nivel_actual))
        if not (tipo == TipoRegimen.ALCISTA and patron_previo):
            continue
        dist_min = (close[c.idx_fondo2] - minimo_caida[c.idx_fondo2]) / minimo_caida[c.idx_fondo2] * 100
        fin = c.idx_fondo2 + DIAS_EXITO
        if fin >= n:
            continue
        precio0 = close[c.idx_fondo2]
        retorno = (close[fin] - precio0) / precio0 * 100
        filas.append({"idx_fondo2": c.idx_fondo2, "dist_min": dist_min, "retorno": retorno})
    return filas


def _monte_carlo(retornos: np.ndarray, umbral: float, rng: np.random.default_rng) -> float:
    """Exito aqui = SUBIR al menos `umbral`% (mirror del descenso del techo)."""
    aciertos_reales = (retornos >= umbral).mean()
    media_global = retornos.mean()
    centrado = retornos - media_global
    n = len(retornos)
    resultados = np.array([
        (rng.choice(centrado, size=n, replace=True) >= umbral).mean()
        for _ in range(N_SIMULACIONES)
    ])
    return float((resultados >= aciertos_reales).mean())


if __name__ == "__main__":
    print("Cargando y resampleando XRP, SOL, BNB (4h -> diario)...")
    monedas = {
        "ETH": cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="validacion_multi_combo_suelo_eth"),
        "BTC": cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="validacion_multi_combo_suelo_btc"),
        "XRP": _resample_diario("XRPUSDT"),
        "SOL": _resample_diario("SOLUSDT"),
        "BNB": _resample_diario("BNBUSDT"),
    }

    df_eth = monedas["ETH"]
    resultados_grid = []
    for pesos in vcp.PESOS_SUELO:
        filas = vcp._entradas_confirmadas_suelo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, True)
        resultados_grid.append({"pesos": pesos, "ajuste": r})
    pesos_congelados = vcp._mejor(resultados_grid)["pesos"]
    print(f"Pesos de forma congelados (elegidos SOLO en ETH-ajuste): {pesos_congelados}\n")

    todas_filas = []
    print()
    for nombre, df in monedas.items():
        filas = _candidatos_combo_fuerte(df, pesos_congelados)
        rets = [f["retorno"] for f in filas]
        todas_filas.extend(filas)
        if rets:
            arr = np.array(rets)
            print(f"{nombre}: n={len(arr)}  retorno medio={arr.mean():.2f}%  "
                  f"acierta +5%: {(arr>=5).mean()*100:.0f}%  acierta +10%: {(arr>=10).mean()*100:.0f}%")
        else:
            print(f"{nombre}: sin candidatos con el combo completo")

    todos = np.array([f["retorno"] for f in todas_filas])
    print()
    print(f"=== CONJUNTO DE LAS 5 MONEDAS (n={len(todos)}) ===")
    print(f"retorno medio: {todos.mean():.2f}%  (mediana: {np.median(todos):.2f}%)")

    rng = np.random.default_rng(20260912)
    print()
    print("Monte Carlo (5000 simulaciones) -- probabilidad de que este resultado sea casualidad:")
    for umbral in UMBRALES_EXITO_PCT:
        acierto_real = (todos >= umbral).mean() * 100
        p = _monte_carlo(todos, umbral, rng)
        print(f"  subir al menos {umbral}%: acierta {acierto_real:.0f}% de las veces ({acierto_real/10:.1f} de cada 10) -- p={p:.4f}")

    dist_min_arr = np.array([f["dist_min"] for f in todas_filas])
    mediana = np.median(dist_min_arr)
    cerca = todos[dist_min_arr <= mediana]
    lejos = todos[dist_min_arr > mediana]
    print()
    print(f"=== DESGLOSE por distancia al minimo dentro del combo (mediana={mediana:.1f}%) ===")
    print(f"cerca del minimo (n={len(cerca)}): retorno medio {cerca.mean():.2f}%  acierta +5%: {(cerca>=5).mean()*100:.0f}%")
    print(f"lejos del minimo (n={len(lejos)}): retorno medio {lejos.mean():.2f}%  acierta +5%: {(lejos>=5).mean()*100:.0f}%")
