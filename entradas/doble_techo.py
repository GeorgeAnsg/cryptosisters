"""
Regla de entrada para doble techo, graduada desde
laboratorio/patrones/probabilidad_en_vivo_techo.py el 12-sept-2026.

CONCLUSION VALIDADA (laboratorio/patrones/umbral_decision_en_vivo.py,
ETH-ajuste / ETH-tiempo / BTC, re-confirmada el 12-sept-2026 con la logica
ya corregida de aqui sobre BTC/ETH completos): esperar a que la confianza
en vivo suba NO mejora el resultado frente a entrar en cuanto el motor
detecta el candidato -- dia 0 da 3.39%/3.29% de retorno medio (techo,
BTC/ETH) frente a -0.34%/0.91% esperando a 50% de confianza y -1.56%/-2.36%
esperando a 90%. No hay umbral de confianza que esperar -- la regla es
entrar en el DIA 0.

OJO, matiz importante: "dia 0" NO significa operar cualquier maximo
aparente sin mas filtro -- eso se probo por accidente al re-verificar esto
y da un retorno medio malo (la mayoria de maximos aparentes nunca llegan a
ser un patron real). El filtro sigue siendo `probabilidad_total`/
`probabilidad_en_vivo` (continuo, sin cortes duros); "dia 0" solo dice que,
una vez ahi, no hay que esperar mas dias de confirmacion pensando que la
nota va a subir y merecer mas la pena -- no mejora.

POR QUE "DIA 0" NO ES idx_techo2 DEL MOTOR: `motores/doble_techo.py`
detecta un techo2 con una ventana CENTRADA (`_detectar_techos_simple`,
mira 3 dias hacia el pasado Y 3 hacia el futuro) -- correcto para
backtest, pero en vivo esa confirmacion solo llega 3 dias despues del pico
real. "Dia 0" aqui es el MAXIMO APARENTE: el dia mas alto de los ultimos 3
dias (incluyendose el mismo) -- esto SI se sabe en tiempo real, sin mirar
al futuro.

CORRECCION DE ARQUITECTURA (12-sept-2026): la version original en
laboratorio tenia su PROPIA copia de los pesos de forma
(peso_nivel=0.35/peso_caida=0.25/peso_altura=0.30), desincronizada de los
que trae `motores/doble_techo.py` (0.15/0.15/0.60) -- el dia 3 (ya
confirmado del todo) no coincidia exactamente con el numero del motor
batch (diferencia de ~10% relativo, comprobada con datos reales). Aqui se
importa `_score_pareja_forma()` directamente del motor graduado en vez de
reimplementar la formula, para que el dia 3 sea identico al numero ya
validado POR CONSTRUCCION, no por sincronizacion manual que se puede
volver a romper.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from dataclasses import dataclass

import numpy as np
import pandas as pd

from motores import doble_techo as motor
from motores import regimen_mercado
from motores.regimen_mercado import TipoRegimen

# Curva empirica (laboratorio/patrones/probabilidad_evolutiva_techo.py,
# promedio ETH+BTC, historial completo, sin segmentar por volatilidad --
# se vio que no discrimina): P(que el maximo aparente termine confirmado
# como techo2 real) segun cuantos dias lleva sin ser superado.
CURVA_SUPERVIVENCIA_TECHO = {0: 0.31, 1: 0.71, 2: 0.85, 3: 1.0}


@dataclass
class CandidatoEntradaTecho:
    idx_maximo_aparente: int
    dia_transcurrido: int  # 0-3 (3 = confirmado del todo)
    probabilidad_total_si_confirma: float  # score completo del motor, tratando este punto como techo2
    probabilidad_en_vivo: float  # la anterior * curva de supervivencia del dia


def maximos_aparentes(close: np.ndarray, ventana_pasada: int = 3) -> list[int]:
    """Un dia `i` es 'maximo aparente' si es el mas alto de los ultimos
    `ventana_pasada` dias (incluyendose el mismo) -- se sabe en tiempo
    real, sin mirar al futuro. Distinto de un techo confirmado por
    `motores.doble_techo._detectar_techos_simple` (esa exige tambien
    margen HACIA ADELANTE, solo disponible en backtest)."""
    n = len(close)
    return [i for i in range(ventana_pasada, n) if close[i] == close[i - ventana_pasada: i + 1].max()]


def calcular_en_vivo(
    df: pd.DataFrame,
    idx_maximo_aparente: int,
    dia_transcurrido: int,
    ventana_min_dias: int = 4,
    ventana_max_dias: int = 45,
    peso_forma: float = 0.5,
    peso_contexto: float = 0.5,
) -> CandidatoEntradaTecho | None:
    """Trata `idx_maximo_aparente` COMO SI fuera el techo2 definitivo (su
    precio ya se conoce; lo que no se sabe aun es si seguira siendo el mas
    alto) y multiplica por la curva de supervivencia del dia transcurrido."""
    close_s = df["close"]
    close = close_s.to_numpy()

    techos_confirmados = motor._detectar_techos_simple(close)
    techo1_opciones = [t for t in techos_confirmados if t < idx_maximo_aparente]
    if not techo1_opciones:
        return None

    precio2 = close[idx_maximo_aparente]
    mejor_score, idx_techo1 = -1.0, None
    for idx1 in techo1_opciones:
        dias = idx_maximo_aparente - idx1
        if dias < ventana_min_dias or dias > ventana_max_dias:
            continue
        precio1 = close[idx1]
        minimo_intermedio = close[idx1: idx_maximo_aparente + 1].min()
        prob_forma, _, _ = motor._score_pareja_forma(precio1, precio2, minimo_intermedio)
        if prob_forma > mejor_score:
            mejor_score, idx_techo1 = prob_forma, idx1

    if idx_techo1 is None:
        return None
    # redondeado igual que `CandidatoDobleTecho.probabilidad_forma` en
    # motor.detectar() -- si no se redondea aqui tambien, probabilidad_total
    # sale a un ~0.001 del numero del motor batch por el redondeo interno
    # que este ya aplica antes de usarlo (comprobado el 12-sept-2026).
    probabilidad_forma = round(mejor_score, 3)

    sma200 = close_s.rolling(200).mean()
    ath_hasta = np.maximum.accumulate(close)
    tipo, score_regimen = regimen_mercado.clasificar(df, idx_maximo_aparente, sma200)

    nivel_actual = (close[idx_techo1] + precio2) / 2
    limite_previos = idx_techo1 - motor.GAP_MINIMO_VELAS_NIVEL_PREVIO
    # mismo criterio que motor.calcular(): "nivel repetido" = existe OTRO
    # techo2 ya confirmable (misma deteccion causal del motor, sobre TODO
    # el historico disponible hasta hoy) con idx_techo2 < techo1 - GAP, a
    # un nivel parecido. Antes esto se derivaba re-detectando sobre un
    # trozo truncado del historico (df.iloc[:limite_previos]) -- se
    # cambio el 12-sept-2026 porque esa re-deteccion, cerca del propio
    # corte, puede fallar en confirmar un techo2 real por falta de margen
    # futuro DENTRO del trozo (aunque si tenga margen de sobra en el
    # historico completo) y dar un patron_previo distinto del que ve
    # motor.calcular() -- se comprobo con datos reales y llegaba a
    # duplicar la probabilidad_total en algun candidato (0.48 vs 0.83).
    candidatos_todos = motor.detectar(df)
    patron_previo = any(
        c.idx_techo2 < limite_previos
        and abs((close[c.idx_techo1] + close[c.idx_techo2]) / 2 - nivel_actual) / nivel_actual * 100
        <= motor.TOLERANCIA_NIVEL_PATRON_PREVIO_PCT
        for c in candidatos_todos
    )

    dist_ath_pct = (ath_hasta[idx_maximo_aparente] - precio2) / ath_hasta[idx_maximo_aparente] * 100
    score_ath = motor._score_ath(dist_ath_pct)

    if tipo == TipoRegimen.BAJISTA:
        score_contexto = (score_regimen * score_ath) ** 0.5 if patron_previo else score_regimen
    elif tipo == TipoRegimen.ALCISTA:
        score_contexto = max((score_regimen * score_ath) ** 0.5 * motor.DESCUENTO_CONTEXTO_ALCISTA, 1e-3)
    else:
        score_contexto = 1e-3

    prob_forma_safe = max(probabilidad_forma, 1e-3)
    score_contexto_safe = max(score_contexto, 1e-3)
    probabilidad_total = prob_forma_safe ** peso_forma * score_contexto_safe ** peso_contexto

    curva = CURVA_SUPERVIVENCIA_TECHO[min(dia_transcurrido, 3)]
    return CandidatoEntradaTecho(
        idx_maximo_aparente=idx_maximo_aparente, dia_transcurrido=dia_transcurrido,
        probabilidad_total_si_confirma=round(probabilidad_total, 3),
        probabilidad_en_vivo=round(probabilidad_total * curva, 3),
    )


def candidatos_entrada(df: pd.DataFrame) -> list[CandidatoEntradaTecho]:
    """La regla de entrada en sí: un candidato por cada maximo aparente,
    evaluado el mismo dia en que aparece (dia 0) -- no se espera
    confirmacion, esa es la conclusion ya validada. Devuelve solo los
    candidatos del dia 0 (para inspeccionar la trayectoria completa de uno
    en concreto, usar `calcular_en_vivo` directamente con dia 1/2/3)."""
    close = df["close"].to_numpy()
    resultados = []
    for idx in maximos_aparentes(close):
        r = calcular_en_vivo(df, idx, dia_transcurrido=0)
        if r is not None:
            resultados.append(r)
    return resultados
