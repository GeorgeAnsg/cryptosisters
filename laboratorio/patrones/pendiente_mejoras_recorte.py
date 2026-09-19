"""
Tres variantes de pendiente_acelerada que NO son un filtro de contexto de
mercado (los 8 probados antes fallaron) -- cambian que HACE la propia
señal segun el estado de CADA operacion, algo estructuralmente distinto.
Motivadas por el analisis del 15-sept-2026: en tendencias fuertes (BTC
2023, XRP 2024), pendiente_acelerada cierra posiciones que YA IBAN MUY
GANADAS por un movimiento brusco que resulto ser solo una pausa, no una
reversion -- dejando sobre la mesa 300+€/año en objetivos que si se
habrian alcanzado sin el corte.

A) TRAILING TRAS COLCHON: si la posicion ya avanzo >= cushion_pct a favor
   cuando llega el corte, en vez de cerrar del todo se aprieta el stop
   (trailing por ATR) y se deja seguir -- protege lo ganado sin renunciar
   al resto de la tendencia. Si NO ha avanzado ese colchon, se cierra
   igual que antes (sin cambios para operaciones tempranas).
B) PERSISTENCIA: exige que el movimiento en contra se mantenga
   `n_persistencia` dias seguidos antes de cerrar -- filtra pausas de un
   solo dia.
C) CORTE PARCIAL: en el primer disparo, cierra solo una fraccion de la
   posicion (como la venta parcial) y deja correr el resto con el
   stop/objetivo normales.

Metodologia identica a todo lo demas esta sesion: grid + ajuste SOLO en
ETH, congelar, confirmar sin tocar nada en BTC y XRP. Vigilar el mismo
riesgo de siempre: si el ganador del grid cae en el borde del rango,
extenderlo antes de dar nada por bueno.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import CAPITAL_INICIAL, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX, RIESGO_BASE_PCT
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = sc.K_ATR_STOP, sc.R_FIJO, 45
UMBRAL_PENDIENTE = 1.5
MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}


def simular_trade_variante(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                            senal_externa, pendiente, umbral, atr_entrada,
                            variante, cushion_pct=None, k_atr_trailing=None,
                            n_persistencia=None, fraccion_corte=None,
                            usar_venta_parcial=True):
    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    venta_hecha = False
    fraccion_restante = 1.0
    pnl_parcial_por_unidad = 0.0
    pendiente_extremo = 0.0
    stop_efectivo = niveles.stop
    extremo_favorable = precio_entrada
    trailing_activo = False
    racha_persistente = 0
    corte_parcial_hecho = False

    for i in range(idx_entrada + 1, fin + 1):
        if usar_venta_parcial and not venta_hecha:
            ganancia_pct = (high[i] - precio_entrada) / precio_entrada if direccion == "largo" \
                else (precio_entrada - low[i]) / precio_entrada
            if ganancia_pct >= sc.UMBRAL_GANANCIA_VENTA_PARCIAL:
                venta_hecha = True
                precio_vp = precio_entrada * (1 + sc.UMBRAL_GANANCIA_VENTA_PARCIAL) if direccion == "largo" \
                    else precio_entrada * (1 - sc.UMBRAL_GANANCIA_VENTA_PARCIAL)
                signo = 1 if direccion == "largo" else -1
                pnl_parcial_por_unidad += sc.PORCENTAJE_VENTA_PARCIAL * fraccion_restante * signo * (precio_vp - precio_entrada)
                fraccion_restante *= (1.0 - sc.PORCENTAJE_VENTA_PARCIAL)

        if variante == "trailing" and trailing_activo:
            if direccion == "largo":
                extremo_favorable = max(extremo_favorable, high[i])
                stop_efectivo = max(stop_efectivo, extremo_favorable - k_atr_trailing * atr_entrada)
            else:
                extremo_favorable = min(extremo_favorable, low[i])
                stop_efectivo = min(stop_efectivo, extremo_favorable + k_atr_trailing * atr_entrada)

        toca_stop = low[i] <= stop_efectivo if direccion == "largo" else high[i] >= stop_efectivo
        toca_objetivo = high[i] >= niveles.objetivo if direccion == "largo" else low[i] <= niveles.objetivo
        if toca_stop:
            motivo = "stop_trailing" if trailing_activo else "stop"
            return dict(idx_salida=i, precio_salida=stop_efectivo, motivo=motivo,
                        fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)
        if toca_objetivo:
            return dict(idx_salida=i, precio_salida=niveles.objetivo, motivo="objetivo",
                        fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)

        p = pendiente[i]
        if not np.isnan(p):
            cae_fuerte = (p <= -umbral) if direccion == "largo" else (p >= umbral)

            if variante == "trailing":
                if cae_fuerte and not trailing_activo:
                    avance_pct = (close[i] / precio_entrada - 1) if direccion == "largo" else (1 - close[i] / precio_entrada)
                    if avance_pct >= cushion_pct:
                        trailing_activo = True
                        extremo_favorable = high[i] if direccion == "largo" else low[i]
                        stop_efectivo = max(stop_efectivo, extremo_favorable - k_atr_trailing * atr_entrada) if direccion == "largo" \
                            else min(stop_efectivo, extremo_favorable + k_atr_trailing * atr_entrada)
                    else:
                        return dict(idx_salida=i, precio_salida=close[i], motivo="pendiente_acelerada",
                                    fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)

            elif variante == "persistencia":
                racha_persistente = racha_persistente + 1 if cae_fuerte else 0
                if racha_persistente >= n_persistencia:
                    return dict(idx_salida=i, precio_salida=close[i], motivo="pendiente_acelerada",
                                fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)

            elif variante == "parcial":
                if cae_fuerte and not corte_parcial_hecho:
                    corte_parcial_hecho = True
                    signo = 1 if direccion == "largo" else -1
                    pnl_parcial_por_unidad += fraccion_corte * fraccion_restante * signo * (close[i] - precio_entrada)
                    fraccion_restante *= (1.0 - fraccion_corte)
                elif cae_fuerte and corte_parcial_hecho:
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


def simular_cuenta_variante(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente, fechas,
                             variante, **kwargs):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = simular_trade_variante(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal,
                                    pendiente, UMBRAL_PENDIENTE, atr[idx], variante, **kwargs)
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
            _cerrar(abierta, motivo_switch="cambio_candidato_fuerte")
            abierta = _abrir(idx, direccion, prob)

    if abierta is not None:
        _cerrar(abierta)
    return capital


def total_año(df, atr, rt, rs, pend, fechas, variante, **kwargs):
    total = 0.0
    for año in AÑOS:
        cand = candidatos_por_año(df, año)
        total += simular_cuenta_variante(df, cand, atr, rt, rs, pend, fechas, variante, **kwargs)
    return total


if __name__ == "__main__":
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    fechas = df["open_time"]

    print("=== A) TRAILING TRAS COLCHON -- grid en ETH ===")
    mejor_a = None
    for cushion in [0.02, 0.04, 0.06, 0.08, 0.10]:
        for k_trail in [1.0, 1.5, 2.0, 2.5]:
            t = total_año(df, atr, rt, rs, pend, fechas, "trailing", cushion_pct=cushion, k_atr_trailing=k_trail)
            print(f"  cushion={cushion} k_trail={k_trail}: total={t:.2f}")
            if mejor_a is None or t > mejor_a[0]:
                mejor_a = (t, cushion, k_trail)
    print(f"GANADOR A: {mejor_a}  (ref ETH: BASE=9490.02, pendiente sin filtro=10662.53)")

    print("\n=== B) PERSISTENCIA -- grid en ETH ===")
    mejor_b = None
    for n_p in [1, 2, 3, 4, 5]:
        t = total_año(df, atr, rt, rs, pend, fechas, "persistencia", n_persistencia=n_p)
        print(f"  n_persistencia={n_p}: total={t:.2f}")
        if mejor_b is None or t > mejor_b[0]:
            mejor_b = (t, n_p)
    print(f"GANADOR B: {mejor_b}")

    print("\n=== C) CORTE PARCIAL -- grid en ETH ===")
    mejor_c = None
    for frac in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        t = total_año(df, atr, rt, rs, pend, fechas, "parcial", fraccion_corte=frac)
        print(f"  fraccion_corte={frac}: total={t:.2f}")
        if mejor_c is None or t > mejor_c[0]:
            mejor_c = (t, frac)
    print(f"GANADOR C: {mejor_c}")

    print("\n" + "="*60)
    print("CONFIRMACION CONGELADA en BTC y XRP (sin tocar nada)")
    print("="*60)
    configs = {
        "A_trailing": dict(variante="trailing", cushion_pct=mejor_a[1], k_atr_trailing=mejor_a[2]),
        "B_persistencia": dict(variante="persistencia", n_persistencia=mejor_b[1]),
        "C_parcial": dict(variante="parcial", fraccion_corte=mejor_c[1]),
    }
    for nombre, cargador in [("BTC", lambda: cargar("BTCUSDT")), ("XRP", cargar_xrp)]:
        dfx, atrx, rtx, rsx, pendx, clx, ccx = cargador()
        fechasx = dfx["open_time"]
        for etiqueta, cfg in configs.items():
            t = total_año(dfx, atrx, rtx, rsx, pendx, fechasx, **cfg)
            print(f"  {nombre} {etiqueta}: total={t:.2f}")
    print("  ref BTC: BASE=8863.09, pendiente sin filtro=8882.40")
    print("  ref XRP: BASE=7222.06, pendiente sin filtro=7451.85")
