"""
bot_swing.py — Estrategia swing (v6)
=====================================
Timeframe base: 1h
HTF: 1D como veto duro (solo opera si el diario está de acuerdo)

Parámetros típicos:
  SL: 2.5-4×ATR  |  TP: 7-12×ATR  |  Duración: 1-5 días

Diferencias clave respecto a intraday:
  - Opera sobre velas 1h → menos ruido, señales más fiables para trades largos
  - Filtro HTF 1D (no 4h): la tendencia diaria importa más para trades de días
  - Indicadores ponderados de forma diferente: más peso a MACD y EMAs lentas
  - min_hold_candles más alto: dejar que el trade respire antes de cerrar por señal
  - Score umbral más exigente (se recomienda MS ≥ 60)

Nota: este bot descarga datos 1h en live y usa precompute_indicators_1h en backtest.
El DataFrame de 1h se prepara desde run_live/run_backtest con timeframe='1h'.

Uso:
    from v6.strategies.bot_swing import SwingStrategy
    strategy = SwingStrategy()
    signal = strategy.get_signal(df_slice, live_extras)
"""

import pandas as pd
import pandas_ta as ta

from v6.core.bot_risk import calculate_scores
from v6.core.bot_core import Signal


def _analyze_swing(row, prev_row=None) -> dict:
    """Scoring técnico optimizado para velas 1h y trades de días.

    Pesos ajustados respecto al intraday:
      - EMAs lentas (1h) tienen más peso: tendencia de horas no es ruido
      - RSI: zonas más extremas para entrar (sobrecompra/venta verdaderas en 1h)
      - MACD: solo cuenta el cruce, no el momentum parcial (menos señales, más fiables)
      - Patrones de vela: menos peso (1h ya tiene menos ruido, no necesitan boost extra)
      - HTF (4h): sigue scoring porque sigue siendo relevante para el swing
    """
    if prev_row is None:
        prev_row = row

    bullish = 0
    bearish = 0
    details = {}

    price  = row["close"]
    details["price"] = round(price, 2)

    # RSI (max 10 pts — zonas más extremas que en 15m)
    rsi = row.get("rsi", 50)
    if pd.notna(rsi):
        details["rsi"] = round(rsi, 1)
        if rsi < 20:   bullish += 10
        elif rsi < 30: bullish += 7
        elif rsi < 40: bullish += 3
        if rsi > 80:   bearish += 10
        elif rsi > 70: bearish += 7
        elif rsi > 60: bearish += 3
    else:
        details["rsi"] = 50.0

    # EMAs (max 15 pts — mismo peso pero exigimos más separación)
    e9, e21, e50, e200 = (row.get(k, 0) for k in ("ema_9", "ema_21", "ema_50", "ema_200"))
    if pd.notna(e9) and pd.notna(e21) and pd.notna(e50):
        if e9 > e21 > e50:
            bullish += 12; details["trend"] = "alcista fuerte"
        elif e9 > e21:
            bullish += 6;  details["trend"] = "alcista"
        elif e9 < e21 < e50:
            bearish += 12; details["trend"] = "bajista fuerte"
        elif e9 < e21:
            bearish += 6;  details["trend"] = "bajista"
        else:
            details["trend"] = "lateral"
        if pd.notna(e200):
            if price > e200:   bullish += 3; details["above_ema200"] = True
            elif price < e200: bearish += 3; details["above_ema200"] = False
            else:              details["above_ema200"] = None
    else:
        details["trend"] = "calculando"

    # MACD (max 10 pts — solo cruces, no momentum parcial)
    mh  = row.get("MACDh_12_26_9", 0)
    pmh = prev_row.get("MACDh_12_26_9", 0)
    if pd.notna(mh) and pd.notna(pmh):
        if mh > 0 and pmh <= 0:   bullish += 10; details["macd"] = "cruce alcista"
        elif mh > 0:               bullish += 3;  details["macd"] = "momentum alcista"
        elif mh < 0 and pmh >= 0: bearish += 10; details["macd"] = "cruce bajista"
        elif mh < 0:               bearish += 3;  details["macd"] = "momentum bajista"
        else:                                      details["macd"] = "neutral"
    else:
        details["macd"] = "sin datos"

    # Bollinger Bands (max 8 pts)
    bbl = row.get("BBL_20_2.0")
    bbu = row.get("BBU_20_2.0")
    if pd.notna(bbl) and pd.notna(bbu) and (bbu - bbl) > 0:
        if price <= bbl:   bullish += 8; details["bollinger"] = "bajo banda inferior"
        elif price >= bbu: bearish += 8; details["bollinger"] = "sobre banda superior"
        else:
            bb_pos = (price - bbl) / (bbu - bbl)
            if bb_pos < 0.25:   bullish += 4
            elif bb_pos > 0.75: bearish += 4
            details["bollinger"] = f"pos:{bb_pos:.0%}"
    else:
        details["bollinger"] = "sin datos"

    # Price action (menos peso en swing — la vela 1h ya es un trade completo)
    body  = row.get("body_size", 0)
    open_p = row.get("open", price)
    atr_pa = row.get("atr", 0)
    if row.get("bull_engulf", 0) > 0.5: bullish += 6; details["pa"] = "engulf alcista"
    elif row.get("bear_engulf", 0) > 0.5: bearish += 6; details["pa"] = "engulf bajista"
    if row.get("hammer", 0) > 0.5: bullish += 5; details["pa_vela"] = "hammer"
    elif row.get("shooting_star", 0) > 0.5: bearish += 5; details["pa_vela"] = "shooting star"
    if row.get("three_bull", 0) > 0.5: bullish += 5; details["pa_seq"] = "3 alcistas"
    elif row.get("three_bear", 0) > 0.5: bearish += 5; details["pa_seq"] = "3 bajistas"
    if pd.notna(body) and pd.notna(atr_pa) and atr_pa > 0 and body > 2.0 * atr_pa:
        if price > open_p:   bullish += 4; details["pa_impulso"] = f"bull {body/atr_pa:.1f}xATR"
        elif price < open_p: bearish += 4; details["pa_impulso"] = f"bear {body/atr_pa:.1f}xATR"

    # S/R breakout (en 1h los niveles son más significativos)
    r20  = row.get("rolling_high_20");  l20  = row.get("rolling_low_20")
    r100 = row.get("rolling_high_100"); l100 = row.get("rolling_low_100")
    if r100 is not None and pd.notna(r100) and price > r100:
        bullish += 6; details["sr_break"] = "resist diaria rota"
    elif l100 is not None and pd.notna(l100) and price < l100:
        bearish += 6; details["sr_break"] = "soporte diario roto"
    elif r20 is not None and pd.notna(r20) and price > r20:
        bullish += 4; details["sr_break"] = "resist 20h rota"
    elif l20 is not None and pd.notna(l20) and price < l20:
        bearish += 4; details["sr_break"] = "soporte 20h roto"

    # Consolidación
    details["consolidacion"] = bool(row.get("atr_contracted", 0) > 0.5)

    # VWAP
    vwap = row.get("vwap")
    if vwap is not None and pd.notna(vwap):
        details["vwap"] = round(vwap, 2)
        details["vwap_bias"] = "sobre VWAP" if price > vwap else "bajo VWAP"
    else:
        details["vwap_bias"] = "sin datos"

    # HTF 4h en swing (contexto, no bloqueo — el bloqueo viene del 1D)
    e9_4h  = row.get("ema_9_4h")
    e21_4h = row.get("ema_21_4h")
    e50_4h = row.get("ema_50_4h")
    if pd.notna(e9_4h) and pd.notna(e21_4h) and pd.notna(e50_4h):
        if e9_4h > e21_4h > e50_4h:
            bullish += 6; details["htf_trend"] = "alcista"
        elif e9_4h > e21_4h:
            bullish += 3; details["htf_trend"] = "alcista parcial"
        elif e9_4h < e21_4h < e50_4h:
            bearish += 6; details["htf_trend"] = "bajista"
        elif e9_4h < e21_4h:
            bearish += 3; details["htf_trend"] = "bajista parcial"
        else:
            details["htf_trend"] = "lateral"
    else:
        details["htf_trend"] = "calculando"

    # Tendencia 1D (para registro en details)
    d_ema20 = row.get("d_ema20")
    d_ema50 = row.get("d_ema50")
    if pd.notna(d_ema20) and pd.notna(d_ema50) and d_ema50 > 0:
        if d_ema20 > d_ema50 * 1.002:   details["htf_1d_trend"] = "alcista"
        elif d_ema20 < d_ema50 * 0.998: details["htf_1d_trend"] = "bajista"
        else:                            details["htf_1d_trend"] = "lateral"
    else:
        details["htf_1d_trend"] = "calculando"

    # Volumen (confirmación swing: exige más volumen)
    vol_ratio = row.get("vol_ratio", 1.0)
    if pd.notna(vol_ratio):
        details["vol_ratio"] = round(vol_ratio, 2)
        if vol_ratio > 2.5:
            if bullish > bearish: bullish += 7
            elif bearish > bullish: bearish += 7
        elif vol_ratio > 1.5:
            if bullish > bearish: bullish += 3
            elif bearish > bullish: bearish += 3
    else:
        details["vol_ratio"] = 1.0

    details["atr"] = round(atr_pa, 2) if pd.notna(atr_pa) else 0

    return {
        "bullish_score": min(50, bullish),
        "bearish_score": min(50, bearish),
        "details":       details,
        "bbl":           row.get("BBL_20_2.0"),
        "bbu":           row.get("BBU_20_2.0"),
    }


