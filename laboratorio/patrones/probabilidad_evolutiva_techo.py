"""
Fase C, punto 4 del roadmap ("probabilidad evolutiva mientras se forma el
patron") -- primera pieza, la mas basica y medible: en vez de esperar
ciegamente 3 dias fijos para confirmar que un maximo local es un techo
real (regla actual, `_detectar_techos_simple`, ventana=3), calcular una
probabilidad EMPIRICA de que aguante, dia a dia, mientras se va formando.

Motivacion del usuario (11-sept-2026): para apostar un trade hay que
decidir en algun momento, ANTES de la confirmacion retroactiva completa,
que un pico "va a ser" un pico -- necesitamos saber con que confianza se
puede hacer eso en cada dia transcurrido, no solo un si/no al final.

Definicion (real-time, sin mirar al futuro en el momento de la decision):
un dia `i` es "candidato a techo" si `close[i]` es el maximo de los
ultimos 3 dias (`close[i-3:i+1]`) -- esto SI se puede saber en tiempo real,
el mismo dia `i`. Lo que no se sabe todavia es si `close[i+1]`, `close[i+2]`
y `close[i+3]` se van a quedar todos por debajo (que es la definicion
exacta de techo confirmado en `_detectar_techos_simple`, ventana centrada
de 3 dias). Se mide, empiricamente:
- P(sobrevive dia i+1 | es candidato en dia i)
- P(sobrevive dia i+2 | sobrevivio dia i+1)
- P(sobrevive dia i+3 | sobrevivio dia i+2)  -- esto YA es la confirmacion final

Se segmenta ademas por volatilidad (terciles de ATR%/precio en los ultimos
14 dias) porque el propio usuario señalo que en un mercado mas volatil "ser
el maximo de los ultimos 3 dias" dice menos.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np
import pandas as pd

from laboratorio.datos_lab import cargar_ohlcv_lab


def _candidatos_y_supervivencia(df: pd.DataFrame, ventana: int = 3) -> pd.DataFrame:
    close = df["close"].to_numpy()
    high = df["high"].to_numpy() if "high" in df.columns else close
    low = df["low"].to_numpy() if "low" in df.columns else close
    n = len(close)

    # volatilidad: rango medio (high-low)/close de los ultimos 14 dias, en %
    rango_pct = (high - low) / close * 100
    vol_14 = pd.Series(rango_pct).rolling(14).mean().to_numpy()

    filas = []
    for i in range(ventana, n - ventana):
        # candidato: close[i] es el maximo de los ultimos `ventana` dias
        # (incluyendose el mismo) -- esto se sabe en tiempo real en el dia i.
        if close[i] != close[i - ventana: i + 1].max():
            continue
        sobrevive_1 = close[i + 1] <= close[i] if i + 1 < n else None
        sobrevive_2 = (sobrevive_1 and close[i + 2] <= close[i]) if i + 2 < n and sobrevive_1 is not None else None
        sobrevive_3 = (sobrevive_2 and close[i + 3] <= close[i]) if i + 3 < n and sobrevive_2 is not None else None
        filas.append({
            "idx": i, "volatilidad_pct": vol_14[i], "sobrevive_1": sobrevive_1,
            "sobrevive_2": sobrevive_2, "sobrevive_3": sobrevive_3,
        })
    return pd.DataFrame(filas)


def _tabla_probabilidad(df_cand: pd.DataFrame, etiqueta: str) -> None:
    n = len(df_cand)
    if n == 0:
        print(f"  {etiqueta}: sin candidatos")
        return
    p1 = df_cand["sobrevive_1"].mean()
    # de los que sobrevivieron dia 1, cuantos sobreviven dia 2 (condicional)
    sobrevivientes_1 = df_cand[df_cand["sobrevive_1"] == True]
    p2_cond = sobrevivientes_1["sobrevive_2"].mean() if len(sobrevivientes_1) > 0 else None
    sobrevivientes_2 = df_cand[df_cand["sobrevive_2"] == True]
    p3_cond = sobrevivientes_2["sobrevive_3"].mean() if len(sobrevivientes_2) > 0 else None
    # probabilidad ACUMULADA de terminar confirmado, vista desde el dia 0 (candidato)
    p_final = df_cand["sobrevive_3"].mean()
    print(f"  {etiqueta} (n_candidatos={n}):")
    print(f"    dia 0 (candidato, recien detectado): P(termine confirmado) = {p_final:.1%}")
    print(f"    dia 1 (sobrevivio 1 dia): P(sobreviva dia 2) = {p2_cond:.1%}" if p2_cond is not None else "    dia 1: sin datos")
    print(f"    dia 2 (sobrevivio 2 dias): P(sobreviva dia 3, = confirmado) = {p3_cond:.1%}" if p3_cond is not None else "    dia 2: sin datos")
    print(f"    P(sobrevive al menos 1 dia) = {p1:.1%}")


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="probabilidad_evolutiva_techo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="probabilidad_evolutiva_techo_btc")

    for nombre, df in [("ETH (todo el historial disponible)", df_eth), ("BTC (todo el historial disponible)", df_btc)]:
        print(f"=== {nombre} ===")
        cand = _candidatos_y_supervivencia(df)
        _tabla_probabilidad(cand, "TODOS los candidatos")

        validos = cand.dropna(subset=["volatilidad_pct"])
        terciles = validos["volatilidad_pct"].quantile([1/3, 2/3]).values
        baja = validos[validos["volatilidad_pct"] <= terciles[0]]
        media = validos[(validos["volatilidad_pct"] > terciles[0]) & (validos["volatilidad_pct"] <= terciles[1])]
        alta = validos[validos["volatilidad_pct"] > terciles[1]]
        _tabla_probabilidad(baja, "volatilidad BAJA (tercil inferior)")
        _tabla_probabilidad(media, "volatilidad MEDIA (tercil medio)")
        _tabla_probabilidad(alta, "volatilidad ALTA (tercil superior)")
        print()
