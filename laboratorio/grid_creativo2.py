"""
Segunda ronda de ideas creativas para el grid, partiendo ya del hallazgo
bueno de grid_creativo.py (objetivo desacoplado del espaciado, mult~1.5).
El usuario señala que 431 trades/año (~1.2/dia) ya se acerca a "una vez al
dia" y pide seguir insistiendo, aunque sean ideas locas.

Tres mecanismos NUEVOS, todos построен sobre grid_adaptativo.simular() con
k_atr_objetivo_mult ya adoptado:

1. Timeframe diario (1d) en vez de 4h -- mismo mecanismo, misma logica,
   simplemente menos "ruido intradia" tocando niveles. Nunca probado a
   este timeframe. velas_recentrado escalado a las mismas ~30 dias
   naturales (180 velas de 4h = 30 dias -> 30 velas de 1d = 30 dias).

2. Objetivo escalonado por profundidad de nivel: los niveles mas profundos
   (mayor caida para activarse) tienen un objetivo TODAVIA mas lejano que
   los niveles superficiales -- la intuicion es que una caida mas grande
   sugiere mas "cuerda" para un rebote mas grande. Implementado como
   k_atr_objetivo_mult efectivo = objetivo_base + objetivo_paso * idx_nivel.

3. Grid combinado con doble suelo/techo como "mascara de calidad" --  NO
   bloquear entradas fuera de la señal (eso ya sabemos que rompe el grid),
   sino usar la señal de Doble suelo/techo (ya confirmada, ver
   doble_suelo.py) como disparador de un objetivo EXTRA amplio en niveles
   que caen dentro de su ventana -- ya existe en la API como
   `senal_refuerzo`/`mult_espaciado_reforzado`, solo hay que conectarlo con
   la señal real en vez de una sintetica.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from datos.cargar import cargar_ohlcv
from laboratorio.grid_adaptativo import simular, evaluar_capital, calcular_atr, calcular_tendencia_fuerte
from laboratorio.doble_suelo import calcular_indicadores as calc_ind_ds, calcular_senales as calc_sen_ds

BASE = dict(n_niveles=3, espaciado_dinamico=True, stop_bajo_rejilla=2.0)


def metricas(df, res, n_niveles=3):
    capital, dd = evaluar_capital(res, n_niveles)
    n_trades = len(res.trades)
    n_anos = (df["open_time"].iloc[-1] - df["open_time"].iloc[0]).days / 365.25
    trades_ano = n_trades / n_anos if n_anos > 0 else float("nan")
    calmar = (capital - 100) / abs(dd) if dd != 0 else float("nan")
    return capital, dd, calmar, n_trades, trades_ano


def experimento_1_timeframe_diario():
    print("\n### Experimento 1: mismo mecanismo, timeframe 1d en vez de 4h ###")
    print(f"{'par':<10} {'tf':<4} {'capital':>9} {'drawdown':>9} {'calmar':>8} {'trades':>7} {'trades/año':>11}")
    for par in ["BTCUSDT", "ETHUSDT"]:
        for tf, velas_recentrado, k_espaciado, k_tendencia in [
            ("4h", 180, 0.5, 1.5),
            ("1d", 30, 0.5, 1.5),
        ]:
            df = cargar_ohlcv(par, tf, ruta_base="/Users/jorgeansotegui/Desktop/corvus4/datos/crudo")
            res = simular(df, k_atr_espaciado=k_espaciado, k_atr_espaciado_tendencia=k_tendencia,
                          velas_recentrado=velas_recentrado, k_atr_objetivo_mult=1.5, **BASE)
            capital, dd, calmar, n_trades, trades_ano = metricas(df, res)
            print(f"{par:<10} {tf:<4} {capital:9.1f} {dd:9.1f} {calmar:8.1f} {n_trades:7d} {trades_ano:11.1f}")


def simular_objetivo_por_nivel(df, n_niveles, k_atr_espaciado, k_atr_espaciado_tendencia,
                                velas_recentrado, stop_bajo_rejilla, objetivo_base, objetivo_paso,
                                ventana_atr=14):
    """Copia minima de simular() con objetivo dependiente de idx_nivel -- no
    cabe en la API generica de k_atr_objetivo_mult (que es un escalar), asi
    que se prototipa aqui en vez de complicar grid_adaptativo.py con un
    parametro mas para una idea que aun no esta validada."""
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    atr = calcular_atr(df, ventana_atr).to_numpy()
    tendencia_fuerte = calcular_tendencia_fuerte(df).to_numpy()
    n = len(df)
    from laboratorio.grid_adaptativo import TradeGrid, ResultadoGrid
    resultado = ResultadoGrid()

    def nueva_rejilla(i):
        k = k_atr_espaciado_tendencia if tendencia_fuerte[i] else k_atr_espaciado
        espaciado = k * atr[i]
        centro = close[i]
        niveles_compra = [centro - espaciado * kk for kk in range(1, n_niveles + 1)]
        return centro, espaciado, niveles_compra

    idx0 = ventana_atr
    while idx0 < n and np.isnan(atr[idx0]):
        idx0 += 1
    if idx0 >= n:
        return resultado

    centro, espaciado, niveles_compra = nueva_rejilla(idx0)
    posiciones_abiertas: dict[int, tuple[int, float]] = {}
    idx_ultimo_recentrado = idx0

    for i in range(idx0, n):
        nivel_mas_bajo = min(niveles_compra)
        if close[i] < nivel_mas_bajo - stop_bajo_rejilla * espaciado and posiciones_abiertas:
            for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, close[i], "stop_rejilla", idx_nivel=idx_nivel))
            posiciones_abiertas = {}
            resultado.n_stops_rejilla += 1
            centro, espaciado, niveles_compra = nueva_rejilla(i)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i
            continue

        cambio_regimen = i > 0 and tendencia_fuerte[i] != tendencia_fuerte[i - 1]
        if i - idx_ultimo_recentrado >= velas_recentrado or cambio_regimen:
            centro, espaciado, niveles_compra = nueva_rejilla(i)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i

        for idx_nivel, nivel in enumerate(niveles_compra):
            if idx_nivel in posiciones_abiertas:
                continue
            if low[i] <= nivel:
                posiciones_abiertas[idx_nivel] = (i, nivel)

        for idx_nivel in list(posiciones_abiertas.keys()):
            idx_ent, precio_ent = posiciones_abiertas[idx_nivel]
            objetivo_mult_nivel = objetivo_base + objetivo_paso * idx_nivel
            nivel_venta = precio_ent + espaciado * objetivo_mult_nivel
            if high[i] >= nivel_venta:
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, nivel_venta, "venta_nivel", idx_nivel=idx_nivel))
                del posiciones_abiertas[idx_nivel]

    for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
        resultado.trades.append(TradeGrid(idx_ent, n - 1, precio_ent, close[-1], "fin_periodo", idx_nivel=idx_nivel))
    return resultado


def experimento_2_objetivo_por_nivel():
    print("\n### Experimento 2: objetivo mas lejano en niveles mas profundos ###")
    print(f"{'par':<10} {'config':<24} {'capital':>9} {'drawdown':>9} {'calmar':>8} {'trades':>7} {'trades/año':>11}")
    configs = [
        ("plano 1.5 (control)", 1.5, 0.0),
        ("escalonado 1.0+0.5*n", 1.0, 0.5),
        ("escalonado 1.0+1.0*n", 1.0, 1.0),
        ("escalonado 1.5+0.5*n", 1.5, 0.5),
    ]
    for par in ["BTCUSDT", "ETHUSDT"]:
        df = cargar_ohlcv(par, "4h", ruta_base="/Users/jorgeansotegui/Desktop/corvus4/datos/crudo")
        for nombre, base, paso in configs:
            res = simular_objetivo_por_nivel(df, n_niveles=3, k_atr_espaciado=0.5, k_atr_espaciado_tendencia=1.5,
                                              velas_recentrado=180, stop_bajo_rejilla=2.0,
                                              objetivo_base=base, objetivo_paso=paso)
            capital, dd, calmar, n_trades, trades_ano = metricas(df, res)
            print(f"{par:<10} {nombre:<24} {capital:9.1f} {dd:9.1f} {calmar:8.1f} {n_trades:7d} {trades_ano:11.1f}")


def experimento_3_refuerzo_doble_suelo():
    print("\n### Experimento 3: objetivo extra-amplio cuando el nivel coincide con Doble suelo/techo real ###")
    print(f"{'par':<10} {'config':<28} {'capital':>9} {'drawdown':>9} {'calmar':>8} {'trades':>7} {'trades/año':>11}")
    for par in ["BTCUSDT", "ETHUSDT"]:
        df = cargar_ohlcv(par, "4h", ruta_base="/Users/jorgeansotegui/Desktop/corvus4/datos/crudo")
        df_ind = calc_sen_ds(calc_ind_ds(df.copy()))
        senal_refuerzo = df_ind["entra_largo"].to_numpy()
        for mult_ref, nombre in [(1.0, "sin refuerzo (control, obj=1.5)"), (2.5, "refuerzo x2.5 si coincide con doble suelo")]:
            res = simular(df, k_atr_espaciado=0.5, k_atr_espaciado_tendencia=1.5, velas_recentrado=180,
                          k_atr_objetivo_mult=1.5,
                          senal_refuerzo=senal_refuerzo if mult_ref > 1.0 else None,
                          mult_espaciado_reforzado=mult_ref, **BASE)
            capital, dd, calmar, n_trades, trades_ano = metricas(df, res)
            print(f"{par:<10} {nombre:<28} {capital:9.1f} {dd:9.1f} {calmar:8.1f} {n_trades:7d} {trades_ano:11.1f}")


if __name__ == "__main__":
    experimento_1_timeframe_diario()
    experimento_2_objetivo_por_nivel()
    experimento_3_refuerzo_doble_suelo()
