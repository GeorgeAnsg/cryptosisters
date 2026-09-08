"""
Puerta 1 — Causalidad (lookahead)

La pregunta que responde esta puerta, en una frase:
"Si el bot solo hubiera visto las velas hasta este momento -ni una más-,
¿habría calculado exactamente la misma señal que ve hoy, con todo el
histórico por delante?"

Cómo se comprueba (idea, sin jerga):
Se elige un puñado de momentos del pasado al azar. Para cada uno:
  1. Se corta el histórico justo ahí -- se borra todo lo que viene después,
     como si esa vela fuera "ahora mismo" en vivo.
  2. Se recalculan los indicadores y la señal SOLO con ese trozo cortado.
  3. Se compara la señal de la última vela del trozo cortado con la señal
     que esa misma vela tiene cuando se calcula con el histórico completo.

Si coinciden siempre, el indicador es causal: nunca se ha estado
"asomando" al futuro. Si alguna vez no coinciden, hay una fuga de
información desde el futuro hacia el pasado -- el resultado del cribado
original quedaría invalidado, porque el bot en vivo jamás podría haber
visto lo que el backtest sí vio.

Esto NO comprueba si el histórico disponible es más corto o más largo
(eso es la Puerta 5, recursividad/calentamiento) -- aquí SIEMPRE se
recalcula desde el principio del dataframe hasta el corte, cambiando solo
lo que hay DESPUÉS del corte.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ResultadoCausalidad:
    n_cortes_probados: int
    columnas: list[str]
    filas_mismatch: list[dict] = field(default_factory=list)

    @property
    def pasa(self) -> bool:
        return len(self.filas_mismatch) == 0

    def resumen(self) -> str:
        if self.pasa:
            return (
                f"PASA — {self.n_cortes_probados} cortes probados, "
                f"0 diferencias en {len(self.columnas)} columnas de señal. "
                "El indicador nunca vio el futuro."
            )
        detalle = "\n".join(
            f"  - corte en {m['timestamp']}: columna '{m['columna']}' "
            f"con histórico completo = {m['valor_completo']!r}, "
            f"con histórico cortado = {m['valor_cortado']!r}"
            for m in self.filas_mismatch[:10]
        )
        extra = "" if len(self.filas_mismatch) <= 10 else f"\n  ... y {len(self.filas_mismatch) - 10} más"
        return (
            f"NO PASA — {len(self.filas_mismatch)} diferencias encontradas "
            f"sobre {self.n_cortes_probados} cortes probados:\n{detalle}{extra}"
        )


def verificar_causalidad(
    df_ohlcv: pd.DataFrame,
    fn_indicadores,
    fn_senales,
    columnas_a_comparar: list[str],
    n_cortes: int = 30,
    warmup_minimo: int = 200,
    semilla: int = 42,
) -> ResultadoCausalidad:
    """Ejecuta la Puerta 1 sobre una función de indicadores + señales.

    - df_ohlcv: histórico completo, ordenado ascendente por tiempo, con una
      columna de tiempo llamada 'open_time' (o el índice ya siendo tiempo).
    - fn_indicadores: función df -> df que añade las columnas de indicador.
    - fn_senales: función df -> df que añade las columnas de señal a
      partir de los indicadores.
    - columnas_a_comparar: qué columnas de señal/indicador se comparan.
    - n_cortes: cuántos momentos del pasado se prueban.
    - warmup_minimo: no se prueban cortes antes de esta vela, porque los
      indicadores necesitan un mínimo de historia para tener sentido (con
      menos de esto, comparar sería comparar ruido de calentamiento, que es
      cosa de la Puerta 5, no de esta).
    """
    n = len(df_ohlcv)
    if n <= warmup_minimo + 10:
        raise ValueError("histórico demasiado corto para probar causalidad con este warmup")

    df_completo = fn_senales(fn_indicadores(df_ohlcv))

    rng = np.random.default_rng(semilla)
    cortes = sorted(rng.choice(
        np.arange(warmup_minimo, n - 1), size=min(n_cortes, n - warmup_minimo - 1), replace=False,
    ))

    mismatches: list[dict] = []
    for corte in cortes:
        trozo = df_ohlcv.iloc[: corte + 1]
        trozo_calc = fn_senales(fn_indicadores(trozo))
        fila_cortada = trozo_calc.iloc[-1]
        fila_completa = df_completo.iloc[corte]

        for col in columnas_a_comparar:
            v_completo = fila_completa[col]
            v_cortado = fila_cortada[col]
            iguales = (
                (pd.isna(v_completo) and pd.isna(v_cortado))
                or v_completo == v_cortado
                or (
                    isinstance(v_completo, (int, float, np.floating))
                    and isinstance(v_cortado, (int, float, np.floating))
                    and np.isclose(v_completo, v_cortado, equal_nan=True, atol=1e-9)
                )
            )
            if not iguales:
                ts = df_ohlcv.iloc[corte].get("open_time", corte)
                mismatches.append({
                    "timestamp": ts,
                    "columna": col,
                    "valor_completo": v_completo,
                    "valor_cortado": v_cortado,
                })

    return ResultadoCausalidad(
        n_cortes_probados=len(cortes),
        columnas=columnas_a_comparar,
        filas_mismatch=mismatches,
    )
