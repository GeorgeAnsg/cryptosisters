"""
Triple techo -- espejo bajista exacto de `triple_suelo_flexible.py` (ver
ese archivo para la metodologia completa y la nota sobre media geometrica
ponderada frente a doble_suelo/doble_techo, que aun usan aritmetica).

Estructura: pico1 -> fondo1 -> pico2 -> fondo2 -> pico3 (dos caidas
intermedias). Mismas 5 dimensiones que triple suelo, en espejo: nivel
(mayor diferencia entre los 3 techos), caida1 y caida2 (dos caidas
intermedias, separadas), altura (sobre la caida MAS PEQUEÑA de las dos),
tiempo (plano), volumen (en la ruptura tras pico3).

Solo se construye el DETECTOR -- ninguna prueba de rentabilidad todavia.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CandidatoTripleTecho:
    idx_pico1: int
    idx_fondo1: int
    idx_pico2: int
    idx_fondo2: int
    idx_pico3: int
    probabilidad_forma: float  # 5 dimensiones -- sin volumen
    diferencia_nivel_max_pct: float  # mayor diferencia entre cualquier par de los 3 techos
    caida1_pct: float
    caida2_pct: float
    dias_total: int
    n_alternativas_decentes: int
    volumen_ratio: float
    score_volumen: float


def _detectar_techos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Maximos locales causales -- espejo exacto de _detectar_fondos_simple."""
    n = len(close)
    techos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.max():
            techos.append(i)
    return techos


