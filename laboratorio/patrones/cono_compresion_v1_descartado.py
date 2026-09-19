"""
Primer intento (17-sept-2026) de un MOTOR NUEVO -- no otra salida mas --
para el problema de "racha rota ciega" documentado en
`sistema_confirmado_switch_14sept2026.py`: operaciones que suben 10-25%
limpio y luego bajan LENTO en zigzag sin que ningun patron de reversion
llegue a confirmarse. Ya se probaron 8 mecanismos de gestion de salida
distintos y todos fallaron -- la causa raiz es de DETECCION (falta un
motor que reconozca la forma de "cono de compresion/bajada lenta"), no de
cuando salir. Este fichero es ese primer intento de deteccion, y el
resultado es NEGATIVO -- se documenta completo por la misma disciplina de
"persistir siempre el script de validacion" que se aplica a cualquier
intento, exitoso o no.

Cuantificacion previa que motivo el intento (ver conversacion 17-sept):
de las operaciones que llegan a +10% de ganancia flotante, hay casos
genuinamente "ciegos" (cierran por stop o por tiempo maximo, SIN que
ningun mecanismo existente llegue a activarse): 12 en ETH (270.8pp
devueltos en total), 6 en BTC (105.5pp), 27 en XRP (667.9pp) -- XRP es,
con diferencia, la mas afectada.

DISEÑO (v1): puntuacion continua 0-1 combinando 3 dimensiones sobre una
ventana movil de W dias, causal:
  - deriva: cuanto se ha movido el precio en contra de la posicion en la
    ventana, saturando a DERIVA_OBJETIVO=6%.
  - lentitud: que ese movimiento sea LENTO (velocidad diaria media baja
    respecto al ATR), para no solaparse con pendiente_acelerada (que ya
    cubre las caidas RAPIDAS).
  - zigzag: fraccion de cambios de signo dia a dia en la ventana (alterna
    subida/bajada en vez de moverse en una sola direccion).
Combinadas con pesos iguales (1/3 cada una) -- ESTA ES LA SIMPLIFICACION
PRINCIPAL de este primer intento: la metodologia de `deteccion-flexible-
patrones` pide un CONJUNTO de configuraciones variando tambien los pesos
internos (no solo umbrales/ventanas), que aqui NO se hizo por ser un
primer paso exploratorio ("vemos si merece la pena" antes de invertir en
la maquinaria completa).

Grid en ETH: ventana en [2..22], umbral_disparo en [0.30..0.85] (144
combinaciones) -- resultado aparentemente MUY prometedor, mejora sobre
baseline (harness simplificado, sin venta parcial ni switch, por eso los
totales no son comparables a las cifras canonicas del sistema real) en
143 de 144 celdas, con una meseta amplia (no un pico aislado) alrededor de
ventana=5-8, umbral=0.30-0.45. Congelado ventana=7, umbral=0.40 (centro
de la meseta). Confirmado sin tocar nada en BTC (+27.0%) y XRP (+27.3%),
mejora casi identica a ETH (+24.0%) en las tres monedas -- una uniformidad
sospechosamente perfecta que debia comprobarse antes de creersela.

TEST DECISIVO -- Monte Carlo (17-sept-2026): ¿el disparo basado en la
puntuacion es mejor que disparar el MISMO NUMERO de veces pero en dias
elegidos al azar? Si el numero de dias de disparo es enorme (ver abajo),
la pregunta real es si el "donde" dispara importa, no solo el "cuanto".

Resultado -- Y AQUI SE ROMPE EL INTENTO: el disparo esta activo en el
**93-94% de todos los dias** en las 3 monedas (ETH 2523/2694=93.6%,
BTC 2493/2694=92.5%, XRP 2328/2494=93.3% aprox) -- no es un detector de
una forma rara y especifica, es casi un interruptor "sal pronto casi
siempre". Y comparando contra disparar en dias aleatorios con el MISMO
recuento:
  ETH (moneda de AJUSTE, se buscaron 144 configs para maximizarla): p=0.0000
  BTC (confirmacion, sin tocar nada):                                p=0.1400 (NO significativo)
  XRP (confirmacion, sin tocar nada):                                p=0.9733 (PEOR que el 97% del azar)

Es decir: la mejora de +24-27% NO viene de detectar de verdad el cono de
compresion -- viene de que, en este backtest, salir pronto y a menudo (de
casi cualquier forma) ya mejora el resultado. En ETH parece funcionar
porque se buscaron los parametros que mejor encajaban con ESE historial
concreto (sobreajuste). En las monedas donde no se toco nada, el mismo
mecanismo no es mejor que salir en dias aleatorios -- en XRP es
literalmente peor que el azar la mayoria de las veces. Firma clasica de
sobreajuste: funciona solo donde se ajusto, no generaliza.

Veredicto: DESCARTADO tal cual. La puntuacion v1 es demasiado permisiva
(el umbral de disparo se alcanza casi cualquier dia porque los objetivos
de saturacion -- 6% de deriva en 5-14 dias, ratio de lentitud, zigzag --
son demasiado faciles de cumplir en un activo tan volatil como cripto).
Para que esto sea un motor de verdad (no una salida generica disfrazada),
la puntuacion tiene que ser mucho mas EXIGENTE -- disparar en un
porcentaje pequeño de dias (un cono de compresion real deberia ser algo
infrecuente, no presente 9 de cada 10 dias), y el conjunto de
configuraciones deberia variar tambien los PESOS internos, no solo
ventana/umbral, siguiendo la metodologia completa de
`deteccion-flexible-patrones` que aqui se simplifico. Ver
`registro/intentos.jsonl`.
"""

