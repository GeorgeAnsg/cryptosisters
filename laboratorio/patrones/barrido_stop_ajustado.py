"""
El usuario notó (14-sept-2026, revisando el grafico ETH 2024 caso a caso)
que el stop mediano esta al 12.2% de la entrada y el objetivo al 36.5% --
enorme para una vela diaria. Eso explica por que ganancias intermedias
reales (+6%, +15%) nunca se protegen: ni se acercan al objetivo lejano, y
cuando el precio se da la vuelta, se recorre TODA esa distancia hasta el
stop, convirtiendo una ganancia en una perdida de doble digito.

Se prueba un stop/objetivo bastante mas ajustado (k_atr_stop y R_fijo mas
pequeños) para ver si reduce este problema, midiendo con la metrica
correcta (exceso sobre comprar-y-aguantar, observacion 0011) -- no se
asume que "mas ajustado" sea mejor, se compara.

Validacion cruzada de siempre: ETH ajusta, BTC confirma.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.comparacion_salida_fija_vs_dinamica import _candidatos
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

DIAS_MAXIMO = 45  # sin tocar, no es el foco de esta prueba

# la config actual (2.5, 3.0) da stop~12%/objetivo~36% de mediana -- se prueban
# combinaciones bastante mas ajustadas para ver si eso, medido bien, ayuda
K_ATR_STOP_GRID = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5]
R_FIJO_GRID = [0.75, 1.0, 1.5, 2.0, 2.5, 3.0]


def _excesos(df, candidatos, atr, k_atr_stop, r_fijo):
    close = df["close"].to_numpy()
    excesos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, k_atr_stop, r_fijo)
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO)
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
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_stop_ajustado")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_stop_ajustado")

    print("=== ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)

    resultados = []
    for k in K_ATR_STOP_GRID:
        for r in R_FIJO_GRID:
            ret = _excesos(eth, cand_eth, atr_eth, k, r)
            resultados.append({"k_atr_stop": k, "r_fijo": r, **_resumen(ret)})

    resultados.sort(key=lambda r: -r["exceso_medio"])
    print("Top 8 configs por exceso medio:")
    for r in resultados[:8]:
        print(" ", r)

    base = next(r for r in resultados if r["k_atr_stop"] == 2.5 and r["r_fijo"] == 3.0)
    print(f"\nconfig actual (2.5, 3.0): {base}")

    mejor = resultados[0]
    en_borde_k = mejor["k_atr_stop"] in (min(K_ATR_STOP_GRID), max(K_ATR_STOP_GRID))
    en_borde_r = mejor["r_fijo"] in (min(R_FIJO_GRID), max(R_FIJO_GRID))
    print(f"mejor: {mejor} -- k {'EN EL BORDE' if en_borde_k else 'dentro'}, r {'EN EL BORDE' if en_borde_r else 'dentro'}")

    print("\n=== BTC (confirmacion, sin tocar la config ganadora de ETH) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    base_btc = _resumen(_excesos(btc, cand_btc, atr_btc, 2.5, 3.0))
    ganador_btc = _resumen(_excesos(btc, cand_btc, atr_btc, mejor["k_atr_stop"], mejor["r_fijo"]))
    print(f"config actual (2.5, 3.0) en BTC: {base_btc}")
    print(f"config ganadora de ETH ({mejor['k_atr_stop']}, {mejor['r_fijo']}) en BTC: {ganador_btc}")


if __name__ == "__main__":
    main()
