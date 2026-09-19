"""
Espejo de `factor_techo_simultaneo.py` para el suelo: si BTC y ETH forman
un doble suelo casi al mismo tiempo (fondo2 de ambos dentro de una
ventana de N dias), es mas probable que sea un suelo de MERCADO real (todo
el dinero girando a la vez) y no ruido propio de una sola moneda.

No se asume que la ventana o la fuerza del efecto sea igual al techo --
se mide de cero, con el mismo rango de ventanas.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_suelo_flexible

DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT
VENTANAS_SIMULTANEIDAD_DIAS = [2, 4, 6, 10]
PESOS_FORMA = (0.2, 0.2, 0.1, 0.5)


def _fechas_fondo2(df: pd.DataFrame, pesos: tuple):
    peso_nivel, peso_rebote, peso_tiempo, peso_altura = pesos
    candidatos = doble_suelo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_rebote=peso_rebote, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    fechas = df["open_time"]
    return sorted(fechas.iloc[c.idx_fondo2] for c in candidatos), candidatos


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


def _analizar(nombre: str, df_propio: pd.DataFrame, fechas_otro: list, desde, hasta):
    print(f"=== {nombre} ===")
    fechas_propio, candidatos_propio = _fechas_fondo2(df_propio, PESOS_FORMA)
    fechas_otro_arr = pd.DatetimeIndex(fechas_otro)
    fechas_df = df_propio["open_time"]

    for ventana in VENTANAS_SIMULTANEIDAD_DIAS:
        con_apoyo, sin_apoyo = [], []
        for c in candidatos_propio:
            fecha2 = fechas_df.iloc[c.idx_fondo2]
            if fecha2 < desde or fecha2 >= hasta:
                continue
            r = _retorno_directo(df_propio, c.idx_fondo2)
            if r is None:
                continue
            diffs = np.abs((fechas_otro_arr - fecha2).days)
            tiene_apoyo = bool(len(diffs) > 0 and diffs.min() <= ventana)
            (con_apoyo if tiene_apoyo else sin_apoyo).append(r)

        def resumen(nombre_grupo, arr):
            if len(arr) == 0:
                return f"{nombre_grupo}: sin casos"
            arr = np.array(arr)
            aciertos = [float((arr >= u).mean() * 100) for u in UMBRALES_EXITO_PCT]  # exito de suelo = SUBIR
            return f"{nombre_grupo} (n={len(arr)}): retorno medio={arr.mean():.2f}%, acierto medio={np.mean(aciertos):.1f}%"

        p_txt = ""
        if len(con_apoyo) >= 5 and len(sin_apoyo) >= 5:
            _, p = mannwhitneyu(con_apoyo, sin_apoyo, alternative="greater")
            p_txt = f"  (Mann-Whitney U, con_apoyo > sin_apoyo: p={p:.3f})"
        print(f"  ventana +/-{ventana}d: {resumen('CON apoyo del otro activo', con_apoyo)} | {resumen('SIN apoyo', sin_apoyo)}{p_txt}")
    print()


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="factor_suelo_simultaneo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_suelo_simultaneo_btc")

    fechas_btc, _ = _fechas_fondo2(df_btc, PESOS_FORMA)
    fechas_eth, _ = _fechas_fondo2(df_eth, PESOS_FORMA)

    _analizar("ETH ajuste (2021-2023) -- apoyo de BTC", df_eth, fechas_btc, vcp.CORTE, vcp.CORTE_AJUSTE_FIN)
    _analizar("ETH tiempo (2023-2025, nunca visto) -- apoyo de BTC", df_eth, fechas_btc, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN)
    _analizar("BTC completo (nunca visto) -- apoyo de ETH", df_btc, fechas_eth, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN)
