"""
Motor de doble suelo v2 (12-sept-2026) -- mismas 4 capas que
`doble_techo_motor_v2.py`, pero el resultado NO es un espejo literal del
techo. Historial de esta sesion, porque el camino hasta aqui importa para
no repetir los mismos errores en el futuro:

1. Espejo naive ("regimen alcista ya confirmado" = encima+subiendo
   media200, sin mas) -- NEGATIVO. Funciona en ETH-ajuste, se invierte en
   ETH-tiempo y BTC (`segmentacion_regimen_suelo.py`).
2. Espejo "regimen bajista + cerca de un extremo" (copiando el lado del
   techo que SI funciono, sin espejar tambien la direccion del extremo) --
   tambien NEGATIVO, sin señal consistente (`segmentacion_minimo_por_regimen.py`).
   El usuario detecto el error: al espejar hay que cambiar AMBAS piezas
   (regimen Y direccion del extremo), no solo una.
3. Combo "regimen ALCISTA + soporte ya repetido + lejos del minimo de la
   caida anterior" -- parecia validado a escala
   (`validacion_multi_moneda_combo_fuerte_suelo.py`, n=347, p<0.0001 en
   todos los umbrales frente al azar) pero results enganosos: nunca se
   comparo contra el caso SIN soporte repetido. Al hacerlo (n=500,
   regimen alcista completo): CON soporte repetido retorno medio 7.09%,
   SIN soporte repetido 15.45% -- el soporte repetido PERJUDICA, no ayuda.
   Y la distancia al minimo, sobre el conjunto completo (no solo el
   subgrupo con soporte), no tiene señal real (rho=0.028, p=0.53) --
   el efecto que parecia consistente antes era un artefacto de mirar solo
   el subgrupo filtrado, no un factor independiente.

CONCLUSION PARA ALCISTA (mas simple de lo esperado, no un fallo): el
factor que funciona es el REGIMEN ALCISTA POR SI SOLO (n=500, 5 monedas:
retorno medio 9.65%, acierta +5% el 48% de las veces, frente a 3.87%/37%
del azar) -- igual que "regimen bajista universal" para el techo, sin
pieza extra. Ni "soporte repetido" ni "distancia al minimo" sobreviven
como factores independientes (ver arriba).

4. Encontrado el mismo dia, por una confusion util del usuario (dijo ATH
   queriendo decir ATL): probar "lejos del ATH" (no "cerca del ATL") DENTRO
   de regimen BAJISTA para el suelo -- SI funciona, y con mas fuerza que el
   ATL real. Logica: un suelo que aparece ya lejos del ATH (caida avanzada)
   rebota mas que uno recien empezado (todavia cerca del ATH, mas probable
   que la caida continue) -- el mismo mecanismo que bajista+cerca_ATH para
   el techo, pero en la direccion que corresponde al suelo. Se probo
   tambien "cerca del ATL real" (el espejo literal que el usuario proponia
   al principio) y tambien sale en la misma direccion (5/5 monedas), pero
   con escala no comparable entre monedas (SOL/BNB salen a bolsa casi a
   cero, distancias en miles por ciento) -- inservible para pooling directo
   sin normalizar por moneda. "Lejos del ATH" es la version operativa:
   escala acotada 0-100% igual que en el techo, y ya validada a escala
   (n=496, 5 monedas, Monte Carlo p=0.0000 en todos los umbrales: retorno
   medio lejos=10.20% vs cerca=4.09%). DIST_ATH_LEJOS_IDEAL_PCT=89.0
   calibrado igual que en el techo (percentil real p90, n=496: p10=49,
   p25=61, p50=70, p75=80, p90=89, min=17, max=96 -- casi identica
   distribucion a la del techo, coincidencia de la propia dinamica de
   mercado, no una constante compartida a proposito).

CAPA 1 -- FORMA: `doble_suelo_flexible.py` (nivel/rebote/tiempo/altura).
CAPA 2 -- TIPO DE REGIMEN: `regimen_mercado.py` (compartido).
CAPA 3 -- CONTEXTO:
  ALCISTA -> score_regimen solo (validado, universal, n=500).
  BAJISTA -> score_regimen combinado con "lejos del ATH" (validado,
    n=496, ver punto 4 arriba).
  NEUTRO -> igual que en el techo, sin pieza propia.
CAPA 4 -- CONFIRMACION CRUZADA: no probada todavia para suelo.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.patrones import doble_suelo_flexible, regimen_mercado
from laboratorio.patrones.doble_suelo_flexible import CandidatoDobleSuelo
from laboratorio.patrones.regimen_mercado import TipoRegimen

DIST_ATH_LEJOS_IDEAL_PCT = 89.0  # saturacion en p90 real (n=496, candidatos bajista) -- a esta distancia o mas, score_ath_lejos ~ 1


@dataclass
class CandidatoMotorV2Suelo:
    candidato: CandidatoDobleSuelo
    score_forma: float
    tipo_regimen: TipoRegimen
    score_regimen: float
    score_contexto: float
    probabilidad_total: float
    detalle_contexto: dict


def _score_ath_lejos(dist_ath_pct: float, ideal_pct: float = DIST_ATH_LEJOS_IDEAL_PCT) -> float:
    if dist_ath_pct != dist_ath_pct:
        return 1e-3
    return max(min(dist_ath_pct / ideal_pct, 1.0), 1e-3)


def calcular(
    df: pd.DataFrame,
    peso_forma: float = 0.5,
    peso_contexto: float = 0.5,
    **kwargs_detectar,
) -> list[CandidatoMotorV2Suelo]:
    candidatos = doble_suelo_flexible.detectar(df, **kwargs_detectar)
    close_s = df["close"]
    close = close_s.to_numpy()
    sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)

    resultados = []
    for c in candidatos:
        tipo, score_regimen = regimen_mercado.clasificar(df, c.idx_fondo2, sma200)

        if tipo == TipoRegimen.ALCISTA:
            # Validado, universal (5 monedas, n=500): el regimen alcista
            # por si solo ya bate el azar con claridad. Ni "soporte
            # repetido" ni "distancia al minimo" sobrevivieron como
            # factores independientes -- ver docstring del modulo.
            score_contexto = score_regimen
            detalle = {"nota": "regimen alcista solo, validado n=500/5 monedas"}
        elif tipo == TipoRegimen.BAJISTA:
            # Validado (n=496, 5 monedas, Monte Carlo p=0.0000): un suelo
            # ya lejos del ATH (caida avanzada) rebota mas que uno cerca
            # del ATH (caida recien empezada) -- ver docstring del modulo.
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

        resultados.append(CandidatoMotorV2Suelo(
            candidato=c, score_forma=c.probabilidad_forma, tipo_regimen=tipo,
            score_regimen=round(score_regimen, 3), score_contexto=round(score_contexto, 3),
            probabilidad_total=round(probabilidad_total, 3), detalle_contexto=detalle,
        ))
    return resultados
