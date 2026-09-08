"""
PDH/PDL como continuación — romper el máximo (PDH) o mínimo (PDL) del día
anterior y SEGUIR en esa dirección, a diferencia de barrido_liquidez.py
(que apostaba a la reversión tras una mecha que perfora y vuelve). Aquí
la apuesta es la contraria: la ruptura es real, no una trampa.

Señal (largo): close[i] > high del día anterior completo (PDH), sin haber
tocado antes ese nivel en la misma vela desde abajo con vuelta (eso ya
sería el patrón de barrido, no de continuación).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fecha"] = df["open_time"].dt.date
    diario = df.groupby("fecha").agg(low_dia=("low", "min"), high_dia=("high", "max")).reset_index()
    diario["pdl"] = diario["low_dia"].shift(1)
    diario["pdh"] = diario["high_dia"].shift(1)
    df = df.merge(diario[["fecha", "pdl", "pdh"]], on="fecha", how="left")
    return df


def calcular_senales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rompe = (df["close"] > df["pdh"]) & (df["close"].shift(1) <= df["pdh"])
    df["entra_largo"] = rompe.fillna(False)
    return df


@dataclass
class TradePDH:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = 0.10, stop: float = -0.05) -> list[TradePDH]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    n = len(df)
    trades: list[TradePDH] = []
    en_posicion = False
    idx_entrada = precio_entrada = None
    for i in range(n):
        if not en_posicion:
            if entra[i]:
                en_posicion = True
                idx_entrada, precio_entrada = i, close[i]
        else:
            retorno = close[i] / precio_entrada - 1
            if retorno >= objetivo or retorno <= stop:
                motivo = "objetivo" if retorno >= objetivo else "stop"
                trades.append(TradePDH(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False
    return trades