def _precompute_1h_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Precalcula indicadores sobre un DataFrame de velas 1h."""
    from v6.core.bot_indicators import _add_htf_4h_columns, _add_htf_1d_columns
    df = df.copy()
    df["rsi"]     = ta.rsi(df["close"], length=14)
    df["ema_9"]   = ta.ema(df["close"], length=9)
    df["ema_21"]  = ta.ema(df["close"], length=21)
    df["ema_50"]  = ta.ema(df["close"], length=50)
    df["ema_200"] = ta.ema(df["close"], length=200)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None:
        df = pd.concat([df, bb], axis=1)
    df["atr"]      = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["vol_sma"]  = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma"]
    df["body_size"]    = (df["close"] - df["open"]).abs()
    df["upper_wick"]   = df["high"] - df[["close", "open"]].max(axis=1)
    df["lower_wick"]   = df[["close", "open"]].min(axis=1) - df["low"]
    df["candle_range"] = df["high"] - df["low"]
    df["bull_engulf"]  = (
        (df["close"] > df["open"]) &
        (df["open"]  < df["close"].shift(1)) &
        (df["close"] > df["open"].shift(1))
    ).astype(float)
    df["bear_engulf"]  = (
        (df["close"] < df["open"]) &
        (df["open"]  > df["close"].shift(1)) &
        (df["close"] < df["open"].shift(1))
    ).astype(float)
    df["hammer"] = (
        (df["lower_wick"] > 2 * df["body_size"].clip(lower=0.0001)) &
        (df["upper_wick"] < df["body_size"]) &
        (df["candle_range"] > 0)
    ).astype(float)
    df["shooting_star"] = (
        (df["upper_wick"] > 2 * df["body_size"].clip(lower=0.0001)) &
        (df["lower_wick"] < df["body_size"]) &
        (df["candle_range"] > 0)
    ).astype(float)
    df["three_bull"] = (
        (df["close"] > df["open"]) &
        (df["close"].shift(1) > df["open"].shift(1)) &
        (df["close"].shift(2) > df["open"].shift(2)) &
        (df["close"] > df["close"].shift(1)) &
        (df["close"].shift(1) > df["close"].shift(2))
    ).astype(float)
    df["three_bear"] = (
        (df["close"] < df["open"]) &
        (df["close"].shift(1) < df["open"].shift(1)) &
        (df["close"].shift(2) < df["open"].shift(2)) &
        (df["close"] < df["close"].shift(1)) &
        (df["close"].shift(1) < df["close"].shift(2))
    ).astype(float)
    df["rolling_high_20"]  = df["high"].rolling(20).max().shift(1)
    df["rolling_low_20"]   = df["low"].rolling(20).min().shift(1)
    df["rolling_high_100"] = df["high"].rolling(100).max().shift(1)
    df["rolling_low_100"]  = df["low"].rolling(100).min().shift(1)
    df["atr_sma20"]        = df["atr"].rolling(20).mean()
    df["atr_contracted"]   = (df["atr"] < df["atr_sma20"] * 0.6).astype(float)
    df["_date"] = df["timestamp"].dt.date
    df["vwap"]  = (
        df.groupby("_date", group_keys=False)
        .apply(lambda g: (g["close"] * g["volume"]).cumsum() / g["volume"].cumsum())
        .reset_index(level=0, drop=True)
    )
    df = df.drop(columns=["_date"])
    df = _add_htf_4h_columns(df)
    df = _add_htf_1d_columns(df)
    return df


class Strategy1h:
    """Estrategia swing 1h con filtro HTF 1D duro."""

    timeframe = "1h"

    # Veto HTF 1D: si el diario está bajista no hay longs, si está alcista no hay shorts
    _HTF_1D_BLOCKS_LONG  = {"bajista"}
    _HTF_1D_BLOCKS_SHORT = {"alcista"}

    def get_signal(self, df_ltf: pd.DataFrame, live_extras: dict,
                   row=None) -> Signal:
        """Calcula la señal swing.

        df_ltf: DataFrame de velas 1h (precalculadas en backtest o raw en live).
        """
        if row is not None:
            # Modo backtest
            prev_row = df_ltf.iloc[-2] if len(df_ltf) >= 2 else row
            tech     = _analyze_swing(row, prev_row)
            # Régimen desde tendencia 1D
            d_ema20  = row.get("d_ema20")
            d_ema50  = row.get("d_ema50")
        else:
            # Modo live: calcular indicadores 1h sobre la ventana
            df_with_ind = _precompute_1h_indicators(df_ltf)
            last  = df_with_ind.iloc[-1]
            prev  = df_with_ind.iloc[-2] if len(df_with_ind) >= 2 else last
            tech  = _analyze_swing(last, prev)
            d_ema20 = last.get("d_ema20")
            d_ema50 = last.get("d_ema50")

        # Régimen desde EMA 1D
        if (pd.notna(d_ema20) and pd.notna(d_ema50) and d_ema50 > 0):
            if d_ema20 > d_ema50 * 1.002:   regime = "bull"
            elif d_ema20 < d_ema50 * 0.998: regime = "bear"
            else:                            regime = "neutral"
        else:
            regime = "neutral"

        # HTF 1D — veto duro
        htf_1d = tech["details"].get("htf_1d_trend", "lateral")
        htf_blocks_long  = htf_1d in self._HTF_1D_BLOCKS_LONG
        htf_blocks_short = htf_1d in self._HTF_1D_BLOCKS_SHORT

        scores = calculate_scores(
            technical  = tech,
            sentiment  = live_extras.get("sentiment",  {"bullish_score": 0, "bearish_score": 0}),
            fear_greed = live_extras.get("fear_greed", {"bull_mod": 5, "bear_mod": 5}),
            funding    = live_extras.get("funding",    {"bull_mod": 3, "bear_mod": 3}),
            orderbook  = live_extras.get("orderbook",  {"bull_mod": 0, "bear_mod": 0}),
            macro_corr = live_extras.get("macro_corr", {"bull_mod": 0, "bear_mod": 0}),
        )

        tech["trade_type"] = "swing"

        return Signal(
            bull_score       = scores["bullish_total"],
            bear_score       = scores["bearish_total"],
            technical        = tech,
            htf_blocks_long  = htf_blocks_long,
            htf_blocks_short = htf_blocks_short,
            regime           = regime,
        )
