"""
Dos ideas mas de la lista del 12-sept-2026, ambas con datos ya
disponibles en el proyecto:

1. ORO como "refugio": si el oro (XAUUSD) sube fuerte justo cuando el
   segundo pico se esta formando, puede ser senal de que el dinero
   institucional ya esta rotando hacia refugio antes de que se note en
   cripto -- mas probable que el doble techo cripto sea real.
   Definicion continua: roc_oro_pct = variacion % del oro en los K dias
   antes de techo2 (rango de K, nunca un solo numero).

2. PROXIMIDAD AL MAXIMO HISTORICO (ATH): un doble techo muy cerca del ATH
   de todos los tiempos pesa distinto (psicologicamente) que uno a mitad
   de una simple correccion.
   Definicion continua: distancia_ath_pct = (ATH_hasta_ese_dia - precio) / ATH * 100.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab


def _cargar_oro_yahoo(ruta: str = "datos/crudo/XAUUSD_1d_yahoo_futures.csv") -> pd.DataFrame:
    df = pd.read_csv(ruta)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.sort_values("open_time").reset_index(drop=True)
from laboratorio.patrones import doble_techo_flexible

DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
PESOS_FORMA = (0.35, 0.25, 0.1, 0.3)
VENTANAS_ORO_DIAS = [10, 20, 30]


def _candidatos(df: pd.DataFrame, pesos: tuple) -> list:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    return doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _serie_oro_diaria(df_oro: pd.DataFrame) -> pd.Series:
    return df_oro.set_index("open_time")["close"].resample("1D").last().ffill()


def _resumen_terciles(nombre_dim: str, valores: np.ndarray, retornos: np.ndarray):
    rho, p = spearmanr(valores, retornos)
    print(f"    {nombre_dim}: rho={rho:.3f} p={p:.3f}")
    terciles = np.quantile(valores, [1 / 3, 2 / 3])
    bajo = retornos[valores <= terciles[0]]
    alto = retornos[valores > terciles[1]]
    if len(bajo) and len(alto):
        print(f"      tercil bajo -> retorno medio {bajo.mean():.2f}% (n={len(bajo)}) | tercil alto -> retorno medio {alto.mean():.2f}% (n={len(alto)})")


def _analizar(nombre: str, df: pd.DataFrame, oro_diario: pd.Series, desde, hasta):
    print(f"=== {nombre} ===")
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    candidatos = _candidatos(df, PESOS_FORMA)

    # --- ATH ---
    ath_hasta = np.maximum.accumulate(close)
    dist_ath, ret_ath = [], []
    for c in candidatos:
        fecha2 = fechas.iloc[c.idx_techo2]
        if fecha2 < desde or fecha2 >= hasta:
            continue
        r = _retorno_directo(df, c.idx_techo2)
        if r is None:
            continue
        ath = ath_hasta[c.idx_techo2]
        dist_ath.append((ath - close[c.idx_techo2]) / ath * 100)
        ret_ath.append(r)
    if len(dist_ath) >= 5:
        print(f"  Proximidad al ATH (n={len(dist_ath)}):")
        _resumen_terciles("distancia_ath_pct vs retorno (si la idea es correcta: MENOS distancia -> MAS bajada -> rho POSITIVO)", np.array(dist_ath), np.array(ret_ath))
    else:
        print("  ATH: muestra insuficiente")

    # --- ORO ---
    print("  Oro (roc% antes de techo2, rho positivo esperado = oro sube -> retorno cripto mas negativo??? ver signo abajo):")
    for K in VENTANAS_ORO_DIAS:
        rocs, rets = [], []
        for c in candidatos:
            fecha2 = fechas.iloc[c.idx_techo2].normalize()
            if fecha2 < desde or fecha2 >= hasta:
                continue
            fecha_antes = fecha2 - pd.Timedelta(days=K)
            if fecha_antes not in oro_diario.index or fecha2 not in oro_diario.index:
                continue
            oro0, oro1 = oro_diario.loc[fecha_antes], oro_diario.loc[fecha2]
            if pd.isna(oro0) or pd.isna(oro1) or oro0 == 0:
                continue
            r = _retorno_directo(df, c.idx_techo2)
            if r is None:
                continue
            rocs.append((oro1 - oro0) / oro0 * 100)
            rets.append(r)
        if len(rocs) < 5:
            print(f"    K={K}d: muestra insuficiente (n={len(rocs)})")
            continue
        rocs_arr, rets_arr = np.array(rocs), np.array(rets)
        rho, p = spearmanr(rocs_arr, rets_arr)
        mediana = np.median(rocs_arr)
        oro_debil = rets_arr[rocs_arr <= mediana]
        oro_fuerte = rets_arr[rocs_arr > mediana]
        print(f"    K={K}d (n={len(rocs)}): rho={rho:.3f} p={p:.3f} | oro DEBIL antes del pico -> retorno cripto {oro_debil.mean():.2f}% | oro FUERTE antes del pico -> retorno cripto {oro_fuerte.mean():.2f}%")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_oro_ath_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_oro_ath_btc")
    df_oro = _cargar_oro_yahoo()
    oro_diario = _serie_oro_diaria(df_oro)
    print(f"Cobertura oro: {oro_diario.index.min()} a {oro_diario.index.max()}\n")

    _analizar("ETH ajuste (2021-2023)", df_eth, oro_diario, vcp.CORTE, vcp.CORTE_AJUSTE_FIN)
    _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, oro_diario, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    _analizar("BTC completo (nunca visto)", df_btc, oro_diario, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
