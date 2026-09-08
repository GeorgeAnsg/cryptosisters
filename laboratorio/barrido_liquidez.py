"""
M5 — Barrido de liquidez (Liquidity Sweep) + reversión.
investigacion/06-traders-discrecional.md §1.4: "el precio perfora
brevemente un máximo o mínimo evidente (donde hay stops acumulados),
recoge esa liquidez, y revierte con fuerza". Nivel evidente elegido aquí:
el mínimo/máximo del DÍA ANTERIOR completo (el más "evidente" de los
candidatos que menciona la investigación).

Nota: esencialmente el mismo fenómeno que Spring de Wyckoff (ya
descartado) descrito con otro vocabulario y sin la condición de volumen
-- se prueba de todas formas porque la investigación lo marca como "el
concepto ICT con la base económica más sólida" y con evidencia mixta
positiva (StatOasis: +0,119%, t=+0,94, dirección correcta pero no
significativo).

Definición: low[i] < mínimo del día anterior completo, pero close[i] >
ese mismo mínimo (mecha que barre y cierra de vuelta dentro) -> sweep
alcista. Espejo con máximos para sweep bajista.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fecha"] = df["open_time"].dt.date
    diario = df.groupby("fecha").agg(low_dia=("low", "min"), high_dia=("high", "max")).reset_index()
    diario["low_dia_ant"] = diario["low_dia"].shift(1)
    diario["high_dia_ant"] = diario["high_dia"].shift(1)
    df = df.merge(diario[["fecha", "low_dia_ant", "high_dia_ant"]], on="fecha", how="left")
    return df


def calcular_senales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["entra_largo"] = (
        (df["low"] < df["low_dia_ant"]) & (df["close"] > df["low_dia_ant"])
    ).fillna(False)
    return df


@dataclass
class TradeBarrido:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = 0.20, margen_stop: float = 0.03) -> list[TradeBarrido]:
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    n = len(df)

    trades: list[TradeBarrido] = []
    en_posicion = False
    idx_entrada = precio_entrada = stop = None

    for i in range(n):
        if not en_posicion:
            if entra[i]:
                en_posicion = True
                idx_entrada = i
                precio_entrada = close[i]
                stop = low[i] * (1 - margen_stop)
        else:
            retorno = close[i] / precio_entrada - 1
            if retorno >= objetivo or close[i] <= stop:
                motivo = "objetivo" if retorno >= objetivo else "stop"
                trades.append(TradeBarrido(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False

    return trades
