"""
Miedo extremo — reversión tras Fear & Greed Index en mínimos + caída
reciente. Candidato NUEVO (no heredado de corvus2/corvus3), construido a
partir de un dato descargado para otro proyecto (~/Desktop/tr/data/) y
nunca usado como motor.

Mecanismo (mismo espíritu que M2/funding_extremo, pero con sentimiento
agregado en vez de derivados): cuando el índice de miedo está en sus
niveles más bajos DE VERDAD (no solo "algo de miedo", sino un extremo
poco común incluso para su propio historial reciente) y coincide con una
caída violenta de precio, la apuesta es que el mercado está
sobre-vendido por pánico, no por deterioro fundamental -- terreno fértil
para un rebote técnico.

A diferencia de funding (dato de derivados, actualizado cada 8h), F&G es
un agregado diario de varias fuentes (volatilidad, momentum, redes
sociales, encuestas, dominancia, tendencias de búsqueda) -- mecanismo
económico distinto, aunque la forma de la señal (extremo + caída) es
comparable.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from datos.cargar_fear_greed import cargar_fear_greed, fusionar_fear_greed

VENTANA_PERCENTIL = 180    # ~30 dias en velas de 4h -- F&G se mueve mas lento que funding
PERCENTIL_CORTE = 0.05     # F&G en el 5% mas bajo de su propio historial reciente
VENTANA_CAIDA = 6          # 1 dia en 4h
CAIDA_MINIMA = -0.08       # caida de al menos 8% en ese dia


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = fusionar_fear_greed(df, cargar_fear_greed())
    df["fg_percentil"] = df["fg_valor"].rolling(VENTANA_PERCENTIL).rank(pct=True)
    df["caida_reciente"] = df["close"] / df["close"].shift(VENTANA_CAIDA) - 1
    return df


def calcular_senales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["entra_largo"] = (
        (df["fg_percentil"] <= PERCENTIL_CORTE)
        & (df["caida_reciente"] <= CAIDA_MINIMA)
    ).fillna(False)
    return df


@dataclass
class TradeMiedo:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = 0.15, stop: float = -0.10) -> list[TradeMiedo]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    n = len(df)
    trades: list[TradeMiedo] = []
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
                trades.append(TradeMiedo(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False
    return trades
