"""
Cross-validacion del ajuste hecho para oro (PAXG, 4h) en plata y platino --
pregunta directa del usuario: si el patron encontrado en oro (espaciado mas
fino, casi sin ensanchar en tendencia) es real, deberia repetirse en otros
metales preciosos con dinamica de precio parecida, no ser un accidente de
una sola serie.

No existe token cripto de plata/platino en Binance (comprobado via
exchangeInfo) -- se usan futuros reales de Yahoo Finance (SI=F plata, PL=F
platino, GC=F oro real como referencia adicional a PAXG), diarios, ultimos
10 años. Mismo barrido de parametros que se hizo para oro/1d, aplicado por
separado a cada metal -- sin mirar los resultados de uno para elegir los
parametros de otro (eso seria la misma trampa de sobreajuste que se quiere
evitar).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import pandas as pd

from laboratorio.grid_adaptativo import simular, evaluar_capital

COLUMNAS_NUMERICAS = ["open", "high", "low", "close", "volume"]


def cargar_yahoo(nombre_archivo: str) -> pd.DataFrame:
    df = pd.read_csv(f"/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/{nombre_archivo}")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in COLUMNAS_NUMERICAS:
        df[c] = df[c].astype(float)
    return df.sort_values("open_time").reset_index(drop=True)


def barrer(df: pd.DataFrame, velas_recentrado: int = 30) -> pd.DataFrame:
    n_anos = (df["open_time"].iloc[-1] - df["open_time"].iloc[0]).days / 365.25
    filas = []
    for k_esp in [0.3, 0.5, 0.7, 1.0]:
        for k_tend in [0.5, 1.0, 1.5, 2.0]:
            if k_tend < k_esp:
                continue
            for obj in [1.0, 1.5, 2.0, 2.5, 3.0]:
                res = simular(df, n_niveles=3, k_atr_espaciado=k_esp, k_atr_espaciado_tendencia=k_tend,
                              k_atr_objetivo_mult=obj, espaciado_dinamico=True,
                              velas_recentrado=velas_recentrado, stop_bajo_rejilla=2.0)
                capital, dd = evaluar_capital(res, 3)
                calmar = (capital - 100) / abs(dd) if dd != 0 else float("nan")
                filas.append(dict(k_esp=k_esp, k_tend=k_tend, obj=obj, capital=capital, dd=dd,
                                   calmar=calmar, n_trades=len(res.trades), trades_ano=len(res.trades) / n_anos))
    return pd.DataFrame(filas)


def main():
    activos = [
        ("XAUUSD_1d_yahoo_futures.csv", "Oro (futuro real GC=F)"),
        ("XAGUSD_1d_yahoo_futures.csv", "Plata (futuro real SI=F)"),
        ("XPTUSD_1d_yahoo_futures.csv", "Platino (futuro real PL=F)"),
    ]
    for archivo, nombre in activos:
        df = cargar_yahoo(archivo)
        print(f"\n=== {nombre}: {len(df)} velas diarias, {(df['open_time'].iloc[-1]-df['open_time'].iloc[0]).days} dias ===")
        tabla = barrer(df)
        print("-- Top 5 por Calmar --")
        print(tabla.sort_values("calmar", ascending=False).head(5).to_string(index=False))
        print("-- Config genérica BTC/ETH (0.5/1.5/1.5) para referencia --")
        gen = tabla[(tabla.k_esp == 0.5) & (tabla.k_tend == 1.5) & (tabla.obj == 1.5)]
        print(gen.to_string(index=False))


if __name__ == "__main__":
    main()
