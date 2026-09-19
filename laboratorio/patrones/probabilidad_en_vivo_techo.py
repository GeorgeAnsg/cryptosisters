"""
Une dos piezas:
  1. `probabilidad_evolutiva_techo.py` -- cuanta confianza hay de que un
     maximo aparente aguante, segun cuantos dias lleva sin ser superado
     (dia 0 ~31%, dia 1 ~70%, dia 2 ~85%, dia 3 = 100%, ya confirmado).
  2. `doble_techo_motor_v2.py` -- forma + regimen (capas) + contexto
     (nivel repetido + ATH, o descuento alcista), calculado sobre un
     techo2 YA confirmado (3 dias despues del pico real).

ACTUALIZADO el 12-sept-2026: este modulo usaba la formula ANTIGUA de
`doble_techo_probabilidad_total.py` (antes de los dos bugs corregidos hoy
en el motor v2: el suelo de 1e-3 que aplastaba el bajista sin nivel
repetido, y el DIST_ATH_IDEAL_PCT=30 sin calibrar, ahora 90). Se
reimplementa aqui la misma logica de motor_v2 en vez de la antigua, para
que la probabilidad "en vivo" no diverja de la ya validada.

Objetivo (pedido explicito del usuario): una cifra que vaya SUBIENDO EN
VIVO cada dia mientras el patron se termina de formar, no solo un numero
final el dia que todo esta confirmado -- para poder decidir si merece la
pena apostar el trade ANTES de esperar la confirmacion completa.

Mecanismo: en el dia k desde que aparecio el maximo aparente (posible
techo2), se calcula la probabilidad_total COMO SI ese maximo ya fuera el
techo2 definitivo (su precio ya se conoce, lo que no se sabe aun es si
seguira siendo el mas alto) y se multiplica por la curva de supervivencia
del dia k. Es una probabilidad EN VIVO: sube si el candidato sigue
aguantando dia a dia, y en el dia 3 coincide exactamente con el numero
final ya validado (curva=100%).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.patrones import doble_techo_flexible, regimen_mercado
from laboratorio.patrones.doble_techo_motor_v2 import DESCUENTO_CONTEXTO_ALCISTA, _score_ath
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
from laboratorio.patrones.regimen_mercado import TipoRegimen

# Curva empirica de `probabilidad_evolutiva_techo.py` (promedio ETH+BTC,
# todo el historial, sin segmentar por volatilidad -- se vio que no discrimina).
# dia 0: P(que termine confirmado) visto desde el arranque.
# dia 1: P(que termine confirmado) dado que ya sobrevivio 1 dia.
# dia 2: P(que termine confirmado) dado que ya sobrevivio 2 dias.
# dia 3: confirmado del todo.
CURVA_SUPERVIVENCIA_TECHO = {0: 0.31, 1: 0.71, 2: 0.85, 3: 1.0}


@dataclass
class CandidatoEnVivo:
    idx_maximo_aparente: int
    dia_transcurrido: int  # 0, 1, 2 o 3 (3 = confirmado del todo)
    probabilidad_total_si_confirma: float  # forma+regimen+nivel, tratando el maximo aparente como techo2
    probabilidad_en_vivo: float  # la anterior * curva de supervivencia del dia


def _maximos_aparentes(close: np.ndarray, ventana_pasada: int = 3) -> list[int]:
    """Un dia `i` es 'maximo aparente' si es el mas alto de los ultimos
    `ventana_pasada` dias (incluyendose el mismo) -- esto SI se sabe en
    tiempo real, sin mirar al futuro."""
    n = len(close)
    candidatos = []
    for i in range(ventana_pasada, n):
        if close[i] == close[i - ventana_pasada: i + 1].max():
            candidatos.append(i)
    return candidatos


def calcular_en_vivo(
    df: pd.DataFrame,
    idx_maximo_aparente: int,
    dia_transcurrido: int,
    ventana_min_dias: int = 4,
    ventana_max_dias: int = 45,
    tolerancia_nivel_pct: float = 15.0,
    caida_ideal_pct: float = 8.0,
    altura_ideal_pct: float = 20.0,
    peso_nivel: float = 0.35,
    peso_caida: float = 0.25,
    peso_tiempo: float = 0.10,
    peso_altura: float = 0.30,
    peso_forma: float = 0.5,
    peso_contexto: float = 0.5,
) -> CandidatoEnVivo | None:
    """Trata `idx_maximo_aparente` COMO SI fuera el techo2 definitivo (para
    poder calcular forma/regimen/nivel ya mismo, sin esperar a los 3 dias
    que `doble_techo_flexible._detectar_techos_simple` necesita para
    confirmarlo con su ventana CENTRADA) y multiplica por la curva de
    supervivencia del dia transcurrido. No se puede reutilizar
    `doble_techo_flexible.detectar()` tal cual para esto -- su detector de
    techos interno mira 3 dias hacia el futuro antes de considerar un punto
    candidato, así que nunca incluiria a `idx_maximo_aparente` como techo2
    hasta el dia 3 (justo el problema que esto intenta resolver). Se
    reimplementa aqui la MISMA formula de puntuacion de forma (nivel/caida/
    altura/tiempo), aplicada solo a este candidato, usando como techo1
    cualquier pico YA confirmado con datos pasados (esos si tienen sus 3
    dias de margen cumplidos de sobra)."""
    close_s = df["close"]
    close = close_s.to_numpy()

    techos_confirmados = doble_techo_flexible._detectar_techos_simple(close)
    techo1_opciones = [t for t in techos_confirmados if t < idx_maximo_aparente]
    if not techo1_opciones:
        return None

    precio2 = close[idx_maximo_aparente]
    mejor_score, mejor = -1.0, None
    for idx1 in techo1_opciones:
        dias = idx_maximo_aparente - idx1
        if dias < ventana_min_dias or dias > ventana_max_dias:
            continue
        precio1 = close[idx1]
        diferencia_nivel_pct = (precio2 - precio1) / precio1 * 100
        minimo_intermedio = close[idx1: idx_maximo_aparente + 1].min()
        caida_intermedia_pct = (max(precio1, precio2) - minimo_intermedio) / max(precio1, precio2) * 100

        score_nivel = max(0.0, 1 - abs(diferencia_nivel_pct) / tolerancia_nivel_pct)
        score_caida = min(caida_intermedia_pct / caida_ideal_pct, 1.0)
        score_altura = min(caida_intermedia_pct / altura_ideal_pct, 1.0)
        score_tiempo = 1.0
        prob_forma = (peso_nivel * score_nivel + peso_caida * score_caida
                      + peso_tiempo * score_tiempo + peso_altura * score_altura)
        if prob_forma > mejor_score:
            mejor_score, mejor = prob_forma, idx1

    if mejor is None:
        return None
    idx_techo1, probabilidad_forma = mejor, mejor_score

    sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    tipo, score_regimen = regimen_mercado.clasificar(df, idx_maximo_aparente, sma200)

    nivel_actual = (close[idx_techo1] + precio2) / 2
    limite_previos = idx_techo1 - 3
    candidatos_previos = doble_techo_flexible.detectar(df.iloc[:limite_previos]) if limite_previos > 210 else []
    patron_previo = any(
        abs((close[c_prev.idx_techo1] + close[c_prev.idx_techo2]) / 2 - nivel_actual) / nivel_actual * 100
        <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
        for c_prev in candidatos_previos
    )

    # misma logica de capa 3 que doble_techo_motor_v2.calcular (12-sept-2026)
    if tipo == TipoRegimen.BAJISTA:
        if patron_previo:
            dist_ath_pct = (ath_hasta[idx_maximo_aparente] - precio2) / ath_hasta[idx_maximo_aparente] * 100
            score_ath = _score_ath(dist_ath_pct)
            score_contexto = (score_regimen * score_ath) ** 0.5
        else:
            score_contexto = score_regimen
    elif tipo == TipoRegimen.ALCISTA:
        dist_ath_pct = (ath_hasta[idx_maximo_aparente] - precio2) / ath_hasta[idx_maximo_aparente] * 100
        score_ath = _score_ath(dist_ath_pct)
        score_contexto = max((score_regimen * score_ath) ** 0.5 * DESCUENTO_CONTEXTO_ALCISTA, 1e-3)
    else:
        score_contexto = 1e-3

    prob_forma_safe = max(probabilidad_forma, 1e-3)
    score_contexto_safe = max(score_contexto, 1e-3)
    probabilidad_total = prob_forma_safe ** peso_forma * score_contexto_safe ** peso_contexto

    curva = CURVA_SUPERVIVENCIA_TECHO[min(dia_transcurrido, 3)]
    return CandidatoEnVivo(
        idx_maximo_aparente=idx_maximo_aparente, dia_transcurrido=dia_transcurrido,
        probabilidad_total_si_confirma=round(probabilidad_total, 3),
        probabilidad_en_vivo=round(probabilidad_total * curva, 3),
    )
