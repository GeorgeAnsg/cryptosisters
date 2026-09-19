"""
salidas/ -- señal de salida "pendiente acelerada".

Corta la operacion si el precio se movio demasiado fuerte, demasiado
rapido, EN CONTRA de la posicion -- sin depender de que exista ningun
patron de doble techo/suelo confirmado cerca (a diferencia de la logica
de racha rota, que SI depende de eso y por tanto se queda apagada cuando
no hay ningun pico confirmado a mano; ver el caso real de ETH 02-abr-2024
en `laboratorio/patrones/canal_sobre_sistema_completo.py`, docstring).
Pensada para usarse junto a `stop_objetivo.simular_trade` a traves del
gancho generico `senal_externa` -- esta capa no sabe nada de patrones ni
de regimen, solo mide velocidad de precio.

Validacion (15-sept-2026, `laboratorio/patrones/validacion_puertas_pendiente_sin_filtro.py`):
- Umbral (1.5 x ATR sobre 5 dias) ajustado SOLO en ETH, congelado y
  confirmado sin retocar en BTC y XRP -- mejora sobre el sistema base en
  ETH (+12.4%) y XRP (+3.2%), practicamente igual en BTC (+0.2%, ni
  mejora ni empeora).
- Puerta 1 (causalidad): PASA -- 25 cortes probados, 0 fugas de futuro.
- Puerta 5 (recursividad): PASA -- 25 puntos probados con solo 60 velas
  de historia disponible, 0 diferencias (el indicador solo mira 5 dias
  atras, no arrastra memoria de mas alla).
- Puerta 4 (DSR): PASA con margen amplio en las 3 monedas (t-stat 7.0-10.6
  frente a un liston de 2.69 con el presupuesto de intentos actual, 161).
- Puerta 3 (costes): la cuenta compuesta sobre las operaciones reales
  sigue muy por encima del capital inicial incluso a 1.0%/operacion de
  coste (muy por encima del coste real documentado en QuantFury, ~0% en
  BTC) -- la ventaja no es fragil frente a costes.

Lo que NO se lleva a produccion de esta fase: la mayoria de filtros de
contexto que modulan CUANDO aplicar este corte (canal lateral casero,
regimen NEUTRO, Efficiency Ratio, percentil por activo, volumen,
dominancia, canal-percentil-relativo, canal-percentil+piso, aceleracion
de la aceleracion, forma de vela) fallaron o no generalizaron (ver
observaciones 0022-0027 y `registro/intentos.jsonl`).

**Excepcion, sin resolver todavia (17-sept-2026):** el filtro de canal
por CALIDAD ABSOLUTA (`probabilidad_forma>=0.5` sobre el motor
`canal_ascendente`/`canal_descendente` graduado, no el detector casero) SI
funciono -- es el resultado con mas solidez estadistica de toda la
investigacion (BTC p=0.015). Sigue sin migrar a `filtros/` porque tiene un
defecto conocido en XRP que dos intentos de arreglo no consiguieron
resolver sin empeorar BTC (ver `laboratorio/patrones/pendiente_veto_canal.py`
y `registro/intentos.jsonl`). Hasta que se decida si se acepta con ese
defecto o se sigue intentando arreglar, esta version SIN NINGUN filtro
(la de este fichero) es la que corre en `ejecucion/cuenta_referencia.py`.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

Direccion = Literal["largo", "corto"]

UMBRAL_PENDIENTE_ATR = 1.5  # ajustado en ETH, confirmado sin tocar en BTC/XRP
VENTANA_DIAS = 5


def calcular_pendiente_atr(df: pd.DataFrame, atr: np.ndarray, ventana_dias: int = VENTANA_DIAS) -> np.ndarray:
    """(close[i] - close[i-ventana_dias]) / atr[i] -- movimiento de precio
    normalizado por volatilidad, causal (solo mira `ventana_dias` atras).
    Positivo = subida fuerte reciente, negativo = caida fuerte reciente."""
    close = df["close"].to_numpy()
    n = len(close)
    pendiente = np.full(n, np.nan)
    for i in range(ventana_dias, n):
        if not np.isnan(atr[i]) and atr[i] > 0:
            pendiente[i] = (close[i] - close[i - ventana_dias]) / atr[i]
    return pendiente


def señal_para_direccion(
    pendiente: np.ndarray, direccion: Direccion, umbral: float = UMBRAL_PENDIENTE_ATR,
) -> np.ndarray:
    """Array booleano listo para pasar como `senal_externa` a
    `stop_objetivo.simular_trade` -- True el dia que el movimiento en
    contra de esta direccion supera el umbral. Un largo se corta con una
    caida fuerte (pendiente muy negativa); un corto, con una subida
    fuerte (pendiente muy positiva)."""
    con_valor = ~np.isnan(pendiente)
    if direccion == "largo":
        return con_valor & (pendiente <= -umbral)
    return con_valor & (pendiente >= umbral)
