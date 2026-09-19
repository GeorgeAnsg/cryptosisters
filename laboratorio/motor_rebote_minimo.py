"""
Motor nuevo -- rebote tras minimo, en desarrollo (idea del usuario, separado
del grid): "tras una caida, el precio suele tardar unos dias en marcar
techo, con un ritmo bastante consistente" (medido en
canal_probabilidad_continua.py / analisis de minimos-a-maximo: mediana
5-8 dias, subida mediana 7-13%).

Deteccion CAUSAL (sin mirar al futuro, a diferencia del primer analisis
exploratorio que usaba argrelextrema con ventana centrada):
- Entra cuando el precio lleva `dias_caida` dias bajando o lateral desde
  un maximo reciente, y luego encadena `confirmacion` dias subiendo
  seguidos -- eso es lo unico que se puede saber en tiempo real el dia
  de la señal, sin trampa de mirar hacia adelante.
- Sale a los `dias_objetivo` dias (mediana medida) o si toca el stop,
  lo que ocurra primero.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TradeRebote:
    idx_entrada: int
    idx_salida: int
    retorno_pct: float
    motivo: str  # "objetivo_tiempo", "stop"


def simular(
    df: pd.DataFrame,
    dias_caida_min: int = 5,
    caida_min_pct: float = 5.0,
    confirmacion: int = 2,
    dias_objetivo: int = 6,
    stop_pct: float = -8.0,
) -> list[TradeRebote]:
    close = df["close"].to_numpy()
    n = len(close)
    trades: list[TradeRebote] = []
    en_posicion = False
    idx_entrada = precio_entrada = None
    i = dias_caida_min + confirmacion

    while i < n:
        if not en_posicion:
            maximo_reciente = close[i - confirmacion - dias_caida_min: i - confirmacion + 1].max()
            caida = (close[i - confirmacion] / maximo_reciente - 1) * 100
            subiendo = all(close[i - confirmacion + k] > close[i - confirmacion + k - 1] for k in range(confirmacion + 1))
            if caida <= -caida_min_pct and subiendo:
                en_posicion = True
                idx_entrada = i
                precio_entrada = close[i]
            i += 1
        else:
            dias_en_posicion = i - idx_entrada
            retorno_actual = (close[i] / precio_entrada - 1) * 100
            if retorno_actual <= stop_pct:
                trades.append(TradeRebote(idx_entrada, i, retorno_actual, "stop"))
                en_posicion = False
            elif dias_en_posicion >= dias_objetivo:
                trades.append(TradeRebote(idx_entrada, i, retorno_actual, "objetivo_tiempo"))
                en_posicion = False
            i += 1

    return trades
