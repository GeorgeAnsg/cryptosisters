"""
14-sept-2026: idea del usuario -- el mercado alterna entre fases de
movimientos amplios (expansion) y fases de movimientos comprimidos
(contraccion). Propuesta: en vez de un umbral fijo de venta parcial (20%,
prueba_venta_parcial.py), medir la amplitud de los ULTIMOS swings
confirmados (los mismos puntos de maximo/minimo que ya usa racha_rota) y,
si el ultimo tramo fue inusualmente amplio, asumir que viene compresion y
tomar beneficio parcial ANTES (umbral mas bajo) en esa operacion concreta.

Medicion: se fusionan los puntos de techo y suelo confirmados (mismos que
usa racha_rota) en una sola secuencia cronologica de swings. Para cada
swing, amplitud = |precio_actual - precio_anterior| / precio_anterior. En
el momento de abrir un trade, se mira la amplitud del ULTIMO swing
completado antes de esa fecha, dividido por la MEDIANA de amplitud de los
`VENTANA_SWINGS` swings anteriores a ese -- eso da un ratio de "cuan
grande fue el ultimo movimiento comparado con lo normal reciente". Si el
ratio supera UMBRAL_EXPANSION, se usa un umbral de venta parcial mas bajo
(UMBRAL_GANANCIA_COMPRIMIDO) para esa operacion; si no, el umbral normal
(UMBRAL_GANANCIA_NORMAL = 20%, el ya validado).

Barrido de UMBRAL_EXPANSION x UMBRAL_GANANCIA_COMPRIMIDO. Sobre el sistema
final ya elegido (K=1.2, R_FIJO=4.0, racha_rota+caida 30%, venta parcial
50%). Ajuste SOLO en ETH 2024, confirmacion sin tocar nada en BTC 2024,
multi-anio despues.
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

UMBRAL_SWITCH = 0.0
UMBRAL_CAIDA_FILTRO = 0.3
K_ATR_STOP = 1.2
R_FIJO = 4.0
PORCENTAJE_VENTA = 0.5
UMBRAL_GANANCIA_NORMAL = 0.20
VENTANA_SWINGS = 4

UMBRAL_EXPANSION_GRID = [999, 3.0, 2.5, 2.0, 1.5, 1.25]
UMBRAL_GANANCIA_COMPRIMIDO_GRID = [0.06, 0.08, 0.10, 0.12, 0.15]


def _serie_amplitud_regimen(df, puntos_techo, puntos_suelo, ventana_swings):
    """Para cada dia i, ratio = amplitud del ultimo swing completado antes
    de i / mediana de amplitud de los `ventana_swings` swings previos a ese.
    NaN si no hay suficiente historia."""
    close = df["close"].to_numpy()
    n = len(df)
    swings = sorted(puntos_techo + puntos_suelo, key=lambda x: x[0])
    amplitudes = []  # (idx_swing, amplitud_pct)
    for k in range(1, len(swings)):
        idx_a, precio_a = swings[k - 1]
        idx_b, precio_b = swings[k]
        amp = abs(precio_b - precio_a) / precio_a
        amplitudes.append((idx_b, amp))

    ratio = np.full(n, np.nan)
    j = 0  # puntero sobre `amplitudes`
    for i in range(n):
        while j < len(amplitudes) and amplitudes[j][0] <= i:
            j += 1
        # amplitudes[0:j] son los swings completados hasta el dia i (inclusive)
        if j >= ventana_swings + 1:
            ultimo = amplitudes[j - 1][1]
            previos = [a for _, a in amplitudes[j - 1 - ventana_swings:j - 1]]
            mediana_previa = np.median(previos)
            if mediana_previa > 0:
                ratio[i] = ultimo / mediana_previa
    return ratio


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           senal_externa, pendiente, umbral_caida_filtro, umbral_ganancia_pct, porcentaje_venta):
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
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        if not venta_hecha:
            if direccion == "largo":
                ganancia_pct = (high[i] - precio_entrada) / precio_entrada
            else:
                ganancia_pct = (precio_entrada - low[i]) / precio_entrada
            if ganancia_pct >= umbral_ganancia_pct:
                venta_hecha = True
                precio_venta = precio_entrada * (1 + umbral_ganancia_pct) if direccion == "largo" else precio_entrada * (1 - umbral_ganancia_pct)
                signo = 1 if direccion == "largo" else -1
                pnl_parcial_por_unidad = porcentaje_venta * signo * (precio_venta - precio_entrada)
                fraccion_restante = 1.0 - porcentaje_venta

        if direccion == "largo":
            toca_stop = low[i] <= niveles.stop
            toca_objetivo = high[i] >= niveles.objetivo
        else:
            toca_stop = high[i] >= niveles.stop
            toca_objetivo = low[i] <= niveles.objetivo
        if toca_stop:
            return i, niveles.stop, "stop", fraccion_restante, pnl_parcial_por_unidad
        if toca_objetivo:
            return i, niveles.objetivo, "objetivo", fraccion_restante, pnl_parcial_por_unidad

        if senal_externa is not None and senal_externa[i]:
            p = pendiente[i]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                    listón = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = pendiente_extremo <= 0 or p <= listón
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
                    listón = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = pendiente_extremo >= 0 or p >= listón
                if honra_corte:
                    return i, close[i], "senal_externa", fraccion_restante, pnl_parcial_por_unidad
            else:
                return i, close[i], "senal_externa", fraccion_restante, pnl_parcial_por_unidad
        else:
            p = pendiente[i]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
    return fin, close[fin], "tiempo_maximo", fraccion_restante, pnl_parcial_por_unidad


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente, ratio_regimen,
             umbral_switch, umbral_caida, umbral_expansion, umbral_ganancia_comprimido):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _umbral_para(idx):
        if umbral_expansion < 999 and not np.isnan(ratio_regimen[idx]) and ratio_regimen[idx] >= umbral_expansion:
            return umbral_ganancia_comprimido
        return UMBRAL_GANANCIA_NORMAL

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        umbral_g = _umbral_para(idx)
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pendiente,
                                   umbral_caida, umbral_g, PORCENTAJE_VENTA)
        if r is None:
            return None
        idx_salida, precio_salida, motivo, fraccion_restante, pnl_parcial_por_unidad = r
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return {"idx_entrada": idx, "direccion": direccion, "probabilidad": prob,
                "idx_salida": idx_salida, "precio_entrada": close[idx], "precio_salida": precio_salida,
                "unidades": pos.unidades, "fraccion_restante": fraccion_restante,
                "pnl_parcial_por_unidad": pnl_parcial_por_unidad}

    def _cerrar(pos, idx_cierre, precio_cierre, fraccion_restante=1.0, pnl_parcial_por_unidad=0.0):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl_resto = pos["unidades"] * fraccion_restante * (precio_cierre - pos["precio_entrada"]) * signo
        pnl_parcial = pos["unidades"] * pnl_parcial_por_unidad
        capital += pnl_resto + pnl_parcial
        curva.append((fechas.iloc[idx_cierre], capital))
        trades.append({"pnl_eur": pnl_resto + pnl_parcial})

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["idx_salida"]:
            _cerrar(abierta, abierta["idx_salida"], abierta["precio_salida"], abierta["fraccion_restante"], abierta["pnl_parcial_por_unidad"])
            abierta = None
        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= umbral_switch:
            _cerrar(abierta, idx, close[idx], abierta["fraccion_restante"], abierta["pnl_parcial_por_unidad"])
            nueva = _abrir(idx, direccion, prob)
            abierta = nueva

    if abierta is not None:
        _cerrar(abierta, abierta["idx_salida"], abierta["precio_salida"], abierta["fraccion_restante"], abierta["pnl_parcial_por_unidad"])

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, len(trades), ganadoras, drawdown_max_pct


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_venta_parcial_dinamica_regimen")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    ratio_regimen = _serie_amplitud_regimen(df, puntos_techo, puntos_suelo, VENTANA_SWINGS)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente, ratio_regimen


def ajuste_eth_2024():
    print("=== Ajuste: venta parcial DINAMICA por regimen de amplitud -- SOLO ETH 2024 ===")
    df, atr, rt, rs, pendiente, ratio_regimen = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    cap_base, n_b, gan_b, dd_b = _simular(df, cand, atr, rt, rs, pendiente, ratio_regimen, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 999, 0.1)
    print(f"  baseline (umbral fijo 20%, sin regimen): {cap_base:.2f}€ -- {n_b} trades, {gan_b} ganadoras, dd {dd_b:.2f}%")
    mejor = None
    for ue in UMBRAL_EXPANSION_GRID:
        if ue >= 999:
            continue
        for ugc in UMBRAL_GANANCIA_COMPRIMIDO_GRID:
            cap, n, gan, dd = _simular(df, cand, atr, rt, rs, pendiente, ratio_regimen, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, ue, ugc)
            print(f"  umbral_expansion={ue}x, umbral_ganancia_comprimido={ugc:.0%}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n} trades, {gan} ganadoras ({gan/n*100:.0f}%), dd {dd:.2f}%")
            if mejor is None or cap > mejor[2]:
                mejor = (ue, ugc, cap)
    print(f"  -> mejor: umbral_expansion={mejor[0]}x, umbral_ganancia_comprimido={mejor[1]:.0%} ({mejor[2]:.2f}€) vs baseline {cap_base:.2f}€")
    return mejor[0], mejor[1]


def confirmar_y_multi_anio(ue_elegido, ugc_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con umbral_expansion={ue_elegido}x, umbral_ganancia_comprimido={ugc_elegido:.0%} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente, ratio_regimen = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a = _simular(df, cand, atr, rt, rs, pendiente, ratio_regimen, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 999, 0.1)
            cap_nuevo, n_n, gan_n, dd_n = _simular(df, cand, atr, rt, rs, pendiente, ratio_regimen, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, ue_elegido, ugc_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: fijo20% {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"regimen {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append(gana)
    print(f"\nResultado: gana en {sum(resultados)} de {len(resultados)} combinaciones")


if __name__ == "__main__":
    ue, ugc = ajuste_eth_2024()
    confirmar_y_multi_anio(ue, ugc)
