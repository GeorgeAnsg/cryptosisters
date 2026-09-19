"""
Cierre riguroso de "caida brusca y recuperacion": test de significancia
Monte Carlo sobre la mejor configuracion encontrada en
busqueda_grid_caida.py (reutilizando el motor generico de
monte_carlo_confirmacion.py, que no es especifico de suelo/techo), MAS
una prueba de si el volumen (`score_volumen`, ya separado de la forma)
añade algo -- exactamente la combinacion que nunca se habia probado.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import caida_recuperacion
from laboratorio.patrones.busqueda_grid_caida import _entradas_confirmadas_caida_grid
from laboratorio.patrones.monte_carlo_confirmacion import _retornos_confirmados, monte_carlo

SEMILLA = 20260911
MEJOR_CONFIG = (4, 25, 20.0, 4.0, 7, 40.0, 20, (0.3, 0.3, 0.4))


def _candidatos_con_volumen_y_retorno(df, config, desde, hasta):
    """Para cada señal CONFIRMADA en el tramo, empareja su score_volumen
    (calculado en idx_fondo, causal) con el retorno tras la confirmacion --
    misma logica que volumen_en_rotura.py pero aplicada a este patron."""
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
    fechas = df["open_time"]
    volumenes, retornos = [], []
    for c in candidatos:
        fecha_fondo = fechas.iloc[c.idx_fondo]
        if fecha_fondo < desde or fecha_fondo >= hasta:
            continue
        fin_conf = min(c.idx_fondo + 1 + dias_confirmacion, n)
        tramo_conf = df["close"].iloc[c.idx_fondo + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf > c.precio_pico]
        if len(cruces) == 0:
            continue
        idx_conf = int(cruces[0])
        fin_exito = idx_conf + vcp.DIAS_EXITO
        if fin_exito >= n:
            continue
        precio0 = df["close"].iloc[idx_conf]
        retorno = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
        volumenes.append(c.score_volumen)
        retornos.append(retorno)
    return np.array(volumenes), np.array(retornos)


def _spearman(x, y):
    return float(pd.Series(x).corr(pd.Series(y), method="spearman"))


def permutacion_volumen(volumenes, retornos, rng, n_sim=5000):
    n = len(volumenes)
    if n < 5:
        return {"error": f"muestra insuficiente (n={n})"}
    rho_obs = _spearman(volumenes, retornos)
    idx = np.arange(n)
    rhos_sim = np.empty(n_sim)
    for i in range(n_sim):
        rhos_sim[i] = _spearman(volumenes, retornos[rng.permutation(idx)])
    p = float((rhos_sim >= rho_obs).mean()) if rho_obs >= 0 else float((rhos_sim <= rho_obs).mean())
    return {"n": n, "rho_observado": round(rho_obs, 3), "p_valor": round(p, 4)}


if __name__ == "__main__":
    import json

    rng = np.random.default_rng(SEMILLA)

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="significancia_caida_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="significancia_caida_btc")

    print("=== PARTE 1: Monte Carlo -- es real el 30-34% de acierto, o es azar? ===\n")

    filas_eth = _entradas_confirmadas_caida_grid(df_eth, MEJOR_CONFIG)
    ret_eth = _retornos_confirmados(df_eth, filas_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    res_eth = monte_carlo(df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, ret_eth, True, rng)
    print(f"ETH tiempo no visto (n={len(ret_eth)}):")
    print(json.dumps(res_eth, indent=2, default=str))

    filas_btc = _entradas_confirmadas_caida_grid(df_btc, MEJOR_CONFIG)
    ret_btc = _retornos_confirmados(df_btc, filas_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    res_btc = monte_carlo(df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, ret_btc, True, rng)
    print(f"\nBTC completo (n={len(ret_btc)}):")
    print(json.dumps(res_btc, indent=2, default=str))

    print("\n\n=== PARTE 2: el volumen (score_volumen, ya separado) añade algo aqui? ===\n")

    vol_eth, ret_vol_eth = _candidatos_con_volumen_y_retorno(df_eth, MEJOR_CONFIG, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    res_vol_eth = permutacion_volumen(vol_eth, ret_vol_eth, rng)
    print("ETH tiempo no visto:", json.dumps(res_vol_eth, default=str))

    vol_btc, ret_vol_btc = _candidatos_con_volumen_y_retorno(df_btc, MEJOR_CONFIG, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    res_vol_btc = permutacion_volumen(vol_btc, ret_vol_btc, rng)
    print("BTC completo:", json.dumps(res_vol_btc, default=str))
