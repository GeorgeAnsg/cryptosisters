"""
Motor de doble suelo -- capas 1-4, graduado desde laboratorio el
12-sept-2026. Historial completo de validacion (por que "regimen alcista
solo" y "bajista+lejos del ATH" son las piezas correctas, y por que
"soporte repetido"/"cerca del minimo" NO lo son, pese a parecerlo al
principio) en laboratorio/patrones/doble_suelo_motor_v2.py -- este fichero
es la version LIMPIA para produccion, no repite esa narrativa.

CAPA 1 -- FORMA: nivel/rebote/tiempo/altura (geometria pura).
CAPA 2 -- REGIMEN: ver motores/regimen_mercado.py.
CAPA 3 -- CONTEXTO:
  ALCISTA: regimen solo, sin pieza extra (validado, universal, n=500/5
    monedas) -- "soporte repetido" se probo y PERJUDICA (7.09% vs 15.45%
    de retorno medio sin el), no se incluye.
  BAJISTA: regimen combinado con "lejos del ATH" (validado, n=496, 5
    monedas, Monte Carlo p=0.0000) -- un suelo que aparece ya lejos del ATH
    (caida avanzada) rebota mas que uno recien empezado.
  NEUTRO: sin pieza de contexto validada.
CAPA 4 -- CONFIRMACION CRUZADA: probada dos veces para suelo (par BTC-ETH
  simple, y con las 5 monedas cruzadas) y nunca salio significativa -- a
  diferencia del techo, aqui NO hay capa 4 todavia.

REQUISITO OPERATIVO PARA VIVO: igual que doble_techo.py -- `dist_ath_pct`
necesita el historico diario COMPLETO desde el listing (ver la nota
completa en motores/regimen_mercado.py).

CAMPOS QUE NO SE HAN TRAIDO desde el laboratorio: `volumen_ratio`/
`score_volumen` (no se usan en `probabilidad_forma`, y ademas miran hasta
6 dias DESPUES del fondo2 -- no utilizable tal cual en el mismo dia del
patron) y `n_parejas_alternativas_decentes` (pensado para el enfoque de
consenso por grid, este motor no lo usa).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from dataclasses import dataclass

import numpy as np
import pandas as pd

from motores import regimen_mercado
from motores.regimen_mercado import TipoRegimen

# Derivado de datos reales (ver laboratorio/patrones/doble_suelo_motor_v2.py):
# distancia real al ATH entre candidatos bajista (n=496, 5 monedas):
# percentiles 10/25/50/75/90 = 49/61/70/80/89 -- saturacion puesta en el
# p90 real, misma metodologia que el techo (el parecido de escala con
# DIST_ATH_IDEAL_PCT es coincidencia de la propia dinamica de mercado, no
# una constante compartida a proposito).
DIST_ATH_LEJOS_IDEAL_PCT = 89.0


@dataclass
class CandidatoDobleSuelo:
    idx_fondo1: int
    idx_fondo2: int
    probabilidad_forma: float  # SOLO geometria: nivel, rebote, tiempo, altura
    diferencia_nivel_pct: float
    rebote_intermedio_pct: float
    dias_entre_fondos: int


@dataclass
class CandidatoMotorSuelo:
    candidato: CandidatoDobleSuelo
    score_forma: float
    tipo_regimen: TipoRegimen
    score_regimen: float
    score_contexto: float
    probabilidad_total: float
    detalle_contexto: dict


def _detectar_fondos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Minimos locales causales -- espejo exacto de _detectar_techos_simple
    en doble_techo.py: un fondo en `i` solo se confirma `ventana` velas
    despues, nunca antes."""
    n = len(close)
    fondos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.min():
            fondos.append(i)
    return fondos


# Pesos/ideales de CAPA 1 por defecto -- unica fuente de verdad, misma
# razon que en doble_techo.py: `entradas/doble_suelo.py` importa
# `_score_pareja_forma()` en vez de reimplementar la formula, para que no
# puedan desincronizarse (ese fue exactamente el bug encontrado el
# 12-sept-2026 en la version del techo).
TOLERANCIA_NIVEL_PCT_DEFECTO = 15.0
REBOTE_IDEAL_PCT_DEFECTO = 8.0
ALTURA_IDEAL_PCT_DEFECTO = 20.0
PESO_NIVEL_DEFECTO = 0.15
PESO_REBOTE_DEFECTO = 0.15
PESO_TIEMPO_DEFECTO = 0.10
PESO_ALTURA_DEFECTO = 0.60


def _score_pareja_forma(
    precio1: float,
    precio2: float,
    maximo_intermedio: float,
    tolerancia_nivel_pct: float = TOLERANCIA_NIVEL_PCT_DEFECTO,
    rebote_ideal_pct: float = REBOTE_IDEAL_PCT_DEFECTO,
    altura_ideal_pct: float = ALTURA_IDEAL_PCT_DEFECTO,
    peso_nivel: float = PESO_NIVEL_DEFECTO,
    peso_rebote: float = PESO_REBOTE_DEFECTO,
    peso_tiempo: float = PESO_TIEMPO_DEFECTO,
    peso_altura: float = PESO_ALTURA_DEFECTO,
) -> tuple[float, float, float]:
    """CAPA 1 -- forma de una pareja (fondo1, fondo2) concreta. Devuelve
    (probabilidad_forma, diferencia_nivel_pct, rebote_intermedio_pct).

    Nota: `peso_tiempo` existe como parametro pero `score_tiempo` vale
    siempre 1.0 mas abajo -- igual que en doble_techo.py, esa dimension no
    discrimina nada todavia."""
    diferencia_nivel_pct = (precio2 - precio1) / precio1 * 100
    rebote_intermedio_pct = (maximo_intermedio - min(precio1, precio2)) / min(precio1, precio2) * 100

    score_nivel = max(0.0, 1 - abs(diferencia_nivel_pct) / tolerancia_nivel_pct)
    score_rebote = min(rebote_intermedio_pct / rebote_ideal_pct, 1.0)
    score_altura = min(rebote_intermedio_pct / altura_ideal_pct, 1.0)
    score_tiempo = 1.0

    probabilidad_forma = (peso_nivel * score_nivel + peso_rebote * score_rebote
                           + peso_tiempo * score_tiempo + peso_altura * score_altura)
    return probabilidad_forma, diferencia_nivel_pct, rebote_intermedio_pct


