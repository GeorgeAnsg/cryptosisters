"""
Idea del usuario (12-sept-2026): no solo tendencias macro lentas (ya
probadas: IPC, tipos, dolar...) sino un SHOCK puntual y brusco -- una
noticia geopolitica (guerra, cierre de un estrecho, etc.) que golpea el
precio de golpe, muchas veces en fin de semana o fuera de horario de
mercados tradicionales. No tenemos un calendario de noticias, asi que se
mide como una ANOMALIA ESTADISTICA en vez de clasificar la noticia en si:

1. SHOCK DE PRECIO: el mayor movimiento diario (en valor absoluto) de
   cripto en una ventana antes de techo2, medido en "desviaciones" sobre
   su propia volatilidad reciente (z-score) -- si un dia se mueve mucho
   mas de lo normal para ESE activo en ESE momento, es un shock.

2. SHOCK DE VIX: el mayor salto porcentual del VIX (miedo en la bolsa
   tradicional) en una ventana antes de techo2 -- un shock de panico en
   mercados tradicionales que salpica a cripto.

Ambos se prueban como intensidad CONTINUA (no si "hubo o no hubo shock",
sino CUANTO de grande fue el mayor shock en la ventana), aplicando la
leccion de hoy: primero dentro del grupo ya validado, luego en todos.
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
VENTANAS_SHOCK_DIAS = [3, 5, 10]
VENTANA_VOLATILIDAD_BASE = 30  # dias para medir la volatilidad "normal" de referencia


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


def _shock_precio_zscore(retornos_diarios: np.ndarray, idx_techo2: int, ventana_shock: int) -> float | None:
    """Mayor |z-score| de retorno diario en los `ventana_shock` dias antes
    de techo2, usando la volatilidad de los VENTANA_VOLATILIDAD_BASE dias
    anteriores a esa ventana como referencia de "normalidad"."""
    inicio_base = idx_techo2 - ventana_shock - VENTANA_VOLATILIDAD_BASE
    fin_base = idx_techo2 - ventana_shock
    if inicio_base < 0:
        return None
    base = retornos_diarios[inicio_base:fin_base]
    if len(base) < 10:
        return None
    std_base = base.std()
    if std_base == 0 or np.isnan(std_base):
        return None
    tramo_shock = retornos_diarios[fin_base: idx_techo2]
    if len(tramo_shock) == 0:
        return None
    z = np.abs(tramo_shock) / std_base
    return float(z.max())


def _analizar(nombre: str, df: pd.DataFrame, vix: pd.Series, desde, hasta, solo_validados: bool):
    print(f"=== {nombre} ({'grupo validado' if solo_validados else 'todos'}) ===")
    fechas = df["open_time"]
    close = df["close"].to_numpy()
    retornos_diarios = np.diff(close) / close[:-1] * 100
    retornos_diarios = np.concatenate([[0.0], retornos_diarios])  # alinear indices
    filas = _candidatos_completos(df, PESOS_FORMA)

    for ventana in VENTANAS_SHOCK_DIAS:
        # --- shock de precio ---
        shocks, retornos = [], []
        for f in filas:
            c = f["c"]
            if solo_validados and not (f["debajo_y_cayendo"] and f["patron_previo"]):
                continue
            fecha2 = fechas.iloc[c.idx_techo2]
            if fecha2 < desde or fecha2 >= hasta:
                continue
            z = _shock_precio_zscore(retornos_diarios, c.idx_techo2, ventana)
            if z is None:
                continue
            r = _retorno_directo(df, c.idx_techo2)
            if r is None:
                continue
            shocks.append(z)
            retornos.append(r)
        if len(shocks) >= 6:
            shocks_arr, ret_arr = np.array(shocks), np.array(retornos)
            rho, p = spearmanr(shocks_arr, ret_arr)
            mediana = np.median(shocks_arr)
            sin_shock = ret_arr[shocks_arr <= mediana]
            con_shock = ret_arr[shocks_arr > mediana]
            print(f"  SHOCK PRECIO ventana={ventana}d (n={len(shocks)}): rho={rho:.3f} p={p:.3f} | sin_shock->retorno {sin_shock.mean():.2f}% | con_shock->retorno {con_shock.mean():.2f}%")
        else:
            print(f"  SHOCK PRECIO ventana={ventana}d: muestra insuficiente (n={len(shocks)})")

        # --- shock de VIX (mayor salto % en la ventana) ---
        shocks_vix, retornos_vix = [], []
        vix_pct = vix.pct_change() * 100
        for f in filas:
            c = f["c"]
            if solo_validados and not (f["debajo_y_cayendo"] and f["patron_previo"]):
                continue
            fecha2 = fechas.iloc[c.idx_techo2].normalize()
            if fecha2 < desde or fecha2 >= hasta:
                continue
            rango_fechas = pd.date_range(fecha2 - pd.Timedelta(days=ventana - 1), fecha2, freq="D", tz="UTC")
            valores = vix_pct.reindex(rango_fechas).dropna()
            if len(valores) == 0:
                continue
            r = _retorno_directo(df, c.idx_techo2)
            if r is None:
                continue
            shocks_vix.append(float(valores.abs().max()))
            retornos_vix.append(r)
        if len(shocks_vix) >= 6:
            shocks_arr, ret_arr = np.array(shocks_vix), np.array(retornos_vix)
            rho, p = spearmanr(shocks_arr, ret_arr)
            mediana = np.median(shocks_arr)
            sin_shock = ret_arr[shocks_arr <= mediana]
            con_shock = ret_arr[shocks_arr > mediana]
            print(f"  SHOCK VIX ventana={ventana}d (n={len(shocks_vix)}): rho={rho:.3f} p={p:.3f} | sin_shock->retorno {sin_shock.mean():.2f}% | con_shock->retorno {con_shock.mean():.2f}%")
        else:
            print(f"  SHOCK VIX ventana={ventana}d: muestra insuficiente (n={len(shocks_vix)})")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_shock_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_shock_btc")
    vix = _cargar_fred("VIXCLS")

    for solo_validados in (True, False):
        _analizar("ETH 2017-2021", df_eth, vix, df_eth["open_time"].min(), vcp.CORTE, solo_validados)
        _analizar("ETH ajuste (2021-2023)", df_eth, vix, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, solo_validados)
        _analizar("ETH tiempo (2023-2025, nunca visto)", df_eth, vix, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN, solo_validados)
        _analizar("BTC (nunca visto)", df_btc, vix, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN, solo_validados)
