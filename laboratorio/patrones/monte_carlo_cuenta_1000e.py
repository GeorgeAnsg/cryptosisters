"""
Monte Carlo sobre la prueba de cuenta de `prueba_cuenta_1000e_v2.py` --
pedido explicitamente por el usuario tras ver el resultado de una unica
secuencia de 2024. Motivo (ligado a la observacion 0012 de task-observer,
del mismo dia): con el tamaño de posicion como fraccion fija del capital,
la cuenta es MULTIPLICATIVA y por tanto DEPENDE DEL ORDEN -- la misma
bolsa de operaciones, en otro orden (otra "suerte"), da un capital final
distinto. Una sola secuencia historica (los ~10-20 candidatos reales de
2024) no dice nada sobre cuanto de esa suerte era orden y cuanto era la
estrategia en si.

Metodo: se resuelve la MISMA bolsa de operaciones que ya se resuelve en
`barrido_tamano.py::_resolver_trades()` (poblacion completa de Desarrollo,
no solo 2024 -- para tener una distribucion de resultados por operacion
mas robusta que los ~10-20 casos de un solo año) con la config YA
aceptada de `salidas/` y `tamano/`. Cada operacion se convierte en un
factor multiplicativo de capital POR EURO arriesgado (independiente de la
escala de capital, ver `_factor_capital`). Se remuestrea ese conjunto de
factores CON REEMPLAZO (bootstrap), en secuencias del mismo tamaño que
las operaciones reales de un año (el n de la prueba de 2024), miles de
veces, y se reporta la distribucion de capital final y drawdown maximo --
no un unico numero.

Esto NO es un barrido de parametros (los de `salidas/`/`tamano/` ya estan
fijos y aceptados) -- es una prueba de robustez/incertidumbre sobre la
propia cuenta, con los parametros ya decididos.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_tamano import (
    UMBRAL_CONTRARIA,
    _candidatos,
    _prob_contraria,
    _resolver_trades,
)
from laboratorio.patrones.prueba_cuenta_1000e_v2 import (
    MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN,
    RIESGO_BASE_PCT,
    _candidatos_2024,
    _serie_señal_contraria,
    _simular_cuenta as _simular_cuenta_2024,
)
from motores.volatilidad import atr_absoluto
from tamano.tamano import escalar_probabilidad

CAPITAL_INICIAL = 1000.0
N_SIMULACIONES = 5000
SEMILLA = 14092026  # reproducible, no es un valor de ajuste


def _factor_capital(trade):
    """Cuanto multiplica el capital esta operacion, POR EURO arriesgado --
    independiente de la escala de capital, para poder remuestrear libremente
    sin tener que rehacer la simulacion completa de la cuenta."""
    multiplicador = escalar_probabilidad(trade["probabilidad"], MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
    riesgo_efectivo_pct = RIESGO_BASE_PCT * multiplicador
    r_realizado = trade["cambio_precio_por_unidad"] / trade["riesgo_por_unidad"]
    return 1 + riesgo_efectivo_pct * r_realizado


def _monte_carlo(factores: np.ndarray, n_por_simulacion: int, n_simulaciones: int, rng: np.random.Generator):
    finales = np.empty(n_simulaciones)
    drawdowns = np.empty(n_simulaciones)
    for i in range(n_simulaciones):
        muestra = rng.choice(factores, size=n_por_simulacion, replace=True)
        curva = CAPITAL_INICIAL * np.cumprod(muestra)
        curva = np.concatenate(([CAPITAL_INICIAL], curva))
        pico = np.maximum.accumulate(curva)
        drawdowns[i] = float(((curva - pico) / pico).min()) * 100
        finales[i] = curva[-1]
    return finales, drawdowns


def _resumen_percentiles(valores, etiqueta, unidad=""):
    p = np.percentile(valores, [5, 25, 50, 75, 95])
    print(f"  {etiqueta}: p5={p[0]:.1f}{unidad}  p25={p[1]:.1f}{unidad}  "
          f"mediana={p[2]:.1f}{unidad}  p75={p[3]:.1f}{unidad}  p95={p[4]:.1f}{unidad}")


def main():
    rng = np.random.default_rng(SEMILLA)
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="monte_carlo_cuenta_1000e")
        atr = atr_absoluto(df)

        cand_completo = _candidatos(df)
        prob_corto, prob_largo = _prob_contraria(df)
        senal_corto = prob_corto >= UMBRAL_CONTRARIA
        senal_largo = prob_largo >= UMBRAL_CONTRARIA
        trades_completo = _resolver_trades(df, cand_completo, atr, senal_corto, senal_largo)
        factores = np.array([_factor_capital(t) for t in trades_completo])

        # numero de operaciones REALMENTE EJECUTADAS en 2024 (no candidatos -- muchos
        # candidatos no llegan a abrirse por la restriccion de no solapamiento, igual que en
        # la cuenta real de `prueba_cuenta_1000e_v2.py`)
        cand_2024 = _candidatos_2024(df)
        contraria_corto, contraria_largo = _serie_señal_contraria(df)
        _capital_real, trades_2024, _dd_real, _motivos_real = _simular_cuenta_2024(
            df, cand_2024, atr, contraria_corto, contraria_largo)
        n_2024 = len(trades_2024)

        print(f"\n=== {moneda} -- bolsa historica: {len(trades_completo)} operaciones resueltas "
              f"(toda Desarrollo) -- simulando años de {n_2024} operaciones "
              f"(las realmente ejecutadas en 2024, no candidatos) ===")
        print(f"  factor medio por operación: {factores.mean():.4f} "
              f"(ganancia media {((factores.mean() - 1) * 100):+.2f}% del capital por operación)")

        finales, drawdowns = _monte_carlo(factores, n_2024, N_SIMULACIONES, rng)
        prob_perdida = float((finales < CAPITAL_INICIAL).mean()) * 100
        prob_ruina_50 = float((finales < CAPITAL_INICIAL * 0.5).mean()) * 100

        _resumen_percentiles(finales, "Capital final (eur)")
        _resumen_percentiles(drawdowns, "Drawdown máximo dentro del año", unidad="%")
        print(f"  P(terminar el año con pérdidas) = {prob_perdida:.1f}%")
        print(f"  P(perder más de la mitad del capital en el año) = {prob_ruina_50:.1f}%")


if __name__ == "__main__":
    main()
