"""
14-sept-2026: idea del usuario, distinta de prueba_toma_beneficio_pct.py.
Aquella probaba un umbral de GANANCIA TOTAL desde la entrada (ej. "si llevas
+15% desde que abriste, cierra") -- fue rechazada (2/8 multi-anio).

Esta es sobre la VELOCIDAD del movimiento, no la ganancia acumulada: si en
una ventana corta de N dias el precio se ha movido un % a favor de la
operacion (ej. +12% en 3-4 dias), cerrar -- sin esperar ningun patron de
giro (doble techo/suelo) ni que la ganancia total acumulada sea grande.
Motivado por el trade ETH largo 02-abr-2024 -> 03-may-2024: llega a +13.8%
en solo 6 dias sin que racha_rota se dispare nunca, y acaba perdiendo.

Barrido de ventana (dias) y umbral (%) simultaneo -- no un numero fijo a
ojo de cada uno. Ajuste SOLO en ETH 2024, confirmacion sin tocar nada en
BTC 2024, multi-anio despues si supera la confirmacion.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
VENTANA_DIAS_GRID = [3, 4, 5, 7, 10]
UMBRAL_VELOCIDAD_GRID = [0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 999]
# 999 = disparador desactivado (equivale al sistema actual sin este mecanismo)


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           ventana_dias, umbral_velocidad):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    for i in range(idx_entrada + 1, fin + 1):
        if direccion == "largo":
            toca_stop = low[i] <= niveles.stop
            toca_objetivo = high[i] >= niveles.objetivo
        else:
            toca_stop = high[i] >= niveles.stop
            toca_objetivo = low[i] <= niveles.objetivo
        if toca_stop:
            return i, niveles.stop, "stop"
        if toca_objetivo:
            return i, niveles.objetivo, "objetivo"
        if umbral_velocidad < 999:
            j = i - ventana_dias
            if j >= idx_entrada:
                if direccion == "largo":
                    variacion = (close[i] - close[j]) / close[j]
                else:
                    variacion = (close[j] - close[i]) / close[j]
                if variacion >= umbral_velocidad:
                    return i, close[i], "velocidad_subida"
    return fin, close[fin], "tiempo_maximo"


def _simular(df, candidatos, atr, umbral_switch, ventana_dias, umbral_velocidad):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, ventana_dias, umbral_velocidad)
        if r is None:
            return None
        idx_salida, precio_salida, motivo = r
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob,
                "idx_salida": idx_salida, "precio_entrada": close[idx], "precio_salida": precio_salida,
                "unidades": pos.unidades}

    def _cerrar(pos, idx_cierre, precio_cierre):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["precio_entrada"]) * signo
        capital += pnl
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({"pnl_eur": pnl})

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["idx_salida"]:
            _cerrar(abierta, abierta["idx_salida"], abierta["precio_salida"])
            abierta = None
        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= umbral_switch:
            _cerrar(abierta, idx, close[idx])
            nueva = _abrir(idx, direccion, prob)
            abierta = nueva

    if abierta is not None:
        _cerrar(abierta, abierta["idx_salida"], abierta["precio_salida"])

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, len(trades), ganadoras, drawdown_max_pct


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_toma_beneficio_por_velocidad")
    atr = atr_absoluto(df)
    return df, atr


def ajuste_eth_2024():
    print("=== Ajuste: toma de beneficio por VELOCIDAD (ventana dias x umbral %) -- SOLO ETH 2024 ===")
    df, atr = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    cap_base, n_b, gan_b, dd_b = _simular(df, cand, atr, UMBRAL_SWITCH, 3, 999)
    print(f"  baseline (sin disparador): {cap_base:.2f}€ ({(cap_base/CAPITAL_INICIAL-1)*100:+.1f}%) -- {n_b} trades, {gan_b} ganadoras, dd {dd_b:.2f}%")
    mejor = None
    for ventana in VENTANA_DIAS_GRID:
        for umbral in UMBRAL_VELOCIDAD_GRID:
            if umbral >= 999:
                continue
            cap, n, gan, dd = _simular(df, cand, atr, UMBRAL_SWITCH, ventana, umbral)
            print(f"  ventana={ventana}d, umbral={umbral:.0%}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n} trades, {gan} ganadoras, dd {dd:.2f}%")
            if mejor is None or cap > mejor[2]:
                mejor = (ventana, umbral, cap)
    print(f"  -> mejor: ventana={mejor[0]}d, umbral={mejor[1]:.0%} ({mejor[2]:.2f}€) vs baseline {cap_base:.2f}€")
    return mejor[0], mejor[1]


def confirmar_y_multi_anio(ventana_elegida, umbral_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con ventana={ventana_elegida}d, umbral={umbral_elegido:.0%} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, UMBRAL_SWITCH, ventana_elegida, 999)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, UMBRAL_SWITCH, ventana_elegida, umbral_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con velocidad {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    ventana, umbral = ajuste_eth_2024()
    confirmar_y_multi_anio(ventana, umbral)
