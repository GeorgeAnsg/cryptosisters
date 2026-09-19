"""
18-sept-2026: sobre el arreglo de `racha_confirmacion_arreglo.py`
(extremo_activo -- corrige el caso real del corto ETH 04-may-2022, pero NO
generaliza como cambio universal: 3/8 en holdout, se estanca barriendo el
umbral 10%-70%), se prueba la idea que el usuario ya habia propuesto antes
de esa investigacion: bajar la confirmacion de racha_rota a resolucion de
4h, con PERSISTENCIA -- la misma idea que ya funciono para el trailing
(`trailing_4h_persistencia.py`, condicional: 8/8).

Motivacion: el arreglo diario o bien confirma DEMASIADO rapido (bug
original, extremo_activo=False siempre honra) o espera a que el CIERRE
DIARIO complete un ciclo entero de "pico + 30% de caida" (arreglo simple),
que en años erraticos (2021, 2024) es demasiado lento. A 4h, la pendiente
se recalcula 6 veces al dia en vez de 1 -- da la oportunidad de detectar
el pico y el enfriamiento del 30% DENTRO del mismo dia, sin ni la trampa
del dia-1 ni la lentitud del cierre diario. Se combina con `velas_persistencia`
(4h consecutivas cumpliendo la condicion) para filtrar ruido de una sola
mecha, igual que en el trailing.

ATR y ventana de pendiente reescalados a DIAS REALES, no a velas (regla del
proyecto -- portar un indicador entre timeframes sin esto infla o encoge la
ventana real): VELAS_POR_DIA_4H=6, ATR ventana=14 dias=84 velas de 4h,
M_DIAS=5 dias=30 velas de 4h (mismos dias que la version diaria).

Metodologia identica a las anteriores: velas_persistencia se barre SOLO en
ETH 2021-2023, se elige por robustez frente al sistema ACTUAL (diario, sin
ningun arreglo), y se confirma sin tocar nada en ETH-2024 + BTC completo.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from laboratorio.patrones.trailing_4h_persistencia import _indices_4h_por_dia
from laboratorio.patrones.trailing_retroceso_alto import (
    UMBRAL_CAIDA_FILTRO, UMBRAL_SWITCH, _cargar, _simular,
)
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

VELAS_POR_DIA_4H = 6
VENTANA_ATR_DIAS = 14
M_DIAS = 5

VELAS_PERSISTENCIA_GRID = [1, 2, 3, 4, 5, 6]  # 1 vela=4h .. 6 velas=un dia entero


def _pendiente_atr_4h(df4h, atr4h):
    close = df4h["close"].to_numpy()
    n = len(close)
    ventana = M_DIAS * VELAS_POR_DIA_4H
    pendiente = np.full(n, np.nan)
    for i in range(ventana, n):
        if not np.isnan(atr4h[i]) and atr4h[i] > 0:
            pendiente[i] = (close[i] - close[i - ventana]) / atr4h[i]
    return pendiente


def _cargar_4h(moneda):
    df, atr, rt, rs, pendiente = _cargar(moneda)
    df4h = cargar_ohlcv_lab(moneda, "4h", estrategia="racha_confirmacion_4h")
    inicio4h, fin4h = _indices_4h_por_dia(df, df4h)
    atr4h = atr_absoluto(df4h, ventana=VENTANA_ATR_DIAS * VELAS_POR_DIA_4H)
    pendiente4h = _pendiente_atr_4h(df4h, atr4h)
    return df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente, pendiente4h


def _simular_trade_manual_racha_4h(df, df4h, inicio4h, fin4h, idx_entrada, direccion, precio_entrada,
                                    niveles, dias_maximo, senal_externa, pendiente4h,
                                    umbral_caida_filtro, velas_persistencia):
    """Igual que `_simular_trade_manual_arreglado` (extremo_activo), pero la
    confirmacion de racha_rota se evalua a 4h con persistencia, en vez de
    una vez al cierre del dia -- racha_rota en si sigue siendo un evento
    DIARIO (no se recalcula el patron a 4h, solo su confirmacion)."""
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


def _simular_racha_4h(df, df4h, inicio4h, fin4h, candidatos, atr, racha_rota_techo, racha_rota_suelo,
                       pendiente4h, umbral_switch, umbral_caida_filtro, velas_persistencia):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual_racha_4h(df, df4h, inicio4h, fin4h, idx, direccion, close[idx], niveles,
                                            DIAS_MAXIMO, senal, pendiente4h, umbral_caida_filtro, velas_persistencia)
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


UMBRAL_GRANDE_MULT_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]  # multiplo de ACTIVACION_CONFIRMADA (5%)
VELAS_PERSISTENCIA_COND_GRID = [1, 2, 3, 4, 5, 6]


def _simular_trade_manual_racha_4h_condicional(df, df4h, inicio4h, fin4h, idx_entrada, direccion, precio_entrada,
                                                niveles, dias_maximo, senal_externa, pendiente, pendiente4h,
                                                umbral_caida_filtro, velas_persistencia, umbral_grande_pct):
    """Decomponiendo operacion a operacion (18-sept-2026) se ve el patron
    INVERSO al del trailing: la confirmacion a 4h RESCATA operaciones que
    el sistema diario mandaba a `stop` (reacciona antes a una reversion
    real), pero RECORTA operaciones sanas que iban camino de `objetivo`/
    `tiempo_maximo` con ganancias grandes (una mecha normal de 4h dentro de
    una subida fuerte parece "reversion" a esa resolucion, cuando al cierre
    diario no lo es). Arreglo: usar la confirmacion a 4h+persistencia SOLO
    mientras la ganancia de pico siga siendo pequeña (< umbral_grande_pct);
    en cuanto se hace grande, volver al chequeo simple de una vez al dia
    (pendiente diaria, sin persistencia) -- el que ya protege bien a los
    ganadores grandes en el sistema actual."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close_d = df["close"].to_numpy()
    high4h = df4h["high"].to_numpy()
    low4h = df4h["low"].to_numpy()
    close4h = df4h["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None

    pendiente_extremo = 0.0
    extremo_activo = False
    racha_persistente = 0
    racha_rota_activa = False
    mejor_ganancia_pct = 0.0

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

        for j in range(inicio4h[dia], fin4h[dia]):
            if direccion == "largo":
                mejor_ganancia_pct = max(mejor_ganancia_pct, (high4h[j] - precio_entrada) / precio_entrada)
            else:
                mejor_ganancia_pct = max(mejor_ganancia_pct, (precio_entrada - low4h[j]) / precio_entrada)

        modo_pequeño = mejor_ganancia_pct < umbral_grande_pct

        if racha_rota_activa and modo_pequeño:
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
        elif racha_rota_activa:
            p = pendiente[dia]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                    listón_p = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = pendiente_extremo <= 0 or p <= listón_p
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
                    listón_p = pendiente_extremo * (1 - umbral_caida_filtro)
                    honra_corte = pendiente_extremo >= 0 or p >= listón_p
                if honra_corte:
                    return dia, close_d[dia], "senal_externa"
            else:
                return dia, close_d[dia], "senal_externa"
        else:
            p = pendiente[dia]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
    return fin, close_d[fin], "tiempo_maximo"


def _simular_racha_4h_condicional(df, df4h, inicio4h, fin4h, candidatos, atr, racha_rota_techo, racha_rota_suelo,
                                   pendiente, pendiente4h, umbral_switch, umbral_caida_filtro,
                                   velas_persistencia, umbral_grande_pct):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual_racha_4h_condicional(df, df4h, inicio4h, fin4h, idx, direccion, close[idx],
                                                        niveles, DIAS_MAXIMO, senal, pendiente, pendiente4h,
                                                        umbral_caida_filtro, velas_persistencia, umbral_grande_pct)
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


def seleccion_robusta_condicional(años_ajuste=(2021, 2022, 2023)):
    from laboratorio.patrones.trailing_retroceso_alto import ACTIVACION_CONFIRMADA
    df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente, pendiente4h = _cargar_4h("ETHUSDT")
    referencias = {}
    for año in años_ajuste:
        cand = candidatos_por_año(df, año)
        cap_actual, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
        referencias[año] = cap_actual

    print(f"=== Barrido condicional (umbral_grande x velas_persistencia) -- SOLO ETH {list(años_ajuste)} ===")
    resultados = []
    for mult in UMBRAL_GRANDE_MULT_GRID:
        umbral_grande = mult * ACTIVACION_CONFIRMADA
        for velas in VELAS_PERSISTENCIA_COND_GRID:
            victorias, exceso_total = 0, 0.0
            for año in años_ajuste:
                cand = candidatos_por_año(df, año)
                cap, *_ = _simular_racha_4h_condicional(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente,
                                                         pendiente4h, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, velas,
                                                         umbral_grande)
                cap_actual = referencias[año]
                if cap > cap_actual:
                    victorias += 1
                exceso_total += (cap - cap_actual) / cap_actual
            resultados.append((victorias, exceso_total, mult, velas))

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    print(f"{'umbral_x':>9} {'velas':>6} {'victorias':>10} {'exceso_medio':>13}")
    for v, exc, mult, velas in resultados[:10]:
        print(f"{mult:>8.1f}x {velas:>6} {v:>9}/{len(años_ajuste)} {exc/len(años_ajuste)*100:>11.2f}%")
    mejor = resultados[0]
    print(f"\n-> mas robusto: umbral_grande={mejor[2]:.1f}x activacion ({mejor[2]*ACTIVACION_CONFIRMADA:.1%}), velas_persistencia={mejor[3]}")
    return mejor[2] * ACTIVACION_CONFIRMADA, mejor[3]


def confirmar_holdout_condicional(umbral_grande_pct, velas_persistencia):
    print(f"\n=== Confirmacion holdout condicional (ETH-2024 + BTC completo), umbral_grande={umbral_grande_pct:.1%} velas={velas_persistencia} ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente, pendiente4h = _cargar_4h(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a, _ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                         UMBRAL_CAIDA_FILTRO, 0.10, 999)
            cap_c, n_c, gan_c, dd_c = _simular_racha_4h_condicional(df, df4h, inicio4h, fin4h, cand, atr, rt, rs,
                                                                     pendiente, pendiente4h, UMBRAL_SWITCH,
                                                                     UMBRAL_CAIDA_FILTRO, velas_persistencia,
                                                                     umbral_grande_pct)
            gana = cap_c > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"condicional {cap_c:.2f}€ ({n_c}/{gan_c}, dd {dd_c:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_actual, cap_c, gana))
        print()
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"Resultado: condicional gana en {n_gana} de {len(resultados)} combinaciones frente al actual")
    return resultados


def seleccion_robusta_4h(años_ajuste=(2021, 2022, 2023)):
    df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente, pendiente4h = _cargar_4h("ETHUSDT")
    referencias = {}
    for año in años_ajuste:
        cand = candidatos_por_año(df, año)
        cap_actual, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
        referencias[año] = cap_actual

    print(f"=== Barrido de persistencia (confirmacion racha_rota a 4h) -- SOLO ETH {list(años_ajuste)} ===")
    resultados = []
    for velas in VELAS_PERSISTENCIA_GRID:
        victorias, exceso_total = 0, 0.0
        detalle = []
        for año in años_ajuste:
            cand = candidatos_por_año(df, año)
            cap, *_ = _simular_racha_4h(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente4h,
                                         UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, velas)
            cap_actual = referencias[año]
            if cap > cap_actual:
                victorias += 1
            exceso_total += (cap - cap_actual) / cap_actual
            detalle.append(f"{año}:{cap:.0f}€({(cap/cap_actual-1)*100:+.1f}%)")
        resultados.append((victorias, exceso_total, velas))
        print(f"  velas={velas} ({velas*4}h): {victorias}/{len(años_ajuste)} victorias, exceso medio {exceso_total/len(años_ajuste)*100:+.2f}%   {' '.join(detalle)}")

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    mejor = resultados[0][2]
    print(f"\n-> mas robusto: velas_persistencia={mejor} ({resultados[0][0]}/{len(años_ajuste)} años mejora, exceso medio {resultados[0][1]/len(años_ajuste)*100:+.2f}%)")
    return mejor


def confirmar_holdout_4h(velas_persistencia):
    print(f"\n=== Confirmacion holdout (ETH-2024 + BTC completo), confirmacion racha_rota a 4h, velas_persistencia={velas_persistencia} ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente, pendiente4h = _cargar_4h(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a, _ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                         UMBRAL_CAIDA_FILTRO, 0.10, 999)
            cap_4h, n_4, gan_4, dd_4 = _simular_racha_4h(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente4h,
                                                          UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, velas_persistencia)
            gana = cap_4h > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"racha 4h persist={velas_persistencia} {cap_4h:.2f}€ ({n_4}/{gan_4}, dd {dd_4:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_actual, cap_4h, gana))
        print()
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"Resultado: racha 4h (persistencia={velas_persistencia}) gana en {n_gana} de {len(resultados)} combinaciones frente al actual")
    return resultados


if __name__ == "__main__":
    mejor = seleccion_robusta_4h()
    confirmar_holdout_4h(mejor)
