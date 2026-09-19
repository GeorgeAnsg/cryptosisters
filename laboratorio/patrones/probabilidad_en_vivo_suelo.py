"""
Espejo de `probabilidad_en_vivo_techo.py` para el suelo, pero usando la
formula CORREGIDA de `doble_suelo_motor_v2.py` (regimen alcista solo /
regimen bajista + lejos del ATH), no la formula antigua y ya superada de
`doble_techo_probabilidad_total.py` que todavia usa el modulo del techo
(detectado el 12-sept-2026 al revisar este modulo -- pendiente decidir si
se actualiza tambien el del techo).

Curva de supervivencia medida de cero para el suelo
(`probabilidad_evolutiva_suelo.py`, promedio ETH+BTC, historial completo):
  dia 0 (candidato, recien detectado): P(termine confirmado) = 39%
  dia 1 (sobrevivio 1 dia): P(sobreviva dia 2) = 76%
  dia 2 (sobrevivio 2 dias): P(sobreviva dia 3, confirmado) = 89%
  dia 3: confirmado del todo = 100%
No es la misma curva del techo (31/71/85/100) -- parecida en forma pero
mas alta en cada escalon, medida por separado, no asumida igual.

Mecanismo: en el dia k desde que aparecio el minimo aparente (posible
fondo2), se calcula la probabilidad_total COMO SI ese minimo ya fuera el
fondo2 definitivo (via la logica de doble_suelo_motor_v2: regimen +
contexto) y se multiplica por la curva de supervivencia del dia k.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.patrones import doble_suelo_flexible, regimen_mercado
from laboratorio.patrones.doble_suelo_motor_v2 import _score_ath_lejos
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
from laboratorio.patrones.regimen_mercado import TipoRegimen

CURVA_SUPERVIVENCIA_SUELO = {0: 0.39, 1: 0.76, 2: 0.89, 3: 1.0}


@dataclass
class CandidatoEnVivoSuelo:
    idx_minimo_aparente: int
    dia_transcurrido: int
    probabilidad_total_si_confirma: float
    probabilidad_en_vivo: float


def _minimos_aparentes(close: np.ndarray, ventana_pasada: int = 3) -> list[int]:
    """Un dia `i` es 'minimo aparente' si es el mas bajo de los ultimos
    `ventana_pasada` dias (incluyendose el mismo) -- se sabe en tiempo
    real, sin mirar al futuro."""
    n = len(close)
    candidatos = []
    for i in range(ventana_pasada, n):
        if close[i] == close[i - ventana_pasada: i + 1].min():
            candidatos.append(i)
    return candidatos


def calcular_en_vivo(
    df: pd.DataFrame,
    idx_minimo_aparente: int,
    dia_transcurrido: int,
    ventana_min_dias: int = 4,
    ventana_max_dias: int = 45,
    tolerancia_nivel_pct: float = 15.0,
    rebote_ideal_pct: float = 8.0,
    altura_ideal_pct: float = 20.0,
    peso_nivel: float = 0.2,
    peso_rebote: float = 0.2,
    peso_tiempo: float = 0.1,
    peso_altura: float = 0.5,
    peso_forma: float = 0.5,
    peso_contexto: float = 0.5,
) -> CandidatoEnVivoSuelo | None:
    """Trata `idx_minimo_aparente` COMO SI fuera el fondo2 definitivo, igual
    logica que `probabilidad_en_vivo_techo.calcular_en_vivo` mirror-imagen:
    no se puede reutilizar `doble_suelo_flexible.detectar()` tal cual
    porque su detector interno de fondos exige 3 dias de margen futuro
    antes de aceptar un candidato -- justo lo que esto evita."""
    close_s = df["close"]
    close = close_s.to_numpy()

    fondos_confirmados = doble_suelo_flexible._detectar_fondos_simple(close)
    fondo1_opciones = [f for f in fondos_confirmados if f < idx_minimo_aparente]
    if not fondo1_opciones:
        return None

    precio2 = close[idx_minimo_aparente]
    mejor_score, mejor = -1.0, None
    for idx1 in fondo1_opciones:
        dias = idx_minimo_aparente - idx1
        if dias < ventana_min_dias or dias > ventana_max_dias:
            continue
        precio1 = close[idx1]
        diferencia_nivel_pct = (precio2 - precio1) / precio1 * 100
        maximo_intermedio = close[idx1: idx_minimo_aparente + 1].max()
        rebote_intermedio_pct = (maximo_intermedio - min(precio1, precio2)) / min(precio1, precio2) * 100

        score_nivel = max(0.0, 1 - abs(diferencia_nivel_pct) / tolerancia_nivel_pct)
        score_rebote = min(rebote_intermedio_pct / rebote_ideal_pct, 1.0)
        score_altura = min(rebote_intermedio_pct / altura_ideal_pct, 1.0)
        score_tiempo = 1.0
        prob_forma = (peso_nivel * score_nivel + peso_rebote * score_rebote
                      + peso_tiempo * score_tiempo + peso_altura * score_altura)
        if prob_forma > mejor_score:
            mejor_score, mejor = prob_forma, idx1

    if mejor is None:
        return None
    idx_fondo1, probabilidad_forma = mejor, mejor_score

    sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    tipo, score_regimen = regimen_mercado.clasificar(df, idx_minimo_aparente, sma200)

    if tipo == TipoRegimen.ALCISTA:
        score_contexto = score_regimen
    elif tipo == TipoRegimen.BAJISTA:
        dist_ath_pct = (ath_hasta[idx_minimo_aparente] - precio2) / ath_hasta[idx_minimo_aparente] * 100
        score_ath_lejos = _score_ath_lejos(dist_ath_pct)
        score_contexto = (score_regimen * score_ath_lejos) ** 0.5
    else:
        score_contexto = 1e-3

    prob_forma_safe = max(probabilidad_forma, 1e-3)
    score_contexto_safe = max(score_contexto, 1e-3)
    probabilidad_total = prob_forma_safe ** peso_forma * score_contexto_safe ** peso_contexto

    curva = CURVA_SUPERVIVENCIA_SUELO[min(dia_transcurrido, 3)]
    return CandidatoEnVivoSuelo(
        idx_minimo_aparente=idx_minimo_aparente, dia_transcurrido=dia_transcurrido,
        probabilidad_total_si_confirma=round(probabilidad_total, 3),
        probabilidad_en_vivo=round(probabilidad_total * curva, 3),
    )
