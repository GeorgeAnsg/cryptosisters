"""
Fear & Greed Index (alternative.me) -- dato diario de sentimiento agregado
(0=miedo extremo, 100=codicia extrema). Copiado sin modificar desde
~/Desktop/tr/data/fear_greed_historical.csv (mismo dato ya descargado para
otro proyecto, cobertura 2018-2026, sin huecos relevantes).
"""
from __future__ import annotations

import pandas as pd


def cargar_fear_greed(ruta: str = "datos/crudo/fear_greed_historical.csv") -> pd.DataFrame:
    df = pd.read_csv(ruta)
    df["open_time"] = pd.to_datetime(df["date"], format="%d-%m-%Y", utc=True)
    df = df.drop(columns="date").sort_values("open_time").reset_index(drop=True)
    df = df.rename(columns={"value": "fg_valor", "classification": "fg_clase"})
    return df


def fusionar_fear_greed(df_precio: pd.DataFrame, df_fg: pd.DataFrame) -> pd.DataFrame:
    """Fusión causal (backward): a cada vela de precio se le asigna el
    último valor de F&G PUBLICADO antes o en ese momento -- nunca uno
    futuro. El índice se publica una vez al día (00:00 UTC aprox.), así que
    una vela de 4h a las 04:00 usa el valor publicado a las 00:00 de ese
    mismo día, no el del día siguiente."""
    izq = df_precio.sort_values("open_time").copy()
    der = df_fg[["open_time", "fg_valor", "fg_clase"]].sort_values("open_time").copy()
    izq["open_time"] = izq["open_time"].astype("datetime64[us, UTC]")
    der["open_time"] = der["open_time"].astype("datetime64[us, UTC]")
    return pd.merge_asof(izq, der, on="open_time", direction="backward")
