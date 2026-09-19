"""
Version "consenso" del doble techo flexible -- espejo exacto de
doble_suelo_consenso.py (ver ese archivo y la skill
`deteccion-flexible-patrones` para la explicacion completa del porque).
Arranca directamente con los pesos que resultaron ganadores en doble
suelo (volumen + altura dominantes), en vez de repetir la exploracion de
"pesos compartidos = falso consenso" desde cero.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.patrones.doble_techo_flexible import detectar


@dataclass
class CandidatoConsensoTecho:
    idx_techo2: int
    idx_techo1_mas_comun: int
    consenso_pct: float
    n_configs_totales: int
    n_configs_de_acuerdo: int


# 11-sept-2026: el volumen se SEPARA de esta puntuacion, espejo exacto del
# cambio en doble_suelo_consenso.py -- probabilidad_forma es ahora SOLO
# geometria (nivel, caida, tiempo, altura). Mismos pesos que en suelo
# (altura dominante), como punto de partida para el espejo bajista.
# (peso_nivel, peso_caida, peso_tiempo, peso_altura) -- suman 1.0
PESOS_FORMA = [
    (0.20, 0.20, 0.10, 0.50),
    (0.15, 0.15, 0.10, 0.60),
    (0.10, 0.10, 0.05, 0.75),
    (0.05, 0.05, 0.05, 0.85),
    (0.35, 0.25, 0.10, 0.30),
]

GRID_CONFIGS = list(itertools.product(
    [10.0, 18.0, 25.0],              # tolerancia_nivel_pct
    [4.0, 8.0],                      # caida_ideal_pct
    [4, 7],                          # ventana_min_dias
    [25, 45],                        # ventana_max_dias
    [18.0, 30.0],                    # altura_ideal_pct
    [1.3, 1.8],                      # vol_mult_ideal (solo afecta score_volumen)
    [4, 8],                          # dias_ventana_volumen
    PESOS_FORMA,
))


def analizar_consenso(df: pd.DataFrame, umbral_decente: float = 0.5) -> list[CandidatoConsensoTecho]:
    n_configs = len(GRID_CONFIGS)
    resultados_por_config = []
    for tol_nivel, caida_ideal, ventana_min, ventana_max, altura_ideal, vol_mult, dias_vol, pesos in GRID_CONFIGS:
        peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
        candidatos = detectar(
            df, ventana_min_dias=ventana_min, ventana_max_dias=ventana_max, tolerancia_nivel_pct=tol_nivel,
            caida_ideal_pct=caida_ideal,
            altura_ideal_pct=altura_ideal, vol_mult_ideal=vol_mult, dias_ventana_volumen=dias_vol,
            peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo,
            peso_altura=peso_altura,
        )
        mapa = {c.idx_techo2: (c.probabilidad_forma, c.idx_techo1) for c in candidatos}
        resultados_por_config.append(mapa)

    todos_idx2 = set()
    for mapa in resultados_por_config:
        todos_idx2.update(mapa.keys())

    salida = []
    for idx2 in sorted(todos_idx2):
        de_acuerdo = 0
        techos1_contados: dict[int, int] = {}
        for mapa in resultados_por_config:
            if idx2 in mapa:
                prob, idx1 = mapa[idx2]
                if prob >= umbral_decente:
                    de_acuerdo += 1
                    techos1_contados[idx1] = techos1_contados.get(idx1, 0) + 1
        if de_acuerdo == 0:
            continue
        idx1_comun = max(techos1_contados, key=techos1_contados.get)
        salida.append(CandidatoConsensoTecho(
            idx_techo2=idx2, idx_techo1_mas_comun=idx1_comun,
            consenso_pct=round(de_acuerdo / n_configs * 100, 1),
            n_configs_totales=n_configs, n_configs_de_acuerdo=de_acuerdo,
        ))
    return salida


def probabilidad_media_por_techo2(df: pd.DataFrame) -> dict[int, float]:
    """Promedio de probabilidad de todas las configs que encontraron algun
    candidato para ese techo2, penalizado por ambiguedad -- la agregacion
    que de verdad se usa (ver leccion 'contar umbral fijo = corte duro por
    la puerta de atras')."""
    suma, cuenta = {}, {}
    for tol_nivel, caida_ideal, ventana_min, ventana_max, altura_ideal, vol_mult, dias_vol, pesos in GRID_CONFIGS:
        peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
        candidatos = detectar(
            df, ventana_min_dias=ventana_min, ventana_max_dias=ventana_max, tolerancia_nivel_pct=tol_nivel,
            caida_ideal_pct=caida_ideal,
            altura_ideal_pct=altura_ideal, vol_mult_ideal=vol_mult, dias_ventana_volumen=dias_vol,
            peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo,
            peso_altura=peso_altura,
        )
        for c in candidatos:
            n_alt = max(0, c.n_parejas_alternativas_decentes)
            score = c.probabilidad_forma / (1 + n_alt)
            suma[c.idx_techo2] = suma.get(c.idx_techo2, 0.0) + score
            cuenta[c.idx_techo2] = cuenta.get(c.idx_techo2, 0) + 1
    return {idx2: suma[idx2] / cuenta[idx2] for idx2 in suma}
