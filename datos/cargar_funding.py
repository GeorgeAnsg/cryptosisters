"""Carga el funding rate de BTCUSDT y lo fusiona sobre un df de precio ya
cargado con datos.cargar.cargar_ohlcv -- fusion causal (asof hacia atras,
nunca mira un valor de funding publicado despues de la vela)."""
from __future__ import annotations

import pandas as pd


def cargar_funding(ruta: str = "datos/crudo/BTCUSDT_funding_binance.csv") -> pd.DataFrame:
    f = pd.read_csv(ruta)
    f["calc_time"] = pd.to_datetime(f["calc_time"], unit="ms", utc=True)
    f = f.drop_duplicates(subset="calc_time").sort_values("calc_time").reset_index(drop=True)
    f = f.rename(columns={"last_funding_rate": "funding"})
    return f[["calc_time", "funding"]]


def fusionar_funding(df_precio: pd.DataFrame, df_funding: pd.DataFrame) -> pd.DataFrame:
    df = df_precio.sort_values("open_time").reset_index(drop=True)
    fu = df_funding.sort_values("calc_time").reset_index(drop=True)
    fusion = pd.merge_asof(df, fu, left_on="open_time", right_on="calc_time", direction="backward")
    return fusion
