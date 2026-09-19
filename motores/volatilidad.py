"""
ATR (rango verdadero medio) como funcion compartida de motores/, graduada
desde `laboratorio/patrones/volatilidad.py::atr_pct` el 13-sept-2026.

Por que aqui y no en laboratorio: `salidas/` (stop/objetivo por
volatilidad) necesita esta formula, y la regla del proyecto (README.md
raiz) es que ninguna capa de produccion importa laboratorio/. Formula sin
ningun cambio respecto al original -- `laboratorio/patrones/volatilidad.py`
ahora importa esta misma funcion en vez de mantener su propia copia, para
no repetir el bug de "misma formula, dos copias que se desincronizan"
encontrado el 12-sept-2026 en los pesos de forma de tecno/suelo (ver
`entradas/doble_techo.py`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def atr_pct(df: pd.DataFrame, ventana: int = 14) -> np.ndarray:
    """ATR como % del precio de cierre, causal -- usa solo velas ya
    cerradas hasta cada punto, ninguna del futuro."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    rango_verdadero = np.maximum(
        high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close))
    )
    atr = pd.Series(rango_verdadero).rolling(ventana).mean().to_numpy()
    return atr / close * 100


def atr_absoluto(df: pd.DataFrame, ventana: int = 14) -> np.ndarray:
    """ATR en unidades de precio (no %) -- lo que hace falta para fijar
    un stop/objetivo como precio_entrada +/- k*ATR."""
    return atr_pct(df, ventana) / 100 * df["close"].to_numpy()
