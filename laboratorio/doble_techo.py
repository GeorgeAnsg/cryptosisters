"""
Doble techo SELECTIVO, en corto — espejo bajista de doble_suelo.py, portado
de corvus2 (`user_data/strategies/doble_techo.py`, variante
`DobleTechoDowntrend`, la mejor de las tres probadas allí).

Situación de partida: hay evidencia real (+143% neto en Desarrollo de
corvus2), pero con un ASTERISCO importante ya anotado: casi toda esa
ganancia viene del único mercado bajista disponible en esos datos (2022).
Un solo caso no demuestra nada por sí solo (misma limitación que el ciclo
del halving, n=1).

Lo que cambia aquí: corvus4 tiene 9 años de histórico BTC (2017-2026, no
solo 2020-2026), así que hay un SEGUNDO mercado bajista independiente para
comprobar -- el de 2018 (BTC cayó de ~20.000 a ~3.000). Si el patrón
también gana ahí, ya no es n=1.

Qué dice la señal: espejo exacto de doble suelo -- resistencia tocada
≥2 veces en ventana de 120 velas, patrón ≥15% de altura, ROTURA HACIA
ABAJO del "neckline" (el soporte del patrón) para entrar en corto. Filtro:
solo se opera si BTC está en tendencia bajista de verdad -- por debajo de
su media de 200 días Y esa media cayendo (no solo un bajón pasajero que
luego rebota). Salida: objetivo -30% (el corto gana si cae), stop +12%
(el corto pierde si sube).

Adaptado a BTC-solo: la moneda que forma el patrón y la referencia de
régimen son el mismo activo (igual que se hizo con Canal).
"""
from __future__ import annotations

import pandas as pd

VENTANA = 120
TOLERANCIA_TECHO = 0.03
ALTURA_MINIMA = 0.15
MIN_TOQUES = 2
OBJETIVO_ROI = -0.30   # el corto gana si el precio CAE un 30%
STOPLOSS = 0.12        # el corto pierde si el precio SUBE un 12%
VELAS_REGIMEN = 200 * 6
MA_CAE_VELAS = 180


def calcular_indicadores(
    df: pd.DataFrame,
    ventana: int = VENTANA,
    tolerancia_techo: float = TOLERANCIA_TECHO,
    velas_regimen: int = VELAS_REGIMEN,
    ma_cae_velas: int = MA_CAE_VELAS,
) -> pd.DataFrame:
    df = df.copy()
    resist = df["high"].rolling(ventana).max()
    cerca = df["high"] >= resist * (1 - tolerancia_techo)
    df["toques"] = cerca.rolling(ventana).sum().shift(1)
    df["neckline"] = df["low"].rolling(ventana).min().shift(1)
    df["resist"] = resist.shift(1)
    df["altura"] = (df["resist"] - df["neckline"]) / df["neckline"]

    ma = df["close"].rolling(velas_regimen).mean()
    cae = ma < ma.shift(ma_cae_velas)
    df["btc_bear"] = (df["close"] < ma) & cae
    return df


def calcular_senales(
    df: pd.DataFrame,
    min_toques: int = MIN_TOQUES,
    altura_minima: float = ALTURA_MINIMA,
) -> pd.DataFrame:
    df = df.copy()
    rompe = (df["close"] < df["neckline"]) & (df["close"].shift(1) >= df["neckline"])
    df["entra_corto"] = (
        rompe.fillna(False)
        & (df["toques"] >= min_toques)
        & (df["altura"] >= altura_minima)
        & df["btc_bear"].fillna(False)
    )
    return df
