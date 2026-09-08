"""
Patrones de una sola vela — Hammer, Engulfing (alcista y bajista).
Evidencia mixta en la literatura (ver investigacion/06-traders-discrecional.md):
el Hammer muestra algo de ventaja en un par de estudios académicos, pero
los backtests más grandes y rigurosos no encuentran ventaja como señal
SOLA. Aquí se usan solo como CONFIRMACIÓN extra sobre Doble suelo/techo,
que ya tienen ventaja demostrada -- nunca como señal independiente.

Definiciones estándar (Nison, "Japanese Candlestick Charting Techniques"):
- Hammer (alcista): cuerpo pequeño cerca de la parte alta del rango,
  mecha inferior larga (>= 2x el cuerpo), mecha superior mínima/nula.
- Shooting star (bajista): espejo del hammer -- cuerpo pequeño cerca de
  la parte baja, mecha superior larga, mecha inferior mínima.
- Engulfing alcista: vela verde cuyo cuerpo envuelve por completo el
  cuerpo de la vela roja anterior.
- Engulfing bajista: espejo -- vela roja que envuelve el cuerpo de la
  vela verde anterior.
"""
from __future__ import annotations

import pandas as pd


def calcular_patrones_vela(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cuerpo = (df["close"] - df["open"]).abs()
    rango = df["high"] - df["low"]
    mecha_inf = df[["open", "close"]].min(axis=1) - df["low"]
    mecha_sup = df["high"] - df[["open", "close"]].max(axis=1)

    df["hammer"] = (
        (mecha_inf >= 2 * cuerpo)
        & (mecha_sup <= 0.1 * rango)
        & (cuerpo > 0)
        & (rango > 0)
    ).fillna(False)

    df["shooting_star"] = (
        (mecha_sup >= 2 * cuerpo)
        & (mecha_inf <= 0.1 * rango)
        & (cuerpo > 0)
        & (rango > 0)
    ).fillna(False)

    open_prev, close_prev = df["open"].shift(1), df["close"].shift(1)
    verde_prev, roja_prev = close_prev > open_prev, close_prev < open_prev
    verde_ahora, roja_ahora = df["close"] > df["open"], df["close"] < df["open"]

    df["engulfing_alcista"] = (
        roja_prev & verde_ahora
        & (df["open"] <= close_prev) & (df["close"] >= open_prev)
    ).fillna(False)

    df["engulfing_bajista"] = (
        verde_prev & roja_ahora
        & (df["open"] >= close_prev) & (df["close"] <= open_prev)
    ).fillna(False)

    df["confirma_alcista"] = df["hammer"] | df["engulfing_alcista"]
    df["confirma_bajista"] = df["shooting_star"] | df["engulfing_bajista"]
    return df
