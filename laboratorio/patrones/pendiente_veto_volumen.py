"""
Variante de deteccion, 17-sept-2026: en vez de vetar el corte de
pendiente_acelerada por CONTEXTO de tendencia (canal ascendente/descendente,
ver pendiente_veto_canal.py y pendiente_veto_canal_percentil.py -- via
agotada esta sesion, ningun refinamiento de "cuan estricto es el filtro de
canal" resolvio el compromiso entre BTC/ETH/XRP), probar un mecanismo
DISTINTO: el VOLUMEN del propio dia del corte.

Idea: un movimiento de precio brusco (lo que dispara pendiente_acelerada)
con volumen alto suele ser un giro real -- mucha gente vendiendo/comprando
de golpe. El mismo movimiento con volumen bajo puede ser ruido o un susto
pasajero que no confirma nada. Es informacion que `pendiente_acelerada`
todavia no usa en ningun punto (ver `salidas/pendiente_acelerada.py`,
docstring: "esta capa no sabe nada de patrones ni de regimen, solo mide
velocidad de precio").

A diferencia del veto por canal (que depende de la DIRECCION de la
operacion -- un canal ascendente solo protege largos), el volumen es
direccion-agnostico: un corte con poco volumen es igual de sospechoso sea
largo o corto. Se usa la MISMA mascara para ambas direcciones.

Causal: `volume_media` es una media movil de `VENTANA_VOLUMEN` dias
terminada en el dia actual (nunca incluye dias futuros).
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.pendiente_veto_canal import simular_cuenta_veto_canal

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}

VENTANA_VOLUMEN = 30


def _no_confirma_volumen(df, umbral_volumen, ventana_volumen=VENTANA_VOLUMEN):
    """True el dia en que el volumen esta POR DEBAJO de `umbral_volumen`
    veces su propia media reciente -- ese dia, un corte de pendiente
    acelerada NO se confia (se veta), por poco convincente."""
    volume = df["volume"].to_numpy()
    vol_media = df["volume"].rolling(ventana_volumen).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = volume / vol_media
    no_confirma = np.where(np.isnan(ratio), False, ratio < umbral_volumen)
    return no_confirma


def _total_por_moneda(df, atr, rt, rs, pend, fechas, en_largo, en_corto, cand_por_año=None):
    if cand_por_año is None:
        cand_por_año = {año: candidatos_por_año(df, año) for año in AÑOS}
    total = 0.0
    por_año = {}
    for año in AÑOS:
        cap = simular_cuenta_veto_canal(df, cand_por_año[año], atr, rt, rs, pend, fechas, en_largo, en_corto)
        por_año[año] = round(cap, 2)
        total += cap
    return total, por_año


if __name__ == "__main__":
    print("=== 1) AJUSTE en ETH: grid de umbral_volumen ===")
    df_eth, atr_e, rt_e, rs_e, pend_e, cl_e, cc_e = cargar("ETHUSDT")
    fechas_e = df_eth["open_time"]
    cand_eth = {año: candidatos_por_año(df_eth, año) for año in AÑOS}

    GRID = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4, 1.6]
    resultados = {}
    for u in GRID:
        veto = _no_confirma_volumen(df_eth, u)
        total, _ = _total_por_moneda(df_eth, atr_e, rt_e, rs_e, pend_e, fechas_e, veto, veto, cand_eth)
        resultados[u] = total
        print(f"  umbral_volumen={u}: total={total:.2f}  (dias_vetados={int(veto.sum())})")

    ganador = max(resultados, key=resultados.get)
    print(f"GANADOR ETH: umbral_volumen={ganador} -> {resultados[ganador]:.2f}")
    if ganador in (GRID[0], GRID[-1]):
        print("  AVISO: el ganador esta en el borde del rango probado -- habria que extender el grid.")

    print()
    print(f"=== 2) CONFIRMACION congelada (umbral_volumen={ganador}, sin tocar nada) ===")
    for nombre in ("BTC", "XRP"):
        cargador = MONEDAS[nombre]
        df, atr, rt, rs, pend, cl, cc = cargador()
        fechas = df["open_time"]
        veto = _no_confirma_volumen(df, ganador)
        total, por_año = _total_por_moneda(df, atr, rt, rs, pend, fechas, veto, veto)
        print(f"  {nombre}: TOTAL={total:.2f}  por_año={por_año}  dias_vetados={int(veto.sum())}/{len(df)}")