import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc
from salidas.stop_objetivo import calcular_niveles_fijos
from tamano.tamano import calcular_tamano
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import CAPITAL_INICIAL, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX, RIESGO_BASE_PCT

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}
K_ATR_STOP, R_FIJO, DIAS_MAXIMO = sc.K_ATR_STOP, sc.R_FIJO, 45
UMBRAL_PENDIENTE = 1.5

# --- deteccion: puntuacion continua de "cono de compresion" ---
DERIVA_OBJETIVO = 0.06  # 6% de caida/subida neta en la ventana ya satura la dimension de deriva

def puntuacion_cono(df, atr, ventana, pesos=(1/3, 1/3, 1/3)):
    close = df["close"].to_numpy()
    n = len(close)
    ret = np.full(n, np.nan)
    ret[1:] = close[1:] / close[:-1] - 1
    score_largo = np.zeros(n)
    score_corto = np.zeros(n)
    w_deriva, w_lentitud, w_zigzag = pesos
    for i in range(ventana, n):
        r = ret[i - ventana + 1: i + 1]
        if np.isnan(r).any() or np.isnan(atr[i]) or atr[i] <= 0:
            continue
        deriva = close[i] / close[i - ventana] - 1
        lentitud_ratio = np.mean(np.abs(r)) / (atr[i] / close[i])
        signos = np.sign(r)
        signos = signos[signos != 0]
        cambios = np.mean(signos[1:] != signos[:-1]) if len(signos) > 1 else 0.0

        s_lentitud = np.clip(1 - lentitud_ratio, 0, 1)
        s_zigzag = cambios

        s_deriva_largo = np.clip(-deriva / DERIVA_OBJETIVO, 0, 1)
        score_largo[i] = w_deriva * s_deriva_largo + w_lentitud * s_lentitud + w_zigzag * s_zigzag

        s_deriva_corto = np.clip(deriva / DERIVA_OBJETIVO, 0, 1)
        score_corto[i] = w_deriva * s_deriva_corto + w_lentitud * s_lentitud + w_zigzag * s_zigzag
    return score_largo, score_corto


