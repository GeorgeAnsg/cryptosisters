"""
Idea del usuario (12-sept-2026): panorama macro -- tipos de interes
(bonos del Tesoro a 10 y 30 anios) y liquidez global (balance de la Fed,
oferta monetaria M2). Hipotesis: cuando los tipos suben o la Fed retira
liquidez (balance cayendo, "QT"), el dinero es mas caro y los activos de
riesgo (cripto) son mas fragiles -- un doble techo en ese contexto deberia
ser mas fiable.

Datos: descargados de FRED (fuente oficial, gratuita) el 12-sept-2026 --
DGS10, DGS30 (diario), WALCL (semanal, balance Fed), M2SL (mensual, M2).
Fusion CAUSAL (merge_asof backward, igual que ya se hace con funding rate
y Open Interest en el proyecto) -- nunca se usa un dato publicado despues
del dia del pico.

Se prueba, aplicando la leccion de hoy, DENTRO del grupo ya validado
(regimen bajista + nivel repetido) y tambien en todos los candidatos.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible
from laboratorio.patrones.doble_techo_probabilidad_total import TOLERANCIA_NIVEL_PATRON_PREVIO_PCT

DIAS_EXITO = vcp.DIAS_EXITO
PESOS_FORMA = (0.35, 0.25, 0.1, 0.3)
VENTANAS_ROC_DIAS = [20, 40, 60]


def _cargar_fred(serie: str) -> pd.Series:
    df = pd.read_csv(f"datos/crudo/{serie}.csv")
    df["observation_date"] = pd.to_datetime(df["observation_date"], utc=True)
    df[serie] = pd.to_numeric(df[serie], errors="coerce")
    s = df.set_index("observation_date")[serie].sort_index()
    return s.resample("1D").last().ffill()


def _candidatos_completos(df: pd.DataFrame, pesos: tuple) -> list:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]; close = close_s.to_numpy(); sma200 = close_s.rolling(200).mean()
    ordenados = sorted(candidatos, key=lambda c: c.idx_techo2)
    niveles_previos = []
    filas = []
    for c in ordenados:
        media = sma200.iloc[c.idx_techo2]
        media_hace_20 = sma200.iloc[c.idx_techo2 - 20] if c.idx_techo2 >= 20 else None
        debajo = bool(media == media and close[c.idx_techo2] < media)
        cayendo = bool(media == media and media_hace_20 is not None and media_hace_20 == media_hace_20 and media < media_hace_20)
        debajo_y_cayendo = debajo and cayendo
        nivel_actual = (close[c.idx_techo1] + close[c.idx_techo2]) / 2
        patron_previo = any(
            idx2p < c.idx_techo1 - 3 and abs(nivp - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2p, nivp in niveles_previos
        )
        niveles_previos.append((c.idx_techo2, nivel_actual))
        filas.append({"c": c, "debajo_y_cayendo": debajo_y_cayendo, "patron_previo": patron_previo})
    return filas


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _analizar(nombre: str, df: pd.DataFrame, series_macro: dict[str, pd.Series], desde, hasta, solo_validados: bool):
    print(f"=== {nombre} ({'grupo validado' if solo_validados else 'todos'}) ===")
    fechas = df["open_time"]
    filas = _candidatos_completos(df, PESOS_FORMA)

    for nombre_serie, serie in series_macro.items():
        for K in VENTANAS_ROC_DIAS:
            rocs, retornos = [], []
            for f in filas:
                c = f["c"]
                if solo_validados and not (f["debajo_y_cayendo"] and f["patron_previo"]):
                    continue
                fecha2 = fechas.iloc[c.idx_techo2].normalize()
                fecha_antes = fecha2 - pd.Timedelta(days=K)
                if fecha2 < desde or fecha2 >= hasta:
                    continue
                if fecha2 not in serie.index or fecha_antes not in serie.index:
                    continue
                v0, v1 = serie.loc[fecha_antes], serie.loc[fecha2]
                if pd.isna(v0) or pd.isna(v1) or v0 == 0:
                    continue
                r = _retorno_directo(df, c.idx_techo2)
                if r is None:
                    continue
                rocs.append((v1 - v0) / abs(v0) * 100)
                retornos.append(r)
            if len(rocs) < 6:
                print(f"  {nombre_serie} K={K}d: muestra insuficiente (n={len(rocs)})")
                continue
            rocs_arr, ret_arr = np.array(rocs), np.array(retornos)
            rho, p = spearmanr(rocs_arr, ret_arr)
            mediana = np.median(rocs_arr)
            bajo = ret_arr[rocs_arr <= mediana]
            alto = ret_arr[rocs_arr > mediana]
            print(f"  {nombre_serie} K={K}d (n={len(rocs)}): rho={rho:.3f} p={p:.3f} | {nombre_serie} BAJA/CAE->retorno {bajo.mean():.2f}% | {nombre_serie} SUBE->retorno {alto.mean():.2f}%")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_macro_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_macro_btc")

    series_macro = {
        "DGS10 (bono 10a)": _cargar_fred("DGS10"),
        "DGS30 (bono 30a)": _cargar_fred("DGS30"),
        "WALCL (balance Fed)": _cargar_fred("WALCL"),
        "M2SL (oferta M2)": _cargar_fred("M2SL"),
        "CPIAUCSL (IPC)": _cargar_fred("CPIAUCSL"),
        "PPIACO (IPP)": _cargar_fred("PPIACO"),
        "PAYEMS (nominas no agricolas)": _cargar_fred("PAYEMS"),
        "DTWEXBGS (dolar DXY)": _cargar_fred("DTWEXBGS"),
        "VIXCLS (miedo bolsa VIX)": _cargar_fred("VIXCLS"),
        "USDT_SUPPLY (oferta stablecoin)": _cargar_fred("USDT_SUPPLY"),
    }
    for nombre_serie, s in series_macro.items():
        print(f"Cobertura {nombre_serie}: {s.index.min().date()} a {s.index.max().date()}")
    print()

    for solo_validados in (True, False):
        _analizar("ETH 2017-2021", df_eth, series_macro, df_eth["open_time"].min(), vcp.CORTE, solo_validados)
        _analizar("ETH ajuste (2021-2023)", df_eth, series_macro, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, solo_validados)
        _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, series_macro, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, solo_validados)
        _analizar("BTC (nunca visto)", df_btc, series_macro, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, solo_validados)
