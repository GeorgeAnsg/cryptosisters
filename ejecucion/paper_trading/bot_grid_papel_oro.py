#!/usr/bin/env python3
"""
Igual que bot_grid_papel.py pero para el oro -- fuente de datos distinta
(Yahoo Finance, futuro real GC=F, no hay token cripto de oro fiable tras lo
visto con PAXG) y por eso va en un script aparte en vez de meterlo en la
lista de pares cripto.

AVISO que hay que recordar cada vez que se mire este log: el oro es, con
diferencia, el candidato mas fragil de todo el proyecto -- su "buen"
resultado solo se vio en una ventana de 2.4 años que coincidio con un
rally, nunca paso ninguna puerta de validacion, y la version ajustada
especificamente a el mismo se rompio al probarla en plata/platino. Aqui se
usa la CONFIG GENERICA (la misma de BTC/ETH), no la version ajustada al
oro, precisamente para no arrastrar ese sobreajuste al forward-test.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from laboratorio.grid_adaptativo import simular
from bot_grid_papel import (
    CONFIG_GENERICA, VARIANTES_COSTE, evaluar_capital_con_coste,
    DIR_BASE, DIR_DATOS_VIVOS, DIR_LOGS, obtener_fecha_inicio_paper,
)

SIMBOLO_YAHOO = "GC=F"
NOMBRE_ARCHIVO = "XAUUSD_4h"


def descargar_1h_reciente(simbolo: str, dias: int = 60) -> pd.DataFrame:
    # quote() codifica simbolos como "^GSPC" (indices) a "%5EGSPC" -- sin
    # esto Yahoo devuelve un 404 para cualquier ticker que empiece por "^".
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(simbolo)}?range={dias}d&interval=1h"
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
    return agg.reset_index()


def cargar_o_iniciar_historial() -> pd.DataFrame:
    ruta = os.path.join(DIR_DATOS_VIVOS, f"{NOMBRE_ARCHIVO}.csv")
    if os.path.exists(ruta):
        h = pd.read_csv(ruta)
        h["open_time"] = pd.to_datetime(h["open_time"], utc=True)
        return h
    ruta_semilla = os.path.join(DIR_BASE, "..", "..", "datos", "crudo", f"{NOMBRE_ARCHIVO}_yahoo_futures.csv")
    if os.path.exists(ruta_semilla):
        s = pd.read_csv(ruta_semilla)
        s["open_time"] = pd.to_datetime(s["open_time"], unit="ms", utc=True)
        for c in ["open", "high", "low", "close", "volume"]:
            s[c] = s[c].astype(float)
        return s[["open_time", "open", "high", "low", "close", "volume"]]
    return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])


def ejecutar_ciclo():
    historial = cargar_o_iniciar_historial()
    # Sin nada guardado todavia (ni datos_vivos/ ni semilla local -- esta
    # ultima esta en datos/crudo/, que esta en .gitignore y no viaja con un
    # despliegue nuevo): pedir el maximo que Yahoo permite en velas de 1h
    # (730 dias) para arrancar con años de calentamiento real en vez de
    # los 60 dias de una actualizacion normal.
    dias = 729 if historial.empty else 60
    df1h = descargar_1h_reciente(SIMBOLO_YAHOO, dias=dias)
    velas_nuevas = a_4h(df1h)

    combinado = pd.concat([historial, velas_nuevas]).drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume"]:
        combinado[c] = combinado[c].astype(float)
    os.makedirs(DIR_DATOS_VIVOS, exist_ok=True)
    combinado.to_csv(os.path.join(DIR_DATOS_VIVOS, f"{NOMBRE_ARCHIVO}.csv"), index=False)

    res = simular(combinado, **CONFIG_GENERICA)
    fecha_inicio = obtener_fecha_inicio_paper("XAUUSD")

    fila_log = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "par": "XAUUSD", "n_velas_historial": len(combinado)}
    for nombre_variante, coste in VARIANTES_COSTE.items():
        capital, drawdown, n_trades = evaluar_capital_con_coste(res, CONFIG_GENERICA["n_niveles"], coste, combinado, fecha_inicio)
        fila_log[f"capital_{nombre_variante}"] = round(capital, 4)
        fila_log[f"drawdown_{nombre_variante}"] = round(drawdown, 4)
        fila_log["n_trades"] = n_trades

    os.makedirs(DIR_LOGS, exist_ok=True)
    ruta_log = os.path.join(DIR_LOGS, "XAUUSD_4h_paper.csv")
    existe = os.path.exists(ruta_log)
    with open(ruta_log, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fila_log.keys()))
        if not existe:
            w.writeheader()
        w.writerow(fila_log)

    print(f"[{fila_log['timestamp_utc']}] XAUUSD 4h -- "
          f"spot={fila_log['capital_spot']:.2f} "
          f"futuros_mercado={fila_log['capital_futuros_mercado']:.2f} "
          f"futuros_limite={fila_log['capital_futuros_limite']:.2f} "
          f"(n_trades={fila_log['n_trades']}, historial={len(combinado)} velas)")


if __name__ == "__main__":
    try:
        ejecutar_ciclo()
    except Exception as e:
        print(f"[ERROR] XAUUSD: {e}")
