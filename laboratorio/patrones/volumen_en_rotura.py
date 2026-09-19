"""
Idea del usuario (10/11-sept-2026, madrugada): la "confirmacion de ruptura"
descartada esta noche (ver validacion_cruzada_pesos.py / monte_carlo_confirmacion.py)
solo comprobaba SI el precio rompia el nivel intermedio -- nunca si esa
rotura venia acompañada de volumen alto. La version ESTRICTA antigua de
doble suelo (`project_corvus4` memoria, sesion 8-sept-2026) SI exigia
volumen > 1.5x media en la rotura y mostro ventaja real en BTC. El volumen
que ya vive en `doble_suelo_flexible.py` (peso_volumen, dominante en los
pesos congelados) mide un pico en una ventana FIJA de 6 dias tras fondo2 --
no el volumen del dia exacto de la rotura, que no se conoce hasta la
Etapa 2 (este script).

Esta prueba: ¿el volumen del dia EXACTO de la confirmacion (idx_confirmacion,
causal, solo datos hasta ese dia) predice si la ruptura tiene mas o menos
retorno? En vez de anadir otro corte duro ("volumen > X"), se mide como
DIMENSION CONTINUA y se correlaciona (Spearman) con el retorno -- coherente
con el principio rector de la skill deteccion-flexible-patrones ("nada de
absolutos"). Significancia via test de permutacion (Monte Carlo): barajar
5000 veces el emparejamiento volumen<->retorno de los mismos eventos ya
observados y ver que fraccion de esos barajeos iguala o supera la
correlacion real.

Metodologia identica a validacion_cruzada_pesos.py: pesos de FORMA ya
congelados esa noche (no se retocan aqui, no consume presupuesto extra por
ese lado); ajuste de la hipotesis de volumen SOLO en ETH 2021-2023, luego
confirmacion sin tocar nada en ETH 2023-2025 (tiempo no visto) y BTC
completo (moneda no vista).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab

N_SIMULACIONES = 5000
SEMILLA = 20260911
VENTANA_MEDIA_VOLUMEN = 30


def _volumen_ratio_en(df: pd.DataFrame, idx: int) -> float | None:
    volume = df["volume"].to_numpy()
    vol_media = df["volume"].rolling(VENTANA_MEDIA_VOLUMEN).mean().to_numpy()
    if idx >= len(volume) or np.isnan(vol_media[idx]) or vol_media[idx] == 0:
        return None
    return float(volume[idx] / vol_media[idx])


def _pares_volumen_retorno(
    df: pd.DataFrame,
    filas: list[tuple[int, int | None]],
    desde: pd.Timestamp,
    hasta: pd.Timestamp,
    exito_es_subida: bool,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(df)
    fechas = df["open_time"]
    volumenes, bondades = [], []
    for idx2, idx_conf in filas:
        if idx_conf is None:
            continue
        fecha2 = fechas.iloc[idx2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        fin_exito = idx_conf + vcp.DIAS_EXITO
        if fin_exito >= n:
            continue
        vol_ratio = _volumen_ratio_en(df, idx_conf)
        if vol_ratio is None:
            continue
        precio0 = df["close"].iloc[idx_conf]
        retorno = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
        bondad = retorno if exito_es_subida else -retorno
        volumenes.append(vol_ratio)
        bondades.append(bondad)
    return np.array(volumenes), np.array(bondades)


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    return float(pd.Series(x).corr(pd.Series(y), method="spearman"))


def permutacion_correlacion(volumenes: np.ndarray, bondades: np.ndarray, rng: np.random.Generator) -> dict:
    n = len(volumenes)
    if n < 5:
        return {"error": f"muestra insuficiente para correlacion (n={n})"}
    rho_obs = _spearman(volumenes, bondades)
    rhos_sim = np.empty(N_SIMULACIONES)
    idx = np.arange(n)
    for i in range(N_SIMULACIONES):
        barajado = rng.permutation(idx)
        rhos_sim[i] = _spearman(volumenes, bondades[barajado])
    p_valor = float((rhos_sim >= rho_obs).mean()) if rho_obs >= 0 else float((rhos_sim <= rho_obs).mean())
    return {
        "n": n,
        "rho_observado": round(rho_obs, 3),
        "rho_azar_medio": round(float(rhos_sim.mean()), 3),
        "p_valor": round(p_valor, 4),
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


if __name__ == "__main__":
    import json

    rng = np.random.default_rng(SEMILLA)

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="volumen_en_rotura_eth")
    pesos_suelo, pesos_techo = _congelar_pesos(df_eth)
    print(f"Pesos de forma (ya congelados la noche anterior) -- suelo: {pesos_suelo}, techo: {pesos_techo}\n")

    # --- PASO 1: explorar la hipotesis SOLO en ETH, tramo de ajuste (nunca se mira BTC aqui) ---
    filas_suelo = vcp._entradas_confirmadas_suelo(df_eth, pesos_suelo)
    filas_techo = vcp._entradas_confirmadas_techo(df_eth, pesos_techo)

    vol_ajuste_suelo, bondad_ajuste_suelo = _pares_volumen_retorno(
        df_eth, filas_suelo, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, True
    )
    vol_ajuste_techo, bondad_ajuste_techo = _pares_volumen_retorno(
        df_eth, filas_techo, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False
    )

    print("=== PASO 1 -- exploracion en ETH, tramo de ajuste 2021-2023 (para decidir si seguir) ===")
    res_ajuste_suelo = permutacion_correlacion(vol_ajuste_suelo, bondad_ajuste_suelo, rng)
    res_ajuste_techo = permutacion_correlacion(vol_ajuste_techo, bondad_ajuste_techo, rng)
    print("Suelo:", json.dumps(res_ajuste_suelo, default=str))
    print("Techo:", json.dumps(res_ajuste_techo, default=str))

    # --- PASO 2: confirmacion 1, ETH tramo de tiempo nunca visto ---
    vol_eth_t, bondad_eth_t_suelo = _pares_volumen_retorno(
        df_eth, filas_suelo, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, True
    )
    vol_eth_t_techo, bondad_eth_t_techo = _pares_volumen_retorno(
        df_eth, filas_techo, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, False
    )
    print(f"\n=== PASO 2 -- CONFIRMACION 1: ETH, tramo {vcp.CORTE_AJUSTE_FIN.date()}->{vcp.CORTE_DESARROLLO_FIN.date()} (nunca visto) ===")
    res_eth_t_suelo = permutacion_correlacion(vol_eth_t, bondad_eth_t_suelo, rng)
    res_eth_t_techo = permutacion_correlacion(vol_eth_t_techo, bondad_eth_t_techo, rng)
    print("Suelo:", json.dumps(res_eth_t_suelo, default=str))
    print("Techo:", json.dumps(res_eth_t_techo, default=str))

    # --- PASO 3: confirmacion 2, BTC completo (moneda nunca vista) ---
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="volumen_en_rotura_btc")
    filas_suelo_btc = vcp._entradas_confirmadas_suelo(df_btc, pesos_suelo)
    filas_techo_btc = vcp._entradas_confirmadas_techo(df_btc, pesos_techo)

    vol_btc_suelo, bondad_btc_suelo = _pares_volumen_retorno(
        df_btc, filas_suelo_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, True
    )
    vol_btc_techo, bondad_btc_techo = _pares_volumen_retorno(
        df_btc, filas_techo_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, False
    )
    print("\n=== PASO 3 -- CONFIRMACION 2: BTC completo, pesos de forma congelados (moneda nunca vista) ===")
    res_btc_suelo = permutacion_correlacion(vol_btc_suelo, bondad_btc_suelo, rng)
    res_btc_techo = permutacion_correlacion(vol_btc_techo, bondad_btc_techo, rng)
    print("Suelo:", json.dumps(res_btc_suelo, default=str))
    print("Techo:", json.dumps(res_btc_techo, default=str))

    print("\nRESUMEN rho/p-valor por caso:")
    print(json.dumps({
        "ETH_ajuste_suelo": res_ajuste_suelo, "ETH_ajuste_techo": res_ajuste_techo,
        "ETH_tiempo_suelo": res_eth_t_suelo, "ETH_tiempo_techo": res_eth_t_techo,
        "BTC_moneda_suelo": res_btc_suelo, "BTC_moneda_techo": res_btc_techo,
    }, indent=2, default=str))
