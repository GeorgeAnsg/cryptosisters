"""
Trailing stop combinado con el grid -- idea del usuario ("compensar
poniendo el stop mas abajo para ganar mas en la subida"). grid_adaptativo.py
YA tiene dos mecanismos de este tipo, construidos antes pero nunca
probados con la config ganadora actual (k_atr_objetivo_mult=1.5):

1. interruptor_tendencia: mientras hay tendencia alcista fuerte (ADX+DI),
   NO vende en el nivel fijo -- deja correr con un trailing de
   k_atr_trailing x ATR por detras del maximo. Vende solo si el precio cae
   por debajo del trailing (o si la tendencia deja de estar confirmada).

2. salida_parcial: en CADA nivel, cierra una fraccion (fraccion_parcial) en
   el take-profit normal (beneficio asegurado) y deja el resto corriendo
   con trailing (k_atr_trailing_parcial x ATR), sin depender de si hay
   tendencia confirmada.

Barrido en BTC y ETH (9 años), comparando contra el baseline actual
(objetivo_mult=1.5, sin trailing) que es lo que corre en produccion/paper
trading ahora mismo.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from datos.cargar import cargar_ohlcv
from laboratorio.grid_adaptativo import simular, evaluar_capital

BASE = dict(
    n_niveles=3, k_atr_espaciado=0.5, k_atr_espaciado_tendencia=1.5,
    k_atr_objetivo_mult=1.5, espaciado_dinamico=True,
    velas_recentrado=180, stop_bajo_rejilla=2.0,
)


def evaluar(df, config):
    res = simular(df, **config)
    capital, drawdown = evaluar_capital(res, config["n_niveles"])
    calmar = (capital - 100) / abs(drawdown) if drawdown != 0 else float("nan")
    return capital, drawdown, calmar, len(res.trades)


def main():
    btc = cargar_ohlcv("BTCUSDT", "4h")
    eth = cargar_ohlcv("ETHUSDT", "4h")

    print("=== BASELINE (sin trailing, config actual de produccion) ===")
    for nombre, df in [("BTC", btc), ("ETH", eth)]:
        cap, dd, cal, n = evaluar(df, BASE)
        print(f"{nombre}: capital={cap:.1f} dd={dd:.2f}% Calmar={cal:.1f} trades={n}")

    print()
    print("=== interruptor_tendencia (trailing durante tendencia confirmada) ===")
    for k_trail in [1.5, 2.0, 3.0, 4.0]:
        config = dict(BASE, interruptor_tendencia=True, k_atr_trailing=k_trail)
        for nombre, df in [("BTC", btc), ("ETH", eth)]:
            cap, dd, cal, n = evaluar(df, config)
            print(f"k_atr_trailing={k_trail} {nombre}: capital={cap:.1f} dd={dd:.2f}% Calmar={cal:.1f} trades={n}")

    print()
    print("=== salida_parcial (asegura fraccion, deja correr el resto con trailing) ===")
    for frac in [0.3, 0.5, 0.7]:
        for k_trail_parcial in [1.5, 2.0, 3.0]:
            config = dict(BASE, salida_parcial=True, fraccion_parcial=frac, k_atr_trailing_parcial=k_trail_parcial)
            for nombre, df in [("BTC", btc), ("ETH", eth)]:
                cap, dd, cal, n = evaluar(df, config)
                print(f"frac={frac} k_trail_parcial={k_trail_parcial} {nombre}: capital={cap:.1f} dd={dd:.2f}% Calmar={cal:.1f} trades={n}")


if __name__ == "__main__":
    main()
