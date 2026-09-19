"""
Idea pendiente desde el 14-sept-2026 (README de salidas/, "Ideas
pendientes" #1): el trailing simple ya se probo y salio uniformemente
peor -- pero el caso real que lo motivo (ETH, corto del 02-ene-2024:
entra a 2355.34, baja a 2209.72 el 03-ene -- ya un 6.2% a favor -- y
nadie protege esa ganancia; el precio se da la vuelta y para el stop el
10-ene a 2584.38, -10.08%) no se resuelve solo con "no usar trailing".
Hipotesis: el trailing simple fallaba porque reacciona a CUALQUIER avance,
por pequeno, y eso tightea el stop demasiado pronto en operaciones que
solo tenian ruido normal, no una ganancia real que proteger. Se prueba
aqui la variante con "colchon minimo": el trailing no empieza a moverse
hasta que el precio ya avanzo al menos `cushion_pct_minimo` a favor.

Metrica y disciplina identicas a barrido_trailing.py: EXCESO sobre
comprar-y-aguantar el mismo numero de dias (observacion 0011), barrido
en ETH, confirmacion en BTC sin retocar nada, sin senal contraria ni
racha (una idea a la vez).
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.comparacion_salida_fija_vs_dinamica import _candidatos
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45  # config de salidas/ ya aceptada
K_ATR_TRAILING_GRID = [0.75, 1.0, 1.5, 2.0, 2.5, 3.5, 5.0, 7.0]
CUSHION_GRID = [0.02, 0.03, 0.05, 0.07, 0.10]


def _excesos(df, candidatos, atr, k_atr_trailing, cushion):
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
                               atr_valor=atr[idx], k_atr_trailing=k_atr_trailing,
                               cushion_pct_minimo=cushion)
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
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_trailing_colchon")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_trailing_colchon")

    print("=== ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    base_eth = _resumen(_excesos(eth, cand_eth, atr_eth, None, None))
    print(f"SIN trailing (base): {base_eth}")

    resultados = []
    for k in K_ATR_TRAILING_GRID:
        for c in CUSHION_GRID:
            r = _resumen(_excesos(eth, cand_eth, atr_eth, k, c))
            resultados.append({"k_atr_trailing": k, "cushion_pct_minimo": c, **r})

    resultados.sort(key=lambda r: -r["exceso_medio"])
    print("\nTop 8 configs (k_atr_trailing, cushion_pct_minimo):")
    for r in resultados[:8]:
        print(" ", r)

    mejor = resultados[0]
    en_borde_k = mejor["k_atr_trailing"] in (min(K_ATR_TRAILING_GRID), max(K_ATR_TRAILING_GRID))
    en_borde_c = mejor["cushion_pct_minimo"] in (min(CUSHION_GRID), max(CUSHION_GRID))
    print(f"mejor: {mejor} -- k {'EN EL BORDE' if en_borde_k else 'dentro'}, cushion {'EN EL BORDE' if en_borde_c else 'dentro'}")

    print("\n=== BTC (confirmacion, sin tocar la config ganadora de ETH) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    base_btc = _resumen(_excesos(btc, cand_btc, atr_btc, None, None))
    ganador_btc = _resumen(_excesos(btc, cand_btc, atr_btc, mejor["k_atr_trailing"], mejor["cushion_pct_minimo"]))
    print(f"SIN trailing (base) en BTC: {base_btc}")
    print(f"config ganadora de ETH en BTC: {ganador_btc}")


if __name__ == "__main__":
    main()
