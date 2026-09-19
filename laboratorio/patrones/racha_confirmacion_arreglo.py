"""
18-sept-2026: el usuario senalo dos operaciones reales de ETH (corto
04-may-2022, corto 05-jun-2024) donde la salida se ejecuta sospechosamente
rapido, dejando sobre la mesa una parte grande del movimiento a favor.
Investigando ambas por separado (ver conversacion, no persistida aparte):

- El caso de 05-jun-2024 lo corta el SWITCH de sentido (`UMBRAL_SWITCH=0.0`
  en trailing_retroceso_alto.py) -- no es un bug de este fichero, es una
  cuestion de que tan facil es cambiar de sentido, y el coste real ahi son
  las DOS operaciones largas que siguieron y perdieron, no un movimiento
  gigante sin capturar. No se toca aqui.

- El caso de 04-may-2022 SI es un bug real, encontrado al trazar paso a
  paso `_simular_trade_manual` (trailing_retroceso_alto.py, rama
  `senal_externa`/`pendiente` = confirmacion retardada de racha_rota por
  pendiente-ATR, `UMBRAL_CAIDA_FILTRO=0.3`): `pendiente_extremo` arranca en
  0.0, y la clausula de escape `pendiente_extremo >= 0` (corto) /
  `<= 0` (largo) --pensada, se intuye, para el caso "el impulso ya se
  enfrio del todo, no hace falta esperar mas"-- se cumple TRIVIALMENTE
  mientras `pendiente_extremo` siga en su valor inicial sin haberse movido
  nunca hacia el lado que confirmaria la reversion. Si racha_rota se
  dispara el PRIMER dia evaluado y la pendiente todavia no se ha movido a
  favor de la reversion (caso real: pendiente=+0.14 el dia 1, positiva,
  osea el precio ni siquiera habia empezado a caer todavia), la
  confirmacion se salta por completo y se honra la salida sin haber
  esperado nada -- exactamente lo opuesto de lo que el mecanismo dice que
  hace. Consecuencia real: el corto de 04-may-2022 salio con +6.55% un dia
  antes del crash de Terra/Luna, que sumo otro -29% en la semana siguiente
  nunca capturado.

Arreglo probado aqui: separar "extremo == 0 porque nunca se movio" de
"extremo == 0 porque genuinamente ya se enfrio" con una bandera
`extremo_activo`, que solo se activa la PRIMERA vez que pendiente cruza al
lado que confirma la reversion. Mientras no este activa, NO se honra por
esta via (el stop/objetivo/tiempo_maximo de siempre siguen protegiendo por
debajo) -- se espera a que el impulso favorable exista de verdad antes de
poder pedirle que se enfrie un 30% desde su pico, que es lo que el
mecanismo dice hacer.

Metodologia identica a `trailing_retroceso_alto.seleccion_robusta`: mismo
UMBRAL_CAIDA_FILTRO=0.3 (no se retoca aqui, es un arreglo de logica, no un
recalibrado de umbral), comparado contra el baseline actual (racha_rota+
caida tal cual esta hoy) en los mismos 8 tramos (ETH 2021-2023 ajuste,
ETH-2024+BTC completo holdout).
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from laboratorio.patrones.trailing_retroceso_alto import (
    UMBRAL_CAIDA_FILTRO, UMBRAL_SWITCH, _cargar, _simular,
)
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano


def _simular_trade_manual_arreglado(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                                     senal_externa, pendiente, umbral_caida_filtro):
    """Copia de `_simular_trade_manual` (trailing_retroceso_alto.py) SIN la
    parte de trailing (activacion/retroceso -- aqui no se toca, se prueba
    solo el arreglo de la confirmacion de racha_rota), con el arreglo
    `extremo_activo` descrito en el docstring del modulo."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    pendiente_extremo = 0.0
    extremo_activo = False
    for i in range(idx_entrada + 1, fin + 1):
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

        p = pendiente[i]
        if senal_externa is not None and senal_externa[i]:
            if np.isnan(p):
                return i, close[i], "senal_externa"
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
                return i, close[i], "senal_externa"
        else:
            if not np.isnan(p):
                if direccion == "largo" and p > 0:
                    pendiente_extremo = max(pendiente_extremo, p)
                    extremo_activo = True
                elif direccion == "corto" and p < 0:
                    pendiente_extremo = min(pendiente_extremo, p)
                    extremo_activo = True
    return fin, close[fin], "tiempo_maximo"


