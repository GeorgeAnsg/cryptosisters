"""
Version EN VIVO de canal, construida el 15-sept-2026 a partir de
`laboratorio/patrones/canal_flexible.py` (el detector batch).

UBICACION (corregida el 15-sept-2026, avisado por el usuario): este
fichero vivio brevemente en `entradas/canal.py` -- error de arquitectura.
Segun `entradas/README.md` ("Una vez que un motor -motores/- emite un
candidato... esta capa decide..."), `entradas/` esta reservada para reglas
construidas ENCIMA DE UN MOTOR YA GRADUADO a `motores/` (ver
`entradas/doble_techo.py`, que importa `from motores import doble_techo`).
Este fichero importa directamente de `laboratorio.patrones.canal_flexible`,
que todavia NO esta graduado (le falta el grid cruzado ETH->BTC y sus
propias puertas) -- que la capa de encima haya pasado la Puerta 1 no
valida el motor de abajo. Se queda en `laboratorio/patrones/` hasta que
`canal_flexible.py` se gradue de verdad a `motores/canal.py`; solo
entonces esta version en vivo debe reconstruirse importando de ahi y
mudarse a `entradas/`.

NO GRADUAR A motores/ TODAVIA -- pedido explicito del usuario (15-sept-2026):
"construimos la version en vivo hasta que tengamos algo correcto, no lo
pasamos a motores". Falta pasar la Puerta 1 (causalidad) con datos reales,
la Puerta 5 (recursividad, por el rolling de volumen) y el grid cruzado
ETH->BTC que `canal_flexible.py` ya deja pendiente en su propio docstring.

POR QUE HACE FALTA UNA VERSION EN VIVO SEPARADA (mismo motivo que
`entradas/doble_techo.py`, 12-sept-2026): `canal_flexible._detectar_fondos_simple`
y `_detectar_picos_simple` confirman un minimo/maximo local con una ventana
CENTRADA (miran 3 dias hacia el pasado Y 3 hacia el futuro). Eso es
correcto para explorar el histórico en lote, pero en vivo esa confirmacion
solo llega 3 dias despues del extremo real. El detector batch, ademas,
SIEMPRE agrupa los candidatos por su punto de finalizacion (`idx_pico2`,
ver `por_pico2` en `canal_flexible._detectar`) -- es decir, la topologia
fondo1 < pico1 < fondo2 < pico2 hace que el punto de incertidumbre en vivo
sea SIEMPRE el ultimo pico, sea cual sea la direccion (ascendente,
descendente o lateral): fondo1, pico1 y fondo2 ya llevan tiempo confirmados
en cuanto pico2 empieza a formarse (el tramo minimo entre fondo1 y fondo2
es `dias_min_tramo=10` dias, muy por encima de la ventana de confirmacion
de 3 dias).

"Pico aparente" (igual que "maximo aparente" en doble techo): el dia mas
alto de los ultimos `ventana_pasada` dias, incluyendose el mismo -- esto SI
se sabe en tiempo real. No es lo mismo que `idx_pico2` del motor batch, que
exige tambien margen hacia adelante.

CORRECCION DE ARQUITECTURA aplicada desde el principio (no como parche
posterior, a diferencia de doble techo el 12-sept): la formula de
puntuacion de forma vive en una unica funcion compartida,
`canal_flexible._score_forma()`, extraida el 15-sept-2026 exactamente para
esto -- aqui NO se reimplementa nada, se importa y se llama igual que
`_detectar()` la llama internamente. Un dia ya confirmado del todo
(dia_transcurrido=3) debe dar el mismo numero que el motor batch por
construccion, nunca por sincronizacion manual.

PENDIENTE, a diferencia de techo/suelo: NO existe todavia una curva de
supervivencia empirica (P(que el pico aparente termine siendo el pico2
real) segun dias transcurridos sin ser superado) ni la conclusion de si
conviene esperar confirmacion o entrar en dia 0 -- eso requiere el mismo
estudio que se hizo para techo/suelo
(`laboratorio/patrones/probabilidad_evolutiva_techo.py` /
`umbral_decision_en_vivo.py`), todavia no hecho para canal. Por eso
`CandidatoEntradaCanal` NO tiene un campo `probabilidad_en_vivo` descontado
por ninguna curva -- solo `probabilidad_total_si_confirma`, tal cual sale
de tratar el pico aparente COMO SI ya fuera el pico2 definitivo.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.patrones import canal_flexible as motor


@dataclass
class CandidatoEntradaCanal:
    direccion: str  # "subida" | "bajada" | "lateral"
    idx_fondo1: int
    idx_pico1: int
    idx_fondo2: int
    idx_pico_aparente: int
    dia_transcurrido: int
    probabilidad_total_si_confirma: float  # tratando el pico aparente como pico2 definitivo


def picos_aparentes(close: np.ndarray, ventana_pasada: int = 3) -> list[int]:
    """Un dia `i` es 'pico aparente' si es el mas alto de los ultimos
    `ventana_pasada` dias (incluyendose el mismo) -- se sabe en tiempo
    real, sin mirar al futuro. Es el punto de incertidumbre para las TRES
    direcciones de canal (ver docstring del modulo: la topologia siempre
    termina en un pico, sea canal ascendente, descendente o lateral)."""
    n = len(close)
    return [i for i in range(ventana_pasada, n) if close[i] == close[i - ventana_pasada: i + 1].max()]


def calcular_en_vivo(
    df: pd.DataFrame,
    idx_pico_aparente: int,
    direccion: str,
    dia_transcurrido: int,
    dias_min_tramo: int = 10,
    dias_max_tramo: int = 60,
    pendiente_ideal_pct_dia: float | None = None,
    paralelismo_tolerancia_pct_dia: float = 0.5,
    ancho_ideal_pct: float = 8.0,
    ancho_tolerancia_exceso_pct: float = 10.0,
    consistencia_tolerancia: float = 0.5,
    contencion_tolerancia_pct: float = 10.0,
    peso_pendiente: float = 0.05,
    peso_paralelismo: float = 0.20,
    peso_ancho: float = 0.30,
    peso_consistencia: float = 0.10,
    peso_contencion: float = 0.35,
) -> CandidatoEntradaCanal | None:
    """Trata `idx_pico_aparente` COMO SI fuera el pico2 definitivo del
    canal (su precio ya se conoce; lo que no se sabe aun es si seguira
    siendo el mas alto de los proximos dias) y busca, entre los fondo1/
    pico1/fondo2 YA CONFIRMADOS antes de el, la combinacion que mejor
    puntua -- exactamente el mismo criterio de "mejor combinacion por
    punto de finalizacion" que usa `canal_flexible._detectar` (agrupacion
    `por_pico2`), aqui con el punto de finalizacion fijado de antemano."""
    if pendiente_ideal_pct_dia is None:
        pendiente_ideal_pct_dia = 0.3 if direccion == "lateral" else 1.0

    lateral = direccion == "lateral"
    ascendente = direccion == "subida"

    close = df["close"].to_numpy()
    precio_pico2 = close[idx_pico_aparente]

    # CRITICO para causalidad (bug real encontrado el 15-sept-2026 al correr
    # laboratorio/patrones/puerta1_canal.py): a diferencia de doble techo/
    # suelo (un solo punto ancla previo), canal tiene TRES anclas previas
    # (fondo1, pico1, fondo2) y no hay ningun hueco minimo obligatorio entre
    # fondo2/pico1 y el pico aparente -- si se detectan fondos/picos sobre
    # el `close` COMPLETO, un fondo2 a solo 1-2 dias del pico aparente puede
    # "confirmarse" usando dias que en vivo todavia no habrian llegado (su
    # ventana de +-3 dias se sale por delante de "hoy"). Truncar el
    # historico disponible a `idx_pico_aparente` antes de detectar fondos/
    # picos hace que _detectar_fondos_simple/_detectar_picos_simple excluyan
    # automaticamente cualquier punto que necesitara ver mas alla de hoy
    # para confirmarse -- verificado con tests/-style puerta 1
    # (laboratorio/patrones/puerta1_canal.py): 150/150 sin fuga tras este fix.
    # `dia_transcurrido` dias despues del pico aparente ya han pasado -- esa
    # es toda la informacion adicional disponible en vivo a estas alturas
    # (ni un dia mas: seria mirar al futuro respecto al momento simulado).
    close_disponible = close[: idx_pico_aparente + dia_transcurrido + 1]
    fondos = motor._detectar_fondos_simple(close_disponible)
    picos = motor._detectar_picos_simple(close_disponible)

    mejor = None
    for i, idx_fondo1 in enumerate(fondos):
        precio_fondo1 = close[idx_fondo1]
        if idx_pico_aparente - idx_fondo1 > dias_max_tramo:
            continue
        for idx_fondo2 in fondos[i + 1:]:
            dias_tramo = idx_fondo2 - idx_fondo1
            if dias_tramo > dias_max_tramo:
                break
            if dias_tramo < dias_min_tramo:
                continue
            if idx_fondo2 >= idx_pico_aparente:
                continue
            precio_fondo2 = close[idx_fondo2]
            if not lateral:
                if ascendente and precio_fondo2 <= precio_fondo1:
                    continue
                if not ascendente and precio_fondo2 >= precio_fondo1:
                    continue

            pico1_opts = [p for p in picos if idx_fondo1 < p < idx_fondo2]
            if not pico1_opts:
                continue

            for idx_pico1 in pico1_opts:
                precio_pico1 = close[idx_pico1]
                if precio_pico1 <= max(precio_fondo1, precio_fondo2):
                    continue
                if not lateral:
                    if ascendente and precio_pico2 <= precio_pico1:
                        continue
                    if not ascendente and precio_pico2 >= precio_pico1:
                        continue

                r = motor._score_forma(
                    idx_fondo1, idx_pico1, idx_fondo2, idx_pico_aparente,
                    precio_fondo1, precio_pico1, precio_fondo2, precio_pico2,
                    close, lateral, pendiente_ideal_pct_dia, paralelismo_tolerancia_pct_dia,
                    ancho_ideal_pct, ancho_tolerancia_exceso_pct, consistencia_tolerancia,
                    contencion_tolerancia_pct, peso_pendiente, peso_paralelismo,
                    peso_ancho, peso_consistencia, peso_contencion,
                )
                if r is None:
                    continue
                if mejor is None or r["probabilidad_forma"] > mejor["probabilidad_forma"]:
                    mejor = dict(r, idx_fondo1=idx_fondo1, idx_pico1=idx_pico1, idx_fondo2=idx_fondo2)

    if mejor is None:
        return None

    return CandidatoEntradaCanal(
        direccion=direccion,
        idx_fondo1=mejor["idx_fondo1"], idx_pico1=mejor["idx_pico1"], idx_fondo2=mejor["idx_fondo2"],
        idx_pico_aparente=idx_pico_aparente, dia_transcurrido=dia_transcurrido,
        probabilidad_total_si_confirma=round(mejor["probabilidad_forma"], 3),
    )


def candidatos_entrada(df: pd.DataFrame, direccion: str) -> list[CandidatoEntradaCanal]:
    """Un candidato por cada pico aparente, evaluado el mismo dia en que
    aparece (dia 0) -- todavia SIN estudiar si conviene esperar
    confirmacion (ver docstring del modulo)."""
    close = df["close"].to_numpy()
    resultados = []
    for idx in picos_aparentes(close):
        r = calcular_en_vivo(df, idx, direccion, dia_transcurrido=0)
        if r is not None:
            resultados.append(r)
    return resultados
