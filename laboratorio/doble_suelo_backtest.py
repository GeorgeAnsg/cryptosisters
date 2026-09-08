"""Backtest real entrada->salida para doble_suelo.py, fiel a la versión
original de corvus2 (objetivo fijo 30%, stop fijo -12%, sin salida
dinámica -- eso es justo lo que estaba pendiente de mejorar allí)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.doble_suelo import OBJETIVO_ROI, STOPLOSS


@dataclass
class TradeDobleSuelo:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = OBJETIVO_ROI, stop: float = STOPLOSS) -> list[TradeDobleSuelo]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    n = len(df)

    trades: list[TradeDobleSuelo] = []
    en_posicion = False
    idx_entrada = precio_entrada = None

    for i in range(n):
        if not en_posicion:
            if entra[i]:
                en_posicion = True
                idx_entrada = i
                precio_entrada = close[i]
        else:
            retorno = close[i] / precio_entrada - 1
            if retorno >= objetivo or retorno <= stop:
                motivo = "objetivo" if retorno >= objetivo else "stop"
                trades.append(TradeDobleSuelo(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False

    return trades
