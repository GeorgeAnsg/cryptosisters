"""
bot_indicators.py — Cálculo de indicadores técnicos (v6)
=========================================================
Responsabilidades:
  - precompute_indicators(): precalcula TODO sobre el DataFrame histórico (backtest)
  - compute_indicators(): calcula indicadores en tiempo real sobre una ventana (live)
  - _add_htf_4h_columns(): añade contexto 4h a cada vela 15m
  - _add_htf_1d_columns(): añade tendencia diaria a cada vela 15m/1h
  - _add_1h_pattern_columns(): añade 6 patrones de 1h a cada vela 15m
  - analyze_ltf(): scoring técnico sobre velas LTF (15m)
  - analyze_1h(): scoring técnico sobre velas 1h (para bot swing)
  - fetch_htf_4h_live(): descarga el contexto 4h en modo live
  - fetch_htf_1d_live(): descarga el contexto 1D en modo live
  - is_weekend / is_volatile_session / apply_weekend_filter
  - check_signal_quality

Arquitectura de 3 capas (v6):
  HTF (4h/1D) → permiso direccional (veto duro en la estrategia)
  MTF (1h)    → identificar zona de entrada (para bot swing)
  LTF (15m)   → trigger exacto de entrada
"""

import numpy as np
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from typing import Optional


# =============================================================================
# CAPA HTF: COLUMNAS 4H
# =============================================================================

def _add_htf_4h_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Resamplea 15m → 4h y une el contexto HTF a cada vela LTF via merge_asof.
    Cada vela 15m ve la ÚLTIMA vela 4h completada (direction=backward)."""
    df_4h = (
        df.set_index("timestamp")
        .resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
        .reset_index()
    )
    df_4h["ema_9_4h"]  = ta.ema(df_4h["close"], length=9)
    df_4h["ema_21_4h"] = ta.ema(df_4h["close"], length=21)
    df_4h["ema_50_4h"] = ta.ema(df_4h["close"], length=50)
    df_4h["rsi_4h"]    = ta.rsi(df_4h["close"], length=14)
    macd_4h = ta.macd(df_4h["close"], fast=12, slow=26, signal=9)
    if macd_4h is not None and "MACDh_12_26_9" in macd_4h.columns:
        df_4h["macd_hist_4h"] = macd_4h["MACDh_12_26_9"].values

    # Market Structure 4h: HH+HL (alcista) vs LH+LL (bajista) en ventana de 20 velas 4h (~3.3 días)
    _w4 = 20
    _4h_curr_h = df_4h["high"].rolling(_w4).max()
    _4h_prev_h = df_4h["high"].rolling(_w4).max().shift(_w4)
    _4h_curr_l = df_4h["low"].rolling(_w4).min()
    _4h_prev_l = df_4h["low"].rolling(_w4).min().shift(_w4)
    df_4h["ms_bull_4h"] = ((_4h_curr_h > _4h_prev_h) & (_4h_curr_l > _4h_prev_l)).astype(float)
    df_4h["ms_bear_4h"] = ((_4h_curr_h < _4h_prev_h) & (_4h_curr_l < _4h_prev_l)).astype(float)

    # Patrones de velas 4h: engulfing + hammer/shooting star
    _body_4h  = (df_4h["close"] - df_4h["open"]).abs()
    _lwick_4h = df_4h[["close", "open"]].min(axis=1) - df_4h["low"]
    _uwick_4h = df_4h["high"] - df_4h[["close", "open"]].max(axis=1)
    df_4h["bull_engulf_4h"] = (
        (df_4h["close"] > df_4h["open"]) &
        (df_4h["open"]  < df_4h["close"].shift(1)) &
        (df_4h["close"] > df_4h["open"].shift(1))
    ).astype(float)
    df_4h["bear_engulf_4h"] = (
        (df_4h["close"] < df_4h["open"]) &
        (df_4h["open"]  > df_4h["close"].shift(1)) &
        (df_4h["close"] < df_4h["open"].shift(1))
    ).astype(float)
    df_4h["hammer_4h"] = (
        (_lwick_4h > 2 * _body_4h.clip(lower=0.0001)) &
        (_uwick_4h < _body_4h) &
        ((df_4h["high"] - df_4h["low"]) > 0)
    ).astype(float)
    df_4h["shooting_star_4h"] = (
        (_uwick_4h > 2 * _body_4h.clip(lower=0.0001)) &
        (_lwick_4h < _body_4h) &
        ((df_4h["high"] - df_4h["low"]) > 0)
    ).astype(float)

    htf_cols = ["timestamp", "ema_9_4h", "ema_21_4h", "ema_50_4h", "rsi_4h",
                "ms_bull_4h", "ms_bear_4h",
                "bull_engulf_4h", "bear_engulf_4h", "hammer_4h", "shooting_star_4h"]
    if "macd_hist_4h" in df_4h.columns:
        htf_cols.append("macd_hist_4h")

    return pd.merge_asof(
        df.sort_values("timestamp"),
        df_4h[htf_cols].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )


# =============================================================================
# CAPA HTF: COLUMNAS 1D
# =============================================================================

def _add_htf_1d_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Añade EMA20/EMA50/EMA100 diarias para detección de tendencia diaria.
    d_ema100 es usada exclusivamente por el veto compuesto (requiere tendencia sostenida)."""
    daily = df.set_index("timestamp").resample("D")["close"].last().dropna().to_frame()
    daily["d_ema20"]  = ta.ema(daily["close"], length=20)
    daily["d_ema50"]  = ta.ema(daily["close"], length=50)
    daily["d_ema100"] = ta.ema(daily["close"], length=100)
    daily = daily[["d_ema20", "d_ema50", "d_ema100"]].reset_index()
    return pd.merge_asof(
        df.sort_values("timestamp"),
        daily.sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )


# =============================================================================
# CAPA MTF: PATRONES 1H
# =============================================================================

