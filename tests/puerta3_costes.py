"""
Puerta 3 — Costes reales

La pregunta que responde esta puerta, en una frase:
"Si a cada operación le restamos el coste real de ejecutarla (no una
comisión, que en QuantFury es cero, sino el precio que de verdad se
consigue -spread- más el retraso de que un humano ejecute el aviso a
mano), ¿sigue quedando ventaja, o el coste se la come entera?"

Cómo se mide aquí (versión de cribado, no la confirmación final):
Como todavía no existe `salidas/` (reglas de cierre reales: stop,
objetivo, tiempo máximo), esta puerta usa por ahora un horizonte fijo
-Nº de velas tras la señal- como aproximación, igual que hizo el
cribado original en corvus3. ESTO ES UN PROXY, NO LA PRUEBA FINAL:
la Regla 10 de corvus3 (ver docs/catalogo_bot_viejo.md) es clara -- un
cribado de horizonte fijo sirve para DESCARTAR, nunca para CONFIRMAR,
porque la operación real sale antes por el stop o por una salida
dinámica. Aquí se usa solo para una primera criba barata: si ni
siquiera sobrevive a un coste bajo con horizonte fijo, no hace falta
construir `salidas/` de verdad para descartarlo. Si sobrevive, sigue
siendo "pendiente de confirmación real" hasta que exista `salidas/`.

Colapso por evento (Regla 7 heredada de corvus3): señales que se
disparan en velas seguidas o casi seguidas (p.ej. varias velas de
sobreventa durante la misma caída) no son N oportunidades independientes,
son la misma oportunidad contada N veces. Se agrupan en un solo "evento"
si no ha pasado un hueco mínimo desde la señal anterior.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def agrupar_en_eventos(senal: pd.Series, gap_min_velas: int) -> list[int]:
    """Devuelve los índices (posición entera) de la PRIMERA vela de cada
    evento -- señales que se repiten dentro de `gap_min_velas` desde el
    evento anterior se consideran la misma oportunidad y no cuentan de nuevo.
    """
    idx_true = np.flatnonzero(senal.to_numpy())
    if len(idx_true) == 0:
        return []
    eventos = [int(idx_true[0])]
    for i in idx_true[1:]:
        if i - eventos[-1] > gap_min_velas:
            eventos.append(int(i))
    return eventos


@dataclass
class ResultadoCostes:
    n_eventos: int
    horizonte_velas: int
    retorno_medio_bruto: float
    retorno_medio_baseline: float
    exceso_bruto: float
    coste_breakeven: float
    tabla_sensibilidad: pd.DataFrame

    def resumen(self) -> str:
        piezas = [
            f"{self.n_eventos} eventos, horizonte {self.horizonte_velas} velas.",
            f"Retorno medio por evento (bruto, sin coste): {self.retorno_medio_bruto:+.3f}%",
            f"Baseline (comprar en cualquier vela al azar, mismo horizonte): {self.retorno_medio_baseline:+.3f}%",
            f"Exceso sobre baseline (bruto): {self.exceso_bruto:+.3f}%",
        ]
        if np.isnan(self.coste_breakeven):
            piezas.append("El exceso bruto ya es <= 0: ningún coste hace falta para matarlo, muere solo.")
        else:
            piezas.append(
                f"Coste de ida y vuelta a partir del cual el exceso desaparece "
                f"(breakeven): ~{self.coste_breakeven:.3f}% por operación."
            )
        return "\n".join(piezas)


def evaluar_costes(
    df: pd.DataFrame,
    senal: pd.Series,
    horizonte_velas: int,
    gap_min_velas: int,
    costes_a_probar: list[float],
) -> ResultadoCostes:
    close = df["close"].to_numpy()
    n = len(close)

    eventos = agrupar_en_eventos(senal, gap_min_velas)
    eventos = [e for e in eventos if e + horizonte_velas < n]

    retornos_evento = np.array([
        (close[e + horizonte_velas] / close[e] - 1) * 100 for e in eventos
    ])

    entradas_todas = np.arange(0, n - horizonte_velas)
    retornos_baseline = (close[entradas_todas + horizonte_velas] / close[entradas_todas] - 1) * 100

    retorno_medio_bruto = float(np.mean(retornos_evento))
    retorno_medio_baseline = float(np.mean(retornos_baseline))
    exceso_bruto = retorno_medio_bruto - retorno_medio_baseline

    filas = []
    for coste in costes_a_probar:
        retorno_neto = retorno_medio_bruto - coste
        exceso_neto = retorno_neto - retorno_medio_baseline
        pct_eventos_positivos_netos = float(np.mean((retornos_evento - coste) > 0)) * 100
        filas.append({
            "coste_%_por_operacion": coste,
            "retorno_medio_neto_%": round(retorno_neto, 3),
            "exceso_sobre_baseline_neto_%": round(exceso_neto, 3),
            "%_eventos_positivos_tras_coste": round(pct_eventos_positivos_netos, 1),
        })
    tabla = pd.DataFrame(filas)

    coste_breakeven = float("nan")
    if exceso_bruto > 0:
        coste_breakeven = retorno_medio_bruto - retorno_medio_baseline

    return ResultadoCostes(
        n_eventos=len(eventos),
        horizonte_velas=horizonte_velas,
        retorno_medio_bruto=retorno_medio_bruto,
        retorno_medio_baseline=retorno_medio_baseline,
        exceso_bruto=exceso_bruto,
        coste_breakeven=coste_breakeven,
        tabla_sensibilidad=tabla,
    )
