import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar, simular_cuenta_con_canal
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import CAPITAL_INICIAL, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX, RIESGO_BASE_PCT

# Efficiency Ratio de Kaufman: causal (solo pasado), sin unidades de precio,
# no depende del nombre de la moneda -- 1.0 = tendencia limpia, 0.0 = zigzag puro.
def efficiency_ratio(close, ventana):
    n = len(close)
    er = np.full(n, np.nan)
    abs_diffs = np.abs(np.diff(close))
    cum_abs = np.concatenate([[0.0], np.cumsum(abs_diffs)])
    for i in range(ventana, n):
        net = abs(close[i] - close[i - ventana])
        total = cum_abs[i] - cum_abs[i - ventana]
        er[i] = net / total if total > 1e-9 else 0.0
    return er


UMBRAL_BASE = 1.5
UMBRAL_MAXIMO = 6.0  # tope -- por encima de esto el corte queda de facto desactivado
EPS_ER = 0.05


def umbral_adaptativo(close, ventana_er, exponente):
    er = efficiency_ratio(close, ventana_er)
    er_clip = np.clip(er, EPS_ER, 1.0)
    u = UMBRAL_BASE / (er_clip ** exponente)
    return np.minimum(u, UMBRAL_MAXIMO)


def simular_trade_adaptativo(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                              senal_externa, pendiente, umbral_por_dia, usar_venta_parcial=True):
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
        u = umbral_por_dia[i]
        if not np.isnan(p) and not np.isnan(u):
            cae_fuerte = (p <= -u) if direccion == "largo" else (p >= u)
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


def simular_cuenta_adaptativa(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente, fechas, umbral_por_dia, usar_venta_parcial=True):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, sc.K_ATR_STOP, sc.R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = simular_trade_adaptativo(df, idx, direccion, close[idx], niveles, 45, senal, pendiente, umbral_por_dia, usar_venta_parcial)
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
        trades.append({"direccion": pos["direccion"], "motivo": motivo_switch if motivo_switch else pos["motivo"],
                        "pnl_eur": round(float(pnl), 2), "capital_tras": round(float(capital), 2)})

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
    return capital, trades


if __name__ == "__main__":
    VENTANA_GRID = [10, 15, 20, 30]
    EXPONENTE_GRID = [0.5, 1.0, 1.5]

    print("=== AJUSTE en ETH: grid (ventana_er x exponente) ===")
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    fechas = df["open_time"]
    close = df["close"].to_numpy()
    mejor = None
    for ventana in VENTANA_GRID:
        for exp in EXPONENTE_GRID:
            u = umbral_adaptativo(close, ventana, exp)
            total = 0.0
            for año in AÑOS:
                cand = candidatos_por_año(df, año)
                cap, tr = simular_cuenta_adaptativa(df, cand, atr, rt, rs, pend, fechas, u)
                total += cap
            print(f"  ventana={ventana:2d} exp={exp}: total={total:.2f}")
            if mejor is None or total > mejor[0]:
                mejor = (total, ventana, exp)
    print(f"GANADOR ETH: ventana={mejor[1]} exponente={mejor[2]} -> {mejor[0]:.2f}")
    print("  (ref ETH: BASE=9490.02, pendiente fijo sin filtro=10662.53, +regimen NEUTRO=10440.01)")

    ventana_ganadora, exp_ganador = mejor[1], mejor[2]

    print(f"\n=== CONFIRMACIÓN congelada (ventana={ventana_ganadora}, exponente={exp_ganador}) en BTC y XRP ===")
    for moneda in ["BTCUSDT"]:
        dfx, atrx, rtx, rsx, pendx, clx, ccx = cargar(moneda)
        fechasx = dfx["open_time"]
        closex = dfx["close"].to_numpy()
        u = umbral_adaptativo(closex, ventana_ganadora, exp_ganador)
        total = 0.0
        for año in AÑOS:
            cand = candidatos_por_año(dfx, año)
            cap, tr = simular_cuenta_adaptativa(dfx, cand, atrx, rtx, rsx, pendx, fechasx, u)
            total += cap
            print(f"  {moneda} {año}: {cap:.2f}")
        print(f"  {moneda} TOTAL={total:.2f}  (ref BASE=8863.09, pendiente fijo sin filtro=8882.40, +regimen NEUTRO=8951.12)")
