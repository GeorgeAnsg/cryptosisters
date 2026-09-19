"""
Capa 1 del bot (12-sept-2026) -- primera vez que se combinan dos motores
de patron en una sola salida. Con doble_techo_motor_v2 y
doble_suelo_motor_v2 cerrados y validados, y sin querer tocar canal
todavia (decision explicita del usuario: "por ahora no quiero probar el
del canal ni nada"), esto es deliberadamente pequeño: unir los dos
motores que ya existen, no construir el orquestador completo de Fase D.

Diseño: los DOS motores se ejecutan SIEMPRE sobre el mismo df -- no hay
un filtro previo tipo "si regimen bajista, no busques suelo". Cada motor
YA descuenta el contexto de forma continua segun el regimen (ver sus
docstrings): un candidato de techo en regimen alcista no se descarta,
sale con probabilidad baja/descontada; igual un suelo en bajista. Meter
aqui un corte binario de que motor lanzar violaria el mismo principio de
"no absolutos" que ya gobierna la puntuacion interna de cada motor -- esa
decision (que motores tiene sentido lanzar SEGUN el regimen, a nivel
global) es la pregunta de Fase D, explicitamente aplazada hasta que haya
mas motores maduros (ver hoja de ruta).

Salida: una lista plana de `SenalCapa1`, cada una con el tipo de patron,
el indice, la probabilidad total de su propio motor y el regimen que vio
ese motor -- pensada para que un futuro orquestador (o, por ahora, la
inspeccion visual/manual) pueda filtrar u ordenar sin perder informacion.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

from dataclasses import dataclass

import pandas as pd

from laboratorio.patrones import doble_suelo_motor_v2, doble_techo_motor_v2
from laboratorio.patrones.regimen_mercado import TipoRegimen


@dataclass
class SenalCapa1:
    tipo_patron: str  # "doble_techo" | "doble_suelo"
    idx: int  # idx_techo2 o idx_fondo2, segun tipo_patron
    probabilidad_total: float
    tipo_regimen: TipoRegimen
    score_regimen: float
    score_forma: float


def detectar(
    df: pd.DataFrame,
    kwargs_techo: dict | None = None,
    kwargs_suelo: dict | None = None,
) -> list[SenalCapa1]:
    kwargs_techo = kwargs_techo or {}
    kwargs_suelo = kwargs_suelo or {}

    resultados_techo = doble_techo_motor_v2.calcular(df, **kwargs_techo)
    resultados_suelo = doble_suelo_motor_v2.calcular(df, **kwargs_suelo)

    senales = [
        SenalCapa1(
            tipo_patron="doble_techo", idx=r.candidato.idx_techo2,
            probabilidad_total=r.probabilidad_total, tipo_regimen=r.tipo_regimen,
            score_regimen=r.score_regimen, score_forma=r.score_forma,
        )
        for r in resultados_techo
    ] + [
        SenalCapa1(
            tipo_patron="doble_suelo", idx=r.candidato.idx_fondo2,
            probabilidad_total=r.probabilidad_total, tipo_regimen=r.tipo_regimen,
            score_regimen=r.score_regimen, score_forma=r.score_forma,
        )
        for r in resultados_suelo
    ]
    return sorted(senales, key=lambda s: s.idx)