def _simular_arreglado(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente,
                        umbral_switch, umbral_caida_filtro):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        r = _simular_trade_manual_arreglado(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO,
                                             senal, pendiente, umbral_caida_filtro)
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


UMBRAL_CAIDA_FILTRO_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70]


def seleccion_robusta_arreglo(años_ajuste=(2021, 2022, 2023)):
    """Igual criterio que `trailing_retroceso_alto.seleccion_robusta`: barre
    SOLO el umbral de enfriamiento (0.3 no es intocable, es tan "absoluto"
    como cualquier otro numero elegido a ojo) usando SOLO ETH en los años de
    ajuste, eligiendo por robustez frente al sistema ACTUAL (sin arreglo)."""
    df, atr, rt, rs, pendiente = _cargar("ETHUSDT")
    referencias = {}
    for año in años_ajuste:
        cand = candidatos_por_año(df, año)
        cap_actual, *_ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, UMBRAL_CAIDA_FILTRO, 0.10, 999)
        referencias[año] = cap_actual

    print(f"=== Barrido del umbral de enfriamiento (arreglo extremo_activo) -- SOLO ETH {list(años_ajuste)} ===")
    resultados = []
    for umbral in UMBRAL_CAIDA_FILTRO_GRID:
        victorias, exceso_total = 0, 0.0
        detalle = []
        for año in años_ajuste:
            cand = candidatos_por_año(df, año)
            cap, *_ = _simular_arreglado(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH, umbral)
            cap_actual = referencias[año]
            if cap > cap_actual:
                victorias += 1
            exceso_total += (cap - cap_actual) / cap_actual
            detalle.append(f"{año}:{cap:.0f}€({(cap/cap_actual-1)*100:+.1f}%)")
        resultados.append((victorias, exceso_total, umbral))
        print(f"  umbral={umbral:.0%}: {victorias}/{len(años_ajuste)} victorias, exceso medio {exceso_total/len(años_ajuste)*100:+.2f}%   {' '.join(detalle)}")

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    mejor = resultados[0][2]
    print(f"\n-> mas robusto: umbral_caida_filtro={mejor:.0%} ({resultados[0][0]}/{len(años_ajuste)} años mejora, exceso medio {resultados[0][1]/len(años_ajuste)*100:+.2f}%)")
    return mejor


def confirmar_holdout_arreglo(umbral_caida_filtro):
    print(f"\n=== Confirmacion holdout arreglo (ETH-2024 + BTC completo), umbral_caida_filtro={umbral_caida_filtro:.0%} ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a, _ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                         UMBRAL_CAIDA_FILTRO, 0.10, 999)
            cap_arr, n_r, gan_r, dd_r = _simular_arreglado(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                             umbral_caida_filtro)
            gana = cap_arr > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"arreglado {cap_arr:.2f}€ ({n_r}/{gan_r}, dd {dd_r:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_actual, cap_arr, gana))
        print()
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"Resultado: arreglo (umbral={umbral_caida_filtro:.0%}) gana en {n_gana} de {len(resultados)} combinaciones frente al actual")
    return resultados


def confirmar_arreglo():
    print("=== Arreglo confirmacion racha_rota (extremo_activo) vs actual -- 8 combinaciones ===\n")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df, atr, rt, rs, pendiente = _cargar(moneda)
        print(f"-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(df, año)
            cap_actual, n_a, gan_a, dd_a, _ = _simular(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                         UMBRAL_CAIDA_FILTRO, 0.10, 999)
            cap_arr, n_r, gan_r, dd_r = _simular_arreglado(df, cand, atr, rt, rs, pendiente, UMBRAL_SWITCH,
                                                             UMBRAL_CAIDA_FILTRO)
            gana = cap_arr > cap_actual
            print(f"  {año}: actual {cap_actual:.2f}€ ({n_a}/{gan_a}, dd {dd_a:.2f}%) -- "
                  f"arreglado {cap_arr:.2f}€ ({n_r}/{gan_r}, dd {dd_r:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_actual, cap_arr, gana))
        print()
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"Resultado: arreglo gana en {n_gana} de {len(resultados)} combinaciones frente al actual")
    return resultados


if __name__ == "__main__":
    confirmar_arreglo()
    print()
    mejor = seleccion_robusta_arreglo()
    confirmar_holdout_arreglo(mejor)
