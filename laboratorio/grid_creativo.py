"""
Grid dinamico -- variantes creativas propuestas por mi, no por el usuario,
en respuesta directa a su pregunta sobre TP/SL asimetricos. Tres mecanismos
NUEVOS que grid_adaptativo.py no soporta, probados por separado y combinados:

1. objetivo_mult: DESACOPLA el take-profit del espaciado de entrada. Hoy
   (grid_adaptativo.py) el nivel de venta es SIEMPRE "un escalon de rejilla
   mas arriba" -- la misma distancia que separa los niveles de compra. Aqui
   el TP puede ser un multiplo mayor de esa distancia (p.ej. 2x) sin tocar
   ni el espaciado de entrada ni el stop de seguridad (que sigue anclado al
   espaciado de entrada) -- exactamente la idea de "TP mas grande, SL mas
   pequeño" que planteo el usuario, pero con distancias ATR-adaptativas en
   vez de % fijos.

2. confirmar_rebote: NO comprar en cuanto el precio toca el nivel (eso es
   comprar en plena caida, "cuchillo cayendo") -- exigir que la vela que
   toca el nivel cierre por encima de su apertura (vela alcista, primer
   signo de rebote) antes de dar la entrada por buena.

3. filtro_volumen: solo abrir un nivel si el volumen de esa vela supera la
   media reciente -- la idea es que una caida con volumen alto es mas
   probable que sea una capitulacion real (rebote despues) que una caida
   con volumen bajo (puede seguir cayendo sin nadie parandolo).

Todos reusan calcular_atr/calcular_tendencia_fuerte de grid_adaptativo.py
para no duplicar logica ya validada; grid_adaptativo.py no se toca.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from datos.cargar import cargar_ohlcv
from laboratorio.grid_adaptativo import calcular_atr, calcular_tendencia_fuerte, TradeGrid, ResultadoGrid, evaluar_capital


def simular_creativo(
    df: pd.DataFrame,
    n_niveles: int = 3,
    k_atr_espaciado: float = 0.5,
    k_atr_espaciado_tendencia: float = 1.5,
    velas_recentrado: int = 180,
    stop_bajo_rejilla: float = 2.0,
    ventana_atr: int = 14,
    objetivo_mult: float = 1.0,
    confirmar_rebote: bool = False,
    filtro_volumen: bool = False,
    vol_n: int = 20,
    vol_mult_entrada: float = 1.2,
) -> ResultadoGrid:
    close = df["close"].to_numpy()
    open_ = df["open"].to_numpy()
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    volume = df["volume"].to_numpy()
    atr = calcular_atr(df, ventana_atr).to_numpy()
    vol_media = df["volume"].rolling(vol_n).mean().to_numpy()
    tendencia_fuerte = calcular_tendencia_fuerte(df).to_numpy()
    n = len(df)

    resultado = ResultadoGrid()

    def nueva_rejilla(i):
        k = k_atr_espaciado_tendencia if tendencia_fuerte[i] else k_atr_espaciado
        espaciado = k * atr[i]
        centro = close[i]
        niveles_compra = [centro - espaciado * kk for kk in range(1, n_niveles + 1)]
        return centro, espaciado, niveles_compra

    idx0 = ventana_atr
    while idx0 < n and (np.isnan(atr[idx0]) or np.isnan(vol_media[idx0])):
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
                if confirmar_rebote and not (close[i] > open_[i]):
                    continue
                if filtro_volumen and not (volume[i] > vol_mult_entrada * vol_media[i]):
                    continue
                posiciones_abiertas[idx_nivel] = (i, nivel)

        for idx_nivel in list(posiciones_abiertas.keys()):
            idx_ent, precio_ent = posiciones_abiertas[idx_nivel]
            nivel_venta = precio_ent + espaciado * objetivo_mult
            if high[i] >= nivel_venta:
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, nivel_venta, "venta_nivel", idx_nivel=idx_nivel))
                del posiciones_abiertas[idx_nivel]

    for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
        resultado.trades.append(TradeGrid(idx_ent, n - 1, precio_ent, close[-1], "fin_periodo", idx_nivel=idx_nivel))

    return resultado


CONFIG_BASE = dict(n_niveles=3, velas_recentrado=180, stop_bajo_rejilla=2.0)

VARIANTES = [
    ("baseline (control)", dict(objetivo_mult=1.0, confirmar_rebote=False, filtro_volumen=False)),
    ("objetivo x1.5", dict(objetivo_mult=1.5, confirmar_rebote=False, filtro_volumen=False)),
    ("objetivo x2.0", dict(objetivo_mult=2.0, confirmar_rebote=False, filtro_volumen=False)),
    ("objetivo x3.0", dict(objetivo_mult=3.0, confirmar_rebote=False, filtro_volumen=False)),
    ("confirmar_rebote solo", dict(objetivo_mult=1.0, confirmar_rebote=True, filtro_volumen=False)),
    ("filtro_volumen solo", dict(objetivo_mult=1.0, confirmar_rebote=False, filtro_volumen=True)),
    ("rebote + volumen", dict(objetivo_mult=1.0, confirmar_rebote=True, filtro_volumen=True)),
    ("objetivo x2.0 + rebote", dict(objetivo_mult=2.0, confirmar_rebote=True, filtro_volumen=False)),
    ("objetivo x2.0 + volumen", dict(objetivo_mult=2.0, confirmar_rebote=False, filtro_volumen=True)),
    ("objetivo x2.0 + rebote + volumen", dict(objetivo_mult=2.0, confirmar_rebote=True, filtro_volumen=True)),
]


def evaluar(df: pd.DataFrame, params: dict) -> dict:
    res = simular_creativo(df, k_atr_espaciado=0.5, k_atr_espaciado_tendencia=1.5, **CONFIG_BASE, **params)
    capital, drawdown = evaluar_capital(res, CONFIG_BASE["n_niveles"])
    n_trades = len(res.trades)
    n_anos = (df["open_time"].iloc[-1] - df["open_time"].iloc[0]).days / 365.25
    trades_ano = n_trades / n_anos if n_anos > 0 else float("nan")
    calmar = (capital - 100) / abs(drawdown) if drawdown != 0 else float("nan")
    return dict(capital=capital, drawdown=drawdown, calmar=calmar, n_trades=n_trades, trades_ano=trades_ano)


def main():
    for par in ["BTCUSDT", "ETHUSDT"]:
        df = cargar_ohlcv(par, "4h", ruta_base="/Users/jorgeansotegui/Desktop/corvus4/datos/crudo")
        print(f"\n=== {par} 4h ===")
        print(f"{'variante':<32} {'capital':>9} {'drawdown':>9} {'calmar':>8} {'n_trades':>9} {'trades/año':>11}")
        for nombre, params in VARIANTES:
            r = evaluar(df, params)
            print(f"{nombre:<32} {r['capital']:9.1f} {r['drawdown']:9.1f} {r['calmar']:8.1f} "
                  f"{r['n_trades']:9d} {r['trades_ano']:11.1f}")


if __name__ == "__main__":
    main()
