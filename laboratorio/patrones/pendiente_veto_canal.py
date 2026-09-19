"""
Variante de deteccion, 15-sept-2026: en vez de vetar el corte de
pendiente_acelerada con una media de pendiente sobre otra ventana (que
en ETH exige ventana=22 y en BTC 2023 no basta, ver diagnostico en
diagnostico_btc2023_veto.py), usar el propio canal ascendente/descendente
-- motor YA GRADUADO (validado con Monte Carlo en 5 monedas, puertas
1/4/5 pasadas) para reconocer tendencias sostenidas de meses -- como
señal de "la tendencia de fondo sigue viva, no cortes".

Un dia se marca "en tendencia confirmada" (a favor de un largo) si cae
dentro de [idx_fondo1, idx_confirmacion] de cualquier canal ascendente
CONFIRMADO -- y simetrico para corto con canal descendente.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import CAPITAL_INICIAL, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX, RIESGO_BASE_PCT
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.pendiente_filtro_lateral import UMBRAL_PENDIENTE
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano
from motores import canal_ascendente, canal_descendente
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = sc.K_ATR_STOP, sc.R_FIJO, 45
MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}


def _en_tendencia_confirmada(df, direccion, extension_dias=0, umbral_prob_forma=0.0):
    n = len(df)
    activo = np.zeros(n, dtype=bool)
    cands = canal_ascendente.calcular(df) if direccion == "largo" else canal_descendente.calcular(df)
    for c in cands:
        if c.confirmado and c.probabilidad_forma >= umbral_prob_forma:
            fin = min(c.idx_confirmacion + extension_dias, n - 1)
            activo[c.idx_fondo1:fin + 1] = True
    return activo


def simular_trade_veto_canal(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                              senal_externa, pendiente, umbral, en_tendencia, usar_venta_parcial=True):
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

        p = pendiente[i]
        if not np.isnan(p) and not en_tendencia[i]:
            cae_fuerte = (p <= -umbral) if direccion == "largo" else (p >= umbral)
            if cae_fuerte:
                return dict(idx_salida=i, precio_salida=close[i], motivo="pendiente_acelerada",
                            fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)

        if senal_externa is not None and senal_externa[i]:
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
            if not np.isnan(p):
                pendiente_extremo = max(pendiente_extremo, p) if direccion == "largo" else min(pendiente_extremo, p)
    return dict(idx_salida=fin, precio_salida=close[fin], motivo="tiempo_maximo",
                fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)


def simular_cuenta_veto_canal(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente, fechas,
                               en_tendencia_largo, en_tendencia_corto, umbral=UMBRAL_PENDIENTE):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        en_tend = en_tendencia_largo if direccion == "largo" else en_tendencia_corto
        r = simular_trade_veto_canal(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pendiente, umbral, en_tend)
        if r is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        r.update(idx_entrada=idx, direccion=direccion, probabilidad=prob, precio_entrada=close[idx], unidades=pos.unidades)
        return r

    def _cerrar(pos):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl_resto = pos["unidades"] * pos["fraccion_restante"] * (pos["precio_salida"] - pos["precio_entrada"]) * signo
        pnl_parcial = pos["unidades"] * pos["pnl_parcial_por_unidad"]
        capital += pnl_resto + pnl_parcial

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
            _cerrar(abierta)
            abierta = _abrir(idx, direccion, prob)

    if abierta is not None:
        _cerrar(abierta)
    return capital


if __name__ == "__main__":
    df, atr, rt, rs, pend, cl, cc = cargar("BTCUSDT")
    fechas = df["open_time"]
    en_largo = _en_tendencia_confirmada(df, "largo")
    en_corto = _en_tendencia_confirmada(df, "corto")

    print(f"BTC: dias en tendencia ascendente confirmada = {en_largo.sum()}/{len(df)}")
    print(f"BTC: dias en tendencia descendente confirmada = {en_corto.sum()}/{len(df)}")

    # Cuanto cubre esto exactamente en los 14 cortes de 2023 que ya diagnosticamos
    mask_2023 = (fechas.dt.year == 2023).to_numpy()
    print(f"Dias 2023 en tendencia ascendente confirmada: {en_largo[mask_2023].sum()}/{mask_2023.sum()}")

    total = 0.0
    por_año = {}
    for año in AÑOS:
        cand = candidatos_por_año(df, año)
        cap = simular_cuenta_veto_canal(df, cand, atr, rt, rs, pend, fechas, en_largo, en_corto)
        por_año[año] = round(cap, 2)
        total += cap
    print(f"BTC TOTAL={total:.2f}  por_año={por_año}")
    print("ref BTC: BASE=8863.09 (2023=2161), sin_filtro=8882.40 (2023=1612.98), veto_pendiente22=9180.77 (2023=1612.98)")
