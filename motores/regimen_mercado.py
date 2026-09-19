"""
Clasificacion de REGIMEN DE MERCADO -- infraestructura compartida por
cualquier motor de patrones. Graduado desde
laboratorio/patrones/regimen_mercado.py el 12-sept-2026; historial completo
de validacion en ese fichero (BAJISTA universal en 5 monedas; ALCISTA
definido por simetria, mas debil, solo confirmado como contexto de doble
techo en 2/4 cortes -- no asumir que vale igual para otros patrones sin
probarlo).

REQUISITO OPERATIVO PARA VIVO: este modulo necesita ~220 dias de
calentamiento (SMA200 + 20 dias de pendiente). Los motores que dependen de
el (doble_techo.py, doble_suelo.py) ademas necesitan el ATH desde el ORIGEN
del historico, no una ventana movil -- con una ventana recortada el score
sale sistematicamente mas alto que en backtest (verificado el 12-sept-2026:
0.722 con historico completo vs 0.939 con solo las ultimas 500 velas, mismo
dia). El bot en vivo DEBE cargar y mantener el historico diario COMPLETO
desde el listing de cada moneda -- trivial en la practica (~2700 velas /
~250KB para BTC/ETH), la API de klines de Binance pagina hacia atras sin
restriccion.
"""
from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd

# NO DERIVADOS AUN de un barrido de percentiles reales -- heredados sin
# cambio del laboratorio para no alterar los resultados ya validados con
# ellos (a diferencia de DIST_ATH_IDEAL_PCT/DESCUENTO_CONTEXTO_ALCISTA en
# doble_techo.py, que si tienen esa derivacion documentada). Pendientes de
# su propia calibracion -- decision del 12-sept-2026: se calibran los 4
# numeros pendientes (estos dos + TOLERANCIA_NIVEL_PATRON_PREVIO_PCT y
# peso_forma/peso_contexto en doble_techo.py/doble_suelo.py) en UNA sola
# pasada de calibracion + re-validacion, cuando ya exista el pipeline
# completo (entradas + salidas + tamano + cartera), justo antes de operar
# con dinero real -- no antes, para no gastar presupuesto de la puerta 4
# recalibrando cada vez que se anade una capa nueva.
#
# Comprobacion rapida (sin calibrar, solo para ver de que dependen) hecha
# el 12-sept-2026 con historico completo de BTC+ETH:
#   distancia a SMA200 en dias YA bajistas: p10=8.7 p25=15.2 p50=25.9
#     p75=37.0 p90=50.1 (n=1497) -- DIST_MEDIA200_IDEAL_PCT=10.0 cae casi
#     en el p10 real, NO cerca del p90 donde deberia saturar (asi se
#     calibro DIST_ATH_IDEAL_PCT). Efecto: el 90% de los dias bajistas ya
#     sacan nota maxima en score_dist -- mismo tipo de fallo que el bug ya
#     corregido de DIST_ATH_IDEAL_PCT=30 (saturaba casi todo a la vez).
#     De los 4 pendientes, este es el que mas probablemente sea un error
#     real, no solo una imprecision -- candidato a adelantarse solo, sin
#     esperar a los otros 3, si se quiere.
#   pendiente SMA200 20d en dias YA bajistas: p10=1.0 p25=2.9 p50=5.7
#     p75=8.0 p90=10.6 (n=1497) -- PENDIENTE_MEDIA200_IDEAL_PCT=5.0 cae
#     casi en la mediana real, plantado en un sitio razonable. Este no
#     parece roto.
#   (lado alcista, n=2366, mismo patron: dist p10=8.7/p90=95.7,
#   pendiente p10=1.2/p90=16.5 -- incluido en la sesion del 12-sept-2026
#   pero no repetido aqui por brevedad, ver el chat de esa fecha)
DIST_MEDIA200_IDEAL_PCT = 10.0
PENDIENTE_MEDIA200_IDEAL_PCT = 5.0


class TipoRegimen(str, Enum):
    BAJISTA = "bajista"   # precio bajo su media 200 Y esa media cayendo -- validado, universal
    ALCISTA = "alcista"   # precio sobre su media 200 Y esa media subiendo -- simetrico, menos probado
    NEUTRO = "neutro"     # ni una cosa ni la otra (o sin historial suficiente)


def clasificar(df: pd.DataFrame, idx: int, sma200: pd.Series | None = None) -> tuple[TipoRegimen, float]:
    """Devuelve (tipo_regimen, score_0_a_1) para el dia `idx` de `df`.

    El score mide "cuanto marcado" esta ese regimen (no es comparable entre
    bajista y alcista sin mas -- cada lado tiene su propia validacion)."""
    close = df["close"].to_numpy() if not isinstance(df, np.ndarray) else df
    if sma200 is None:
        sma200 = df["close"].rolling(200).mean()

    media = sma200.iloc[idx]
    if media != media or idx < 20:  # NaN -- no hay suficiente historial. El "idx<20"
        # es redundante en la practica hoy (con sma200=rolling(200).mean(),
        # `media` ya sale NaN para todo idx<199, mucho antes de idx<20) --
        # pero es la proteccion real contra un indice negativo en
        # sma200.iloc[idx-20] si algun dia un llamador pasa un sma200
        # calculado de otra forma (ej. con min_periods distinto). Se deja
        # a proposito, no es codigo muerto de verdad.
        return TipoRegimen.NEUTRO, 1e-3
    media_hace_20 = sma200.iloc[idx - 20]
    if media_hace_20 != media_hace_20:
        return TipoRegimen.NEUTRO, 1e-3

    dist_pct = (media - close[idx]) / media * 100        # >0 si el precio esta por debajo
    pendiente_pct = (media_hace_20 - media) / media_hace_20 * 100  # >0 si la media cae

    debajo = dist_pct > 0
    cayendo = pendiente_pct > 0
    encima = dist_pct < 0
    subiendo = pendiente_pct < 0

    if debajo and cayendo:
        score_dist = max(0.0, min(dist_pct / DIST_MEDIA200_IDEAL_PCT, 1.0))
        score_pendiente = max(0.0, min(pendiente_pct / PENDIENTE_MEDIA200_IDEAL_PCT, 1.0))
        score = float(max(score_dist, 1e-3) ** 0.5 * max(score_pendiente, 1e-3) ** 0.5)
        return TipoRegimen.BAJISTA, score
    if encima and subiendo:
        score_dist = max(0.0, min(-dist_pct / DIST_MEDIA200_IDEAL_PCT, 1.0))
        score_pendiente = max(0.0, min(-pendiente_pct / PENDIENTE_MEDIA200_IDEAL_PCT, 1.0))
        score = float(max(score_dist, 1e-3) ** 0.5 * max(score_pendiente, 1e-3) ** 0.5)
        return TipoRegimen.ALCISTA, score
    return TipoRegimen.NEUTRO, 1e-3
