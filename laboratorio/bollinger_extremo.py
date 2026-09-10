"""
Bollinger extremo — re-verificación de un candidato heredado de corvus3
(`motores/bollinger_extremo.py`), marcado ahí como "CANDIDATO FUERTE"
(screening_bb_extremo, sharpe 0.35, notas "confirmado en desarrollo Y en
validación 2025 +2,26% por evento") pero NUNCA pasado por el pipeline de
corvus4 ni comprobado BTC-solo -- la evidencia original es multi-moneda
(34 pares), la misma trampa que mató a StochRSI+ADX y a Canal.

Mecanismo (idéntico al original): reversión a la banda media de Bollinger.
- Entra: el cierre toca o perfora la banda inferior (20, 2 desviaciones) Y
  hay un pico de volumen (>=2x su media de 20 velas) -- "capitulación real"
  (venta forzada), no un simple goteo sin fuerza detrás.
- Sale: el cierre vuelve a alcanzar la banda MEDIA (SMA20), o stop -20%, o
  48h (12 velas de 4h) sin llegar -- backstop de tiempo, igual que el
  original (salidas/tiempo_fijo.py).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandas_ta as pta

BB_LENGTH = 20
BB_STD = 2.0
VOL_N = 20
VOL_MULT = 2.0
STOPLOSS = -0.20
VELAS_MAX = 12  # 48h en 4h


def calcular_indicadores(df: pd.DataFrame, bb_length: int = BB_LENGTH, bb_std: float = BB_STD, vol_n: int = VOL_N) -> pd.DataFrame:
    df = df.copy()
    bb = pta.bbands(df["close"], length=bb_length, std=bb_std)
    col_bbl = next(c for c in bb.columns if c.startswith("BBL_"))
    col_bbm = next(c for c in bb.columns if c.startswith("BBM_"))
    df["bbl"] = bb[col_bbl]
    df["bbm"] = bb[col_bbm]
    df["vol_media"] = df["volume"].rolling(vol_n).mean()
    return df


def calcular_senales(df: pd.DataFrame, vol_mult: float = VOL_MULT) -> pd.DataFrame:
    df = df.copy()
    capitulacion = df["volume"] >= vol_mult * df["vol_media"]
    df["entra_largo"] = (
        (df["close"] <= df["bbl"]) & df["bbl"].notna() & capitulacion.fillna(False)
    )
    df["sale"] = (df["close"] >= df["bbm"]).fillna(False)
    return df


@dataclass
class TradeBB:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str  # "reversion", "stop", "tiempo"

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, stop: float = STOPLOSS, velas_max: int = VELAS_MAX) -> list[TradeBB]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    sale = df["sale"].to_numpy()
    n = len(df)

    trades: list[TradeBB] = []
    en_posicion = False
    idx_entrada = precio_entrada = None

    for i in range(n):
        if not en_posicion:
            if entra[i]:
                en_posicion = True
                idx_entrada = i
                precio_entrada = close[i]
        else:
            profit = close[i] / precio_entrada - 1
            velas_abiertas = i - idx_entrada
            if profit <= stop:
                trades.append(TradeBB(idx_entrada, i, precio_entrada, close[i], "stop"))
                en_posicion = False
            elif sale[i]:
                trades.append(TradeBB(idx_entrada, i, precio_entrada, close[i], "reversion"))
                en_posicion = False
            elif velas_abiertas >= velas_max:
                trades.append(TradeBB(idx_entrada, i, precio_entrada, close[i], "tiempo"))
                en_posicion = False

    return trades
