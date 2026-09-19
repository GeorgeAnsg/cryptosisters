"""
Detector de martillo (hammer) -- primer patron de vela suelta del motor de
deteccion. Igual que el resto de detectores de esta carpeta: no dice
"si/no", da una probabilidad amplia basada en cuanto se parece la vela al
patron ideal, para que la Etapa 2 (acotamiento con mas velas) decida si el
candidato se confirma o se descarta.

Definicion clasica: cuerpo pequeño, mecha inferior larga (al menos
`ratio_mecha_min` veces el cuerpo), mecha superior corta o nula, y
aparece tras una caida previa (si no hay caida previa, es solo una vela
con esa forma, no un martillo con sentido direccional).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CandidatoMartillo:
    idx: int
    probabilidad: float  # 0-1, cuanto encaja con el patron ideal
    ratio_mecha: float
    caida_previa_pct: float


def detectar(
    df: pd.DataFrame,
    dias_caida_previa: int = 5,
    caida_previa_min_pct: float = 3.0,
    ratio_mecha_min: float = 1.5,
    ratio_mecha_ideal: float = 3.0,
) -> list[CandidatoMartillo]:
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)

    candidatos = []
    for i in range(dias_caida_previa, n):
        cuerpo = abs(c[i] - o[i])
        rango = h[i] - l[i]
        if rango == 0:
            continue
        cuerpo_min = min(o[i], c[i])
        cuerpo_max = max(o[i], c[i])
        mecha_inferior = cuerpo_min - l[i]
        mecha_superior = h[i] - cuerpo_max

        if cuerpo == 0:
            cuerpo = rango * 0.05  # doji: trata el cuerpo como minimo, evita division por cero

        ratio_mecha = mecha_inferior / cuerpo
        if ratio_mecha < ratio_mecha_min:
            continue
        if mecha_superior > cuerpo:  # mecha superior no puede ser mayor que el cuerpo
            continue

        caida_previa = (c[i - dias_caida_previa] - l[max(0, i - dias_caida_previa):i].min())
        maximo_previo = df["close"].iloc[max(0, i - dias_caida_previa):i].max()
        caida_previa_pct = (c[i] / maximo_previo - 1) * 100
        if caida_previa_pct > -caida_previa_min_pct:
            continue  # no hubo caida previa relevante -- no cuenta como martillo con sentido

        # probabilidad: mezcla de que tan larga es la mecha (saturando en ratio_mecha_ideal)
        # y que tan pequeña es la mecha superior relativa al cuerpo
        score_mecha = min(ratio_mecha / ratio_mecha_ideal, 1.0)
        score_limpieza = 1.0 - min(mecha_superior / cuerpo, 1.0)
        probabilidad = 0.5 * score_mecha + 0.5 * score_limpieza

        candidatos.append(CandidatoMartillo(i, round(probabilidad, 3), round(ratio_mecha, 2), round(caida_previa_pct, 2)))

    return candidatos
