#!/usr/bin/env python3
"""
Piloto de forward-test ("paper trading") del grid adaptativo — dinero
FICTICIO, precio REAL. Objetivo: comprobar si la ventaja que vemos en el
backtest se sostiene con datos que van llegando de verdad, sin arriesgar
nada, y comparar en paralelo tres formas de ejecutar la misma estrategia
(spot / futuros a mercado / futuros límite) para ver cuánto se lleva cada
una en comisiones reales.

Cómo funciona (se ejecuta periódicamente, p.ej. via cron cada 4h):
1. Descarga las velas de 4h más recientes de Binance (BTC, dinero real de
   verdad cotizando -- no hace falta cuenta ni API key, es el endpoint
   publico de klines).
2. Las junta con el historial ya guardado en datos/live/.
3. Vuelve a correr `simular()` (el MISMO codigo que el backtest, sin
   ninguna version especial "para produccion") sobre todo el historial
   acumulado -- barato computacionalmente (unos pocos miles de velas).
4. Para cada variante de coste (spot/futuros mercado/futuros limite),
   recalcula el capital ficticio aplicando el coste por operacion
   correspondiente, y lo anota en el log CSV con fecha.
5. No ejecuta NINGUNA orden real. Es contabilidad ficticia sobre precio
   real -- pensado para dejar correr semanas/meses y ver si el resultado
   del backtest se sostiene antes de arriesgar dinero real.

NO requiere claves de API ni acceso a ninguna cuenta -- deliberadamente
seguro para dejar corriendo sin supervision.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pandas as pd

from laboratorio.grid_adaptativo import simular, ResultadoGrid

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
# En local, por defecto vive junto al script (compatibilidad con lo ya
# probado). En el contenedor, CORVUS4_DATA_ROOT=/app/data apunta al volumen
# persistente de Coolify -- una sola carpeta que montar, no dos.
DIR_DATA_ROOT = os.environ.get("CORVUS4_DATA_ROOT", DIR_BASE)
DIR_DATOS_VIVOS = os.path.join(DIR_DATA_ROOT, "datos_vivos")
DIR_LOGS = os.path.join(DIR_DATA_ROOT, "logs")
DIR_INICIO_PAPER = os.path.join(DIR_DATA_ROOT, "inicio_paper")

CONFIG_GENERICA = dict(
    n_niveles=3, k_atr_espaciado=0.5, k_atr_espaciado_tendencia=1.5,
    k_atr_objetivo_mult=1.5, espaciado_dinamico=True,
    velas_recentrado=180, stop_bajo_rejilla=2.0,
)

# Pares cripto a correr con la misma config generica (via Binance publico).
# BTC/ETH: confirmados con evidencia solida (Doble suelo/Techo + grid probado
# extensamente). El resto -- XRP/BNB/SOL/ADA/DOGE/LINK/AVAX/DOT/LTC/TRX --
# el GRID nunca se ha probado en ellos hasta ahora; este paper trading es,
# de facto, su primera prueba con el grid, aunque sea en vivo y no en
# backtest historico. Son todos pares liquidos de Binance (misma familia
# 24/7 que BTC/ETH), lo cual es barato añadir: mismo codigo, mismo coste
# computacional trivial por activo, solo una llamada API + una simulacion.
PARES_CRIPTO = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT",
    "SOLUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT",
    "AVAXUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT",
]

VARIANTES_COSTE = {
    "spot": 0.20,               # Bybit spot: 0.10% + 0.10% ida y vuelta
    "futuros_mercado": 0.11,    # Bybit perp taker: 0.055% x 2
    "futuros_limite": 0.02,     # Bybit perp maker: 0.01% x 2 (mejor caso -- no siempre se llena)
}


def descargar_velas_recientes(par: str, tf: str = "4h", limite: int = 1000) -> pd.DataFrame:
    """Binance publico, sin autenticacion -- las mismas velas reales que
    cotizan ahora mismo en el mercado."""
    url = f"https://api.binance.com/api/v3/klines?symbol={par}&interval={tf}&limit={limite}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    filas = [(d[0], float(d[1]), float(d[2]), float(d[3]), float(d[4]), float(d[5])) for d in data]
    df = pd.DataFrame(filas, columns=["open_time", "open", "high", "low", "close", "volume"])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df


def descargar_historial_completo(par: str, tf: str = "4h", max_velas: int = 20000) -> pd.DataFrame:
    """Pagina hacia atras en Binance (endTime decreciente) hasta juntar
    hasta max_velas velas o hasta que Binance ya no tenga mas historia para
    ese par (respuesta vacia o mas corta de lo pedido -- llegamos al inicio
    de su cotizacion). 20000 velas de 4h son ~9 años, de sobra para
    BTC/ETH; para pares mas nuevos simplemente para antes, en su propio
    inicio real. Solo se usa al arrancar de cero (sin datos_vivos/ ni
    semilla local) -- en ciclos normales se sigue usando
    descargar_velas_recientes (una sola llamada, barato)."""
    todas: list[tuple] = []
    end_time = None
    while len(todas) < max_velas:
        url = f"https://api.binance.com/api/v3/klines?symbol={par}&interval={tf}&limit=1000"
        if end_time is not None:
            url += f"&endTime={end_time}"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        if not data:
            break
        filas = [(d[0], float(d[1]), float(d[2]), float(d[3]), float(d[4]), float(d[5])) for d in data]
        todas = filas + todas
        end_time = data[0][0] - 1
        if len(data) < 1000:
            break  # llegamos al principio de la historia cotizada de este par
    if not todas:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(todas, columns=["open_time", "open", "high", "low", "close", "volume"])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)


def cargar_o_iniciar_historial(par: str, tf: str) -> pd.DataFrame:
    """La primera vez, arranca con años de historial real en vez de
    empezar en vacío -- así el ADX/ATR tienen calentamiento correcto desde
    el primer ciclo Y el "capital" que se registra cada noche refleja una
    muestra grande, no solo unas semanas. Antes dependía de un archivo
    semilla en datos/crudo/, pero esa carpeta esta en .gitignore (no viaja
    con el repo a un despliegue nuevo) -- asi que si no hay nada guardado
    todavia, se descarga paginando Binance en vez de asumir que la semilla
    esta ahi. A partir de la primera vez, vive en datos_vivos/ y crece con
    cada ciclo normal (una sola llamada, no repagina)."""
    ruta = os.path.join(DIR_DATOS_VIVOS, f"{par}_{tf}.csv")
    if os.path.exists(ruta):
        historial = pd.read_csv(ruta)
        historial["open_time"] = pd.to_datetime(historial["open_time"], utc=True)
        return historial

    ruta_semilla = os.path.join(DIR_BASE, "..", "..", "datos", "crudo", f"{par}_{tf}_spot_binance.csv")
    if os.path.exists(ruta_semilla):
        from datos.cargar import cargar_ohlcv
        semilla = cargar_ohlcv(par, tf, ruta_base=os.path.join(DIR_BASE, "..", "..", "datos", "crudo"))
        return semilla[["open_time", "open", "high", "low", "close", "volume"]]

    print(f"[{par}] sin historial local ni semilla -- descargando historico completo de Binance (puede tardar unos segundos)...")
    return descargar_historial_completo(par, tf)


def guardar_historial(df: pd.DataFrame, par: str, tf: str):
    os.makedirs(DIR_DATOS_VIVOS, exist_ok=True)
    df.to_csv(os.path.join(DIR_DATOS_VIVOS, f"{par}_{tf}.csv"), index=False)


def obtener_fecha_inicio_paper(nombre: str):
    """La PRIMERA vez que un activo corre en este despliegue, fija su
    "dia 1" real y lo guarda en disco. A partir de ahi, esa fecha nunca
    cambia -- es el punto de referencia para separar "resultado del
    backtest sobre el historial descargado" (que no cuenta, son años
    pasados) de "resultado desde que este bot vigila el activo en el
    servidor" (lo unico que responde a "?voy ganando o perdiendo hoy?").
    Sin esto, evaluar_capital_con_coste sumaria de golpe todas las
    operaciones de los años de historial usados solo para calentar
    ADX/ATR, y el primer mensaje ya saldria con decenas de trades y
    capital movido antes de que el bot llevara ni un ciclo corriendo."""
    os.makedirs(DIR_INICIO_PAPER, exist_ok=True)
    ruta = os.path.join(DIR_INICIO_PAPER, f"{nombre}.txt")
    if os.path.exists(ruta):
        with open(ruta) as f:
            return pd.Timestamp(f.read().strip())
    ahora = pd.Timestamp.now(tz="UTC")
    with open(ruta, "w") as f:
        f.write(ahora.isoformat())
    return ahora


def evaluar_capital_con_coste(res: ResultadoGrid, n_niveles: int, coste_rt_pct: float,
                               velas: pd.DataFrame | None = None, fecha_inicio=None) -> tuple[float, float, int]:
    brutos = [n_niveles - k for k in range(n_niveles)]
    suma = sum(brutos)
    pesos = {k: brutos[k] / suma for k in range(n_niveles)}
    trades_ordenados = sorted(res.trades, key=lambda t: t.idx_salida)
    if velas is not None and fecha_inicio is not None:
        # Descarta las operaciones que el backtest "encuentra" dentro del
        # historial descargado para calentar indicadores -- ya pasaron
        # antes de que este despliegue existiera, no son parte del
        # resultado que se le esta mostrando al usuario dia a dia.
        trades_ordenados = [t for t in trades_ordenados if velas.iloc[t.idx_salida]["open_time"] >= fecha_inicio]
    capital, pico, caida_max = 100.0, 100.0, 0.0
    for t in trades_ordenados:
        peso = pesos.get(t.idx_nivel, 1 / n_niveles) * t.peso_fraccion
        retorno_neto = t.retorno_pct - coste_rt_pct
        capital += 100.0 * peso * (retorno_neto / 100)
        pico = max(pico, capital)
        caida_max = min(caida_max, (capital / pico - 1) * 100)
    return capital, caida_max, len(trades_ordenados)


def ejecutar_ciclo(par: str = "BTCUSDT", tf: str = "4h", config: dict = CONFIG_GENERICA):
    velas_nuevas = descargar_velas_recientes(par, tf)
    historial = cargar_o_iniciar_historial(par, tf)

    combinado = pd.concat([historial, velas_nuevas]).drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume"]:
        combinado[c] = combinado[c].astype(float)
    guardar_historial(combinado, par, tf)

    res = simular(combinado, **config)
    fecha_inicio = obtener_fecha_inicio_paper(par)

    fila_log = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "par": par, "n_velas_historial": len(combinado)}
    for nombre_variante, coste in VARIANTES_COSTE.items():
        capital, drawdown, n_trades = evaluar_capital_con_coste(res, config["n_niveles"], coste, combinado, fecha_inicio)
        fila_log[f"capital_{nombre_variante}"] = round(capital, 4)
        fila_log[f"drawdown_{nombre_variante}"] = round(drawdown, 4)
        fila_log["n_trades"] = n_trades

    os.makedirs(DIR_LOGS, exist_ok=True)
    ruta_log = os.path.join(DIR_LOGS, f"{par}_{tf}_paper.csv")
    existe = os.path.exists(ruta_log)
    with open(ruta_log, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fila_log.keys()))
        if not existe:
            w.writeheader()
        w.writerow(fila_log)

    print(f"[{fila_log['timestamp_utc']}] {par} {tf} -- "
          f"spot={fila_log['capital_spot']:.2f} "
          f"futuros_mercado={fila_log['capital_futuros_mercado']:.2f} "
          f"futuros_limite={fila_log['capital_futuros_limite']:.2f} "
          f"(n_trades={fila_log['n_trades']}, historial={len(combinado)} velas)")


if __name__ == "__main__":
    pares = sys.argv[1:] if len(sys.argv) > 1 else PARES_CRIPTO
    for par in pares:
        try:
            ejecutar_ciclo(par)
        except Exception as e:
            print(f"[ERROR] {par}: {e}")
