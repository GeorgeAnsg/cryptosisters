"""
Combina, en UNA probabilidad final, las 3 piezas validadas en la sesion del
11-sept-2026 sobre doble techo:
  1. `probabilidad_forma` -- forma del patron (ya existe en doble_techo_flexible.py)
  2. Regimen de mercado debil (precio bajo su media 200 Y esa media cayendo)
     -- validado en 5 monedas (BTC, ETH, XRP, SOL, BNB), universal.
  3. Nivel repetido (ese mismo nivel ya formo un doble techo completo antes)
     -- validado fuerte en BTC/ETH, neutro (no perjudica) en el resto.

Ninguna de las 3 se usa como filtro binario -- las 3 son dimensiones
continuas, combinadas con media geometrica ponderada (mismo mecanismo que
canal/triangulo/triple suelo-techo), con varias configuraciones de pesos
compitiendo (`PESOS_TOTAL`) en vez de un numero fijo elegido a mano.

Esto NO sustituye a `doble_techo_flexible.detectar()` -- se apoya en el,
añadiendo el contexto de mercado que faltaba.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.patrones import doble_techo_flexible
from laboratorio.patrones.doble_techo_flexible import CandidatoDobleTecho

DIST_MEDIA200_IDEAL_PCT = 10.0   # % por debajo de la media 200 que da la nota maxima en esa dimension
PENDIENTE_MEDIA200_IDEAL_PCT = 5.0  # % de caida de la media en 20 dias que da la nota maxima
TOLERANCIA_NIVEL_PATRON_PREVIO_PCT = 5.0
DIAS_VENTANA_PATRON_PREVIO = None  # sin limite -- todo el historial pasado


@dataclass
class CandidatoDobleTechoTotal:
    candidato: CandidatoDobleTecho
    score_regimen: float
    score_nivel_repetido: float
    probabilidad_total: float


def _score_regimen(close: np.ndarray, sma200: pd.Series, idx: int) -> float:
    media = sma200.iloc[idx]
    if media != media:  # NaN -- no hay suficiente historial (menos de 200 dias)
        return 1e-3
    media_hace_20 = sma200.iloc[idx - 20] if idx >= 20 else None
    if media_hace_20 is None or media_hace_20 != media_hace_20:
        return 1e-3
    dist_pct = (media - close[idx]) / media * 100  # >0 si el precio esta por debajo
    pendiente_pct = (media_hace_20 - media) / media_hace_20 * 100  # >0 si la media cae

    score_dist = max(0.0, min(dist_pct / DIST_MEDIA200_IDEAL_PCT, 1.0))
    score_pendiente = max(0.0, min(pendiente_pct / PENDIENTE_MEDIA200_IDEAL_PCT, 1.0))
    score_dist_safe = max(score_dist, 1e-3)
    score_pendiente_safe = max(score_pendiente, 1e-3)
    return float(score_dist_safe ** 0.5 * score_pendiente_safe ** 0.5)


def calcular(
    df: pd.DataFrame,
    peso_forma: float = 0.4,
    peso_regimen: float = 0.4,
    peso_nivel_repetido: float = 0.2,
    **kwargs_detectar,
) -> list[CandidatoDobleTechoTotal]:
    candidatos = doble_techo_flexible.detectar(df, **kwargs_detectar)
    close_s = df["close"]
    close = close_s.to_numpy()
    sma200 = close_s.rolling(200).mean()

    candidatos_ordenados = sorted(candidatos, key=lambda c: c.idx_techo2)
    niveles_previos: list[tuple[int, float]] = []

    salida = []
    for c in candidatos_ordenados:
        nivel_actual = (close[c.idx_techo1] + close[c.idx_techo2]) / 2
        score_regimen = _score_regimen(close, sma200, c.idx_techo2)

        n_patrones_previos = sum(
            1 for idx2_prev, nivel_prev in niveles_previos
            if idx2_prev < c.idx_techo1 - 3
            and abs(nivel_prev - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
        )
        score_nivel_repetido = max(min(n_patrones_previos, 1) * 1.0, 1e-3)
        niveles_previos.append((c.idx_techo2, nivel_actual))

        prob_forma_safe = max(c.probabilidad_forma, 1e-3)
        score_regimen_safe = max(score_regimen, 1e-3)
        score_nivel_safe = max(score_nivel_repetido, 1e-3)
        probabilidad_total = (prob_forma_safe ** peso_forma
                               * score_regimen_safe ** peso_regimen
                               * score_nivel_safe ** peso_nivel_repetido)

        salida.append(CandidatoDobleTechoTotal(
            candidato=c, score_regimen=round(score_regimen, 3),
            score_nivel_repetido=round(score_nivel_repetido, 3),
            probabilidad_total=round(probabilidad_total, 3),
        ))
    return salida


# (peso_forma, peso_regimen, peso_nivel_repetido) -- suman 1.0. Varias
# configuraciones compitiendo, nunca un solo numero fijo.
PESOS_TOTAL = [
    (0.40, 0.40, 0.20),  # equilibrado -- default
    (0.70, 0.20, 0.10),  # forma dominante (como si el contexto no importara)
    (0.20, 0.60, 0.20),  # regimen dominante (la pieza mas universal)
    (0.20, 0.40, 0.40),  # nivel repetido dominante
]
