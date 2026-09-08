"""
M6 — AVWAP anclado a swing lows confirmados.
investigacion/06-traders-discrecional.md §4.1: "plausible pero sin
evidencia publicada independiente" -- mecanismo del coste medio agregado
desde un punto de inflexión real, distinto del VWAP de sesión (ya
descartado, sin sentido en cripto 24/7).

Ancla: el pivote de mínimo confirmado más reciente (reutiliza
`calcular_pivotes` de canal_diagonal_rebote.py, ya validado por la
Puerta 1) -- regla objetiva fijada de antemano, no elegida a posteriori.

Señal: tras alejarse claramente por encima del AVWAP (el mercado ya
confía en el nivel), el precio vuelve a tocarlo y cierra de vuelta por
encima -- rebote sobre el "coste medio" de quien compró desde el mínimo,
uso clásico descrito por Brian Shannon (AlphaTrends).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.canal_diagonal_rebote import calcular_pivotes


def calcular_avwap(df: pd.DataFrame, ventana_pivote: int = 30) -> pd.DataFrame:
    df = df.copy()
    _, bajos = calcular_pivotes(df, ventana_pivote)

    tp = (df["high"] + df["low"] + df["close"]) / 3
    tpv = (tp * df["volume"]).to_numpy()
    vol = df["volume"].to_numpy()
    n = len(df)

    avwap = np.full(n, np.nan)
    ya_se_alejo = np.zeros(n, dtype=bool)

    ptr = 0
    idx_ancla = None
    suma_tpv = suma_vol = 0.0
    max_desde_ancla = -np.inf

    for i in range(n):
        while ptr < len(bajos) and bajos[ptr][1] <= i:
            idx_ancla = bajos[ptr][0]
            suma_tpv = suma_vol = 0.0
            max_desde_ancla = -np.inf
            ptr += 1
        if idx_ancla is None:
            continue
        # reconstruir la suma desde el ancla nueva la primera vez que se activa en este bucle
        # (sencillo: si se acaba de anclar aqui, sumar retroactivamente desde idx_ancla hasta i)
        if suma_vol == 0.0 and i >= idx_ancla:
            suma_tpv = tpv[idx_ancla:i + 1].sum()
            suma_vol = vol[idx_ancla:i + 1].sum()
        elif i > 0:
            suma_tpv += tpv[i]
            suma_vol += vol[i]

        if suma_vol > 0:
            avwap[i] = suma_tpv / suma_vol
            max_desde_ancla = max(max_desde_ancla, df["close"].iat[i])
            ya_se_alejo[i] = max_desde_ancla > avwap[i] * 1.03

    df["avwap"] = avwap
    df["avwap_alejado"] = ya_se_alejo
    return df


def calcular_senales(df: pd.DataFrame, tolerancia: float = 0.015) -> pd.DataFrame:
    df = df.copy()
    toca = df["low"] <= df["avwap"] * (1 + tolerancia)
    cierra_encima = df["close"] > df["avwap"]
    df["entra_largo"] = (toca & cierra_encima & df["avwap_alejado"].shift(1).fillna(False)).fillna(False)
    return df


@dataclass
class TradeAVWAP:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = 0.15, stop: float = -0.08) -> list[TradeAVWAP]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    n = len(df)
    trades: list[TradeAVWAP] = []
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
                trades.append(TradeAVWAP(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False
    return trades
