"""
18-sept-2026: el gating condicional por TAMANO de ganancia de la propia
operacion (`racha_confirmacion_4h.py::_simular_trade_manual_racha_4h_condicional`)
NO generaliza (3/8, peor que el 5/8 sin condicional) -- en BTC 2022 el
4h+persistencia tambien ayudaba en operaciones que acabaron con ganancia
grande, asi que forzar la vuelta a confirmacion diaria ahi quito
proteccion util. Ver `registro/intentos.jsonl`,
`racha_confirmacion_4h_condicional_por_ganancia`.

Mirando que AÑOS ganan con cada mecanismo (no que OPERACIONES): 2022 (ETH
y BTC) gana con la confirmacion diaria simple (extremo_activo); 2021,
2023, 2024 ganan con 4h+persistencia. 2022 es el año de un crash de
volatilidad extrema (Terra/Luna, luego FTX en el propio 2022); los otros
son mas erraticos/laterales. Hipotesis: la variable correcta no es cuanto
gana la operacion, es el REGIMEN DE VOLATILIDAD vigente en el momento de
la entrada -- en expansion fuerte de volatilidad, la confirmacion diaria
(mas lenta, deja correr el momentum) protege mejor; en regimen normal, el
4h+persistencia reacciona antes a reversiones reales sin ser tan lento.

Medida de regimen (causal, solo pasado): ratio entre el ATR del dia de
entrada y la MEDIANA de ese mismo ATR en los `VENTANA_BASELINE_DIAS` dias
anteriores. Ratio alto = volatilidad se ha disparado frente a su propio
historial reciente = regimen de expansion/crash. Se decide UNA VEZ por
operacion, en el momento de entrada (no a mitad de operacion), para que
la logica de confirmacion no cambie de mecanismo a mitad de camino.

El umbral de "regimen alto" (RATIO_REGIMEN_GRID) se barre como rango, no
como numero fijo (regla del proyecto, ver skill deteccion-flexible-patrones
/ memoria `feedback_no_absolutos_todo_el_codigo`) -- SOLO ETH 2021-2023
para elegir, confirmacion sin tocar nada en ETH-2024 + BTC completo.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from laboratorio.patrones.racha_confirmacion_4h import _cargar_4h
from laboratorio.patrones.trailing_retroceso_alto import (
    UMBRAL_CAIDA_FILTRO, UMBRAL_SWITCH, _simular,
)
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

VELAS_PERSISTENCIA_FIJO = 6  # punto mas robusto ya encontrado en racha_confirmacion_4h (5/8)
VENTANA_BASELINE_DIAS = 60
RATIO_REGIMEN_GRID = [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0, 2.5]


def _regimen_alto(atr, idx, ventana_baseline=VENTANA_BASELINE_DIAS):
    """Ratio ATR(idx) / mediana(ATR[idx-ventana:idx]). NaN si no hay historial
    suficiente (causal: solo mira hacia atras)."""
    if idx < ventana_baseline:
        return np.nan
    tramo = atr[idx - ventana_baseline:idx]
    tramo = tramo[~np.isnan(tramo)]
    if len(tramo) == 0:
        return np.nan
    baseline = np.median(tramo)
    if baseline <= 0 or np.isnan(atr[idx]):
        return np.nan
    return atr[idx] / baseline


def _simular_trade_manual_racha_regimen(df, df4h, inicio4h, fin4h, idx_entrada, direccion, precio_entrada,
                                         niveles, dias_maximo, senal_externa, pendiente, pendiente4h,
                                         umbral_caida_filtro, velas_persistencia, usa_diario):
    """Decide UNA VEZ (usa_diario, calculado en el momento de entrada segun
    el regimen de volatilidad) que mecanismo de confirmacion de racha_rota
    usar durante TODA la operacion: diario simple (extremo_activo, mejor en
    regimen de expansion/crash) o 4h+persistencia (mejor en regimen normal)."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close_d = df["close"].to_numpy()
    close4h = df4h["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None

    pendiente_extremo = 0.0
    extremo_activo = False
    racha_persistente = 0
    racha_rota_activa = False

    for dia in range(idx_entrada + 1, fin + 1):
        if direccion == "largo":
            toca_stop_dia = low[dia] <= niveles.stop
            toca_objetivo_dia = high[dia] >= niveles.objetivo
        else:
            toca_stop_dia = high[dia] >= niveles.stop
            toca_objetivo_dia = low[dia] <= niveles.objetivo
        if toca_stop_dia:
            return dia, niveles.stop, "stop"
        if toca_objetivo_dia:
            return dia, niveles.objetivo, "objetivo"

        if senal_externa is not None and senal_externa[dia]:
            racha_rota_activa = True

        if usa_diario:
            p = pendiente[dia]
            if racha_rota_activa:
                if np.isnan(p):
                    return dia, close_d[dia], "senal_externa"
                if direccion == "largo":
                    if p > 0:
                        pendiente_extremo = max(pendiente_extremo, p)
                        extremo_activo = True
                    listón_p = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = extremo_activo and p <= listón_p
                else:
                    if p < 0:
                        pendiente_extremo = min(pendiente_extremo, p)
                        extremo_activo = True
                    listón_p = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = extremo_activo and p >= listón_p
                if honra_corte:
                    return dia, close_d[dia], "senal_externa"
            else:
                if not np.isnan(p):
                    if direccion == "largo" and p > 0:
                        pendiente_extremo = max(pendiente_extremo, p)
                        extremo_activo = True
                    elif direccion == "corto" and p < 0:
                        pendiente_extremo = min(pendiente_extremo, p)
                        extremo_activo = True
        else:
            if racha_rota_activa:
                for j in range(inicio4h[dia], fin4h[dia]):
                    p = pendiente4h[j]
                    if np.isnan(p):
                        continue
                    if direccion == "largo":
                        if p > 0:
                            pendiente_extremo = max(pendiente_extremo, p)
                            extremo_activo = True
                        listón_p = pendiente_extremo * (1 - umbral_caida_filtro)
                        rompe = extremo_activo and p <= listón_p
                    else:
                        if p < 0:
                            pendiente_extremo = min(pendiente_extremo, p)
                            extremo_activo = True
                        listón_p = pendiente_extremo * (1 - umbral_caida_filtro)
                        rompe = extremo_activo and p >= listón_p
                    racha_persistente = racha_persistente + 1 if rompe else 0
                    if racha_persistente >= velas_persistencia:
                        return dia, close4h[j], "senal_externa"
            else:
                p = pendiente4h[fin4h[dia] - 1] if fin4h[dia] > inicio4h[dia] else np.nan
                if not np.isnan(p):
                    if direccion == "largo" and p > 0:
                        pendiente_extremo = max(pendiente_extremo, p)
                        extremo_activo = True
                    elif direccion == "corto" and p < 0:
                        pendiente_extremo = min(pendiente_extremo, p)
                        extremo_activo = True
    return fin, close_d[fin], "tiempo_maximo"


def _simular_racha_regimen(df, df4h, inicio4h, fin4h, candidatos, atr, racha_rota_techo, racha_rota_suelo,
                            pendiente, pendiente4h, umbral_switch, umbral_caida_filtro, velas_persistencia,
                            ratio_regimen):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        regimen = _regimen_alto(atr, idx)
        usa_diario = (not np.isnan(regimen)) and regimen >= ratio_regimen
        r = _simular_trade_manual_racha_regimen(df, df4h, inicio4h, fin4h, idx, direccion, close[idx], niveles,
                                                 DIAS_MAXIMO, senal, pendiente, pendiente4h, umbral_caida_filtro,
                                                 velas_persistencia, usa_diario)
        if r is None:
            return None
        idx_salida, precio_salida, motivo = r
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob,
                "idx_salida": idx_salida, "precio_entrada": close[idx], "precio_salida": precio_salida,
                "unidades": pos.unidades, "motivo": motivo}

    def _cerrar(pos, idx_cierre, precio_cierre):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_cierre - pos["precio_entrada"]) * signo
        capital += pnl
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({"pnl_eur": pnl, "motivo": pos.get("motivo")})

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


