"""
Validacion completa (cordura + confirmacion de ruptura) para doble suelo y
doble techo flexibles, en 1 dia -- el UNICO timeframe en el que estos
detectores funcionan correctamente ahora mismo (ventana_min_dias /
ventana_max_dias / dias_ventana_volumen asumen 1 vela = 1 dia; usarlos en
15m/1h/4h sin escalar por velas-por-dia produce ventanas silenciosamente
equivocadas -- ver leccion 5 de la skill `deteccion-flexible-patrones`).

Dos pruebas independientes, sobre 2021-01-01 en adelante:

1. Cordura: para cada señal real del detector ESTRICTO (que dispara el DIA
   DE LA ROTURA, no el dia del segundo suelo/techo), se promedian TODOS los
   candidatos flexibles cuyo fondo2/techo2 cayera en una ventana de dias
   previos -- y esto se repite para varias ventanas distintas
   (`VENTANAS_CORDURA_DIAS`), nunca una sola fija ni "solo el mas cercano",
   siguiendo el mismo principio de "sin absolutos" del resto de la
   metodologia (ver skill `deteccion-flexible-patrones`). Se mira la
   probabilidad media de consenso (`probabilidad_media_por_fondo2/techo2`,
   ensemble de 960 configs) de esos candidatos emparejados. Si las señales
   estrictas caen en un percentil alto de la distribucion completa -- y ese
   percentil es estable entre ventanas, no un artefacto de una sola
   eleccion de ventana -- el flexible esta capturando lo mismo que el
   estricto (y mas).

2. Confirmacion (Etapa 2): de TODOS los candidatos que detecta el
   flexible (una sola configuracion -- los pesos por defecto de
   detectar(), que son los ganadores), se separan en los que confirman
   con una rotura real del extremo intermedio en los `DIAS_CONFIRMACION`
   dias siguientes y los que no, y se compara el acierto/retorno de cada
   grupo contra el azar (cualquier dia al azar, mismo horizonte).

Gobernanza de datos: carga por `laboratorio.datos_lab.cargar_ohlcv_lab`,
que por defecto recorta a Desarrollo (< 2025-01-01) -- ver ese modulo. Una
version anterior de este script cargaba histórico hasta 2026 sin querer,
tocando Validacion y Reserva sin registrar el acceso; divulgado y corregido
el 10-sept-2026 (ver registro/accesos_validacion_reserva.jsonl).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio import doble_suelo, doble_techo
from laboratorio.patrones import doble_suelo_flexible, doble_techo_flexible
from laboratorio.patrones.doble_suelo_consenso import probabilidad_media_por_fondo2
from laboratorio.patrones.doble_techo_consenso import probabilidad_media_por_techo2

CORTE = pd.Timestamp("2021-01-01", tz="UTC")
BUFFER_ENSEMBLE = pd.Timestamp("2020-06-01", tz="UTC")
DIAS_CONFIRMACION = 10
DIAS_EXITO = 15
UMBRAL_EXITO_PCT = 5.0
VENTANA_ESTRICTO_DIAS = 20  # ventana=20 en 1d, escalado desde 120 velas de 4h -- misma que calcular_indicadores
VENTANAS_CORDURA_DIAS = [10, 15, 20, 25, 30]  # rango, no un valor fijo, para el emparejamiento de cordura -- "estamos jugando con absolutos"


def _cordura(df_ens: pd.DataFrame, prob_por_idx2: dict, fechas_estrictas: list) -> dict:
    """Para cada ventana en VENTANAS_CORDURA_DIAS: empareja cada señal
    estricta con la MEDIA (no el mas cercano) de todos los candidatos
    flexibles en esa ventana previa, y calcula el percentil resultante.
    Ninguna ventana unica decide el resultado -- se reporta el rango/media
    entre ventanas para que el chequeo no dependa de una eleccion
    arbitraria de "cuantos dias mirar atras" ni de "cual candidato usar"."""
    idx2_ordenados = sorted(prob_por_idx2.keys())
    fechas_idx2 = df_ens.loc[idx2_ordenados, "open_time"].reset_index(drop=True)
    todas = np.array([prob_por_idx2[i] for i in idx2_ordenados])

    por_ventana = {}
    for ventana in VENTANAS_CORDURA_DIAS:
        delta = pd.Timedelta(days=ventana)
        probs_estrictas = []
        for fecha in fechas_estrictas:
            en_rango = (fechas_idx2 <= fecha) & (fechas_idx2 >= fecha - delta)
            candidatos = todas[en_rango.to_numpy()]
            if len(candidatos) == 0:
                continue
            probs_estrictas.append(float(candidatos.mean()))
        if not probs_estrictas:
            por_ventana[ventana] = None
            continue
        media_estrictas = float(np.mean(probs_estrictas))
        por_ventana[ventana] = {
            "n_emparejado": len(probs_estrictas),
            "estrictas_media": round(media_estrictas, 3),
            "percentil": round(float((todas < media_estrictas).mean() * 100), 1),
        }

    percentiles = [v["percentil"] for v in por_ventana.values() if v is not None]
    return {
        "n_estricto": len(fechas_estrictas),
        "todas_media": round(float(todas.mean()), 3) if len(todas) else None,
        "por_ventana_dias": por_ventana,
        "percentil_medio": round(float(np.mean(percentiles)), 1) if percentiles else None,
        "percentil_rango": [round(float(min(percentiles)), 1), round(float(max(percentiles)), 1)] if percentiles else None,
    }


def _confirmacion_suelo(df: pd.DataFrame) -> dict:
    candidatos = doble_suelo_flexible.detectar(df)
    n = len(df)
    con, sin = [], []
    for c in candidatos:
        fecha2 = df.loc[c.idx_fondo2, "open_time"]
        if fecha2 < CORTE:
            continue
        fin_exito = c.idx_fondo2 + DIAS_EXITO
        if fin_exito >= n:
            continue
        maximo_intermedio = df["close"].iloc[c.idx_fondo1: c.idx_fondo2 + 1].max()
        fin_conf = min(c.idx_fondo2 + 1 + DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_fondo2 + 1: fin_conf]
        confirma = bool((tramo_conf > maximo_intermedio).any())
        precio0 = df["close"].iloc[c.idx_fondo2]
        retorno_pct = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
        (con if confirma else sin).append(retorno_pct)
    return _resumen_grupos(con, sin, exito_es_subida=True)


def _confirmacion_techo(df: pd.DataFrame) -> dict:
    candidatos = doble_techo_flexible.detectar(df)
    n = len(df)
    con, sin = [], []
    for c in candidatos:
        fecha2 = df.loc[c.idx_techo2, "open_time"]
        if fecha2 < CORTE:
            continue
        fin_exito = c.idx_techo2 + DIAS_EXITO
        if fin_exito >= n:
            continue
        minimo_intermedio = df["close"].iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + DIAS_CONFIRMACION, n)
        tramo_conf = df["close"].iloc[c.idx_techo2 + 1: fin_conf]
        confirma = bool((tramo_conf < minimo_intermedio).any())
        precio0 = df["close"].iloc[c.idx_techo2]
        retorno_pct = (df["close"].iloc[fin_exito] - precio0) / precio0 * 100
        (con if confirma else sin).append(retorno_pct)
    return _resumen_grupos(con, sin, exito_es_subida=False)


def _resumen_grupos(con: list, sin: list, exito_es_subida: bool) -> dict:
    def stats(retornos):
        if not retornos:
            return {"n": 0, "acierto_pct": None, "retorno_medio_pct": None}
        arr = np.array(retornos)
        acierto = (arr >= UMBRAL_EXITO_PCT) if exito_es_subida else (arr <= -UMBRAL_EXITO_PCT)
        return {
            "n": len(arr),
            "acierto_pct": round(float(acierto.mean() * 100), 1),
            "retorno_medio_pct": round(float(arr.mean()), 2),
        }
    return {"con_confirmacion": stats(con), "sin_confirmacion": stats(sin)}


def _baseline(df: pd.DataFrame, exito_es_subida: bool) -> dict:
    n = len(df)
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    retornos = []
    for i in range(n - DIAS_EXITO):
        if fechas.iloc[i] < CORTE:
            continue
        retornos.append((close[i + DIAS_EXITO] - close[i]) / close[i] * 100)
    arr = np.array(retornos)
    acierto = (arr >= UMBRAL_EXITO_PCT) if exito_es_subida else (arr <= -UMBRAL_EXITO_PCT)
    return {
        "n": len(arr),
        "acierto_pct": round(float(acierto.mean() * 100), 1),
        "retorno_medio_pct": round(float(arr.mean()), 2),
    }


def ejecutar(par: str, acceso_validacion: bool = False, motivo: str = "") -> dict:
    """Por defecto usa SOLO datos de Desarrollo (< 2025-01-01), via
    laboratorio.datos_lab.cargar_ohlcv_lab -- ver esa funcion y
    registro/accesos_validacion_reserva.jsonl para el porque. Pasar
    acceso_validacion=True + motivo solo si de verdad hace falta mirar 2025
    (Reserva 2026-hoy no se expone aqui a proposito)."""
    df_full = cargar_ohlcv_lab(
        par, "1d", estrategia="doble_suelo_techo_flexible_validacion",
        acceso_validacion=acceso_validacion, motivo=motivo,
    )

    # --- estricto: necesita el historial completo para sus rolling windows ---
    df_suelo = doble_suelo.calcular_indicadores(df_full, ventana=VENTANA_ESTRICTO_DIAS)
    df_suelo = doble_suelo.calcular_senales(df_suelo)
    fechas_suelo = df_suelo.loc[df_suelo["entra_largo"] & (df_suelo["open_time"] >= CORTE), "open_time"].tolist()

    df_techo = doble_techo.calcular_indicadores(df_full, ventana=VENTANA_ESTRICTO_DIAS, velas_regimen=200, ma_cae_velas=30)
    df_techo = doble_techo.calcular_senales(df_techo)
    fechas_techo = df_techo.loc[df_techo["entra_corto"] & (df_techo["open_time"] >= CORTE), "open_time"].tolist()

    # --- ensemble flexible: solo necesita un buffer de unos meses antes del corte ---
    df_ens = df_full[df_full["open_time"] >= BUFFER_ENSEMBLE].reset_index(drop=True)
    prob_suelo = probabilidad_media_por_fondo2(df_ens)
    prob_techo = probabilidad_media_por_techo2(df_ens)

    cordura_suelo = _cordura(df_ens, prob_suelo, fechas_suelo)
    cordura_techo = _cordura(df_ens, prob_techo, fechas_techo)

    conf_suelo = _confirmacion_suelo(df_full)
    conf_techo = _confirmacion_techo(df_full)

    baseline_subida = _baseline(df_full, exito_es_subida=True)
    baseline_bajada = _baseline(df_full, exito_es_subida=False)

    return {
        "par": par,
        "cordura_suelo": cordura_suelo,
        "cordura_techo": cordura_techo,
        "confirmacion_suelo": conf_suelo,
        "confirmacion_techo": conf_techo,
        "baseline_subida": baseline_subida,
        "baseline_bajada": baseline_bajada,
    }


if __name__ == "__main__":
    import json
    import time

    for par in ["BTCUSDT", "ETHUSDT"]:
        t0 = time.time()
        resultado = ejecutar(par)
        resultado["segundos"] = round(time.time() - t0, 1)
        print(json.dumps(resultado, indent=2, default=str))
