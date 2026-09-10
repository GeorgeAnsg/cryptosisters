#!/usr/bin/env python3
"""Descarga velas horarias de un futuro de Yahoo Finance (max 730 dias que
Yahoo permite para interval=1h) y las agrupa en velas de 4h -- necesario
para comparar version "rapida" (4h) vs "lenta" (1d) del grid en el mismo
periodo exacto, ya que Yahoo no ofrece 4h directamente ni historial largo
en intradia para estos futuros continuos."""
import csv
import json
import sys
import urllib.request

import pandas as pd

COLUMNAS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]


def descargar_1h(simbolo: str) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?range=730d&interval=1h"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    filas = []
    for i in range(len(ts)):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if o is None:
            continue
        filas.append((ts[i], o, h, l, c, v or 0))
    df = pd.DataFrame(filas, columns=["ts", "open", "high", "low", "close", "volume"])
    df["open_time"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df.set_index("open_time")[["open", "high", "low", "close", "volume"]]


def a_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    agg = df_1h.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return agg


def guardar(df_4h: pd.DataFrame, nombre_salida: str, ruta_base: str = "datos/crudo"):
    salida = f"{ruta_base}/{nombre_salida}"
    with open(salida, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        for idx, row in df_4h.iterrows():
            open_time_ms = int(idx.timestamp() * 1000)
            close_time_ms = open_time_ms + 4 * 3_600_000 - 1
            w.writerow([open_time_ms, row["open"], row["high"], row["low"], row["close"], row["volume"],
                        close_time_ms, 0, 0, 0, 0, 0])
    print(f"{nombre_salida}: {len(df_4h)} velas de 4h")


if __name__ == "__main__":
    df1h = descargar_1h("GC=F")
    df4h = a_4h(df1h)
    guardar(df4h, "XAUUSD_4h_yahoo_futures.csv")
