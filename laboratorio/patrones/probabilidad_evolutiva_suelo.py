"""
Espejo de `probabilidad_evolutiva_techo.py` para el suelo -- medido de
cero, no asumiendo que la curva de supervivencia del techo (31%/71%/85%/
100%) sirve igual para el suelo (misma disciplina de toda la sesion: no
asumir simetria entre techo y suelo sin comprobarlo).

Definicion (real-time, sin mirar al futuro en el momento de la decision):
un dia `i` es "candidato a fondo" si `close[i]` es el MINIMO de los
ultimos 3 dias -- se sabe en tiempo real. Lo que no se sabe todavia es si
`close[i+1..i+3]` se quedan todos por ENCIMA (confirmacion de fondo real).
Se mide, empiricamente:
- P(sobrevive dia i+1 | es candidato en dia i)
- P(sobrevive dia i+2 | sobrevivio dia i+1)
- P(sobrevive dia i+3 | sobrevivio dia i+2) -- confirmacion final
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

    rango_pct = (high - low) / close * 100
    vol_14 = pd.Series(rango_pct).rolling(14).mean().to_numpy()

    filas = []
    for i in range(ventana, n - ventana):
        if close[i] != close[i - ventana: i + 1].min():
            continue
        sobrevive_1 = close[i + 1] >= close[i] if i + 1 < n else None
        sobrevive_2 = (sobrevive_1 and close[i + 2] >= close[i]) if i + 2 < n and sobrevive_1 is not None else None
        sobrevive_3 = (sobrevive_2 and close[i + 3] >= close[i]) if i + 3 < n and sobrevive_2 is not None else None
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
    sobrevivientes_1 = df_cand[df_cand["sobrevive_1"] == True]
    p2_cond = sobrevivientes_1["sobrevive_2"].mean() if len(sobrevivientes_1) > 0 else None
    sobrevivientes_2 = df_cand[df_cand["sobrevive_2"] == True]
    p3_cond = sobrevivientes_2["sobrevive_3"].mean() if len(sobrevivientes_2) > 0 else None
    p_final = df_cand["sobrevive_3"].mean()
    print(f"  {etiqueta} (n_candidatos={n}):")
    print(f"    dia 0 (candidato, recien detectado): P(termine confirmado) = {p_final:.1%}")
    print(f"    dia 1 (sobrevivio 1 dia): P(sobreviva dia 2) = {p2_cond:.1%}" if p2_cond is not None else "    dia 1: sin datos")
    print(f"    dia 2 (sobrevivio 2 dias): P(sobreviva dia 3, = confirmado) = {p3_cond:.1%}" if p3_cond is not None else "    dia 2: sin datos")
    print(f"    P(sobrevive al menos 1 dia) = {p1:.1%}")


if __name__ == "__main__":
    df_eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="probabilidad_evolutiva_suelo_eth")
    df_btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="probabilidad_evolutiva_suelo_btc")

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
