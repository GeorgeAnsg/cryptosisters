import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar, simular_cuenta_con_canal
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import CAPITAL_INICIAL, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX, RIESGO_BASE_PCT
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano
from laboratorio.patrones import canal_flexible as cf
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = sc.K_ATR_STOP, sc.R_FIJO, 45
UMBRAL_PENDIENTE = 1.5


def _en_lateral(df, umbral_prob_lateral):
    n = len(df)
    cands = cf.detectar_lateral(df)
    activo = np.zeros(n, dtype=bool)
    for c in cands:
        if c.probabilidad_forma >= umbral_prob_lateral:
            activo[c.idx_fondo1:c.idx_pico2 + 1] = True
    return activo


def simular_trade_filtrado(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                            senal_externa, pendiente, umbral, en_lateral, usar_venta_parcial=True):
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
        if not np.isnan(p) and not en_lateral[i]:
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


def simular_cuenta_filtrada(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente, fechas, umbral, en_lateral, usar_venta_parcial=True):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = simular_trade_filtrado(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pendiente, umbral, en_lateral, usar_venta_parcial)
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
        trades.append({"direccion": pos["direccion"], "fecha_entrada": str(fechas.iloc[pos["idx_entrada"]].date()),
                        "fecha_salida": str(fechas.iloc[pos["idx_salida"]].date()),
                        "precio_entrada": round(float(pos["precio_entrada"]), 2), "precio_salida": round(float(pos["precio_salida"]), 2),
                        "motivo": motivo_switch if motivo_switch else pos["motivo"],
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


UMBRAL_LATERAL_GRID = [0.5, 0.6, 0.7, 0.8]

print("=== AJUSTE en ETH: umbral pendiente=1.5 fijo, grid del umbral de 'es lateral' ===")
df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
fechas = df["open_time"]
mejor = None
for ul in UMBRAL_LATERAL_GRID:
    en_lat = _en_lateral(df, ul)
    total = 0.0
    for año in AÑOS:
        cand = candidatos_por_año(df, año)
        cap, tr = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, en_lat)
        total += cap
    dias_suprimidos = en_lat.sum()
    print(f"  umbral_lateral={ul}: suma capital={total:.2f}  (dias marcados lateral: {dias_suprimidos}/{len(df)})")
    if mejor is None or total > mejor[0]:
        mejor = (total, ul)
print(f"GANADOR ETH: umbral_lateral={mejor[1]} -> {mejor[0]:.2f}  (ref: pendiente sin filtro=10662.53, BASE=9490.02)")

print("\n=== BTC: mismo grid, viendo especificamente 2023 (el año roto) ===")
df2, atr2, rt2, rs2, pend2, cl2, cc2 = cargar("BTCUSDT")
fechas2 = df2["open_time"]
for ul in UMBRAL_LATERAL_GRID:
    en_lat2 = _en_lateral(df2, ul)
    fila = f"  umbral_lateral={ul}:"
    total = 0.0
    for año in AÑOS:
        cand = candidatos_por_año(df2, año)
        cap, tr = simular_cuenta_filtrada(df2, cand, atr2, rt2, rs2, pend2, fechas2, UMBRAL_PENDIENTE, en_lat2)
        total += cap
        if año == 2023:
            fila += f"  2023={cap:.0f}"
    fila += f"   TOTAL={total:.2f}"
    print(fila)
print(f"  referencia: BASE total=8863.09 (2023 BASE=2161) | pendiente sin filtro total=8882.40 (2023 sin filtro=1612.98)")
