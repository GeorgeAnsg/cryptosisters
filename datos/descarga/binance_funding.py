#!/usr/bin/env python3
"""
Descarga historico de FUNDING RATE de futuros perpetuos USDT-M de Binance
desde los volcados publicos de data.binance.vision. Sin dependencias
externas: solo biblioteca estandar. Igual patron que binance_spot_klines.py.

Para que: M2 del catalogo (docs/00-PLAN-MAESTRO.md 7.2) -- reversion tras
funding extremo negativo + cascada de liquidaciones. El funding es la
tasa que pagan los que estan largos a los que estan cortos (o al reves)
en un perpetuo, cada 8 horas; un funding muy negativo extremo significa
que hay muchisimos mas cortos que largos -- apalancamiento forzado, no
opinion, que es justo el mecanismo que hace creible a M2.

NO ejecuta nada descargado: solo baja ZIPs de datos y los concatena.
"""
import csv, io, os, sys, time, zipfile, urllib.request, urllib.error
from datetime import date

BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "crudo")

COLUMNAS = ["calc_time", "funding_interval_hours", "last_funding_rate"]


def meses(desde, hasta):
    y, m = desde
    while (y, m) <= hasta:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def descargar_mes(par, y, m):
    url = f"{BASE}/{par}/{par}-fundingRate-{y:04d}-{m:02d}.zip"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        nombre = z.namelist()[0]
        with z.open(nombre) as f:
            texto = f.read().decode("utf-8")
    filas = list(csv.reader(io.StringIO(texto)))
    if filas and filas[0][0].strip().lower() in ("calc_time", "calctime"):
        filas = filas[1:]
    return filas


def descargar_par(par, hasta_hoy=True):
    hoy = date.today()
    desde = (2019, 9)  # BTCUSDT perpetuo empieza sept-2019 en Binance
    hasta = (hoy.year, hoy.month)
    ruta_salida = os.path.join(RAIZ, f"{par}_funding_binance.csv")
    os.makedirs(RAIZ, exist_ok=True)

    total = 0
    with open(ruta_salida, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(COLUMNAS)
        for y, m in meses(desde, hasta):
            filas = descargar_mes(par, y, m)
            if filas is None:
                print(f"  {par} {y:04d}-{m:02d}: no disponible (normal si es futuro)")
                continue
            w.writerows(filas)
            total += len(filas)
            print(f"  {par} {y:04d}-{m:02d}: {len(filas)} filas")
            time.sleep(0.2)
    print(f"{par}: {total} filas totales -> {ruta_salida}")


if __name__ == "__main__":
    pares = sys.argv[1].split(",") if len(sys.argv) > 1 else ["BTCUSDT"]
    for par in pares:
        descargar_par(par)
