"""
Version continua de "grado de canal" -- respuesta directa a la duda del
usuario: "hemos jugado con absolutos (es canal / no es canal), ?no habra
algo si lo tratamos como probabilidad?".

En vez de un umbral binario (canal_diagonal.py, ya descartado), esto
calcula, en CADA vela, un ajuste de regresion lineal sobre los ultimos W
cierres:
- fuerza = R^2 del ajuste (0 = no hay tendencia lineal clara, 1 = recta
  perfecta) -- "cuanto parece un canal", en continuo, no binario.
- pendiente = signo de la recta (positivo = canal de subida, negativo =
  canal de bajada).

Test honesto: si esta "fuerza de canal" contiene informacion real sobre
el futuro, entonces velas con fuerza alta y pendiente positiva deberian
tener, en promedio, retornos futuros mejores que velas con fuerza alta y
pendiente negativa (canal de bajada) o que fuerza baja (sin canal claro).
Se mide con correlacion de Spearman entre (fuerza * signo(pendiente)) y
el retorno futuro a horizonte H, no con un umbral fijo -- exactamente el
enfoque "en probabilidades" que pide el usuario, no "en absolutos".
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd
from scipy import stats

from datos.cargar import cargar_ohlcv


def grado_canal(close: np.ndarray, ventana: int) -> tuple[np.ndarray, np.ndarray]:
    """Para cada indice i, ajusta una recta a close[i-ventana+1 : i+1] y
    devuelve (r2, pendiente_normalizada). Vectorizado con rolling manual
    (ventanas de miles de velas, aceptable para este tamano de dataset)."""
    n = len(close)
    r2 = np.full(n, np.nan)
    pendiente = np.full(n, np.nan)
    x = np.arange(ventana)
    x_centrado = x - x.mean()
    ss_x = np.sum(x_centrado ** 2)
    for i in range(ventana - 1, n):
        y = close[i - ventana + 1: i + 1]
        y_centrado = y - y.mean()
        b = np.sum(x_centrado * y_centrado) / ss_x
        pred = y.mean() + b * x_centrado
        ss_res = np.sum((y - pred) ** 2)
        ss_tot = np.sum(y_centrado ** 2)
        r2[i] = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        pendiente[i] = b / y.mean()  # normalizada por nivel de precio
    return r2, pendiente


def evaluar(par: str, tf: str, ventana: int, horizonte: int):
    df = cargar_ohlcv(par, tf)
    close = df["close"].to_numpy()
    r2, pendiente = grado_canal(close, ventana)

    fuerza_dirigida = r2 * np.sign(pendiente)
    retorno_futuro = np.full(len(close), np.nan)
    retorno_futuro[:-horizonte] = (close[horizonte:] / close[:-horizonte] - 1) * 100

    valido = ~np.isnan(fuerza_dirigida) & ~np.isnan(retorno_futuro)
    x = fuerza_dirigida[valido]
    y = retorno_futuro[valido]
    rho, p = stats.spearmanr(x, y)

    # Tambien: solo canales FUERTES (r2 alto), subida vs bajada
    fuerte = r2[valido] > 0.5
    sube = fuerte & (pendiente[valido] > 0)
    baja = fuerte & (pendiente[valido] < 0)
    media_sube = y[sube].mean() if sube.sum() > 0 else float("nan")
    media_baja = y[baja].mean() if baja.sum() > 0 else float("nan")

    print(f"{par} {tf} ventana={ventana} horizonte={horizonte}: "
          f"n={valido.sum()} spearman_rho={rho:.4f} p={p:.4f} | "
          f"canal_fuerte_subida n={sube.sum()} retorno_medio={media_sube:.2f}% | "
          f"canal_fuerte_bajada n={baja.sum()} retorno_medio={media_baja:.2f}%")


def main():
    for tf, ventana, horizonte in [("1h", 20, 20), ("4h", 20, 20), ("1d", 20, 20),
                                     ("1h", 50, 50), ("4h", 50, 50), ("1d", 50, 50)]:
        for par in ["BTCUSDT", "ETHUSDT"]:
            evaluar(par, tf, ventana, horizonte)
        print()


if __name__ == "__main__":
    main()
