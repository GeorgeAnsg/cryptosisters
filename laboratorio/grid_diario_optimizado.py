"""
Re-optimizar el grid ESPECIFICAMENTE para timeframe 1d, en vez de reusar sin
mas los parametros ganadores de 4h (que fueron ajustados para ese ruido y esa
escala de ATR). Barrido sobre espaciado lateral/tendencia y el nuevo
objetivo_mult, buscando recuperar Calmar sin perder la ventaja de frecuencia
baja que dio el cambio de timeframe.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import pandas as pd

from datos.cargar import cargar_ohlcv
from laboratorio.grid_adaptativo import simular, evaluar_capital

BASE = dict(n_niveles=3, espaciado_dinamico=True, velas_recentrado=30, stop_bajo_rejilla=2.0)

ESPACIADOS = [0.3, 0.5, 0.7, 1.0]
ESPACIADOS_TENDENCIA = [1.0, 1.5, 2.0]
OBJETIVOS = [1.0, 1.5, 2.0, 2.5, 3.0]


def metricas(df, res, n_niveles=3):
    capital, dd = evaluar_capital(res, n_niveles)
    n_trades = len(res.trades)
    n_anos = (df["open_time"].iloc[-1] - df["open_time"].iloc[0]).days / 365.25
    trades_ano = n_trades / n_anos if n_anos > 0 else float("nan")
    calmar = (capital - 100) / abs(dd) if dd != 0 else float("nan")
    return dict(capital=capital, drawdown=dd, calmar=calmar, n_trades=n_trades, trades_ano=trades_ano)


def main():
    for par in ["BTCUSDT", "ETHUSDT"]:
        df = cargar_ohlcv(par, "1d", ruta_base="/Users/jorgeansotegui/Desktop/corvus4/datos/crudo")
        filas = []
        for k_esp in ESPACIADOS:
            for k_tend in ESPACIADOS_TENDENCIA:
                if k_tend < k_esp:
                    continue
                for obj in OBJETIVOS:
                    res = simular(df, k_atr_espaciado=k_esp, k_atr_espaciado_tendencia=k_tend,
                                  k_atr_objetivo_mult=obj, **BASE)
                    m = metricas(df, res)
                    filas.append(dict(k_esp=k_esp, k_tend=k_tend, obj=obj, **m))
        tabla = pd.DataFrame(filas)
        print(f"\n=== {par} 1d -- top 10 por Calmar ===")
        print(tabla.sort_values("calmar", ascending=False).head(10).to_string(index=False))
        print(f"\n=== {par} 1d -- top 10 por Calmar CON trades/año <= 100 ===")
        sub = tabla[tabla["trades_ano"] <= 100]
        print(sub.sort_values("calmar", ascending=False).head(10).to_string(index=False))
        print(f"\n=== {par} 1d -- top 5 por Calmar CON trades/año <= 60 ===")
        sub2 = tabla[tabla["trades_ano"] <= 60]
        print(sub2.sort_values("calmar", ascending=False).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
