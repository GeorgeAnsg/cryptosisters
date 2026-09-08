"""
Multiplicador de riesgo global — reduce TODAS las posiciones a la vez
(no una por una) cuando el mercado se pone raro. Es distinto de un stop
por operación: esto actúa sobre la cartera entera.

Por ahora, con datos de precio, se implementa un único componente: la
volatilidad realizada respecto a su propio historial. Cuando la
volatilidad reciente está en un percentil extremo de lo que es normal
para BTC, se reduce el multiplicador. Es en momentos así (crashes, shocks
de noticias) cuando la diversificación entre motores falla más -- todo se
mueve junto, correlación 1.

Pendiente para cuando haya más de un motor con solapamiento real: el
componente de "sacudida de correlación" descrito en el plan maestro §6.1
(hoy no hace falta, Doble suelo y Doble techo casi no se solapan, medido
en docs/reverificacion.md).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def multiplicador_por_volatilidad(
    df: pd.DataFrame,
    ventana_volatilidad: int = 20,
    ventana_percentil: int = 500,
    percentil_corte: float = 0.90,
    multiplicador_minimo: float = 0.3,
) -> pd.Series:
    """Devuelve una serie con el multiplicador (0-1) por vela.

    - ventana_volatilidad: sobre cuántas velas se mide la volatilidad
      reciente (desviación de los retornos logarítmicos).
    - ventana_percentil: histórico contra el que se compara esa
      volatilidad para saber si es "extrema" (percentil, no un umbral fijo
      -- así se adapta si el mercado en general se vuelve más o menos
      volátil con los años, en vez de usar un número mágico).
    - percentil_corte: a partir de qué percentil se empieza a reducir.
    - multiplicador_minimo: el multiplicador nunca baja de esto, ni en el
      peor de los casos -- reducir del todo equivaldría a apagar el bot,
      que es una decisión distinta (kill switch), no de esta pieza.
    """
    logret = np.log(df["close"] / df["close"].shift(1))
    vol = logret.rolling(ventana_volatilidad).std()

    percentil = vol.rolling(ventana_percentil).rank(pct=True)

    exceso = (percentil - percentil_corte).clip(lower=0) / (1 - percentil_corte)
    multiplicador = 1.0 - exceso * (1.0 - multiplicador_minimo)
    return multiplicador.clip(lower=multiplicador_minimo, upper=1.0)
