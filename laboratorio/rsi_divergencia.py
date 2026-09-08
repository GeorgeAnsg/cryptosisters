"""
M8 — Divergencia alcista de RSI. Réplica fiel de `rsi_divergencia` en
`~/Desktop/tr/v6/core/bot_indicators.py` (ya portada antes en
`corvus3/motores/senales_bot_viejo.py`), causal por diseño: un pivote solo
se confirma mirando `ventana` velas hacia ambos lados, dentro de la propia
ventana ya pasada respecto a la vela actual.

Cribado previo (corvus3, 7-sept-2026): +0,205% vs +0,064% baseline,
n=20.652 -- pero ese "n" cuenta señales sueltas sobre 34 monedas, no
eventos de mercado en BTC (Regla 7: contar así infla la muestra). Aquí se
prueba con la disciplina completa: BTC solo, entrada/salida real, no un
horizonte fijo.

Salida: objetivo 20% / stop -10% -- valores de partida razonables, no
ajustados a los datos (igual disciplina que con Canal: no se busca el
número que mejor quede).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandas_ta as ta


def calcular_indicadores(df: pd.DataFrame, rsi_len: int = 14) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = ta.rsi(df["close"], length=rsi_len)
    return df


def _rsi_divergencia(high: pd.Series, low: pd.Series, rsi: pd.Series, ventana: int = 20) -> pd.Series:
    n = len(high)
    resultado = pd.Series([None] * n, index=high.index, dtype=object)
    h, lo, r = high.to_numpy(), low.to_numpy(), rsi.to_numpy()

    for i in range(ventana + 1, n):
        seg_hi = h[i - ventana:i + 1]
        seg_lo = lo[i - ventana:i + 1]
        seg_rsi = r[i - ventana:i + 1]
        ph = [k for k in range(1, ventana) if seg_hi[k] > seg_hi[k - 1] and seg_hi[k] > seg_hi[k + 1]]
        pl = [k for k in range(1, ventana) if seg_lo[k] < seg_lo[k - 1] and seg_lo[k] < seg_lo[k + 1]]
        if len(pl) >= 2 and not any(np.isnan(seg_rsi[pl[-2:]])):
            p1, p2 = pl[-2], pl[-1]
            if seg_lo[p2] < seg_lo[p1] and seg_rsi[p2] > seg_rsi[p1] + 3:
                resultado.iat[i] = "bullish"
        if len(ph) >= 2 and not any(np.isnan(seg_rsi[ph[-2:]])):
            p1, p2 = ph[-2], ph[-1]
            if seg_hi[p2] > seg_hi[p1] and seg_rsi[p2] < seg_rsi[p1] - 3:
                resultado.iat[i] = "bearish"
    return resultado


def calcular_senales(df: pd.DataFrame, ventana: int = 20) -> pd.DataFrame:
    df = df.copy()
    div = _rsi_divergencia(df["high"], df["low"], df["rsi"], ventana)
    df["entra_largo"] = (div == "bullish").fillna(False)
    return df


OBJETIVO_ROI = 0.20
STOPLOSS = -0.10


@dataclass
class TradeRSIDiv:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = OBJETIVO_ROI, stop: float = STOPLOSS) -> list[TradeRSIDiv]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    n = len(df)

    trades: list[TradeRSIDiv] = []
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
                trades.append(TradeRSIDiv(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False

    return trades
