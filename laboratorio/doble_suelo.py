"""
Doble suelo SELECTIVO — portado de corvus2
(`user_data/strategies/doble_fondo_selectivo.py`). Vive en laboratorio/,
sin pasar aún ninguna puerta en corvus4.

Situación de partida (distinta de Canal): esta versión concreta (con
confirmación de volumen) SÍ tiene evidencia pre-registrada de 2025 en
corvus2 (`DobleFondoVolVolumen`: +17,7% no visto). Ojo: una nota antigua
del roadmap de corvus2 decía "aún no bate costes" -- esa nota estaba
DESATUALIZADA, corresponde a una versión anterior sin la confirmación de
volumen; se corrige aquí para no repetir el error.

Qué dice la señal, en palabras normales:
- Se busca un patrón de "doble suelo": el precio toca una zona de mínimo
  al menos 2 veces en una ventana de ~20 días (120 velas de 4h), sin bajar
  mucho más de esa zona cada vez (tolerancia 3%).
- El patrón tiene que ser GRANDE: la distancia entre el suelo y el máximo
  de la ventana (el "neckline", el cuello que hay que romper) tiene que
  ser al menos un 15% del precio. La hipótesis original: patrones pequeños
  se los come el coste, solo los grandes dejan margen de verdad.
- Entrada: cuando el precio rompe por encima del neckline, Y ADEMÁS el
  volumen de esa vela supera 1,5x su media de 30 velas -- confirmación de
  que la rotura es de verdad, no un movimiento sin fuerza detrás.
- Salida: objetivo fijo del 30%, stop fijo del -12% -- sin salida dinámica
  todavía (eso sigue pendiente de mejorar, igual que en el original).

Nota: la versión validada en corvus2 también incluía tamaño de posición
por volatilidad (ATR) -- eso es una decisión de `tamano/`, no cambia el
retorno % de cada operación individual, así que se deja fuera de esta
primera comprobación y se retoma en su capa correspondiente si esto pasa
las puertas.
"""
from __future__ import annotations

import pandas as pd

VENTANA = 120          # ~20 días en 4h
TOLERANCIA_SUELO = 0.03
ALTURA_MINIMA = 0.15
MIN_TOQUES = 2
OBJETIVO_ROI = 0.30
STOPLOSS = -0.12
VOL_MULT = 1.5
VOL_N = 30


def calcular_indicadores(
    df: pd.DataFrame,
    ventana: int = VENTANA,
    tolerancia_suelo: float = TOLERANCIA_SUELO,
    vol_n: int = VOL_N,
) -> pd.DataFrame:
    df = df.copy()
    soporte = df["low"].rolling(ventana).min()
    cerca = df["low"] <= soporte * (1 + tolerancia_suelo)
    df["toques"] = cerca.rolling(ventana).sum().shift(1)
    df["neckline"] = df["high"].rolling(ventana).max().shift(1)
    df["soporte"] = soporte.shift(1)
    df["altura"] = (df["neckline"] - df["soporte"]) / df["soporte"]
    df["vol_media"] = df["volume"].rolling(vol_n).mean()
    return df


def calcular_senales(
    df: pd.DataFrame,
    min_toques: int = MIN_TOQUES,
    altura_minima: float = ALTURA_MINIMA,
    vol_mult: float = VOL_MULT,
) -> pd.DataFrame:
    df = df.copy()
    rompe = (df["close"] > df["neckline"]) & (df["close"].shift(1) <= df["neckline"])
    vol_ok = df["volume"] > vol_mult * df["vol_media"]
    df["entra_largo"] = (
        rompe.fillna(False)
        & (df["toques"] >= min_toques)
        & (df["altura"] >= altura_minima)
        & vol_ok.fillna(False)
    )
    return df
