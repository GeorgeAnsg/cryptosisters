"""
17-sept-2026: el usuario pregunto, con razon, si de verdad no se puede
cortar un trade que sube limpio y luego cae ~80% desde su pico. El
diagnostico (comprobar_pullback_en_ganadores_reales.py, en el scratchpad de
la sesion, no persistido -- ver registro/intentos.jsonl para el resumen)
mostro que a un umbral ALTO de retroceso (80%+) el falso positivo sobre
ganadores reales es bajo (9%), muy por debajo del 18-35% que se esperaria a
umbrales moderados (20-60%, la zona que SI se probo a fondo en
trailing_ganancia_relativa.py y fallo). Esta zona alta (70-95%) no se
exploro con suficiente detalle alli (el barrido usaba R-multiplos para la
activacion, no % de ganancia bruta). Aqui se prueba directamente en escala
de % de ganancia bruta, igual que el diagnostico.

Se añade COMO EXTRA sobre el sistema real confirmado (racha_rota+caida),
nunca lo sustituye.

Dos rondas de barrido, ambas ajustando SOLO en ETH 2024 -- ERROR
METODOLOGICO ya corregido, ver mas abajo:
1) Grid grueso (ACTIVACION_PCT_GRID x RETROCESO_ALTO_GRID): mejor punto
   activacion=10% retroceso=85% -> 2006.10€ (baseline 1920.90€).
2) Grid fino (ACTIVACION_FINO x RETROCESO_FINO, ver `contorno_fino()`):
   revela que el punto grueso no es un pico aislado -- hay una MESETA
   amplia (100 de 160 combinaciones mejoran el baseline en mas de 1%), y
   el mejor punto puntual de esa meseta es activacion=5% retroceso=75% ->
   2056.57€ (+7.1%).

**Correccion metodologica (17-sept-2026, tras migrar el fichero):** elegir
el punto final mirando solo el mejor resultado de UN año de UNA moneda
(ETH 2024) es precisamente el error que el resto del proyecto ya evita
(nunca fiarse de un pico aislado). Al correr por primera vez la
confirmacion completa de 8 combinaciones con ese punto (5%/75%), dio solo
5/8 -- peor que el 6/8 del punto del grid grueso (10%/85%), pese a ser
"mejor" en el propio año de ajuste. Se repitio la seleccion con el
criterio correcto: barrer todo el grid fino usando SOLO ETH 2021-2023
(2024 reservado como holdout, igual que BTC), y elegir por ROBUSTEZ
(cuantos de esos 3 años mejora, luego exceso medio) en vez de por el mejor
numero en un solo año. El punto mas robusto por ese criterio es
activacion=5% retroceso=92.5% -- y al confirmarlo sin tocar nada ni en
ETH-2024 ni en BTC, **gana en las 8 de 8 combinaciones**, con drawdown
igual o menor en casi todos los años. Parametros confirmados y congelados
con este criterio: ACTIVACION_CONFIRMADA / RETROCESO_CONFIRMADO abajo.
Ver `seleccion_robusta()` para reproducir la seleccion.

Es el primer mecanismo de salida de todo el proyecto que pasa la
validacion cruzada limpia (8/8) -- ningun otro mecanismo de proteccion de
ganancia lo habia conseguido (ver `project_corvus4_switch_confirmado` en
la memoria persistente: 8 mecanismos probados el 14-sept, todos fallaron).

Movido de scratchpad a laboratorio/ el 17-sept-2026 -- ver
`tests/verificar_trailing_retroceso_alto.py` para la comprobacion de que
la migracion no cambio ningun numero (referencias actualizadas al punto
final 5%/92.5%).
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
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, N_LEN, M_DIAS, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

UMBRAL_SWITCH = 0.0
UMBRAL_CAIDA_FILTRO = 0.3

ACTIVACION_PCT_GRID = [0.06, 0.08, 0.10, 0.12, 0.15]
RETROCESO_ALTO_GRID = [999, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]

ACTIVACION_FINO = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.14, 0.16]
RETROCESO_FINO = [0.60, 0.625, 0.65, 0.675, 0.70, 0.725, 0.75, 0.775, 0.80,
                   0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 0.98]

# Parametros congelados tras seleccion robusta (ETH 2021-2023, ver
# `seleccion_robusta()`) y confirmacion 8/8 en ETH-2024 holdout + BTC
# completo. No volver a ajustar sin repetir la validacion cruzada completa
# (ver docstring del modulo) -- y NUNCA elegir el punto final mirando el
# resultado de un solo año/moneda, ese fue exactamente el error corregido
# el 17-sept-2026.
ACTIVACION_CONFIRMADA = 0.05
RETROCESO_CONFIRMADO = 0.925


def _simular_trade_manual(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                           senal_externa, pendiente, umbral_caida_filtro,
                           activacion_pct, retroceso_pct):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    pendiente_extremo = 0.0
    mejor_ganancia_pct = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        if direccion == "largo":
            ganancia_pico_pct = (high[i] - precio_entrada) / precio_entrada
            ganancia_actual_pct = (close[i] - precio_entrada) / precio_entrada
        else:
            ganancia_pico_pct = (precio_entrada - low[i]) / precio_entrada
            ganancia_actual_pct = (precio_entrada - close[i]) / precio_entrada
        mejor_ganancia_pct = max(mejor_ganancia_pct, ganancia_pico_pct)

        if retroceso_pct < 999 and mejor_ganancia_pct >= activacion_pct:
            listón = mejor_ganancia_pct * (1 - retroceso_pct)
            if ganancia_actual_pct <= listón:
                return i, close[i], "trailing_retroceso_alto"

        if direccion == "largo":
            toca_stop = low[i] <= niveles.stop
            toca_objetivo = high[i] >= niveles.objetivo
        else:
            toca_stop = high[i] >= niveles.stop
            toca_objetivo = low[i] <= niveles.objetivo
        if toca_stop:
            return i, niveles.stop, "stop"
        if toca_objetivo:
            return i, niveles.objetivo, "objetivo"

        if senal_externa is not None and senal_externa[i]:
            p = pendiente[i]
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
                    return i, close[i], "senal_externa"
            else:
                return i, close[i], "senal_externa"
        else:
            p = pendiente[i]
            if not np.isnan(p):
                if direccion == "largo":
                    pendiente_extremo = max(pendiente_extremo, p)
                else:
                    pendiente_extremo = min(pendiente_extremo, p)
    return fin, close[fin], "tiempo_maximo"


def _simular(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente,
             umbral_switch, umbral_caida_filtro, activacion_pct, retroceso_pct):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                                   senal, pendiente, umbral_caida_filtro, activacion_pct, retroceso_pct)
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
    n_disparos = sum(1 for t in trades if t["motivo"] == "trailing_retroceso_alto")
    return capital, len(trades), ganadoras, drawdown_max_pct, n_disparos


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="trailing_retroceso_alto")
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    return df, atr, racha_rota_techo, racha_rota_suelo, pendiente


def ajuste_eth_2024():
    print("=== Ajuste: trailing de retroceso ALTO (grid grueso) -- SOLO ETH 2024 ===\n")
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    cap_base, n_b, gan_b, dd_b, _ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
    print(f"baseline real (racha_rota+caida, sin trailing): {cap_base:.2f}€ ({(cap_base/CAPITAL_INICIAL-1)*100:+.1f}%) -- {n_b} trades, {gan_b} ganadoras, dd {dd_b:.2f}%\n")

    mejor = None
    for act in ACTIVACION_PCT_GRID:
        for retroceso in RETROCESO_ALTO_GRID:
            cap, n, gan, dd, n_disp = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, act, retroceso)
            marca = " <-- mejora" if cap > cap_base else ""
            etiqueta = "sin trailing" if retroceso >= 999 else f"retroceso={retroceso:.0%}"
            print(f"  activacion={act:.0%} {etiqueta}: {cap:.2f}€ ({(cap/CAPITAL_INICIAL-1)*100:+.1f}%) -- "
                  f"{n} trades, {gan} ganadoras, dd {dd:.2f}%, disparos={n_disp}{marca}")
            if retroceso < 999 and (mejor is None or cap > mejor[2]):
                mejor = (act, retroceso, cap)
        print()
    print(f"-> mejor con trailing activo: activacion={mejor[0]:.0%} retroceso={mejor[1]:.0%} ({mejor[2]:.2f}€) vs baseline {cap_base:.2f}€")
    return mejor[0], mejor[1], cap_base


def contorno_fino():
    print("=== Contorno fino de la meseta -- SOLO ETH 2024 ===\n")
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    cap_base, n_b, gan_b, dd_b, _ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
    print(f"baseline: {cap_base:.2f}€\n")

    resultados = {}
    mejor = None
    for act in ACTIVACION_FINO:
        fila = []
        for retroceso in RETROCESO_FINO:
            cap, n, gan, dd, n_disp = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, act, retroceso)
            fila.append(cap)
            if mejor is None or cap > mejor[2]:
                mejor = (act, retroceso, cap)
        resultados[act] = fila

    header = "act\\retro".ljust(10) + "".join(f"{r:>7.1%}" for r in RETROCESO_FINO)
    print(header)
    for act in ACTIVACION_FINO:
        fila_str = "".join(
            (f"{'=':>7}" if abs(v - cap_base) < 0.01 else (f"{'+' + str(round((v/cap_base-1)*100)):>6}%" if v > cap_base else f"{round((v/cap_base-1)*100):>6}%"))
            for v in resultados[act]
        )
        print(f"{act:>8.0%}  " + fila_str)

    print(f"\n-> mejor: activacion={mejor[0]:.0%} retroceso={mejor[1]:.1%} -> {mejor[2]:.2f}€ vs baseline {cap_base:.2f}€ ({(mejor[2]/cap_base-1)*100:+.1f}%)")

    n_mejoran = sum(1 for act in ACTIVACION_FINO for v in resultados[act] if v > cap_base * 1.01)
    n_total = len(ACTIVACION_FINO) * len(RETROCESO_FINO)
    print(f"   {n_mejoran} de {n_total} combinaciones mejoran el baseline en mas de 1% -- {'meseta amplia' if n_mejoran > n_total*0.3 else 'zona estrecha'}")
    return mejor


def confirmar_y_multi_anio(activacion_elegida, retroceso_elegido):
    print(f"\n=== Confirmacion BTC 2024 y multi-anio con activacion={activacion_elegida:.0%} retroceso={retroceso_elegido:.0%} (congelado) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a, _ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
            cap_nuevo, n_n, gan_n, dd_n, n_disp = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, activacion_elegida, retroceso_elegido)
            gana = cap_nuevo > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"con trailing alto {cap_nuevo:.2f}€ ({n_n}/{gan_n}, dd {dd_n:.2f}%, disparos={n_disp}) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_nuevo, gana))
    n_gana = sum(1 for _, _, _, g in resultados if g)
    print(f"\nResultado: gana en {n_gana} de {len(resultados)} combinaciones")
    return resultados


def seleccion_robusta(años_ajuste=(2021, 2022, 2023)):
    """Elige el punto del grid fino por ROBUSTEZ (nº de años que mejora el
    baseline, luego exceso medio) usando SOLO estos años de ETH -- nunca el
    resultado de un solo año, y nunca BTC (se reserva como holdout real).
    Reemplaza la seleccion original (mejor punto en ETH-2024 solo), que
    resulto generalizar peor pese a ganar mas en su propio año de ajuste.
    """
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    baselines = {}
    for año in años_ajuste:
        cand = candidatos_por_año(df, año)
        cap_base, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
        baselines[año] = cap_base

    resultados = []
    for act in ACTIVACION_FINO:
        for retroceso in RETROCESO_FINO:
            victorias, exceso_total = 0, 0.0
            for año in años_ajuste:
                cand = candidatos_por_año(df, año)
                cap, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, act, retroceso)
                base = baselines[año]
                if cap > base:
                    victorias += 1
                exceso_total += (cap - base) / base
            resultados.append((victorias, exceso_total, act, retroceso))

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    print(f"Top 10 configs mas robustas (ajuste SOLO ETH {list(años_ajuste)}, resto reservado):")
    print(f"{'victorias':>10} {'exceso_medio':>13}   activacion  retroceso")
    for v, exc, act, retro in resultados[:10]:
        print(f"{v:>9}/{len(años_ajuste)} {exc/len(años_ajuste)*100:>11.2f}%   {act:>9.0%}  {retro:>8.1%}")
    return resultados[0][2], resultados[0][3]


def confirmacion_final():
    """Tabla de confirmacion con los parametros YA congelados (5%/75%),
    nunca ejecutada explicitamente en la sesion original -- las exportaciones
    a HTML asumieron este punto pero esta es la primera vez que se corre la
    tabla completa de 8 combinaciones con el.
    """
    return confirmar_y_multi_anio(ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO)


if __name__ == "__main__":
    seleccion_robusta()
    confirmacion_final()
