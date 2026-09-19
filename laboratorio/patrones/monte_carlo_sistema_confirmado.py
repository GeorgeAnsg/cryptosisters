"""
14-sept-2026: Monte Carlo de robustez sobre el sistema confirmado
(sistema_confirmado_switch_14sept2026.py). Para cada una de las 8
combinaciones (ETH/BTC x 2021-2024), se toma la secuencia real de
retornos multiplicativos por operacion (capital_despues/capital_antes) y
se REMUESTREA CON REEMPLAZO 5000 veces, manteniendo el mismo numero de
operaciones -- esto responde a "¿el resultado real depende del ORDEN
concreto en que llegaron las operaciones, o es robusto a mezclar el
mismo conjunto de resultados en otro orden/repeticion?". Reporta
percentil del resultado real dentro de la distribucion simulada, rango
5%-95%, y probabilidad de acabar en perdidas.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import json
import numpy as np

from laboratorio.patrones.sistema_confirmado_switch_14sept2026 import (
    cargar_datos, simular_cuenta, CAPITAL_INICIAL,
)
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año, AÑOS

N_SIMULACIONES = 5000
rng = np.random.default_rng(42)

resultados_montecarlo = {}

for moneda in ["ETHUSDT", "BTCUSDT"]:
    df, atr, rt, rs, pendiente = cargar_datos(moneda)
    for año in AÑOS:
        cand = candidatos_por_año(df, año)
        cap_real, trades, gan, dd_real = simular_cuenta(df, cand, atr, rt, rs, pendiente, df["open_time"])
        if len(trades) == 0:
            continue
        # retornos multiplicativos por operacion
        capitales = [CAPITAL_INICIAL] + [t["capital_tras"] for t in trades]
        retornos = [capitales[i + 1] / capitales[i] for i in range(len(capitales) - 1)]
        retornos = np.array(retornos)
        n_trades = len(retornos)

        finales = np.empty(N_SIMULACIONES)
        drawdowns = np.empty(N_SIMULACIONES)
        for s in range(N_SIMULACIONES):
            muestra = rng.choice(retornos, size=n_trades, replace=True)
            curva = CAPITAL_INICIAL * np.cumprod(muestra)
            finales[s] = curva[-1]
            pico = np.maximum.accumulate(np.concatenate([[CAPITAL_INICIAL], curva]))
            valores = np.concatenate([[CAPITAL_INICIAL], curva])
            drawdowns[s] = ((valores - pico) / pico).min() * 100

        percentil_real = float((finales < cap_real).mean() * 100)
        prob_perdida = float((finales < CAPITAL_INICIAL).mean() * 100)
        p5, p50, p95 = np.percentile(finales, [5, 50, 95])
        dd_p5 = np.percentile(drawdowns, 5)

        clave = f"{moneda}_{año}"
        resultados_montecarlo[clave] = {
            "moneda": moneda, "año": año, "n_trades": int(n_trades),
            "capital_real": round(float(cap_real), 2),
            "percentil_real": round(percentil_real, 1),
            "prob_perdida_pct": round(prob_perdida, 2),
            "p5": round(float(p5), 2), "p50": round(float(p50), 2), "p95": round(float(p95), 2),
            "drawdown_real": round(float(dd_real), 2),
            "drawdown_p5_montecarlo": round(float(dd_p5), 2),
        }
        print(f"{moneda} {año}: real={cap_real:.0f}€ (percentil {percentil_real:.0f} de la distribucion MC) -- "
              f"MC p5={p5:.0f}€ p50={p50:.0f}€ p95={p95:.0f}€ -- prob. de perdida={prob_perdida:.1f}% -- "
              f"dd real={dd_real:.1f}% vs dd p5 MC={dd_p5:.1f}%")

json.dump(resultados_montecarlo, open("/tmp/monte_carlo_resultados.json", "w"))
print("\nGuardado en /tmp/monte_carlo_resultados.json")
