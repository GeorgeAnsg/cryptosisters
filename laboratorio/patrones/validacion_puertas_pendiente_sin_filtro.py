"""
Validacion formal de pendiente_acelerada COMO PIEZA NUEVA del sistema base
-- 15-sept-2026. Reencuadre tras el fallo del filtro de regimen NEUTRO
(ver observacion 0026): pendiente_acelerada SIN ningun filtro de contexto
es, en la practica, el arreglo estructural de "racha rota ciega" (Sección
3 de pruebas_canal.html) -- racha_rota_techo/suelo SOLO puede activarse si
existe una secuencia de picos/valles YA CONFIRMADOS por el detector de
doble techo/suelo cerca (_racha_rota en barrido_racha_tendencia.py, que
depende de _puntos_confirmados). Si no hay ningun pico2 confirmado
todavia -- como en el caso de abril 2024 -- el mecanismo esta APAGADO,
no mal calibrado. pendiente_acelerada, en cambio, se calcula solo con
close/ATR (ver _pendiente_atr), sin depender de ningun pico confirmado --
cubre exactamente ese hueco estructural.

Aqui se valida pendiente_acelerada como pieza propia (no como filtro
sobre otra cosa): Puerta 1 (causalidad), Puerta 5 (recursividad), Puerta 4
(DSR) y Puerta 3 (costes reales) sobre los trades SIN ningun filtro de
regimen -- la version que sobrevivio a todo lo demas esta sesion.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, UMBRAL_PENDIENTE, _en_lateral
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from tests.puerta1_causalidad import verificar_causalidad
from tests.puerta5_recursividad import verificar_recursividad
from tests.puerta4_dsr import evaluar as evaluar_dsr
from tests.puerta_presupuesto import verificar_presupuesto

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}


def _retorno_pct_trade(t):
    if t["direccion"] == "largo":
        return (t["precio_salida"] / t["precio_entrada"] - 1) * 100
    return (t["precio_entrada"] / t["precio_salida"] - 1) * 100


# ---------------------------------------------------------------------
print("=" * 70)
print("1) PUERTA 1 (causalidad) y PUERTA 5 (recursividad) sobre pendiente_atr")
print("=" * 70)


def _fn_indicadores(df):
    return df


def _fn_senales(df):
    df = df.copy()
    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr = pd_ewm_atr = None
    import pandas as pd
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    p = _pendiente_atr(df, atr)
    df["pendiente"] = p
    df["corte_pendiente"] = (np.abs(p) >= UMBRAL_PENDIENTE).astype(int)
    return df


df_eth, *_ = cargar("ETHUSDT")
r1 = verificar_causalidad(df_eth, _fn_indicadores, _fn_senales, ["pendiente", "corte_pendiente"], n_cortes=25, warmup_minimo=30)
print(r1.resumen())
r5 = verificar_recursividad(df_eth, _fn_indicadores, _fn_senales, ["pendiente", "corte_pendiente"], historia_disponible=60, n_puntos=25)
print(r5.resumen())

# ---------------------------------------------------------------------
print("\n" + "=" * 70)
print("2) PUERTA 4 (DSR) sobre pendiente_acelerada SIN filtro de contexto")
print("=" * 70)

presupuesto = verificar_presupuesto()
n_intentos = presupuesto["n_intentos_distintos"]
print(f"presupuesto: {n_intentos} intentos registrados / {presupuesto['presupuesto_total']}")

todos_retornos = []
trades_por_moneda = {}
for nombre, cargador in MONEDAS.items():
    df, atr, rt, rs, pend, cl, cc = cargador()
    fechas = df["open_time"]
    sin_filtro = np.zeros(len(df), dtype=bool)
    total, trades = 0.0, []
    for año in AÑOS:
        cand = candidatos_por_año(df, año)
        cap, tr = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, sin_filtro)
        total += cap
        trades.extend(tr)
    trades_por_moneda[nombre] = trades
    retornos = [_retorno_pct_trade(t) for t in trades]
    todos_retornos.extend(retornos)
    r_dsr = evaluar_dsr(np.array(retornos), n_intentos)
    print(r_dsr.resumen(nombre) + f"  [total capital 4 años = {total:.2f}]")

r_dsr_pool = evaluar_dsr(np.array(todos_retornos), n_intentos)
print(r_dsr_pool.resumen("POOL (3 monedas)"))

# ---------------------------------------------------------------------
print("\n" + "=" * 70)
print("3) PUERTA 3 (costes reales) -- sensibilidad, cuenta continua compuesta")
print("=" * 70)


def _capital_con_coste(trades, coste_pct):
    capital = 1000.0
    for t in trades:
        r = _retorno_pct_trade(t)
        peso_capital = t["pnl_eur"] / (r / 100) if r != 0 else 0.0
        pnl_neto = t["pnl_eur"] - abs(peso_capital) * (coste_pct / 100) if peso_capital else t["pnl_eur"]
        capital += pnl_neto
    return capital


COSTES_PCT = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
for nombre, trades in trades_por_moneda.items():
    print(f"\n{nombre} ({len(trades)} operaciones):")
    for c in COSTES_PCT:
        cap = _capital_con_coste(trades, c)
        print(f"  coste={c:.1f}%/op: capital_final={cap:.2f}")

print("\nFIN", flush=True)