def _detectar_fondos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Minimos locales causales -- espejo exacto de _detectar_picos_simple."""
    n = len(close)
    fondos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.min():
            fondos.append(i)
    return fondos


def detectar(
    df: pd.DataFrame,
    dias_min_tramo: int = 8,
    dias_max_tramo: int = 90,
    tolerancia_nivel_pct: float = 15.0,
    caida_ideal_pct: float = 8.0,
    caida_tolerancia_exceso_pct: float = 15.0,
    altura_ideal_pct: float = 20.0,
    peso_nivel: float = 0.25,
    peso_caida1: float = 0.15,
    peso_caida2: float = 0.15,
    peso_altura: float = 0.35,
    peso_tiempo: float = 0.10,
    vol_mult_ideal: float = 1.5,
    dias_ventana_volumen: int = 6,
) -> list[CandidatoTripleTecho]:
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy() if "volume" in df.columns else None
    vol_media = df["volume"].rolling(30).mean().to_numpy() if volume is not None else None

    techos = _detectar_techos_simple(close)
    fondos = _detectar_fondos_simple(close)
    n = len(close)

    por_pico3: dict[int, list[tuple]] = {}
    for i, idx_pico1 in enumerate(techos):
        precio_pico1 = close[idx_pico1]
        for idx_pico2 in techos[i + 1:]:
            dias_12 = idx_pico2 - idx_pico1
            if dias_12 > dias_max_tramo:
                break
            if dias_12 < dias_min_tramo // 2:
                continue
            precio_pico2 = close[idx_pico2]

            fondo1_opts = [f for f in fondos if idx_pico1 < f < idx_pico2]
            if not fondo1_opts:
                continue

            for idx_pico3 in techos:
                if idx_pico3 <= idx_pico2:
                    continue
                dias_total = idx_pico3 - idx_pico1
                if dias_total > dias_max_tramo:
                    break
                if dias_total < dias_min_tramo:
                    continue
                precio_pico3 = close[idx_pico3]

                fondo2_opts = [f for f in fondos if idx_pico2 < f < idx_pico3]
                if not fondo2_opts:
                    continue

                for idx_fondo1 in fondo1_opts:
                    precio_fondo1 = close[idx_fondo1]
                    if precio_fondo1 >= min(precio_pico1, precio_pico2):
                        continue
                    for idx_fondo2 in fondo2_opts:
                        precio_fondo2 = close[idx_fondo2]
                        if precio_fondo2 >= min(precio_pico2, precio_pico3):
                            continue

                        niveles = [precio_pico1, precio_pico2, precio_pico3]
                        nivel_medio = float(np.mean(niveles))
                        diferencia_nivel_max_pct = float(
                            (max(niveles) - min(niveles)) / nivel_medio * 100
                        )
                        caida1_pct = (max(precio_pico1, precio_pico2) - precio_fondo1) \
                            / max(precio_pico1, precio_pico2) * 100
                        caida2_pct = (max(precio_pico2, precio_pico3) - precio_fondo2) \
                            / max(precio_pico2, precio_pico3) * 100

                        score_nivel = max(0.0, 1 - diferencia_nivel_max_pct / tolerancia_nivel_pct)
                        # puntuacion en PICO, espejo exacto del fix aplicado a
                        # triple_suelo_flexible.py el 11-sept-2026 (bug real:
                        # una caida intermedia enorme puntuaba igual -- tope
                        # 1.0 -- que una moderada).
                        if caida1_pct <= caida_ideal_pct:
                            score_caida1 = max(0.0, caida1_pct / caida_ideal_pct)
                        else:
                            score_caida1 = float(np.exp(-(caida1_pct - caida_ideal_pct) / caida_tolerancia_exceso_pct))
                        if caida2_pct <= caida_ideal_pct:
                            score_caida2 = max(0.0, caida2_pct / caida_ideal_pct)
                        else:
                            score_caida2 = float(np.exp(-(caida2_pct - caida_ideal_pct) / caida_tolerancia_exceso_pct))
                        caida_menor_pct = min(caida1_pct, caida2_pct)
                        score_altura = min(caida_menor_pct / altura_ideal_pct, 1.0)
                        score_tiempo = 1.0

                        score_nivel_safe = max(score_nivel, 1e-3)
                        score_caida1_safe = max(score_caida1, 1e-3)
                        score_caida2_safe = max(score_caida2, 1e-3)
                        score_altura_safe = max(score_altura, 1e-3)
                        score_tiempo_safe = max(score_tiempo, 1e-3)
                        probabilidad_forma = (score_nivel_safe ** peso_nivel
                                               * score_caida1_safe ** peso_caida1
                                               * score_caida2_safe ** peso_caida2
                                               * score_altura_safe ** peso_altura
                                               * score_tiempo_safe ** peso_tiempo)

                        opcion = (idx_pico1, idx_fondo1, idx_pico2, idx_fondo2, idx_pico3,
                                  diferencia_nivel_max_pct, caida1_pct, caida2_pct, probabilidad_forma)
                        por_pico3.setdefault(idx_pico3, []).append(opcion)

    candidatos: list[CandidatoTripleTecho] = []
    for idx_pico3, opciones in por_pico3.items():
        opciones.sort(key=lambda o: o[8], reverse=True)
        (idx_pico1, idx_fondo1, idx_pico2, idx_fondo2, _idx_pico3,
         diferencia_nivel_max_pct, caida1_pct, caida2_pct, probabilidad_forma) = opciones[0]
        n_decentes = sum(1 for o in opciones if o[8] >= 0.3) - 1

        volumen_ratio = 0.0
        if volume is not None:
            fin_v = min(idx_pico3 + dias_ventana_volumen, n)
            tramo_vol = volume[idx_pico3:fin_v]
            tramo_media = vol_media[idx_pico3:fin_v]
            validos = ~np.isnan(tramo_media) & (tramo_media > 0)
            if validos.any():
                volumen_ratio = float((tramo_vol[validos] / tramo_media[validos]).max())
        score_volumen = min(volumen_ratio / vol_mult_ideal, 1.0)

        candidatos.append(CandidatoTripleTecho(
            idx_pico1=idx_pico1, idx_fondo1=idx_fondo1, idx_pico2=idx_pico2,
            idx_fondo2=idx_fondo2, idx_pico3=idx_pico3,
            probabilidad_forma=round(probabilidad_forma, 3),
            diferencia_nivel_max_pct=round(diferencia_nivel_max_pct, 2),
            caida1_pct=round(caida1_pct, 2), caida2_pct=round(caida2_pct, 2),
            dias_total=idx_pico3 - idx_pico1, n_alternativas_decentes=n_decentes,
            volumen_ratio=round(volumen_ratio, 3), score_volumen=round(score_volumen, 3),
        ))

    return candidatos


# Espejo exacto de PESOS_FORMA en triple_suelo_flexible.py.
PESOS_FORMA = [
    (0.25, 0.15, 0.15, 0.35, 0.10),  # equilibrado -- default
    (0.55, 0.10, 0.10, 0.15, 0.10),  # nivel dominante
    (0.10, 0.35, 0.35, 0.10, 0.10),  # caidas dominantes
    (0.10, 0.10, 0.10, 0.60, 0.10),  # altura casi absoluta
]
