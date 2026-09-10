"""
Barrido combinado #3 -- consecuencia directa del #2: bloquear entradas
(filtro_bear, filtro M1) siempre empeoró el grid porque le quita
operaciones, que es justo lo que lo hace ganar. Aquí se prueba un
mecanismo distinto que no bloquea nada: REDUCIR el tamaño de la posición
en vez de impedirla, usando `multiplicador_por_volatilidad`
(cartera/riesgo_global.py) -- ya construido para la cartera global, nunca
aplicado dentro de un motor individual.

Mecánica: en vez de `stake = capital/n_niveles` fijo, cada trade pesa
`capital/n_niveles * multiplicador[idx_entrada]` -- en volatilidad normal
pesa igual que siempre, en volatilidad extrema (percentil alto) pesa
menos, pero la operación se sigue haciendo (no se pierde la oscilación).

Cruce real de condiciones:
  for percentil_corte en {0.80, 0.90, 0.95}       -- cuán pronto se empieza a recortar
    for multiplicador_minimo en {0.2, 0.4, 0.6}   -- cuánto se recorta como máximo
      for espaciado_dinamico en {False, True}
        se simula y se compara contra el baseline sin recorte de tamaño
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

import pandas as pd

from datos.cargar import cargar_ohlcv
from laboratorio import grid_adaptativo as g
from cartera.riesgo_global import multiplicador_por_volatilidad


def evaluar_capital_con_multiplicador(res, n_niveles, mult_vol, decreciente=True):
    if decreciente:
        brutos = [n_niveles - k for k in range(n_niveles)]
        suma = sum(brutos)
        pesos_nivel = {k: brutos[k] / suma for k in range(n_niveles)}
    else:
        pesos_nivel = {k: 1 / n_niveles for k in range(n_niveles)}

    trades_ordenados = sorted(res.trades, key=lambda t: t.idx_salida)
    capital, pico, caida_max = 100.0, 100.0, 0.0
    for t in trades_ordenados:
        peso_nivel = pesos_nivel.get(t.idx_nivel, 1 / n_niveles)
        m = mult_vol[t.idx_entrada] if not pd.isna(mult_vol[t.idx_entrada]) else 1.0
        capital += 100.0 * peso_nivel * m * (t.retorno_pct / 100)
        pico = max(pico, capital)
        caida_max = min(caida_max, (capital / pico - 1) * 100)
    return capital, caida_max


def main():
    df4h = cargar_ohlcv("BTCUSDT", "4h")
    n_niveles = 3
    base_kwargs = dict(n_niveles=n_niveles, k_atr_espaciado=0.5, velas_recentrado=180, stop_bajo_rejilla=2.0)

    filas = []
    for espaciado_dinamico in (False, True):
        kwargs = dict(base_kwargs)
        kwargs["espaciado_dinamico"] = espaciado_dinamico
        if espaciado_dinamico:
            kwargs["k_atr_espaciado_tendencia"] = 1.5
        res = g.simular(df4h, **kwargs)

        # baseline sin recorte de tamaño (multiplicador siempre 1.0)
        mult_neutro = pd.Series(1.0, index=df4h.index).to_numpy()
        capital_base, caida_base = evaluar_capital_con_multiplicador(res, n_niveles, mult_neutro)
        filas.append({
            "din": espaciado_dinamico, "percentil_corte": "-", "mult_min": "-",
            "capital_final": round(capital_base, 1), "caida_max_pct": round(caida_base, 1),
            "n_trades": len(res.trades),
        })

        for percentil_corte in (0.80, 0.90, 0.95):
            for multiplicador_minimo in (0.2, 0.4, 0.6):
                mult = multiplicador_por_volatilidad(
                    df4h, percentil_corte=percentil_corte, multiplicador_minimo=multiplicador_minimo
                ).to_numpy()
                capital, caida = evaluar_capital_con_multiplicador(res, n_niveles, mult)
                filas.append({
                    "din": espaciado_dinamico, "percentil_corte": percentil_corte, "mult_min": multiplicador_minimo,
                    "capital_final": round(capital, 1), "caida_max_pct": round(caida, 1),
                    "n_trades": len(res.trades),
                })

    tabla = pd.DataFrame(filas)
    tabla["calmar"] = tabla.apply(
        lambda r: (r.capital_final - 100) / abs(r.caida_max_pct) if r.caida_max_pct < 0 else float("inf"), axis=1
    ).round(2)
    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", 100)
    print(tabla.sort_values(["din", "capital_final"], ascending=[True, False]).to_string(index=False))
    tabla.to_csv("laboratorio/resultados_grid_combinaciones3.csv", index=False)


if __name__ == "__main__":
    main()
