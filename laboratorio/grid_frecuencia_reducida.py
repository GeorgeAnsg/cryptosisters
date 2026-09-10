"""
Grid con objetivo de FRECUENCIA ACOTADA, no capital maximo -- propuesto por
mi tras la pregunta del usuario "como hago que el grid de pocas operaciones
para poder ejecutarlo a mano". Todos los sweeps anteriores de grid_adaptativo
(grid_combinaciones2/3) optimizaban capital final total; nunca se habia
mirado que config gana si el objetivo es "trades/año bajo, buen retorno por
operacion" en vez de "capital final maximo". Es una pregunta distinta y
puede tener una respuesta distinta.

Mecanismo probado: ensanchar el espaciado de la rejilla (k_atr_espaciado,
k_atr_espaciado_tendencia) para que cada nivel represente un movimiento mas
grande -- menos niveles se tocan por año, pero cada toque es una oscilacion
mas amplia. Se mide capital, drawdown, Calmar, trades/año Y retorno medio
por operacion (ponderado por capital comprometido, via evaluar_capital).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import pandas as pd

from datos.cargar import cargar_ohlcv
from laboratorio.grid_adaptativo import simular, evaluar_capital

CONFIG_BASE = dict(
    n_niveles=3,
    espaciado_dinamico=True,
    velas_recentrado=180,
    stop_bajo_rejilla=2.0,
)

# factor de ensanchado sobre el espaciado ganador conocido (0.5 / 1.5)
FACTORES = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]


def evaluar(df: pd.DataFrame, factor: float) -> dict:
    k_lateral = 0.5 * factor
    k_tendencia = 1.5 * factor
    res = simular(
        df,
        k_atr_espaciado=k_lateral,
        k_atr_espaciado_tendencia=k_tendencia,
        **CONFIG_BASE,
    )
    capital, drawdown = evaluar_capital(res, CONFIG_BASE["n_niveles"])
    n_trades = len(res.trades)
    n_anos = (df["open_time"].iloc[-1] - df["open_time"].iloc[0]).days / 365.25
    trades_ano = n_trades / n_anos if n_anos > 0 else float("nan")
    calmar = (capital - 100) / abs(drawdown) if drawdown != 0 else float("nan")
    # retorno medio por operacion, ponderado por el capital realmente
    # comprometido en cada trade (no la media simple de retorno_pct)
    if res.trades:
        pesos = [t.peso_fraccion for t in res.trades]
        retorno_ponderado = sum(t.retorno_pct * p for t, p in zip(res.trades, pesos)) / sum(pesos)
    else:
        retorno_ponderado = float("nan")
    return dict(
        factor=factor, capital=capital, drawdown=drawdown, calmar=calmar,
        n_trades=n_trades, trades_ano=trades_ano, retorno_medio_trade=retorno_ponderado,
    )


def main():
    for par in ["BTCUSDT", "ETHUSDT"]:
        df = cargar_ohlcv(par, "4h", ruta_base="/Users/jorgeansotegui/Desktop/corvus4/datos/crudo")
        print(f"\n=== {par} 4h ({len(df)} velas, {(df['open_time'].iloc[-1]-df['open_time'].iloc[0]).days} dias) ===")
        print(f"{'factor':>6} {'capital':>9} {'drawdown':>9} {'calmar':>8} {'n_trades':>9} {'trades/año':>11} {'ret_medio/trade%':>17}")
        for factor in FACTORES:
            r = evaluar(df, factor)
            print(f"{r['factor']:6.1f} {r['capital']:9.1f} {r['drawdown']:9.1f} {r['calmar']:8.1f} "
                  f"{r['n_trades']:9d} {r['trades_ano']:11.1f} {r['retorno_medio_trade']:17.3f}")


if __name__ == "__main__":
    main()
