"""
Version "confianza creciente" del canal (idea del usuario): en vez de medir
el canal en una ventana fija de velas, se sigue la secuencia real de suelos
(fondos) que va marcando el precio -- fondo1, rebote, fondo2 (mas alto que
fondo1, formando una linea ascendente), rebote, fondo3... -- y en cada
fondo nuevo se ajusta una recta a TODOS los fondos anteriores de esa
racha. La pregunta que hace el usuario, literal: si ya llevas 2 fondos
confirmando la linea, ?predices peor el SIGUIENTE fondo que si ya llevas
4 fondos confirmando la misma linea? Es decir, ?la confianza (numero de
toques limpios) se traduce en mejor precision real?

Deteccion de fondos: causal, con `confirmacion` dias de rebote tras el
minimo para confirmarlo (igual que motor_rebote_minimo.py) -- no mira al
futuro mas alla de ese margen pequeño y necesario.

Racha ascendente: mientras cada fondo nuevo quede POR ENCIMA de la
proyeccion de la recta ajustada a los fondos anteriores (con una
tolerancia), se anade a la misma racha. Si cae claramente por debajo,
se rompe la racha y empieza una nueva.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def detectar_fondos(close: np.ndarray, ventana_min: int = 5, confirmacion: int = 2) -> list[int]:
    """Fondos locales causales: minimo de los ultimos `ventana_min` dias,
    confirmado por `confirmacion` dias seguidos subiendo despues."""
    n = len(close)
    fondos = []
    i = ventana_min + confirmacion
    while i < n:
        idx_candidato = i - confirmacion
        es_minimo = close[idx_candidato] == close[idx_candidato - ventana_min + 1: idx_candidato + 1].min()
        subiendo = all(close[idx_candidato + k] > close[idx_candidato + k - 1] for k in range(1, confirmacion + 1))
        if es_minimo and subiendo:
            fondos.append(idx_candidato)
            i = idx_candidato + confirmacion + 1
        else:
            i += 1
    return fondos


def analizar_rachas(close: np.ndarray, fondos: list[int], tolerancia_pct: float = 3.0):
    """Recorre los fondos en orden y agrupa en rachas ascendentes (canal).
    Para cada fondo nuevo con >=2 fondos previos en la racha, calcula el
    error de prediccion: ajusta recta a los fondos previos de la racha,
    predice donde deberia estar el fondo actual, compara con donde
    realmente esta. Devuelve lista de (n_toques_previos, error_pct)."""
    resultados = []
    racha = []  # lista de (idx, precio)

    for idx in fondos:
        precio = close[idx]
        if len(racha) >= 2:
            xs = np.array([p[0] for p in racha])
            ys = np.array([p[1] for p in racha])
            b, a = np.polyfit(xs, ys, 1)
            prediccion = a + b * idx
            error_pct = (precio - prediccion) / prediccion * 100
            resultados.append((len(racha), error_pct))
            dentro_tolerancia = abs(error_pct) <= tolerancia_pct or precio > prediccion
        else:
            dentro_tolerancia = True

        if len(racha) == 0:
            racha = [(idx, precio)]
        elif dentro_tolerancia:
            racha.append((idx, precio))
        else:
            racha = [(idx, precio)]  # rompe la racha, empieza otra

    return resultados


def main():
    import sys
    sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
    from datos.cargar import cargar_ohlcv

    for par in ["BTCUSDT", "ETHUSDT"]:
        df = cargar_ohlcv(par, "1d")
        close = df["close"].to_numpy()
        fondos = detectar_fondos(close)
        resultados = analizar_rachas(close, fondos)

        print(f"=== {par}: {len(fondos)} fondos detectados, {len(resultados)} predicciones evaluadas ===")
        por_toques: dict[int, list[float]] = {}
        for n_toques, error in resultados:
            grupo = min(n_toques, 5)  # agrupa 5+ juntos, poca muestra si no
            por_toques.setdefault(grupo, []).append(abs(error))

        for grupo in sorted(por_toques):
            errores = np.array(por_toques[grupo])
            etiqueta = f"{grupo} toques previos" if grupo < 5 else "5+ toques previos"
            print(f"  {etiqueta}: n={len(errores)} error_absoluto_medio={errores.mean():.2f}% mediana={np.median(errores):.2f}%")
        print()


if __name__ == "__main__":
    main()
