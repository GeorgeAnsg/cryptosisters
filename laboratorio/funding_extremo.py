"""
M2 — Reversión tras funding extremo negativo + caída violenta.

Mecanismo (docs/00-PLAN-MAESTRO.md 7.2): funding muy negativo = hay
muchos más cortos que largos pagando por mantener su posición -- eso es
apalancamiento real, no opinión. Combinado con una caída violenta
reciente, la apuesta es que una subida rápida fuerza a esos cortos a
cerrar (short squeeze), amplificando el rebote.

Primer motor del proyecto que usa datos que NO son solo precio.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from datos.cargar_funding import cargar_funding, fusionar_funding

VENTANA_PERCENTIL = 540    # ~90 dias en velas de 4h
PERCENTIL_CORTE = 0.05     # funding en el 5% mas negativo de su propio historial reciente
VENTANA_CAIDA = 6          # 1 dia en 4h
CAIDA_MINIMA = -0.08       # caida de al menos 8% en ese dia


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = fusionar_funding(df, cargar_funding())
    df["funding_percentil"] = df["funding"].rolling(VENTANA_PERCENTIL).rank(pct=True)
    df["caida_reciente"] = df["close"] / df["close"].shift(VENTANA_CAIDA) - 1
    return df


def calcular_senales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["entra_largo"] = (
        (df["funding_percentil"] <= PERCENTIL_CORTE)
        & (df["caida_reciente"] <= CAIDA_MINIMA)
    ).fillna(False)
    return df


@dataclass
class TradeFunding:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = 0.15, stop: float = -0.10) -> list[TradeFunding]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    n = len(df)
    trades: list[TradeFunding] = []
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
                trades.append(TradeFunding(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False
    return trades
