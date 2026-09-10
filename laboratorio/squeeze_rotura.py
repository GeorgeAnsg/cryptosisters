"""
Squeeze de volatilidad + rotura — candidato NUEVO, propuesto por mí (no por
el usuario) tras revisar qué mecanismos no se habían probado hoy. Verificado
con WebSearch antes de construir: la evidencia encontrada es SOLO de
marketing/vendors de indicadores (TradingView, blogs de trading), sin
ningún estudio académico riguroso -- se trata exactamente igual que
cualquier otro candidato de hoy (probar con datos propios, sin dar por
buena la narrativa).

Mecanismo (distinto de todo lo probado hasta ahora): no es reversión a un
extremo (eso es Bollinger extremo, ya descartado) -- es CONTINUACIÓN tras
compresión de volatilidad. Cuando el ancho de las bandas de Bollinger cae
a un mínimo poco común (percentil bajo de su propio historial reciente),
el mercado está "comprimido"; la apuesta es que la siguiente ruptura de esa
compresión, con volumen y tendencia confirmando, tiende a seguir en esa
dirección (no es aleatoria).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pandas_ta as pta

from laboratorio.grid_adaptativo import calcular_atr, calcular_tendencia_fuerte

BB_LENGTH = 20
BB_STD = 2.0
VENTANA_PERCENTIL_ANCHO = 250   # ~40 dias en 4h
PERCENTIL_SQUEEZE = 0.10        # ancho de banda en el 10% mas estrecho de su propio historial
VOL_N = 20
VOL_MULT = 1.5


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    bb = pta.bbands(df["close"], length=BB_LENGTH, std=BB_STD)
    col_bbu = next(c for c in bb.columns if c.startswith("BBU_"))
    col_bbl = next(c for c in bb.columns if c.startswith("BBL_"))
    col_bbm = next(c for c in bb.columns if c.startswith("BBM_"))
    df["bbu"], df["bbl"], df["bbm"] = bb[col_bbu], bb[col_bbl], bb[col_bbm]
    df["ancho_banda"] = (df["bbu"] - df["bbl"]) / df["bbm"]
    df["ancho_percentil"] = df["ancho_banda"].rolling(VENTANA_PERCENTIL_ANCHO).rank(pct=True)
    df["vol_media"] = df["volume"].rolling(VOL_N).mean()
    df["tendencia_fuerte"] = calcular_tendencia_fuerte(df)
    df["atr"] = calcular_atr(df)
    return df


def calcular_senales(df: pd.DataFrame, percentil_squeeze: float = PERCENTIL_SQUEEZE, vol_mult: float = VOL_MULT) -> pd.DataFrame:
    df = df.copy()
    hubo_squeeze_reciente = (df["ancho_percentil"] <= percentil_squeeze).rolling(6).max().shift(1).fillna(0).astype(bool)
    rompe_arriba = (df["close"] > df["bbu"]) & (df["close"].shift(1) <= df["bbu"].shift(1))
    vol_ok = df["volume"] > vol_mult * df["vol_media"]
    df["entra_largo"] = (
        hubo_squeeze_reciente
        & rompe_arriba.fillna(False)
        & vol_ok.fillna(False)
        & df["tendencia_fuerte"].fillna(False)
    )
    return df


@dataclass
class TradeSqueeze:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, k_atr_trailing: float = 3.0) -> list[TradeSqueeze]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    atr = df["atr"].to_numpy()
    n = len(df)
    trades: list[TradeSqueeze] = []
    en_pos = False
    idx_entrada = precio_entrada = maximo = trailing = None
    for i in range(n):
        if not en_pos:
            if entra[i] and atr[i] == atr[i]:  # not NaN
                en_pos = True
                idx_entrada, precio_entrada = i, close[i]
                maximo = close[i]
                trailing = close[i] - k_atr_trailing * atr[i]
        else:
            maximo = max(maximo, close[i])
            trailing = max(trailing, maximo - k_atr_trailing * atr[i])
            if close[i] < trailing:
                trades.append(TradeSqueeze(idx_entrada, i, precio_entrada, close[i]))
                en_pos = False
    return trades
