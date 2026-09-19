"""
Dos factores nuevos pedidos por el usuario (11-sept-2026), probados DENTRO
del subgrupo ya validado (regimen de mercado debil: precio bajo media 200
Y cayendo) -- no solos, porque ya se vio hoy que una pista debil por
separado puede restar en vez de sumar al combinarse a ciegas.

1. RSI en SOBRECOMPRA ABSOLUTA en techo2 (rsi_techo2 > umbral) -- distinto
   de la divergencia RSI ya probada y descartada (esta mira el NIVEL, no
   la comparacion entre techo1 y techo2).
2. Patron de doble techo COMPLETO previo en el mismo nivel de precio (no
   solo un pico suelto, que ya se probo y salio debil) -- se busca si
   existe otro candidato de doble techo ANTERIOR (su techo2 ya paso) cuyo
   nivel de precio coincida con el nivel actual, con tolerancia.
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

RSI_SOBRECOMPRA = 65.0
TOLERANCIA_NIVEL_PATRON_PREVIO_PCT = 5.0


def _candidatos_confirmados_completo(df: pd.DataFrame, pesos: tuple) -> list[dict]:
    peso_nivel, peso_caida, peso_tiempo, peso_altura = pesos
    candidatos = doble_techo_flexible.detectar(
        df, peso_nivel=peso_nivel, peso_caida=peso_caida, peso_tiempo=peso_tiempo, peso_altura=peso_altura,
    )
    close_s = df["close"]
    close = close_s.to_numpy()
    sma200 = close_s.rolling(200).mean()
    n = len(df)

    # niveles de todos los dobles techo previos (para el factor 2) --
    # ordenados por idx_techo2, para poder mirar "solo los que ya pasaron"
    candidatos_ordenados = sorted(candidatos, key=lambda c: c.idx_techo2)
    niveles_previos: list[tuple[int, float]] = []  # (idx_techo2, nivel)

    filas = []
    for c in candidatos_ordenados:
        nivel_actual = (close[c.idx_techo1] + close[c.idx_techo2]) / 2

        # regimen (ya validado, base de todo este analisis)
        media = sma200.iloc[c.idx_techo2]
        media_hace_20 = sma200.iloc[c.idx_techo2 - 20] if c.idx_techo2 >= 20 else None
        debajo_media = bool(media == media and close[c.idx_techo2] < media)
        media_cayendo = bool(
            media == media and media_hace_20 is not None and media_hace_20 == media_hace_20 and media < media_hace_20
        )
        debajo_y_cayendo = debajo_media and media_cayendo

        # factor 1: RSI sobrecompra absoluto en techo2
        rsi_sobrecompra = c.rsi_techo2 is not None and c.rsi_techo2 > RSI_SOBRECOMPRA

        # factor 2: hubo un doble techo COMPLETO previo (su techo2 ya paso,
        # con margen de los 3 dias de confirmacion del pico) en el mismo nivel
        patron_previo_mismo_nivel = any(
            idx2_prev < c.idx_techo1 - 3
            and abs(nivel_prev - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2_prev, nivel_prev in niveles_previos
        )
        niveles_previos.append((c.idx_techo2, nivel_actual))

        minimo_intermedio = close_s.iloc[c.idx_techo1: c.idx_techo2 + 1].min()
        fin_conf = min(c.idx_techo2 + 1 + vcp.DIAS_CONFIRMACION, n)
        tramo_conf = close_s.iloc[c.idx_techo2 + 1: fin_conf]
        cruces = tramo_conf.index[tramo_conf < minimo_intermedio]
        idx_confirmacion = int(cruces[0]) if len(cruces) > 0 else None

        filas.append({
            "idx_techo2": c.idx_techo2, "idx_confirmacion": idx_confirmacion,
            "debajo_y_cayendo": debajo_y_cayendo, "rsi_sobrecompra": rsi_sobrecompra,
            "patron_previo_mismo_nivel": patron_previo_mismo_nivel,
        })
    return filas


def _resumen_segmento(df: pd.DataFrame, filas: list[dict], desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    filas_planas = [(f["idx_techo2"], f["idx_confirmacion"]) for f in filas]
    return vcp._resumen(df, filas_planas, desde, hasta, exito_es_subida=False)["con_confirmacion"]


if __name__ == "__main__":
    import json

    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="segmentacion_rsi_patron_previo_techo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="segmentacion_rsi_patron_previo_techo_btc")

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
        filas = _candidatos_confirmados_completo(df, mejor_pesos)
        base = [f for f in filas if f["debajo_y_cayendo"]]  # el subgrupo ya validado
        print(f"  [base: regimen debil solo, n={len(base)}]: {json.dumps(_resumen_segmento(df, base, desde, hasta), default=str)}")

        con_rsi = [f for f in base if f["rsi_sobrecompra"]]
        sin_rsi = [f for f in base if not f["rsi_sobrecompra"]]
        print(f"  regimen + RSI sobrecompra (n={len(con_rsi)}): {json.dumps(_resumen_segmento(df, con_rsi, desde, hasta), default=str)}")
        print(f"  regimen + RSI normal (n={len(sin_rsi)}): {json.dumps(_resumen_segmento(df, sin_rsi, desde, hasta), default=str)}")

        con_patron = [f for f in base if f["patron_previo_mismo_nivel"]]
        sin_patron = [f for f in base if not f["patron_previo_mismo_nivel"]]
        print(f"  regimen + patron previo mismo nivel (n={len(con_patron)}): {json.dumps(_resumen_segmento(df, con_patron, desde, hasta), default=str)}")
        print(f"  regimen + sin patron previo (n={len(sin_patron)}): {json.dumps(_resumen_segmento(df, sin_patron, desde, hasta), default=str)}")
        print()
