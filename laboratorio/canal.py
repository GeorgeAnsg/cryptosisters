"""
Canal (Donchian 20/10) filtrado por régimen de BTC — RoturaCanalLargo,
portado de corvus2 (`~/Desktop/corvus2/user_data/strategies/rotura_canal.py`
+ `rotura_canal_largo.py`). Vive en laboratorio/ hasta pasar las 6 puertas
en corvus4; no se importa desde motores/.

Adaptado a BTC-solo: en corvus2 esto operaba muchas monedas, filtradas por
si BTC estaba alcista o bajista. Aquí la "moneda" que rompe canal y la
referencia de régimen son el mismo activo (BTC), porque corvus4 se
construye solo con BTC (decisión cerrada, ver docs/00-PLAN-MAESTRO.md §10).

Qué dice la señal, en palabras normales:
- Se compra cuando BTC rompe por encima de su propio máximo de 20 días
  (aprox. 120 velas de 4h), Y ADEMÁS BTC está por encima de su media de
  200 días (contexto alcista de fondo).
- Se cierra la posición cuando BTC cae de vuelta a su canal de 10 días
  (aprox. 60 velas de 4h), O cuando BTC pasa a estar por debajo de su
  media de 200 días (protección: se sale a efectivo si el fondo se pone
  bajista) -- lo que ocurra antes.

El canal usa `shift(1)` a propósito: el máximo de 20 días NUNCA incluye la
vela de hoy, porque si la incluyera, el precio jamás podría "romper" su
propio máximo (sería mirar al futuro de forma trivial). Esto ya lo
comprobó la Puerta 1 en corvus2; aquí se hereda el diseño, no el veredicto.
"""
from __future__ import annotations

import pandas as pd

VELAS_DIA = 6                    # 24h / 4h
VELAS_ENTRADA = 20 * VELAS_DIA   # canal de 20 días
VELAS_SALIDA = 10 * VELAS_DIA    # canal de 10 días
VELAS_REGIMEN = 200 * VELAS_DIA  # media de 200 días


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["canal_alto"] = df["high"].shift(1).rolling(VELAS_ENTRADA).max()
    df["canal_bajo"] = df["low"].shift(1).rolling(VELAS_ENTRADA).min()
    df["salida_alto"] = df["high"].shift(1).rolling(VELAS_SALIDA).max()
    df["salida_bajo"] = df["low"].shift(1).rolling(VELAS_SALIDA).min()
    df["media_200d"] = df["close"].rolling(VELAS_REGIMEN).mean()
    return df


def calcular_senales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["btc_bull"] = df["close"] > df["media_200d"]
    df["btc_bear"] = df["close"] < df["media_200d"]

    df["rompe_arriba"] = (df["close"] > df["canal_alto"]).fillna(False)
    df["vuelve_abajo"] = (df["close"] < df["salida_bajo"]).fillna(False)

    df["entra_largo"] = df["rompe_arriba"] & df["btc_bull"]
    df["sale_largo"] = df["vuelve_abajo"] | df["btc_bear"]
    return df
