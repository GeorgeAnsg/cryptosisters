"""
Grid trading adaptativo — rejilla de niveles de compra/venta cuyo
espaciado se adapta a la volatilidad reciente (ATR), en vez de un
espaciado fijo en %.

Mecanismo: se colocan N niveles de compra por debajo del precio central
y N de venta por encima, separados por k×ATR. Cuando el precio cae hasta
un nivel de compra, se abre una posición ahí; cuando sube un escalón más
(el nivel de venta correspondiente), se cierra, capturando el espaciado
como beneficio. Se gana con la oscilación, no con la dirección.

RIESGO CONOCIDO Y CONTROLADO: en una tendencia bajista fuerte, el precio
puede caer por debajo de TODOS los niveles de compra sin volver a subir
-- el bot seguiría comprando niveles cada vez más bajos sin vender nunca,
acumulando pérdida sin límite. Para evitarlo: STOP DE SEGURIDAD -- si el
precio cae por debajo del nivel de compra más bajo en más de
`stop_bajo_rejilla`, se cierran TODAS las posiciones abiertas de golpe
(pérdida realizada, no se deja correr) y se re-centra la rejilla.

Re-centrado: cada `velas_recentrado` velas, o tras un stop, se recalculan
los niveles alrededor del precio actual usando el ATR reciente --
"adaptativo" significa esto: el tamaño de la rejilla cambia con la
volatilidad del momento, no queda fijo para siempre.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def calcular_atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


@dataclass
class TradeGrid:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str  # "venta_nivel" o "stop_rejilla"

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


@dataclass
class ResultadoGrid:
    trades: list[TradeGrid] = field(default_factory=list)
    n_stops_rejilla: int = 0
    n_recentrados: int = 0


def simular(
    df: pd.DataFrame,
    n_niveles: int = 5,
    k_atr_espaciado: float = 0.5,
    velas_recentrado: int = 180,       # ~30 dias en 4h
    stop_bajo_rejilla: float = 2.0,    # en unidades de "espaciado de rejilla"
    ventana_atr: int = 14,
) -> ResultadoGrid:
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    atr = calcular_atr(df, ventana_atr).to_numpy()
    n = len(df)

    resultado = ResultadoGrid()

    def nueva_rejilla(i):
        espaciado = k_atr_espaciado * atr[i]
        centro = close[i]
        niveles_compra = [centro - espaciado * k for k in range(1, n_niveles + 1)]
        return centro, espaciado, niveles_compra

    idx_ultimo_recentrado = ventana_atr  # esperar a tener ATR valido
    while idx_ultimo_recentrado < n and np.isnan(atr[idx_ultimo_recentrado]):
        idx_ultimo_recentrado += 1
    if idx_ultimo_recentrado >= n:
        return resultado

    centro, espaciado, niveles_compra = nueva_rejilla(idx_ultimo_recentrado)
    # posiciones abiertas: lista de (idx_nivel, idx_entrada, precio_entrada)
    posiciones_abiertas: dict[int, tuple[int, float]] = {}

    for i in range(idx_ultimo_recentrado, n):
        # 1. stop de seguridad: precio muy por debajo del nivel de compra mas bajo
        nivel_mas_bajo = min(niveles_compra)
        if close[i] < nivel_mas_bajo - stop_bajo_rejilla * espaciado and posiciones_abiertas:
            for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, close[i], "stop_rejilla"))
            posiciones_abiertas = {}
            resultado.n_stops_rejilla += 1
            centro, espaciado, niveles_compra = nueva_rejilla(i)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i
            continue

        # 2. re-centrado periodico (si no hubo stop)
        if i - idx_ultimo_recentrado >= velas_recentrado:
            centro, espaciado, niveles_compra = nueva_rejilla(i)
            resultado.n_recentrados += 1
            idx_ultimo_recentrado = i

        # 3. rellenar compras: nivel tocado y sin posicion abierta ahi
        for idx_nivel, nivel in enumerate(niveles_compra):
            if idx_nivel in posiciones_abiertas:
                continue
            if low[i] <= nivel:
                posiciones_abiertas[idx_nivel] = (i, nivel)

        # 4. rellenar ventas: precio sube un escalon por encima del nivel de compra
        for idx_nivel in list(posiciones_abiertas.keys()):
            _, precio_ent = posiciones_abiertas[idx_nivel]
            nivel_venta = precio_ent + espaciado
            if high[i] >= nivel_venta:
                idx_ent, _ = posiciones_abiertas[idx_nivel]
                resultado.trades.append(TradeGrid(idx_ent, i, precio_ent, nivel_venta, "venta_nivel"))
                del posiciones_abiertas[idx_nivel]

    # cerrar lo que quede abierto al final, al ultimo precio (marcar a mercado)
    for idx_nivel, (idx_ent, precio_ent) in posiciones_abiertas.items():
        resultado.trades.append(TradeGrid(idx_ent, n - 1, precio_ent, close[-1], "fin_periodo"))

    return resultado
