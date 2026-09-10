#!/usr/bin/env python3
"""
Igual que bot_grid_papel_oro.py pero para acciones (Yahoo Finance, mismo
endpoint, cambia solo el simbolo) -- Nvidia, Google, Coca-Cola.

AVISO importante, mas fuerte que el del oro: esto es terreno no explorado
en ningun backtest previo del proyecto. Todo lo probado hasta ahora
(Doble suelo/Techo, el grid) se valido sobre mercados cripto que cotizan
24/7 sin huecos. Una accion cierra cada tarde y abre al dia siguiente con
un salto de precio (a veces grande, por ejemplo tras resultados
trimestrales) que no existe en cripto -- mecanismos como el re-centrado
periodico o el calculo de ATR nunca se han visto sometidos a ese patron.
No sabemos si el grid se comporta razonablemente aqui o no; ESO es lo que
este forward test esta comprobando, no una hipotesis ya validada como en
BTC/ETH. Trata estos numeros con el maximo escepticismo del grupo, mas
incluso que el oro.

Usa la CONFIG GENERICA (la misma de BTC/ETH), no una version ajustada a
acciones -- no existe tal version, y crear una ahora seria sobreajustar
sin ni siquiera haber comprobado que el mecanismo basico tiene sentido
aqui.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from laboratorio.grid_adaptativo import simular
from bot_grid_papel import (
    CONFIG_GENERICA, VARIANTES_COSTE, evaluar_capital_con_coste,
    DIR_DATOS_VIVOS, DIR_LOGS, obtener_fecha_inicio_paper,
)
from bot_grid_papel_oro import descargar_1h_reciente, a_4h

# Clave = ticker real de Yahoo (lo que se pide en la URL), valor = nombre
# de archivo (los indices usan "^", invalido en nombres de archivo, de ahi
# la separacion). No hay archivo semilla en datos/crudo/ para ninguna de
# estas -- arrancan desde cero con lo que Yahoo permita (maximo 730 dias de
# velas de 1h), a diferencia de BTC/ETH/oro que ya tenian años de historial
# previo. ^GSPC = S&P 500, ^IXIC = Nasdaq Composite -- igual de terreno no
# explorado que las acciones sueltas (mismo aviso de arriba: mercado con
# horario y huecos, nunca visto por este mecanismo).
ACCIONES = {
    "NVDA": "NVDA", "GOOGL": "GOOGL", "KO": "KO",
    "^GSPC": "SPX", "^IXIC": "NASDAQ",
}


def cargar_o_iniciar_historial(nombre_archivo: str):
    import pandas as pd
    ruta = os.path.join(DIR_DATOS_VIVOS, f"{nombre_archivo}.csv")
    if os.path.exists(ruta):
        h = pd.read_csv(ruta)
        h["open_time"] = pd.to_datetime(h["open_time"], utc=True)
        return h
    return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])


def ejecutar_ciclo(ticker: str, nombre_archivo: str):
    import pandas as pd
    # 729 dias (el maximo que Yahoo permite en velas de 1h) para arrancar
    # con el mayor calentamiento posible de ADX/ATR desde el primer ciclo.
    df1h = descargar_1h_reciente(ticker, dias=729)
    velas_nuevas = a_4h(df1h)
    historial = cargar_o_iniciar_historial(nombre_archivo)

    combinado = pd.concat([historial, velas_nuevas]).drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume"]:
        combinado[c] = combinado[c].astype(float)
    os.makedirs(DIR_DATOS_VIVOS, exist_ok=True)
    combinado.to_csv(os.path.join(DIR_DATOS_VIVOS, f"{nombre_archivo}.csv"), index=False)

    res = simular(combinado, **CONFIG_GENERICA)
    fecha_inicio = obtener_fecha_inicio_paper(nombre_archivo)

    fila_log = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "par": ticker, "n_velas_historial": len(combinado)}
    for nombre_variante, coste in VARIANTES_COSTE.items():
        capital, drawdown, n_trades = evaluar_capital_con_coste(res, CONFIG_GENERICA["n_niveles"], coste, combinado, fecha_inicio)
        fila_log[f"capital_{nombre_variante}"] = round(capital, 4)
        fila_log[f"drawdown_{nombre_variante}"] = round(drawdown, 4)
        fila_log["n_trades"] = n_trades

    os.makedirs(DIR_LOGS, exist_ok=True)
    ruta_log = os.path.join(DIR_LOGS, f"{nombre_archivo}_paper.csv")
    existe = os.path.exists(ruta_log)
    with open(ruta_log, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fila_log.keys()))
        if not existe:
            w.writeheader()
        w.writerow(fila_log)

    print(f"[{fila_log['timestamp_utc']}] {ticker} 4h -- "
          f"spot={fila_log['capital_spot']:.2f} "
          f"futuros_mercado={fila_log['capital_futuros_mercado']:.2f} "
          f"futuros_limite={fila_log['capital_futuros_limite']:.2f} "
          f"(n_trades={fila_log['n_trades']}, historial={len(combinado)} velas)")


if __name__ == "__main__":
    for ticker, nombre_archivo in ACCIONES.items():
        try:
            ejecutar_ciclo(ticker, nombre_archivo)
        except Exception as e:
            print(f"[ERROR] {ticker}: {e}")
