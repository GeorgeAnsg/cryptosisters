"""
Doble suelo — salida dinámica por ATR con toma parcial + trailing.
Respuesta directa a la idea del usuario: en vez de TP/SL fijos en %,
adaptar la salida a la volatilidad del momento (ATR), y en vez de cerrar
todo de golpe al llegar al objetivo, coger una parte y dejar correr el
resto con un trailing stop (igual que el Chandelier Exit ya usado en M1 /
grid_adaptativo, aplicado aquí a Doble suelo).

Mecánica:
- Entra: igual que doble_suelo.py (patrón de doble suelo + rotura +
  volumen), sin cambios en la detección.
- Stop inicial: precio_entrada - k_atr_stop * ATR(14) en el momento de
  entrar (no un -12%/-4% fijo -- si la vela es muy volátil el stop tiene
  más margen, si está tranquila, menos).
- Objetivo inicial: precio_entrada + k_atr_objetivo * ATR(14) en la
  entrada. Al tocarlo, se cierra `fraccion_parcial` de la posición ahí
  (beneficio asegurado) y el resto pasa a un trailing stop de
  k_atr_trailing * ATR por debajo del máximo alcanzado desde la entrada.
- El retorno de la operación es el promedio ponderado de las dos salidas
  (parcial + resto), no dos operaciones separadas.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.grid_adaptativo import calcular_atr


@dataclass
class TradeDobleSueloDinamico:
    idx_entrada: int
    idx_salida_parcial: int | None
    idx_salida_final: int
    precio_entrada: float
    precio_salida_parcial: float | None
    precio_salida_final: str
    retorno_pct: float
    motivo_final: str  # "trailing", "stop_inicial", "fin_periodo"
    tomo_parcial: bool


def simular(
    df: pd.DataFrame,
    k_atr_stop: float = 3.0,
    k_atr_objetivo: float = 3.0,
    k_atr_trailing: float = 2.0,
    fraccion_parcial: float = 0.5,
    ventana_atr: int = 14,
) -> list[TradeDobleSueloDinamico]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    atr = calcular_atr(df, ventana_atr).to_numpy()
    n = len(df)

    trades: list[TradeDobleSueloDinamico] = []
    en_posicion = False
    idx_entrada = precio_entrada = atr_entrada = stop = objetivo = None
    tomo_parcial = False
    idx_parcial = precio_parcial = None
    maximo_desde_parcial = None

    for i in range(n):
        if not en_posicion:
            if entra[i] and not np.isnan(atr[i]):
                en_posicion = True
                idx_entrada = i
                precio_entrada = close[i]
                atr_entrada = atr[i]
                stop = precio_entrada - k_atr_stop * atr_entrada
                objetivo = precio_entrada + k_atr_objetivo * atr_entrada
                tomo_parcial = False
        else:
            if not tomo_parcial:
                if close[i] <= stop:
                    retorno = (close[i] / precio_entrada - 1) * 100
                    trades.append(TradeDobleSueloDinamico(
                        idx_entrada, None, i, precio_entrada, None, close[i],
                        retorno, "stop_inicial", False))
                    en_posicion = False
                elif close[i] >= objetivo:
                    tomo_parcial = True
                    idx_parcial, precio_parcial = i, close[i]
                    maximo_desde_parcial = close[i]
            else:
                maximo_desde_parcial = max(maximo_desde_parcial, close[i])
                trailing = maximo_desde_parcial - k_atr_trailing * atr[i]
                if close[i] < trailing:
                    ret_parcial = (precio_parcial / precio_entrada - 1) * 100
                    ret_final = (close[i] / precio_entrada - 1) * 100
                    retorno = fraccion_parcial * ret_parcial + (1 - fraccion_parcial) * ret_final
                    trades.append(TradeDobleSueloDinamico(
                        idx_entrada, idx_parcial, i, precio_entrada, precio_parcial, close[i],
                        retorno, "trailing", True))
                    en_posicion = False

    if en_posicion:
        if tomo_parcial:
            ret_parcial = (precio_parcial / precio_entrada - 1) * 100
            ret_final = (close[-1] / precio_entrada - 1) * 100
            retorno = fraccion_parcial * ret_parcial + (1 - fraccion_parcial) * ret_final
        else:
            retorno = (close[-1] / precio_entrada - 1) * 100
        trades.append(TradeDobleSueloDinamico(
            idx_entrada, idx_parcial, n - 1, precio_entrada, precio_parcial, close[-1],
            retorno, "fin_periodo", tomo_parcial))

    return trades
