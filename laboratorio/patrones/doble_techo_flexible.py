"""
Doble techo con MUCHO margen, version probabilidad -- espejo bajista exacto
de doble_suelo_flexible.py (ver ese archivo y la skill
`deteccion-flexible-patrones` para la metodologia completa). Construido
incorporando desde el principio las dos piezas que resultaron clave en
doble suelo (volumen en la confirmacion, tamaño del patron como dimension
continua propia), en vez de descubrirlas otra vez desde cero.

Diferencias con el estricto (doble_techo.py), igual que en doble suelo:
tolerancia de nivel amplia (no 3% fijo), sin exigencia dura de altura
minima (dimension continua en su lugar), y el filtro de regimen bajista
(BTC por debajo de su media 200 y cayendo) se deja FUERA por ahora --
aqui se prueba primero si el patron en si mismo (forma + volumen) tiene
señal, igual que se hizo con doble suelo antes de añadir capas de
contexto.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandas_ta as ta


@dataclass
class CandidatoDobleTecho:
    idx_techo1: int
    idx_techo2: int
    probabilidad_forma: float  # SOLO geometria: nivel, caida, tiempo, altura -- sin volumen
    diferencia_nivel_pct: float
    caida_intermedia_pct: float
    dias_entre_techos: int
    n_parejas_alternativas_decentes: int
    volumen_ratio: float
    score_volumen: float  # volumen_ratio normalizado 0-1, INDEPENDIENTE de probabilidad_forma
    # Campos NUEVOS (11-sept-2026) -- solo REGISTRADOS, no puntuan
    # probabilidad_forma todavia. Hipotesis del usuario: un doble techo
    # "real" deberia llegar al segundo techo con MENOS momentum/volumen que
    # el primero (divergencia bajista) -- promediar todos los dobles techo
    # juntos (con y sin esa divergencia) puede estar tapando la señal.
    rsi_techo1: float | None
    rsi_techo2: float | None
    divergencia_rsi: float | None  # rsi_techo2 - rsi_techo1; negativo = techo2 mas debil (bajista)
    volumen_techo1: float
    volumen_techo2: float
    ratio_volumen_techos: float | None  # volumen_techo2 / volumen_techo1; <1 = segundo empujon mas debil


def _detectar_techos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Maximos locales causales -- espejo exacto de _detectar_fondos_simple
    en doble_suelo_flexible.py."""
    n = len(close)
    techos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.max():
            techos.append(i)
    return techos


def detectar(
    df: pd.DataFrame,
    ventana_min_dias: int = 4,
    ventana_max_dias: int = 45,
    tolerancia_nivel_pct: float = 15.0,
    caida_ideal_pct: float = 8.0,
    peso_nivel: float = 0.15,
    peso_caida: float = 0.15,
    peso_tiempo: float = 0.10,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
    peso_altura: float = 0.60,
    altura_ideal_pct: float = 20.0,
    rsi_len: int = 14,
) -> list[CandidatoDobleTecho]:
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None
    rsi = ta.rsi(df["close"], length=rsi_len).to_numpy()
    techos = _detectar_techos_simple(close)

    n = len(close)
    candidatos: list[CandidatoDobleTecho] = []
    for pos2, idx2 in enumerate(techos):
        precio2 = close[idx2]

        # volumen: pico de volumen tras el segundo techo (donde ocurriria
        # la rotura HACIA ABAJO), relativo a su media de 30 velas.
        volumen_ratio = 0.0
        if volume is not None:
            fin_v = min(idx2 + dias_ventana_volumen, n)
            tramo_vol = volume[idx2:fin_v]
            tramo_media = vol_media[idx2:fin_v]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        parejas = []
        for idx1 in techos[:pos2]:
            dias = idx2 - idx1
            if dias < ventana_min_dias or dias > ventana_max_dias:
                continue
            precio1 = close[idx1]
            diferencia_nivel_pct = (precio2 - precio1) / precio1 * 100
            minimo_intermedio = close[idx1:idx2 + 1].min()
            caida_intermedia_pct = (max(precio1, precio2) - minimo_intermedio) / max(precio1, precio2) * 100

            score_nivel = max(0.0, 1 - abs(diferencia_nivel_pct) / tolerancia_nivel_pct)
            score_caida = min(caida_intermedia_pct / caida_ideal_pct, 1.0)
            score_altura = min(caida_intermedia_pct / altura_ideal_pct, 1.0)
            score_tiempo = 1.0

            probabilidad_forma = (peso_nivel * score_nivel + peso_caida * score_caida
                                   + peso_tiempo * score_tiempo + peso_altura * score_altura)
            parejas.append((idx1, probabilidad_forma, diferencia_nivel_pct, caida_intermedia_pct, dias))

        if not parejas:
            continue

        parejas.sort(key=lambda p: p[1], reverse=True)
        mejor = parejas[0]
        n_decentes = sum(1 for p in parejas if p[1] >= 0.3) - 1
        idx1_mejor = mejor[0]

        rsi_t1 = float(rsi[idx1_mejor]) if not np.isnan(rsi[idx1_mejor]) else None
        rsi_t2 = float(rsi[idx2]) if not np.isnan(rsi[idx2]) else None
        divergencia_rsi = (rsi_t2 - rsi_t1) if rsi_t1 is not None and rsi_t2 is not None else None
        vol_t1 = float(volume[idx1_mejor]) if volume is not None else 0.0
        vol_t2 = float(volume[idx2]) if volume is not None else 0.0
        ratio_vol_techos = (vol_t2 / vol_t1) if vol_t1 > 0 else None

        candidatos.append(CandidatoDobleTecho(
            idx_techo1=idx1_mejor, idx_techo2=idx2, probabilidad_forma=round(mejor[1], 3),
            diferencia_nivel_pct=round(mejor[2], 2), caida_intermedia_pct=round(mejor[3], 2),
            dias_entre_techos=mejor[4], n_parejas_alternativas_decentes=n_decentes,
            volumen_ratio=round(volumen_ratio, 3), score_volumen=round(score_volumen, 3),
            rsi_techo1=round(rsi_t1, 2) if rsi_t1 is not None else None,
            rsi_techo2=round(rsi_t2, 2) if rsi_t2 is not None else None,
            divergencia_rsi=round(divergencia_rsi, 2) if divergencia_rsi is not None else None,
            volumen_techo1=round(vol_t1, 3), volumen_techo2=round(vol_t2, 3),
            ratio_volumen_techos=round(ratio_vol_techos, 3) if ratio_vol_techos is not None else None,
        ))

    return candidatos
