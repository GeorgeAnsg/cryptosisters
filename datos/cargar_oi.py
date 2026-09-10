"""
Open Interest agregado de BTC en derivados, 4h. Copiado sin modificar desde
~/Desktop/tr/data/oi_historical_4h.csv (dato ya descargado para otro
proyecto, cobertura dic-2020 a ago-2026, sin huecos ni duplicados).
"""
from __future__ import annotations

import pandas as pd


def cargar_oi(ruta: str = "datos/crudo/oi_historical_4h.csv") -> pd.DataFrame:
    df = pd.read_csv(ruta)
    df["open_time"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True).astype("datetime64[us, UTC]")
    df = df.drop(columns="timestamp_ms").sort_values("open_time").reset_index(drop=True)
    df = df.rename(columns={"open_interest": "oi"})
    return df


def fusionar_oi(df_precio: pd.DataFrame, df_oi: pd.DataFrame) -> pd.DataFrame:
    """Fusión causal (backward) -- ambos ya están en 4h, pero se usa
    merge_asof en vez de un merge directo por si hay desalineación de
    minutos entre los dos volcados (evita perder filas por un `merge`
    exacto que no encuentre coincidencia exacta de timestamp)."""
    izq = df_precio.sort_values("open_time").copy()
    izq["open_time"] = izq["open_time"].astype("datetime64[us, UTC]")
    return pd.merge_asof(izq, df_oi[["open_time", "oi"]], on="open_time", direction="backward")
