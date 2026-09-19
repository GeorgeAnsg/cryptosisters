"""
Regla de entrada para doble suelo, graduada desde
laboratorio/patrones/probabilidad_en_vivo_suelo.py el 12-sept-2026. Mismo
razonamiento que `entradas/doble_techo.py` -- leer ese fichero primero,
aqui no se repite la explicacion completa.

CONCLUSION VALIDADA (laboratorio/patrones/umbral_decision_en_vivo_suelo.py,
re-confirmada el 12-sept-2026 con la logica corregida sobre BTC/ETH
completos): esperar a que la confianza en vivo suba NO mejora el resultado
-- dia 0 da 7.81%/9.67% de retorno medio (BTC/ETH) frente a 3.94%/5.10%
esperando a 50% de confianza. Entrar en el DIA 0 (minimo aparente, sin
esperar confirmacion) es la regla, igual que en el techo -- mismo matiz
sobre no operar cualquier minimo aparente sin el filtro de
`probabilidad_total`, ver `entradas/doble_techo.py`.

CORRECCION DE ARQUITECTURA (12-sept-2026): igual que en el techo, la
version original tenia su propia copia de los pesos de forma
(peso_nivel=0.2/peso_rebote=0.2/peso_altura=0.5), desincronizada de
`motores/doble_suelo.py` (0.15/0.15/0.60). Aqui se importa
`_score_pareja_forma()` del motor graduado en vez de reimplementarla.

Nota: a diferencia del techo, el suelo no tiene "nivel/soporte repetido"
como factor (se probo y PERJUDICA, ver `motores/doble_suelo.py`) -- por
eso aqui no hay ningun calculo equivalente al `patron_previo` del techo.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from dataclasses import dataclass

import numpy as np
import pandas as pd

from motores import doble_suelo as motor
from motores import regimen_mercado
from motores.regimen_mercado import TipoRegimen

# Curva empirica (laboratorio/patrones/probabilidad_evolutiva_suelo.py,
# promedio ETH+BTC, historial completo) -- distinta de la del techo
# (31/71/85/100), medida por separado, no asumida igual.
CURVA_SUPERVIVENCIA_SUELO = {0: 0.39, 1: 0.76, 2: 0.89, 3: 1.0}


@dataclass
class CandidatoEntradaSuelo:
    idx_minimo_aparente: int
    dia_transcurrido: int
    probabilidad_total_si_confirma: float
    probabilidad_en_vivo: float


def minimos_aparentes(close: np.ndarray, ventana_pasada: int = 3) -> list[int]:
    """Un dia `i` es 'minimo aparente' si es el mas bajo de los ultimos
    `ventana_pasada` dias (incluyendose el mismo) -- se sabe en tiempo
    real, sin mirar al futuro."""
    n = len(close)
    return [i for i in range(ventana_pasada, n) if close[i] == close[i - ventana_pasada: i + 1].min()]


def calcular_en_vivo(
    df: pd.DataFrame,
    idx_minimo_aparente: int,
    dia_transcurrido: int,
    ventana_min_dias: int = 4,
    ventana_max_dias: int = 45,
    peso_forma: float = 0.5,
    peso_contexto: float = 0.5,
) -> CandidatoEntradaSuelo | None:
    """Trata `idx_minimo_aparente` COMO SI fuera el fondo2 definitivo,
    mismo mecanismo que `entradas.doble_techo.calcular_en_vivo`
    mirror-imagen."""
    close_s = df["close"]
    close = close_s.to_numpy()

    fondos_confirmados = motor._detectar_fondos_simple(close)
    fondo1_opciones = [f for f in fondos_confirmados if f < idx_minimo_aparente]
    if not fondo1_opciones:
        return None

    precio2 = close[idx_minimo_aparente]
    mejor_score, idx_fondo1 = -1.0, None
    for idx1 in fondo1_opciones:
        dias = idx_minimo_aparente - idx1
        if dias < ventana_min_dias or dias > ventana_max_dias:
            continue
        precio1 = close[idx1]
        maximo_intermedio = close[idx1: idx_minimo_aparente + 1].max()
        prob_forma, _, _ = motor._score_pareja_forma(precio1, precio2, maximo_intermedio)
        if prob_forma > mejor_score:
            mejor_score, idx_fondo1 = prob_forma, idx1

    if idx_fondo1 is None:
        return None
    # redondeado igual que `CandidatoDobleSuelo.probabilidad_forma` en
    # motor.detectar() -- mismo motivo que en entradas/doble_techo.py.
    probabilidad_forma = round(mejor_score, 3)

    sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    tipo, score_regimen = regimen_mercado.clasificar(df, idx_minimo_aparente, sma200)

    if tipo == TipoRegimen.ALCISTA:
        score_contexto = score_regimen
    elif tipo == TipoRegimen.BAJISTA:
        dist_ath_pct = (ath_hasta[idx_minimo_aparente] - precio2) / ath_hasta[idx_minimo_aparente] * 100
        score_ath_lejos = motor._score_ath_lejos(dist_ath_pct)
        score_contexto = (score_regimen * score_ath_lejos) ** 0.5
    else:
        score_contexto = 1e-3

    prob_forma_safe = max(probabilidad_forma, 1e-3)
    score_contexto_safe = max(score_contexto, 1e-3)
    probabilidad_total = prob_forma_safe ** peso_forma * score_contexto_safe ** peso_contexto

    curva = CURVA_SUPERVIVENCIA_SUELO[min(dia_transcurrido, 3)]
    return CandidatoEntradaSuelo(
        idx_minimo_aparente=idx_minimo_aparente, dia_transcurrido=dia_transcurrido,
        probabilidad_total_si_confirma=round(probabilidad_total, 3),
        probabilidad_en_vivo=round(probabilidad_total * curva, 3),
    )


def candidatos_entrada(df: pd.DataFrame) -> list[CandidatoEntradaSuelo]:
    """La regla de entrada: un candidato por cada minimo aparente,
    evaluado el mismo dia en que aparece (dia 0)."""
    close = df["close"].to_numpy()
    resultados = []
    for idx in minimos_aparentes(close):
        r = calcular_en_vivo(df, idx, dia_transcurrido=0)
        if r is not None:
            resultados.append(r)
    return resultados
