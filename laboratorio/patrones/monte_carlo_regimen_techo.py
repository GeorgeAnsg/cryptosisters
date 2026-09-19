"""
Monte Carlo sobre el hallazgo de `segmentacion_regimen_techo.py`: el
subgrupo "debajo de la media 200" consistentemente confirma mejor que el
subgrupo "encima" en los 3 cortes (ETH-ajuste, ETH-tiempo, BTC). Aqui se
comprueba si el subgrupo "debajo media200" por si solo bate al azar --
mismo mecanismo que `monte_carlo_confirmacion.py` (tramos no solapados,
5000 simulaciones, rango de umbrales de exito).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
import laboratorio.patrones.monte_carlo_confirmacion as mc
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.segmentacion_regimen_techo import _candidatos_confirmados_con_regimen

SEMILLA = 20260911
N_SIMULACIONES = 5000


def _retornos_segmento(df: pd.DataFrame, filas: list[dict], desde: pd.Timestamp, hasta: pd.Timestamp) -> list[float]:
    filas_planas = [(f["idx_techo2"], f["idx_confirmacion"]) for f in filas]
    return mc._retornos_confirmados(df, filas_planas, desde, hasta)


if __name__ == "__main__":
    import json

    rng = np.random.default_rng(SEMILLA)
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="mc_regimen_techo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="mc_regimen_techo_btc")

    resultados_techo = []
    for pesos in vcp.PESOS_TECHO:
        filas = vcp._entradas_confirmadas_techo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
        resultados_techo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_techo)["pesos"]
    print(f"Pesos congelados: {mejor_pesos}\n")

    cortes = [
        ("ETH tiempo (nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN),
        ("BTC completo (moneda nunca vista)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN),
    ]

    salida = {}
    for nombre, df, desde, hasta in cortes:
        filas = _candidatos_confirmados_con_regimen(df, mejor_pesos)
        debajo = [f for f in filas if f["debajo_media200"]]
        retornos = _retornos_segmento(df, debajo, desde, hasta)
        if retornos:
            res = mc.monte_carlo(df, desde, hasta, retornos, exito_es_subida=False, rng=rng)
            salida[f"{nombre} (debajo media200)"] = res
            print(f"=== {nombre} -- debajo media200 (n={len(retornos)}) ===")
            print(json.dumps(res, indent=2, default=str))
            print()

        dyc = [f for f in filas if f["debajo_y_cayendo"]]
        retornos_dyc = _retornos_segmento(df, dyc, desde, hasta)
        if retornos_dyc:
            res_dyc = mc.monte_carlo(df, desde, hasta, retornos_dyc, exito_es_subida=False, rng=rng)
            salida[f"{nombre} (debajo Y cayendo)"] = res_dyc
            print(f"=== {nombre} -- debajo Y CAYENDO (n={len(retornos_dyc)}) ===")
            print(json.dumps(res_dyc, indent=2, default=str))
            print()
        else:
            print(f"=== {nombre} -- debajo Y CAYENDO: sin datos suficientes ===\n")

    print("RESUMEN p-valor acierto (rango) y p-valor retorno:",
          {k: (v.get("p_valor_acierto_rango"), v.get("p_valor_retorno")) for k, v in salida.items()})
