"""
Puerta 5 — Recursividad / calentamiento

La pregunta que responde, en una frase:
"Si el bot en vivo solo tiene, pongamos, 1500 velas de histórico (lo que
el exchange le da), en vez de las 19.000 que tenemos en el backtest,
¿calcula la misma señal hoy que si tuviera todo el histórico?"

Por qué puede fallar esto y la Puerta 1 no lo detecta:
La Puerta 1 comprueba que nunca se mire al FUTURO. Esta puerta comprueba
algo distinto: cuánto PASADO hace falta. Un indicador como una media móvil
simple (rolling mean de ventana fija) solo depende de las últimas N velas
-- da igual si detrás hay 500 velas más o 50.000, el resultado es idéntico.
Pero un indicador RECURSIVO -EMA, RSI, ADX, cualquiera con "suavizado de
Wilder"- arrastra memoria desde la primera vela que se le dé: si el
backtest lo calienta con todo el histórico y el bot en vivo solo tiene
una ventana corta, los dos darán números ligeramente distintos para la
misma fecha, sin que sea culpa de ningún error de programación -- es una
propiedad matemática del propio indicador.

Cómo se comprueba: igual que la Puerta 1 pero al revés. En vez de cortar
el futuro, se corta el PASADO -- se simula que el bot en vivo solo tiene
`historia_disponible` velas antes de "ahora", y se compara la señal
resultante contra la del histórico completo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ResultadoRecursividad:
    n_puntos_probados: int
    historia_disponible: int
    columnas: list[str]
    filas_mismatch: list[dict] = field(default_factory=list)

    @property
    def pasa(self) -> bool:
        return len(self.filas_mismatch) == 0

    def resumen(self) -> str:
        if self.pasa:
            return (
                f"PASA — {self.n_puntos_probados} puntos probados con solo "
                f"{self.historia_disponible} velas de historial disponible, "
                f"0 diferencias en {len(self.columnas)} columnas. La señal no "
                "depende de cuánto pasado tenga el bot en vivo."
            )
        detalle = "\n".join(
            f"  - en {m['timestamp']}: columna '{m['columna']}' "
            f"con histórico completo = {m['valor_completo']!r}, "
            f"con solo {m.get('historia_disponible', '?')} velas = {m['valor_limitado']!r}"
            for m in self.filas_mismatch[:10]
        )
        extra = "" if len(self.filas_mismatch) <= 10 else f"\n  ... y {len(self.filas_mismatch) - 10} más"
        return (
            f"NO PASA — {len(self.filas_mismatch)} diferencias encontradas:\n{detalle}{extra}"
        )


def verificar_recursividad(
    df_ohlcv: pd.DataFrame,
    fn_indicadores,
    fn_senales,
    columnas_a_comparar: list[str],
    historia_disponible: int,
    n_puntos: int = 30,
    semilla: int = 42,
) -> ResultadoRecursividad:
    """
    - historia_disponible: cuántas velas se simula que tiene el bot en vivo
      antes de "ahora" (p.ej. lo que de verdad ofrece el exchange por API).
      Debe ser generosamente mayor que la ventana más larga del indicador,
      o esta prueba solo estaría confirmando que hace falta warmup -algo ya
      sabido- en vez de medir si hay memoria recursiva de verdad.
    """
    n = len(df_ohlcv)
    df_completo = fn_senales(fn_indicadores(df_ohlcv))

    minimo = historia_disponible + 10
    if n <= minimo:
        raise ValueError("histórico demasiado corto para esta prueba con esta historia_disponible")

    rng = np.random.default_rng(semilla)
    puntos = sorted(rng.choice(
        np.arange(historia_disponible, n), size=min(n_puntos, n - historia_disponible), replace=False,
    ))

    mismatches: list[dict] = []
    for p in puntos:
        ventana = df_ohlcv.iloc[p - historia_disponible: p + 1]
        ventana_calc = fn_senales(fn_indicadores(ventana))
        fila_limitada = ventana_calc.iloc[-1]
        fila_completa = df_completo.iloc[p]

        for col in columnas_a_comparar:
            v_completo = fila_completa[col]
            v_limitado = fila_limitada[col]
            iguales = (
                (pd.isna(v_completo) and pd.isna(v_limitado))
                or v_completo == v_limitado
                or (
                    isinstance(v_completo, (int, float, np.floating))
                    and isinstance(v_limitado, (int, float, np.floating))
                    and np.isclose(v_completo, v_limitado, equal_nan=True, atol=1e-9)
                )
            )
            if not iguales:
                ts = df_ohlcv.iloc[p].get("open_time", p)
                mismatches.append({
                    "timestamp": ts,
                    "columna": col,
                    "valor_completo": v_completo,
                    "valor_limitado": v_limitado,
                    "historia_disponible": historia_disponible,
                })

    return ResultadoRecursividad(
        n_puntos_probados=len(puntos),
        historia_disponible=historia_disponible,
        columnas=columnas_a_comparar,
        filas_mismatch=mismatches,
    )
