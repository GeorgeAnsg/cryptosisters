"""
Canal diagonal (rebote) — candidato nuevo, propuesto por el usuario
(8-sept-2026). Apuesta a que el precio rebota DENTRO de un canal inclinado
(línea de mínimos crecientes / línea de máximos crecientes, o al revés si
es descendente), en vez de apostar a que lo rompe (eso es Canal, el otro
motor). Vive en laboratorio/, es exploratorio, no pasa aún ninguna puerta.

Decisiones de diseño, para que se puedan juzgar (versión simplificada a
propósito, primera pasada):

1. PIVOTES CAUSALES. Un máximo o mínimo local solo se puede confirmar
   mirando unas velas hacia ambos lados -- por eso solo se "sabe" que la
   vela i fue un pivote `ventana` velas DESPUÉS de i, nunca antes. Esto
   replica la misma técnica ya usada en el catálogo heredado
   (`rsi_divergencia`, ~/Desktop/tr/v6) para evitar mirar al futuro.
2. LAS LÍNEAS se ajustan (regresión simple) sobre los últimos N pivotes
   YA CONFIRMADOS en el momento de operar -- nunca sobre pivotes futuros.
3. SEÑAL: se considera "toque" cuando la mecha de la vela llega cerca de
   la línea de soporte (mínimos) pero el CIERRE queda por encima --eso es
   la "reacción" que confirma el rebote, no solo tocar la línea.
4. INVALIDACIÓN: si el precio CIERRA por debajo de la línea de soporte
   más de un margen pequeño, el canal se da por roto y no se opera más
   sobre él hasta que se formen pivotes nuevos.
5. SALIDA: al tocar la línea de resistencia (objetivo), o si el canal se
   invalida (stop).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def calcular_pivotes(df: pd.DataFrame, ventana: int = 10) -> tuple[list[tuple[int, int, float]], list[tuple[int, int, float]]]:
    """Devuelve (pivotes_altos, pivotes_bajos), cada uno una lista de
    tuplas (indice_del_pivote, indice_en_que_se_confirma, precio).
    """
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    n = len(df)
    altos, bajos = [], []
    for i in range(ventana, n - ventana):
        seg_h = high[i - ventana: i + ventana + 1]
        if high[i] == seg_h.max() and np.sum(seg_h == high[i]) == 1:
            altos.append((i, i + ventana, float(high[i])))
        seg_l = low[i - ventana: i + ventana + 1]
        if low[i] == seg_l.min() and np.sum(seg_l == low[i]) == 1:
            bajos.append((i, i + ventana, float(low[i])))
    return altos, bajos


def _ajustar_linea(puntos: list[tuple[int, float]]) -> tuple[float, float] | None:
    """Regresión lineal simple (mínimos cuadrados) sobre (indice, precio).
    Devuelve (pendiente, intercepto) o None si hay menos de 2 puntos."""
    if len(puntos) < 2:
        return None
    xs = np.array([p[0] for p in puntos], dtype=float)
    ys = np.array([p[1] for p in puntos], dtype=float)
    pendiente, intercepto = np.polyfit(xs, ys, 1)
    return float(pendiente), float(intercepto)


@dataclass
class TradeDiagonal:
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
    ventana_pivote: int = 10,
    n_pivotes_linea: int = 3,
    tolerancia_toque: float = 0.01,
    margen_invalidacion: float = 0.02,
) -> list[TradeDiagonal]:
    """Simula la estrategia de rebote sobre un canal diagonal.

    - ventana_pivote: velas a cada lado para confirmar un pivote.
    - n_pivotes_linea: cuántos pivotes recientes (ya confirmados) se usan
      para ajustar cada línea.
    - tolerancia_toque: cuán cerca de la línea (en % del precio) cuenta
      como "toque" de la mecha.
    - margen_invalidacion: cuánto tiene que cerrar por debajo/encima de la
      línea contraria para dar el canal por roto.
    """
    altos, bajos = calcular_pivotes(df, ventana_pivote)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)

    trades: list[TradeDiagonal] = []
    en_posicion = False
    idx_entrada = precio_entrada = None
    canal_invalidado_hasta = -1  # evita re-operar el mismo canal roto

    ptr_alto = ptr_bajo = 0  # punteros para ir incorporando pivotes ya confirmados

    pivotes_altos_confirmados: list[tuple[int, float]] = []
    pivotes_bajos_confirmados: list[tuple[int, float]] = []

    for t in range(n):
        while ptr_alto < len(altos) and altos[ptr_alto][1] <= t:
            pivotes_altos_confirmados.append((altos[ptr_alto][0], altos[ptr_alto][2]))
            ptr_alto += 1
        while ptr_bajo < len(bajos) and bajos[ptr_bajo][1] <= t:
            pivotes_bajos_confirmados.append((bajos[ptr_bajo][0], bajos[ptr_bajo][2]))
            ptr_bajo += 1

        linea_soporte = _ajustar_linea(pivotes_bajos_confirmados[-n_pivotes_linea:])
        linea_resistencia = _ajustar_linea(pivotes_altos_confirmados[-n_pivotes_linea:])
        if linea_soporte is None or linea_resistencia is None:
            continue

        m_s, b_s = linea_soporte
        m_r, b_r = linea_resistencia
        soporte_t = m_s * t + b_s
        resistencia_t = m_r * t + b_r
        if soporte_t <= 0 or resistencia_t <= soporte_t:
            continue  # canal degenerado (líneas cruzadas o precio absurdo), se ignora

        if not en_posicion:
            if t <= canal_invalidado_hasta:
                continue
            tocó_soporte = low[t] <= soporte_t * (1 + tolerancia_toque)
            cerró_encima = close[t] > soporte_t
            if tocó_soporte and cerró_encima:
                en_posicion = True
                idx_entrada = t
                precio_entrada = close[t]
        else:
            invalidado = close[t] < soporte_t * (1 - margen_invalidacion)
            tocó_resistencia = high[t] >= resistencia_t * (1 - tolerancia_toque)
            if invalidado or tocó_resistencia:
                motivo = "canal_roto" if invalidado else "objetivo_resistencia"
                trades.append(TradeDiagonal(idx_entrada, t, precio_entrada, close[t], motivo))
                en_posicion = False
                if invalidado:
                    canal_invalidado_hasta = t + ventana_pivote

    return trades
