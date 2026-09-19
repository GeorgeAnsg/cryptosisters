"""
tamano/ -- el CUANTO. Ver README.md para el porque de la formula.

Disciplina de capas: esta funcion NO sabe nada de ATR, de patrones ni de
niveles de stop/objetivo -- recibe `riesgo_por_unidad` (la distancia en
precio hasta el stop de la operacion concreta, ya calculada por
`salidas/stop_objetivo.py`) como un simple float, igual que recibe
`probabilidad` como un simple float. Quien orquesta (backtest o bot en
vivo) es quien conecta ambas capas; ninguna importa la otra.

T1 (vol-targeting, ⚙️ ya "construido" segun docs/00-PLAN-MAESTRO.md §7.4):
arriesgar un dinero fijo por operacion y convertirlo en unidades dividiendo
por la distancia al stop -- una vela mas volatil (stop mas lejos en precio)
compra automaticamente MENOS unidades para el mismo riesgo en dinero. Esto
ya pasaba de forma provisional en `laboratorio/patrones/prueba_cuenta_1000e.py`
(RIESGO_PCT fijo); graduado aqui como la pieza real de `tamano/`.

T2 (pronostico escalado y con tope, la solucion al problema del arbitro,
plan maestro §6.1): la probabilidad de la señal NO decide si se opera (ya
comprobado con datos: fuerza no predice acierto, dia 0 sin absolutos) pero
SI escala un poco el tamaño, dentro de un rango acotado
[multiplicador_min, multiplicador_max] -- para que una señal extrema
(probablemente rara o un error) no se coma la cartera.

T3 (Kelly fraccional) queda aparcado (14-sept-2026): requiere una
estimacion fiable de la ventaja/tasa de acierto, y la sesion de `salidas/`
de esta misma fecha confirmo que el exceso real sobre comprar-y-aguantar es
minusculo y no se confirma entre monedas -- meter Kelly sobre una ventaja
tan inestable es mas riesgo que beneficio. T4 (correlacion) y T5 (banda
muerta) se mueven conceptualmente a `cartera/`, que es quien ve el conjunto
de posiciones abiertas -- `tamano/` calcula el tamaño AISLADO de una sola
operacion, sin saber de las demas (ver README.md, "Que NO hace").

PENDIENTE explicito: multiplicador_min/multiplicador_max son un rango
razonable elegido a mano, no barrido todavia -- antes de usar esto con
dinero real hay que barrerlos igual que se hizo con R/k_atr_stop en
`salidas/` (ver `skill:deteccion-flexible-patrones`, "no absolutos").
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TamanoPosicion:
    unidades: float
    riesgo_dinero: float
    multiplicador_probabilidad: float


def escalar_probabilidad(probabilidad: float, multiplicador_min: float, multiplicador_max: float) -> float:
    """Lineal y con tope por construccion: probabilidad ya viene acotada
    0-1 desde el motor, así que el resultado nunca sale de
    [multiplicador_min, multiplicador_max] -- ese es el "tapado" de T2."""
    probabilidad = max(0.0, min(1.0, probabilidad))
    return multiplicador_min + (multiplicador_max - multiplicador_min) * probabilidad


def calcular_tamano(
    capital: float,
    riesgo_por_unidad: float,
    probabilidad: float,
    riesgo_base_pct: float,
    multiplicador_min: float,
    multiplicador_max: float,
) -> TamanoPosicion:
    if riesgo_por_unidad <= 0:
        raise ValueError("riesgo_por_unidad debe ser positivo (distancia al stop en precio)")
    multiplicador = escalar_probabilidad(probabilidad, multiplicador_min, multiplicador_max)
    riesgo_dinero = capital * riesgo_base_pct * multiplicador
    unidades = riesgo_dinero / riesgo_por_unidad
    return TamanoPosicion(unidades=unidades, riesgo_dinero=riesgo_dinero, multiplicador_probabilidad=multiplicador)
