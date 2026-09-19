"""
18-sept-2026: el diagnostico operacion-a-operacion de `diagnostico_racha_4h_perdedores.py`
encontro que comparar CAPITAL AGREGADO entre "actual" y "racha_4h" esta contaminado por un
efecto cascada -- el sistema mantiene UNA sola posicion abierta a la vez, asi que en cuanto una
operacion se cierra en fecha distinta bajo cada mecanismo, TODAS las entradas siguientes de ese
año se desplazan (ya no es ni la misma operacion). Un cambio real el 25-ene-2024 (ETH) reordeno
el calendario completo del resto del año -- por eso el gating por tamaño de ganancia (3/8) y por
regimen de volatilidad (4/8) no generalizaron: no estaban midiendo el efecto del gate, estaban
midiendo una cadena de mariposa acumulada.

Este script aisla cada señal real de racha_rota (evento day-by-day, tal y como ya se dispara HOY
en produccion) y, para CADA una, simula el resto de esa operacion en paralelo con ambos
mecanismos de confirmacion (diario-actual vs 4h+persistencia) SIN dejar que ninguno afecte a la
entrada de la operacion siguiente -- ambas ramas parten del mismo precio de entrada y niveles,
solo difieren en como se resuelve la confirmacion de racha_rota. Se reporta, señal a señal, cual
de los dos gana y por cuanto, para los 8 tramos (ETH ajuste + holdout completo).
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import DIAS_MAXIMO, K_ATR_STOP, R_FIJO
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from laboratorio.patrones.racha_confirmacion_4h import _cargar_4h, _simular_trade_manual_racha_4h
from laboratorio.patrones.trailing_retroceso_alto import UMBRAL_CAIDA_FILTRO, _simular_trade_manual
from salidas.stop_objetivo import calcular_niveles_fijos

ACTIVACION_ACTUAL = 0.10
RETROCESO_ACTUAL = 999
VELAS_PERSISTENCIA = 6


def _resolver_ambos(df, df4h, inicio4h, fin4h, idx_entrada, direccion, precio_entrada, niveles,
                     senal, pendiente, pendiente4h):
    """Misma entrada, mismos niveles -- solo cambia el mecanismo de confirmacion de racha_rota.
    Devuelve (motivo_actual, pnl_pct_actual, motivo_4h, pnl_pct_4h)."""
    signo = 1 if direccion == "largo" else -1
    r_a = _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, DIAS_MAXIMO,
                                 senal, pendiente, UMBRAL_CAIDA_FILTRO, ACTIVACION_ACTUAL, RETROCESO_ACTUAL)
    r_b = _simular_trade_manual_racha_4h(df, df4h, inicio4h, fin4h, idx_entrada, direccion, precio_entrada,
                                          niveles, DIAS_MAXIMO, senal, pendiente4h, UMBRAL_CAIDA_FILTRO,
                                          VELAS_PERSISTENCIA)
    if r_a is None or r_b is None:
        return None
    _, precio_a, motivo_a = r_a
    _, precio_b, motivo_b = r_b
    pnl_a = (precio_a / precio_entrada - 1) * signo * 100
    pnl_b = (precio_b / precio_entrada - 1) * signo * 100
    return motivo_a, pnl_a, motivo_b, pnl_b


def analizar(moneda, año, atr):
    df, df4h, inicio4h, fin4h, _, rt, rs, pendiente, pendiente4h = _cargar_4h(moneda)
    cand = candidatos_por_año(df, año)
    close = df["close"].to_numpy()

    resultados = []
    abierta_hasta = -1
    for idx, direccion, prob in cand:
        if np.isnan(atr[idx]) or idx <= abierta_hasta:
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = rt if direccion == "largo" else rs
        r = _resolver_ambos(df, df4h, inicio4h, fin4h, idx, direccion, close[idx], niveles,
                             senal, pendiente, pendiente4h)
        if r is None:
            continue
        motivo_a, pnl_a, motivo_b, pnl_b = r
        # avanzamos el calendario con el mecanismo ACTUAL (el que esta en produccion hoy) para
        # decidir cuando se abre la siguiente operacion real -- asi cada señal analizada es una
        # que de verdad ocurriria en el calendario de produccion, no una hipotetica
        r_a_full = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                                          senal, pendiente, UMBRAL_CAIDA_FILTRO, ACTIVACION_ACTUAL,
                                          RETROCESO_ACTUAL)
        abierta_hasta = r_a_full[0]
        solo_racha = motivo_a == "senal_externa" or motivo_b == "senal_externa"
        resultados.append({
            "moneda": moneda, "año": año, "idx": idx, "direccion": direccion,
            "motivo_a": motivo_a, "pnl_a": pnl_a, "motivo_b": motivo_b, "pnl_b": pnl_b,
            "difiere": motivo_a != motivo_b or abs(pnl_a - pnl_b) > 0.01,
            "solo_racha": solo_racha,
        })
    return resultados


if __name__ == "__main__":
    from laboratorio.patrones.trailing_retroceso_alto import _cargar as _cargar_atr_helper
    todos = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        _, atr, *_ = _cargar_atr_helper(moneda)
        for año in AÑOS:
            todos.extend(analizar(moneda, año, atr))

    difs = [r for r in todos if r["difiere"]]
    print(f"Total señales evaluadas: {len(todos)} | difieren actual vs 4h: {len(difs)}\n")

    gana_4h = sum(1 for r in difs if r["pnl_b"] > r["pnl_a"])
    gana_actual = sum(1 for r in difs if r["pnl_a"] > r["pnl_b"])
    print(f"De las que difieren: 4h mejor en {gana_4h}, actual mejor en {gana_actual}, empate en {len(difs) - gana_4h - gana_actual}")
    exceso_medio = sum(r["pnl_b"] - r["pnl_a"] for r in difs) / len(difs)
    print(f"Diferencia media de pnl (4h - actual) en las que difieren: {exceso_medio:+.2f} puntos porcentuales\n")

    print(f"{'moneda':<9}{'año':<6}{'dir':<7}{'motivo_actual':<16}{'pnl_a':>8}   {'motivo_4h':<16}{'pnl_b':>8}   quien_gana")
    for r in sorted(difs, key=lambda r: (r["moneda"], r["año"], r["idx"])):
        quien = "4H" if r["pnl_b"] > r["pnl_a"] else ("ACTUAL" if r["pnl_a"] > r["pnl_b"] else "=")
        print(f"{r['moneda']:<9}{r['año']:<6}{r['direccion']:<7}{r['motivo_a']:<16}{r['pnl_a']:>7.2f}%   "
              f"{r['motivo_b']:<16}{r['pnl_b']:>7.2f}%   {quien}")

    print("\n=== Por año ===")
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        for año in AÑOS:
            sub = [r for r in difs if r["moneda"] == moneda and r["año"] == año]
            if not sub:
                continue
            g4h = sum(1 for r in sub if r["pnl_b"] > r["pnl_a"])
            gact = sum(1 for r in sub if r["pnl_a"] > r["pnl_b"])
            exc = sum(r["pnl_b"] - r["pnl_a"] for r in sub) / len(sub)
            print(f"  {moneda} {año}: {len(sub)} señales distintas -- 4h gana {g4h}, actual gana {gact}, exceso medio {exc:+.2f}pp")
