"""
Dos correcciones del usuario sobre la primera version de este script
(11-sept-2026):

1. Comparar "entrar nada mas detectar el fondo" vs "entrar con
   confirmacion completa" ya era una mejora, pero "confirmacion completa"
   (recuperar el 100% de la caida, romper el pico) es OTRO absoluto
   disfrazado -- debe ser un RANGO de umbrales de recuperacion (20/40/60/
   80/100%), no un corte binario, igual que el resto de la metodologia.

2. El universo no solapado para el Monte Carlo puede ser mas pequeño que
   el numero de candidatos observados cuando se entra pronto (sin exigir
   confirmacion, hay muchos mas candidatos) -- se soluciona muestreando
   CON reemplazo cuando el universo no alcanza (declarado explicitamente,
   no oculto).

Pregunta que responde: ¿en que punto de la recuperacion conviene entrar?
Si el problema es "no saber cuando entrar en la caida", este es el barrido
que lo comprueba de verdad -- desde "nada mas tocar fondo" (0% recuperado)
hasta "ya recupero todo" (100%, lo unico probado hasta ahora).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import caida_recuperacion

SEMILLA = 20260911
N_SIMULACIONES = 5000
MEJOR_CONFIG = (4, 25, 20.0, 4.0, 7, 40.0, 20, (0.3, 0.3, 0.4))
UMBRALES_RECUPERACION_PCT = [20.0, 40.0, 60.0, 80.0, 100.0]  # rango, no un corte fijo
DIAS_MAX_ENTRADA = 20  # ventana para alcanzar el umbral de recuperacion, igual que dias_confirmacion


def _candidatos(df, config):
    (ventana_min, ventana_max, caida_ideal, velocidad_ideal, dias_rec,
     recuperacion_ideal, dias_confirmacion, pesos) = config
    peso_caida, peso_velocidad, peso_recuperacion = pesos
    return caida_recuperacion.detectar(
        df, ventana_min_dias=ventana_min, ventana_max_dias=ventana_max,
        caida_ideal_pct=caida_ideal, velocidad_ideal_pct_dia=velocidad_ideal,
        dias_ventana_recuperacion=dias_rec, recuperacion_ideal_pct=recuperacion_ideal,
        peso_caida=peso_caida, peso_velocidad=peso_velocidad, peso_recuperacion=peso_recuperacion,
    )


def _retornos_en_umbral(df, config, desde, hasta, umbral_recuperacion_pct):
    candidatos = _candidatos(df, config)
    n = len(df)
    fechas = df["open_time"]
    close = df["close"].to_numpy()
    retornos = []
    for c in candidatos:
        fecha_fondo = fechas.iloc[c.idx_fondo]
        if fecha_fondo < desde or fecha_fondo >= hasta:
            continue
        objetivo = c.precio_fondo if hasattr(c, "precio_fondo") else close[c.idx_fondo]
        objetivo = objetivo + (umbral_recuperacion_pct / 100.0) * (c.precio_pico - objetivo)

        fin_v = min(c.idx_fondo + 1 + DIAS_MAX_ENTRADA, n)
        tramo = close[c.idx_fondo + 1: fin_v]
        alcanza = np.where(tramo >= objetivo)[0]
        if len(alcanza) == 0:
            continue
        idx_entrada = c.idx_fondo + 1 + int(alcanza[0])

        fin_exito = idx_entrada + vcp.DIAS_EXITO
        if fin_exito >= n:
            continue
        precio0 = close[idx_entrada]
        retornos.append((close[fin_exito] - precio0) / precio0 * 100)
    return retornos


def _puntos_no_solapados(df, desde, hasta):
    fechas = df["open_time"]
    n = len(df)
    idxs, i = [], 0
    while i + vcp.DIAS_EXITO < n:
        f = fechas.iloc[i]
        if desde <= f < hasta:
            idxs.append(i)
        i += vcp.DIAS_EXITO
    return idxs


def monte_carlo_con_reemplazo(df, desde, hasta, retornos_obs, rng):
    n_obs = len(retornos_obs)
    universo = _puntos_no_solapados(df, desde, hasta)
    if len(universo) < 5:
        return {"error": f"universo insuficiente para simular ({len(universo)} puntos)"}
    con_reemplazo = n_obs > len(universo)

    retorno_obs_medio = float(np.mean(retornos_obs))
    retornos_sim = np.empty(N_SIMULACIONES)
    for i in range(N_SIMULACIONES):
        muestra = rng.choice(universo, size=n_obs, replace=con_reemplazo)
        rets = []
        for idx in muestra:
            fin = idx + vcp.DIAS_EXITO
            p0 = df["close"].iloc[idx]
            rets.append((df["close"].iloc[fin] - p0) / p0 * 100)
        retornos_sim[i] = np.mean(rets)

    p_valor = float((retornos_sim >= retorno_obs_medio).mean())
    return {
        "n_obs": n_obs, "universo": len(universo), "con_reemplazo": con_reemplazo,
        "retorno_obs_pct": round(retorno_obs_medio, 2),
        "retorno_azar_medio_pct": round(float(retornos_sim.mean()), 2),
        "p_valor_retorno": round(p_valor, 4),
    }


if __name__ == "__main__":
    import json

    rng = np.random.default_rng(SEMILLA)
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="timing_entrada_caida_eth_v2")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="timing_entrada_caida_btc_v2")

    casos = [
        ("ETH tiempo no visto", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN),
        ("BTC completo", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN),
    ]

    resumen = {}
    for nombre, df, desde, hasta in casos:
        resumen[nombre] = {}
        print(f"\n=== {nombre} ===")
        for umbral in UMBRALES_RECUPERACION_PCT:
            retornos = _retornos_en_umbral(df, MEJOR_CONFIG, desde, hasta, umbral)
            if len(retornos) < 5:
                print(f"  recuperar {umbral}%: muestra insuficiente (n={len(retornos)})")
                continue
            res = monte_carlo_con_reemplazo(df, desde, hasta, retornos, rng)
            resumen[nombre][f"{umbral}%"] = res
            print(f"  recuperar {umbral}%: {json.dumps(res, default=str)}")

    print("\n\nRESUMEN:")
    print(json.dumps(resumen, indent=2, default=str))