def _add_1h_pattern_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Resamplea 15m → 1h, calcula 6 patrones y une al LTF via merge_asof.

    Patrones calculados:
      rsi_div_1h       : 'bullish' / 'bearish' / None
      double_top_1h    : 1/0
      double_bottom_1h : 1/0
      flag_1h          : 'bull' / 'bear' / None
      sr_retest_1h     : 'bullish' / 'bearish' / None
      vwap_cross_1h    : 'bullish' / 'bearish' / None
      fvg_1h           : 'bullish' / 'bearish' / None
    """
    df_1h = (
        df.set_index("timestamp")
        .resample("1h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
        .reset_index()
    )
    df_1h["rsi_1h"]    = ta.rsi(df_1h["close"], length=14)
    df_1h["atr_1h"]   = ta.atr(df_1h["high"], df_1h["low"], df_1h["close"], length=14)
    df_1h["ema_9_1h"]  = ta.ema(df_1h["close"], length=9)
    df_1h["ema_21_1h"] = ta.ema(df_1h["close"], length=21)
    df_1h["ema_50_1h"] = ta.ema(df_1h["close"], length=50)
    df_1h["_date"]  = df_1h["timestamp"].dt.date
    df_1h["vwap_1h"] = (
        df_1h.groupby("_date", group_keys=False)
        .apply(lambda g: (g["close"] * g["volume"]).cumsum() / g["volume"].cumsum())
        .reset_index(level=0, drop=True)
    )
    df_1h = df_1h.drop(columns=["_date"])

    n          = len(df_1h)
    rsi_div    = [None] * n
    dbl_top    = np.zeros(n)
    dbl_bot    = np.zeros(n)
    flag_sig   = [None] * n
    sr_ret     = [None] * n
    vwap_cross = [None] * n
    fvg_sig    = [None] * n

    hi   = df_1h["high"].values
    lo   = df_1h["low"].values
    cl   = df_1h["close"].values
    rsi  = df_1h["rsi_1h"].values
    atr  = df_1h["atr_1h"].values
    vwap = df_1h["vwap_1h"].values

    for i in range(30, n):
        # 1. Divergencia RSI (ventana 20 velas)
        w       = 20
        seg_hi  = hi[i-w:i+1]
        seg_lo  = lo[i-w:i+1]
        seg_rsi = rsi[i-w:i+1]
        ph_idx  = [k for k in range(1, w) if seg_hi[k] > seg_hi[k-1] and seg_hi[k] > seg_hi[k+1]]
        pl_idx  = [k for k in range(1, w) if seg_lo[k] < seg_lo[k-1] and seg_lo[k] < seg_lo[k+1]]
        if len(ph_idx) >= 2 and not any(np.isnan(seg_rsi[ph_idx[-2:]])):
            p1, p2 = ph_idx[-2], ph_idx[-1]
            if seg_hi[p2] > seg_hi[p1] and seg_rsi[p2] < seg_rsi[p1] - 3:
                rsi_div[i] = "bearish"
        if len(pl_idx) >= 2 and not any(np.isnan(seg_rsi[pl_idx[-2:]])):
            p1, p2 = pl_idx[-2], pl_idx[-1]
            if seg_lo[p2] < seg_lo[p1] and seg_rsi[p2] > seg_rsi[p1] + 3:
                rsi_div[i] = "bullish"

        # 2. Doble techo / Doble suelo (ventana 40 velas)
        lb     = 40
        start  = max(0, i - lb)
        seg_h2 = hi[start:i+1]
        seg_l2 = lo[start:i+1]
        at     = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else 0
        phs    = [k for k in range(1, len(seg_h2)-1)
                  if seg_h2[k] >= seg_h2[k-1] and seg_h2[k] >= seg_h2[k+1]]
        pls    = [k for k in range(1, len(seg_l2)-1)
                  if seg_l2[k] <= seg_l2[k-1] and seg_l2[k] <= seg_l2[k+1]]
        if len(phs) >= 2 and at > 0:
            j1, j2 = phs[-2], phs[-1]
            if (j2 - j1) >= 4 and abs(seg_h2[j2] - seg_h2[j1]) / seg_h2[j1] < 0.015:
                valley = seg_l2[j1:j2+1].min()
                if (seg_h2[j2] - valley) > 2 * at:
                    dbl_top[i] = 1
        if len(pls) >= 2 and at > 0:
            j1, j2 = pls[-2], pls[-1]
            if (j2 - j1) >= 4 and abs(seg_l2[j2] - seg_l2[j1]) / seg_l2[j1] < 0.015:
                peak = seg_h2[j1:j2+1].max()
                if (peak - seg_l2[j2]) > 2 * at:
                    dbl_bot[i] = 1

        # 3. Bull/Bear flag (mástil 5 velas + consolidación 3 velas)
        if i >= 8:
            pole  = cl[i-7:i-2]
            flagh = hi[i-2:i+1]
            flagl = lo[i-2:i+1]
            if len(pole) == 5 and pole[0] > 0:
                pole_move  = (pole[-1] - pole[0]) / pole[0] * 100
                flag_range = (flagh.max() - flagl.min()) / cl[i] * 100 if cl[i] > 0 else 99
                if abs(pole_move) >= 2.5 and flag_range < 1.2:
                    flag_sig[i] = "bull" if pole_move > 0 else "bear"

        # 4. Breakout + Retest (S/R de 20 velas, roto en últimas 10, retest ahora)
        if i >= 30:
            sr_window  = hi[i-30:i-10]
            resistance = sr_window.max()
            support    = lo[i-30:i-10].min()
            recent_cl  = cl[i-10:i]
            tol        = cl[i] * 0.005
            if recent_cl.max() > resistance and abs(cl[i] - resistance) < tol:
                sr_ret[i] = "bullish"
            elif recent_cl.min() < support and abs(cl[i] - support) < tol:
                sr_ret[i] = "bearish"

        # 5. Cruce de VWAP
        if i >= 2 and not np.isnan(vwap[i]) and not np.isnan(vwap[i-1]):
            if cl[i-1] < vwap[i-1] and cl[i] > vwap[i]:
                vwap_cross[i] = "bullish"
            elif cl[i-1] > vwap[i-1] and cl[i] < vwap[i]:
                vwap_cross[i] = "bearish"

        # 6. Fair Value Gap
        if i >= 2:
            if hi[i-2] < lo[i]:
                fvg_sig[i] = "bullish"
            elif lo[i-2] > hi[i]:
                fvg_sig[i] = "bearish"

    df_1h["rsi_div_1h"]       = rsi_div
    df_1h["double_top_1h"]    = dbl_top
    df_1h["double_bottom_1h"] = dbl_bot
    df_1h["flag_1h"]          = flag_sig
    df_1h["sr_retest_1h"]     = sr_ret
    df_1h["vwap_cross_1h"]    = vwap_cross
    df_1h["fvg_1h"]           = fvg_sig

    # Market Structure 1h: HH+HL (alcista) vs LH+LL (bajista) en ventana de 20 velas 1h (20h)
    _w1h = 20
    _1h_curr_h = df_1h["high"].rolling(_w1h).max()
    _1h_prev_h = df_1h["high"].rolling(_w1h).max().shift(_w1h)
    _1h_curr_l = df_1h["low"].rolling(_w1h).min()
    _1h_prev_l = df_1h["low"].rolling(_w1h).min().shift(_w1h)
    df_1h["ms_bull_1h"] = ((_1h_curr_h > _1h_prev_h) & (_1h_curr_l > _1h_prev_l)).astype(float)
    df_1h["ms_bear_1h"] = ((_1h_curr_h < _1h_prev_h) & (_1h_curr_l < _1h_prev_l)).astype(float)

    pat_cols = ["timestamp", "rsi_div_1h", "double_top_1h", "double_bottom_1h",
                "flag_1h", "sr_retest_1h", "vwap_cross_1h", "fvg_1h",
                "ms_bull_1h", "ms_bear_1h",
                "ema_9_1h", "ema_21_1h", "ema_50_1h"]
    return pd.merge_asof(
        df.sort_values("timestamp"),
        df_1h[pat_cols].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )


# =============================================================================
# PRECOMPUTE (backtest)
# =============================================================================

def precompute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Precalcula todos los indicadores sobre el DataFrame completo.
    Llamar UNA sola vez antes del loop del backtest."""
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

    df["atr"]       = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["vol_sma"]   = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma"]

    df["body_size"]    = (df["close"] - df["open"]).abs()
    df["upper_wick"]   = df["high"] - df[["close", "open"]].max(axis=1)
    df["lower_wick"]   = df[["close", "open"]].min(axis=1) - df["low"]
    df["candle_range"] = df["high"] - df["low"]

    df["bull_engulf"] = (
        (df["close"] > df["open"]) &
        (df["open"]  < df["close"].shift(1)) &
        (df["close"] > df["open"].shift(1))
    ).astype(float)
    df["bear_engulf"] = (
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
    doji_thr = df["atr"] * 0.1
    df["doji"] = (df["body_size"] < doji_thr).astype(float)
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

    _pn = 5
    df["pivot_high"] = df["high"].rolling(2*_pn+1, center=True).apply(
        lambda x: float(x[_pn] == x.max()), raw=True).fillna(0)
    df["pivot_low"] = df["low"].rolling(2*_pn+1, center=True).apply(
        lambda x: float(x[_pn] == x.min()), raw=True).fillna(0)

    _ph  = df["pivot_high"].values.astype(bool)
    _pl  = df["pivot_low"].values.astype(bool)
    _hi  = df["high"].values
    _lo  = df["low"].values
    _at  = df["atr"].values
    _lb  = 100
    _dt  = np.zeros(len(df))
    _db  = np.zeros(len(df))
    _ph_idx = np.where(_ph)[0]
    _pl_idx = np.where(_pl)[0]
    for _i in _ph_idx:
        if _i < _lb: continue
        _ch = _hi[_i]; _a = _at[_i]
        if _a == 0 or np.isnan(_a): continue
        _cands = _ph_idx[(_ph_idx >= _i - _lb) & (_ph_idx < _i - _pn)]
        for _j in _cands[::-1]:
            if abs(_hi[_j] - _ch) / _ch < 0.015:
                if (_ch - _lo[_j:_i+1].min()) > 2 * _a:
                    _dt[_i] = 1; break
    for _i in _pl_idx:
        if _i < _lb: continue
        _cl = _lo[_i]; _a = _at[_i]
        if _a == 0 or np.isnan(_a): continue
        _cands = _pl_idx[(_pl_idx >= _i - _lb) & (_pl_idx < _i - _pn)]
        for _j in _cands[::-1]:
            if abs(_lo[_j] - _cl) / _cl < 0.015:
                if (_hi[_j:_i+1].max() - _cl) > 2 * _a:
                    _db[_i] = 1; break
    df["double_top"]    = _dt
    df["double_bottom"] = _db

    _cw = 40
    df["ch_top"] = df["high"].rolling(_cw).max()
    df["ch_bot"] = df["low"].rolling(_cw).min()
    _ch_valid = (df["ch_top"] - df["ch_bot"]) > df["atr"]
    df["near_channel_top"] = ((df["close"] >= df["ch_top"] - 0.5 * df["atr"]) & _ch_valid).astype(float)
    df["near_channel_bot"] = ((df["close"] <= df["ch_bot"] + 0.5 * df["atr"]) & _ch_valid).astype(float)

    df["atr_sma20"]      = df["atr"].rolling(20).mean()
    df["atr_contracted"] = (df["atr"] < df["atr_sma20"] * 0.6).astype(float)

    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx_df is not None:
        df["adx"]     = adx_df.get("ADX_14", pd.Series(dtype=float))
        df["adx_dmp"] = adx_df.get("DMP_14", pd.Series(dtype=float))
        df["adx_dmn"] = adx_df.get("DMN_14", pd.Series(dtype=float))

    # StochRSI — más sensible que RSI, capta giros antes en intraday
    _srsi = ta.stochrsi(df["close"], length=14, rsi_length=14, k=3, d=3)
    if _srsi is not None:
        df["stochrsi_k"] = _srsi.get("STOCHRSIk_14_14_3_3", pd.Series(dtype=float))
        df["stochrsi_d"] = _srsi.get("STOCHRSId_14_14_3_3", pd.Series(dtype=float))

    # Market Structure — HH+HL (alcista) vs LH+LL (bajista) usando ventana de 48 velas (12h)
    # Información diferente a EMAs: basada en pivots reales, no precio suavizado.
    # 48 velas = 12h en 15m → suficiente para filtrar ruido intraday sin retrasar la señal.
    _w = 48
    _curr_h = df["high"].rolling(_w).max()
    _prev_h = df["high"].rolling(_w).max().shift(_w)
    _curr_l = df["low"].rolling(_w).min()
    _prev_l = df["low"].rolling(_w).min().shift(_w)
    df["ms_bull"] = ((_curr_h > _prev_h) & (_curr_l > _prev_l)).astype(float)
    df["ms_bear"] = ((_curr_h < _prev_h) & (_curr_l < _prev_l)).astype(float)

    df["_date"] = df["timestamp"].dt.date
    df["vwap"]  = (
        df.groupby("_date", group_keys=False)
        .apply(lambda g: (g["close"] * g["volume"]).cumsum() / g["volume"].cumsum())
        .reset_index(level=0, drop=True)
    )
    df = df.drop(columns=["_date"])

    # Hurst Exponent proxy — autocorrelación lag-1 de log-returns en ventana 100 velas
    # acf1 > 0: mercado tendencial (momentum persiste)
    # acf1 < 0: mean-reverting (rebota al promedio)
    _logret = np.log(df["close"] / df["close"].shift(1)).fillna(0)
    df["hurst_acf1"] = _logret.rolling(100, min_periods=50).apply(
        lambda x: float(np.corrcoef(x[:-1], x[1:])[0, 1]),
        raw=True,
    )

    # Volume Profile POC — nivel de precio con mayor volumen en últimas 96 velas (24h)
    _poc_win, _poc_bins = 96, 20
    _cl_v  = df["close"].values
    _hi_v2 = df["high"].values
    _lo_v2 = df["low"].values
    _vl_v  = df["volume"].values
    _tp_v  = (_hi_v2 + _lo_v2 + _cl_v) / 3
    _poc_arr = np.full(len(df), np.nan)
    for _i in range(_poc_win - 1, len(df)):
        _s_lo = _lo_v2[_i - _poc_win + 1:_i + 1].min()
        _s_hi = _hi_v2[_i - _poc_win + 1:_i + 1].max()
        if _s_hi <= _s_lo:
            continue
        _tp_w  = _tp_v[_i - _poc_win + 1:_i + 1]
        _vl_w  = _vl_v[_i - _poc_win + 1:_i + 1]
        _bidx  = np.clip(((_tp_w - _s_lo) / (_s_hi - _s_lo) * _poc_bins).astype(int), 0, _poc_bins - 1)
        _best  = np.argmax(np.bincount(_bidx, weights=_vl_w, minlength=_poc_bins))
        _poc_arr[_i] = _s_lo + (_best + 0.5) * (_s_hi - _s_lo) / _poc_bins
    df["poc"] = _poc_arr

    # CUSUM Filter (Lopez de Prado, 2018) — acumula returns y señala solo cuando
    # el acumulado supera 0.5×ATR normalizado. Evita entrar en ruido intraday.
    # cusum_state: +1 = momentum alcista acumulado, -1 = bajista, 0 = neutral
    _cl_c  = df["close"].values
    _atr_c = df["atr"].fillna(0).values
    _cusum_state = np.zeros(len(df))
    _s_up = 0.0; _s_dn = 0.0; _cstate = 0
    for _i in range(1, len(df)):
        if _cl_c[_i - 1] == 0 or _atr_c[_i] == 0:
            _cusum_state[_i] = _cstate
            continue
        _ret = (_cl_c[_i] - _cl_c[_i - 1]) / _cl_c[_i - 1]
        _s_up = max(0.0, _s_up + _ret)
        _s_dn = min(0.0, _s_dn + _ret)
        _thr  = _atr_c[_i] / _cl_c[_i] * 0.5  # 0.5 ATR normalizado
        if _s_up >= _thr:
            _cstate = 1; _s_up = 0.0; _s_dn = 0.0
        elif _s_dn <= -_thr:
            _cstate = -1; _s_dn = 0.0; _s_up = 0.0
        _cusum_state[_i] = _cstate
    df["cusum_state"] = _cusum_state

    # Capas HTF
    df = _add_htf_4h_columns(df)
    df = _add_1h_pattern_columns(df)
    df = _add_htf_1d_columns(df)

    return df


# =============================================================================
# COMPUTE INDICATORS (live — ventana de velas recientes)
# =============================================================================

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula indicadores sobre una ventana LTF reciente para el modo live.
    Devuelve el mismo df con columnas de indicadores añadidas."""
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
    doji_thr = df["atr"] * 0.1
    df["doji"]       = (df["body_size"] < doji_thr).astype(float)
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
    adx_live = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx_live is not None:
        df["adx"]     = adx_live.get("ADX_14", pd.Series(dtype=float))
        df["adx_dmp"] = adx_live.get("DMP_14", pd.Series(dtype=float))
        df["adx_dmn"] = adx_live.get("DMN_14", pd.Series(dtype=float))
    _srsi_live = ta.stochrsi(df["close"], length=14, rsi_length=14, k=3, d=3)
    if _srsi_live is not None:
        df["stochrsi_k"] = _srsi_live.get("STOCHRSIk_14_14_3_3", pd.Series(dtype=float))
        df["stochrsi_d"] = _srsi_live.get("STOCHRSId_14_14_3_3", pd.Series(dtype=float))
    _w = 48
    _curr_h = df["high"].rolling(_w).max()
    _prev_h = df["high"].rolling(_w).max().shift(_w)
    _curr_l = df["low"].rolling(_w).min()
    _prev_l = df["low"].rolling(_w).min().shift(_w)
    df["ms_bull"] = ((_curr_h > _prev_h) & (_curr_l > _prev_l)).astype(float)
    df["ms_bear"] = ((_curr_h < _prev_h) & (_curr_l < _prev_l)).astype(float)
    df["_date"] = df["timestamp"].dt.date
    df["vwap"]  = (
        df.groupby("_date", group_keys=False)
        .apply(lambda g: (g["close"] * g["volume"]).cumsum() / g["volume"].cumsum())
        .reset_index(level=0, drop=True)
    )
    df = df.drop(columns=["_date"])

    # Capas HTF en live
    df = _add_htf_4h_columns(df)
    df = _add_1h_pattern_columns(df)
    df = _add_htf_1d_columns(df)
    return df


# =============================================================================
# SCORING LTF (15m) — para bot intraday
# =============================================================================

def analyze_ltf(row, prev_row=None) -> dict:
    """Scoring técnico sobre una vela 15m ya pre-calculada.
    Returns {"bullish_score": int, "bearish_score": int, "details": dict}.
    """
    if prev_row is None:
        prev_row = row

    bullish = 0
    bearish = 0
    details = {}

    price = row["close"]
    details["price"] = round(price, 2)

    # RSI (max 10 pts)
    rsi = row.get("rsi", 50)
    if pd.notna(rsi):
        details["rsi"] = round(rsi, 1)
        if rsi < 25: bullish += 10
        elif rsi < 35: bullish += 7
        elif rsi < 45: bullish += 3
        if rsi > 75: bearish += 10
        elif rsi > 65: bearish += 7
        elif rsi > 55: bearish += 3
    else:
        details["rsi"] = 50.0

    # EMAs (max 15 pts)
    e9, e21, e50, e200 = (row.get(k, 0) for k in ("ema_9", "ema_21", "ema_50", "ema_200"))
    if pd.notna(e9) and pd.notna(e21) and pd.notna(e50):
        if e9 > e21 > e50:
            bullish += 12; details["trend"] = "alcista fuerte"
        elif e9 > e21:
            bullish += 7;  details["trend"] = "alcista"
        elif e9 < e21 < e50:
            bearish += 12; details["trend"] = "bajista fuerte"
        elif e9 < e21:
            bearish += 7;  details["trend"] = "bajista"
        else:
            details["trend"] = "lateral"
        if pd.notna(e200):
            if price > e200: bullish += 3; details["above_ema200"] = True
            elif price < e200: bearish += 3; details["above_ema200"] = False
            else: details["above_ema200"] = None
    else:
        details["trend"] = "calculando"

    # MACD (max 10 pts)
    mh  = row.get("MACDh_12_26_9", 0)
    pmh = prev_row.get("MACDh_12_26_9", 0)
    if pd.notna(mh) and pd.notna(pmh):
        if mh > 0 and pmh <= 0:   bullish += 10; details["macd"] = "cruce alcista"
        elif mh > 0 and mh > pmh: bullish += 5;  details["macd"] = "momentum alcista"
        elif mh < 0 and pmh >= 0: bearish += 10; details["macd"] = "cruce bajista"
        elif mh < 0 and mh < pmh: bearish += 5;  details["macd"] = "momentum bajista"
        else:                                     details["macd"] = "neutral"
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
            if bb_pos < 0.3: bullish += 4
            elif bb_pos > 0.7: bearish += 4
            details["bollinger"] = f"pos:{bb_pos:.0%}"
    else:
        details["bollinger"] = "sin datos"

    # Price Action
    atr_pa = row.get("atr", 0)
    body   = row.get("body_size", 0)
    open_p = row.get("open", price)
    if row.get("bull_engulf", 0) > 0.5: bullish += 8; details["pa"] = "engulf alcista"
    elif row.get("bear_engulf", 0) > 0.5: bearish += 8; details["pa"] = "engulf bajista"
    # Hammer/shooting star con filtro RSI: solo válido en zona correcta
    # Hammer en overbought (RSI>60) = ruido; shooting star en oversold (RSI<40) = ruido
    _rsi_pa = row.get("rsi", 50) or 50
    if row.get("hammer", 0) > 0.5 and _rsi_pa < 60:
        bullish += 7; details["pa_vela"] = "hammer"
    elif row.get("shooting_star", 0) > 0.5 and _rsi_pa > 40:
        bearish += 7; details["pa_vela"] = "shooting star"
    if row.get("three_bull", 0) > 0.5: bullish += 6; details["pa_seq"] = "3 alcistas"
    elif row.get("three_bear", 0) > 0.5: bearish += 6; details["pa_seq"] = "3 bajistas"
    if pd.notna(body) and pd.notna(atr_pa) and atr_pa > 0 and body > 1.5 * atr_pa:
        if price > open_p: bullish += 5; details["pa_impulso"] = f"bull {body/atr_pa:.1f}xATR"
        elif price < open_p: bearish += 5; details["pa_impulso"] = f"bear {body/atr_pa:.1f}xATR"

    # S/R breakout
    r20  = row.get("rolling_high_20");  l20  = row.get("rolling_low_20")
    r100 = row.get("rolling_high_100"); l100 = row.get("rolling_low_100")
    if r100 is not None and pd.notna(r100) and price > r100:
        bullish += 5; details["sr_break"] = "resist diaria rota"
    elif l100 is not None and pd.notna(l100) and price < l100:
        bearish += 5; details["sr_break"] = "soporte diario roto"
    elif r20 is not None and pd.notna(r20) and price > r20:
        bullish += 4; details["sr_break"] = "resist 5h rota"
    elif l20 is not None and pd.notna(l20) and price < l20:
        bearish += 4; details["sr_break"] = "soporte 5h roto"

    # Consolidación ATR
    details["consolidacion"] = bool(row.get("atr_contracted", 0) > 0.5)

    # ADX
    adx_val = row.get("adx")
    adx_dmp = row.get("adx_dmp")
    adx_dmn = row.get("adx_dmn")
    if adx_val is not None and pd.notna(adx_val):
        details["adx"] = round(adx_val, 1)
        details["adx_trending"] = adx_val >= 25
    else:
        details["adx_trending"] = True

    # VWAP
    vwap = row.get("vwap")
    if vwap is not None and pd.notna(vwap):
        details["vwap"] = round(vwap, 2)
        details["vwap_bias"] = "sobre VWAP" if price > vwap else "bajo VWAP"
    else:
        details["vwap_bias"] = "sin datos"

    # Tendencia diaria (1D) — scoring L2
    d_ema20 = row.get("d_ema20")
    d_ema50 = row.get("d_ema50")
    if pd.notna(d_ema20) and pd.notna(d_ema50) and d_ema50 > 0:
        if d_ema20 > d_ema50 * 1.002:
            bullish += 6; details["htf_1d_trend"] = "alcista"
        elif d_ema20 < d_ema50 * 0.998:
            bearish += 6; details["htf_1d_trend"] = "bajista"
        else:
            details["htf_1d_trend"] = "lateral"
    else:
        details["htf_1d_trend"] = "calculando"

    # HTF 4h — scoring activo
    e9_4h  = row.get("ema_9_4h")
    e21_4h = row.get("ema_21_4h")
    e50_4h = row.get("ema_50_4h")
    rsi_4h = row.get("rsi_4h")
    mh_4h  = row.get("macd_hist_4h")
    if pd.notna(e9_4h) and pd.notna(e21_4h) and pd.notna(e50_4h):
        if e9_4h > e21_4h > e50_4h:
            bullish += 8; details["htf_trend"] = "alcista"
        elif e9_4h > e21_4h:
            bullish += 4; details["htf_trend"] = "alcista parcial"
        elif e9_4h < e21_4h < e50_4h:
            bearish += 8; details["htf_trend"] = "bajista"
        elif e9_4h < e21_4h:
            bearish += 4; details["htf_trend"] = "bajista parcial"
        else:
            details["htf_trend"] = "lateral"
    else:
        details["htf_trend"] = "calculando"
    if mh_4h is not None and pd.notna(mh_4h):
        details["htf_macd"] = "alcista" if mh_4h > 0 else "bajista"
        if mh_4h > 0: bullish += 4
        else: bearish += 4
    if rsi_4h is not None and pd.notna(rsi_4h):
        details["htf_rsi"] = round(rsi_4h, 1)
        if rsi_4h < 40: bullish += 3
        elif rsi_4h > 60: bearish += 3

    # 4h Market Structure (L2) — HH+HL vs LH+LL en ventana de 80h (3.3 días)
    if row.get("ms_bull_4h", 0) > 0.5:
        bullish += 6; details["ms_4h"] = "HH+HL alcista 4h"
    elif row.get("ms_bear_4h", 0) > 0.5:
        bearish += 6; details["ms_4h"] = "LH+LL bajista 4h"
    else:
        details["ms_4h"] = "sin estructura 4h"

    # Patrones de velas 4h (L2) — engulfing=7pts, hammer/SS=5pts
    if row.get("bull_engulf_4h", 0) > 0.5:
        bullish += 7; details["pa_4h"] = "engulf alcista 4h"
    elif row.get("bear_engulf_4h", 0) > 0.5:
        bearish += 7; details["pa_4h"] = "engulf bajista 4h"
    elif row.get("hammer_4h", 0) > 0.5:
        bullish += 5; details["pa_4h"] = "hammer 4h"
    elif row.get("shooting_star_4h", 0) > 0.5:
        bearish += 5; details["pa_4h"] = "shooting star 4h"

    # Tendencia diaria sostenida (para veto compuesto) — d_ema50 vs d_ema100
    # Requiere meses de tendencia establecida, no simples correcciones de 2-3 semanas
    d_ema100 = row.get("d_ema100")
    if pd.notna(d_ema50) and pd.notna(d_ema100) and d_ema100 > 0:
        if d_ema50 > d_ema100 * 1.001:   details["htf_1d_strong"] = "alcista"
        elif d_ema50 < d_ema100 * 0.999: details["htf_1d_strong"] = "bajista"
        else:                             details["htf_1d_strong"] = "lateral"
    else:
        details["htf_1d_strong"] = "calculando"

    # Patrones 1h
    if row.get("double_top_1h", 0):    bearish += 8; details["pattern"] = "doble_techo_1h"
    elif row.get("double_bottom_1h", 0): bullish += 8; details["pattern"] = "doble_suelo_1h"
    rsi_div = row.get("rsi_div_1h")
    if rsi_div == "bearish":   bearish += 9; details["rsi_div"] = "div_bajista_1h"
    elif rsi_div == "bullish": bullish += 9; details["rsi_div"] = "div_alcista_1h"
    flag = row.get("flag_1h")
    if flag == "bull":   bullish += 7; details["flag"] = "bull_flag_1h"
    elif flag == "bear": bearish += 7; details["flag"] = "bear_flag_1h"
    sr_ret = row.get("sr_retest_1h")
    if sr_ret == "bullish":   bullish += 7; details["sr_retest"] = "retest_alcista_1h"
    elif sr_ret == "bearish": bearish += 7; details["sr_retest"] = "retest_bajista_1h"
    vwap_cross = row.get("vwap_cross_1h")
    if vwap_cross == "bullish":   bullish += 6; details["vwap_cross"] = "reclaim_1h"
    elif vwap_cross == "bearish": bearish += 6; details["vwap_cross"] = "ruptura_1h"
    fvg = row.get("fvg_1h")
    if fvg == "bullish":   bullish += 5; details["fvg"] = "fvg_alcista_1h"
    elif fvg == "bearish": bearish += 5; details["fvg"] = "fvg_bajista_1h"

    # 1h Market Structure (L2) — cadena completa 15m → 1h → 4h → 1D
    if row.get("ms_bull_1h", 0) > 0.5:
        bullish += 5; details["ms_1h"] = "HH+HL alcista 1h"
    elif row.get("ms_bear_1h", 0) > 0.5:
        bearish += 5; details["ms_1h"] = "LH+LL bajista 1h"

    # Canal de precio
    if row.get("near_channel_bot", 0): bullish += 5; details["channel"] = "soporte_canal"
    elif row.get("near_channel_top", 0): bearish += 5; details["channel"] = "resistencia_canal"

    # Volumen (confirmación, max 7 pts)
    vol_ratio = row.get("vol_ratio", 1.0)
    if pd.notna(vol_ratio):
        details["vol_ratio"] = round(vol_ratio, 2)
        if vol_ratio > 2.0:
            if bullish > bearish: bullish += 7
            elif bearish > bullish: bearish += 7
        elif vol_ratio > 1.3:
            if bullish > bearish: bullish += 3
            elif bearish > bullish: bearish += 3
    else:
        details["vol_ratio"] = 1.0

    # ADX — scoring activo (ya calculado, hasta ahora solo metadata)
    adx_val = row.get("adx")
    adx_dmp = row.get("adx_dmp")   # +DI
    adx_dmn = row.get("adx_dmn")   # -DI
    if adx_val is not None and pd.notna(adx_val) and adx_val >= 25:
        # Tendencia real: potencia las señales EMA/MACD
        if adx_dmp is not None and adx_dmn is not None and pd.notna(adx_dmp) and pd.notna(adx_dmn):
            if adx_dmp > adx_dmn:
                bullish += 5; details["adx"] = f"trend_bull {adx_val:.0f}"
            else:
                bearish += 5; details["adx"] = f"trend_bear {adx_val:.0f}"
        else:
            details["adx"] = f"trend {adx_val:.0f}"
    else:
        details["adx"] = f"lateral {adx_val:.0f}" if adx_val is not None and pd.notna(adx_val) else "sin datos"

    # VWAP — scoring activo
    vwap = row.get("vwap")
    if vwap is not None and pd.notna(vwap) and vwap > 0:
        details["vwap"] = round(vwap, 2)
        gap_pct = (price - vwap) / vwap
        if gap_pct > 0.002:
            bullish += 4; details["vwap_bias"] = f"sobre VWAP +{gap_pct:.1%}"
        elif gap_pct < -0.002:
            bearish += 4; details["vwap_bias"] = f"bajo VWAP {gap_pct:.1%}"
        else:
            details["vwap_bias"] = "en VWAP"
    else:
        details["vwap_bias"] = "sin datos"

    # Hurst Exponent proxy (max 5 pts) — tendencial vs mean-reverting
    _hurst_ltf = row.get("hurst_acf1")
    if _hurst_ltf is not None and pd.notna(_hurst_ltf):
        if _hurst_ltf > 0.15:
            if bullish > bearish:   bullish += 5
            elif bearish > bullish: bearish += 5
            details["hurst"] = f"tendencial {_hurst_ltf:.2f}"
        elif _hurst_ltf < -0.10:
            if bullish > bearish:   bearish += 3
            elif bearish > bullish: bullish += 3
            details["hurst"] = f"mean_rev {_hurst_ltf:.2f}"
        else:
            details["hurst"] = f"neutral {_hurst_ltf:.2f}"

    # Volume Profile POC (max 4 pts) — zona de mayor volumen = soporte/resistencia
    _poc_ltf = row.get("poc")
    _atr_ltf = row.get("atr", 0) or 0
    if _poc_ltf is not None and pd.notna(_poc_ltf) and _atr_ltf > 0:
        _poc_dist_ltf = (price - _poc_ltf) / _atr_ltf
        if abs(_poc_dist_ltf) < 0.3:
            details["poc"] = f"en_POC {_poc_ltf:.0f}"
        elif _poc_dist_ltf > 0.3:
            bullish += 4; details["poc"] = f"sobre_POC {_poc_ltf:.0f} (+{_poc_dist_ltf:.1f}ATR)"
        else:
            bearish += 4; details["poc"] = f"bajo_POC {_poc_ltf:.0f} ({_poc_dist_ltf:.1f}ATR)"

    # StochRSI (max 6 pts) — con filtro ADX: en tendencia fuerte, extremos = continuación
    _sk  = row.get("stochrsi_k");      _sd  = row.get("stochrsi_d")
    _psk = prev_row.get("stochrsi_k"); _psd = prev_row.get("stochrsi_d")
    _adx_v = row.get("adx"); _dmp_v = row.get("adx_dmp"); _dmn_v = row.get("adx_dmn")
    _trending_ltf = (_adx_v is not None and pd.notna(_adx_v) and _adx_v >= 25
                     and _dmp_v is not None and _dmn_v is not None
                     and pd.notna(_dmp_v) and pd.notna(_dmn_v))
    _bull_trend_ltf = _trending_ltf and _dmp_v > _dmn_v
    _bear_trend_ltf = _trending_ltf and _dmn_v > _dmp_v
    if _sk is not None and _sd is not None and pd.notna(_sk) and pd.notna(_sd):
        if _sk < 20 and _sd < 20:
            bullish += 2 if _bear_trend_ltf else 6
            details["stochrsi"] = f"oversold {_sk:.0f}" + (" (bear)" if _bear_trend_ltf else "")
        elif _sk > 80 and _sd > 80:
            bearish += 2 if _bull_trend_ltf else 6
            details["stochrsi"] = f"overbought {_sk:.0f}" + (" (bull)" if _bull_trend_ltf else "")
        elif (_psk is not None and pd.notna(_psk) and pd.notna(_psd)
              and _sk < 50 and _sk > _sd and _psk <= _psd):
            bullish += 3; details["stochrsi"] = f"cruce alcista {_sk:.0f}"
        elif (_psk is not None and pd.notna(_psk) and pd.notna(_psd)
              and _sk > 50 and _sk < _sd and _psk >= _psd):
            bearish += 3; details["stochrsi"] = f"cruce bajista {_sk:.0f}"
        else:
            details["stochrsi"] = f"neutro {_sk:.0f}"

    # Market Structure (max 8 pts) — HH+HL = alcista, LH+LL = bajista
    if row.get("ms_bull", 0) > 0.5:
        bullish += 8; details["ms"] = "HH+HL alcista"
    elif row.get("ms_bear", 0) > 0.5:
        bearish += 8; details["ms"] = "LH+LL bajista"

    # Doji contextual (max 3 pts) — solo cerca de BB extremo o S/R con volumen
    if row.get("doji", 0) > 0.5 and pd.notna(vol_ratio) and vol_ratio >= 1.0:
        _atr_d = atr_pa if pd.notna(atr_pa) and atr_pa > 0 else 0
        _bbl_d = row.get("BBL_20_2.0"); _bbu_d = row.get("BBU_20_2.0")
        _r20_d = row.get("rolling_high_20"); _l20_d = row.get("rolling_low_20")
        _near_bbl = _bbl_d is not None and pd.notna(_bbl_d) and price <= _bbl_d + _atr_d * 0.5
        _near_bbu = _bbu_d is not None and pd.notna(_bbu_d) and price >= _bbu_d - _atr_d * 0.5
        _near_sup = _l20_d is not None and pd.notna(_l20_d) and abs(price - _l20_d) < _atr_d * 0.5
        _near_res = _r20_d is not None and pd.notna(_r20_d) and abs(price - _r20_d) < _atr_d * 0.5
        if _near_bbl or _near_sup:
            bullish += 3; details["doji_ctx"] = "doji en soporte"
        elif _near_bbu or _near_res:
            bearish += 3; details["doji_ctx"] = "doji en resistencia"

    details["atr"] = round(atr_pa, 2) if pd.notna(atr_pa) else 0

    return {
        "bullish_score": min(50, bullish),
        "bearish_score": min(50, bearish),
        "details":       details,
        "bbl":           row.get("BBL_20_2.0"),
        "bbu":           row.get("BBU_20_2.0"),
    }


def analyze_layer1(row, prev_row=None) -> dict:
    """Scoring técnico PURO de 15m — sin HTF 4h, sin patrones 1h.
    Usado para el backtest de capa 1 aislada.
    """
    if prev_row is None:
        prev_row = row

    bullish = 0
    bearish = 0
    details = {}
    price   = row["close"]
    details["price"] = round(price, 2)

    # RSI (max 10 pts)
    rsi = row.get("rsi", 50)
    if pd.notna(rsi):
        details["rsi"] = round(rsi, 1)
        if rsi < 25:   bullish += 10
        elif rsi < 35: bullish += 7
        elif rsi < 45: bullish += 3
        if rsi > 75:   bearish += 10
        elif rsi > 65: bearish += 7
        elif rsi > 55: bearish += 3
    else:
        details["rsi"] = 50.0

    # EMAs 15m (max 15 pts)
    e9, e21, e50, e200 = (row.get(k, 0) for k in ("ema_9", "ema_21", "ema_50", "ema_200"))
    if pd.notna(e9) and pd.notna(e21) and pd.notna(e50):
        if e9 > e21 > e50:   bullish += 12; details["trend"] = "alcista fuerte"
        elif e9 > e21:       bullish += 7;  details["trend"] = "alcista"
        elif e9 < e21 < e50: bearish += 12; details["trend"] = "bajista fuerte"
        elif e9 < e21:       bearish += 7;  details["trend"] = "bajista"
        else:                               details["trend"] = "lateral"
        if pd.notna(e200):
            if price > e200:   bullish += 3; details["above_ema200"] = True
            elif price < e200: bearish += 3; details["above_ema200"] = False
    else:
        details["trend"] = "calculando"

    # MACD (max 10 pts)
    mh  = row.get("MACDh_12_26_9", 0)
    pmh = prev_row.get("MACDh_12_26_9", 0)
    if pd.notna(mh) and pd.notna(pmh):
        if mh > 0 and pmh <= 0:   bullish += 10; details["macd"] = "cruce alcista"
        elif mh > 0 and mh > pmh: bullish += 5;  details["macd"] = "momentum alcista"
        elif mh < 0 and pmh >= 0: bearish += 10; details["macd"] = "cruce bajista"
        elif mh < 0 and mh < pmh: bearish += 5;  details["macd"] = "momentum bajista"
        else:                                     details["macd"] = "neutral"
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
            if bb_pos < 0.3:   bullish += 4
            elif bb_pos > 0.7: bearish += 4
            details["bollinger"] = f"pos:{bb_pos:.0%}"
    else:
        details["bollinger"] = "sin datos"

    # Price Action (max 26 pts)
    atr_pa = row.get("atr", 0)
    body   = row.get("body_size", 0)
    open_p = row.get("open", price)
    if row.get("bull_engulf", 0) > 0.5: bullish += 8; details["pa"] = "engulf alcista"
    elif row.get("bear_engulf", 0) > 0.5: bearish += 8; details["pa"] = "engulf bajista"
    _rsi_pa = row.get("rsi", 50) or 50
    if row.get("hammer", 0) > 0.5 and _rsi_pa < 60:
        bullish += 7; details["pa_vela"] = "hammer"
    elif row.get("shooting_star", 0) > 0.5 and _rsi_pa > 40:
        bearish += 7; details["pa_vela"] = "shooting star"
    if row.get("three_bull", 0) > 0.5: bullish += 6; details["pa_seq"] = "3 alcistas"
    elif row.get("three_bear", 0) > 0.5: bearish += 6; details["pa_seq"] = "3 bajistas"
    if pd.notna(body) and pd.notna(atr_pa) and atr_pa > 0 and body > 1.5 * atr_pa:
        if price > open_p:   bullish += 5; details["pa_impulso"] = f"bull {body/atr_pa:.1f}xATR"
        elif price < open_p: bearish += 5; details["pa_impulso"] = f"bear {body/atr_pa:.1f}xATR"

    # S/R breakout (max 5 pts)
    r20  = row.get("rolling_high_20");  l20  = row.get("rolling_low_20")
    r100 = row.get("rolling_high_100"); l100 = row.get("rolling_low_100")
    if r100 is not None and pd.notna(r100) and price > r100:
        bullish += 5; details["sr_break"] = "resist diaria rota"
    elif l100 is not None and pd.notna(l100) and price < l100:
        bearish += 5; details["sr_break"] = "soporte diario roto"
    elif r20 is not None and pd.notna(r20) and price > r20:
        bullish += 4; details["sr_break"] = "resist 5h rota"
    elif l20 is not None and pd.notna(l20) and price < l20:
        bearish += 4; details["sr_break"] = "soporte 5h roto"

    # ADX — scoring (max 5 pts)
    adx_val = row.get("adx")
    adx_dmp = row.get("adx_dmp")
    adx_dmn = row.get("adx_dmn")
    if adx_val is not None and pd.notna(adx_val) and adx_val >= 25:
        if adx_dmp is not None and adx_dmn is not None and pd.notna(adx_dmp) and pd.notna(adx_dmn):
            if adx_dmp > adx_dmn:
                bullish += 5; details["adx"] = f"trend_bull {adx_val:.0f}"
            else:
                bearish += 5; details["adx"] = f"trend_bear {adx_val:.0f}"
        else:
            details["adx"] = f"trend {adx_val:.0f}"
    else:
        details["adx"] = f"lateral {adx_val:.0f}" if adx_val is not None and pd.notna(adx_val) else "sin datos"

    # VWAP — scoring (max 4 pts)
    vwap = row.get("vwap")
    if vwap is not None and pd.notna(vwap) and vwap > 0:
        gap_pct = (price - vwap) / vwap
        if gap_pct > 0.002:    bullish += 4; details["vwap_bias"] = f"sobre VWAP +{gap_pct:.1%}"
        elif gap_pct < -0.002: bearish += 4; details["vwap_bias"] = f"bajo VWAP {gap_pct:.1%}"
        else:                               details["vwap_bias"] = "en VWAP"
    else:
        details["vwap_bias"] = "sin datos"

    # Hurst Exponent proxy (max 5 pts) — tendencial vs mean-reverting
    _hurst = row.get("hurst_acf1")
    if _hurst is not None and pd.notna(_hurst):
        if _hurst > 0.15:    # tendencial: refuerza la señal dominante
            if bullish > bearish:   bullish += 5
            elif bearish > bullish: bearish += 5
            details["hurst"] = f"tendencial {_hurst:.2f}"
        elif _hurst < -0.10: # mean-reverting: favorece la señal contraria
            if bullish > bearish:   bearish += 3
            elif bearish > bullish: bullish += 3
            details["hurst"] = f"mean_rev {_hurst:.2f}"
        else:
            details["hurst"] = f"neutral {_hurst:.2f}"

    # Volume Profile POC (max 4 pts) — zona de mayor volumen = soporte/resistencia
    _poc = row.get("poc")
    _atr_poc = atr_pa or 0
    if _poc is not None and pd.notna(_poc) and _atr_poc > 0:
        _poc_dist = (price - _poc) / _atr_poc
        if abs(_poc_dist) < 0.3:
            details["poc"] = f"en_POC {_poc:.0f}"
        elif _poc_dist > 0.3:
            bullish += 4; details["poc"] = f"sobre_POC {_poc:.0f} (+{_poc_dist:.1f}ATR)"
        else:
            bearish += 4; details["poc"] = f"bajo_POC {_poc:.0f} ({_poc_dist:.1f}ATR)"

    # Volumen (max 7 pts)
    vol_ratio = row.get("vol_ratio", 1.0)
    if pd.notna(vol_ratio):
        details["vol_ratio"] = round(vol_ratio, 2)
        if vol_ratio > 2.0:
            if bullish > bearish: bullish += 7
            elif bearish > bullish: bearish += 7
        elif vol_ratio > 1.3:
            if bullish > bearish: bullish += 3
            elif bearish > bullish: bearish += 3

    # StochRSI (max 6 pts) — capta giros antes que RSI plano, estándar intraday
    # IMPORTANTE: en mercados tendenciales (ADX ≥ 25), los extremos overbought/oversold
    # significan CONTINUACIÓN, no reversión. Solo usarlos como señal contraria en ranging.
    sk  = row.get("stochrsi_k");      sd  = row.get("stochrsi_d")
    psk = prev_row.get("stochrsi_k"); psd = prev_row.get("stochrsi_d")
    _adx_val = row.get("adx");  _dmp = row.get("adx_dmp"); _dmn = row.get("adx_dmn")
    _trending = (_adx_val is not None and pd.notna(_adx_val) and _adx_val >= 25
                 and _dmp is not None and _dmn is not None
                 and pd.notna(_dmp) and pd.notna(_dmn))
    _trend_is_bull = _trending and _dmp > _dmn
    _trend_is_bear = _trending and _dmn > _dmp
    if sk is not None and sd is not None and pd.notna(sk) and pd.notna(sd):
        if sk < 20 and sd < 20:
            # Oversold: señal alcista fuerte SALVO si hay tendencia bajista dominante
            if not _trend_is_bear:
                bullish += 6; details["stochrsi"] = f"oversold {sk:.0f}"
            else:
                # En bear trend, oversold = continuación bajista (pullback breve)
                bullish += 2; details["stochrsi"] = f"oversold en bear {sk:.0f}"
        elif sk > 80 and sd > 80:
            # Overbought: señal bajista fuerte SALVO si hay tendencia alcista dominante
            if not _trend_is_bull:
                bearish += 6; details["stochrsi"] = f"overbought {sk:.0f}"
            else:
                # En bull trend, overbought = continuación (no reversión)
                bearish += 2; details["stochrsi"] = f"overbought en bull {sk:.0f}"
        elif (psk is not None and pd.notna(psk) and pd.notna(psd)
              and sk < 50 and sk > sd and psk <= psd):
            bullish += 3; details["stochrsi"] = f"cruce alcista {sk:.0f}"
        elif (psk is not None and pd.notna(psk) and pd.notna(psd)
              and sk > 50 and sk < sd and psk >= psd):
            bearish += 3; details["stochrsi"] = f"cruce bajista {sk:.0f}"
        else:
            details["stochrsi"] = f"neutro {sk:.0f}"
    else:
        details["stochrsi"] = "sin datos"

    # Market Structure (max 8 pts) — HH+HL = alcista, LH+LL = bajista
    # Diferente de EMAs: mide comportamiento real de pivots, no precio suavizado
    if row.get("ms_bull", 0) > 0.5:
        bullish += 8; details["ms"] = "HH+HL alcista"
    elif row.get("ms_bear", 0) > 0.5:
        bearish += 8; details["ms"] = "LH+LL bajista"
    else:
        details["ms"] = "sin estructura clara"

    # Doji contextual (max 3 pts) — solo útil en extremos con volumen
    # Un doji en zona neutral es ruido puro en 15m; solo cuenta cerca de BB/SR con vol
    if row.get("doji", 0) > 0.5 and pd.notna(vol_ratio) and vol_ratio >= 1.0:
        _atr_ctx = atr_pa if pd.notna(atr_pa) and atr_pa > 0 else 0
        _near_bbl = (bbl is not None and pd.notna(bbl) and price <= bbl + _atr_ctx * 0.5)
        _near_bbu = (bbu is not None and pd.notna(bbu) and price >= bbu - _atr_ctx * 0.5)
        _near_sup = (l20 is not None and pd.notna(l20) and abs(price - l20) < _atr_ctx * 0.5)
        _near_res = (r20 is not None and pd.notna(r20) and abs(price - r20) < _atr_ctx * 0.5)
        if _near_bbl or _near_sup:
            bullish += 3; details["doji_ctx"] = "doji en soporte"
        elif _near_bbu or _near_res:
            bearish += 3; details["doji_ctx"] = "doji en resistencia"
        else:
            details["doji_ctx"] = "doji sin contexto"
    elif row.get("doji", 0) > 0.5:
        details["doji_ctx"] = "doji vol insuf"

    details["atr"] = round(atr_pa, 2) if pd.notna(atr_pa) else 0
    details["layer"] = "L1_only"

    return {
        "bullish_score": min(50, bullish),
        "bearish_score": min(50, bearish),
        "details":       details,
        "bbl":           row.get("BBL_20_2.0"),
        "bbu":           row.get("BBU_20_2.0"),
    }


# =============================================================================
# DETECCIÓN DE RÉGIMEN AUTOMÁTICO
# =============================================================================

def detect_regime_auto(row) -> str:
    """Detecta bull/bear/neutral usando EMA diarias y HTF 4h."""
    d_ema20 = row.get("d_ema20")
    d_ema50 = row.get("d_ema50")
    e9_4h   = row.get("ema_9_4h")
    e21_4h  = row.get("ema_21_4h")

    if not (pd.notna(d_ema20) and pd.notna(d_ema50) and d_ema50 > 0):
        return "neutral"

    daily_bull = d_ema20 > d_ema50 * 1.002
    daily_bear = d_ema20 < d_ema50 * 0.998
    htf_bull   = pd.notna(e9_4h) and pd.notna(e21_4h) and e9_4h > e21_4h
    htf_bear   = pd.notna(e9_4h) and pd.notna(e21_4h) and e9_4h < e21_4h

    if daily_bull and htf_bull:
        return "bull"
    if daily_bear and htf_bear:
        return "bear"
    return "neutral"


# =============================================================================
# HTF LIVE FETCH
# =============================================================================

def fetch_htf_4h_live(exchange, pair: str) -> dict:
    """Descarga las últimas 60 velas de 4h y devuelve tendencia HTF."""
    try:
        import pandas_ta as _ta
        ohlcv = exchange.fetch_ohlcv(pair, "4h", limit=60)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["ema_9"]  = _ta.ema(df["close"], length=9)
        df["ema_21"] = _ta.ema(df["close"], length=21)
        df["ema_50"] = _ta.ema(df["close"], length=50)
        df["rsi"]    = _ta.rsi(df["close"], length=14)
        last = df.iloc[-1]
        e9, e21, e50 = last.get("ema_9"), last.get("ema_21"), last.get("ema_50")
        if pd.notna(e9) and pd.notna(e21) and pd.notna(e50):
            if e9 > e21 > e50:   trend = "alcista"
            elif e9 < e21 < e50: trend = "bajista"
            else:                 trend = "lateral"
        else:
            trend = "calculando"
        rsi_val = round(last.get("rsi", 50), 1) if pd.notna(last.get("rsi")) else 50
        return {"htf_trend": trend, "htf_rsi": rsi_val,
                "htf_blocks_long": trend == "bajista",
                "htf_blocks_short": trend == "alcista"}
    except Exception:
        return {"htf_trend": "lateral", "htf_rsi": 50,
                "htf_blocks_long": False, "htf_blocks_short": False}


def fetch_htf_1d_live(exchange, pair: str) -> dict:
    """Descarga las últimas 60 velas diarias y devuelve tendencia 1D."""
    try:
        import pandas_ta as _ta
        ohlcv = exchange.fetch_ohlcv(pair, "1d", limit=60)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["ema_20"] = _ta.ema(df["close"], length=20)
        df["ema_50"] = _ta.ema(df["close"], length=50)
        last = df.iloc[-1]
        e20, e50 = last.get("ema_20"), last.get("ema_50")
        if pd.notna(e20) and pd.notna(e50) and e50 > 0:
            if e20 > e50 * 1.002:   trend = "alcista"
            elif e20 < e50 * 0.998: trend = "bajista"
            else:                    trend = "lateral"
        else:
            trend = "calculando"
        return {"htf_1d_trend": trend,
                "htf_1d_blocks_long": trend == "bajista",
                "htf_1d_blocks_short": trend == "alcista"}
    except Exception:
        return {"htf_1d_trend": "lateral",
                "htf_1d_blocks_long": False, "htf_1d_blocks_short": False}


# =============================================================================
# FILTROS DE SESIÓN Y CALIDAD DE SEÑAL
# =============================================================================

def is_weekend(timestamp) -> bool:
    if hasattr(timestamp, "weekday"):
        return timestamp.weekday() >= 5
    return False


def is_volatile_session(timestamp) -> bool:
    """True durante apertura NYSE (14:30-15:10 UTC) y Londres (08:00-08:30 UTC)."""
    if not hasattr(timestamp, "hour"):
        return False
    total_min = timestamp.hour * 60 + timestamp.minute
    return (870 <= total_min < 910) or (480 <= total_min < 510)


def check_signal_quality(technical: dict, side: str, min_confirmations: int = 3) -> bool:
    """Requiere al menos min_confirmations de 4 condiciones técnicas alineadas."""
    details = technical.get("details", {})
    conf    = 0
    rsi = details.get("rsi", 50)
    if pd.notna(rsi):
        if side == "LONG"  and rsi < 55: conf += 1
        elif side == "SHORT" and rsi > 45: conf += 1
    trend = details.get("trend", "lateral")
    if side == "LONG"  and trend in ("alcista", "alcista fuerte"): conf += 1
    elif side == "SHORT" and trend in ("bajista", "bajista fuerte"): conf += 1
    macd = details.get("macd", "neutral")
    if side == "LONG"  and macd in ("cruce alcista", "momentum alcista"): conf += 1
    elif side == "SHORT" and macd in ("cruce bajista", "momentum bajista"): conf += 1
    vol = details.get("vol_ratio", 1.0)
    if pd.notna(vol) and vol > 1.2: conf += 1
    return conf >= min_confirmations


def apply_weekend_filter(technical: dict, side: str, bull_score: int,
                         bear_score: int, risk_profile: dict,
                         timestamp) -> tuple:
    """Aplica lógica de fin de semana. Returns (puede_operar, min_score_efectivo)."""
    weekend_mode = risk_profile.get("weekend_mode", "range")
    bonus        = risk_profile.get("weekend_min_score_bonus", 10)
    base_min     = risk_profile["min_score"]

    if not is_weekend(timestamp):
        return True, base_min

    if weekend_mode is None:
        return False, base_min

    effective_min = base_min + bonus

    if weekend_mode == "trend":
        return True, effective_min

    # weekend_mode == "range": solo si precio en extremo de BB
    details = technical.get("details", {})
    price   = details.get("price", 0)
    bbl     = technical.get("bbl")
    bbu     = technical.get("bbu")
    if not bbl or not bbu or (bbu - bbl) == 0:
        return False, effective_min
    bb_pos = (price - bbl) / (bbu - bbl)
    if side == "LONG":
        return bb_pos <= 0.20, effective_min
    else:
        return bb_pos >= 0.80, effective_min
