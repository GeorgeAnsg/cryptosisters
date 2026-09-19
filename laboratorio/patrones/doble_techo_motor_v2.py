"""
Motor de doble techo v2 (12-sept-2026) -- reconstruido como CAPAS
separadas e inspeccionables, no un unico numero opaco. Pedido explicito
del usuario: "esto no va metido en el motor... son como capas, no?".

CAPA 1 -- FORMA: la puntuacion de siempre (nivel/caida/tiempo/altura),
  de `doble_techo_flexible.py`. Se aplica siempre, es la base.

CAPA 2 -- TIPO DE REGIMEN: clasifica el contexto de mercado en tres
  estados (BAJISTA / ALCISTA / NEUTRO) usando precio vs media200 y
  pendiente de la media. Esta capa no da una probabilidad -- decide QUE
  capa 3 aplica, porque hoy se demostro que un factor que funciona en
  mercado bajista no tiene por que funcionar igual en uno alcista.

CAPA 3 -- CONTEXTO ESPECIFICO DEL REGIMEN (solo lo validado hoy con
  cruce de moneda y de tiempo):
  - BAJISTA: nivel ya repetido antes + todavia relativamente cerca del
    ATH. Este es el combo MAS FUERTE de toda la sesion (validado en
    ETH-ajuste, ETH-tiempo, ETH-2017-21 y BTC).
  - ALCISTA: solo cercania al ATH (mas debil, solo se confirmo en 2 de
    4 cortes -- se incluye pero con menos peso relativo).
  - NEUTRO: no hay ningun factor de contexto validado para este caso --
    se deja con nota de "sin pieza propia", no se inventa un numero.

CAPA 4 -- CONFIRMACION CRUZADA (separada, NO se mezcla en el numero
  final): si el otro activo (BTC<->ETH) tambien tiene un techo2 dentro
  de +/-2 dias. Validado hoy en los 3 cortes, pero es una pieza de
  naturaleza distinta (evidencia de mercado, no del propio patron) --
  se reporta al lado como flag, para que se use como filtro o refuerzo
  manual, no como parte silenciosa de la probabilidad.

Factores probados hoy pero descartados o sin confirmar (Open Interest,
compresion de volatilidad, IPC/tipos de interes, shock de precio/VIX) NO
se incluyen -- ninguno paso el cruce de moneda con solidez suficiente.

REQUISITO OPERATIVO PARA VIVO (encontrado al correr tests/puerta_recursividad.py
el 12-sept-2026, puerta 5): `dist_ath_pct` usa `np.maximum.accumulate(close)`
-- el maximo DESDE EL ORIGEN de los datos, no una ventana movil. Si el bot en
vivo mantuviera solo un trozo reciente del historico (ej. las ultimas 500
velas) en vez del historico diario completo desde el listing, el ATH
calculado en vivo podria ser mas bajo que el real, inflando el score
respecto al backtest -- confirmado: con ventana recortada los scores salen
sistematicamente mas altos (ej. 0.722 backtest vs 0.939 con 500 velas).
Esto NO es un bug del calculo (correcto si hay histórico completo) sino un
requisito de despliegue: el histórico diario de BTC/ETH desde 2017 son solo
~2700 velas (~250 KB), trivial de mantener completo en memoria, y la API de
klines de Binance permite paginar hacia atras hasta el listing sin
restriccion -- NO hay excusa tecnica para truncarlo en timeframe diario. El
bot en vivo DEBE cargar y mantener el historico diario completo desde el
listing para este motor (y para `regimen_mercado.py` en general, aunque ese
solo necesita ~220 dias de calentamiento, mucho menos exigente). Puerta 5
verificada con `margen_seguridad=225` (200 SMA + 20 pendiente) en
`tests/puerta_recursividad.py` -- OK bajo ese supuesto de histórico completo.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.patrones import doble_techo_flexible, regimen_mercado
from laboratorio.patrones.doble_techo_flexible import CandidatoDobleTecho
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
from laboratorio.patrones.regimen_mercado import TipoRegimen


# Bug real encontrado el 12-sept-2026 al revisar el grafico: se habia puesto
# 30.0 a ojo, sin comprobar contra los datos. La distancia real al ATH entre
# los candidatos bajista+nivel_repetido (ETH+BTC, n=115) va de 14% a 91%,
# mediana 66% (percentiles 10/25/50/75/90: 43/61/66/75/89) -- con "ideal=30"
# CASI TODO el año 2022 (una caida del 60-70% desde el ATH de 2021) quedaba
# aplastado a la nota minima, justo los casos con nivel repetido que mas
# deberian destacar. Recalibrado al percentil 90 real (~90), para que el
# score se reparta por todo el rango observado en vez de saturar a cero.
DIST_ATH_IDEAL_PCT = 90.0  # saturacion: a esta distancia o mas, score_ath ~ 0 (antes 30, sin calibrar)

# Descuento de confianza para el contexto ALCISTA frente al BAJISTA.
# NO es un numero elegido a dedo -- sale de comparar la magnitud real de
# retorno encontrada hoy en cada grupo (segmentacion_ath_por_regimen.py):
# bajista+nivel+ATH: ETH2017-21 -16.6%, ETH-ajuste -16.2%, BTC -11.7% -> media ~-14.9%
# alcista+ATH (solo en los 2 cortes que salieron significativos): ETH-tiempo -6.0%, BTC -6.7% -> media ~-6.3%
# ratio ~0.42 -- el alcista pesa menos porque su efecto medido es menos de
# la mitad de fuerte, ademas de haber confirmado en menos cortes (2/4 vs 4/4).
DESCUENTO_CONTEXTO_ALCISTA = 0.42


@dataclass
class CandidatoMotorV2:
    candidato: CandidatoDobleTecho
    score_forma: float
    tipo_regimen: TipoRegimen
    score_regimen: float          # que tan marcado esta ese regimen (0-1)
    score_contexto: float         # capa 3, depende del tipo_regimen
    probabilidad_total: float     # combinacion de forma + contexto (SIN la capa 4)
    detalle_contexto: dict        # piezas sueltas de la capa 3, para inspeccionar


def _score_ath(dist_ath_pct: float, ideal_pct: float = DIST_ATH_IDEAL_PCT) -> float:
    return max(1.0 - dist_ath_pct / ideal_pct, 1e-3) if dist_ath_pct == dist_ath_pct else 1e-3


def calcular(
    df: pd.DataFrame,
    peso_forma: float = 0.5,
    peso_contexto: float = 0.5,
    **kwargs_detectar,
) -> list[CandidatoMotorV2]:
    """Capas 1-3. La capa 4 (confirmacion cruzada) se calcula aparte con
    `confirmacion_cruzada()`, sobre la lista de resultados de esta funcion
    y la de otro activo -- se mantiene fuera a proposito."""
    candidatos = doble_techo_flexible.detectar(df, **kwargs_detectar)
    close_s = df["close"]
    close = close_s.to_numpy()
    sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)

    ordenados = sorted(candidatos, key=lambda c: c.idx_techo2)
    niveles_previos: list[tuple[int, float]] = []
    resultados = []

    for c in ordenados:
        tipo, score_regimen = regimen_mercado.clasificar(df, c.idx_techo2, sma200)
        dist_ath_pct = (ath_hasta[c.idx_techo2] - close[c.idx_techo2]) / ath_hasta[c.idx_techo2] * 100
        score_ath = _score_ath(dist_ath_pct)

        nivel_actual = (close[c.idx_techo1] + close[c.idx_techo2]) / 2
        patron_previo = any(
            idx2p < c.idx_techo1 - 3 and abs(nivp - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2p, nivp in niveles_previos
        )
        niveles_previos.append((c.idx_techo2, nivel_actual))
        score_nivel_repetido = 1.0 if patron_previo else 1e-3

        detalle = {"dist_ath_pct": round(dist_ath_pct, 1), "score_ath": round(score_ath, 3)}

        if tipo == TipoRegimen.BAJISTA:
            # El regimen bajista YA es, por si solo, un factor validado y
            # universal (5 monedas) -- es la base, nunca se aplasta.
            # El combo nivel_repetido+ATH es un EXTRA que refuerza cuando
            # esta presente (era el hallazgo mas fuerte de la sesion), pero
            # su AUSENCIA es neutra (no hay ese dato, no es evidencia
            # negativa) -- antes se penalizaba con un suelo de 1e-3, lo que
            # aplastaba casi todos los puntos bajistas de golpe (bug
            # encontrado el 12-sept-2026 al revisar el grafico: "todo se ve
            # igual de pequenito").
            if patron_previo:
                score_contexto = (score_regimen * score_ath) ** 0.5
            else:
                score_contexto = score_regimen
            detalle["score_nivel_repetido"] = round(score_nivel_repetido, 3)
            detalle["combo_fuerte_nivel_mas_ath"] = patron_previo
        elif tipo == TipoRegimen.ALCISTA:
            # simetrico: base = regimen alcista (continuo), reforzado por
            # ATH cuando esta cerca -- descontado en conjunto porque el
            # lado alcista solo se confirmo en 2/4 cortes, la mitad de
            # fuerte que el bajista.
            score_contexto = max((score_regimen * score_ath) ** 0.5 * DESCUENTO_CONTEXTO_ALCISTA, 1e-3)
            detalle["nota"] = "regimen+ATH, confirmado en 2/4 cortes -- descontado x0.42 frente al combo bajista"
        else:
            score_contexto = 1e-3
            detalle["nota"] = "sin pieza de contexto validada para regimen neutro"

        prob_forma_safe = max(c.probabilidad_forma, 1e-3)
        score_contexto_safe = max(score_contexto, 1e-3)
        probabilidad_total = prob_forma_safe ** peso_forma * score_contexto_safe ** peso_contexto

        resultados.append(CandidatoMotorV2(
            candidato=c, score_forma=c.probabilidad_forma, tipo_regimen=tipo,
            score_regimen=round(score_regimen, 3), score_contexto=round(score_contexto, 3),
            probabilidad_total=round(probabilidad_total, 3), detalle_contexto=detalle,
        ))
    return resultados


def confirmacion_cruzada(
    df_propio: pd.DataFrame, resultados_propio: list[CandidatoMotorV2],
    df_otro: pd.DataFrame, resultados_otro: list[CandidatoMotorV2],
    ventana_dias: int = 2,
) -> dict[int, bool]:
    """CAPA 4, separada -- para cada techo2 del activo propio, si el otro
    activo tiene un techo2 dentro de +/- ventana_dias. Devuelve
    {idx_techo2: bool}, para usar como filtro/refuerzo manual, no mezclado
    en probabilidad_total."""
    fechas_propio = df_propio["open_time"]
    fechas_otro = pd.DatetimeIndex([df_otro["open_time"].iloc[r.candidato.idx_techo2] for r in resultados_otro])
    out = {}
    for r in resultados_propio:
        fecha2 = fechas_propio.iloc[r.candidato.idx_techo2]
        diffs = np.abs((fechas_otro - fecha2).days) if len(fechas_otro) else np.array([])
        out[r.candidato.idx_techo2] = bool(len(diffs) > 0 and diffs.min() <= ventana_dias)
    return out
