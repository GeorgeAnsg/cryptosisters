"""
Prueba concreta pedida por el usuario, 13-sept-2026: "con mil euros en un
año, ¿qué hace?" -- una cuenta simulada, no solo una media de retornos
abstracta. Y, explicitamente, PROBAR CADA IDEA POR SEPARADO antes de
combinarlas (esta sesion metio dos ideas nuevas sin probar -- patron
contrario y cambio de regimen -- y el usuario paro para exigir que se
prueben una a una primero):

  A) BASE: solo stop/objetivo (fija) + tiempo maximo -- lo que ya habia
     antes de las dos ideas nuevas.
  B) BASE + señal de patron contrario (sola).
  C) BASE + cambio de regimen persistente (sola).

Simplificaciones deliberadas de esta prueba (no son decisiones de
`tamano/`/`cartera/`, que no existen todavia -- se marcan aqui como
provisionales, solo para poder correr una cuenta de verdad):
- Tamano de posicion: arriesgar un `RIESGO_PCT` fijo del capital actual en
  cada operacion (2% -- numero de gestion de riesgo estandar, no derivado
  de nada del proyecto, PROVISIONAL).
- Sin solapamiento: si ya hay una posicion abierta, se ignoran nuevos
  candidatos hasta que se cierre (una cuenta real solo abre lo que puede
  vigilar a la vez; el arbitraje real de varias oportunidades simultaneas
  es trabajo de `cartera/`, no de esta prueba).

Periodo: TODO el historico de Desarrollo (necesario para que el ATH y el
regimen de `motores/` se calculen bien, ver aviso en
`motores/regimen_mercado.py` sobre no usar una ventana recortada), pero
solo se cuentan como candidatos de entrada los que caen en el año civil
2024 (el ultimo año completo dentro de Desarrollo, que termina
2025-01-01) -- asi se responde a "en un año" sin romper la particion.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from laboratorio.datos_lab import cargar_ohlcv_lab
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores import regimen_mercado
from motores.regimen_mercado import TipoRegimen
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

CAPITAL_INICIAL = 1000.0
RIESGO_PCT = 0.02  # PROVISIONAL -- no es una decision de tamano/, ver docstring
K_ATR_STOP = 2.5
R_FIJO = 3.0        # config razonable/moderada, NO la ganadora del barrido (ese sigue sin resolver,
DIAS_MAXIMO = 45    # ver salidas/README.md) -- aqui el foco es aislar el efecto de cada señal nueva
UMBRAL_CONTRARIA = 0.5
DIAS_PERSISTENCIA_REGIMEN = 3

AÑO = 2024


def _candidatos_2024(df):
    """[(idx, direccion, probabilidad)] restringido a fechas de 2024."""
    fechas = df["open_time"]
    out = []
    for c in techo_motor.detectar(df):
        if fechas.iloc[c.idx_techo2].year != AÑO:
            continue
        r = en_vivo_techo(df, c.idx_techo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_techo2, "corto", r.probabilidad_total_si_confirma))
    for c in suelo_motor.detectar(df):
        if fechas.iloc[c.idx_fondo2].year != AÑO:
            continue
        r = en_vivo_suelo(df, c.idx_fondo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_fondo2, "largo", r.probabilidad_total_si_confirma))
    return sorted(out, key=lambda c: c[0])


def _serie_señal_contraria(df):
    """señal_contraria_techo[i] = True si dia i es un candidato de SUELO en
    vivo (dia 0) con probabilidad >= umbral -- valida como señal de cierre
    para un CORTO. Y viceversa para un LARGO."""
    n = len(df)
    contraria_para_corto = np.zeros(n, dtype=bool)  # cierra cortos: aparece un suelo
    contraria_para_largo = np.zeros(n, dtype=bool)  # cierra largos: aparece un techo
    from entradas.doble_suelo import minimos_aparentes
    from entradas.doble_techo import maximos_aparentes
    close = df["close"].to_numpy()
    for idx in minimos_aparentes(close):
        r = en_vivo_suelo(df, idx, dia_transcurrido=0)
        if r is not None and r.probabilidad_total_si_confirma >= UMBRAL_CONTRARIA:
            contraria_para_corto[idx] = True
    for idx in maximos_aparentes(close):
        r = en_vivo_techo(df, idx, dia_transcurrido=0)
        if r is not None and r.probabilidad_total_si_confirma >= UMBRAL_CONTRARIA:
            contraria_para_largo[idx] = True
    return contraria_para_corto, contraria_para_largo


def _serie_regimen_desfavorable(df):
    """desfavorable_para_corto[i] = True si el dia i NO esta en regimen
    BAJISTA (favorable para un corto). Y viceversa para largo/ALCISTA."""
    n = len(df)
    sma200 = df["close"].rolling(200).mean()
    desfavorable_para_corto = np.zeros(n, dtype=bool)
    desfavorable_para_largo = np.zeros(n, dtype=bool)
    for i in range(n):
        tipo, _score = regimen_mercado.clasificar(df, i, sma200)
        desfavorable_para_corto[i] = tipo != TipoRegimen.BAJISTA
        desfavorable_para_largo[i] = tipo != TipoRegimen.ALCISTA
    return desfavorable_para_corto, desfavorable_para_largo


def _simular_cuenta(df, candidatos, atr, variante: str,
                     contraria_corto=None, contraria_largo=None,
                     desfav_corto=None, desfav_largo=None):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    curva = [capital]
    trades = []
    idx_libre_desde = 0

    for idx, direccion, _prob in candidatos:
        if idx < idx_libre_desde or np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)

        senal_externa = condicion_persistente = None
        if variante == "contraria":
            senal_externa = contraria_corto if direccion == "corto" else contraria_largo
        elif variante == "regimen":
            condicion_persistente = desfav_corto if direccion == "corto" else desfav_largo

        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                           senal_externa=senal_externa,
                           condicion_persistente=condicion_persistente,
                           dias_persistencia=DIAS_PERSISTENCIA_REGIMEN)
        if t is None:
            continue

        riesgo_dinero = capital * RIESGO_PCT
        tamano_unidades = riesgo_dinero / niveles.riesgo
        pnl = tamano_unidades * (t.precio_salida - t.precio_entrada) * (1 if direccion == "largo" else -1)
        capital += pnl
        curva.append(capital)
        trades.append({"idx_entrada": idx, "direccion": direccion, "motivo": t.motivo,
                        "retorno_pct_precio": t.retorno_pct, "pnl_eur": round(pnl, 2),
                        "capital_tras": round(capital, 2)})
        idx_libre_desde = t.idx_salida + 1

    curva = np.array(curva)
    pico = np.maximum.accumulate(curva)
    drawdown_pct = float(((curva - pico) / pico).min()) * 100 if len(curva) > 1 else 0.0
    motivos = {}
    for tr in trades:
        motivos[tr["motivo"]] = motivos.get(tr["motivo"], 0) + 1
    return capital, len(trades), drawdown_pct, motivos, trades


def _retornos_por_operacion_aislada(df, candidatos, atr, variante,
                                     contraria_corto=None, contraria_largo=None,
                                     desfav_corto=None, desfav_largo=None):
    """Igual que `_simular_cuenta` pero SIN la restriccion de no
    solapamiento -- cada candidato se resuelve de forma independiente,
    como si fuera la unica operacion abierta. Aisla el efecto de la REGLA
    DE SALIDA en si, sin mezclarlo con cuantas operaciones caben en la
    cuenta (eso es un efecto de `cartera/`, no de la salida)."""
    close = df["close"].to_numpy()
    retornos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal_externa = condicion_persistente = None
        if variante == "contraria":
            senal_externa = contraria_corto if direccion == "corto" else contraria_largo
        elif variante == "regimen":
            condicion_persistente = desfav_corto if direccion == "corto" else desfav_largo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                           senal_externa=senal_externa, condicion_persistente=condicion_persistente,
                           dias_persistencia=DIAS_PERSISTENCIA_REGIMEN)
        if t is not None:
            retornos.append(t.retorno_pct)
    return retornos


def main():
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_cuenta_1000e")
        atr = atr_absoluto(df)
        cand = _candidatos_2024(df)
        print(f"\n=== {moneda} -- candidatos en 2024: {len(cand)} ===")

        contraria_corto, contraria_largo = _serie_señal_contraria(df)
        desfav_corto, desfav_largo = _serie_regimen_desfavorable(df)

        for variante, nombre in [("base", "A) SOLO stop/objetivo/tiempo"),
                                  ("contraria", "B) BASE + señal de patron contrario"),
                                  ("regimen", "C) BASE + cambio de regimen (3 dias seguidos)")]:
            capital, n, dd, motivos, _ = _simular_cuenta(
                df, cand, atr, variante,
                contraria_corto, contraria_largo, desfav_corto, desfav_largo)
            ret_aislados = _retornos_por_operacion_aislada(
                df, cand, atr, variante, contraria_corto, contraria_largo, desfav_corto, desfav_largo)
            print(f"  {nombre}:")
            print(f"    CUENTA SECUENCIAL (con efecto de cuantas caben): capital final={capital:.2f} eur "
                  f"(partiendo de {CAPITAL_INICIAL:.0f}), trades={n}, drawdown_max={dd:.2f}%, motivos={motivos}")
            print(f"    POR OPERACION AISLADA (mismos {len(cand)} candidatos siempre, sin efecto de cuantas "
                  f"caben): retorno_medio={np.mean(ret_aislados):.3f}% sobre {len(ret_aislados)} operaciones")


if __name__ == "__main__":
    main()
