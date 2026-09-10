#!/usr/bin/env python3
"""
Descarga velas diarias de futuros de materias primas (plata, platino, oro)
desde la API de graficos de Yahoo Finance -- no hay ningun token cripto de
plata/platino en Binance (se comprobo via exchangeInfo), asi que para
contrastar el ajuste hecho sobre oro (PAXG) en un segundo/tercer metal
independiente hace falta esta fuente distinta.

Guarda el CSV en el mismo formato de columnas que datos/cargar.py espera
(compatible con Binance), con las columnas que Yahoo no da (quote_volume,
trades, taker_buy_*) puestas a 0 -- no se usan en ningun sitio del proyecto
salvo para completar el esquema.
"""
import csv
import json
import sys
import urllib.request

COLUMNAS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]


def descargar(simbolo: str, rango: str = "10y") -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?range={rango}&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def guardar(simbolo: str, nombre_salida: str, ruta_base: str = "datos/crudo"):
    data = descargar(simbolo)
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    salida = f"{ruta_base}/{nombre_salida}"
    filas = 0
    with open(salida, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        for i in range(len(ts)):
            o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
            if o is None or h is None or l is None or c is None:
                continue
            open_time_ms = ts[i] * 1000
            close_time_ms = open_time_ms + 86_400_000 - 1
            w.writerow([open_time_ms, o, h, l, c, v or 0, close_time_ms, 0, 0, 0, 0, 0])
            filas += 1
    print(f"{simbolo} -> {salida}: {filas} velas diarias")


if __name__ == "__main__":
    guardar("SI=F", "XAGUSD_1d_yahoo_futures.csv")   # plata
    guardar("PL=F", "XPTUSD_1d_yahoo_futures.csv")   # platino
    guardar("GC=F", "XAUUSD_1d_yahoo_futures.csv")   # oro (futuro real, para contrastar tambien con PAXG)
