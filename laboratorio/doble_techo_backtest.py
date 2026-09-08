"""Backtest real entrada->salida para doble_techo.py (posiciones CORTAS):
gana si el precio cae, pierde si sube. Espejo de doble_suelo_backtest.py."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from laboratorio.doble_techo import OBJETIVO_ROI, STOPLOSS


@dataclass
class TradeDobleTecho:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        # posicion corta: se gana cuando el precio BAJA (precio_salida < precio_entrada)
        return (self.precio_entrada / self.precio_salida - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = OBJETIVO_ROI, stop: float = STOPLOSS) -> list[TradeDobleTecho]:
    close = df["close"].to_numpy()
    entra = df["entra_corto"].to_numpy()
    n = len(df)

    trades: list[TradeDobleTecho] = []
    en_posicion = False
    idx_entrada = precio_entrada = None

    for i in range(n):
        if not en_posicion:
            if entra[i]:
                en_posicion = True
                idx_entrada = i
                precio_entrada = close[i]
        else:
            retorno_corto = (precio_entrada / close[i] - 1)   # positivo si el precio bajo
            if retorno_corto >= abs(objetivo) or -retorno_corto >= stop:
                motivo = "objetivo" if retorno_corto >= abs(objetivo) else "stop"
                trades.append(TradeDobleTecho(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False

    return trades
