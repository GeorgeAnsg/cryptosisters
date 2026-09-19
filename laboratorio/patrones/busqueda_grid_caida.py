"""
Correccion de un fallo de proceso (11-sept-2026): la primera prueba de
"caida brusca y recuperacion" solo probo pesos distintos, con las mismas
ventanas de tiempo y los mismos "ideales" de saturacion (caida_ideal_pct,
velocidad_ideal_pct_dia, dias_ventana_recuperacion, recuperacion_ideal_pct,
dias_confirmacion) -- salio floja y se declaro "descartado" tras UNA sola
prueba real. El usuario lo señalo directamente: eso es abandonar ante un
resultado negativo sin agotar variantes razonables (ver
feedback_no_abandonar_ante_resultado_negativo), y ademas es una aplicacion
incompleta de la propia skill (paso 3: variar TAMBIEN tolerancias, no solo
pesos).

Este script hace la busqueda completa que debio hacerse desde el principio:
grid sobre ventanas + ideales + confirmacion + pesos, todo evaluado SOLO en
el tramo de ajuste de ETH (2021-2023), antes de congelar nada y confirmar
fuera de muestra.
"""
from __future__ import annotations

import itertools
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import pandas as pd

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import caida_recuperacion
from laboratorio.patrones.caida_recuperacion import PESOS_FORMA
import laboratorio.patrones.validacion_cruzada_pesos as vcp

GRID_CONFIGS = list(itertools.product(
    [2, 4],           # ventana_min_dias
    [15, 25],         # ventana_max_dias
    [10.0, 20.0],     # caida_ideal_pct
    [2.0, 4.0],       # velocidad_ideal_pct_dia
    [7, 14],          # dias_ventana_recuperacion
    [40.0, 70.0],     # recuperacion_ideal_pct
    [10, 20],         # dias_confirmacion (Etapa 2 -- cuanto tarda en confirmarse la vuelta al pico)
    PESOS_FORMA,
))


def _entradas_confirmadas_caida_grid(df: pd.DataFrame, config: tuple) -> list[tuple[int, int | None]]:
    (ventana_min, ventana_max, caida_ideal, velocidad_ideal, dias_rec,
     recuperacion_ideal, dias_confirmacion, pesos) = config
    peso_caida, peso_velocidad, peso_recuperacion = pesos
    candidatos = caida_recuperacion.detectar(
        df, ventana_min_dias=ventana_min, ventana_max_dias=ventana_max,
        caida_ideal_pct=caida_ideal, velocidad_ideal_pct_dia=velocidad_ideal,
        dias_ventana_recuperacion=dias_rec, recuperacion_ideal_pct=recuperacion_ideal,
        peso_caida=peso_caida, peso_velocidad=peso_velocidad, peso_recuperacion=peso_recuperacion,
    )
    n = len(df)
    filas = []
    for c in candidatos:
        fin_conf = min(c.idx_fondo + 1 + dias_confirmacion, n)
        tramo_conf = df["close"].iloc[c.idx_fondo + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf > c.precio_pico]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        filas.append((c.idx_fondo, idx_confirmacion))
    return filas


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="busqueda_grid_caida_solo_eth")

    print(f"Probando {len(GRID_CONFIGS)} configuraciones (ventanas + ideales + confirmacion + pesos), solo ETH ajuste 2021-2023...\n")

    resultados = []
    for config in GRID_CONFIGS:
        filas = _entradas_confirmadas_caida_grid(df_eth, config)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, exito_es_subida=True)
        resultados.append({"config": config, "ajuste": r})

    con_datos = [r for r in resultados if r["ajuste"]["con_confirmacion"]["n"] >= 8]
    universo = con_datos if con_datos else resultados
    top10 = sorted(
        universo,
        key=lambda r: (r["ajuste"]["con_confirmacion"]["acierto_pct_medio"] or -1,
                       r["ajuste"]["con_confirmacion"]["retorno_medio_pct"] or -999),
        reverse=True,
    )[:10]

    print("=== TOP 10 configuraciones por acierto medio en ajuste (n>=8) ===")
    for r in top10:
        print(json.dumps({"config": r["config"], "ajuste": r["ajuste"]["con_confirmacion"]}, default=str))

    mejor = top10[0]
    print("\n-> MEJOR config (a congelar y confirmar fuera de muestra):")
    print(json.dumps(mejor, default=str, indent=2))
