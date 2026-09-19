"""
salidas/ -- señal de salida "racha rota".

Cierra la operación si la racha de picos/valles confirmados que sostenía
la tendencia (techos cada vez más altos para un largo, suelos cada vez
más bajos para un corto) se rompe -- ver `motores/canal_ascendente.py` y
`motores/canal_descendente.py` para el concepto de tendencia sostenida
por otra vía; aquí se usa directamente el propio detector de doble
techo/suelo (`entradas/doble_techo.py`, `entradas/doble_suelo.py`) para
marcar cada máximo/mínimo aparente que el sistema causal pudo confirmar,
y se seguella secuencia.

Limitación conocida, DELIBERADAMENTE no resuelta (ver
`laboratorio/patrones/sistema_confirmado_switch_14sept2026.py`,
docstring): si nunca llega a confirmarse ningún pico/valle cerca de la
operación, esta señal se queda "ciega" -- no es un bug de calibración, es
cómo está definida. Por eso `salidas/pendiente_acelerada.py` existe como
señal INDEPENDIENTE que cubre exactamente ese hueco (no depende de
ningún patrón confirmado), y las dos se usan A LA VEZ en producción, no
una en vez de la otra.

Validado 14-sept-2026 junto con el resto de "parámetros confirmados"
(ver `laboratorio/patrones/sistema_confirmado_switch_14sept2026.py`):
- N_LEN=4, M_DIAS=5: hace falta una racha de al menos 4 picos/valles
  seguidos, cada uno dentro de 5 días del anterior, para que se considere
  una tendencia sostenida cuya ruptura merece cerrar la operación.
- El aviso de racha rota NO cierra de inmediato -- se combina con la
  pendiente ATR como confirmación retardada (ver
  `salidas/stop_objetivo.simular_trade`, parámetros
  `senal_con_confirmacion`/`serie_confirmacion`/
  `caida_relativa_confirmacion=0.30`): solo se honra cuando la pendiente
  ya se ha enfriado un 30% relativo desde su propio extremo alcanzado
  DESDE que se abrió la operación. Arregla el caso hipersensible de
  cortar ganadores sanos en su respiración normal.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

Direccion = Literal["largo", "corto"]

N_LEN = 4  # longitud minima de racha, ajustado y confirmado 14-sept-2026
M_DIAS = 5  # dias maximos entre puntos consecutivos de la racha
CAIDA_RELATIVA_CONFIRMACION = 0.30  # confirmacion retardada via pendiente ATR


def puntos_confirmados(df: pd.DataFrame, aparentes_fn, en_vivo_fn) -> list[tuple[int, float]]:
    """[(idx, precio)] de cada máximo/mínimo aparente que el sistema causal
    pudo puntuar -- mismo criterio que el mapa de probabilidad en vivo de
    `entradas/`. `aparentes_fn` es `minimos_aparentes`/`maximos_aparentes`
    y `en_vivo_fn` es `calcular_en_vivo`, ambos de `entradas/doble_suelo.py`
    o `entradas/doble_techo.py` según la dirección."""
    close = df["close"].to_numpy()
    out = []
    for idx in aparentes_fn(close):
        if en_vivo_fn(df, idx, dia_transcurrido=0) is not None:
            out.append((idx, close[idx]))
    return out


def calcular_racha_rota(puntos: list[tuple[int, float]], n_total: int,
                         direccion_favorable: str, n_len: int = N_LEN, m_dias: int = M_DIAS) -> np.ndarray:
    """`direccion_favorable="creciente"` para techos (largo: quiero techos
    cada vez más altos, la racha se rompe con uno más bajo).
    `direccion_favorable="decreciente"` para suelos (corto: quiero suelos
    cada vez más bajos, la racha se rompe con uno más alto)."""
    rota = np.zeros(n_total, dtype=bool)
    racha_len = 1
    anterior = None
    for idx, precio in puntos:
        if anterior is not None:
            dias = idx - anterior[0]
            va_a_favor = (precio > anterior[1]) if direccion_favorable == "creciente" else (precio < anterior[1])
            if va_a_favor and dias <= m_dias:
                racha_len += 1
            else:
                if racha_len >= n_len:
                    rota[idx] = True
                racha_len = 1
        anterior = (idx, precio)
    return rota


def calcular_para_direccion(df: pd.DataFrame, direccion: Direccion) -> np.ndarray:
    """Punto de entrada de alto nivel: dado un df OHLCV y una dirección,
    devuelve el array booleano de racha rota listo para pasar como
    `senal_con_confirmacion` a `stop_objetivo.simular_trade`."""
    from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo, minimos_aparentes
    from entradas.doble_techo import calcular_en_vivo as en_vivo_techo, maximos_aparentes

    n = len(df)
    if direccion == "largo":
        puntos = puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
        return calcular_racha_rota(puntos, n, direccion_favorable="creciente")
    puntos = puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    return calcular_racha_rota(puntos, n, direccion_favorable="decreciente")
