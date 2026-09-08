"""
M1 — Momentum de N días en BTC diario, con salida por ATR (trailing stop).

Del catálogo (docs/00-PLAN-MAESTRO.md §7.2): "es la familia con más
evidencia académica de la historia, y la salida dinámica es justo lo que
no se probó" -- Canal usó salida fija (canal de 10 días o régimen), esto
usa una salida que se adapta a la volatilidad reciente (ATR), dejando
correr las ganadoras más que un objetivo fijo pero cortando antes que un
canal ancho.

Entrada: BTC cierra por encima de su máximo de N días (N=20 o 50),
igual que un Donchian pero en velas DIARIAS, no 4h.

Salida: trailing stop de k×ATR(14) por debajo del máximo alcanzado desde
la entrada (Chandelier Exit, técnica estándar de seguimiento de
tendencia) -- se mueve hacia arriba con el precio, nunca hacia abajo.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def calcular_indicadores(df: pd.DataFrame, n_entrada: int = 50, n_atr: int = 14) -> pd.DataFrame:
    df = df.copy()
    df["max_n"] = df["high"].shift(1).rolling(n_entrada).max()

    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(n_atr).mean()
    return df


def calcular_senales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["entra_largo"] = (df["close"] > df["max_n"]).fillna(False)
    return df


@dataclass
class TradeMomentum:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, k_atr: float = 3.0) -> list[TradeMomentum]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    atr = df["atr"].to_numpy()
    n = len(df)

    trades: list[TradeMomentum] = []
    en_posicion = False
    idx_entrada = precio_entrada = maximo_desde_entrada = trailing = None

    for i in range(n):
        if not en_posicion:
            if entra[i] and not np.isnan(atr[i]):
                en_posicion = True
                idx_entrada = i
                precio_entrada = close[i]
                maximo_desde_entrada = close[i]
                trailing = close[i] - k_atr * atr[i]
        else:
            maximo_desde_entrada = max(maximo_desde_entrada, close[i])
            trailing = max(trailing, maximo_desde_entrada - k_atr * atr[i])
            if close[i] < trailing:
                trades.append(TradeMomentum(idx_entrada, i, precio_entrada, close[i]))
                en_posicion = False

    return trades
