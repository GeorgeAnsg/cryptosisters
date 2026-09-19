"""
Barrido cruzado de `IDEALES_ANCHO` (canal_flexible.py), 11-sept-2026.

Importante -- esto NO es una prueba de rentabilidad (estamos en fase de
DETECCION, ver correccion de fase en la memoria del proyecto). Canal no
tiene una version "estricta" previa en el proyecto, asi que tampoco hay
chequeo de cordura posible (a diferencia de doble_suelo/doble_techo). Sin
una etiqueta de "acierto" real, la validacion aqui es de OTRO tipo:
robustez y sensatez geometrica -- ¿el config produce canales realmente
CONTENIDOS (no la tendencia general disfrazada de canal, el bug que
encontro el usuario visualmente en BTC 2022) de forma consistente en ETH
Y en BTC, sin colapsar a "casi ningun candidato"?

Metrica por config: `pct_sano` = % de candidatos ganadores (tras elegir
el mejor por idx_pico2) cuyo ancho_medio_pct queda dentro de 2x el ancho
ideal de ese config -- un margen generoso, no un corte de calidad nuevo,
solo la vara de medir de esta comprobacion.

Metodologia de validacion cruzada del proyecto: ajustar SOLO en ETH
(2021-2023), congelar, confirmar SIN TOCAR NADA en ETH tiempo no visto
(2023-2025) y en BTC completo (moneda nunca usada para ajustar).
"""
from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones import canal_flexible as cf


def _pct_sano(cands, ancho_ideal_pct: float) -> float:
    if not cands:
        return float("nan")
    sanos = sum(1 for c in cands if c.ancho_medio_pct <= ancho_ideal_pct * 2)
    return sanos / len(cands) * 100


def _evaluar(df: pd.DataFrame, ancho_ideal: float, ancho_tol: float) -> dict:
    resultado = {}
    for direccion, fn in [("ascendente", cf.detectar_ascendente), ("descendente", cf.detectar_descendente)]:
        cands = fn(df, ancho_ideal_pct=ancho_ideal, ancho_tolerancia_exceso_pct=ancho_tol)
        anchos = sorted(c.ancho_medio_pct for c in cands)
        resultado[direccion] = {
            "n": len(cands),
            "pct_sano": round(_pct_sano(cands, ancho_ideal), 1),
            "ancho_mediana": round(anchos[len(anchos) // 2], 2) if anchos else None,
            "ancho_max": round(anchos[-1], 2) if anchos else None,
        }
    return resultado


def main() -> None:
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="busqueda_grid_canal_eth")
    df_eth["fecha"] = pd.to_datetime(df_eth["open_time"], unit="ms").dt.strftime("%Y-%m-%d")
    df_eth_ajuste = df_eth[df_eth["fecha"] < "2023-01-01"].reset_index(drop=True)
    df_eth_confirma = df_eth[df_eth["fecha"] >= "2023-01-01"].reset_index(drop=True)

    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="busqueda_grid_canal_btc")

    print(f"{'config':<20} {'dataset':<14} {'dir':<12} {'n':>5} {'pct_sano':>9} {'mediana%':>9} {'max%':>8}")
    for ancho_ideal, ancho_tol in cf.IDEALES_ANCHO:
        nombre_config = f"({ancho_ideal},{ancho_tol})"
        for nombre_ds, df_ds in [
            ("ETH ajuste", df_eth_ajuste),
            ("ETH confirma", df_eth_confirma),
            ("BTC completo", df_btc),
        ]:
            r = _evaluar(df_ds, ancho_ideal, ancho_tol)
            for direccion in ("ascendente", "descendente"):
                d = r[direccion]
                print(f"{nombre_config:<20} {nombre_ds:<14} {direccion:<12} {d['n']:>5} "
                      f"{d['pct_sano']:>8.1f}% {str(d['ancho_mediana']):>9} {str(d['ancho_max']):>8}")


if __name__ == "__main__":
    main()
