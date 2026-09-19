"""
Clasificacion de REGIMEN DE MERCADO -- infraestructura COMPARTIDA por
cualquier motor de patrones (doble techo, doble suelo, triple techo/suelo,
canal, etc.), no propia de uno solo.

Correccion de arquitectura del usuario (12-sept-2026): el regimen (precio
vs su media 200 y la pendiente de esa media) es informacion del MERCADO en
un dia dado, no del patron que se este mirando. Si cada motor lo calculaba
por su cuenta, el dia que se mejore la clasificacion habria que acordarse
de cambiarla en todos los ficheros. Vive aqui, una sola vez.

Ademas, el regimen no es solo una pieza que puntua DENTRO de un patron ya
detectado -- conceptualmente es la capa que, en el orquestador final (Fase
D de la hoja de ruta), decide que motores tiene sentido lanzar en cada
momento: mercado bajista -> buscar doble techo, triple techo, caida-
reversion; mercado alcista -> buscar doble suelo, triple suelo, subida-
correccion. Este modulo expone esa clasificacion para que la usen tanto
los motores individuales (como pieza de contexto, capa 3) como el futuro
orquestador (como filtro de que lanzar, capa 1 a nivel global).

Validado el 11/12-sept-2026: el lado BAJISTA (precio bajo su media 200 Y
esa media cayendo) es universal, confirmado en 5 monedas (BTC, ETH, XRP,
SOL, BNB). El lado ALCISTA (precio sobre su media 200 y esa media
subiendo) se definio por simetria pero solo se ha probado como contexto
de doble techo (ahi salio mas debil, 2/4 cortes) -- no asumir que la
version alcista es igual de fiable que la bajista en otros patrones sin
probarlo primero.
"""
from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd

DIST_MEDIA200_IDEAL_PCT = 10.0      # % de distancia a la media 200 que da la nota maxima en esa dimension
PENDIENTE_MEDIA200_IDEAL_PCT = 5.0  # % de cambio de la media en 20 dias que da la nota maxima


class TipoRegimen(str, Enum):
    BAJISTA = "bajista"   # precio bajo su media 200 Y esa media cayendo -- validado, universal
    ALCISTA = "alcista"   # precio sobre su media 200 Y esa media subiendo -- simetrico, menos probado
    NEUTRO = "neutro"     # ni una cosa ni la otra (o sin historial suficiente)


def clasificar(df: pd.DataFrame, idx: int, sma200: pd.Series | None = None) -> tuple[TipoRegimen, float]:
    """Devuelve (tipo_regimen, score_0_a_1) para el dia `idx` de `df`.

    El score mide "cuanto marcado" esta ese regimen (no es comparable
    entre bajista y alcista sin mas -- cada lado tiene su propia validacion
    y fiabilidad, ver docstring del modulo)."""
    close = df["close"].to_numpy() if not isinstance(df, np.ndarray) else df
    if sma200 is None:
        sma200 = df["close"].rolling(200).mean()

    media = sma200.iloc[idx]
    if media != media or idx < 20:  # NaN -- no hay suficiente historial (menos de 200 dias)
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
