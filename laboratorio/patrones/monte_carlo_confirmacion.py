"""
Test de significancia Monte Carlo sobre la "confirmacion de ruptura" de
doble suelo / doble techo, aplicado a los resultados ya congelados de
`validacion_cruzada_pesos.py` (pesos ajustados SOLO en ETH 2021-2023, ver
skill `deteccion-flexible-patrones`, paso 7).

Pregunta que responde: si las fechas de entrada "con confirmacion" no
llevaran ninguna informacion real -- si fuesen tan buenas como cualquier
fecha al azar del mismo tramo -- ¿con que frecuencia un grupo aleatorio de
ese tamaño igualaria o superaria el resultado real observado? Esa
frecuencia es el p-valor empirico. Un p-valor alto (por ejemplo 0.5)
significa "la mitad de las veces el azar hace lo mismo o mejor" -- es
decir, no hay edge demostrable.

Metodo (ver leccion 4 de la skill): el universo de fechas candidatas se
construye en tramos NO SOLAPADOS de `DIAS_EXITO` dias, para no inflar el
tamaño de muestra aparente con ventanas que comparten casi todos sus datos.
Se repite 5000 veces (`N_SIMULACIONES`) con semilla fija para
reproducibilidad.

"Exito" NUNCA se mide con un solo umbral fijo (ver correccion del
9-sept-2026, feedback del usuario: "no me gusta que haya sido un cinco
por ciento estricto... tiene que ser siempre dinamico"): se prueba todo
`vcp.UMBRALES_EXITO_PCT` y se reporta el RANGO de p-valores, igual que el
resto de la metodologia trata cualquier corte (ver cordura dinamica en
`validacion_confirmacion.py`).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab

N_SIMULACIONES = 5000
SEMILLA = 20260910


def _puntos_no_solapados(df: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp) -> list[int]:
    fechas = df["open_time"]
    n = len(df)
    idxs, i = [], 0
    while i + vcp.DIAS_EXITO < n:
        f = fechas.iloc[i]
        if desde <= f < hasta:
            idxs.append(i)
        i += vcp.DIAS_EXITO
    return idxs


def _retorno(df: pd.DataFrame, i: int) -> float:
    fin = i + vcp.DIAS_EXITO
    p0 = df["close"].iloc[i]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _retornos_confirmados(df: pd.DataFrame, filas: list, desde: pd.Timestamp, hasta: pd.Timestamp) -> list[float]:
    n = len(df)
    fechas = df["open_time"]
    retornos = []
    for idx2, idx_conf in filas:
        if idx_conf is None:
            continue
        fecha2 = fechas.iloc[idx2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        fin_exito = idx_conf + vcp.DIAS_EXITO
        if fin_exito >= n:
            continue
        precio0 = df["close"].iloc[idx_conf]
        retornos.append((df["close"].iloc[fin_exito] - precio0) / precio0 * 100)
    return retornos


def _aciertos_por_umbral(retornos: np.ndarray, exito_es_subida: bool) -> list[float]:
    return [
        float(((retornos >= u) if exito_es_subida else (retornos <= -u)).mean() * 100)
        for u in vcp.UMBRALES_EXITO_PCT
    ]


def monte_carlo(
    df: pd.DataFrame,
    desde: pd.Timestamp,
    hasta: pd.Timestamp,
    retornos_obs: list[float],
    exito_es_subida: bool,
    rng: np.random.Generator,
) -> dict:
    n_obs = len(retornos_obs)
    universo = _puntos_no_solapados(df, desde, hasta)
    if len(universo) < n_obs:
        return {"error": f"universo insuficiente ({len(universo)} puntos no solapados < {n_obs} observados)"}

    retornos_obs_arr = np.array(retornos_obs)
    aciertos_obs = _aciertos_por_umbral(retornos_obs_arr, exito_es_subida)
    retorno_obs_medio = float(retornos_obs_arr.mean())

    aciertos_sim_por_umbral = [[] for _ in vcp.UMBRALES_EXITO_PCT]
    retornos_sim = []
    for _ in range(N_SIMULACIONES):
        muestra = rng.choice(universo, size=n_obs, replace=False)
        retornos = np.array([_retorno(df, i) for i in muestra])
        for j, a in enumerate(_aciertos_por_umbral(retornos, exito_es_subida)):
            aciertos_sim_por_umbral[j].append(a)
        retornos_sim.append(retornos.mean())

    retornos_sim = np.array(retornos_sim)
    p_valores_acierto = []
    for j, umbral in enumerate(vcp.UMBRALES_EXITO_PCT):
        sim = np.array(aciertos_sim_por_umbral[j])
        p = float((sim >= aciertos_obs[j]).mean())
        p_valores_acierto.append(round(p, 4))

    p_retorno = (
        float((retornos_sim >= retorno_obs_medio).mean())
        if exito_es_subida
        else float((retornos_sim <= retorno_obs_medio).mean())
    )
    return {
        "n_obs": n_obs,
        "universo_no_solapado": len(universo),
        "umbrales_probados_pct": vcp.UMBRALES_EXITO_PCT,
        "acierto_obs_por_umbral_pct": [round(a, 1) for a in aciertos_obs],
        "p_valor_acierto_rango": [min(p_valores_acierto), max(p_valores_acierto)],
        "p_valor_acierto_por_umbral": dict(zip(vcp.UMBRALES_EXITO_PCT, p_valores_acierto)),
        "retorno_obs_medio_pct": round(retorno_obs_medio, 2),
        "retorno_azar_medio_pct": round(float(retornos_sim.mean()), 2),
        "p_valor_retorno": round(p_retorno, 4),
    }


def _congelar_pesos(df_eth: pd.DataFrame) -> tuple[tuple, tuple]:
    resultados_suelo = []
    for pesos in vcp.PESOS_SUELO:
        filas = vcp._entradas_confirmadas_suelo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, True)
        resultados_suelo.append({"pesos": pesos, "ajuste": r})
    mejor_suelo = vcp._mejor(resultados_suelo)

    resultados_techo = []
    for pesos in vcp.PESOS_TECHO:
        filas = vcp._entradas_confirmadas_techo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
        resultados_techo.append({"pesos": pesos, "ajuste": r})
    mejor_techo = vcp._mejor(resultados_techo)

    return mejor_suelo["pesos"], mejor_techo["pesos"]


def _congelar_pesos_canal(df_eth: pd.DataFrame) -> tuple[tuple, tuple]:
    """Devuelve ((pesos, fraccion), (pesos, fraccion)) para ascendente y
    descendente -- grid combinado, ver validacion_cruzada_pesos.py."""
    resultados_asc = []
    for pesos in vcp.PESOS_CANAL:
        for fraccion in vcp.FRACCIONES_CONFIRMACION_CANAL:
            filas = vcp._entradas_confirmadas_canal(df_eth, pesos, "subida", fraccion_confirmacion=fraccion)
            r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, True)
            resultados_asc.append({"pesos": pesos, "fraccion": fraccion, "ajuste": r})
    mejor_asc = vcp._mejor(resultados_asc)

    resultados_desc = []
    for pesos in vcp.PESOS_CANAL:
        for fraccion in vcp.FRACCIONES_CONFIRMACION_CANAL:
            filas = vcp._entradas_confirmadas_canal(df_eth, pesos, "bajada", fraccion_confirmacion=fraccion)
            r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
            resultados_desc.append({"pesos": pesos, "fraccion": fraccion, "ajuste": r})
    mejor_desc = vcp._mejor(resultados_desc)

    return (mejor_asc["pesos"], mejor_asc["fraccion"]), (mejor_desc["pesos"], mejor_desc["fraccion"])


if __name__ == "__main__":
    import json

    rng = np.random.default_rng(SEMILLA)

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="monte_carlo_confirmacion_eth")
    pesos_suelo, pesos_techo = _congelar_pesos(df_eth)

    casos = []

    # Confirmacion 1: ETH, tramo de tiempo nunca visto durante el ajuste
    filas_suelo = vcp._entradas_confirmadas_suelo(df_eth, pesos_suelo)
    ret_suelo = _retornos_confirmados(df_eth, filas_suelo, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    if ret_suelo:
        casos.append(("ETH tiempo (suelo)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, ret_suelo, True))

    filas_techo = vcp._entradas_confirmadas_techo(df_eth, pesos_techo)
    ret_techo = _retornos_confirmados(df_eth, filas_techo, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    if ret_techo:
        casos.append(("ETH tiempo (techo)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, ret_techo, False))

    # Confirmacion 2: BTC completo, pesos congelados, moneda nunca vista
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="monte_carlo_confirmacion_btc")
    filas_suelo_btc = vcp._entradas_confirmadas_suelo(df_btc, pesos_suelo)
    ret_suelo_btc = _retornos_confirmados(df_btc, filas_suelo_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    if ret_suelo_btc:
        casos.append(("BTC moneda (suelo)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, ret_suelo_btc, True))

    filas_techo_btc = vcp._entradas_confirmadas_techo(df_btc, pesos_techo)
    ret_techo_btc = _retornos_confirmados(df_btc, filas_techo_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    if ret_techo_btc:
        casos.append(("BTC moneda (techo)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, ret_techo_btc, False))

    # --- CANAL (Fase B, 11-sept-2026) ---
    (pesos_canal_asc, fraccion_canal_asc), (pesos_canal_desc, fraccion_canal_desc) = _congelar_pesos_canal(df_eth)

    filas_canal_asc = vcp._entradas_confirmadas_canal(df_eth, pesos_canal_asc, "subida", fraccion_canal_asc)
    ret_canal_asc = _retornos_confirmados(df_eth, filas_canal_asc, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    if ret_canal_asc:
        casos.append(("ETH tiempo (canal ascendente)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, ret_canal_asc, True))

    filas_canal_desc = vcp._entradas_confirmadas_canal(df_eth, pesos_canal_desc, "bajada", fraccion_canal_desc)
    ret_canal_desc = _retornos_confirmados(df_eth, filas_canal_desc, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    if ret_canal_desc:
        casos.append(("ETH tiempo (canal descendente)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, ret_canal_desc, False))

    filas_canal_asc_btc = vcp._entradas_confirmadas_canal(df_btc, pesos_canal_asc, "subida", fraccion_canal_asc)
    ret_canal_asc_btc = _retornos_confirmados(df_btc, filas_canal_asc_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    if ret_canal_asc_btc:
        casos.append(("BTC moneda (canal ascendente)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, ret_canal_asc_btc, True))

    filas_canal_desc_btc = vcp._entradas_confirmadas_canal(df_btc, pesos_canal_desc, "bajada", fraccion_canal_desc)
    ret_canal_desc_btc = _retornos_confirmados(df_btc, filas_canal_desc_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
    if ret_canal_desc_btc:
        casos.append(("BTC moneda (canal descendente)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, ret_canal_desc_btc, False))

    print(f"Pesos congelados (elegidos SOLO en ETH 2021-2023) -- suelo: {pesos_suelo}, techo: {pesos_techo}")
    print(f"Canal ascendente: pesos={pesos_canal_asc} fraccion={fraccion_canal_asc}, "
          f"canal descendente: pesos={pesos_canal_desc} fraccion={fraccion_canal_desc}")
    print(f"Umbrales de exito probados (rango, no fijo): {vcp.UMBRALES_EXITO_PCT}\n")

    salida = {}
    for nombre, df, desde, hasta, retornos_obs, exito_es_subida in casos:
        res = monte_carlo(df, desde, hasta, retornos_obs, exito_es_subida, rng)
        salida[nombre] = res
        print(f"=== {nombre} (n={len(retornos_obs)}) ===")
        print(json.dumps(res, indent=2, default=str))
        print()

    print("RESUMEN rango de p-valores (acierto) por caso:", {k: v.get("p_valor_acierto_rango") for k, v in salida.items()})
