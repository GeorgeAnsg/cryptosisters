"""
Prueba AISLADA del trailing stop (S2 del plan maestro, "Chandelier"),
añadido a `salidas/stop_objetivo.py` el 14-sept-2026 tras encontrar un caso
real (ETH, largo del 19-marzo-2024) que llego a +17% de ganancia flotante y
termino en -1.8% de perdida por no tener ningun mecanismo que protegiera
esa ganancia. Se prueba SOLO el trailing, sin la señal de patron contrario
ya aceptada -- disciplina de "una idea a la vez" del proyecto.

Metrica: EXCESO sobre comprar-y-aguantar el mismo numero de dias que la
operacion estuvo abierta (la misma correccion de la observacion 0011 --
sin esto, alargar/acortar el plazo de salida se confunde con la deriva de
mercado). Config de salidas/ ya aceptada como base: k_atr_stop=2.5,
r_fijo=3.0, dias_maximo=45. Se barre k_atr_trailing y se compara contra
"sin trailing" (equivalente a k_atr_trailing=None).

Validacion cruzada de siempre: barrido en ETH, confirmacion en BTC sin
retocar nada.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.comparacion_salida_fija_vs_dinamica import _candidatos
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45  # config de salidas/ ya aceptada
K_ATR_TRAILING_GRID = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]


def _excesos(df, candidatos, atr, k_atr_trailing):
    close = df["close"].to_numpy()
    excesos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        if k_atr_trailing is None:
            t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO)
        else:
            t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                               atr_valor=atr[idx], k_atr_trailing=k_atr_trailing)
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
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_trailing")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_trailing")

    print("=== ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    base_eth = _resumen(_excesos(eth, cand_eth, atr_eth, None))
    print(f"SIN trailing (base): {base_eth}")

    resultados = []
    for k in K_ATR_TRAILING_GRID:
        r = _resumen(_excesos(eth, cand_eth, atr_eth, k))
        resultados.append({"k_atr_trailing": k, **r})
        print(f"  k_atr_trailing={k}: {r}")

    mejor = max(resultados, key=lambda r: r["exceso_medio"])
    en_borde = mejor["k_atr_trailing"] in (min(K_ATR_TRAILING_GRID), max(K_ATR_TRAILING_GRID))
    print(f"mejor k_atr_trailing en ETH: {mejor} -- {'EN EL BORDE' if en_borde else 'dentro del rango'}")

    print("\n=== BTC (confirmacion, sin tocar el k_atr_trailing ganador) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    base_btc = _resumen(_excesos(btc, cand_btc, atr_btc, None))
    ganador_btc = _resumen(_excesos(btc, cand_btc, atr_btc, mejor["k_atr_trailing"]))
    print(f"SIN trailing (base) en BTC: {base_btc}")
    print(f"k_atr_trailing={mejor['k_atr_trailing']} (ganador de ETH) en BTC: {ganador_btc}")


if __name__ == "__main__":
    main()
