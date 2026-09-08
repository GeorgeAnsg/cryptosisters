"""
Rebote en el soporte de un doble suelo ya confirmado — idea propuesta por
el usuario (8-sept-2026). Diferencia clave con el canal diagonal (que ya
se descartó): aquí la zona de soporte no se dibuja a ojo ni con pivotes
genéricos -- es el nivel EXACTO que ya validó una señal de Doble suelo
(motor con ventaja demostrada, ver laboratorio/doble_suelo.py). Eso quita
buena parte del problema de subjetividad ("¿dónde va la línea?") que hundió
al canal diagonal y a soporte/resistencia en general.

Qué dice la señal: cuando una señal de Doble suelo se confirma, se guarda
su nivel de soporte. Si en los siguientes `ventana_relevancia` días el
precio vuelve a bajar cerca de ese mismo nivel (dentro de la tolerancia)
SIN cerrar claramente por debajo (lo que invalidaría la zona), se
considera un "rebote" -- una segunda oportunidad de compra sobre el mismo
nivel ya validado.

Salida: mismo objetivo/stop que Doble suelo (30%/-12%), para no inventar
un parámetro nuevo sin motivo y poder comparar en igualdad de condiciones.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from laboratorio.doble_suelo import OBJETIVO_ROI, STOPLOSS, TOLERANCIA_SUELO


@dataclass
class TradeRebote:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(
    df: pd.DataFrame,
    ventana_relevancia_velas: int = 240,   # ~40 días en 4h
    tolerancia: float = TOLERANCIA_SUELO,
    objetivo: float = OBJETIVO_ROI,
    stop: float = STOPLOSS,
) -> list[TradeRebote]:
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    entra_ds = df["entra_largo"].to_numpy()
    soporte = df["soporte"].to_numpy()
    n = len(df)

    trades: list[TradeRebote] = []
    en_posicion = False
    idx_entrada = precio_entrada = None

    # niveles de soporte activos: lista de (idx_origen, nivel, idx_expira)
    niveles_activos: list[tuple[int, float, int]] = []

    for i in range(n):
        if entra_ds[i]:
            niveles_activos.append((i, soporte[i], i + ventana_relevancia_velas))
        niveles_activos = [nv for nv in niveles_activos if nv[2] >= i]

        if not en_posicion:
            for idx_origen, nivel, idx_expira in niveles_activos:
                if i <= idx_origen:
                    continue
                toca = low[i] <= nivel * (1 + tolerancia)
                no_invalidado = close[i] > nivel * (1 - tolerancia)
                if toca and no_invalidado:
                    en_posicion = True
                    idx_entrada = i
                    precio_entrada = close[i]
                    break
        else:
            retorno = close[i] / precio_entrada - 1
            if retorno >= objetivo or retorno <= stop:
                motivo = "objetivo" if retorno >= objetivo else "stop"
                trades.append(TradeRebote(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False

    return trades
