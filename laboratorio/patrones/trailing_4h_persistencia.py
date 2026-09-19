"""
18-sept-2026: sobre `trailing_retroceso_alto.py` (trailing confirmado
5%/92.5%, ver ese fichero), se probo primero comprobar el suelo del
trailing con velas de 4h en vez de una vez al dia (ver
registro/intentos.jsonl, intento `intradia_salida_4h_trailing_stop`).
Resultado: 5/8 combinaciones ganan, red neto ~-36e -- pero mirando
operacion a operacion (no solo el agregado) aparecio un patron claro con
DOS mecanismos opuestos:
  - 49 casos donde 4h "rescata" una operacion que YA iba a salir por
    trailing de todas formas, pillando la rotura antes, a un precio menos
    malo (+2.94pp de media).
  - 15 casos donde 4h "recorta" una operacion que sin comprobacion 4h
    habria llegado a objetivo/senal_externa con una ganancia grande
    (24-53%), porque una simple mecha intradia durante la propia subida
    toca el 92.5% de retroceso -- ese mismo umbral esta calibrado para el
    ruido de UN DIA, no para el ruido de 4h, asi que se dispara con
    mechas normales de una operacion que sigue sana.

Este fichero prueba si exigir PERSISTENCIA (que el precio se quede por
debajo/encima del listón de trailing durante `velas_persistencia` velas de
4h SEGUIDAS, no una sola vez) consigue quedarse con el beneficio del
rescate sin pagar el coste del recorte -- la misma idea que ya usa
`senal_con_confirmacion`/`caida_relativa_confirmacion` en
`salidas/stop_objetivo.py` para racha_rota, aplicada aqui al trailing.

Con `velas_persistencia=1` este fichero debe reproducir EXACTAMENTE el
resultado ya visto de "4h sin persistencia" (primer toque) -- es el caso
particular N=1, sirve de comprobacion de que el codigo esta bien migrado
antes de barrer valores mayores.

Metodologia (igual que `trailing_retroceso_alto.seleccion_robusta`):
activacion=5%/retroceso=92.5% quedan CONGELADOS (no se retocan aqui, ya
pasaron su propia validacion cruzada); se barre SOLO `velas_persistencia`
usando ETH 2021-2023, comparando contra dos referencias -- el baseline sin
trailing Y el propio 5%/92.5% diario -- y se elige por robustez (cuantos
años mejora sobre el diario). Confirmacion sin tocar nada en ETH-2024
(holdout) + BTC completo.
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
from laboratorio.patrones.trailing_retroceso_alto import (
    ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO, UMBRAL_CAIDA_FILTRO,
    UMBRAL_SWITCH, _cargar, _simular,
)
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

VELAS_PERSISTENCIA_GRID = [1, 2, 3, 4, 5, 6]  # 1 vela=4h .. 6 velas=24h (un dia entero)


def _indices_4h_por_dia(df, df4h):
    """Para el dia `i` de `df`, las velas de `df4h` que caen dentro estan
    en `df4h[inicio[i]:fin[i]]` -- por busqueda de fecha, no por indice
    fijo *6, para no asumir que todos los dias tienen exactamente 6 velas
    de 4h (el primer dia de historico disponible no las tiene)."""
    dias4h = df4h["open_time"].dt.floor("D").to_numpy()
    dias_diarios = df["open_time"].dt.floor("D").to_numpy()
    inicio = np.searchsorted(dias4h, dias_diarios, side="left")
    fin = np.searchsorted(dias4h, dias_diarios, side="right")
    return inicio, fin


def _cargar_4h(moneda):
    df, atr, rt, rs, pendiente = _cargar(moneda)
    df4h = cargar_ohlcv_lab(moneda, "4h", estrategia="trailing_4h_persistencia")
    inicio4h, fin4h = _indices_4h_por_dia(df, df4h)
    return df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente


def _simular_trade_manual_4h(df, df4h, inicio4h, fin4h, idx_entrada, direccion, precio_entrada,
                              niveles, dias_maximo, senal_externa, pendiente, umbral_caida_filtro,
                              activacion_pct, retroceso_pct, velas_persistencia):
    close_d = df["close"].to_numpy()
    high4h = df4h["high"].to_numpy()
    low4h = df4h["low"].to_numpy()
    close4h = df4h["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None

    pendiente_extremo = 0.0
    mejor_ganancia_pct = 0.0
    racha_persistente = 0

    for dia in range(idx_entrada + 1, fin + 1):
        for j in range(inicio4h[dia], fin4h[dia]):
            if direccion == "largo":
                ganancia_pico_pct = (high4h[j] - precio_entrada) / precio_entrada
                ganancia_actual_pct = (close4h[j] - precio_entrada) / precio_entrada
            else:
                ganancia_pico_pct = (precio_entrada - low4h[j]) / precio_entrada
                ganancia_actual_pct = (precio_entrada - close4h[j]) / precio_entrada
            mejor_ganancia_pct = max(mejor_ganancia_pct, ganancia_pico_pct)

            if retroceso_pct < 999 and mejor_ganancia_pct >= activacion_pct:
                listón = mejor_ganancia_pct * (1 - retroceso_pct)
                rompe = ganancia_actual_pct <= listón
                racha_persistente = racha_persistente + 1 if rompe else 0
                if racha_persistente >= velas_persistencia:
                    return dia, close4h[j], "trailing_retroceso_alto"
            else:
                racha_persistente = 0

            if direccion == "largo":
                toca_stop = low4h[j] <= niveles.stop
                toca_objetivo = high4h[j] >= niveles.objetivo
            else:
                toca_stop = high4h[j] >= niveles.stop
                toca_objetivo = low4h[j] <= niveles.objetivo
            if toca_stop:
                return dia, niveles.stop, "stop"
            if toca_objetivo:
                return dia, niveles.objetivo, "objetivo"

        # racha_rota + confirmacion por pendiente: sigue evaluandose UNA
        # vez por dia (al cierre), igual que la version diaria -- aqui NO
        # se esta probando llevar racha_rota a 4h, solo el trailing.
        if senal_externa is not None and senal_externa[dia]:
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


def _simular_4h(df, df4h, inicio4h, fin4h, candidatos, atr, racha_rota_techo, racha_rota_suelo,
                 pendiente, umbral_switch, umbral_caida_filtro, activacion_pct, retroceso_pct,
                 velas_persistencia):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual_4h(df, df4h, inicio4h, fin4h, idx, direccion, close[idx], niveles,
                                      DIAS_MAXIMO, senal, pendiente, umbral_caida_filtro,
                                      activacion_pct, retroceso_pct, velas_persistencia)
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


UMBRAL_GRANDE_MULT_GRID = [1.25, 1.33, 1.5, 1.67, 1.75, 2.0, 2.25, 2.5, 3.0, 4.0]  # multiplo de ACTIVACION_CONFIRMADA
VELAS_PERSISTENCIA_COND_GRID = [1, 2, 3, 4, 5]


def _simular_trade_manual_4h_condicional(df, df4h, inicio4h, fin4h, idx_entrada, direccion, precio_entrada,
                                          niveles, dias_maximo, senal_externa, pendiente, umbral_caida_filtro,
                                          activacion_pct, retroceso_pct, velas_persistencia, umbral_grande_pct):
    """Igual que `_simular_trade_manual_4h`, pero el chequeo INTRADIA del
    trailing (con persistencia) solo se activa una vez que la ganancia de
    pico de la operacion supera `umbral_grande_pct` -- mientras se queda
    por debajo, el trailing se comprueba UNA vez al dia (al cierre), byte
    a byte igual que `_simular_trade_manual` (el 8/8 ya confirmado). Idea
    del usuario, 18-sept-2026: no aplicar el chequeo intradia a todas las
    operaciones, solo a las que ya van muy ganadoras -- que es justo donde
    aparecian los recortes prematuros de -15pp de media."""
    close_d = df["close"].to_numpy()
    high4h = df4h["high"].to_numpy()
    low4h = df4h["low"].to_numpy()
    close4h = df4h["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None

    pendiente_extremo = 0.0
    mejor_ganancia_pct = 0.0
    racha_persistente = 0

    for dia in range(idx_entrada + 1, fin + 1):
        velas_del_dia = list(range(inicio4h[dia], fin4h[dia]))
        for pos_local, j in enumerate(velas_del_dia):
            es_ultima_vela_del_dia = pos_local == len(velas_del_dia) - 1
            if direccion == "largo":
                ganancia_pico_pct = (high4h[j] - precio_entrada) / precio_entrada
                ganancia_actual_pct = (close4h[j] - precio_entrada) / precio_entrada
            else:
                ganancia_pico_pct = (precio_entrada - low4h[j]) / precio_entrada
                ganancia_actual_pct = (precio_entrada - close4h[j]) / precio_entrada
            mejor_ganancia_pct = max(mejor_ganancia_pct, ganancia_pico_pct)

            modo_intradia = mejor_ganancia_pct >= umbral_grande_pct
            comprobar_ahora = modo_intradia or es_ultima_vela_del_dia

            if comprobar_ahora and retroceso_pct < 999 and mejor_ganancia_pct >= activacion_pct:
                listón = mejor_ganancia_pct * (1 - retroceso_pct)
                rompe = ganancia_actual_pct <= listón
                if modo_intradia:
                    racha_persistente = racha_persistente + 1 if rompe else 0
                    dispara = racha_persistente >= velas_persistencia
                else:
                    dispara = rompe
                if dispara:
                    return dia, close4h[j], "trailing_retroceso_alto"

            if direccion == "largo":
                toca_stop = low4h[j] <= niveles.stop
                toca_objetivo = high4h[j] >= niveles.objetivo
            else:
                toca_stop = high4h[j] >= niveles.stop
                toca_objetivo = low4h[j] <= niveles.objetivo
            if toca_stop:
                return dia, niveles.stop, "stop"
            if toca_objetivo:
                return dia, niveles.objetivo, "objetivo"

        if senal_externa is not None and senal_externa[dia]:
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


def _simular_4h_condicional(df, df4h, inicio4h, fin4h, candidatos, atr, racha_rota_techo, racha_rota_suelo,
                             pendiente, umbral_switch, umbral_caida_filtro, activacion_pct, retroceso_pct,
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
        r = _simular_trade_manual_4h_condicional(df, df4h, inicio4h, fin4h, idx, direccion, close[idx], niveles,
                                                  DIAS_MAXIMO, senal, pendiente, umbral_caida_filtro,
                                                  activacion_pct, retroceso_pct, velas_persistencia, umbral_grande_pct)
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


def seleccion_robusta_condicional(años_ajuste=(2021, 2022, 2023)):
    df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente = _cargar_4h("ETHUSDT")
    referencias = {}
    for año in años_ajuste:
        cand = candidatos_por_año(df, año)
        cap_diario, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO,
                                   ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO)
        referencias[año] = cap_diario

    print(f"=== Barrido condicional (umbral_grande x velas_persistencia) -- SOLO ETH {list(años_ajuste)} ===")
    resultados = []
    for mult in UMBRAL_GRANDE_MULT_GRID:
        umbral_grande = mult * ACTIVACION_CONFIRMADA
        for velas in VELAS_PERSISTENCIA_COND_GRID:
            victorias, exceso_total = 0, 0.0
            for año in años_ajuste:
                cand = candidatos_por_año(df, año)
                cap, *_ = _simular_4h_condicional(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente,
                                                   UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, ACTIVACION_CONFIRMADA,
                                                   RETROCESO_CONFIRMADO, velas, umbral_grande)
                cap_diario = referencias[año]
                if cap > cap_diario:
                    victorias += 1
                exceso_total += (cap - cap_diario) / cap_diario
            resultados.append((victorias, exceso_total, mult, velas))

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    print(f"{'umbral_x':>9} {'velas':>6} {'victorias':>10} {'exceso_medio':>13}")
    for v, exc, mult, velas in resultados[:10]:
        print(f"{mult:>8.1f}x {velas:>6} {v:>9}/{len(años_ajuste)} {exc/len(años_ajuste)*100:>11.2f}%")
    mejor = resultados[0]
    print(f"\n-> mas robusto: umbral_grande={mejor[2]:.1f}x activacion, velas_persistencia={mejor[3]}")
    return mejor[2] * ACTIVACION_CONFIRMADA, mejor[3]


def confirmar_holdout_condicional(umbral_grande_pct, velas_persistencia):
    print(f"\n=== Confirmacion holdout condicional (ETH-2024 + BTC completo), umbral_grande={umbral_grande_pct:.1%} velas={velas_persistencia} ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente = _cargar_4h(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_diario, n_d, gan_d, dd_d, n_disp_d = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                               UMBRAL_CAIDA_FILTRO, ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO)
            cap_c, n_c, gan_c, dd_c, n_disp_c = _simular_4h_condicional(df, df4h, inicio4h, fin4h, cand, atr, rt, rs,
                                                                         pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO,
                                                                         ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO,
                                                                         velas_persistencia, umbral_grande_pct)
            gana = cap_c > cap_diario
            print(f"  {año}: diario {cap_diario:.2f}€ ({n_d}/{gan_d}, dd {dd_d:.2f}%, disparos={n_disp_d}) -- "
                  f"condicional {cap_c:.2f}€ ({n_c}/{gan_c}, dd {dd_c:.2f}%, disparos={n_disp_c}) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_diario, cap_c, gana))
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"\nResultado: condicional gana en {n_gana} de {len(resultados)} combinaciones frente al diario")
    return resultados


def comprobar_equivalencia_n1():
    """N=1 debe coincidir centimo a centimo con el 4h "primer toque" ya
    visto en el intento anterior (no persistido como fichero) -- guarda
    aqui esa referencia para que quede comprobado en el repositorio."""
    df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente = _cargar_4h("ETHUSDT")
    cand = candidatos_por_año(df, 2024)
    cap, n, gan, dd, n_disp = _simular_4h(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente,
                                           UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO,
                                           ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO, velas_persistencia=1)
    cap_diario, n_d, gan_d, dd_d, n_disp_d = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                       UMBRAL_CAIDA_FILTRO, ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO)
    print(f"ETH 2024 -- diario: {cap_diario:.2f}€ ({n_d} trades, {n_disp_d} disparos trailing)")
    print(f"ETH 2024 -- 4h N=1: {cap:.2f}€ ({n} trades, {n_disp} disparos trailing)")


def seleccion_robusta_persistencia(años_ajuste=(2021, 2022, 2023)):
    df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente = _cargar_4h("ETHUSDT")
    referencias = {}
    for año in años_ajuste:
        cand = candidatos_por_año(df, año)
        cap_base, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
        cap_diario, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO,
                                   ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO)
        referencias[año] = (cap_base, cap_diario)

    print(f"=== Barrido de persistencia (velas de 4h) -- SOLO ETH {list(años_ajuste)} ===")
    print(f"{'velas':>6} {'vs_base_3y':>12} {'vs_diario_3y':>13}   detalle por año")
    resultados = []
    for velas in VELAS_PERSISTENCIA_GRID:
        victorias_vs_diario, exceso_vs_diario_total = 0, 0.0
        detalle = []
        for año in años_ajuste:
            cand = candidatos_por_año(df, año)
            cap, *_ = _simular_4h(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                   UMBRAL_CAIDA_FILTRO, ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO, velas)
            cap_base, cap_diario = referencias[año]
            if cap > cap_diario:
                victorias_vs_diario += 1
            exceso_vs_diario_total += (cap - cap_diario) / cap_diario
            detalle.append(f"{año}:{cap:.0f}€({(cap/cap_diario-1)*100:+.1f}%vsdiario)")
        resultados.append((victorias_vs_diario, exceso_vs_diario_total, velas))
        print(f"{velas:>6} {'':>12} {exceso_vs_diario_total/len(años_ajuste)*100:>11.2f}%   {' '.join(detalle)}")

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    mejor_velas = resultados[0][2]
    print(f"\n-> mas robusto vs diario: velas_persistencia={mejor_velas} ({resultados[0][0]}/{len(años_ajuste)} años mejora, exceso medio {resultados[0][1]/len(años_ajuste)*100:+.2f}%)")
    return mejor_velas


def confirmar_holdout(velas_persistencia):
    print(f"\n=== Confirmacion holdout (ETH-2024 + BTC completo), velas_persistencia={velas_persistencia} ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, df4h, inicio4h, fin4h, atr, rt, rs, pendiente = _cargar_4h(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_diario, n_d, gan_d, dd_d, n_disp_d = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                               UMBRAL_CAIDA_FILTRO, ACTIVACION_CONFIRMADA, RETROCESO_CONFIRMADO)
            cap_4h, n_4, gan_4, dd_4, n_disp_4 = _simular_4h(df, df4h, inicio4h, fin4h, cand, atr, rt, rs, pendiente,
                                                              UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, ACTIVACION_CONFIRMADA,
                                                              RETROCESO_CONFIRMADO, velas_persistencia)
            gana = cap_4h > cap_diario
            print(f"  {año}: diario {cap_diario:.2f}€ ({n_d}/{gan_d}, dd {dd_d:.2f}%, disparos={n_disp_d}) -- "
                  f"4h persist={velas_persistencia} {cap_4h:.2f}€ ({n_4}/{gan_4}, dd {dd_4:.2f}%, disparos={n_disp_4}) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_diario, cap_4h, gana))
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"\nResultado: 4h con persistencia={velas_persistencia} gana en {n_gana} de {len(resultados)} combinaciones frente al diario")
    return resultados


if __name__ == "__main__":
    comprobar_equivalencia_n1()
    print()
    mejor = seleccion_robusta_persistencia()
    confirmar_holdout(mejor)
