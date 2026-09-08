"""
Hombro-Cabeza-Hombro invertido (alcista) — candidato nuevo, nunca probado
en ningún corvus anterior (estaba anotado en corvus2 como "el siguiente
motor natural" tras el doble suelo, pero el proyecto cambió de
arquitectura antes de llegar a construirlo). Misma familia que Doble
suelo (que ya funcionó en BTC solo): un patrón de fondo grande y
selectivo, no una señal frecuente.

Qué es el patrón, en palabras normales: tres mínimos seguidos --
"hombro izquierdo", "cabeza" (el más bajo de los tres) y "hombro derecho"
(parecido en nivel al izquierdo) -- con dos máximos intermedios que forman
el "neckline" (el cuello). Cuando el precio rompe por encima del
neckline tras formarse el hombro derecho, se considera confirmado.

Detección causal (reutiliza `calcular_pivotes` de canal_diagonal_rebote,
ya validada con la Puerta 1): un pivote solo se conoce `ventana` velas
después de formarse -- igual que con el canal diagonal, nunca se mira al
futuro.

Salida: objetivo por "measured move" (altura cabeza->neckline, proyectada
desde la rotura) y stop por debajo de la cabeza (si el precio vuelve ahí,
el patrón queda invalidado). A diferencia de Canal (estrategia de
tendencia, donde un objetivo fijo demostró perjudicar), aquí SÍ tiene
sentido un objetivo por altura: es la técnica estándar para patrones de
gráfico, no para sistemas de seguir tendencia.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from laboratorio.canal_diagonal_rebote import calcular_pivotes


@dataclass
class PatronHCH:
    idx_hombro_izq: int
    idx_cabeza: int
    idx_hombro_der: int
    idx_confirmacion: int
    precio_cabeza: float
    neckline: float
    altura: float


def detectar_patrones(
    df: pd.DataFrame,
    ventana_pivote: int = 10,
    tolerancia_hombros: float = 0.10,
) -> list[PatronHCH]:
    altos, bajos = calcular_pivotes(df, ventana_pivote)
    patrones = []
    for i in range(2, len(bajos)):
        idx1, _, precio1 = bajos[i - 2]
        idx2, _, precio2 = bajos[i - 1]
        idx3, conf3, precio3 = bajos[i]
        if not (precio2 < precio1 and precio2 < precio3):
            continue
        if abs(precio1 - precio3) / precio1 > tolerancia_hombros:
            continue
        picos_izq = [p for p in altos if idx1 < p[0] < idx2]
        picos_der = [p for p in altos if idx2 < p[0] < idx3]
        if not picos_izq or not picos_der:
            continue
        pico_izq = max(picos_izq, key=lambda p: p[2])
        pico_der = max(picos_der, key=lambda p: p[2])
        neckline = (pico_izq[2] + pico_der[2]) / 2
        if neckline <= precio2:
            continue
        patrones.append(PatronHCH(
            idx_hombro_izq=idx1, idx_cabeza=idx2, idx_hombro_der=idx3,
            idx_confirmacion=conf3, precio_cabeza=precio2, neckline=neckline,
            altura=neckline - precio2,
        ))
    return patrones


@dataclass
class TradeHCH:
    idx_entrada: int
    idx_salida: int
    precio_entrada: float
    precio_salida: float
    motivo_salida: str

    @property
    def retorno_pct(self) -> float:
        return (self.precio_salida / self.precio_entrada - 1) * 100


def simular(df: pd.DataFrame, ventana_pivote: int = 10, tolerancia_hombros: float = 0.10) -> list[TradeHCH]:
    patrones = detectar_patrones(df, ventana_pivote, tolerancia_hombros)
    close = df["close"].to_numpy()
    n = len(df)

    trades: list[TradeHCH] = []
    en_posicion = False
    idx_entrada = precio_entrada = objetivo = stop = None
    ptr = 0
    patrones_disponibles: list[PatronHCH] = []
    patron_usado_hasta = -1

    for t in range(n):
        while ptr < len(patrones) and patrones[ptr].idx_confirmacion <= t:
            patrones_disponibles.append(patrones[ptr])
            ptr += 1

        if not en_posicion:
            # entrada: el patrón disponible cuya rotura del neckline ocurre justo en t
            for p in patrones_disponibles:
                if p.idx_confirmacion > patron_usado_hasta and t >= p.idx_confirmacion:
                    cruzo_ahora = (close[t] > p.neckline) and (t == 0 or close[t - 1] <= p.neckline)
                    invalidado_ya = close[p.idx_confirmacion:t + 1].min() < p.precio_cabeza
                    if invalidado_ya:
                        patron_usado_hasta = max(patron_usado_hasta, p.idx_confirmacion)
                        continue
                    if cruzo_ahora:
                        en_posicion = True
                        idx_entrada = t
                        precio_entrada = close[t]
                        objetivo = precio_entrada + p.altura
                        stop = p.precio_cabeza
                        patron_usado_hasta = p.idx_confirmacion
                        break
        else:
            if close[t] >= objetivo or close[t] <= stop:
                motivo = "objetivo" if close[t] >= objetivo else "stop"
                trades.append(TradeHCH(idx_entrada, t, precio_entrada, close[t], motivo))
                en_posicion = False

    return trades
