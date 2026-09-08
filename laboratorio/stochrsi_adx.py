"""
StochRSI + ADX — candidato heredado de corvus3, réplica fiel de la lógica
del bot viejo (~/Desktop/tr/v6/core/bot_indicators.py, líneas 425-436 y
1041-1076). Vive en laboratorio/ porque todavía NO ha pasado las 6 puertas
-- nadie debe importar esto desde motores/ hasta que se re-escriba allí
tras sobrevivir.

Qué dice la señal, en palabras normales:
- ADX >= 25 y +DI > -DI  ->  "hay una tendencia alcista confirmada"
- ADX >= 25 y -DI > +DI  ->  "hay una tendencia bajista confirmada"
- ADX < 25               ->  "no hay tendencia clara" (mercado lateral)

- StochRSI k y d por debajo de 20  ->  "sobreventa" (posible rebote alcista)
- StochRSI k y d por encima de 80  ->  "sobrecompra" (posible rebote bajista)
- k cruza por encima de d, viniendo de por debajo de 50  ->  "cruce alcista"
- k cruza por debajo de d, viniendo de por encima de 50  ->  "cruce bajista"

El catálogo de corvus3 probó 3 variantes bullish (ver docs/catalogo_bot_viejo.md
del proyecto corvus3): A) sobreventa sin importar la tendencia, B) sobreventa
solo si además hay tendencia bajista confirmada, C) cruce alcista. Aquí se
calculan las tres columnas de señal para poder probarlas por separado.
"""
from __future__ import annotations

import pandas as pd
import pandas_ta as ta


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    """Añade las columnas de StochRSI y ADX a un dataframe OHLCV.

    `df` debe tener columnas open/high/low/close/volume, ordenado por tiempo
    ascendente. No modifica el df de entrada; devuelve una copia.
    """
    df = df.copy()

    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    df["adx"] = adx_df["ADX_14"]
    df["adx_dmp"] = adx_df["DMP_14"]  # +DI
    df["adx_dmn"] = adx_df["DMN_14"]  # -DI

    srsi_df = ta.stochrsi(df["close"], length=14, rsi_length=14, k=3, d=3)
    df["stochrsi_k"] = srsi_df["STOCHRSIk_14_14_3_3"]
    df["stochrsi_d"] = srsi_df["STOCHRSId_14_14_3_3"]

    return df


def calcular_senales(df: pd.DataFrame) -> pd.DataFrame:
    """A partir de un df ya con `calcular_indicadores`, añade columnas de
    señal booleanas por vela: cada una dice "en esta vela, ¿se dispararía
    esta variante de la estrategia?"

    Columnas añadidas:
    - tendencia_alcista, tendencia_bajista  (contexto de ADX)
    - variante_a  -- StochRSI sobreventa (k<20 y d<20), sin mirar tendencia
    - variante_b  -- variante_a, pero solo si tendencia_bajista es True
    - variante_c  -- cruce alcista: k cruza por encima de d, viniendo k<50
    """
    df = df.copy()

    trending = df["adx"] >= 25
    df["tendencia_alcista"] = trending & (df["adx_dmp"] > df["adx_dmn"])
    df["tendencia_bajista"] = trending & (df["adx_dmn"] > df["adx_dmp"])

    sobreventa = (df["stochrsi_k"] < 20) & (df["stochrsi_d"] < 20)
    df["variante_a"] = sobreventa
    df["variante_b"] = sobreventa & df["tendencia_bajista"]

    k, d = df["stochrsi_k"], df["stochrsi_d"]
    k_prev, d_prev = k.shift(1), d.shift(1)
    cruce_alcista = (k_prev <= d_prev) & (k > d) & (k_prev < 50)
    df["variante_c"] = cruce_alcista.fillna(False)

    return df
