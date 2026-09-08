"""
El árbitro — decide qué se toma cuando varios motores señalan a la vez.

Con solo 2 motores (Doble suelo, largo; Doble techo, corto) y un solape
medido de solo 2,7% de las señales (comprobado en BTC 2017-2024), el caso
de conflicto es raro. Pero cuando ocurre, las dos señales dicen cosas
CONTRADICTORIAS (una dice "sube", la otra "baja") sobre el mismo activo
-- no es un caso de "dos oportunidades, cuál priorizo", es un caso de
"el mercado está mandando señales confusas ahora mismo".

Regla (8-sept-2026): ante un conflicto directo (largo y corto a la vez
sobre el mismo activo), NO SE OPERA NINGUNA de las dos. La ambigüedad en
sí misma es información -- forzar una prioridad inventada sobre una
contradicción real sería peor que no hacer nada.

Esta regla se revisita cuando haya más de 2 motores y los conflictos sean
más frecuentes -- entonces sí hará falta una prioridad de verdad por
calidad demostrada (ver docs/00-PLAN-MAESTRO.md §6.1), no solo "saltarse
el conflicto".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SenalCandidata:
    motor: str
    direccion: str  # "largo" o "corto"
    pronostico: float  # fuerza escalada, para tamano/ -- no se usa aquí para elegir


def resolver(senales: list[SenalCandidata]) -> list[SenalCandidata]:
    """Dadas las señales activas en un mismo instante, devuelve las que se
    operan de verdad. Con la regla actual: si hay una de cada dirección a
    la vez, no se opera ninguna. Si son todas de la misma dirección
    (varios motores de acuerdo), se operan todas -- de momento no hay
    límite de posiciones simultáneas implementado aquí (eso es la otra
    mitad de cartera/, riesgo_global.py, y el límite operativo de 5
    posiciones del usuario, que se aplica en ejecucion/).
    """
    direcciones = {s.direccion for s in senales}
    if len(direcciones) > 1:
        return []
    return senales
