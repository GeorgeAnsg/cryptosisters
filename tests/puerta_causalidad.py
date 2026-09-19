"""
Puerta 1 -- Causalidad (lookahead). Ver tests/README.md.

Metodo: cortar el historico en varios puntos y re-ejecutar el mismo
pipeline sobre cada corte. Los resultados en puntos suficientemente
alejados del final de cada corte (mas alla de `margen_seguridad`) deben
ser IDENTICOS a los que salen con el historico completo. Si no lo son, el
pipeline esta mirando datos que en vivo todavia no existirian.

Generico a proposito: `fn_mapa` es cualquier funcion df -> dict[int, valor
comparable] indexado por posicion de vela. Sirve tanto para detectores que
devuelven una lista de candidatos (fn_mapa = lambda df: {c.idx: c.prob for
c in detectar(df)}) como para detectores que devuelven columnas de señal
sobre el propio df (fn_mapa = lambda df: dict(enumerate(calcular_senales(df)["entra_largo"]))).
"""
from __future__ import annotations

from typing import Callable

import pandas as pd


def verificar_causalidad(
    fn_mapa: Callable[[pd.DataFrame], dict],
    df: pd.DataFrame,
    cortes: list[int] | None = None,
    margen_seguridad: int = 15,
) -> dict:
    n = len(df)
    if cortes is None:
        cortes = sorted({int(n * f) for f in (0.5, 0.65, 0.8, 0.9) if int(n * f) > margen_seguridad})

    mapa_completo = fn_mapa(df)

    resultados = []
    ok_total = True
    for corte in cortes:
        mapa_truncado = fn_mapa(df.iloc[:corte].reset_index(drop=True))
        limite = corte - margen_seguridad
        claves = [k for k in mapa_completo if k < limite]

        diffs, faltantes = [], []
        for k in claves:
            if k not in mapa_truncado:
                faltantes.append(k)
                continue
            v_completo, v_truncado = mapa_completo[k], mapa_truncado[k]
            if isinstance(v_completo, float) and isinstance(v_truncado, float):
                if abs(v_completo - v_truncado) > 1e-9:
                    diffs.append({"idx": k, "completo": v_completo, "truncado": v_truncado})
            elif v_completo != v_truncado:
                diffs.append({"idx": k, "completo": v_completo, "truncado": v_truncado})

        ok = not diffs and not faltantes
        ok_total = ok_total and ok
        resultados.append({
            "corte": corte,
            "fecha_corte": str(df["open_time"].iloc[corte - 1]) if corte <= n else None,
            "n_comparados": len(claves),
            "n_diferencias": len(diffs),
            "n_faltantes_en_truncado": len(faltantes),
            "ok": ok,
            "ejemplos_diferencias": diffs[:5],
            "ejemplos_faltantes": faltantes[:5],
        })

    return {"ok": ok_total, "margen_seguridad": margen_seguridad, "detalle": resultados}
