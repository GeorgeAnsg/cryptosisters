"""
Motor de doble techo -- capas 1-4, graduado desde laboratorio el
12-sept-2026. Historial completo de validacion (que se probo, que se
descarto y por que) en laboratorio/patrones/doble_techo_motor_v2.py -- este
fichero es la version LIMPIA para produccion, no repite esa narrativa.

CAPA 1 -- FORMA: nivel/caida/tiempo/altura (geometria pura, sin mercado).
CAPA 2 -- REGIMEN: ver motores/regimen_mercado.py (BAJISTA/ALCISTA/NEUTRO).
CAPA 3 -- CONTEXTO especifico del regimen:
  BAJISTA: nivel ya repetido antes + todavia relativamente cerca del ATH
    (combo mas fuerte, validado con cruce de moneda y de tiempo, y
    confirmado de nuevo en la particion de Validacion 2025).
  ALCISTA: cercania al ATH, mas debil (solo confirmado en 2/4 cortes) --
    se incluye con menos peso (DESCUENTO_CONTEXTO_ALCISTA).
  NEUTRO: sin pieza de contexto validada -- no se inventa un numero.
CAPA 4 -- CONFIRMACION CRUZADA: separada, NUNCA mezclada en
  probabilidad_total (es evidencia de mercado, no del patron propio).

REQUISITO OPERATIVO PARA VIVO: `dist_ath_pct` usa el maximo desde el ORIGEN
del historico (no una ventana movil) -- ver la nota completa en
motores/regimen_mercado.py. El bot en vivo debe mantener el historico
diario COMPLETO desde el listing.

CAMPOS QUE NO SE HAN TRAIDO desde el laboratorio (a proposito): RSI en
techo1/techo2, divergencia de RSI, y volumen tras el segundo techo. Los tres
se probaron en laboratorio/patrones/doble_techo_flexible.py pero quedaron
como "solo registrados, nunca puntuan" -- una hipotesis abierta, nunca
cerrada con cruce de moneda/tiempo. Ademas, el volumen tal como esta medido
alli mira hasta 6 dias DESPUES del techo2 -- valido para explorar en
backtest, pero no utilizable tal cual para una decision en el mismo dia del
patron. Si algun dia se valida de verdad, se trae entonces, no antes.
Tampoco se trae `n_parejas_alternativas_decentes` (penalizacion de
ambiguedad con un umbral de 0.3 sin derivar, pensada para el enfoque de
consenso por grid -- este motor no lo usa).
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from dataclasses import dataclass

import numpy as np
import pandas as pd

from motores import regimen_mercado
from motores.regimen_mercado import TipoRegimen

# Derivado de datos reales (ver laboratorio/patrones/doble_techo_motor_v2.py):
# distancia real al ATH entre candidatos bajista+nivel_repetido (ETH+BTC,
# n=115): percentiles 10/25/50/75/90 = 43/61/66/75/89 -- saturacion puesta
# en el p90 real, en vez de un numero elegido a ojo (antes era 30, sin
# calibrar, y aplastaba casi todo 2022 a la nota minima).
DIST_ATH_IDEAL_PCT = 90.0

# Derivado de datos reales: retorno medio bajista+nivel+ATH ~-14.9% (4/4
# cortes) vs alcista+ATH ~-6.3% (2/4 cortes) -- ratio ~0.42. El lado
# alcista pesa menos porque su efecto medido es menos de la mitad de
# fuerte, ademas de confirmar en la mitad de los cortes.
DESCUENTO_CONTEXTO_ALCISTA = 0.42

# NO DERIVADOS AUN de un barrido real -- heredados sin cambio del
# laboratorio (misma logica que en regimen_mercado.py) para no alterar los
# resultados ya validados con ellos. Decision del 12-sept-2026: se
# calibran junto con los otros 3 numeros pendientes (ver
# motores/regimen_mercado.py) en una sola pasada, cuando exista el
# pipeline completo (entradas+salidas+tamano+cartera), antes de operar con
# dinero real -- no antes.
#
# A diferencia de los umbrales de regimen_mercado.py (que dependen de una
# distribucion de precios y se pueden mirar con un percentil), este numero
# depende de otra cosa: que tan parecidos suelen salir dos techos que un
# trader llamaria "el mismo nivel repetido" frente a dos techos sin
# relacion -- eso no sale de un percentil simple (una comprobacion cruda
# de TODAS las parejas de techos de la serie, sin filtrar por cercania
# temporal, sale con una mediana de 135% de diferencia porque mezcla
# techos de eras de precio distintas, un numero inutil para calibrar
# directamente). Se deriva probando varias tolerancias (2%, 5%, 8%, 12%...)
# y viendo cual separa mejor los resultados reales, igual que el barrido
# de pesos que ya usa el proyecto en otros sitios.
TOLERANCIA_NIVEL_PATRON_PREVIO_PCT = 5.0  # cuanto de parecido cuenta como "mismo nivel"
GAP_MINIMO_VELAS_NIVEL_PREVIO = 3          # separacion minima para contar un patron previo como distinto


@dataclass
class CandidatoDobleTecho:
    idx_techo1: int
    idx_techo2: int
    probabilidad_forma: float  # SOLO geometria: nivel, caida, tiempo, altura
    diferencia_nivel_pct: float
    caida_intermedia_pct: float
    dias_entre_techos: int


@dataclass
class CandidatoMotor:
    candidato: CandidatoDobleTecho
    score_forma: float
    tipo_regimen: TipoRegimen
    score_regimen: float          # que tan marcado esta ese regimen (0-1)
    score_contexto: float         # capa 3, depende del tipo_regimen
    probabilidad_total: float     # combinacion de forma + contexto (SIN la capa 4)
    detalle_contexto: dict        # piezas sueltas de la capa 3, para inspeccionar


def _detectar_techos_simple(close: np.ndarray, ventana: int = 3) -> list[int]:
    """Maximos locales causales: un techo en `i` solo se confirma una vez
    vistas `ventana` velas posteriores sin que ninguna lo supere -- en
    vivo, "hoy fue un techo" solo se sabe `ventana` dias despues, nunca
    antes de eso."""
    n = len(close)
    techos = []
    for i in range(ventana, n - ventana):
        vp = close[i - ventana: i + ventana + 1]
        if close[i] == vp.max():
            techos.append(i)
    return techos


# Pesos/ideales de CAPA 1 por defecto -- unica fuente de verdad. Antes
# `entradas/doble_techo.py` (probabilidad en vivo) tenia su PROPIA copia de
# estos numeros, desincronizada de la de aqui (0.35/0.25/0.10/0.30 en vez
# de estos) -- el dia 3 (ya confirmado del todo) de la version en vivo NO
# coincidia exactamente con este motor batch (diferencia de ~10% relativo
# comprobada el 12-sept-2026). `_score_pareja_forma()` de abajo es ahora la
# UNICA funcion que calcula esto; `entradas/doble_techo.py` la importa en
# vez de reimplementarla, para que no puedan volver a desincronizarse.
TOLERANCIA_NIVEL_PCT_DEFECTO = 15.0
CAIDA_IDEAL_PCT_DEFECTO = 8.0
ALTURA_IDEAL_PCT_DEFECTO = 20.0
PESO_NIVEL_DEFECTO = 0.15
PESO_CAIDA_DEFECTO = 0.15
PESO_TIEMPO_DEFECTO = 0.10
PESO_ALTURA_DEFECTO = 0.60


def _score_pareja_forma(
    precio1: float,
    precio2: float,
    minimo_intermedio: float,
    tolerancia_nivel_pct: float = TOLERANCIA_NIVEL_PCT_DEFECTO,
    caida_ideal_pct: float = CAIDA_IDEAL_PCT_DEFECTO,
    altura_ideal_pct: float = ALTURA_IDEAL_PCT_DEFECTO,
    peso_nivel: float = PESO_NIVEL_DEFECTO,
    peso_caida: float = PESO_CAIDA_DEFECTO,
    peso_tiempo: float = PESO_TIEMPO_DEFECTO,
    peso_altura: float = PESO_ALTURA_DEFECTO,
) -> tuple[float, float, float]:
    """CAPA 1 -- forma de una pareja (techo1, techo2) concreta. Devuelve
    (probabilidad_forma, diferencia_nivel_pct, caida_intermedia_pct).

    Nota: `peso_tiempo` existe como parametro pero `score_tiempo` vale
    siempre 1.0 mas abajo -- hoy esa dimension no discrimina nada (es un
    hueco pendiente, no una funcion real). Al ser una constante igual para
    todos los candidatos no cambia el orden relativo entre ellos, pero
    conviene saberlo antes de confiar en ese 10% de peso como si estuviera
    midiendo algo."""
    diferencia_nivel_pct = (precio2 - precio1) / precio1 * 100
    caida_intermedia_pct = (max(precio1, precio2) - minimo_intermedio) / max(precio1, precio2) * 100

    score_nivel = max(0.0, 1 - abs(diferencia_nivel_pct) / tolerancia_nivel_pct)
    score_caida = min(caida_intermedia_pct / caida_ideal_pct, 1.0)
    score_altura = min(caida_intermedia_pct / altura_ideal_pct, 1.0)
    score_tiempo = 1.0

    probabilidad_forma = (peso_nivel * score_nivel + peso_caida * score_caida
                           + peso_tiempo * score_tiempo + peso_altura * score_altura)
    return probabilidad_forma, diferencia_nivel_pct, caida_intermedia_pct


def detectar(
    df: pd.DataFrame,
    ventana_min_dias: int = 4,
    ventana_max_dias: int = 45,
    tolerancia_nivel_pct: float = TOLERANCIA_NIVEL_PCT_DEFECTO,
    caida_ideal_pct: float = CAIDA_IDEAL_PCT_DEFECTO,
    peso_nivel: float = PESO_NIVEL_DEFECTO,
    peso_caida: float = PESO_CAIDA_DEFECTO,
    peso_tiempo: float = PESO_TIEMPO_DEFECTO,
    peso_altura: float = PESO_ALTURA_DEFECTO,
    altura_ideal_pct: float = ALTURA_IDEAL_PCT_DEFECTO,
) -> list[CandidatoDobleTecho]:
    """CAPA 1 -- forma. Ver `_score_pareja_forma()` para la formula real."""
    close = df["close"].to_numpy()
    techos = _detectar_techos_simple(close)

    candidatos: list[CandidatoDobleTecho] = []
    for pos2, idx2 in enumerate(techos):
        precio2 = close[idx2]
        parejas = []
        for idx1 in techos[:pos2]:
            dias = idx2 - idx1
            if dias < ventana_min_dias or dias > ventana_max_dias:
                continue
            precio1 = close[idx1]
            minimo_intermedio = close[idx1:idx2 + 1].min()
            probabilidad_forma, diferencia_nivel_pct, caida_intermedia_pct = _score_pareja_forma(
                precio1, precio2, minimo_intermedio, tolerancia_nivel_pct, caida_ideal_pct,
                altura_ideal_pct, peso_nivel, peso_caida, peso_tiempo, peso_altura,
            )
            parejas.append((idx1, probabilidad_forma, diferencia_nivel_pct, caida_intermedia_pct, dias))

        if not parejas:
            continue
        parejas.sort(key=lambda p: p[1], reverse=True)
        mejor = parejas[0]
        candidatos.append(CandidatoDobleTecho(
            idx_techo1=mejor[0], idx_techo2=idx2, probabilidad_forma=round(mejor[1], 3),
            diferencia_nivel_pct=round(mejor[2], 2), caida_intermedia_pct=round(mejor[3], 2),
            dias_entre_techos=mejor[4],
        ))
    return candidatos


def _score_ath(dist_ath_pct: float, ideal_pct: float = DIST_ATH_IDEAL_PCT) -> float:
    if dist_ath_pct != dist_ath_pct:
        return 1e-3
    return max(1.0 - dist_ath_pct / ideal_pct, 1e-3)


def calcular(
    df: pd.DataFrame,
    peso_forma: float = 0.5,
    peso_contexto: float = 0.5,
    **kwargs_detectar,
) -> list[CandidatoMotor]:
    """Capas 1-3. La capa 4 (confirmacion cruzada) se calcula aparte con
    `confirmacion_cruzada()`, a proposito fuera de esta funcion.

    `peso_forma`/`peso_contexto` (50/50 por defecto) son un reparto neutral
    razonable, pero -- a diferencia de los pesos internos de `detectar()`,
    que ya se barrieron en el laboratorio -- este reparto en concreto nunca
    se ha barrido contra alternativas. Pendiente, igual que las constantes
    de arriba marcadas como NO DERIVADAS."""
    candidatos = detectar(df, **kwargs_detectar)
    close_s = df["close"]
    close = close_s.to_numpy()
    sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)

    ordenados = sorted(candidatos, key=lambda c: c.idx_techo2)
    niveles_previos: list[tuple[int, float]] = []
    resultados = []

    for c in ordenados:
        tipo, score_regimen = regimen_mercado.clasificar(df, c.idx_techo2, sma200)
        dist_ath_pct = (ath_hasta[c.idx_techo2] - close[c.idx_techo2]) / ath_hasta[c.idx_techo2] * 100
        score_ath = _score_ath(dist_ath_pct)

        nivel_actual = (close[c.idx_techo1] + close[c.idx_techo2]) / 2
        patron_previo = any(
            idx2p < c.idx_techo1 - GAP_MINIMO_VELAS_NIVEL_PREVIO
            and abs(nivp - nivel_actual) / nivel_actual * 100 <= TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
            for idx2p, nivp in niveles_previos
        )
        niveles_previos.append((c.idx_techo2, nivel_actual))

        detalle = {"dist_ath_pct": round(dist_ath_pct, 1), "score_ath": round(score_ath, 3)}

        if tipo == TipoRegimen.BAJISTA:
            # El regimen bajista ya es, por si solo, un factor valido y
            # universal (5 monedas) -- nunca se aplasta. nivel_repetido+ATH
            # es un EXTRA que refuerza cuando esta presente; su ausencia es
            # neutra (no hay ese dato), no evidencia negativa.
            score_contexto = (score_regimen * score_ath) ** 0.5 if patron_previo else score_regimen
            detalle["combo_fuerte_nivel_mas_ath"] = patron_previo
        elif tipo == TipoRegimen.ALCISTA:
            score_contexto = max((score_regimen * score_ath) ** 0.5 * DESCUENTO_CONTEXTO_ALCISTA, 1e-3)
            detalle["nota"] = "regimen+ATH, confirmado en 2/4 cortes -- descontado"
        else:
            score_contexto = 1e-3
            detalle["nota"] = "sin pieza de contexto validada para regimen neutro"

        prob_forma_safe = max(c.probabilidad_forma, 1e-3)
        score_contexto_safe = max(score_contexto, 1e-3)
        probabilidad_total = prob_forma_safe ** peso_forma * score_contexto_safe ** peso_contexto

        resultados.append(CandidatoMotor(
            candidato=c, score_forma=c.probabilidad_forma, tipo_regimen=tipo,
            score_regimen=round(score_regimen, 3), score_contexto=round(score_contexto, 3),
            probabilidad_total=round(probabilidad_total, 3), detalle_contexto=detalle,
        ))
    return resultados


def confirmacion_cruzada(
    df_propio: pd.DataFrame, resultados_propio: list[CandidatoMotor],
    df_otro: pd.DataFrame, resultados_otro: list[CandidatoMotor],
    ventana_dias: int = 2,
) -> dict[int, bool]:
    """CAPA 4, separada -- NUNCA mezclada en probabilidad_total.

    AVISO DE CAUSALIDAD: la ventana es +/- `ventana_dias` (mira hacia atras
    Y hacia adelante del techo2 propio). Eso es correcto para backtest (los
    dos historicos ya estan completos), pero NO es utilizable tal cual para
    una decision EN VIVO en el instante del techo2 propio -- la mitad
    "hacia adelante" de la ventana todavia no ha ocurrido. Antes de conectar
    esto a una entrada real, hay que decidir si se usa solo la mitad hacia
    atras, o si se acepta el retraso de `ventana_dias` como parte de la
    regla de entrada."""
    fechas_propio = df_propio["open_time"]
    fechas_otro = pd.DatetimeIndex([df_otro["open_time"].iloc[r.candidato.idx_techo2] for r in resultados_otro])
    out = {}
    for r in resultados_propio:
        fecha2 = fechas_propio.iloc[r.candidato.idx_techo2]
        diffs = np.abs((fechas_otro - fecha2).days) if len(fechas_otro) else np.array([])
        out[r.candidato.idx_techo2] = bool(len(diffs) > 0 and diffs.min() <= ventana_dias)
    return out
