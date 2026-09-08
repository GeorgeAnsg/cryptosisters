"""
M7 — Spring de Wyckoff. Definición operativa de
investigacion/06-traders-discrecional.md §2.2 (la más precisa encontrada
en la investigación, aunque sin backtest académico independiente -- solo
lógica de mercado y heurísticas de comunidad, "plausible pero sin
evidencia publicada").

Mecanismo: ruptura falsa por debajo de un rango de soporte (sacude a los
que tienen stop ahí) con volumen NO extremo (paradoja Wyckoff: poco
volumen en la ruptura = poca oferta real, señal de fortaleza) + un "test"
posterior que vuelve cerca del mínimo con volumen todavía más bajo y
reacciona al alza.

Simplificado respecto a la definición completa (no se clasifica por tipos
1/2 de penetración) para una primera prueba honesta.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

VENTANA_RANGO = 60          # ~10 dias en 4h
TOLERANCIA_TEST = 0.02
VELAS_MAX_PARA_TEST = 20    # cuanto se espera, como mucho, el "test" tras el spring
MULT_VOL_PENETRACION_MAX = 1.2   # penetracion NO debe tener volumen extremo
MULT_VOL_TEST_MAX = 0.6          # test debe tener volumen bastante menor que la penetracion


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["soporte_rango"] = df["low"].rolling(VENTANA_RANGO).min().shift(1)
    df["vol_media"] = df["volume"].rolling(VENTANA_RANGO).mean().shift(1)
    return df


@dataclass
class TradeSpring:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, objetivo: float = 0.20, margen_stop: float = 0.03) -> list[TradeSpring]:
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    close = df["close"].to_numpy()
    open_ = df["open"].to_numpy()
    volume = df["volume"].to_numpy()
    soporte = df["soporte_rango"].to_numpy()
    vol_media = df["vol_media"].to_numpy()
    n = len(df)

    trades: list[TradeSpring] = []
    en_posicion = False
    idx_entrada = precio_entrada = stop = None

    # springs pendientes de test: (idx_spring, low_spring, vol_spring, idx_limite)
    springs_pendientes: list[tuple[int, float, float, int]] = []

    for i in range(n):
        if not en_posicion:
            # 1. detectar un spring nuevo en la vela i
            if (not pd.isna(soporte[i]) and not pd.isna(vol_media[i])
                    and low[i] < soporte[i]
                    and volume[i] < MULT_VOL_PENETRACION_MAX * vol_media[i]):
                springs_pendientes.append((i, low[i], volume[i], i + VELAS_MAX_PARA_TEST))

            springs_pendientes = [s for s in springs_pendientes if s[3] >= i]

            # 2. comprobar si la vela i es el "test" de algun spring pendiente
            for idx_spring, low_spring, vol_spring, idx_limite in springs_pendientes:
                if i <= idx_spring:
                    continue
                cerca_del_minimo = low[i] <= low_spring * (1 + TOLERANCIA_TEST)
                volumen_bajo = volume[i] < MULT_VOL_TEST_MAX * vol_spring
                vela_alcista = close[i] > open_[i]
                if cerca_del_minimo and volumen_bajo and vela_alcista:
                    en_posicion = True
                    idx_entrada = i
                    precio_entrada = close[i]
                    stop = min(low_spring, low[i]) * (1 - margen_stop)
                    springs_pendientes = []
                    break
        else:
            retorno = close[i] / precio_entrada - 1
            tocó_stop = close[i] <= stop
            if retorno >= objetivo or tocó_stop:
                motivo = "objetivo" if retorno >= objetivo else "stop"
                trades.append(TradeSpring(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False

    return trades
