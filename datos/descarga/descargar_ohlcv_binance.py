"""
19-sept-2026: descarga generica de OHLCV publico de Binance, paginando
hacia atras con `endTime` hasta agotar el historial disponible -- pensado
para traer una moneda nueva (SOL, y potencialmente otras) al mismo
formato que ya usa `datos/cargar.py::cargar_ohlcv` (las 12 columnas
estandar de Binance, en `datos/crudo/{par}_{tf}_spot_binance.csv`), sin
inventar un formato nuevo.

No hace ninguna limpieza (eso ya lo hace `datos/cargar.py` al leer) --
solo pagina y guarda tal cual viene de la API.
"""
from __future__ import annotations

import sys
import time
import urllib.request
import json

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import pandas as pd

COLUMNAS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]


def descargar_historial_completo(par: str, intervalo: str = "1d", limite: int = 1000) -> pd.DataFrame:
    todas = []
    end_time = None
    while True:
        url = f"https://api.binance.com/api/v3/klines?symbol={par}&interval={intervalo}&limit={limite}"
        if end_time is not None:
            url += f"&endTime={end_time}"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        if not data:
            break
        todas = data + todas
        primero = data[0][0]
        if len(data) < limite:
            break
        end_time = primero - 1
        time.sleep(0.2)  # no machacar el rate limit publico
    df = pd.DataFrame(todas, columns=COLUMNAS)
    df = df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    return df


def main(par: str, intervalo: str = "1d"):
    df = descargar_historial_completo(par, intervalo)
    ruta = f"/Users/jorgeansotegui/Desktop/corvus4/datos/crudo/{par}_{intervalo}_spot_binance.csv"
    df.to_csv(ruta, index=False)
    fecha_ini = pd.to_datetime(df["open_time"].iloc[0], unit="ms", utc=True)
    fecha_fin = pd.to_datetime(df["open_time"].iloc[-1], unit="ms", utc=True)
    print(f"{par} {intervalo}: {len(df)} velas, {fecha_ini.date()} -> {fecha_fin.date()} -- guardado en {ruta}")


if __name__ == "__main__":
    par = sys.argv[1] if len(sys.argv) > 1 else "SOLUSDT"
    intervalo = sys.argv[2] if len(sys.argv) > 2 else "1d"
    main(par, intervalo)
