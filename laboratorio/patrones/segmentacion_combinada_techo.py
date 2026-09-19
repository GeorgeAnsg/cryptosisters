"""
Combina las dos pistas encontradas en doble techo esta sesion (11-sept-2026):
1. Regimen de mercado debil: precio bajo su media 200 Y esa media cayendo
   (la mas fuerte -- p=0.025 en BTC, unica significativa hasta ahora).
2. Zona de resistencia testeada: 1+ toque previo al mismo nivel de precio
   en los 180 dias antes de techo1 (consistente en direccion en 4/4 cortes,
   pero no significativa por si sola).

Hipotesis: si ambas apuntan en la misma direccion (un doble techo mas
fiable), combinarlas deberia reforzar la señal mas que cualquiera de las
dos por separado -- o, si la zona de resistencia no aporta nada real,
la combinada no debe ser mejor que el regimen solo.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

import laboratorio.patrones.validacion_cruzada_pesos as vcp
import laboratorio.patrones.monte_carlo_confirmacion as mc
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import doble_techo_flexible
from laboratorio.patrones.doble_techo_flexible import _detectar_techos_simple

DIAS_VENTANA_HISTORICA = 180
TOLERANCIA_NIVEL_PCT = 5.0


def _candidatos_confirmados_combinado(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]
    close = close_s.to_numpy()
    sma200 = close_s.rolling(200).mean()
    todos_techos = _detectar_techos_simple(close)
    n = len(df)
    filas = []
    for c in candidatos:
        # regimen
        media = sma200.iloc[c.idx_techo2]
        media_hace_20 = sma200.iloc[c.idx_techo2 - 20] if c.idx_techo2 >= 20 else None
        debajo_media = bool(media == media and close[c.idx_techo2] < media)
        media_cayendo = bool(
            media == media and media_hace_20 is not None and media_hace_20 == media_hace_20 and media < media_hace_20
        )
        debajo_y_cayendo = debajo_media and media_cayendo

        # zona de resistencia
        nivel = close[c.idx_techo1]
        inicio_ventana = max(0, c.idx_techo1 - DIAS_VENTANA_HISTORICA)
        toques_previos = sum(
            1 for t in todos_techos
            if inicio_ventana <= t < c.idx_techo1 and abs(close[t] - nivel) / nivel * 100 <= TOLERANCIA_NIVEL_PCT
        )
        zona_testeada = toques_previos >= 1

        minimo_intermedio = close_s.iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + vcp.DIAS_CONFIRMACION, n)
        tramo_conf = close_s.iloc[c.idx_techo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf < minimo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None

        filas.append({
            "idx_techo2": c.idx_techo2, "idx_confirmacion": idx_confirmacion,
            "debajo_y_cayendo": debajo_y_cayendo, "zona_testeada": zona_testeada,
            "ambas": debajo_y_cayendo and zona_testeada,
        })
    return filas


def _resumen_segmento(df: pd.DataFrame, filas: list[dict], desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    filas_planas = [(f["idx_techo2"], f["idx_confirmacion"]) for f in filas]
    return vcp._resumen(df, filas_planas, desde, hasta, exito_es_subida=False)["con_confirmacion"]


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_combinada_techo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_combinada_techo_btc")

    resultados_techo = []
    for pesos in vcp.PESOS_TECHO:
        filas = vcp._entradas_confirmadas_techo(df_eth, pesos)
        r = vcp._resumen(df_eth, filas, vcp.CORTE, vcp.CORTE_AJUSTE_FIN, False)
        resultados_techo.append({"pesos": pesos, "ajuste": r})
    mejor_pesos = vcp._mejor(resultados_techo)["pesos"]
    print(f"Pesos congelados: {mejor_pesos}\n")

    rng = np.random.default_rng(20260911)
    cortes = [
        ("ETH 2017-2021 (nunca usado en el ajuste)", df_eth, df_eth["open_time"].min(), vcp.CORTE),
        ("ETH ajuste (2021-2023)", df_eth, vcp.CORTE, vcp.CORTE_AJUSTE_FIN),
        ("ETH tiempo (2023-2025, nunca visto)", df_eth, vcp.CORTE_AJUSTE_FIN, vcp.CORTE_DESARROLLO_FIN),
        ("BTC completo (moneda nunca vista)", df_btc, vcp.CORTE, vcp.CORTE_DESARROLLO_FIN),
    ]

    for nombre, df, desde, hasta in cortes:
        print(f"=== {nombre} ===")
        filas = _candidatos_confirmados_combinado(df, mejor_pesos)
        ambas = [f for f in filas if f["ambas"]]
        solo_regimen = [f for f in filas if f["debajo_y_cayendo"] and not f["zona_testeada"]]
        resto = [f for f in filas if not f["debajo_y_cayendo"]]
        r_ambas = _resumen_segmento(df, ambas, desde, hasta)
        r_solo_regimen = _resumen_segmento(df, solo_regimen, desde, hasta)
        r_resto = _resumen_segmento(df, resto, desde, hasta)
        print(f"  AMBAS condiciones (regimen debil + zona testeada): {json.dumps(r_ambas, default=str)}")
        print(f"  solo regimen debil (sin zona testeada): {json.dumps(r_solo_regimen, default=str)}")
        print(f"  resto (regimen fuerte/neutro): {json.dumps(r_resto, default=str)}")

        filas_planas = [(f["idx_techo2"], f["idx_confirmacion"]) for f in ambas]
        retornos = mc._retornos_confirmados(df, filas_planas, desde, hasta)
        if retornos and len(retornos) >= 3:
            res_mc = mc.monte_carlo(df, desde, hasta, retornos, exito_es_subida=False, rng=rng)
            print(f"  Monte Carlo (ambas, n={len(retornos)}): p_valor_retorno={res_mc['p_valor_retorno']}, "
                  f"p_valor_acierto_rango={res_mc['p_valor_acierto_rango']}")
        print()
