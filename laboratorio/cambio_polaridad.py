"""
Cambio de polaridad: una zona que antes fue soporte (validada por un Doble
suelo confirmado) pasa a actuar como resistencia cuando el precio vuelve a
visitarla DESDE ARRIBA. Idea propuesta por el usuario (8-sept-2026),
distinta de "rebote en soporte" (que ya se descartó): aquí la apuesta es
que el precio RECHAZA la zona hacia abajo, no que rebota hacia arriba.

Mecanismo clásico de análisis técnico ("role reversal" / soporte roto se
convierte en resistencia). Se usa el mismo nivel ya validado por Doble
suelo -- no una zona genérica a ojo -- para no repetir el problema de
subjetividad del canal diagonal.

Señal: tras una señal de Doble suelo confirmada, si el precio SUBE por
encima del nivel de soporte y LUEGO vuelve a bajar hasta esa misma zona
(aproximándose desde arriba) sin refugiarse por debajo del todo, y la vela
muestra rechazo (mecha hacia abajo, cierre de vuelta hacia arriba de la
zona = sigue aguantando; o cierre por debajo = confirma que ahora es
resistencia y rechaza), se entra en corto.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from laboratorio.doble_suelo import TOLERANCIA_SUELO


@dataclass
class TradePolaridad:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        # posicion corta: gana si el precio BAJA
        return (self.precio_entrada / self.precio_salida - 1) * 100


def simular(
    df: pd.DataFrame,
    ventana_relevancia_velas: int = 480,
    tolerancia: float = TOLERANCIA_SUELO,
    objetivo: float = 0.15,   # objetivo mas modesto: es un rechazo, no una rotura de tendencia
    stop: float = 0.08,
) -> list[TradePolaridad]:
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    entra_ds = df["entra_largo"].to_numpy()
    soporte = df["soporte"].to_numpy()
    n = len(df)

    trades: list[TradePolaridad] = []
    en_posicion = False
    idx_entrada = precio_entrada = None

    # niveles: (idx_origen, nivel, idx_expira, ya_estuvo_arriba)
    niveles_activos: list[list] = []

    for i in range(n):
        if entra_ds[i]:
            niveles_activos.append([i, soporte[i], i + ventana_relevancia_velas, False])
        niveles_activos = [nv for nv in niveles_activos if nv[2] >= i]

        for nv in niveles_activos:
            idx_origen, nivel, idx_expira, ya_arriba = nv
            if close[i] > nivel * (1 + 2 * tolerancia):
                nv[3] = True   # ha estado claramente por encima -> ahora una vuelta cuenta como "desde arriba"

        if not en_posicion:
            for idx_origen, nivel, idx_expira, ya_arriba in niveles_activos:
                if i <= idx_origen or not ya_arriba:
                    continue
                toca_desde_arriba = (high[i] >= nivel * (1 - tolerancia)) and (close[i] <= nivel * (1 + tolerancia))
                if toca_desde_arriba:
                    en_posicion = True
                    idx_entrada = i
                    precio_entrada = close[i]
                    break
        else:
            retorno_corto = precio_entrada / close[i] - 1
            if retorno_corto >= objetivo or -retorno_corto >= stop:
                motivo = "objetivo" if retorno_corto >= objetivo else "stop"
                trades.append(TradePolaridad(idx_entrada, i, precio_entrada, close[i], motivo))
                en_posicion = False

    return trades
