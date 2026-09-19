"""15-sept-2026: idea del usuario -- usar la deteccion de canal (ya
graduada como motores/canal_ascendente.py y canal_descendente.py) no como
motor de entrada propio (ya se probo hoy y su ventaja "dia 0" no existe,
ver canal_forma_sola_excedente_benchmark.py), sino como SEÑAL DE SALIDA
para operaciones YA ABIERTAS por doble suelo / doble techo -- "si estoy
largo por un doble suelo y se forma un canal descendente EN CONTRA que
confirma la ruptura, corto ahi en vez de esperar al stop/objetivo de ATR".

Mismo arnes y disciplina exactos que las señales de salida ya probadas
(`laboratorio/patrones/barrido_señales_salida.py`, ver
`salidas/README.md`): config moderada fija (k_atr_stop=2.5, r_fijo=3.0,
dias_maximo=45) para aislar el efecto de la señal nueva; metrica =
retorno medio POR OPERACION AISLADA (observacion 0010 de task-observer:
el capital de una cuenta secuencial mezcla calidad de la salida con
cuantas operaciones caben, hay que medir aislado); barrido de umbral en
ETH (ajuste), confirmacion en BTC sin retocar nada. Regla explicita del
usuario (15-sept-2026): SIEMPRE comparar contra la base ya validada (sin
esta señal) -- no basta con que la señal "haga algo", tiene que MEJORAR
el resultado que ya se tenia.

Señal: para un largo (doble suelo), señal_externa[i] = True si un canal
DESCENDENTE (motores/canal_descendente.py) confirma su ruptura justo ese
dia (`idx_confirmacion == i`) con probabilidad_forma >= umbral -- un
canal descendente confirmado es precisamente el contexto que hoy se
demostro que predice caidas reales, justo lo contrario de lo que quiere
un largo. Espejo para un corto (doble techo): canal ASCENDENTE.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from laboratorio.datos_lab import cargar_ohlcv_lab
from motores import canal_ascendente, canal_descendente
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45  # config moderada, igual que barrido_señales_salida.py
UMBRAL_PROB_CANAL_GRID = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def _candidatos(df):
    out = []
    for c in techo_motor.detectar(df):
        r = en_vivo_techo(df, c.idx_techo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_techo2, "corto", r.probabilidad_total_si_confirma))
    for c in suelo_motor.detectar(df):
        r = en_vivo_suelo(df, c.idx_fondo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_fondo2, "largo", r.probabilidad_total_si_confirma))
    return out


def _senal_canal_en_contra(df) -> tuple[np.ndarray, np.ndarray]:
    """(prob_en_contra_largo, prob_en_contra_corto) -- por dia, la
    probabilidad_forma del canal EN CONTRA que confirma ESE dia (NaN si
    ninguno confirma). Un largo sufre un canal descendente confirmado; un
    corto sufre un canal ascendente confirmado."""
    n = len(df)
    prob_en_contra_largo = np.full(n, np.nan)
    prob_en_contra_corto = np.full(n, np.nan)
    for c in canal_descendente.calcular(df):
        if c.confirmado:
            prob_en_contra_largo[c.idx_confirmacion] = max(
                prob_en_contra_largo[c.idx_confirmacion] if not np.isnan(prob_en_contra_largo[c.idx_confirmacion]) else -1,
                c.probabilidad_forma,
            )
    for c in canal_ascendente.calcular(df):
        if c.confirmado:
            prob_en_contra_corto[c.idx_confirmacion] = max(
                prob_en_contra_corto[c.idx_confirmacion] if not np.isnan(prob_en_contra_corto[c.idx_confirmacion]) else -1,
                c.probabilidad_forma,
            )
    return prob_en_contra_largo, prob_en_contra_corto


def _retornos_base(df, candidatos, atr):
    close = df["close"].to_numpy()
    retornos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO)
        if t is not None:
            retornos.append(t.retorno_pct)
    return retornos


def _barrer_canal(df, candidatos, atr, prob_en_contra_largo, prob_en_contra_corto):
    close = df["close"].to_numpy()
    resultados = []
    for umbral in UMBRAL_PROB_CANAL_GRID:
        senal_largo = np.nan_to_num(prob_en_contra_largo, nan=-1) >= umbral
        senal_corto = np.nan_to_num(prob_en_contra_corto, nan=-1) >= umbral
        retornos = []
        for idx, direccion, _prob in candidatos:
            if np.isnan(atr[idx]):
                continue
            senal = senal_largo if direccion == "largo" else senal_corto
            niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
            t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
            if t is not None:
                retornos.append(t.retorno_pct)
        resultados.append({"umbral_prob_canal": umbral, "n": len(retornos),
                            "retorno_medio": round(float(np.mean(retornos)), 3)})
    return resultados


def main():
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_senal_salida_eth")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_senal_salida_btc")

    print("=== BARRIDO EN ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    base_eth = np.mean(_retornos_base(eth, cand_eth, atr_eth))
    print(f"candidatos ETH: {len(cand_eth)} -- BASE (sin señal de canal): retorno_medio={base_eth:.3f}%")

    prob_largo_eth, prob_corto_eth = _senal_canal_en_contra(eth)
    resultados_eth = _barrer_canal(eth, cand_eth, atr_eth, prob_largo_eth, prob_corto_eth)
    print("\nSeñal 'canal en contra confirmado', por umbral de probabilidad_forma:")
    for r in resultados_eth:
        print(" ", r, "-- MEJORA" if r["retorno_medio"] > base_eth else "-- empeora")
    mejor = max(resultados_eth, key=lambda r: r["retorno_medio"])
    en_borde = mejor["umbral_prob_canal"] in (min(UMBRAL_PROB_CANAL_GRID), max(UMBRAL_PROB_CANAL_GRID))
    print(f"  mejor: {mejor} vs base {base_eth:.3f}% -- {'EN EL BORDE, sospechoso' if en_borde else 'dentro del rango'}")

    print("\n=== CONFIRMACION EN BTC (umbral congelado de ETH, sin retocar) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    base_btc = np.mean(_retornos_base(btc, cand_btc, atr_btc))
    print(f"candidatos BTC: {len(cand_btc)} -- BASE (sin señal de canal): retorno_medio={base_btc:.3f}%")

    prob_largo_btc, prob_corto_btc = _senal_canal_en_contra(btc)
    close_btc = btc["close"].to_numpy()
    senal_largo_btc = np.nan_to_num(prob_largo_btc, nan=-1) >= mejor["umbral_prob_canal"]
    senal_corto_btc = np.nan_to_num(prob_corto_btc, nan=-1) >= mejor["umbral_prob_canal"]
    ret_btc = []
    for idx, direccion, _p in cand_btc:
        if np.isnan(atr_btc[idx]):
            continue
        senal = senal_largo_btc if direccion == "largo" else senal_corto_btc
        niveles = calcular_niveles_fijos(close_btc[idx], atr_btc[idx], direccion, K_ATR_STOP, R_FIJO)
        t = simular_trade(btc, idx, direccion, close_btc[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is not None:
            ret_btc.append(t.retorno_pct)
    veredicto = "MEJORA sobre la base -- candidata seria" if np.mean(ret_btc) > base_btc else "NO mejora la base -- descartar"
    print(f"\nUmbral {mejor['umbral_prob_canal']} (de ETH) en BTC: retorno_medio={np.mean(ret_btc):.3f}% "
          f"(n={len(ret_btc)}) vs base BTC {base_btc:.3f}% -- {veredicto}")


if __name__ == "__main__":
    main()
