"""15-sept-2026: version correcta de la comparacion pedida por el usuario
-- las dos pruebas anteriores (`canal_como_senal_salida.py`,
`canal_senal_salida_sistema_confirmado.py`) se dejaban fuera el "cambio de
candidato fuerte" (switch), una pieza real y confirmada del sistema del
14-sept (`sistema_confirmado_switch_14sept2026.py`). Esta vez se reutiliza
ESE fichero sin tocar su logica de switch/cuenta secuencial/tamaño -- solo
se amplia `simular_trade` con una rama nueva (canal en contra, corte
inmediato) para poder comparar:

  A) BASE: el sistema de ayer, exactamente igual (switch + racha rota +
     venta parcial + tamaño real).
  B) BASE + CANAL: igual que A, pero dentro de cada operacion, si un canal
     en contra confirma, se corta ese mismo dia (ademas del switch y la
     racha rota, lo que llegue primero).

Metrica: capital final de la cuenta secuencial (igual que el sistema
original), por año y moneda -- comparacion directa, no aislada, porque
aqui el objetivo es "¿el sistema COMPLETO de ayer mejora si le añado
canal?", no aislar el efecto de una señal suelta.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import CAPITAL_INICIAL, MULTIPLICADOR_MAX, MULTIPLICADOR_MIN, RIESGO_BASE_PCT
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from motores import canal_ascendente, canal_descendente
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = sc.K_ATR_STOP, sc.R_FIJO, 45
UMBRAL_PROB_CANAL = 0.6  # ganador de la prueba de ayer


def _canal_en_contra(df):
    n = len(df)
    prob_largo = np.full(n, np.nan)
    prob_corto = np.full(n, np.nan)
    for c in canal_descendente.calcular(df):
        if c.confirmado:
            prob_largo[c.idx_confirmacion] = np.nanmax([prob_largo[c.idx_confirmacion], c.probabilidad_forma])
    for c in canal_ascendente.calcular(df):
        if c.confirmado:
            prob_corto[c.idx_confirmacion] = np.nanmax([prob_corto[c.idx_confirmacion], c.probabilidad_forma])
    return np.nan_to_num(prob_largo, nan=-1) >= UMBRAL_PROB_CANAL, np.nan_to_num(prob_corto, nan=-1) >= UMBRAL_PROB_CANAL


def simular_trade_con_canal(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                             senal_externa, pendiente, canal_directo, usar_venta_parcial=True):
    """Copia EXACTA de sc.simular_trade, con UNA rama nueva: `canal_directo`
    corta el mismo dia, evaluada justo antes de la racha rota (stop >
    objetivo > canal_directo > racha_rota > tiempo_maximo)."""
    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    venta_hecha = False
    fraccion_restante = 1.0
    pnl_parcial_por_unidad = 0.0
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        if usar_venta_parcial and not venta_hecha:
            ganancia_pct = (high[i] - precio_entrada) / precio_entrada if direccion == "largo" \
                else (precio_entrada - low[i]) / precio_entrada
            if ganancia_pct >= sc.UMBRAL_GANANCIA_VENTA_PARCIAL:
                venta_hecha = True
                precio_vp = precio_entrada * (1 + sc.UMBRAL_GANANCIA_VENTA_PARCIAL) if direccion == "largo" \
                    else precio_entrada * (1 - sc.UMBRAL_GANANCIA_VENTA_PARCIAL)
                signo = 1 if direccion == "largo" else -1
                pnl_parcial_por_unidad = sc.PORCENTAJE_VENTA_PARCIAL * signo * (precio_vp - precio_entrada)
                fraccion_restante = 1.0 - sc.PORCENTAJE_VENTA_PARCIAL

        toca_stop = low[i] <= niveles.stop if direccion == "largo" else high[i] >= niveles.stop
        toca_objetivo = high[i] >= niveles.objetivo if direccion == "largo" else low[i] <= niveles.objetivo
        if toca_stop:
            return dict(idx_salida=i, precio_salida=niveles.stop, motivo="stop",
                        fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)
        if toca_objetivo:
            return dict(idx_salida=i, precio_salida=niveles.objetivo, motivo="objetivo",
                        fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)

        if canal_directo is not None and canal_directo[i]:
            return dict(idx_salida=i, precio_salida=close[i], motivo="canal_en_contra",
                        fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)

        if senal_externa is not None and senal_externa[i]:
            p = pendiente[i]
            if np.isnan(p):
                return dict(idx_salida=i, precio_salida=close[i], motivo="racha_rota",
                            fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)
            if direccion == "largo":
                pendiente_extremo = max(pendiente_extremo, p)
                honra = pendiente_extremo <= 0 or p <= pendiente_extremo * (1 - sc.UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            else:
                pendiente_extremo = min(pendiente_extremo, p)
                honra = pendiente_extremo >= 0 or p >= pendiente_extremo * (1 - sc.UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            if honra:
                return dict(idx_salida=i, precio_salida=close[i], motivo="racha_rota",
                            fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)
        else:
            p = pendiente[i]
            if not np.isnan(p):
                pendiente_extremo = max(pendiente_extremo, p) if direccion == "largo" else min(pendiente_extremo, p)
    return dict(idx_salida=fin, precio_salida=close[fin], motivo="tiempo_maximo",
                fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)


def simular_cuenta_con_canal(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente,
                              canal_largo, canal_corto, fechas, usar_canal: bool, usar_venta_parcial=True):
    """Copia de sc.simular_cuenta (switch, tamaño, cuenta secuencial
    identicos) con la unica diferencia de llamar a simular_trade_con_canal
    y, si usar_canal=True, pasarle el canal en contra correspondiente."""
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        canal_dir = (canal_largo if direccion == "largo" else canal_corto) if usar_canal else None
        r = simular_trade_con_canal(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pendiente, canal_dir, usar_venta_parcial)
        if r is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        r.update(idx_entrada=idx, direccion=direccion, probabilidad=prob, precio_entrada=close[idx], unidades=pos.unidades)
        return r

    def _cerrar(pos, motivo_switch=None):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl_resto = pos["unidades"] * pos["fraccion_restante"] * (pos["precio_salida"] - pos["precio_entrada"]) * signo
        pnl_parcial = pos["unidades"] * pos["pnl_parcial_por_unidad"]
        pnl = pnl_resto + pnl_parcial
        capital += pnl
        trades.append({
            "direccion": pos["direccion"], "fecha_entrada": str(fechas.iloc[pos["idx_entrada"]].date()),
            "fecha_salida": str(fechas.iloc[pos["idx_salida"]].date()),
            "precio_entrada": round(float(pos["precio_entrada"]), 2), "precio_salida": round(float(pos["precio_salida"]), 2),
            "motivo": motivo_switch if motivo_switch else pos["motivo"],
            "pnl_eur": round(float(pnl), 2), "capital_tras": round(float(capital), 2),
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
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= sc.UMBRAL_SWITCH:
            abierta["idx_salida"] = idx
            abierta["precio_salida"] = close[idx]
            _cerrar(abierta, motivo_switch="cambio_candidato_fuerte")
            abierta = _abrir(idx, direccion, prob)

    if abierta is not None:
        _cerrar(abierta)

    valores = np.array([CAPITAL_INICIAL] + [t["capital_tras"] for t in trades])
    pico = np.maximum.accumulate(valores)
    dd = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, trades, ganadoras, dd


def cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="canal_sobre_sistema_completo")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    rt = _racha_rota(puntos_techo, sc.N_LEN, sc.M_DIAS, n, direccion_favorable="creciente")
    rs = _racha_rota(puntos_suelo, sc.N_LEN, sc.M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    canal_largo, canal_corto = _canal_en_contra(df)
    return df, atr, rt, rs, pendiente, canal_largo, canal_corto


if __name__ == "__main__":
    print("=== Sistema COMPLETO de ayer (switch + racha rota + venta parcial) vs +CANAL ===\n")
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pend, cl, cc = cargar(moneda)
        print(f"-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_a, tr_a, gan_a, dd_a = simular_cuenta_con_canal(df, cand, atr, rt, rs, pend, cl, cc, df["open_time"], usar_canal=False)
            cap_b, tr_b, gan_b, dd_b = simular_cuenta_con_canal(df, cand, atr, rt, rs, pend, cl, cc, df["open_time"], usar_canal=True)
            print(f"  {año}: BASE {cap_a:.2f}€ ({(cap_a/CAPITAL_INICIAL-1)*100:+.1f}%, {len(tr_a)} trades, {gan_a} ganadoras, dd {dd_a:.2f}%)"
                  f"   |   +CANAL {cap_b:.2f}€ ({(cap_b/CAPITAL_INICIAL-1)*100:+.1f}%, {len(tr_b)} trades, {gan_b} ganadoras, dd {dd_b:.2f}%)"
                  f"   {'MEJORA' if cap_b > cap_a else 'empeora'}")
        print()
