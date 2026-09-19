"""
Utilidad de normalizacion por volatilidad, reutilizable por cualquier
detector del proyecto (11-sept-2026, idea del usuario): los parametros
"ideal" de los motores (`ancho_ideal_pct` en canal_flexible.py,
`caida_ideal_pct` en caida_recuperacion.py, etc.) se tunearon mirando
BTC -- pasarlos tal cual a un activo mas o menos volatil (XRP mas
nervioso, oro mas tranquilo) no tiene sentido: un canal "normal" en XRP
es mas ancho que uno "normal" en BTC solo porque XRP se mueve mas en
general, no porque sea un canal mas fuerte o mas real.

Principio de diseño (confirmado con el usuario): el motor se queda
GENERICO, sin saber nada de volatilidad -- ver canal_flexible.py, no se
toca. Esta capa se llama ANTES, calcula cuanto se mueve el activo en el
periodo analizado (ATR% del precio) y devuelve el factor por el que
escalar cualquier parametro "ideal" ya tuneado en BTC, para pasarselo al
motor como un numero normal (el motor nunca ve un "ATR", solo ve el
numero ya escalado). Es una capa de entrada, no un filtro que se aplique
a la salida ni una fusion de detectores -- eso seria fase posterior.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from motores.volatilidad import atr_pct  # noqa: F401 -- reexportado, ver nota abajo

# Mediana historica de ATR% (14 dias) de BTC en el periodo de Desarrollo
# -- el activo sobre el que se tunearon los parametros "ideal" que ya
# existen en los motores (ancho_ideal_pct=8.0, caida_ideal_pct=15.0,
# etc.). No es un umbral de calidad elegido a mano -- es una MEDIDA real
# de BTC que sirve de punto de referencia neutro (factor=1.0 para BTC).
REFERENCIA_ATR_PCT_BTC = 4.65

# `atr_pct` se graduo a `motores/volatilidad.py` el 13-sept-2026 (lo
# necesitaba `salidas/`, que no puede importar laboratorio/) -- se
# reimporta aqui en vez de mantener una segunda copia de la formula, para
# no repetir el bug de "misma formula, dos copias" (ver
# `entradas/doble_techo.py`, correccion del 12-sept-2026).


def factor_volatilidad(
    df: pd.DataFrame, ventana: int = 14, referencia: float = REFERENCIA_ATR_PCT_BTC
) -> float:
    """Cuanto hay que multiplicar un parametro 'ideal' tuneado en BTC para
    adaptarlo a este activo/periodo -- >1 si es mas volatil que BTC, <1 si
    es mas tranquilo (ej. oro). Usa la MEDIANA del tramo completo pasado en
    `df` (no la media, para no dejarse arrastrar por un solo dia extremo).
    `df` puede ser el historico completo de un activo (factor por activo)
    o solo un tramo reciente (factor por regimen de volatilidad actual) --
    la funcion no distingue, es quien la llama quien decide que ventana
    de tiempo representa "la volatilidad de referencia" en cada caso."""
    serie = atr_pct(df, ventana)
    actual = float(np.nanmedian(serie))
    return actual / referencia


def escalar(
    valor_base: float, df: pd.DataFrame, ventana: int = 14, referencia: float = REFERENCIA_ATR_PCT_BTC
) -> float:
    """Escala un parametro 'ideal' (tuneado en BTC) al activo/periodo de `df`."""
    return valor_base * factor_volatilidad(df, ventana, referencia)
