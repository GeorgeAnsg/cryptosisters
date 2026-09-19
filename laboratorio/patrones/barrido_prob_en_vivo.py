"""
Idea (2) del usuario, 14-sept-2026: en vez de decidir la señal de patron
contrario con la nota fija del dia 0 (`probabilidad_total_si_confirma`,
que nunca cambia), usar `probabilidad_en_vivo` -- la misma nota
multiplicada por la curva de supervivencia (aumenta si el maximo/minimo
aparente "aguanta" varios dias sin ser superado: dia 0 x0.31/0.39,
dia 1 x0.71/0.76, dia 2 x0.85/0.89, dia 3 x1.0). Motivo: un caso real
(largo del 19-marzo-2024, ETH) donde ningun candidato de patron contrario
llego nunca a 0.7 de nota fija durante toda la operacion -- quiza alguno SI
la habria alcanzado si se le diera la oportunidad de "confirmarse" con el
paso de los dias, en vez de evaluarse solo una vez el dia que aparece.

Se prueba SOLA esta idea (mismo umbral unico 0.7 para todos los dias, sin
la idea (1) del umbral mas bajo en ganancia, que ya se probo aparte y no
aporto nada medible).

Metrica: exceso sobre comprar-y-aguantar el mismo periodo (observacion
0011). Validacion cruzada de siempre: ETH ajusta, BTC confirma.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_señales_salida import _candidatos
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45
UMBRAL_GRID = [0.5, 0.6, 0.7, 0.8, 0.9]
DIA_MAX_CONFIRMACION = 3  # curva de supervivencia solo llega hasta el dia 3 (confirmado del todo)


def _serie_en_vivo(df, puntos_aparentes, en_vivo_fn):
    """prob_en_vivo[j] = la mejor probabilidad_en_vivo, entre todos los
    maximos/minimos aparentes que SIGUEN SIN SER SUPERADOS el dia j
    (0 <= dia_transcurrido <= 3), disponible ese dia j."""
    n = len(df)
    close = df["close"].to_numpy()
    prob = np.full(n, np.nan)
    for idx in puntos_aparentes:
        precio_extremo = close[idx]
        es_maximo = en_vivo_fn is en_vivo_techo
        for k in range(0, DIA_MAX_CONFIRMACION + 1):
            j = idx + k
            if j >= n:
                break
            if k > 0:
                ventana = close[idx + 1: j + 1]
                superado = ventana.max() > precio_extremo if es_maximo else ventana.min() < precio_extremo
                if superado:
                    break
            r = en_vivo_fn(df, idx, dia_transcurrido=k)
            if r is not None:
                prob[j] = r.probabilidad_en_vivo if np.isnan(prob[j]) else max(prob[j], r.probabilidad_en_vivo)
    return prob


def _prob_contraria_en_vivo(df):
    close = df["close"].to_numpy()
    prob_para_corto = _serie_en_vivo(df, minimos_aparentes(close), en_vivo_suelo)
    prob_para_largo = _serie_en_vivo(df, maximos_aparentes(close), en_vivo_techo)
    return prob_para_corto, prob_para_largo


def _excesos(df, candidatos, atr, prob_corto, prob_largo, umbral):
    close = df["close"].to_numpy()
    prob_corto_s = np.nan_to_num(prob_corto, nan=-1.0)
    prob_largo_s = np.nan_to_num(prob_largo, nan=-1.0)
    excesos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        prob_arr = prob_corto_s if direccion == "corto" else prob_largo_s
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                           prob_contraria=prob_arr, umbral_contraria=umbral)
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
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_prob_en_vivo")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_prob_en_vivo")

    print("=== ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    print("calculando probabilidad_en_vivo (dia 0-3) para todos los maximos/minimos aparentes...")
    prob_corto_eth, prob_largo_eth = _prob_contraria_en_vivo(eth)

    resultados = []
    for u in UMBRAL_GRID:
        r = _resumen(_excesos(eth, cand_eth, atr_eth, prob_corto_eth, prob_largo_eth, u))
        resultados.append({"umbral": u, **r})
        print(f"  umbral={u}: {r}")

    # comparacion directa con la base actual (dia 0, umbral 0.7) usando la señal ya validada
    from laboratorio.patrones.barrido_señales_salida import _prob_contraria as _prob_dia0
    prob_corto_dia0, prob_largo_dia0 = _prob_dia0(eth)
    base_dia0 = _resumen(_excesos(eth, cand_eth, atr_eth, prob_corto_dia0, prob_largo_dia0, 0.7))
    print(f"\nbase actual (dia 0 fijo, umbral 0.7): {base_dia0}")

    mejor = max(resultados, key=lambda r: r["exceso_medio"])
    en_borde = mejor["umbral"] in (min(UMBRAL_GRID), max(UMBRAL_GRID))
    print(f"mejor con probabilidad_en_vivo: {mejor} -- {'EN EL BORDE' if en_borde else 'dentro del rango'}")

    print("\n=== BTC (confirmacion, sin tocar el umbral ganador de ETH) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    prob_corto_btc, prob_largo_btc = _prob_contraria_en_vivo(btc)
    prob_corto_dia0_btc, prob_largo_dia0_btc = _prob_dia0(btc)
    base_btc = _resumen(_excesos(btc, cand_btc, atr_btc, prob_corto_dia0_btc, prob_largo_dia0_btc, 0.7))
    ganador_btc = _resumen(_excesos(btc, cand_btc, atr_btc, prob_corto_btc, prob_largo_btc, mejor["umbral"]))
    print(f"base actual (dia 0, umbral 0.7) en BTC: {base_btc}")
    print(f"probabilidad_en_vivo, umbral={mejor['umbral']} (ganador de ETH) en BTC: {ganador_btc}")


if __name__ == "__main__":
    main()
