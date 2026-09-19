"""
Version "consenso" del doble suelo flexible -- respuesta directa a la idea
del usuario: en vez de UNA formula fija con unos pesos que yo elijo (que
salio mal calibrada, ver doble_suelo_flexible.py), se prueban MUCHAS
configuraciones distintas (distinta tolerancia de nivel, distinto rebote
ideal, distinta ventana de tiempo) sobre el mismo tramo de precio, y la
probabilidad final de que un punto sea un doble suelo real es LA
FRACCION DE CONFIGURACIONES QUE COINCIDEN en darle una puntuacion decente
-- no una puntuacion inventada por una sola formula.

Ejemplo: si 35 de 50 configuraciones distintas dan a este punto una
probabilidad >= 0.5 con SUS propios criterios, el consenso es 35/50 = 70%.
Si solo 10 de 50 lo consideran decente, el consenso es 20% -- mucha menos
confianza, aunque alguna configuracion aislada le diera una nota alta.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.patrones.doble_suelo_flexible import detectar


@dataclass
class CandidatoConsenso:
    idx_fondo2: int
    idx_fondo1_mas_comun: int
    consenso_pct: float
    n_configs_totales: int
    n_configs_de_acuerdo: int


# Rango de variaciones a probar -- cada combinacion es una "opinion" distinta.
# Importante: tambien varian los PESOS internos (no solo las tolerancias) --
# si todas las configs comparten los mismos pesos, tienden a estar de acuerdo
# entre si aunque cambien las tolerancias, y el consenso no discrimina nada
# (le paso exacto que fallo en la primera version).
#
# Historial de ajustes (comprobado siempre contra "?las señales YA
# VALIDADAS del estricto salen con probabilidad alta aqui?"):
# - Sin volumen: las señales estrictas apenas superaban la media general.
# - Con peso_volumen (probabilidad de que el volumen de la ruptura sea
#   alto, igual que exige el estricto): mejora clara.
# - Intentar un requisito DURO de altura minima (altura_minima_pct, si no
#   se alcanza se descarta el candidato entero): EMPEORO -- un corte duro
#   cambia que candidatos entran en la comparacion, no solo su nota.
# - Altura como dimension CONTINUA propia (peso_altura, con su propio
#   "ideal" de tamaño de patron, nunca un descarte): mejora, sin el
#   problema del corte duro.
# - 11-sept-2026: el volumen se SEPARA de esta puntuacion (ver
#   doble_suelo_flexible.py) -- probabilidad_forma es ahora SOLO geometria
#   (nivel, rebote, tiempo, altura), para poder testear forma y volumen por
#   separado en vez de mezclados en un numero compuesto. altura sigue
#   siendo la dimension dominante (era la que mas pesaba tras el volumen).
# (peso_nivel, peso_rebote, peso_tiempo, peso_altura) -- suman 1.0
PESOS_FORMA = [
    (0.20, 0.20, 0.10, 0.50),
    (0.15, 0.15, 0.10, 0.60),
    (0.10, 0.10, 0.05, 0.75),
    (0.05, 0.05, 0.05, 0.85),
    (0.35, 0.25, 0.10, 0.30),  # variante mas equilibrada, para no depender solo de altura
]

GRID_CONFIGS = list(itertools.product(
    [10.0, 18.0, 25.0],              # tolerancia_nivel_pct
    [4.0, 8.0],                      # rebote_ideal_pct (satura pronto -- mide "hubo rebote", no tamaño)
    [4, 7],                          # ventana_min_dias
    [25, 45],                        # ventana_max_dias
    [18.0, 30.0],                    # altura_ideal_pct (satura mas tarde -- mide "patron grande")
    [1.3, 1.8],                      # vol_mult_ideal (solo afecta score_volumen, ya no a probabilidad_forma)
    [4, 8],                          # dias_ventana_volumen
    PESOS_FORMA,
))


def analizar_consenso(df: pd.DataFrame, umbral_decente: float = 0.5) -> list[CandidatoConsenso]:
    n_configs = len(GRID_CONFIGS)
    # por cada configuracion, guarda {idx_fondo2: (probabilidad, idx_fondo1)}
    resultados_por_config = []
    for tol_nivel, rebote_ideal, ventana_min, ventana_max, altura_ideal, vol_mult, dias_vol, pesos in GRID_CONFIGS:
        peso_nivel, peso_rebote, peso_tiempo, peso_altura = pesos
        candidatos = detectar(
            df, ventana_min_dias=ventana_min, ventana_max_dias=ventana_max, tolerancia_nivel_pct=tol_nivel,
            rebote_ideal_pct=rebote_ideal,
            altura_ideal_pct=altura_ideal, vol_mult_ideal=vol_mult, dias_ventana_volumen=dias_vol,
            peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo,
            peso_altura=peso_altura,
        )
        mapa = {c.idx_fondo2: (c.probabilidad_forma, c.idx_fondo1) for c in candidatos}
        resultados_por_config.append(mapa)

    # todos los idx_fondo2 que aparecieron en AL MENOS una configuracion
    todos_idx2 = set()
    for mapa in resultados_por_config:
        todos_idx2.update(mapa.keys())

    salida = []
    for idx2 in sorted(todos_idx2):
        de_acuerdo = 0
        fondos1_contados: dict[int, int] = {}
        for mapa in resultados_por_config:
            if idx2 in mapa:
                prob, idx1 = mapa[idx2]
                if prob >= umbral_decente:
                    de_acuerdo += 1
                    fondos1_contados[idx1] = fondos1_contados.get(idx1, 0) + 1
        if de_acuerdo == 0:
            continue
        idx1_comun = max(fondos1_contados, key=fondos1_contados.get)
        salida.append(CandidatoConsenso(
            idx_fondo2=idx2, idx_fondo1_mas_comun=idx1_comun,
            consenso_pct=round(de_acuerdo / n_configs * 100, 1),
            n_configs_totales=n_configs, n_configs_de_acuerdo=de_acuerdo,
        ))
    return salida


def probabilidad_media_por_fondo2(df: pd.DataFrame) -> dict[int, float]:
    """Promedio de probabilidad de todas las configs que encontraron algun
    candidato para ese fondo2, penalizado por ambiguedad -- la agregacion
    que de verdad se usa (ver leccion 'contar umbral fijo = corte duro por
    la puerta de atras'). Espejo de probabilidad_media_por_techo2() en
    doble_techo_consenso.py."""
    suma, cuenta = {}, {}
    for tol_nivel, rebote_ideal, ventana_min, ventana_max, altura_ideal, vol_mult, dias_vol, pesos in GRID_CONFIGS:
        peso_nivel, peso_rebote, peso_tiempo, peso_altura = pesos
        candidatos = detectar(
            df, ventana_min_dias=ventana_min, ventana_max_dias=ventana_max, tolerancia_nivel_pct=tol_nivel,
            rebote_ideal_pct=rebote_ideal,
            altura_ideal_pct=altura_ideal, vol_mult_ideal=vol_mult, dias_ventana_volumen=dias_vol,
            peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo,
            peso_altura=peso_altura,
        )
        for c in candidatos:
            n_alt = max(0, c.n_parejas_alternativas_decentes)
            score = c.probabilidad_forma / (1 + n_alt)
            suma[c.idx_fondo2] = suma.get(c.idx_fondo2, 0.0) + score
            cuenta[c.idx_fondo2] = cuenta.get(c.idx_fondo2, 0) + 1
    return {idx2: suma[idx2] / cuenta[idx2] for idx2 in suma}


def main():
    import sys
    sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
    from datos.cargar import cargar_ohlcv

    print(f"Probando {len(GRID_CONFIGS)} configuraciones distintas por moneda...\n")
    for par in ["BTCUSDT", "ETHUSDT"]:
        df = cargar_ohlcv(par, "1d")
        resultados = analizar_consenso(df)

        buckets = {"90-100%": 0, "70-90%": 0, "50-70%": 0, "30-50%": 0, "10-30%": 0, "0-10%": 0}
        for r in resultados:
            c = r.consenso_pct
            if c >= 90: buckets["90-100%"] += 1
            elif c >= 70: buckets["70-90%"] += 1
            elif c >= 50: buckets["50-70%"] += 1
            elif c >= 30: buckets["30-50%"] += 1
            elif c >= 10: buckets["10-30%"] += 1
            else: buckets["0-10%"] += 1

        print(f"=== {par}: {len(resultados)} puntos con al menos algo de consenso ===")
        for etiqueta, n in buckets.items():
            print(f"  consenso {etiqueta}: {n} casos")

        altos = sorted([r for r in resultados if 55 <= r.consenso_pct < 75], key=lambda r: -r.consenso_pct)[:5]
        print("  ejemplos con consenso medio (55-75%):")
        for r in altos:
            f1 = df.loc[r.idx_fondo1_mas_comun, "open_time"].date()
            f2 = df.loc[r.idx_fondo2, "open_time"].date()
            print(f"    fondo1={f1} fondo2={f2} consenso={r.consenso_pct}% ({r.n_configs_de_acuerdo}/{r.n_configs_totales} configs)")
        print()


if __name__ == "__main__":
    main()
