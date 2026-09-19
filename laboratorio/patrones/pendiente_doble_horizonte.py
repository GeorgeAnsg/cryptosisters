"""
Idea de DETECCION (no de reaccion), 15-sept-2026: pendiente_acelerada mide
solo un movimiento de 5 dias, sin preguntar si la tendencia de fondo
sigue intacta -- por eso confunde un respiro dentro de una subida fuerte
(BTC 2023, XRP 2024) con una reversion real. Se añade una segunda
pendiente, de horizonte mas largo (mismo ATR como referencia, solo
cambia la ventana de dias), y solo se corta si LAS DOS van en contra de
la posicion a la vez -- si la tendencia larga sigue a favor, un tropiezo
corto no corta.

Distinto de los 8 filtros de contexto ya descartados: no trae un
indicador EXTERNO (SMA200, dominancia, volumen) -- compara la propia
metrica de pendiente consigo misma a otra escala, evitando en principio
la trampa de "correlacionado con el propio evento de 5 dias" documentada
en las lecciones de esta sesion.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import CAPITAL_INICIAL, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX, RIESGO_BASE_PCT
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = sc.K_ATR_STOP, sc.R_FIJO, 45
UMBRAL_PENDIENTE = 1.5
MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}


def _pendiente_ventana(df, atr, ventana):
    close = df["close"].to_numpy()
    n = len(close)
    p = np.full(n, np.nan)
    for i in range(ventana, n):
        if not np.isnan(atr[i]) and atr[i] > 0:
            p[i] = (close[i] - close[i - ventana]) / atr[i]
    return p


def simular_trade_doble(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                         senal_externa, pendiente_corta, pendiente_larga, umbral_corta, umbral_larga,
                         usar_venta_parcial=True, modo="and"):
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

        pc, pl = pendiente_corta[i], pendiente_larga[i]
        if not np.isnan(pc):
            corta_en_contra = (pc <= -umbral_corta) if direccion == "largo" else (pc >= umbral_corta)
            disparar = corta_en_contra
            if corta_en_contra and modo == "and" and not np.isnan(pl):
                larga_en_contra = (pl <= -umbral_larga) if direccion == "largo" else (pl >= umbral_larga)
                disparar = larga_en_contra
            elif corta_en_contra and modo == "veto" and not np.isnan(pl):
                # vetar el corte SOLO si la tendencia larga sigue muy fuerte a favor
                larga_muy_a_favor = (pl >= umbral_larga) if direccion == "largo" else (pl <= -umbral_larga)
                disparar = not larga_muy_a_favor
            if disparar:
                return dict(idx_salida=i, precio_salida=close[i], motivo="pendiente_acelerada",
                            fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)

        if senal_externa is not None and senal_externa[i]:
            p_check = pc
            if np.isnan(p_check):
                return dict(idx_salida=i, precio_salida=close[i], motivo="racha_rota",
                            fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)
            if direccion == "largo":
                pendiente_extremo = max(pendiente_extremo, p_check)
                honra = pendiente_extremo <= 0 or p_check <= pendiente_extremo * (1 - sc.UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            else:
                pendiente_extremo = min(pendiente_extremo, p_check)
                honra = pendiente_extremo >= 0 or p_check >= pendiente_extremo * (1 - sc.UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            if honra:
                return dict(idx_salida=i, precio_salida=close[i], motivo="racha_rota",
                            fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)
        else:
            if not np.isnan(pc):
                pendiente_extremo = max(pendiente_extremo, pc) if direccion == "largo" else min(pendiente_extremo, pc)
    return dict(idx_salida=fin, precio_salida=close[fin], motivo="tiempo_maximo",
                fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)


def simular_cuenta_doble(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente_corta, pendiente_larga,
                          umbral_larga, fechas, umbral_corta=UMBRAL_PENDIENTE, modo="and"):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = simular_trade_doble(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal,
                                 pendiente_corta, pendiente_larga, umbral_corta, umbral_larga, modo=modo)
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


def total_año(df, atr, rt, rs, pend_corta, pend_larga, umbral_larga, fechas, modo="and"):
    total = 0.0
    for año in AÑOS:
        cand = candidatos_por_año(df, año)
        total += simular_cuenta_doble(df, cand, atr, rt, rs, pend_corta, pend_larga, umbral_larga, fechas, modo=modo)
    return total


if __name__ == "__main__":
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    fechas = df["open_time"]

    print("=== DOBLE HORIZONTE -- grid en ETH (ventana_larga x umbral_larga) ===")
    mejor = None
    for ventana_l in [15, 20, 30, 45, 60]:
        pend_larga = _pendiente_ventana(df, atr, ventana_l)
        for umbral_l in [0.5, 1.0, 1.5, 2.0, 3.0]:
            t = total_año(df, atr, rt, rs, pend, pend_larga, umbral_l, fechas)
            print(f"  ventana_larga={ventana_l:2d} umbral_larga={umbral_l}: total={t:.2f}")
            if mejor is None or t > mejor[0]:
                mejor = (t, ventana_l, umbral_l)
    print(f"GANADOR: {mejor}  (ref ETH: BASE=9490.02, pendiente sin filtro=10662.53)")

    ventana_g, umbral_g = mejor[1], mejor[2]
    print(f"\n=== CONFIRMACION CONGELADA (ventana_larga={ventana_g}, umbral_larga={umbral_g}) en BTC y XRP ===")
    for nombre, cargador in [("BTC", lambda: cargar("BTCUSDT")), ("XRP", cargar_xrp)]:
        dfx, atrx, rtx, rsx, pendx, clx, ccx = cargador()
        fechasx = dfx["open_time"]
        pend_larga_x = _pendiente_ventana(dfx, atrx, ventana_g)
        por_año = {}
        total = 0.0
        for año in AÑOS:
            if (fechasx.dt.year == año).sum() <= 300:
                continue
            cand = candidatos_por_año(dfx, año)
            cap = simular_cuenta_doble(dfx, cand, atrx, rtx, rsx, pendx, pend_larga_x, umbral_g, fechasx)
            por_año[año] = round(cap, 2)
            total += cap
        print(f"  {nombre} TOTAL={total:.2f}  por_año={por_año}")
    print("  ref BTC: BASE=8863.09 (2023=2161), sin_filtro=8882.40 (2023=1612.98)")
    print("  ref XRP: BASE=7222.06, sin_filtro=7451.85")