def simular_con_cono(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                      senal_externa, pendiente, umbral, score_cono, umbral_cono):
    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        toca_stop = low[i] <= niveles.stop if direccion == "largo" else high[i] >= niveles.stop
        toca_objetivo = high[i] >= niveles.objetivo if direccion == "largo" else low[i] <= niveles.objetivo
        if toca_stop:
            return dict(idx_salida=i, precio_salida=niveles.stop, motivo="stop")
        if toca_objetivo:
            return dict(idx_salida=i, precio_salida=niveles.objetivo, motivo="objetivo")

        p = pendiente[i]
        if not np.isnan(p):
            cae_fuerte = (p <= -umbral) if direccion == "largo" else (p >= umbral)
            if cae_fuerte:
                return dict(idx_salida=i, precio_salida=close[i], motivo="pendiente_acelerada")

        if senal_externa is not None and senal_externa[i]:
            if np.isnan(p):
                return dict(idx_salida=i, precio_salida=close[i], motivo="racha_rota")
            if direccion == "largo":
                pendiente_extremo = max(pendiente_extremo, p)
                honra = pendiente_extremo <= 0 or p <= pendiente_extremo * (1 - sc.UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            else:
                pendiente_extremo = min(pendiente_extremo, p)
                honra = pendiente_extremo >= 0 or p >= pendiente_extremo * (1 - sc.UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            if honra:
                return dict(idx_salida=i, precio_salida=close[i], motivo="racha_rota")
        else:
            if not np.isnan(p):
                pendiente_extremo = max(pendiente_extremo, p) if direccion == "largo" else min(pendiente_extremo, p)

        # NUEVO: motor cono de compresion
        sc_dir = score_cono[0][i] if direccion == "largo" else score_cono[1][i]
        if sc_dir >= umbral_cono:
            return dict(idx_salida=i, precio_salida=close[i], motivo="cono_compresion")
    return dict(idx_salida=fin, precio_salida=close[fin], motivo="tiempo_maximo")


def simular_cuenta_cono(df, candidatos, atr, rt, rs, pend, score_cono, umbral_cono):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    abierta = None

    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = rt if direccion == "largo" else rs
        r = simular_con_cono(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pend, UMBRAL_PENDIENTE, score_cono, umbral_cono)
        if r is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        r.update(idx_entrada=idx, direccion=direccion, probabilidad=prob, precio_entrada=close[idx], unidades=pos.unidades)
        return r

    def _cerrar(pos):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        capital += pos["unidades"] * (pos["precio_salida"] - pos["precio_entrada"]) * signo

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
    if abierta is not None:
        _cerrar(abierta)
    return capital


if __name__ == "__main__":
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    cand_por_año = {año: candidatos_por_año(df, año) for año in AÑOS}

    # baseline sin cono (motivo cono_compresion nunca dispara con umbral=2.0, imposible)
    print("=== BASELINE (sin cono) ===")
    total_base = 0.0
    for año in AÑOS:
        cap = simular_cuenta_cono(df, cand_por_año[año], atr, rt, rs, pend, (np.zeros(len(df)), np.zeros(len(df))), 2.0)
        total_base += cap
        print(f"  {año}: {cap:.2f}")
    print(f"  TOTAL={total_base:.2f}")

    print("\n=== GRID: ventana x umbral_cono ===")
    mejor = (None, -1)
    for ventana in [5, 7, 10, 14]:
        score = puntuacion_cono(df, atr, ventana)
        for umbral_cono in [0.5, 0.55, 0.6, 0.65, 0.7, 0.75]:
            total = 0.0
            for año in AÑOS:
                total += simular_cuenta_cono(df, cand_por_año[año], atr, rt, rs, pend, score, umbral_cono)
            print(f"  ventana={ventana:2d} umbral={umbral_cono:.2f}: TOTAL={total:.2f}  (vs base {total_base:.2f}, delta={total-total_base:+.2f})")
            if total > mejor[1]:
                mejor = ((ventana, umbral_cono), total)
    print(f"\nGANADOR ETH: {mejor}")

def grid_amplio():
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    cand_por_año = {año: candidatos_por_año(df, año) for año in AÑOS}
    total_base = sum(simular_cuenta_cono(df, cand_por_año[año], atr, rt, rs, pend, (np.zeros(len(df)), np.zeros(len(df))), 2.0) for año in AÑOS)
    print(f"BASE={total_base:.2f}\n")
    resultados = {}
    for ventana in [2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 18, 22]:
        score = puntuacion_cono(df, atr, ventana)
        fila = []
        for umbral_cono in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]:
            total = sum(simular_cuenta_cono(df, cand_por_año[año], atr, rt, rs, pend, score, umbral_cono) for año in AÑOS)
            resultados[(ventana, umbral_cono)] = total
            fila.append(f"{umbral_cono:.2f}:{total:6.0f}")
        print(f"v={ventana:2d}  " + "  ".join(fila))
    ganador = max(resultados, key=resultados.get)
    print(f"\nGANADOR: {ganador} -> {resultados[ganador]:.2f}  (base={total_base:.2f}, mejora={resultados[ganador]-total_base:+.2f})")

grid_amplio()

def confirmar_congelado():
    VENTANA_FINAL, UMBRAL_FINAL = 7, 0.40
    print(f"\n=== CONFIRMACION CONGELADA (ventana={VENTANA_FINAL}, umbral={UMBRAL_FINAL}) ===")
    for nombre, cargador in MONEDAS.items():
        df, atr, rt, rs, pend, cl, cc = cargador()
        cand_por_año = {año: candidatos_por_año(df, año) for año in AÑOS}
        total_base = sum(simular_cuenta_cono(df, cand_por_año[año], atr, rt, rs, pend, (np.zeros(len(df)), np.zeros(len(df))), 2.0) for año in AÑOS)
        score = puntuacion_cono(df, atr, VENTANA_FINAL)
        por_año = {}
        total = 0.0
        for año in AÑOS:
            cap = simular_cuenta_cono(df, cand_por_año[año], atr, rt, rs, pend, score, UMBRAL_FINAL)
            por_año[año] = round(cap, 2)
            total += cap
        print(f"{nombre}: BASE={total_base:.2f}  CON_CONO={total:.2f}  delta={total-total_base:+.2f} ({(total/total_base-1)*100:+.1f}%)  por_año={por_año}")

confirmar_congelado()

def simular_con_cono_random(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                             senal_externa, pendiente, umbral, mask_random_cono):
    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        toca_stop = low[i] <= niveles.stop if direccion == "largo" else high[i] >= niveles.stop
        toca_objetivo = high[i] >= niveles.objetivo if direccion == "largo" else low[i] <= niveles.objetivo
        if toca_stop:
            return dict(idx_salida=i, precio_salida=niveles.stop, motivo="stop")
        if toca_objetivo:
            return dict(idx_salida=i, precio_salida=niveles.objetivo, motivo="objetivo")
        p = pendiente[i]
        if not np.isnan(p):
            cae_fuerte = (p <= -umbral) if direccion == "largo" else (p >= umbral)
            if cae_fuerte:
                return dict(idx_salida=i, precio_salida=close[i], motivo="pendiente_acelerada")
        if senal_externa is not None and senal_externa[i]:
            if np.isnan(p):
                return dict(idx_salida=i, precio_salida=close[i], motivo="racha_rota")
            if direccion == "largo":
                pendiente_extremo = max(pendiente_extremo, p)
                honra = pendiente_extremo <= 0 or p <= pendiente_extremo * (1 - sc.UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            else:
                pendiente_extremo = min(pendiente_extremo, p)
                honra = pendiente_extremo >= 0 or p >= pendiente_extremo * (1 - sc.UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            if honra:
                return dict(idx_salida=i, precio_salida=close[i], motivo="racha_rota")
        else:
            if not np.isnan(p):
                pendiente_extremo = max(pendiente_extremo, p) if direccion == "largo" else min(pendiente_extremo, p)
        if mask_random_cono[i]:
            return dict(idx_salida=i, precio_salida=close[i], motivo="cono_random")
    return dict(idx_salida=fin, precio_salida=close[fin], motivo="tiempo_maximo")


def simular_cuenta_cono_random(df, candidatos, atr, rt, rs, pend, mask_random_cono):
    close = df["close"].to_numpy()
    capital = CAPITAL_INICIAL
    abierta = None
    def _abrir(idx, direccion, prob):
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = rt if direccion == "largo" else rs
        r = simular_con_cono_random(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal, pend, UMBRAL_PENDIENTE, mask_random_cono)
        if r is None:
            return None
        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        r.update(idx_entrada=idx, direccion=direccion, probabilidad=prob, precio_entrada=close[idx], unidades=pos.unidades)
        return r
    def _cerrar(pos):
        nonlocal capital
        signo = 1 if pos["direccion"] == "largo" else -1
        capital += pos["unidades"] * (pos["precio_salida"] - pos["precio_entrada"]) * signo
    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        if abierta is not None and idx > abierta["idx_salida"]:
            _cerrar(abierta); abierta = None
        if abierta is None:
            nueva = _abrir(idx, direccion, prob)
            if nueva is not None:
                abierta = nueva
    if abierta is not None:
        _cerrar(abierta)
    return capital


def montecarlo_random_mismo_conteo(n_perm=300, semilla=42):
    VENTANA_FINAL, UMBRAL_FINAL = 7, 0.40
    print(f"\n=== Monte Carlo: mismo NUMERO de dias de disparo, pero al azar (n_perm={n_perm}) ===")
    for nombre, cargador in MONEDAS.items():
        df, atr, rt, rs, pend, cl, cc = cargador()
        n = len(df)
        cand_por_año = {año: candidatos_por_año(df, año) for año in AÑOS}
        score = puntuacion_cono(df, atr, VENTANA_FINAL)
        mask_largo_real = score[0] >= UMBRAL_FINAL
        mask_corto_real = score[1] >= UMBRAL_FINAL
        mask_real = mask_largo_real | mask_corto_real
        n_disparo = int(mask_real.sum())

        total_real = sum(simular_cuenta_cono(df, cand_por_año[año], atr, rt, rs, pend, score, UMBRAL_FINAL) for año in AÑOS)

        rng = np.random.default_rng(semilla)
        idx_validos = np.arange(n)
        totales_azar = []
        for _ in range(n_perm):
            mask_azar = np.zeros(n, dtype=bool)
            mask_azar[rng.choice(idx_validos, size=n_disparo, replace=False)] = True
            cap_azar = sum(simular_cuenta_cono_random(df, cand_por_año[año], atr, rt, rs, pend, mask_azar) for año in AÑOS)
            totales_azar.append(cap_azar)
        totales_azar = np.array(totales_azar)
        p_valor = float(np.mean(totales_azar >= total_real))
        print(f"{nombre}: n_dias_disparo={n_disparo}  real={total_real:.2f}  media_azar={totales_azar.mean():.2f}  "
              f"p10_azar={np.percentile(totales_azar,10):.2f}  p90_azar={np.percentile(totales_azar,90):.2f}  p-valor={p_valor:.4f}")

montecarlo_random_mismo_conteo()
