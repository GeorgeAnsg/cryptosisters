"""
Puerta 4 — Presupuesto de intentos (Deflated Sharpe Ratio, Bailey & López
de Prado)

La pregunta que responde, en una frase:
"Si hubiéramos probado N estrategias sin ninguna ventaja real, solo por
azar, ¿qué tan bueno habría parecido el MEJOR resultado de las N? Y el
resultado que tenemos delante, ¿es mejor que eso, o es justo lo que cabía
esperar de la suerte pura dado cuántas veces hemos probado?"

Por qué hace falta esto además de un p-valor normal: un p-valor de 0,02
suena convincente visto solo, pero si se ha probado 70 veces, encontrar
UN resultado con p=0,02 por pura casualidad no es raro -- es casi
esperable. Esta puerta ajusta el listón según cuántos intentos van ya.

Fórmula (Bailey & López de Prado, 2014, "The Deflated Sharpe Ratio"):
el "Sharpe esperado por azar" al probar N configuraciones (cada una
evaluada con su propio t-stat, que bajo la hipótesis de "no hay ventaja"
se comporta como una normal estándar) es aproximadamente el máximo
esperado de N variables normales estándar:

    E[max de N normales estándar] ≈ (1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e))

donde γ es la constante de Euler-Mascheroni (≈0,5772) y Φ⁻¹ es la inversa
de la normal estándar acumulada.

El "t-stat" de una estrategia con T operaciones, retorno medio r̄ y
desviación s, es aproximadamente r̄/s · √T (el Sharpe de esas operaciones,
escalado por la raíz del número de operaciones -- así es comparable
directamente al benchmark de arriba, que está en las mismas unidades).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


def sharpe_esperado_por_azar(n_intentos: int) -> float:
    """E[max de N normales estándar] -- el listón que hay que superar."""
    if n_intentos < 2:
        return 0.0
    gamma = 0.5772156649  # constante de Euler-Mascheroni
    return (
        (1 - gamma) * stats.norm.ppf(1 - 1 / n_intentos)
        + gamma * stats.norm.ppf(1 - 1 / (n_intentos * np.e))
    )


@dataclass
class ResultadoDSR:
    n_intentos: int
    n_operaciones: int
    sharpe_muestral: float
    t_stat: float
    listón_azar: float

    @property
    def pasa(self) -> bool:
        return self.t_stat > self.listón_azar

    def resumen(self, nombre: str = "") -> str:
        veredicto = "PASA" if self.pasa else "NO PASA"
        return (
            f"{nombre + ': ' if nombre else ''}{veredicto} — "
            f"t-stat observado = {self.t_stat:.2f}, listón por azar (N={self.n_intentos}) = "
            f"{self.listón_azar:.2f}. "
            f"({self.n_operaciones} operaciones, Sharpe muestral = {self.sharpe_muestral:.3f})"
        )


def evaluar(retornos_pct: np.ndarray, n_intentos_totales: int) -> ResultadoDSR:
    """retornos_pct: array de retornos por operación, en %. n_intentos_totales:
    cuántas configuraciones distintas se han probado en total en el proyecto
    (el presupuesto acumulado, ver registro/intentos.jsonl)."""
    n = len(retornos_pct)
    sharpe_muestral = retornos_pct.mean() / retornos_pct.std(ddof=1)
    t_stat = sharpe_muestral * np.sqrt(n)
    listón = sharpe_esperado_por_azar(n_intentos_totales)
    return ResultadoDSR(
        n_intentos=n_intentos_totales, n_operaciones=n,
        sharpe_muestral=sharpe_muestral, t_stat=t_stat, listón_azar=listón,
    )