def seleccion_robusta_regimen(años_ajuste=(2021, 2022, 2023)):
    df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente, pendiente4h = _cargar_4h("ETHUSDT")
    referencias = {}
    for año in años_ajuste:
        cand = candidatos_por_año(df, año)
        cap_actual, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
        referencias[año] = cap_actual

    print(f"=== Barrido de regimen (ratio ATR/mediana{VENTANA_BASELINE_DIAS}d) -- SOLO ETH {list(años_ajuste)} ===")
    resultados = []
    for ratio in RATIO_REGIMEN_GRID:
        victorias, exceso_total = 0, 0.0
        detalle = []
        for año in años_ajuste:
            cand = candidatos_por_año(df, año)
            cap, *_ = _simular_racha_regimen(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente, pendiente4h,
                                              UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, VELAS_PERSISTENCIA_FIJO, ratio)
            cap_actual = referencias[año]
            if cap > cap_actual:
                victorias += 1
            exceso_total += (cap - cap_actual) / cap_actual
            detalle.append(f"{año}:{cap:.0f}€({(cap/cap_actual-1)*100:+.1f}%)")
        resultados.append((victorias, exceso_total, ratio))
        print(f"  ratio={ratio:.1f}x: {victorias}/{len(años_ajuste)} victorias, exceso medio {exceso_total/len(años_ajuste)*100:+.2f}%   {' '.join(detalle)}")

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    mejor = resultados[0][2]
    print(f"\n-> mas robusto: ratio_regimen={mejor:.1f}x ({resultados[0][0]}/{len(años_ajuste)} años mejora, exceso medio {resultados[0][1]/len(años_ajuste)*100:+.2f}%)")
    return mejor


def confirmar_holdout_regimen(ratio_regimen):
    print(f"\n=== Confirmacion holdout regimen (ETH-2024 + BTC completo), ratio_regimen={ratio_regimen:.1f}x, velas_persistencia={VELAS_PERSISTENCIA_FIJO} ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente, pendiente4h = _cargar_4h(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a, _ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                         UMBRAL_CAIDA_FILTRO, 0.10, 999)
            cap_r, n_r, gan_r, dd_r = _simular_racha_regimen(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente,
                                                              pendiente4h, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO,
                                                              VELAS_PERSISTENCIA_FIJO, ratio_regimen)
            gana = cap_r > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"regimen {cap_r:.2f}€ ({n_r}/{gan_r}, dd {dd_r:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_actual, cap_r, gana))
        print()
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"Resultado: regimen (ratio={ratio_regimen:.1f}x) gana en {n_gana} de {len(resultados)} combinaciones frente al actual")
    return resultados


if __name__ == "__main__":
    mejor = seleccion_robusta_regimen()
    confirmar_holdout_regimen(mejor)
