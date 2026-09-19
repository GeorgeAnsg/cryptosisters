"""
Idea del usuario (11-sept-2026): un doble techo que ademas es RETESTEADO
una tercera vez (el precio vuelve a subir hacia el nivel y vuelve a
fallar, antes de romper el valle intermedio hacia abajo) deberia dar mas
fuerza a la señal que un doble techo simple -- la misma logica por la
que un triple techo se considera un patron de reversion mas fuerte que
un doble techo. Aqui NO se trata como un patron nuevo: se usa
`triple_techo_flexible.py` (ya construido) solo para ETIQUETAR cuales de
los dobles techo confirmados tuvieron ademas ese tercer rechazo antes de
romper, y se compara el resultado entre los dos grupos.

Metodologia: mismos pesos ya congelados de doble techo (solo ETH-ajuste),
misma confirmacion (rotura del valle intermedio en DIAS_CONFIRMACION
dias). Un doble techo (idx_techo1, idx_techo2) se marca "reforzado" si
existe algun candidato de triple techo cuyo pico1/pico2 coincidan con
idx_techo1/idx_techo2 (es decir, hubo un pico3 -- un tercer rechazo --
antes de que el valle terminara rompiendose).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible, triple_techo_flexible


def _pares_reforzados(df: pd.DataFrame) -> set[tuple[int, int]]:
    """(idx_pico1, idx_pico2) de todo candidato de triple techo -- si un
    doble techo comparte ese mismo par, tuvo un tercer rechazo (pico3)
    antes de resolverse."""
    candidatos_triple = triple_techo_flexible.detectar(df)
    return {(c.idx_pico1, c.idx_pico2) for c in candidatos_triple}


def _candidatos_confirmados_con_retest(df: pd.DataFrame, pesos: tuple, pares_reforzados: set) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    n = len(df)
    filas = []
    for c in candidatos:
        minimo_intermedio = df["close"].iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + vcp.DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_techo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf < minimo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None
        reforzado = (c.idx_techo1, c.idx_techo2) in pares_reforzados
        filas.append({
            "idx_techo2": c.idx_techo2, "idx_confirmacion": idx_confirmacion, "reforzado": reforzado,
        })
    return filas


def _resumen_segmento(df: pd.DataFrame, filas: list[dict], desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    filas_planas = [(f["idx_techo2"], f["idx_confirmacion"]) for f in filas]
    return vcp._resumen(df, filas_planas, desde, hasta, exito_es_subida=False)["con_confirmacion"]


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_retest_techo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_retest_techo_btc")

    resultados_techo = []
    for pesos in vcp.PESOS_TECHO:
        filas = vcp._entradas_confirmadas_techo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
        resultados_techo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_techo)["pesos"]
    print(f"Pesos congelados (elegidos SOLO en ETH-ajuste, sin cambios por este analisis): {mejor_pesos}\n")

    pares_reforzados_eth = _pares_reforzados(df_eth)
    pares_reforzados_btc = _pares_reforzados(df_btc)
    print(f"Pares (techo1,techo2) reforzados por un 3er techo -- ETH: {len(pares_reforzados_eth)}, BTC: {len(pares_reforzados_btc)}\n")

    cortes = [
        ("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, pares_reforzados_eth),
        ("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, pares_reforzados_eth),
        ("BTC completo (moneda nunca vista)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, pares_reforzados_btc),
    ]

    for nombre, df, desde, hasta, pares in cortes:
        print(f"=== {nombre} ===")
        filas = _candidatos_confirmados_con_retest(df, mejor_pesos, pares)
        reforzados = [f for f in filas if f["reforzado"]]
        simples = [f for f in filas if not f["reforzado"]]
        r_ref = _resumen_segmento(df, reforzados, desde, hasta)
        r_sim = _resumen_segmento(df, simples, desde, hasta)
        print(f"  reforzado (3er techo antes de romper): {json.dumps(r_ref, default=str)}")
        print(f"  doble simple (sin 3er techo): {json.dumps(r_sim, default=str)}")
        print()
