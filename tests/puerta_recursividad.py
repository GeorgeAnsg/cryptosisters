"""
Puerta 5 -- Recursividad / calentamiento. Ver tests/README.md.

Indicadores CUMULATIVOS (EMA, RSI, ADX, ATR de Wilder...) dan un valor
distinto segun cuantas velas historicas tengan disponibles, porque
arrastran memoria de TODO el historial, no solo de una ventana fija. En
backtest hay todo el historico; en vivo, el exchange solo entrega una
ventana limitada. Si un motor usa un indicador cumulativo sin comprobar
esto, puede comportarse distinto en vivo sin que sea culpa de ningun otro
fallo.

Metodo: repetir el mismo calculo con (a) todo el historico y (b) solo una
ventana "realista de vivo" (las ultimas `ventana_viva` velas antes de cada
punto de prueba) y comprobar que el resultado, en los puntos ya alejados
del arranque de esa ventana recortada, es identico. Generico via fn_mapa,
igual que la puerta 1.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd


def verificar_recursividad(
    fn_mapa: Callable[[pd.DataFrame], dict],
    df: pd.DataFrame,
    ventana_viva: int,
    puntos_prueba: list[int] | None = None,
    margen_seguridad: int = 20,
) -> dict:
    n = len(df)
    if puntos_prueba is None:
        puntos_prueba = sorted({
            int(n * f) for f in (0.6, 0.75, 0.9, 0.98)
            if int(n * f) > ventana_viva + margen_seguridad
        })

    mapa_completo = fn_mapa(df)

    resultados = []
    ok_total = True
    for punto in puntos_prueba:
        inicio = max(0, punto - ventana_viva)
        df_recortado = df.iloc[inicio:punto].reset_index(drop=True)
        mapa_recortado = {k + inicio: v for k, v in fn_mapa(df_recortado).items()}

        limite_inf = inicio + margen_seguridad   # cerca del arranque de la ventana puede faltar calentamiento LEGITIMO (rolling(30), etc.)
        limite_sup = punto - margen_seguridad
        claves = [k for k in mapa_completo if limite_inf <= k < limite_sup]

        diffs, faltantes = [], []
        for k in claves:
            if k not in mapa_recortado:
                faltantes.append(k)
                continue
            v_completo, v_recortado = mapa_completo[k], mapa_recortado[k]
            if isinstance(v_completo, float) and isinstance(v_recortado, float):
                if abs(v_completo - v_recortado) > 1e-9:
                    diffs.append({"idx": k, "completo": v_completo, "recortado": v_recortado})
            elif v_completo != v_recortado:
                diffs.append({"idx": k, "completo": v_completo, "recortado": v_recortado})

        ok = not diffs and not faltantes
        ok_total = ok_total and ok
        resultados.append({
            "punto": punto,
            "ventana_viva": ventana_viva,
            "n_comparados": len(claves),
            "n_diferencias": len(diffs),
            "n_faltantes": len(faltantes),
            "ok": ok,
            "ejemplos_diferencias": diffs[:5],
            "ejemplos_faltantes": faltantes[:5],
        })

    return {"ok": ok_total, "ventana_viva": ventana_viva, "detalle": resultados}
