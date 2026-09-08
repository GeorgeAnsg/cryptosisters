"""
Experimento: objetivo por "altura del canal" (measured move) para Canal.

Idea (propuesta por el usuario, 8-sept-2026): en vez de esperar pasivamente
a que el precio vuelva a caer al canal de salida de 10 días, poner un
objetivo de beneficio a una distancia igual a la ALTURA del canal de
entrada (canal_alto - canal_bajo) medida en el momento de la rotura.
Es una técnica clásica de análisis técnico ("measured move").

Esto es un experimento de laboratorio, no una puerta -- compara dos
versiones del mismo motor con una simulación de operación real (entrada
-> salida), no con el proxy de horizonte fijo que se usó para StochRSI
(aquí SÍ hay una regla de salida real que simular, así que no hace falta
el proxy). Partición respetada: solo Desarrollo (2020-2024) en esta
primera pasada -- 2025 y el grupo sellado se guardan por si esto merece
confirmarse después.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Trade:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular_trades(df: pd.DataFrame, con_objetivo: bool) -> list[Trade]:
    close = df["close"].to_numpy()
    entra = df["entra_largo"].to_numpy()
    sale = df["sale_largo"].to_numpy()
    canal_alto = df["canal_alto"].to_numpy()
    canal_bajo = df["canal_bajo"].to_numpy()

    trades: list[Trade] = []
    en_posicion = False
    idx_entrada = precio_entrada = objetivo = None

    for i in range(len(df)):
        if not en_posicion:
            if entra[i]:
                en_posicion = True
                idx_entrada = i
                precio_entrada = close[i]
                if con_objetivo:
                    altura = canal_alto[i] - canal_bajo[i]
                    objetivo = precio_entrada + altura
        else:
            tocó_objetivo = con_objetivo and close[i] >= objetivo
            if tocó_objetivo or sale[i]:
                motivo = "objetivo" if tocó_objetivo else "salida_original"
                trades.append(Trade(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False

    return trades


@dataclass
class ResumenBacktest:
    n_trades: int
    retorno_medio_pct: float
    retorno_total_compuesto_pct: float
    pct_ganadoras: float
    peor_trade_pct: float
    caida_max_equity_pct: float
    motivos: dict

    def resumen(self) -> str:
        return (
            f"{self.n_trades} operaciones | retorno medio por operación: "
            f"{self.retorno_medio_pct:+.2f}% | retorno total compuesto: "
            f"{self.retorno_total_compuesto_pct:+.1f}% | % ganadoras: "
            f"{self.pct_ganadoras:.1f}% | peor operación: {self.peor_trade_pct:+.1f}% | "
            f"caída máxima de la curva de equity: {self.caida_max_equity_pct:.1f}% | "
            f"motivos de salida: {self.motivos}"
        )


def resumir(trades: list[Trade]) -> ResumenBacktest:
    if not trades:
        return ResumenBacktest(0, 0, 0, 0, 0, 0, {})
    retornos = np.array([t.retorno_pct for t in trades])
    equity = np.cumprod(1 + retornos / 100)
    pico = np.maximum.accumulate(equity)
    caida = (equity / pico - 1) * 100
    motivos = {}
    for t in trades:
        motivos[t.motivo_salida] = motivos.get(t.motivo_salida, 0) + 1
    return ResumenBacktest(
        n_trades=len(trades),
        retorno_medio_pct=float(retornos.mean()),
        retorno_total_compuesto_pct=float((equity[-1] - 1) * 100),
        pct_ganadoras=float((retornos > 0).mean() * 100),
        peor_trade_pct=float(retornos.min()),
        caida_max_equity_pct=float(caida.min()),
        motivos=motivos,
    )
