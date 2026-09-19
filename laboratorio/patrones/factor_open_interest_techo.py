"""
Idea nueva del usuario (12-sept-2026): en vez de mirar solo el precio, mirar
el Open Interest (contratos abiertos en futuros de BTC) para ver si el
segundo pico de un doble techo sube "con conviccion real" (apalancamiento
entrando de verdad) o "sin fuerza" (el OI no acompana la subida de precio
-- posible senal de rally debil, mas probable que sea un techo real).

AVISO DE ALCANCE: el unico dato de Open Interest disponible en el proyecto
es de BTC (`datos/crudo/oi_historical_4h.csv`, dic-2020 a ago-2026, sin
huecos). No hay OI de ETH. Esto rompe la disciplina habitual de "ajustar
en ETH, confirmar en BTC" (memoria: feedback_validacion_cruzada_solo_eth)
-- aqui no hay ETH posible. Tratar cualquier resultado como EXPLORATORIO
sobre una sola moneda, no como hallazgo validado con cruce de activos,
hasta conseguir OI de otra moneda.

Definicion continua (nada de corte binario, regla del proyecto):
  roc_precio = variacion % del precio entre techo1 y techo2
  roc_oi     = variacion % del Open Interest entre techo1 y techo2
  divergencia_oi = roc_precio - roc_oi
    > 0  -> el precio subio mas de lo que crecio el interes abierto
            (posible rally "de papel", sin apalancamiento real detras)
    <= 0 -> el OI acompano o supero la subida de precio (conviccion real)

Se prueba como dimension CONTINUA (correlacion + terciles), nunca con un
umbral fijo elegido a mano.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from datos.cargar_oi import cargar_oi
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible

DIAS_EXITO = vcp.DIAS_EXITO
UMBRALES_EXITO_PCT = vcp.UMBRALES_EXITO_PCT


def _oi_diario(df_oi_4h: pd.DataFrame) -> pd.Series:
    """Resample del OI de 4h a diario (ultimo valor del dia, causal)."""
    s = df_oi_4h.set_index("open_time")["oi"]
    diario = s.resample("1D").last().ffill()
    return diario


def _candidatos_con_oi(df: pd.DataFrame, oi_diario: pd.Series, pesos: tuple) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    n = len(df)
    filas = []
    for c in candidatos:
        f1, f2 = fechas.iloc[c.idx_techo1].normalize(), fechas.iloc[c.idx_techo2].normalize()
        if f1 not in oi_diario.index or f2 not in oi_diario.index:
            continue
        oi1, oi2 = oi_diario.loc[f1], oi_diario.loc[f2]
        if oi1 == 0 or pd.isna(oi1) or pd.isna(oi2):
            continue
        roc_precio = (close[c.idx_techo2] - close[c.idx_techo1]) / close[c.idx_techo1] * 100
        roc_oi = (oi2 - oi1) / oi1 * 100
        divergencia_oi = roc_precio - roc_oi

        minimo_intermedio = df["close"].iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + vcp.DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_techo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf < minimo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None

        filas.append({
            "idx_techo2": c.idx_techo2, "idx_confirmacion": idx_confirmacion,
            "divergencia_oi": divergencia_oi, "roc_precio": roc_precio, "roc_oi": roc_oi,
        })
    return filas


def _retorno_directo(df: pd.DataFrame, idx2: int, dias: int = DIAS_EXITO) -> float | None:
    n = len(df)
    fin = idx2 + dias
    if fin >= n:
        return None
    p0 = df["close"].iloc[idx2]
    return (df["close"].iloc[fin] - p0) / p0 * 100


if __name__ == "__main__":
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="factor_oi_techo_btc", acceso_reserva=True, motivo="OI solo cubre BTC, se necesita rango completo dic-2020 a hoy")
    df_oi_4h = cargar_oi()
    oi_diario = _oi_diario(df_oi_4h)
    print(f"Cobertura OI: {oi_diario.index.min()} a {oi_diario.index.max()}  (n dias={len(oi_diario)})\n")

    pesos = (0.35, 0.25, 0.1, 0.3)  # pesos de forma ya congelados en ETH-ajuste (reutilizados, no re-ajustados aqui)
    filas = _candidatos_con_oi(df_btc, oi_diario, pesos)
    print(f"Candidatos BTC con OI disponible: {len(filas)}\n")

    retornos, divergencias = [], []
    for f in filas:
        r = _retorno_directo(df_btc, f["idx_techo2"])
        if r is None:
            continue
        retornos.append(r)
        divergencias.append(f["divergencia_oi"])

    retornos = np.array(retornos)
    divergencias = np.array(divergencias)
    print(f"Con retorno medible: {len(retornos)}\n")

    from scipy.stats import spearmanr
    rho, p = spearmanr(divergencias, retornos)
    print(f"Correlacion (Spearman) divergencia_oi vs retorno futuro: rho={rho:.3f}, p={p:.3f}")
    print("  (rho positivo esperado: mas divergencia = rally sin OI detras = deberia BAJAR mas -> retorno mas negativo -> rho NEGATIVO si la idea es correcta)\n")

    terciles = np.quantile(divergencias, [1/3, 2/3])
    grupo_bajo = retornos[divergencias <= terciles[0]]
    grupo_medio = retornos[(divergencias > terciles[0]) & (divergencias <= terciles[1])]
    grupo_alto = retornos[divergencias > terciles[1]]

    def resumen(nombre, arr):
        if len(arr) == 0:
            print(f"  {nombre}: sin datos")
            return
        aciertos = [float((arr <= -u).mean() * 100) for u in UMBRALES_EXITO_PCT]
        print(f"  {nombre} (n={len(arr)}): retorno medio={arr.mean():.2f}%, acierto medio short={np.mean(aciertos):.1f}% (rango {min(aciertos):.0f}-{max(aciertos):.0f}%)")

    print("Por terciles de divergencia_oi (bajo = OI acompano o supero al precio; alto = precio subio mucho mas que el OI):")
    resumen("divergencia BAJA (OI fuerte, conviccion real)", grupo_bajo)
    resumen("divergencia MEDIA", grupo_medio)
    resumen("divergencia ALTA (precio subio sin OI detras)", grupo_alto)
