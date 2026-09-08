#!/usr/bin/env python3
"""
Descarga velas (klines) de SPOT de Binance desde los volcados publicos oficiales
de data.binance.vision. Sin dependencias externas: solo biblioteca estandar.

Por que spot y no perpetuo: el spot de BTCUSDT empieza en agosto de 2017, tres
anios antes que el perpetuo de Bybit que ya teniamos (marzo 2020). Esos tres
anios extra son la via mas barata de ampliar el presupuesto de intentos
(ver docs/00-PLAN-MAESTRO.md, seccion 3).

NO ejecuta nada descargado: solo baja ZIPs de datos y los concatena.
Guarda el CSV crudo tal cual viene (columnas de Binance) en datos/crudo/.
"""
import csv, io, os, sys, time, zipfile, urllib.request, urllib.error
from datetime import date

BASE = "https://data.binance.vision/data/spot/monthly/klines"
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "crudo")

COLUMNAS = ["open_time","open","high","low","close","volume","close_time",
            "quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"]

def meses(desde, hasta):
    y, m = desde
    while (y, m) <= hasta:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1

def descargar_mes(par, tf, y, m):
    url = f"{BASE}/{par}/{tf}/{par}-{tf}-{y:04d}-{m:02d}.zip"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None          # mes que no existe todavia: normal
        raise
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        nombre = z.namelist()[0]
        return z.read(nombre).decode("utf-8")

def descargar(par, tf, desde, hasta):
    os.makedirs(RAIZ, exist_ok=True)
    salida = os.path.join(RAIZ, f"{par}_{tf}_spot_binance.csv")
    filas, meses_ok, meses_no = 0, 0, []
    with open(salida, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        for y, m in meses(desde, hasta):
            texto = descargar_mes(par, tf, y, m)
            if texto is None:
                meses_no.append(f"{y}-{m:02d}")
                continue
            for linea in texto.strip().split("\n"):
                campos = linea.split(",")
                if campos[0] == "open_time":     # algunos meses traen cabecera
                    continue
                w.writerow(campos)
                filas += 1
            meses_ok += 1
            time.sleep(0.15)                      # cortesia con el servidor
    print(f"  {par} {tf}: {filas:,} velas · {meses_ok} meses · sin datos: {len(meses_no)}")
    if meses_no:
        print(f"    meses ausentes: {', '.join(meses_no[:6])}{' ...' if len(meses_no) > 6 else ''}")
    return salida, filas

if __name__ == "__main__":
    par = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    tfs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["1d", "4h", "1h", "15m"]
    hoy = date.today()
    hasta = (hoy.year, hoy.month - 1) if hoy.month > 1 else (hoy.year - 1, 12)
    print(f"Descargando {par} desde 2017-08 hasta {hasta[0]}-{hasta[1]:02d}")
    for tf in tfs:
        descargar(par, tf, (2017, 8), hasta)