def detectar(
    df: pd.DataFrame,
    ventana_min_dias: int = 4,
    ventana_max_dias: int = 45,
    tolerancia_nivel_pct: float = TOLERANCIA_NIVEL_PCT_DEFECTO,
    rebote_ideal_pct: float = REBOTE_IDEAL_PCT_DEFECTO,
    peso_nivel: float = PESO_NIVEL_DEFECTO,
    peso_rebote: float = PESO_REBOTE_DEFECTO,
    peso_tiempo: float = PESO_TIEMPO_DEFECTO,
    peso_altura: float = PESO_ALTURA_DEFECTO,
    altura_ideal_pct: float = ALTURA_IDEAL_PCT_DEFECTO,
) -> list[CandidatoDobleSuelo]:
    """CAPA 1 -- forma. Ver `_score_pareja_forma()` para la formula real."""
    close = df["close"].to_numpy()
    fondos = _detectar_fondos_simple(close)

    candidatos: list[CandidatoDobleSuelo] = []
    for pos2, idx2 in enumerate(fondos):
        precio2 = close[idx2]
        parejas = []
        for idx1 in fondos[:pos2]:
            dias = idx2 - idx1
            if dias < ventana_min_dias or dias > ventana_max_dias:
                continue
            precio1 = close[idx1]
            maximo_intermedio = close[idx1:idx2 + 1].max()
            probabilidad_forma, diferencia_nivel_pct, rebote_intermedio_pct = _score_pareja_forma(
                precio1, precio2, maximo_intermedio, tolerancia_nivel_pct, rebote_ideal_pct,
                altura_ideal_pct, peso_nivel, peso_rebote, peso_tiempo, peso_altura,
            )
            parejas.append((idx1, probabilidad_forma, diferencia_nivel_pct, rebote_intermedio_pct, dias))

        if not parejas:
            continue
        parejas.sort(key=lambda p: p[1], reverse=True)
        mejor = parejas[0]
        candidatos.append(CandidatoDobleSuelo(
            idx_fondo1=mejor[0], idx_fondo2=idx2, probabilidad_forma=round(mejor[1], 3),
            diferencia_nivel_pct=round(mejor[2], 2), rebote_intermedio_pct=round(mejor[3], 2),
            dias_entre_fondos=mejor[4],
        ))
    return candidatos


def _score_ath_lejos(dist_ath_pct: float, ideal_pct: float = DIST_ATH_LEJOS_IDEAL_PCT) -> float:
    if dist_ath_pct != dist_ath_pct:
        return 1e-3
    return max(min(dist_ath_pct / ideal_pct, 1.0), 1e-3)


def calcular(
    df: pd.DataFrame,
    peso_forma: float = 0.5,
    peso_contexto: float = 0.5,
    **kwargs_detectar,
) -> list[CandidatoMotorSuelo]:
    """`peso_forma`/`peso_contexto` (50/50): mismo aviso que en
    doble_techo.py -- reparto neutral razonable, nunca barrido contra
    alternativas."""
    candidatos = detectar(df, **kwargs_detectar)
    close_s = df["close"]
    close = close_s.to_numpy()
    sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)

    resultados = []
    for c in candidatos:
        tipo, score_regimen = regimen_mercado.clasificar(df, c.idx_fondo2, sma200)

        if tipo == TipoRegimen.ALCISTA:
            score_contexto = score_regimen
            detalle = {"nota": "regimen alcista solo, validado n=500/5 monedas"}
        elif tipo == TipoRegimen.BAJISTA:
            dist_ath_pct = (ath_hasta[c.idx_fondo2] - close[c.idx_fondo2]) / ath_hasta[c.idx_fondo2] * 100
            score_ath_lejos = _score_ath_lejos(dist_ath_pct)
            score_contexto = (score_regimen * score_ath_lejos) ** 0.5
            detalle = {"dist_ath_pct": round(dist_ath_pct, 1), "score_ath_lejos": round(score_ath_lejos, 3)}
        else:
            score_contexto = 1e-3
            detalle = {"nota": "sin pieza de contexto validada para este regimen en doble suelo"}

        prob_forma_safe = max(c.probabilidad_forma, 1e-3)
        score_contexto_safe = max(score_contexto, 1e-3)
        probabilidad_total = prob_forma_safe ** peso_forma * score_contexto_safe ** peso_contexto

        resultados.append(CandidatoMotorSuelo(
            candidato=c, score_forma=c.probabilidad_forma, tipo_regimen=tipo,
            score_regimen=round(score_regimen, 3), score_contexto=round(score_contexto, 3),
            probabilidad_total=round(probabilidad_total, 3), detalle_contexto=detalle,
        ))
    return resultados
