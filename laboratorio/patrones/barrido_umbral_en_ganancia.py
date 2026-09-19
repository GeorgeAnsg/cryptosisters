"""
Idea (1) del usuario, 14-sept-2026, tras ver el caso real del +17% que
termino en -1.8%: una vez que la operacion YA VA GANANDO, no hace falta
una señal de patron contrario tan exigente (0.7) para plantearse cerrar y
proteger lo conseguido -- basta con un umbral mas bajo. Se prueba con
`umbral_contraria_en_ganancia` (nuevo parametro de
`salidas/stop_objetivo.py::simular_trade`), SOLO esta idea, sin trailing
(aparcado, empeoraba) y sin tocar `probabilidad_en_vivo` (esa es la idea
(2), se prueba por separado).

Base: probabilidad del dia 0 (`probabilidad_total_si_confirma`, la misma
que ya usa la señal contraria aceptada), umbral normal = 0.7 (ya validado).
Se barre `umbral_contraria_en_ganancia` de 0.7 hacia abajo -- 0.7 mismo es
el caso "sin cambio" (equivalente a la config actual).

Metrica: exceso sobre comprar-y-aguantar el mismo periodo (leccion de la
observacion 0011). Validacion cruzada de siempre: ETH ajusta, BTC confirma.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_señales_salida import _candidatos, _prob_contraria
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45
UMBRAL_NORMAL = 0.7
UMBRAL_EN_GANANCIA_GRID = [0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]  # 0.7 = sin cambio (base)


def _excesos(df, candidatos, atr, prob_corto, prob_largo, umbral_en_ganancia):
    close = df["close"].to_numpy()
    excesos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        prob_arr = prob_corto if direccion == "corto" else prob_largo
        prob_arr = np.nan_to_num(prob_arr, nan=-1.0)  # NaN (no es max/min aparente) nunca dispara
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                           prob_contraria=prob_arr, umbral_contraria=UMBRAL_NORMAL,
                           umbral_contraria_en_ganancia=umbral_en_ganancia)
        if t is None:
            continue
        signo = 1 if direccion == "largo" else -1
        retorno_benchmark = (close[t.idx_salida] - close[t.idx_entrada]) / close[t.idx_entrada] * 100 * signo
        excesos.append(t.retorno_pct - retorno_benchmark)
    return excesos


def _resumen(excesos):
    arr = np.array(excesos)
    return {"n": len(arr), "exceso_medio": round(float(arr.mean()), 3),
            "exceso_mediana": round(float(np.median(arr)), 3)}


def main():
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_umbral_en_ganancia")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_umbral_en_ganancia")

    print("=== ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    prob_corto_eth, prob_largo_eth = _prob_contraria(eth)

    resultados = []
    for u in UMBRAL_EN_GANANCIA_GRID:
        r = _resumen(_excesos(eth, cand_eth, atr_eth, prob_corto_eth, prob_largo_eth, u))
        resultados.append({"umbral_en_ganancia": u, **r})
        print(f"  umbral_en_ganancia={u}: {r}")

    base = next(r for r in resultados if r["umbral_en_ganancia"] == UMBRAL_NORMAL)
    mejor = max(resultados, key=lambda r: r["exceso_medio"])
    en_borde = mejor["umbral_en_ganancia"] in (min(UMBRAL_EN_GANANCIA_GRID), max(UMBRAL_EN_GANANCIA_GRID))
    print(f"\nbase (sin cambio, umbral=0.7): {base}")
    print(f"mejor: {mejor} -- {'EN EL BORDE' if en_borde else 'dentro del rango'}")

    print("\n=== BTC (confirmacion, sin tocar el umbral ganador de ETH) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    prob_corto_btc, prob_largo_btc = _prob_contraria(btc)
    base_btc = _resumen(_excesos(btc, cand_btc, atr_btc, prob_corto_btc, prob_largo_btc, UMBRAL_NORMAL))
    ganador_btc = _resumen(_excesos(btc, cand_btc, atr_btc, prob_corto_btc, prob_largo_btc, mejor["umbral_en_ganancia"]))
    print(f"base en BTC: {base_btc}")
    print(f"umbral_en_ganancia={mejor['umbral_en_ganancia']} (ganador de ETH) en BTC: {ganador_btc}")


if __name__ == "__main__":
    main()
