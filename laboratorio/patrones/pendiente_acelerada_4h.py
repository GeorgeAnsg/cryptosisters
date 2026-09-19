"""
19-sept-2026: pregunta del usuario sobre si comprobar pendiente_acelerada
(salidas/pendiente_acelerada.py) a resolucion mas fina que diaria (4h/12h)
mejora el tiempo de reaccion sin perder rendimiento. Esta linea NUNCA se
habia probado -- `racha_confirmacion_4h.py` (18-sept) probo lo mismo pero
para la OTRA señal de salida (racha_rota confirmada), no para
pendiente_acelerada, y ese fichero en concreto se cerro "no confirmado"
usando K_ATR_STOP=2.5/R_FIJO=3.0 (los parametros VIEJOS, ver
`racha_confirmacion_4h_diagnostico_aislado` en registro/intentos.jsonl) --
nunca se revalido bajo el K=1.2/R=4.0 real como si se hizo con el trailing.
Revalidado en esta misma sesion (ver conversacion 19-sept-2026): bajo los
parametros reales tambien empeora (4/8 en holdout, peor que el 5/8 que se
penso que tenia), asi que la conclusion de cerrar esa linea se mantiene,
solo que con el numero correcto.

Metodologia identica a las anteriores investigaciones de este tipo
(trailing_4h_persistencia.py, racha_confirmacion_4h.py): comparacion
AISLADA (solo pendiente_acelerada varia; stop/objetivo con K=1.2/R=4.0
reales y racha_rota confirmada diaria se mantienen igual en los dos
lados, sin venta parcial ni trailing para no mezclar variables) --
ajuste SOLO en ETH 2021-2023, confirmacion sin tocar nada en ETH-2024 +
BTC completo.

pendiente_acelerada en si NO cambia de definicion (mismo UMBRAL_PENDIENTE_ATR=1.5,
mismo VENTANA_DIAS=5 reescalado a velas de 4h) -- lo unico que cambia es
CADA CUANTO se comprueba si ya se cruzo ese umbral: una vez al cierre
diario (como esta en produccion) vs cada 4h con exigencia de persistencia
(para filtrar una mecha suelta de una superacion real y sostenida).

RESULTADOS (19-sept-2026), tres variantes probadas, ninguna confirmada:
- A 4h (formula diaria comprobada cada 4h): 0-1/3 en ajuste ETH en TODOS
  los niveles de persistencia probados, 3/8 en holdout -- mucho ruido,
  el numero de operaciones se dispara (34->42, 33->46...).
- A 12h de verdad (velas agregadas, no la formula diaria mirada mas
  seguido): mejor (2/3 en ajuste, 5/8 en holdout) pero sigue sin llegar
  al 8/8 que exige el proyecto.
- A 12h con periodo de gracia (no comprobar hasta N dias tras la entrada,
  para filtrar el vaiven normal de una operacion recien abierta -- ver
  diagnostico operacion a operacion mas abajo): sigue en 5/8, solo
  redistribuye que combinaciones ganan/pierden.
Diagnostico operacion a operacion (ETH 2023/2024, BTC 2024) mostro que
la version de 12h corta sistematicamente ganadores grandes en el dia+1
al dia+5 desde la entrada, confundiendo el ruido normal de arranque de
una operacion con una reversion real -- el periodo de gracia ataca ese
sintoma puntual pero no cambia el resultado agregado.

CONCLUSION: cerrado como NO CONFIRMADO, con tres variantes agotadas (no
por falta de intentarlo) -- igual que racha_rota a 4h/12h, mirar estas
señales mas seguido introduce mas ruido del que arregla. La mejora que
SI se mantiene sin este problema es comprobar el stop-loss/take-profit
(un precio ya fijado, no un indicador) mas a menudo -- aunque en la
practica esa pieza tambien resulto no aportar nada en Corvus IV, porque
el usuario pone el stop-loss/take-profit como orden REAL en QuantFury y
la plataforma ya lo ejecuta al instante sin ayuda del bot (ver
conversacion 19-sept-2026).
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS
from laboratorio.patrones.trailing_4h_persistencia import _indices_4h_por_dia
from motores.volatilidad import atr_absoluto
from salidas.pendiente_acelerada import UMBRAL_PENDIENTE_ATR, calcular_pendiente_atr, señal_para_direccion
from salidas.racha_rota import calcular_para_direccion as racha_rota_para_direccion, CAIDA_RELATIVA_CONFIRMACION
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano

# parametros REALES de produccion (ejecucion/cuenta_referencia.py) -- a
# diferencia de racha_confirmacion_4h.py, aqui se usan bien desde el
# principio, no como parche posterior.
K_ATR_STOP = 1.2
R_FIJO = 4.0
DIAS_MAXIMO = 45
UMBRAL_SWITCH = 0.0
RIESGO_BASE_PCT = 0.02
MULTIPLICADOR_MIN, MULTIPLICADOR_MAX = 0.9, 1.1
CAPITAL_INICIAL = 1000.0

VELAS_POR_DIA_4H = 6
M_DIAS_PENDIENTE = 5
VELAS_PERSISTENCIA_GRID = [1, 2, 3, 4, 5, 6]  # 4h .. 24h


def _pendiente_atr_4h(df4h, atr4h):
    close = df4h["close"].to_numpy()
    n = len(close)
    ventana = M_DIAS_PENDIENTE * VELAS_POR_DIA_4H
    pendiente = np.full(n, np.nan)
    for i in range(ventana, n):
        if not np.isnan(atr4h[i]) and atr4h[i] > 0:
            pendiente[i] = (close[i] - close[i - ventana]) / atr4h[i]
    return pendiente


VELAS_POR_DIA_12H = 2


def _resample_12h(df4h):
    """Agrega 3 velas de 4h en 1 de 12h de verdad (00-12h y 12-24h UTC) --
    a diferencia de comprobar la formula DIARIA cada 4h (mas ruidosa
    porque cada paso de 4h apenas cambia la ventana de 5 dias), esto
    recalcula ATR y pendiente sobre una serie de precio genuinamente mas
    gruesa, pensado para filtrar la mecha suelta de una vela de 4h sin
    perder tanta reaccion como esperar al cierre diario entero."""
    g = df4h.set_index("open_time").resample("12h", origin="epoch").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna().reset_index()
    return g


def _pendiente_atr_12h(df12h, atr12h):
    close = df12h["close"].to_numpy()
    n = len(close)
    ventana = M_DIAS_PENDIENTE * VELAS_POR_DIA_12H
    pendiente = np.full(n, np.nan)
    for i in range(ventana, n):
        if not np.isnan(atr12h[i]) and atr12h[i] > 0:
            pendiente[i] = (close[i] - close[i - ventana]) / atr12h[i]
    return pendiente


def _cargar(moneda):
    df = cargar_ohlcv_lab(moneda, "1d", estrategia="pendiente_acelerada_4h")
    atr = atr_absoluto(df)
    pendiente = calcular_pendiente_atr(df, atr)
    racha_rota_largo = racha_rota_para_direccion(df, "largo")
    racha_rota_corto = racha_rota_para_direccion(df, "corto")
    señal_pend_largo = señal_para_direccion(pendiente, "largo", UMBRAL_PENDIENTE_ATR)
    señal_pend_corto = señal_para_direccion(pendiente, "corto", UMBRAL_PENDIENTE_ATR)

    df4h = cargar_ohlcv_lab(moneda, "4h", estrategia="pendiente_acelerada_4h")
    inicio4h, fin4h = _indices_4h_por_dia(df, df4h)
    atr4h = atr_absoluto(df4h, ventana=14 * VELAS_POR_DIA_4H)
    pendiente4h = _pendiente_atr_4h(df4h, atr4h)

    df12h = _resample_12h(df4h)
    inicio12h, fin12h = _indices_4h_por_dia(df, df12h)  # misma lógica, generica por fecha
    atr12h = atr_absoluto(df12h, ventana=14 * VELAS_POR_DIA_12H)
    pendiente12h = _pendiente_atr_12h(df12h, atr12h)

    return dict(df=df, df4h=df4h, inicio4h=inicio4h, fin4h=fin4h, atr=atr,
                racha_rota_largo=racha_rota_largo, racha_rota_corto=racha_rota_corto,
                señal_pend_largo=señal_pend_largo, señal_pend_corto=señal_pend_corto,
                pendiente=pendiente, pendiente4h=pendiente4h,
                df12h=df12h, inicio12h=inicio12h, fin12h=fin12h, pendiente12h=pendiente12h)


def _simular_trade(datos, idx_entrada, direccion, precio_entrada, niveles, modo="diaria", velas_persistencia=1, dias_gracia=0):
    """`modo="diaria"`: pendiente_acelerada se comprueba una vez al cierre
    diario (produccion actual). `modo="4h"`/`modo="12h"`: se comprueba con
    velas intradia REALES de esa resolucion, exigiendo `velas_persistencia`
    velas seguidas por encima/debajo del umbral (a 12h, persistencia=1 ya
    equivale a media jornada completa, no hace falta exigir mas de una).
    La racha_rota confirmada (diaria) es IDENTICA en los tres modos -- no
    es la variable que se esta probando aqui. `dias_gracia`: no comprueba
    la señal intradia hasta que la operacion lleve mas de ese numero de
    dias abierta (idea del usuario, 19-sept-2026, para filtrar el ruido
    normal de los primeros dias de una operacion recien abierta)."""
    df = datos["df"]
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + DIAS_MAXIMO, n - 1)
    if fin <= idx_entrada:
        return None

    racha = datos["racha_rota_largo"] if direccion == "largo" else datos["racha_rota_corto"]
    señal_pend_diaria = datos["señal_pend_largo"] if direccion == "largo" else datos["señal_pend_corto"]
    pendiente_extremo = 0.0
    racha_persistente_intradia = 0

    if modo == "4h":
        inicio_ix, fin_ix, pendiente_ix, close_ix = datos["inicio4h"], datos["fin4h"], datos["pendiente4h"], datos["df4h"]["close"].to_numpy()
    elif modo == "12h":
        inicio_ix, fin_ix, pendiente_ix, close_ix = datos["inicio12h"], datos["fin12h"], datos["pendiente12h"], datos["df12h"]["close"].to_numpy()

    for dia in range(idx_entrada + 1, fin + 1):
        if direccion == "largo":
            if low[dia] <= niveles.stop:
                return dia, niveles.stop, "stop"
            if high[dia] >= niveles.objetivo:
                return dia, niveles.objetivo, "objetivo"
        else:
            if high[dia] >= niveles.stop:
                return dia, niveles.stop, "stop"
            if low[dia] <= niveles.objetivo:
                return dia, niveles.objetivo, "objetivo"

        if modo in ("4h", "12h") and (dia - idx_entrada) > dias_gracia:
            for j in range(inicio_ix[dia], fin_ix[dia]):
                p = pendiente_ix[j]
                if np.isnan(p):
                    racha_persistente_intradia = 0
                    continue
                cruza = (p <= -UMBRAL_PENDIENTE_ATR) if direccion == "largo" else (p >= UMBRAL_PENDIENTE_ATR)
                racha_persistente_intradia = racha_persistente_intradia + 1 if cruza else 0
                if racha_persistente_intradia >= velas_persistencia:
                    return dia, close_ix[j], "senal_externa"
        else:
            if señal_pend_diaria[dia]:
                return dia, close[dia], "senal_externa"

        p = datos["pendiente"][dia]
        if not np.isnan(p):
            if direccion == "largo":
                pendiente_extremo = max(pendiente_extremo, p)
                honra = pendiente_extremo <= 0 or p <= pendiente_extremo * (1 - CAIDA_RELATIVA_CONFIRMACION)
            else:
                pendiente_extremo = min(pendiente_extremo, p)
                honra = pendiente_extremo >= 0 or p >= pendiente_extremo * (1 - CAIDA_RELATIVA_CONFIRMACION)
            if racha[dia] and honra:
                return dia, close[dia], "senal_confirmada"
        elif racha[dia]:
            return dia, close[dia], "senal_confirmada"

    return fin, close[fin], "tiempo_maximo"


def _simular_cuenta(datos, candidatos, modo="diaria", velas_persistencia=1, dias_gracia=0):
    close = datos["df"]["close"].to_numpy()
    capital = CAPITAL_INICIAL
    trades = []
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], datos["atr"][idx], direccion, K_ATR_STOP, R_FIJO)
        r = _simular_trade(datos, idx, direccion, close[idx], niveles, modo, velas_persistencia, dias_gracia)
        if r is None:
            return None
        idx_salida, precio_salida, motivo = r
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        return dict(idx_entrada=idx, direccion=direccion, probabilidad=prob, precio_entrada=close[idx],
                    idx_salida=idx_salida, precio_salida=precio_salida, unidades=pos.unidades, motivo=motivo)

    def _cerrar(pos, idx_cierre=None, precio_cierre=None):
        nonlocal capital
        idx_c = idx_cierre if idx_cierre is not None else pos["idx_salida"]
        precio_c = precio_cierre if precio_cierre is not None else pos["precio_salida"]
        signo = 1 if pos["direccion"] == "largo" else -1
        pnl = pos["unidades"] * (precio_c - pos["precio_entrada"]) * signo
        capital += pnl
        trades.append(dict(pnl_eur=pnl, capital_tras=capital))

    for idx, direccion, prob in candidatos:
        if np.isnan(datos["atr"][idx]):
            continue
        if abierta is not None and idx > abierta["idx_salida"]:
            _cerrar(abierta)
            abierta = None
        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
            continue
        if direccion != abierta["direccion"] and prob - abierta["probabilidad"] >= UMBRAL_SWITCH:
            _cerrar(abierta, idx, close[idx])
            abierta = _abrir(idx, direccion, prob)

    if abierta is not None:
        _cerrar(abierta)

    valores = np.array([CAPITAL_INICIAL] + [t["capital_tras"] for t in trades])
    pico = np.maximum.accumulate(valores)
    dd = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)
    return capital, len(trades), ganadoras, dd


def seleccion_robusta(modo, grid, años_ajuste=(2021, 2022, 2023)):
    datos = _cargar("ETHUSDT")
    referencias = {}
    for año in años_ajuste:
        cand = candidatos_por_año(datos["df"], año)
        cap, *_ = _simular_cuenta(datos, cand, modo="diaria")
        referencias[año] = cap

    etiqueta_h = 4 if modo == "4h" else 12
    print(f"=== Barrido de persistencia (pendiente_acelerada a {modo}) -- SOLO ETH {list(años_ajuste)} ===")
    resultados = []
    for velas in grid:
        victorias, exceso_total = 0, 0.0
        detalle = []
        for año in años_ajuste:
            cand = candidatos_por_año(datos["df"], año)
            cap, *_ = _simular_cuenta(datos, cand, modo=modo, velas_persistencia=velas)
            cap_actual = referencias[año]
            if cap > cap_actual:
                victorias += 1
            exceso_total += (cap - cap_actual) / cap_actual
            detalle.append(f"{año}:{cap:.0f}€({(cap/cap_actual-1)*100:+.1f}%)")
        resultados.append((victorias, exceso_total, velas))
        print(f"  velas={velas} ({velas*etiqueta_h}h): {victorias}/{len(años_ajuste)} victorias, "
              f"exceso medio {exceso_total/len(años_ajuste)*100:+.2f}%   {' '.join(detalle)}")

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    mejor = resultados[0][2]
    print(f"\n-> mas robusto: velas_persistencia={mejor} ({mejor*etiqueta_h}h)")
    return mejor


def confirmar_holdout(modo, velas_persistencia):
    etiqueta_h = 4 if modo == "4h" else 12
    print(f"\n=== Confirmacion holdout (ETH-2024 + BTC completo), pendiente_acelerada a {modo}, persistencia={velas_persistencia} ({velas_persistencia*etiqueta_h}h) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        datos = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(datos["df"], año)
            cap_d, n_d, gan_d, dd_d = _simular_cuenta(datos, cand, modo="diaria")
            cap_i, n_i, gan_i, dd_i = _simular_cuenta(datos, cand, modo=modo, velas_persistencia=velas_persistencia)
            gana = cap_i > cap_d
            print(f"  {año}: diaria {cap_d:.2f}€ ({n_d}/{gan_d}, dd {dd_d:.2f}%) -- "
                  f"{modo} persist={velas_persistencia} {cap_i:.2f}€ ({n_i}/{gan_i}, dd {dd_i:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_d, cap_i, gana))
        print()
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"Resultado: pendiente_acelerada a {modo} (persistencia={velas_persistencia}) gana en {n_gana} de {len(resultados)} combinaciones frente a la diaria")
    return resultados


VELAS_PERSISTENCIA_12H_GRID = [1, 2, 3, 4]  # 12h, 24h, 36h, 48h
DIAS_GRACIA_GRID = [0, 1, 2, 3, 4, 5]  # dias tras la entrada sin comprobar pendiente_acelerada a 12h


def seleccion_robusta_con_gracia(años_ajuste=(2021, 2022, 2023)):
    """19-sept-2026: diagnostico operacion-a-operacion de la version 12h
    (persistencia=2) mostro que casi todas las peores diferencias frente a
    la diaria salen el dia+1..dia+5 -- el chequeo intradia confunde el
    vaiven normal de los primeros dias de una operacion nueva con una
    reversion real. Idea del usuario: darle un periodo de gracia (no
    comprobar pendiente_acelerada a 12h hasta que la operacion lleve N
    dias abierta) antes de descartar la resolucion mas fina del todo."""
    datos = _cargar("ETHUSDT")
    referencias = {}
    for año in años_ajuste:
        cand = candidatos_por_año(datos["df"], año)
        cap, *_ = _simular_cuenta(datos, cand, modo="diaria")
        referencias[año] = cap

    print(f"=== Barrido persistencia x dias_gracia (pendiente_acelerada a 12h) -- SOLO ETH {list(años_ajuste)} ===")
    resultados = []
    for gracia in DIAS_GRACIA_GRID:
        for velas in VELAS_PERSISTENCIA_12H_GRID:
            victorias, exceso_total = 0, 0.0
            for año in años_ajuste:
                cand = candidatos_por_año(datos["df"], año)
                cap, *_ = _simular_cuenta(datos, cand, modo="12h", velas_persistencia=velas, dias_gracia=gracia)
                cap_actual = referencias[año]
                if cap > cap_actual:
                    victorias += 1
                exceso_total += (cap - cap_actual) / cap_actual
            resultados.append((victorias, exceso_total, gracia, velas))

    resultados.sort(key=lambda r: (-r[0], -r[1]))
    print(f"{'gracia':>7} {'persist':>8} {'victorias':>10} {'exceso_medio':>13}")
    for v, exc, gracia, velas in resultados[:12]:
        print(f"{gracia:>6}d {velas:>7} ({velas*12}h) {v:>9}/{len(años_ajuste)} {exc/len(años_ajuste)*100:>11.2f}%")
    mejor = resultados[0]
    print(f"\n-> mas robusto: dias_gracia={mejor[2]}, velas_persistencia={mejor[3]} ({mejor[3]*12}h)")
    return mejor[2], mejor[3]


def confirmar_holdout_con_gracia(dias_gracia, velas_persistencia):
    print(f"\n=== Confirmacion holdout (ETH-2024 + BTC completo), pendiente_acelerada a 12h, "
          f"gracia={dias_gracia}d persistencia={velas_persistencia} ({velas_persistencia*12}h) ===")
    resultados = []
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        datos = _cargar(moneda)
        print(f"\n-- {moneda} --")
        for año in AÑOS:
            cand = candidatos_por_año(datos["df"], año)
            cap_d, n_d, gan_d, dd_d = _simular_cuenta(datos, cand, modo="diaria")
            cap_i, n_i, gan_i, dd_i = _simular_cuenta(datos, cand, modo="12h", velas_persistencia=velas_persistencia, dias_gracia=dias_gracia)
            gana = cap_i > cap_d
            print(f"  {año}: diaria {cap_d:.2f}€ ({n_d}/{gan_d}, dd {dd_d:.2f}%) -- "
                  f"12h gracia={dias_gracia}d {cap_i:.2f}€ ({n_i}/{gan_i}, dd {dd_i:.2f}%) -- {'GANA' if gana else 'pierde'}")
            resultados.append((moneda, año, cap_d, cap_i, gana))
        print()
    n_gana = sum(1 for *_, g in resultados if g)
    print(f"Resultado: pendiente_acelerada a 12h con gracia gana en {n_gana} de {len(resultados)} combinaciones frente a la diaria")
    return resultados


if __name__ == "__main__":
    gracia, velas = seleccion_robusta_con_gracia()
    confirmar_holdout_con_gracia(gracia, velas)
