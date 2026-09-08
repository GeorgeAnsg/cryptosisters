"""
Punto único de carga de OHLCV crudo. Nadie más debería leer un CSV de
`datos/crudo/` directamente -- aquí se corrigen, en un solo sitio, los
defectos ya conocidos de los volcados de Binance:

1. Cambio de milisegundos a microsegundos en algunos volcados de 2025
   (ver `datos/descarga/auditoria.py::normaliza_ms`) -- sin esto, las velas
   de 2025 en adelante aparecen con una fecha absurda (año 58636 y similares).
2. Velas de 2018 desalineadas (open_time que no cae en el múltiplo exacto
   del timeframe, por las caídas de Binance ese año) -- documentado en
   `datos/catalogo.md`. Se filtran por defecto.
"""
from __future__ import annotations

import pandas as pd

_PASO_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def _normaliza_ms(v: int) -> int:
    v = int(v)
    return v // 1000 if v > 10**14 else v


def cargar_ohlcv(par: str, tf: str, desde_2019: bool = True, ruta_base: str = "datos/crudo") -> pd.DataFrame:
    """Carga un par+timeframe ya limpio y listo para usar.

    - par: p.ej. "BTCUSDT"
    - tf: p.ej. "4h", "1h", "15m", "1d"
    - desde_2019: si True (por defecto), descarta velas anteriores al
      2019-01-01 en 1h/15m para evitar las 43/81 velas desalineadas de 2018
      (ver datos/catalogo.md). No afecta a 1d/4h (limpios desde el inicio).

    Devuelve un df ordenado ascendente por open_time (datetime UTC), sin
    duplicados, con las columnas estándar de Binance.
    """
    ruta = f"{ruta_base}/{par}_{tf}_spot_binance.csv"
    df = pd.read_csv(ruta)
    ms_epoch = df["open_time"].apply(_normaliza_ms)
    df["open_time"] = pd.to_datetime(ms_epoch, unit="ms", utc=True)
    df["_ms_epoch"] = ms_epoch  # se guarda para el chequeo de alineación de abajo; se descarta al final
    df = df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)

    if desde_2019 and tf in ("1h", "15m"):
        df = df[df["open_time"] >= pd.Timestamp("2019-01-01", tz="UTC")].reset_index(drop=True)

    paso = _PASO_MS.get(tf)
    if paso is not None:
        desalineadas = df["_ms_epoch"] % paso != 0
        if desalineadas.any():
            df = df[~desalineadas].reset_index(drop=True)

    df = df.drop(columns="_ms_epoch")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)

    return df
