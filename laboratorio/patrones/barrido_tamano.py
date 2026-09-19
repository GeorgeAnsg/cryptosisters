"""
Barrido de los parametros de `tamano/tamano.py` -- pendiente que quedo
abierto tras construir `calcular_tamano()` (14-sept-2026): riesgo_base_pct
y multiplicador_min/max eran valores razonables elegidos a mano, no
barridos ("no absolutos", skill:deteccion-flexible-patrones).

A diferencia del barrido de R/k_atr_stop/dias_maximo en `salidas/`
(observacion 0011 de task-observer: ese barrido no tenia freno porque
"objetivo mas lejano + mas tiempo" converge sin limite a comprar-y-aguantar
en una muestra alcista), el tamaño de posicion SI tiene un freno natural
real: al reinvertir un % fijo del capital ACTUAL en cada operacion
(apuesta de fraccion fija), arriesgar demasiado castiga el crecimiento
COMPUESTO por "lastre de volatilidad" (el mismo mecanismo detras de por
que Kelly completo arruina y los fondos usan una fraccion) -- eso SI puede
dar un optimo interior de verdad, no hace falta corregir por benchmark
aqui porque el efecto que se mide (crecimiento geometrico compuesto) es
precisamente lo que EL TAMAÑO controla, no un efecto de deriva de mercado
disfrazado.

Disciplina "una idea a la vez" (la misma que exigio el usuario para las
señales de salida): PRIMERO se barre riesgo_base_pct solo (multiplicador
fijo en 1.0, sin escalado por probabilidad, para aislar el efecto de T1).
DESPUES, con el riesgo_base_pct ganador fijo, se barre multiplicador_min/max
(T2) comparando contra la config plana (1.0, 1.0) como baseline explicito.

Cuenta secuencial (sin solapamiento, igual simplificacion que
`prueba_cuenta_1000e.py` -- el orden/solape real de operaciones es trabajo
de `cartera/`, que no existe todavia). Aqui SI es la metrica correcta medir
en la cuenta compuesta (a diferencia de la leccion de la observacion 0010):
alli el problema era que la VELOCIDAD de la salida cambiaba cuantas
operaciones caben; aqui el tamaño no cambia ni cuando se abre ni cuando se
cierra ninguna operacion -- mismos candidatos, mismo orden, mismos cierres,
solo cambia cuanto dinero se apuesta en cada una.

Metricas: capital final, CAGR (crecimiento geometrico anualizado) y
drawdown maximo -- y un Calmar (CAGR / |drawdown maximo|) como resumen
riesgo/recompensa de la curva de capital (aqui SI es correcto usar un
ratio sobre la curva de capital, porque el orden y el solapamiento no
cambian entre configuraciones, no como en la comparacion de salidas).

Config de salida ya aceptada el 14-sept-2026 (ver salidas/README.md):
k_atr_stop=2.5, r_fijo=3.0, dias_maximo=45, señal de patron contrario con
umbral=0.7.

Validacion cruzada de siempre: barrido en ETH, confirmacion en BTC sin
retocar nada. Poblacion completa de Desarrollo (no solo 2024), para tener
mas operaciones y menos ruido de muestra pequeña.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

CAPITAL_INICIAL = 1000.0
K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45  # config de salidas/ ya aceptada
UMBRAL_CONTRARIA = 0.7  # ya aceptado en salidas/README.md

RIESGO_BASE_PCT_GRID = [0.005, 0.01, 0.015, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20]
# pares (min, max) a comparar en la Fase 2 -- (1.0, 1.0) = plano, sin escalado, es el baseline
MULTIPLICADOR_GRID = [
    (1.0, 1.0),
    (0.9, 1.1),
    (0.8, 1.2),
    (0.7, 1.3),
    (0.5, 1.5),
    (0.3, 1.7),
    (0.6, 1.0),
    (1.0, 1.4),
]


def _candidatos(df):
    out = []
    for c in techo_motor.detectar(df):
        r = en_vivo_techo(df, c.idx_techo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_techo2, "corto", r.probabilidad_total_si_confirma))
    for c in suelo_motor.detectar(df):
        r = en_vivo_suelo(df, c.idx_fondo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_fondo2, "largo", r.probabilidad_total_si_confirma))
    return sorted(out, key=lambda c: c[0])


def _prob_contraria(df):
    n = len(df)
    close = df["close"].to_numpy()
    prob_para_corto = np.full(n, np.nan)
    prob_para_largo = np.full(n, np.nan)
    for idx in minimos_aparentes(close):
        r = en_vivo_suelo(df, idx, dia_transcurrido=0)
        if r is not None:
            prob_para_corto[idx] = r.probabilidad_total_si_confirma
    for idx in maximos_aparentes(close):
        r = en_vivo_techo(df, idx, dia_transcurrido=0)
        if r is not None:
            prob_para_largo[idx] = r.probabilidad_total_si_confirma
    return prob_para_corto, prob_para_largo


def _resolver_trades(df, candidatos, atr, senal_corto, senal_largo):
    """Resuelve la secuencia de trades UNA VEZ (misma para cualquier
    tamaño -- el tamaño no afecta que se abre, cuando, ni cuando se
    cierra). Devuelve [(idx_entrada, idx_salida, riesgo_por_unidad,
    retorno_precio_por_unidad, probabilidad)]."""
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    trades = []
    idx_libre_desde = 0
    for idx, direccion, prob in candidatos:
        if idx < idx_libre_desde or np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = senal_corto if direccion == "corto" else senal_largo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is None:
            continue
        signo = 1 if direccion == "largo" else -1
        cambio_precio_por_unidad = (t.precio_salida - t.precio_entrada) * signo
        trades.append({
            "idx_entrada": t.idx_entrada, "idx_salida": t.idx_salida,
            "riesgo_por_unidad": niveles.riesgo, "cambio_precio_por_unidad": cambio_precio_por_unidad,
            "probabilidad": prob,
            "dias_entrada": fechas.iloc[t.idx_entrada], "dias_salida": fechas.iloc[t.idx_salida],
        })
        idx_libre_desde = t.idx_salida + 1
    return trades


def _simular_cuenta(trades, riesgo_base_pct, multiplicador_min, multiplicador_max):
    capital = CAPITAL_INICIAL
    curva = [capital]
    for tr in trades:
        pos = calcular_tamano(capital, tr["riesgo_por_unidad"], tr["probabilidad"],
                               riesgo_base_pct, multiplicador_min, multiplicador_max)
        pnl = pos.unidades * tr["cambio_precio_por_unidad"]
        capital = max(capital + pnl, 1e-6)  # evita capital <=0 en un escenario de riesgo extremo
        curva.append(capital)
    curva = np.array(curva)
    pico = np.maximum.accumulate(curva)
    drawdown_max_pct = float(((curva - pico) / pico).min()) * 100 if len(curva) > 1 else 0.0

    dias_totales = (trades[-1]["dias_salida"] - trades[0]["dias_entrada"]).days if trades else 0
    años = max(dias_totales / 365.0, 1e-6)
    cagr_pct = ((curva[-1] / CAPITAL_INICIAL) ** (1 / años) - 1) * 100 if curva[-1] > 0 else -100.0
    calmar = cagr_pct / abs(drawdown_max_pct) if drawdown_max_pct < 0 else float("inf")

    return {"capital_final": round(float(curva[-1]), 2), "cagr_pct": round(cagr_pct, 2),
            "drawdown_max_pct": round(drawdown_max_pct, 2), "calmar": round(calmar, 3)}


def _en_el_borde(valor, grid):
    return valor in (min(grid), max(grid))


def main():
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_tamano")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_tamano")

    print("=== FASE 1: riesgo_base_pct (multiplicador fijo en 1.0, sin escalado) ===")
    print("--- ETH (ajuste) ---")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    prob_corto_eth, prob_largo_eth = _prob_contraria(eth)
    senal_corto_eth = prob_corto_eth >= UMBRAL_CONTRARIA
    senal_largo_eth = prob_largo_eth >= UMBRAL_CONTRARIA
    trades_eth = _resolver_trades(eth, cand_eth, atr_eth, senal_corto_eth, senal_largo_eth)
    print(f"candidatos ETH: {len(cand_eth)} -- trades resueltos (sin solapamiento): {len(trades_eth)}")

    resultados_riesgo = []
    for riesgo_pct in RIESGO_BASE_PCT_GRID:
        r = _simular_cuenta(trades_eth, riesgo_pct, 1.0, 1.0)
        resultados_riesgo.append({"riesgo_base_pct": riesgo_pct, **r})
    for r in resultados_riesgo:
        print(" ", r)
    mejor_riesgo = max(resultados_riesgo, key=lambda r: r["calmar"] if np.isfinite(r["calmar"]) else -1e9)
    print(f"  mejor por CALMAR: {mejor_riesgo} -- "
          f"{'EN EL BORDE' if _en_el_borde(mejor_riesgo['riesgo_base_pct'], RIESGO_BASE_PCT_GRID) else 'dentro del rango'}")

    print("\n--- BTC (confirmacion, sin tocar el riesgo_base_pct ganador) ---")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    prob_corto_btc, prob_largo_btc = _prob_contraria(btc)
    senal_corto_btc = prob_corto_btc >= UMBRAL_CONTRARIA
    senal_largo_btc = prob_largo_btc >= UMBRAL_CONTRARIA
    trades_btc = _resolver_trades(btc, cand_btc, atr_btc, senal_corto_btc, senal_largo_btc)
    print(f"candidatos BTC: {len(cand_btc)} -- trades resueltos: {len(trades_btc)}")
    r_btc = _simular_cuenta(trades_btc, mejor_riesgo["riesgo_base_pct"], 1.0, 1.0)
    print(f"  riesgo_base_pct={mejor_riesgo['riesgo_base_pct']} en BTC -> {r_btc}")

    print("\n=== FASE 2: multiplicador_min/max (T2), riesgo_base_pct fijo en el ganador de la Fase 1 ===")
    riesgo_ganador = mejor_riesgo["riesgo_base_pct"]
    print(f"--- ETH (ajuste, riesgo_base_pct={riesgo_ganador}) ---")
    resultados_mult = []
    for mmin, mmax in MULTIPLICADOR_GRID:
        r = _simular_cuenta(trades_eth, riesgo_ganador, mmin, mmax)
        resultados_mult.append({"multiplicador_min": mmin, "multiplicador_max": mmax, **r})
    for r in resultados_mult:
        print(" ", r)
    baseline = next(r for r in resultados_mult if r["multiplicador_min"] == 1.0 and r["multiplicador_max"] == 1.0)
    mejor_mult = max(resultados_mult, key=lambda r: r["calmar"] if np.isfinite(r["calmar"]) else -1e9)
    print(f"  baseline plano (1.0, 1.0): {baseline}")
    print(f"  mejor por CALMAR: {mejor_mult}")

    print(f"\n--- BTC (confirmacion, riesgo_base_pct={riesgo_ganador}, sin tocar el multiplicador ganador) ---")
    r_baseline_btc = _simular_cuenta(trades_btc, riesgo_ganador, 1.0, 1.0)
    r_mult_btc = _simular_cuenta(trades_btc, riesgo_ganador, mejor_mult["multiplicador_min"], mejor_mult["multiplicador_max"])
    print(f"  baseline plano (1.0, 1.0) en BTC -> {r_baseline_btc}")
    print(f"  mejor multiplicador de ETH ({mejor_mult['multiplicador_min']}, {mejor_mult['multiplicador_max']}) en BTC -> {r_mult_btc}")


if __name__ == "__main__":
    main()
