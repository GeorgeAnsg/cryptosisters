"""
15-sept-2026, continuacion de prueba_toma_beneficio_contraria.py: esa
version usaba "en ganancia" = CUALQUIER avance a favor (close > entrada),
igual que ya esta implementado en salidas/stop_objetivo.py. El barrido
mostro que activar la proteccion tan pronto (con solo un poco de ganancia)
sale caro: aunque SI arregla el caso concreto del 02-abr-2024 (umbral de
probabilidad 0.55-0.57 convierte esa perdida en ganancia), el efecto neto
en el año completo es peor que no tocar nada -- corta demasiadas otras
subidas sanas nada mas empezar a ganar un poco.

Aqui se prueba la idea tal como la planteo el usuario literalmente:
"cuando se esta ganando MAS DE UN X%" -- exigir un porcentaje minimo de
ganancia flotante (no solo "positiva") ademas del candidato contrario,
barriendo las DOS dimensiones (umbral de ganancia % y umbral de
probabilidad contraria) en vez de asumir "cualquier ganancia cuenta".
`salidas/stop_objetivo.py` no tiene ese umbral de % (solo el binario
"en_ganancia"), asi que aqui se reimplementa el bucle dia a dia -- no se
toca el modulo compartido, esto es exploracion de laboratorio.
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
from motores.volatilidad import atr_absoluto
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
GANANCIA_PCT_GRID = [0.03, 0.05, 0.08, 0.10, 0.15]
PROB_CONTRARIA_GRID = [0.5, 0.55, 0.6, 0.65, 0.7]


def _series_prob_contraria(df):
    n = len(df)
    close = df["close"].to_numpy()
    prob_techo_dia = np.zeros(n)
    prob_suelo_dia = np.zeros(n)
    for idx in maximos_aparentes(close):
        r = en_vivo_techo(df, idx, dia_transcurrido=0)
        if r is not None:
            prob_techo_dia[idx] = r.probabilidad_total_si_confirma
    for idx in minimos_aparentes(close):
        r = en_vivo_suelo(df, idx, dia_transcurrido=0)
        if r is not None:
            prob_suelo_dia[idx] = r.probabilidad_total_si_confirma
    return prob_techo_dia, prob_suelo_dia


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           senal_externa, prob_contraria, ganancia_pct_min, prob_contraria_min):
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
            ganancia_pct = close[i] / precio_entrada - 1
        else:
            toca_stop = high[i] >= niveles.stop
            toca_objetivo = low[i] <= niveles.objetivo
            ganancia_pct = 1 - close[i] / precio_entrada
        if toca_stop:
            return i, niveles.stop, "stop"
        if toca_objetivo:
            return i, niveles.objetivo, "objetivo"
        if senal_externa is not None and senal_externa[i]:
            return i, close[i], "senal_externa"
        if ganancia_pct >= ganancia_pct_min and prob_contraria[i] >= prob_contraria_min:
            return i, close[i], "toma_beneficio"
    return fin, close[fin], "tiempo_maximo"


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, prob_techo_dia, prob_suelo_dia,
             umbral_switch, ganancia_pct_min, prob_contraria_min):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        prob_contraria = prob_techo_dia if direccion == "largo" else prob_suelo_dia
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                                   senal, prob_contraria, ganancia_pct_min, prob_contraria_min)
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
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_toma_beneficio_pct")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    prob_techo_dia, prob_suelo_dia = _series_prob_contraria(df)
    return df, atr, racha_rota_techo, racha_rota_suelo, prob_techo_dia, prob_suelo_dia


def ajuste_eth_2024():
    print("=== Ajuste 2D (ganancia % minima x probabilidad contraria) -- SOLO ETH 2024 ===")
    df, atr, rt, rs, pt, ps = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    cap_base, n_b, gan_b, dd_b = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, 999, 999)
    print(f"  baseline (sin toma de beneficio): {cap_base:.2f}€ ({n_b} trades, {gan_b} ganadoras, dd {dd_b:.2f}%)")
    mejor = None
    for g in GANANCIA_PCT_GRID:
        for p in PROB_CONTRARIA_GRID:
            cap, n, gan, dd = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, g, p)
            marca = " <-- mejor hasta ahora" if mejor is None or cap > mejor[2] else ""
            print(f"  ganancia>={g:.0%} y prob_contraria>={p:.2f}: {cap:.2f}€ "
                  f"({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- {n} trades, {gan} ganadoras, dd {dd:.2f}%{marca}")
            if mejor is None or cap > mejor[2]:
                mejor = (g, p, cap)
    print(f"\n  -> mejor combinacion en ETH 2024: ganancia>={mejor[0]:.0%}, prob_contraria>={mejor[1]:.2f} ({mejor[2]:.2f}€)")
    print(f"  -> baseline: {cap_base:.2f}€ -- {'MEJORA' if mejor[2] > cap_base else 'NO mejora'} sobre baseline")
    return mejor[0], mejor[1], cap_base


def confirmar_y_multi_anio(g, p):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con ganancia>={g:.0%}, prob_contraria>={p:.2f} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pt, ps = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, 999, 999)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, pt, ps, UMBRAL_SWITCH, g, p)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con toma beneficio {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    g, p, cap_base = ajuste_eth_2024()
    confirmar_y_multi_anio(g, p)
