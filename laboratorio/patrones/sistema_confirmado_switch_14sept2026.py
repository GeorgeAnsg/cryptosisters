"""
14-sept-2026: PARAMETROS CONFIRMADOS para el escenario "cambio de
candidato fuerte" (switch) tras la sesion de ajuste de racha rota. Este
fichero es la fuente de la verdad de los valores validados -- no volver a
barrer estos numeros sin una razon nueva y sin repetir la validacion
cruzada completa (ETH ajuste -> BTC confirmacion -> multi-anio 2021-2024).

Cambios respecto al sistema anterior (K_ATR_STOP=2.5, R_FIJO=3.0, sin
filtro de pendiente sobre racha rota):

  1. UMBRAL_CAIDA_RELATIVA_PENDIENTE = 0.30
     Racha rota deja de cortar de inmediato: solo se honra el aviso
     cuando la pendiente (ATR-normalizada) ha caido un 30% relativo desde
     el maximo propio de ESA operacion. Arregla el caso hipersensible
     (cortar ganadores sanos en su respiracion normal). Ver
     prueba_racha_filtrada_por_caida_pendiente.py. Multi-anio: 5/8.

  2. K_ATR_STOP = 1.2  (antes 2.5)
     El stop-loss anterior era objetivamente demasiado ancho (media 12.6%,
     hasta 22% en algunos trades de 2024). Ver prueba_stop_mas_ceñido.py.
     Multi-anio en este valor: 8/8, y estable en toda la meseta 1.15-1.5
     (no es un punto de suerte).

  3. R_FIJO = 4.0  (antes 3.0)
     Reajustado JUNTO con el stop nuevo (el objetivo depende del riesgo,
     que acaba de cambiar). Ver prueba_stop_y_objetivo_conjunto.py.
     Multi-anio: 8/8.

  4. VENTA_PARCIAL: opcional, mejora pequeña (+1.6% en ETH 2024, 6/8
     multi-anio) pero no critica. UMBRAL_GANANCIA_VENTA_PARCIAL=0.20,
     PORCENTAJE_VENTA=0.50. Ver prueba_venta_parcial.py.

PROBLEMA CONOCIDO, DELIBERADAMENTE NO RESUELTO (racha rota "ciega"):
operaciones que suben 10-25% de forma limpia y luego bajan LENTO y en
zigzag (0.7-0.9%/dia) sin que el detector de doble techo/suelo llegue a
confirmar nunca un patron -- acaban perdiendo aunque llegaron a ganar
mucho. Se probaron 8 mecanismos de "proteccion de ganancia" distintos
(pendiente independiente, retroceso, velocidad de subida, trailing-stop
por ATR, objetivo en escalera, stop a breakeven, venta parcial sensible,
umbral dinamico por regimen de amplitud) -- TODOS fallan en validacion
multi-anio en cuanto se hacen lo bastante sensibles para arreglar estos
casos concretos, porque entonces cortan de mas otros trades sanos. La
causa raiz es de DETECCION (el patron geometrico no se forma a tiempo),
no de gestion de la salida -- la solucion real necesitaria un motor de
compresion/canal/cono nuevo, fuera del alcance de esta sesion.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, MULTIPLICADOR_MAX, MULTIPLICADOR_MIN, N_LEN, M_DIAS, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

# ---- parametros confirmados (no tocar sin re-validar) ----
UMBRAL_SWITCH = 0.0
UMBRAL_CAIDA_RELATIVA_PENDIENTE = 0.30
K_ATR_STOP = 1.2
R_FIJO = 4.0
UMBRAL_GANANCIA_VENTA_PARCIAL = 0.20
PORCENTAJE_VENTA_PARCIAL = 0.50


def simular_trade(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                   senal_externa, pendiente, usar_venta_parcial=True):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    venta_hecha = False
    fraccion_restante = 1.0
    pnl_parcial_por_unidad = 0.0
    fecha_venta_parcial = None
    precio_venta_parcial = None
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        if usar_venta_parcial and not venta_hecha:
            if direccion == "largo":
                ganancia_pct = (high[i] - precio_entrada) / precio_entrada
            else:
                ganancia_pct = (precio_entrada - low[i]) / precio_entrada
            if ganancia_pct >= UMBRAL_GANANCIA_VENTA_PARCIAL:
                venta_hecha = True
                precio_venta_parcial = precio_entrada * (1 + UMBRAL_GANANCIA_VENTA_PARCIAL) if direccion == "largo" \
                    else precio_entrada * (1 - UMBRAL_GANANCIA_VENTA_PARCIAL)
                fecha_venta_parcial = i
                signo = 1 if direccion == "largo" else -1
                pnl_parcial_por_unidad = PORCENTAJE_VENTA_PARCIAL * signo * (precio_venta_parcial - precio_entrada)
                fraccion_restante = 1.0 - PORCENTAJE_VENTA_PARCIAL

        if direccion == "largo":
            toca_stop = low[i] <= niveles.stop
            toca_objetivo = high[i] >= niveles.objetivo
        else:
            toca_stop = high[i] >= niveles.stop
            toca_objetivo = low[i] <= niveles.objetivo
        if toca_stop:
            return dict(idx_salida=i, precio_salida=niveles.stop, motivo="stop",
                        fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad,
                        idx_venta_parcial=fecha_venta_parcial, precio_venta_parcial=precio_venta_parcial)
        if toca_objetivo:
            return dict(idx_salida=i, precio_salida=niveles.objetivo, motivo="objetivo",
                        fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad,
                        idx_venta_parcial=fecha_venta_parcial, precio_venta_parcial=precio_venta_parcial)

        if senal_externa is not None and senal_externa[i]:
            p = pendiente[i]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                    listón = pendiente_extremo * (1 - UMBRAL_CAIDA_RELATIVA_PENDIENTE)
                    honra_corte = pendiente_extremo <= 0 or p <= listón
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
                    listón = pendiente_extremo * (1 - UMBRAL_CAIDA_RELATIVA_PENDIENTE)
                    honra_corte = pendiente_extremo >= 0 or p >= listón
                if honra_corte:
                    return dict(idx_salida=i, precio_salida=close[i], motivo="senal_externa",
                                fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad,
                                idx_venta_parcial=fecha_venta_parcial, precio_venta_parcial=precio_venta_parcial)
            else:
                return dict(idx_salida=i, precio_salida=close[i], motivo="senal_externa",
                            fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad,
                            idx_venta_parcial=fecha_venta_parcial, precio_venta_parcial=precio_venta_parcial)
        else:
            p = pendiente[i]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
    return dict(idx_salida=fin, precio_salida=close[fin], motivo="tiempo_maximo",
                fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad,
                idx_venta_parcial=fecha_venta_parcial, precio_venta_parcial=precio_venta_parcial)


def simular_cuenta(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente, fechas, usar_venta_parcial=True):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pendiente, usar_venta_parcial)
        if r is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        r.update(idx_entrada=idx, direccion=direccion, probabilidad=prob,
                  precio_entrada=close[idx], unidades=pos.unidades)
        return r

    def _cerrar(pos, motivo_switch=None):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl_resto = pos["unidades"] * pos["fraccion_restante"] * (pos["precio_salida"] - pos["precio_entrada"]) * signo
        pnl_parcial = pos["unidades"] * pos["pnl_parcial_por_unidad"]
        pnl = pnl_resto + pnl_parcial
        capital += pnl
        trades.append({
            "direccion": pos["direccion"],
            "fecha_entrada": str(fechas.iloc[pos["idx_entrada"]].date()),
            "fecha_salida": str(fechas.iloc[pos["idx_salida"]].date()),
            "precio_entrada": round(float(pos["precio_entrada"]), 2),
            "precio_salida": round(float(pos["precio_salida"]), 2),
            "motivo": motivo_switch if motivo_switch else pos["motivo"],
            "pnl_eur": round(float(pnl), 2),
            "capital_tras": round(float(capital), 2),
        })

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["idx_salida"]:
            _cerrar(abierta)
            abierta = None
        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= UMBRAL_SWITCH:
            abierta["idx_salida"] = idx
            abierta["precio_salida"] = close[idx]
            _cerrar(abierta, motivo_switch="cambio_candidato_fuerte")
            nueva = _abrir(idx, direccion, prob)
            abierta = nueva

    if abierta is not None:
        _cerrar(abierta)

    valores = [CAPITAL_INICIAL] + [t["capital_tras"] for t in trades]
    valores = np.array(valores)
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, trades, ganadoras, drawdown_max_pct


def cargar_datos(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="sistema_confirmado_switch_14sept2026")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente


if __name__ == "__main__":
    print("=== Sistema confirmado 14-sept-2026: K_ATR_STOP=1.2, R_FIJO=4.0, caida_relativa=30%, venta_parcial=20%/50% ===\n")
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = cargar_datos(moneda)
        print(f"-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap, trades, gan, dd = simular_cuenta(df, cand, atr, rt, rs, pendiente, df["open_time"])
            print(f"  {año}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- {len(trades)} trades, "
                  f"{gan} ganadoras ({gan/len(trades)*100:.0f}%), drawdown maximo {dd:.2f}%")
        print()
