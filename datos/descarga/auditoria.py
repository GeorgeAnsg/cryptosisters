#!/usr/bin/env python3
"""
Auditoria de calidad de un CSV de velas. Falla RUIDOSAMENTE: un hueco silencioso
en 2021 puede inventar una senal que no existio.

Comprueba, para cada archivo:
  1. Orden estricto y sin duplicados de la marca temporal.
  2. Continuidad: ningun hueco distinto al paso esperado del timeframe.
  3. Coherencia OHLC: min <= apertura, cierre <= max; nada negativo.
  4. Velas de volumen cero (sospechosas, no siempre un error).
  5. Saltos de precio imposibles (> 30% entre cierres consecutivos).

Uso:  python3 auditoria.py ../crudo/BTCUSDT_1d_spot_binance.csv [...]
      python3 auditoria.py            # audita todo lo que haya en crudo/
"""
import csv, glob, os, sys
from datetime import datetime, timezone

PASO_MS = {"1m":60_000, "5m":300_000, "15m":900_000, "1h":3_600_000,
           "4h":14_400_000, "1d":86_400_000}

def fecha(ms):
    return datetime.fromtimestamp(ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

def normaliza_ms(v):
    # Binance cambio de milisegundos a microsegundos en algunos volcados de 2025.
    v = int(v)
    return v // 1000 if v > 10**14 else v

def auditar(ruta):
    tf = os.path.basename(ruta).split("_")[1]
    paso = PASO_MS.get(tf)
    if paso is None:
        print(f"  ! timeframe desconocido en {ruta}"); return False
    tiempos, problemas, vol_cero, saltos = [], [], 0, []
    cierre_ant = None
    with open(ruta) as f:
        for i, fila in enumerate(csv.DictReader(f), start=2):
            t = normaliza_ms(fila["open_time"])
            o, h, l, c = (float(fila[k]) for k in ("open","high","low","close"))
            v = float(fila["volume"])
            tiempos.append(t)
            if not (l <= o <= h and l <= c <= h) or l <= 0:
                problemas.append(f"linea {i}: OHLC incoherente ({fecha(t)})")
            if v == 0:
                vol_cero += 1
            if cierre_ant and abs(c/cierre_ant - 1) > 0.30:
                saltos.append(f"{fecha(t)}: {cierre_ant:.0f} -> {c:.0f}")
            cierre_ant = c

    duplicados = len(tiempos) - len(set(tiempos))
    desorden = sum(1 for a, b in zip(tiempos, tiempos[1:]) if b <= a)
    huecos = [(a, b) for a, b in zip(tiempos, tiempos[1:]) if b - a != paso and b > a]

    ok = not problemas and not duplicados and not desorden and not huecos
    print(f"\n  {os.path.basename(ruta)}")
    print(f"    velas: {len(tiempos):,}   desde {fecha(tiempos[0])}   hasta {fecha(tiempos[-1])}")
    print(f"    duplicados: {duplicados}   desorden: {desorden}   huecos: {len(huecos)}")
    print(f"    volumen cero: {vol_cero}   saltos >30%: {len(saltos)}")
    for a, b in huecos[:5]:
        faltan = (b - a)//paso - 1
        print(f"      hueco: {fecha(a)} -> {fecha(b)}  ({faltan} velas ausentes)")
    if len(huecos) > 5:
        print(f"      ... y {len(huecos)-5} huecos mas")
    for p in problemas[:5]:
        print(f"      {p}")
    for s in saltos[:3]:
        print(f"      salto: {s}")
    print(f"    VEREDICTO: {'OK' if ok else 'REVISAR'}")
    return ok

if __name__ == "__main__":
    rutas = sys.argv[1:] or sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "crudo", "*.csv")))
    if not rutas:
        print("No hay nada que auditar."); sys.exit(1)
    print(f"Auditando {len(rutas)} archivo(s)")
    todo_ok = all([auditar(r) for r in rutas])
    print(f"\nRESULTADO GLOBAL: {'todo correcto' if todo_ok else 'HAY ARCHIVOS QUE REVISAR'}")
    sys.exit(0 if todo_ok else 1)
