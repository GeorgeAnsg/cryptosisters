"""
Bot de Trading Cripto v3.0 - Long & Short + Backtesting
=========================================================
- Detecta y ejecuta LONGS y SHORTS
- Scoring separado alcista / bajista
- Backtesting con datos historicos (hasta 1 ano)
- Logs detallados para diagnostico
- Perfil de riesgo seleccionable al arrancar
- Par configurable (no hardcodeado)
- Parametros de estrategia configurables desde el comando

USO EN VIVO (simulacion):
    python trading_bot_v3.py --pair BTC/USDT --risk moderate --exchange bybit

BACKTESTING:
    python trading_bot_v3.py --pair BTC/USDT --risk moderate --backtest --days 365

PARAMETROS DE ESTRATEGIA:
    --min-score 55
    --entry-advantage 25
    --close-threshold 70
    --min-hold-candles 6
    --max-daily-trades 4
    --stop-loss 2.0
    --take-profit 4.0

Requisitos:
    pip install ccxt pandas pandas-ta requests
"""

import ccxt
import pandas as pd
import pandas_ta as ta
import json
import os
import argparse
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# =============================================================================
# PERFILES DE RIESGO (seleccionable con --risk)
# =============================================================================

RISK_PROFILES = {
    "conservative": {
        "position_size_pct": 0.02,
        "stop_loss_atr_mult": 1.5,
        "take_profit_atr_mult": 3.0,
        "min_score": 75,
        "max_daily_trades": 6,
        "max_drawdown_pct": 0.05,
        "trailing_stop": True,
        "max_tp_extensions": 1,   # veces que se puede extender el TP si la señal sigue fuerte
        # Fin de semana: None = no operar, "range" = modo rango BB, "trend" = igual que semana
        "weekend_mode": "range",
        "weekend_min_score_bonus": 10,
    },
    "moderate": {
        "position_size_pct": 0.05,
        "stop_loss_atr_mult": 1.5,
        "take_profit_atr_mult": 4.0,
        "min_score": 55,
        "max_daily_trades": 6,
        "max_drawdown_pct": 0.10,
        "trailing_stop": True,
        "max_tp_extensions": 2,
        "weekend_mode": "range",
        "weekend_min_score_bonus": 10,
    },
    "aggressive": {
        "position_size_pct": 0.10,
        "stop_loss_atr_mult": 2.5,
        "take_profit_atr_mult": 6.0,
        "min_score": 40,
        "max_daily_trades": 12,
        "max_drawdown_pct": 0.20,
        "trailing_stop": False,
        "max_tp_extensions": 3,
        "weekend_mode": "trend",
        "weekend_min_score_bonus": 5,
    },
    # Perfil para trades de alta conviccion que se esperan duren dias.
    # No se usa directamente desde CLI; classify_trade() lo activa automaticamente
    # cuando la señal es suficientemente fuerte.
    "swing": {
        "position_size_pct": 0.12,      # mas tamaño: mas conviccion
        "stop_loss_atr_mult": 2.5,      # SL mas amplio: aguanta pullbacks normales
        "take_profit_atr_mult": 9.0,    # TP muy ambicioso: movimiento de dias
        "min_score": 62,                # umbral de entrada mas exigente (max real ~69)
        "max_daily_trades": 2,          # pocas operaciones, muy selectivas
        "max_drawdown_pct": 0.15,
        "trailing_stop": True,
        "max_tp_extensions": 2,
        "weekend_mode": "trend",        # en swing el contexto semanal manda
        "weekend_min_score_bonus": 5,
        "_swing_min_hold": 16,          # minimo 4 horas antes de cerrar por señal (en 15m)
    },
}

# =============================================================================
# REGIMENES DE MERCADO
# =============================================================================
# Ajustan el comportamiento del bot segun el contexto macro sin tocar los
# parametros base del perfil de riesgo. Se activa con --regime bull|bear|neutral.
#
#   long_min_bonus   / short_min_bonus  : puntos extra exigidos para abrir esa
#                                         direccion (negativo = mas permisivo)
#   long_tp_factor   / short_tp_factor  : multiplica el take_profit_atr_mult
#   long_max_ext     / short_max_ext    : extensiones de TP adicionales
#   breakeven_mult                      : la posicion tarda mas en llegar a
#                                         break-even (numero de sl_distance
#                                         que tiene que avanzar antes de mover SL)
MARKET_REGIMES = {
    "neutral": {
        "long_min_bonus":   0,
        "short_min_bonus":  0,
        "long_tp_factor":   1.0,
        "short_tp_factor":  1.0,
        "long_max_ext":     0,
        "short_max_ext":    0,
        "breakeven_mult":   1.0,   # break-even al +1x sl_distance (comportamiento base)
    },
    "bull": {
        "long_min_bonus":  -5,     # longs un poco mas faciles de abrir
        "short_min_bonus": +20,    # shorts solo si hay conviccion muy fuerte
        "long_tp_factor":   1.4,   # TP 40% mas ambicioso en longs
        "short_tp_factor":  0.8,   # TP mas conservador en shorts
        "long_max_ext":     1,     # una extension extra en longs
        "short_max_ext":    0,
        "breakeven_mult":   1.5,   # break-even tarda un poco mas (las correcciones bull son bruscas)
    },
    "bear": {
        "long_min_bonus":  +20,    # longs solo si hay conviccion muy fuerte
        "short_min_bonus": -5,
        "long_tp_factor":   0.8,
        "short_tp_factor":  1.4,
        "long_max_ext":     0,
        "short_max_ext":    1,
        "breakeven_mult":   1.5,
    },
}


def apply_regime(risk_profile: dict, regime: str) -> dict:
    """Devuelve una copia del perfil de riesgo con los ajustes del regimen aplicados."""
    r = risk_profile.copy()
    adj = MARKET_REGIMES.get(regime, MARKET_REGIMES["neutral"])
    r["_regime"]          = regime
    r["_long_min_bonus"]  = adj["long_min_bonus"]
    r["_short_min_bonus"] = adj["short_min_bonus"]
    r["_long_tp_factor"]  = adj["long_tp_factor"]
    r["_short_tp_factor"] = adj["short_tp_factor"]
    r["_long_max_ext"]    = adj["long_max_ext"]
    r["_short_max_ext"]   = adj["short_max_ext"]
    r["_breakeven_mult"]  = adj["breakeven_mult"]
    return r


# Umbrales configurables para --regime auto (modificar para tuning)
# Compara EMA20 diaria vs EMA50 diaria: funciona con solo 50 días de datos
REGIME_BULL_TH: float = 0.008  # d_ema20/d_ema50 > 1+TH → bull  (tuned: backtest BTC 365d)
REGIME_BEAR_TH: float = 0.008  # d_ema20/d_ema50 < 1-TH → bear  (tuned: backtest BTC 365d)


def detect_regime_auto(row) -> str:
    """Detecta régimen automáticamente usando EMA20 y EMA50 diarias."""
    ema20 = row.get("d_ema20")
    ema50 = row.get("d_ema50")
    if ema20 is None or ema50 is None or pd.isna(ema20) or pd.isna(ema50):
        return "neutral"
    ratio = ema20 / ema50
    if ratio > 1 + REGIME_BULL_TH:
        return "bull"
    elif ratio < 1 - REGIME_BEAR_TH:
        return "bear"
    return "neutral"


# =============================================================================
# KEYWORDS SENTIMIENTO
# =============================================================================

BULLISH_KEYWORDS = [
    "bull", "bullish", "surge", "soar", "rally", "breakout", "moon",
    "all-time high", "ath", "pump", "gain", "growth", "adoption",
    "approved", "approval", "etf approved", "institutional",
    "partnership", "upgrade", "launch", "milestone", "record",
    "accumulation", "recovery", "support held", "inflows",
    "whale buying", "short squeeze", "golden cross",
]

BEARISH_KEYWORDS = [
    "bear", "bearish", "crash", "dump", "plunge", "drop", "sell-off",
    "selloff", "hack", "hacked", "exploit", "vulnerability", "ban",
    "banned", "regulation", "fine", "penalty", "lawsuit", "fraud",
    "scam", "rug pull", "rugpull", "bankruptcy", "insolvent",
    "liquidation", "fear", "panic", "collapse", "warning",
    "outflows", "whale selling", "death cross", "breakdown",
]


# =============================================================================
# LOGGER - Logs detallados para diagnostico
# =============================================================================

class Logger:
    def __init__(self, log_file: str = "bot_decisions.log"):
        self.log_file = log_file

    def log(self, message: str, level: str = "INFO"):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] {message}"
        print(line)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")

    def decision(self, pair: str, bullish_score: int, bearish_score: int,
                 min_score: int, position: Optional[dict], reason: str):
        """Log detallado de cada decision del bot."""
        ts = datetime.now().strftime("%H:%M:%S")
        pos_str = "FLAT"
        if position:
            side = position.get("side", "?")
            entry = position.get("entry_price", 0)
            pos_str = f"{side.upper()} desde {entry:.2f}"

        line = (
            f"[{ts}] [{pair}] Estado:{pos_str} | "
            f"Bull:{bullish_score:3d} Bear:{bearish_score:3d} | "
            f"Min:{min_score} | >> {reason}"
        )
        print(line)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")


logger = Logger()


# =============================================================================
# ESTADO
# =============================================================================

def load_state(path: str) -> dict:
    if Path(path).exists():
        with open(path, "r") as f:
            return json.load(f)
    return {
        "balance_usdt": 1000.0,
        "position": None,
        "trades": [],
        "daily_trades": 0,
        "daily_longs": 0,
        "daily_shorts": 0,
        "daily_date": datetime.now().strftime("%Y-%m-%d"),
        "stats": {
            "wins": 0, "losses": 0, "total_pnl": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "total_longs": 0, "total_shorts": 0,
            "long_wins": 0, "short_wins": 0,
        },
        "peak_balance": 1000.0,
        "created_at": datetime.now().isoformat(),
    }


def save_state(state: dict, path: str):
    with open(path, "w") as f:
        json.dump(state, f, indent=2, default=str)


def reset_daily_counter(state: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("daily_date") != today:
        state["daily_trades"] = 0
        state["daily_longs"] = 0
        state["daily_shorts"] = 0
        state["daily_date"] = today


# =============================================================================
# DATOS DE MERCADO
# =============================================================================

def fetch_ohlcv(exchange, pair: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_historical_ohlcv(exchange, pair: str, timeframe: str, days: int) -> pd.DataFrame:
    """Descarga datos historicos para backtesting."""
    logger.log(f"Descargando {days} dias de datos para {pair} ({timeframe})...")

    all_data = []
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    limit = 1000

    while True:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        all_data.extend(ohlcv)
        since = ohlcv[-1][0] + 1
        if len(ohlcv) < limit:
            break
        time.sleep(0.2)  # Rate limit
        # Progreso
        pct = min(100, len(all_data) / (days * 96) * 100)  # Aprox para 15m
        print(f"\r  Descargando... {len(all_data)} velas ({pct:.0f}%)", end="", flush=True)

    print()  # Nueva linea tras progreso

    df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

    logger.log(f"Descargados {len(df)} velas ({df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]})")
    return df


# =============================================================================
# ANALISIS TECNICO - Scoring SEPARADO alcista/bajista
# =============================================================================

def _add_htf_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Resamplea 15m -> 4h, calcula indicadores y une al DataFrame via merge_asof.
    Cada vela 15m recibe el contexto de la ultima vela 4h COMPLETADA (direction=backward)."""
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

    htf_cols = ["timestamp", "ema_9_4h", "ema_21_4h", "ema_50_4h", "rsi_4h"]
    if "macd_hist_4h" in df_4h.columns:
        htf_cols.append("macd_hist_4h")

    return pd.merge_asof(
        df.sort_values("timestamp"),
        df_4h[htf_cols].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )


def precompute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-calcula todos los indicadores tecnicos sobre el DataFrame completo.
    Llamar UNA sola vez antes del loop del backtest para evitar recalcular
    en cada vela (el cuello de botella principal del optimizer)."""
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

    # Price action (pre-computado para evitar recalculo en el loop)
    df["body_size"]    = (df["close"] - df["open"]).abs()
    df["upper_wick"]   = df["high"] - df[["close", "open"]].max(axis=1)
    df["lower_wick"]   = df[["close", "open"]].min(axis=1) - df["low"]
    df["candle_range"] = df["high"] - df["low"]

    # Engulfing
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

    # Hammer: mecha inferior larga (>2x cuerpo), cuerpo en tercio superior del rango
    # Señal de rebote alcista, especialmente en soporte
    df["hammer"] = (
        (df["lower_wick"] > 2 * df["body_size"].clip(lower=0.0001)) &
        (df["upper_wick"] < df["body_size"]) &
        (df["candle_range"] > 0)
    ).astype(float)

    # Shooting star: mecha superior larga (>2x cuerpo), cuerpo en tercio inferior
    # Señal de rechazo bajista, especialmente en resistencia
    df["shooting_star"] = (
        (df["upper_wick"] > 2 * df["body_size"].clip(lower=0.0001)) &
        (df["lower_wick"] < df["body_size"]) &
        (df["candle_range"] > 0)
    ).astype(float)

    # Doji: cuerpo muy pequeño vs rango → indecision (util en extremos)
    doji_threshold = df["atr"] * 0.1
    df["doji"] = (df["body_size"] < doji_threshold).astype(float)

    # Tres velas consecutivas (momentum confirmado)
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

    # Soporte / Resistencia: maximos y minimos de ventanas mas largas
    df["rolling_high_20"]  = df["high"].rolling(20).max().shift(1)   # ~5h
    df["rolling_low_20"]   = df["low"].rolling(20).min().shift(1)
    df["rolling_high_100"] = df["high"].rolling(100).max().shift(1)  # ~25h (1 dia)
    df["rolling_low_100"]  = df["low"].rolling(100).min().shift(1)

    # Pivots: maximos y minimos locales (ventana de 5 velas a cada lado = 2.5h)
    _pn = 5
    df["pivot_high"] = df["high"].rolling(2*_pn+1, center=True).apply(
        lambda x: float(x[_pn] == x.max()), raw=True).fillna(0)
    df["pivot_low"] = df["low"].rolling(2*_pn+1, center=True).apply(
        lambda x: float(x[_pn] == x.min()), raw=True).fillna(0)

    # Doble techo / Doble suelo: dos pivots similares (<1.5%) con valle/pico entre ellos
    import numpy as np
    _ph = df["pivot_high"].values.astype(bool)
    _pl = df["pivot_low"].values.astype(bool)
    _hi = df["high"].values
    _lo = df["low"].values
    _at = df["atr"].values
    _lb = 100  # lookback en velas (~25h)
    _dt = np.zeros(len(df))
    _db = np.zeros(len(df))
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

    # Canal de precio: rolling max/min de 40 velas (~10h) como techo y suelo del canal
    _cw = 40
    df["ch_top"] = df["high"].rolling(_cw).max()
    df["ch_bot"] = df["low"].rolling(_cw).min()
    _ch_valid = (df["ch_top"] - df["ch_bot"]) > df["atr"]
    df["near_channel_top"] = ((df["close"] >= df["ch_top"] - 0.5 * df["atr"]) & _ch_valid).astype(float)
    df["near_channel_bot"] = ((df["close"] <= df["ch_bot"] + 0.5 * df["atr"]) & _ch_valid).astype(float)

    # Contraccion de ATR: si el ATR actual < 60% del ATR medio -> mercado en rango
    df["atr_sma20"]       = df["atr"].rolling(20).mean()
    df["atr_contracted"]  = (df["atr"] < df["atr_sma20"] * 0.6).astype(float)

    # ADX: fuerza de la tendencia (independiente de la dirección)
    # ADX < 20 = rango/sin tendencia, ADX > 25 = tendencia real, ADX > 40 = tendencia fuerte
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx_df is not None:
        df["adx"]     = adx_df.get("ADX_14", pd.Series(dtype=float))
        df["adx_dmp"] = adx_df.get("DMP_14", pd.Series(dtype=float))  # +DI (direccion alcista)
        df["adx_dmn"] = adx_df.get("DMN_14", pd.Series(dtype=float))  # -DI (direccion bajista)

    # VWAP diario: precio medio ponderado por volumen, se resetea cada día a medianoche UTC
    # Referencia institucional: precio > VWAP = presion compradora, < VWAP = presion vendedora
    df["_date"] = df["timestamp"].dt.date
    df["vwap"] = (
        df.groupby("_date", group_keys=False)
        .apply(lambda g: (g["close"] * g["volume"]).cumsum() / g["volume"].cumsum())
        .reset_index(level=0, drop=True)
    )
    df = df.drop(columns=["_date"])

    # Contexto 4h: cada vela 15m tiene acceso a la ultima vela 4h completada
    df = _add_htf_columns(df)

    # EMA diaria para detección automática de régimen (--regime auto)
    # EMA20 y EMA50 diarias: válidas con solo 50 días de datos (vs 200 semanas del weekly EMA200)
    # EMA20 > EMA50 = tendencia alcista de medio plazo, < = bajista
    daily = df.set_index("timestamp").resample("D")["close"].last().dropna().to_frame()
    daily["d_ema20"] = ta.ema(daily["close"], length=20)
    daily["d_ema50"] = ta.ema(daily["close"], length=50)
    daily = daily[["d_ema20", "d_ema50"]].reset_index()
    df = pd.merge_asof(
        df.sort_values("timestamp"),
        daily.sort_values("timestamp"),
        on="timestamp",
        direction="backward",
    )

    return df


def analyze_technical(df: pd.DataFrame, row=None, prev_row=None) -> dict:
    """
    Retorna dos scores independientes:
      - bullish_score (0-50): fuerza de senal alcista
      - bearish_score (0-50): fuerza de senal bajista

    En el backtest se pasan row/prev_row (Series ya calculadas) para evitar
    recomputar indicadores. En modo live se sigue usando el df completo.
    """
    if row is None and (df is None or len(df) < 50):
        return {"bullish_score": 0, "bearish_score": 0, "details": {}}

    if row is None:
        # Modo live: calcula indicadores sobre la ventana
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
        # Price action (igual que precompute_indicators pero en la ventana live)
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
        df["_date"] = df["timestamp"].dt.date
        df["vwap"] = (
            df.groupby("_date", group_keys=False)
            .apply(lambda g: (g["close"] * g["volume"]).cumsum() / g["volume"].cumsum())
            .reset_index(level=0, drop=True)
        )
        df = df.drop(columns=["_date"])
        last = df.iloc[-1]
        prev = df.iloc[-2]
    else:
        # Modo backtest: usa filas ya pre-calculadas
        last = row
        prev = prev_row if prev_row is not None else row

    bullish = 0
    bearish = 0
    details = {}

    price = last["close"]
    details["price"] = round(price, 2)

    # --- RSI (max 10 pts cada direccion) ---
    rsi = last.get("rsi", 50)
    if pd.notna(rsi):
        details["rsi"] = round(rsi, 1)
        if rsi < 25:
            bullish += 10
        elif rsi < 35:
            bullish += 7
        elif rsi < 45:
            bullish += 3
        if rsi > 75:
            bearish += 10
        elif rsi > 65:
            bearish += 7
        elif rsi > 55:
            bearish += 3
    else:
        details["rsi"] = 50.0

    # --- EMA Trend (max 15 pts) ---
    ema_9 = last.get("ema_9", 0)
    ema_21 = last.get("ema_21", 0)
    ema_50 = last.get("ema_50", 0)
    ema_200 = last.get("ema_200", 0)

    if pd.notna(ema_9) and pd.notna(ema_21) and pd.notna(ema_50):
        if ema_9 > ema_21 > ema_50:
            bullish += 12
            details["trend"] = "alcista fuerte"
        elif ema_9 > ema_21:
            bullish += 7
            details["trend"] = "alcista"
        elif ema_9 < ema_21 < ema_50:
            bearish += 12
            details["trend"] = "bajista fuerte"
        elif ema_9 < ema_21:
            bearish += 7
            details["trend"] = "bajista"
        else:
            details["trend"] = "lateral"

        if pd.notna(ema_200):
            if price > ema_200:
                bullish += 3
                details["above_ema200"] = True
            elif price < ema_200:
                bearish += 3
                details["above_ema200"] = False
            else:
                details["above_ema200"] = None
        else:
            details["above_ema200"] = None
    else:
        details["trend"] = "calculando"

    # --- MACD (max 10 pts) ---
    macd_hist = last.get("MACDh_12_26_9", 0)
    prev_hist = prev.get("MACDh_12_26_9", 0)

    if pd.notna(macd_hist) and pd.notna(prev_hist):
        if macd_hist > 0 and prev_hist <= 0:
            bullish += 10
            details["macd"] = "cruce alcista"
        elif macd_hist > 0 and macd_hist > prev_hist:
            bullish += 5
            details["macd"] = "momentum alcista"
        elif macd_hist < 0 and prev_hist >= 0:
            bearish += 10
            details["macd"] = "cruce bajista"
        elif macd_hist < 0 and macd_hist < prev_hist:
            bearish += 5
            details["macd"] = "momentum bajista"
        else:
            details["macd"] = "neutral"
    else:
        details["macd"] = "sin datos"

    # --- Bollinger Bands (max 8 pts) ---
    bbl = last.get("BBL_20_2.0", None)
    bbu = last.get("BBU_20_2.0", None)

    if pd.notna(bbl) and pd.notna(bbu) and (bbu - bbl) > 0:
        if price <= bbl:
            bullish += 8
            details["bollinger"] = "bajo banda inferior"
        elif price >= bbu:
            bearish += 8
            details["bollinger"] = "sobre banda superior"
        else:
            bb_pos = (price - bbl) / (bbu - bbl)
            if bb_pos < 0.3:
                bullish += 4
            elif bb_pos > 0.7:
                bearish += 4
            details["bollinger"] = f"pos:{bb_pos:.0%}"
    else:
        details["bollinger"] = "sin datos"

    # --- Price Action (dentro del cap 50) ---
    body   = last.get("body_size", 0)
    open_p = last.get("open", price)
    atr_pa = last.get("atr", 0)

    # Engulfing (+8): vela actual engulle a la anterior
    if last.get("bull_engulf", 0) > 0.5:
        bullish += 8
        details["pa"] = "engulf alcista"
    elif last.get("bear_engulf", 0) > 0.5:
        bearish += 8
        details["pa"] = "engulf bajista"

    # Hammer / Shooting Star (+7): mecha larga = rechazo fuerte en extremo de precio
    if last.get("hammer", 0) > 0.5:
        bullish += 7
        details["pa_vela"] = "hammer"
    elif last.get("shooting_star", 0) > 0.5:
        bearish += 7
        details["pa_vela"] = "shooting star"

    # Tres velas consecutivas (+6): momentum sostenido 3 barras seguidas
    if last.get("three_bull", 0) > 0.5:
        bullish += 6
        details["pa_seq"] = "3 alcistas"
    elif last.get("three_bear", 0) > 0.5:
        bearish += 6
        details["pa_seq"] = "3 bajistas"

    # Impulso: cuerpo > 1.5xATR = movimiento directo fuerte (+5)
    if pd.notna(body) and pd.notna(atr_pa) and atr_pa > 0 and body > 1.5 * atr_pa:
        if price > open_p:
            bullish += 5
            details["pa_impulso"] = f"bull {body/atr_pa:.1f}xATR"
        elif price < open_p:
            bearish += 5
            details["pa_impulso"] = f"bear {body/atr_pa:.1f}xATR"

    # Breakout S/R corto plazo ~5h (+5) o largo plazo ~25h (+4)
    r20  = last.get("rolling_high_20")
    l20  = last.get("rolling_low_20")
    r100 = last.get("rolling_high_100")
    l100 = last.get("rolling_low_100")
    if r100 is not None and pd.notna(r100) and price > r100:
        bullish += 4
        details["sr_break"] = "resist diaria rota"
    elif l100 is not None and pd.notna(l100) and price < l100:
        bearish += 4
        details["sr_break"] = "soporte diario roto"
    elif r20 is not None and pd.notna(r20) and price > r20:
        bullish += 5
        details["sr_break"] = "resist 5h rota"
    elif l20 is not None and pd.notna(l20) and price < l20:
        bearish += 5
        details["sr_break"] = "soporte 5h roto"

    # Contraccion ATR: mercado en rango → registrar, el loop puede usarlo para filtrar
    details["consolidacion"] = bool(last.get("atr_contracted", 0) > 0.5)

    # --- ADX: fuerza de tendencia (informativo) ---
    # adx_trending se usa como filtro en el loop de backtest/live si se activa
    adx_val = last.get("adx")
    adx_dmp = last.get("adx_dmp")
    adx_dmn = last.get("adx_dmn")
    if adx_val is not None and pd.notna(adx_val):
        details["adx"] = round(adx_val, 1)
        details["adx_trending"] = adx_val >= 25
        if pd.notna(adx_dmp) and pd.notna(adx_dmn):
            details["adx_dir"] = f"bull {adx_val:.0f}" if adx_dmp > adx_dmn else f"bear {adx_val:.0f}"
        else:
            details["adx_dir"] = f"rango {adx_val:.0f}"
    else:
        details["adx_trending"] = True   # sin datos → no bloquear

    # --- VWAP diario: sesgo institucional (informativo) ---
    vwap = last.get("vwap")
    if vwap is not None and pd.notna(vwap):
        details["vwap"] = round(vwap, 2)
        details["vwap_bias"] = "sobre VWAP" if price > vwap else "bajo VWAP"
    else:
        details["vwap_bias"] = "sin datos"

    # --- HTF (4h): contexto + puntuacion activa (max 15 pts) ---
    ema9_4h  = last.get("ema_9_4h")
    ema21_4h = last.get("ema_21_4h")
    ema50_4h = last.get("ema_50_4h")
    rsi_4h   = last.get("rsi_4h")
    macd_4h  = last.get("macd_hist_4h")

    if pd.notna(ema9_4h) and pd.notna(ema21_4h) and pd.notna(ema50_4h):
        if ema9_4h > ema21_4h > ema50_4h:
            details["htf_trend"] = "alcista"
            bullish += 8
        elif ema9_4h > ema21_4h:
            details["htf_trend"] = "alcista parcial"
            bullish += 4
        elif ema9_4h < ema21_4h < ema50_4h:
            details["htf_trend"] = "bajista"
            bearish += 8
        elif ema9_4h < ema21_4h:
            details["htf_trend"] = "bajista parcial"
            bearish += 4
        else:
            details["htf_trend"] = "lateral"
    else:
        details["htf_trend"] = "calculando"

    if macd_4h is not None and pd.notna(macd_4h):
        details["htf_macd"] = "alcista" if macd_4h > 0 else "bajista"
        if macd_4h > 0:
            bullish += 4
        else:
            bearish += 4

    if rsi_4h is not None and pd.notna(rsi_4h):
        details["htf_rsi"] = round(rsi_4h, 1)
        if rsi_4h < 40:
            bullish += 3
        elif rsi_4h > 60:
            bearish += 3

    # --- Doble techo / Doble suelo (8 pts) ---
    if last.get("double_top", 0):
        bearish += 8
        details["pattern_multi"] = "doble_techo"
    elif last.get("double_bottom", 0):
        bullish += 8
        details["pattern_multi"] = "doble_suelo"

    # --- Canal de precio (5 pts) ---
    if last.get("near_channel_bot", 0):
        bullish += 5
        details["channel"] = "soporte_canal"
    elif last.get("near_channel_top", 0):
        bearish += 5
        details["channel"] = "resistencia_canal"

    # --- Volumen (max 7 pts como confirmacion) ---
    vol_ratio = last.get("vol_ratio", 1.0)
    if pd.notna(vol_ratio):
        details["vol_ratio"] = round(vol_ratio, 2)
        if vol_ratio > 2.0:
            if bullish > bearish:
                bullish += 7
            elif bearish > bullish:
                bearish += 7
        elif vol_ratio > 1.3:
            if bullish > bearish:
                bullish += 3
            elif bearish > bullish:
                bearish += 3
    else:
        details["vol_ratio"] = 1.0

    # --- ATR ---
    atr_val = last.get("atr", 0)
    details["atr"] = round(atr_val, 2) if pd.notna(atr_val) else 0

    bullish = min(50, bullish)
    bearish = min(50, bearish)

    return {
        "bullish_score": bullish,
        "bearish_score": bearish,
        "details": details,
        "bbl": last.get("BBL_20_2.0"),
        "bbu": last.get("BBU_20_2.0"),
    }


# =============================================================================
# LOGICA DIA DE LA SEMANA
# =============================================================================

def classify_trade(technical: dict, side: str, scores: dict) -> str:
    """
    Decide si la señal es suficientemente fuerte para un swing trade (dias)
    o un trade intraday (horas).

    Criterios para swing — deben cumplirse los 4:
      1. Score muy alto (>= swing min_score = 70)
      2. Tendencia fuerte alineada (EMA 9 > 21 > 50 para LONG)
      3. Precio al lado correcto de la EMA 200 (marco temporal mayor)
      4. MACD con cruce o momentum claro en esa direccion

    Si no se cumplen los 4, el trade es intraday (perfil de riesgo normal).
    """
    details = technical.get("details", {})
    swing_min = RISK_PROFILES["swing"]["min_score"]

    score = scores.get("bullish_total", 0) if side == "LONG" else scores.get("bearish_total", 0)
    if score < swing_min:
        return "intraday"

    trend = details.get("trend", "lateral")
    if side == "LONG" and trend != "alcista fuerte":
        return "intraday"
    if side == "SHORT" and trend != "bajista fuerte":
        return "intraday"

    above_ema200 = details.get("above_ema200")
    if side == "LONG" and above_ema200 is not True:
        return "intraday"
    if side == "SHORT" and above_ema200 is not False:
        return "intraday"

    macd = details.get("macd", "neutral")
    if side == "LONG" and macd not in ("cruce alcista", "momentum alcista"):
        return "intraday"
    if side == "SHORT" and macd not in ("cruce bajista", "momentum bajista"):
        return "intraday"

    return "swing"


def check_signal_quality(technical: dict, side: str, min_confirmations: int = 3) -> bool:
    """
    Filtra entradas de baja calidad exigiendo que al menos `min_confirmations`
    de 4 condiciones tecnicas esten de acuerdo con la direccion del trade.

    Condiciones evaluadas:
      1. RSI en zona favorable (no saturado en contra)
      2. EMAs alineadas en la direccion del trade
      3. MACD con momentum en la direccion correcta
      4. Volumen por encima de la media (confirma interes real)

    Esto evita entrar en senales que solo pasan el umbral de score por
    un par de indicadores, sin confluencia real.
    """
    details = technical.get("details", {})
    confirmations = 0

    # 1. RSI
    rsi = details.get("rsi", 50)
    if pd.notna(rsi):
        if side == "LONG" and rsi < 55:    # no sobrecomprado
            confirmations += 1
        elif side == "SHORT" and rsi > 45:  # no sobrevendido
            confirmations += 1

    # 2. EMA alignment — extraemos del dict 'details' (ya calculado)
    trend = details.get("trend", "lateral")
    if side == "LONG" and trend in ("alcista", "alcista fuerte"):
        confirmations += 1
    elif side == "SHORT" and trend in ("bajista", "bajista fuerte"):
        confirmations += 1

    # 3. MACD momentum
    macd = details.get("macd", "neutral")
    if side == "LONG" and macd in ("cruce alcista", "momentum alcista"):
        confirmations += 1
    elif side == "SHORT" and macd in ("cruce bajista", "momentum bajista"):
        confirmations += 1

    # 4. Volumen por encima de la media
    vol_ratio = details.get("vol_ratio", 1.0)
    if pd.notna(vol_ratio) and vol_ratio > 1.2:
        confirmations += 1

    return confirmations >= min_confirmations


def is_weekend(timestamp) -> bool:
    """Devuelve True si el timestamp cae en sabado o domingo."""
    if hasattr(timestamp, "weekday"):
        return timestamp.weekday() >= 5  # 5=sabado, 6=domingo
    return False


def is_volatile_session(timestamp) -> bool:
    """Devuelve True durante las ventanas de alta volatilidad en apertura de mercados.
    Solo bloquea nuevas entradas — las posiciones abiertas se siguen gestionando.
    - NYSE open: 14:30-15:10 UTC (primeros 40 min, fakeouts frecuentes)
    - London open: 08:00-08:30 UTC (menor impacto en crypto pero notable)
    """
    if not hasattr(timestamp, "hour"):
        return False
    h, m = timestamp.hour, timestamp.minute
    total_min = h * 60 + m
    nyse_open   = (14 * 60 + 30) <= total_min < (15 * 60 + 10)  # 14:30-15:10 UTC
    london_open = (8  * 60)      <= total_min < (8  * 60 + 30)  # 08:00-08:30 UTC
    return nyse_open or london_open


def check_weekend_entry(technical: dict, side: str) -> bool:
    """
    En modo fin de semana ('range'): solo entra si el precio esta cerca de las
    Bandas de Bollinger (mercado en rango).
      - LONG: precio <= banda inferior o en el 20% inferior de la banda
      - SHORT: precio >= banda superior o en el 20% superior de la banda
    Devuelve True si la condicion de rango se cumple.
    """
    details = technical.get("details", {})
    price = details.get("price", 0)
    bbl = technical.get("bbl")
    bbu = technical.get("bbu")

    # Si no hay BB disponible, no operamos en fin de semana
    if not bbl or not bbu or (bbu - bbl) == 0:
        return False

    bb_pos = (price - bbl) / (bbu - bbl)  # 0=banda inf, 1=banda sup

    if side == "LONG":
        return bb_pos <= 0.20   # precio en cuarto inferior de la banda
    else:
        return bb_pos >= 0.80   # precio en cuarto superior de la banda


def apply_weekend_filter(technical: dict, side: str, bull_score: int,
                         bear_score: int, risk_profile: dict,
                         timestamp) -> tuple[bool, int]:
    """
    Aplica la logica de fin de semana.
    Retorna (puede_operar, min_score_efectivo).
    """
    weekend_mode = risk_profile.get("weekend_mode", "range")
    bonus = risk_profile.get("weekend_min_score_bonus", 10)
    base_min = risk_profile["min_score"]

    if not is_weekend(timestamp):
        return True, base_min  # semana: logica normal

    if weekend_mode is None:
        return False, base_min  # fin de semana desactivado

    effective_min = base_min + bonus  # umbral mas exigente

    if weekend_mode == "trend":
        return True, effective_min  # misma logica pero mas restrictiva

    # weekend_mode == "range": requiere ademas que el precio este en extremo de BB
    bb_ok = check_weekend_entry(technical, side)
    return bb_ok, effective_min


# =============================================================================
# SENTIMIENTO (GDELT + Fear&Greed)
# =============================================================================

def analyze_headline_sentiment(title: str) -> int:
    title_lower = title.lower()
    bull_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in title_lower)
    bear_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in title_lower)
    if bull_hits > bear_hits:
        return 1
    elif bear_hits > bull_hits:
        return -1
    return 0


# --- GDELT: fuente de noticias unica para vivo (fetch_sentiment) y para el
# backtest (fetch_historical_news.py importa build_gdelt_query y
# fetch_gdelt_articles de aqui). Gratis, sin API key. Usar el mismo
# mecanismo en ambos sitios evita que el backtest entrene con una
# distribucion de noticias distinta a la que ve el bot en produccion.

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Lista corta a proposito: las queries de GDELT con muchas clausulas
# "domainis:...OR..." (probado con 19) reciben 429 de forma consistente
# incluso en la primera peticion, en dos redes distintas - la API penaliza
# la complejidad de la query, no solo la frecuencia. Con 5-6 dominios
# funciona de forma fiable.
CRYPTO_NEWS_DOMAINS = [
    "coindesk.com", "cointelegraph.com", "decrypt.co",
    "theblock.co", "bitcoinmagazine.com", "newsbtc.com",
]

TICKER_TO_NAME = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
    "HYPE": "hyperliquid", "AAVE": "aave",
    "ADA": "cardano", "DOGE": "dogecoin", "BNB": "binance coin",
    "MATIC": "polygon", "DOT": "polkadot", "LTC": "litecoin",
    "AVAX": "avalanche", "LINK": "chainlink", "TRX": "tron",
    "SHIB": "shiba inu", "ATOM": "cosmos", "UNI": "uniswap",
}


def build_gdelt_query(ticker: str) -> str:
    """Query de GDELT acotada a medios cripto conocidos.
    GDELT no admite dos grupos OR anidados, asi que la query es siempre
    simple: nombre del activo + filtro de dominios. Las noticias de
    mercado general (regulacion, ETFs, Fed...) aparecen en medios cripto
    mencionando al activo, por lo que se recogen igual y se clasifican
    client-side con is_market_wide()."""
    domain_filter = " OR ".join(f"domainis:{d}" for d in CRYPTO_NEWS_DOMAINS)
    name = TICKER_TO_NAME.get(ticker.upper(), ticker.lower())
    return f"{name} ({domain_filter})"


def fetch_gdelt_articles(query: str, timespan: str = None, start: str = None,
                          end: str = None, maxrecords: int = 20, retries: int = 6) -> list:
    """Llama a la API DOC 2.0 de GDELT. Devuelve lista de dicts
    {title, date, source}. Ante cualquier fallo (incluido el 429 de rate
    limit) devuelve [] en vez de propagar la excepcion, igual que
    fetch_fear_greed() - un dia sin noticias cae al sentimiento neutral."""
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": maxrecords,
        "sort": "datedesc",
    }
    if timespan:
        params["timespan"] = timespan
    if start and end:
        params["startdatetime"] = start
        params["enddatetime"] = end

    for attempt in range(retries):
        try:
            resp = requests.get(GDELT_URL, params=params, timeout=20,
                                 headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                articles = []
                for a in data.get("articles", []):
                    seendate = a.get("seendate", "")  # ej "20260824T091500Z"
                    date_str = f"{seendate[0:4]}-{seendate[4:6]}-{seendate[6:8]}" if len(seendate) >= 8 else ""
                    articles.append({
                        "title": a.get("title", ""),
                        "date": date_str,
                        "source": a.get("domain", ""),
                    })
                return articles
            if resp.status_code == 429:
                time.sleep(15)
                continue
            return []
        except (requests.RequestException, ValueError):
            time.sleep(5)
    return []


def fetch_sentiment(pair: str) -> dict:
    """GDELT - gratis, sin API key. Usa el mismo build_gdelt_query /
    fetch_gdelt_articles que el backtest historico."""
    symbol = pair.split("/")[0]
    try:
        query = build_gdelt_query(symbol)
        articles = fetch_gdelt_articles(query, timespan="3d", maxrecords=20)

        bullish = 0
        bearish = 0
        news_list = []

        for article in articles[:15]:
            title = article.get("title", "")
            val = analyze_headline_sentiment(title)
            if val > 0:
                bullish += 1
            elif val < 0:
                bearish += 1
            news_list.append({
                "title": title[:80],
                "sentiment": "+" if val > 0 else ("-" if val < 0 else "="),
            })

        total = bullish + bearish
        if total == 0:
            bull_score = 0
            bear_score = 0
            sentiment = "neutral"
            shock = None
        else:
            bull_score = round((bullish / total) * 15)
            bear_score = round((bearish / total) * 15)
            if bullish > bearish * 1.5:
                sentiment = "positivo"
            elif bearish > bullish * 1.5:
                sentiment = "negativo"
            else:
                sentiment = "mixto"
            # Shock: mismo criterio que load_daily_sentiment (>=80% en una dirección, >=4 artículos)
            shock = None
            if total >= 4:
                if bearish / total >= 0.8:
                    shock = "bear"
                elif bullish / total >= 0.8:
                    shock = "bull"

        return {
            "bullish_score": bull_score,
            "bearish_score": bear_score,
            "sentiment": sentiment,
            "shock": shock,
            "news": news_list[:5],
        }

    except Exception as e:
        return {"bullish_score": 0, "bearish_score": 0, "sentiment": "error", "news": [], "error": str(e)}


def load_daily_sentiment(news_file: str) -> dict:
    """
    Carga el JSON generado por fetch_historical_news.py y agrega las
    noticias por dia, replicando la MISMA formula que usa fetch_sentiment()
    en vivo (bull_score y bear_score sobre una escala 0-15).

    Cada dia incluye tanto las noticias especificas del activo ("asset")
    como las de mercado general ("market"), igual que se explico al
    construir fetch_historical_news.py.

    Devuelve: { "2025-01-15": {"bullish_score": int, "bearish_score": int,
                                "sentiment": str}, ... }
    Si un dia no tiene noticias, no aparece en el dict (el llamador debe
    usar el neutral por defecto como fallback).
    """
    with open(news_file, "r", encoding="utf-8") as f:
        news = json.load(f)

    by_day = {}
    for item in news:
        day = item.get("date", "")
        if not day:
            continue
        by_day.setdefault(day, []).append(item["sentiment"])

    result = {}
    for day, labels in by_day.items():
        bullish = sum(1 for s in labels if s == "+")
        bearish = sum(1 for s in labels if s == "-")
        total = bullish + bearish

        if total == 0:
            bull_score, bear_score, sentiment = 0, 0, "neutral"
        else:
            bull_score = round((bullish / total) * 15)
            bear_score = round((bearish / total) * 15)
            if bullish > bearish * 1.5:
                sentiment = "positivo"
            elif bearish > bullish * 1.5:
                sentiment = "negativo"
            else:
                sentiment = "mixto"

        # Shock: dia con sentimiento extremo (>= 80% de articulos en una direccion
        # y al menos 4 articulos). Permite abrir antes de que los indicadores confirmen.
        shock = None
        if total >= 4:
            if bearish / total >= 0.8:
                shock = "bear"
            elif bullish / total >= 0.8:
                shock = "bull"

        result[day] = {
            "bullish_score": bull_score,
            "bearish_score": bear_score,
            "sentiment": sentiment,
            "shock": shock,
        }

    return result


def fetch_fear_greed() -> dict:
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        response = requests.get(url, timeout=10)
        data = response.json()["data"][0]
        value = int(data["value"])
        label = data["value_classification"]

        if value < 25:
            bull_mod = 10
            bear_mod = 0
        elif value < 40:
            bull_mod = 7
            bear_mod = 2
        elif value > 75:
            bull_mod = 0
            bear_mod = 10
        elif value > 60:
            bull_mod = 2
            bear_mod = 7
        else:
            bull_mod = 5
            bear_mod = 5

        return {"value": value, "label": label, "bull_mod": bull_mod, "bear_mod": bear_mod}

    except Exception:
        return {"value": 50, "label": "neutral", "bull_mod": 5, "bear_mod": 5}


# =============================================================================
# TELEGRAM — Notificaciones de señales
# =============================================================================

TELEGRAM_SILENT = False   # True cuando --silent: suprime notificaciones por trade


def send_telegram(message: str):
    """Envía un mensaje al chat de Telegram configurado.
    Requiere variables de entorno TELEGRAM_TOKEN y TELEGRAM_CHAT_ID.
    Si no están definidas, no hace nada (modo silencioso)."""
    if TELEGRAM_SILENT:
        return
    token   = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                      timeout=10)
    except Exception:
        pass   # fallo silencioso: las notificaciones no deben romper el bot


def _tg_open(side: str, pair: str, price: float, sl: float, tp: float, score: int, atr: float,
             trade_type: str = "intraday", amount_usdt: float = 0, balance: float = 0):
    emoji = "📈" if side == "LONG" else "📉"
    dir_es = "LONG (compra)" if side == "LONG" else "SHORT (venta)"
    swing_tag = " 🔥 <b>[SWING]</b>" if trade_type == "swing" else ""
    size_line = ""
    if amount_usdt > 0 and balance > 0:
        pct = amount_usdt / balance * 100
        size_line = f"Inversión: <b>{amount_usdt:,.2f} USDT ({pct:.1f}% del balance)</b>\n"
    send_telegram(
        f"{emoji} <b>SEÑAL {dir_es}</b>{swing_tag}\n"
        f"Par: <b>{pair}</b>\n"
        f"Precio entrada: <b>{price:,.2f} USDT</b>\n"
        f"{size_line}"
        f"Stop Loss:   {sl:,.2f} USDT  ({abs(price-sl)/price*100:.2f}%)\n"
        f"Take Profit: {tp:,.2f} USDT  ({abs(tp-price)/price*100:.2f}%)\n"
        f"Score: {score} | ATR: {atr:.0f}"
    )


def _tg_update(pair: str, side: str, msg: str, sl: float, tp: float):
    """Notificación de cambio en posición abierta (SL movido, TP extendido, swing activado)."""
    send_telegram(
        f"⚙️ <b>ACTUALIZACIÓN {side} {pair}</b>\n"
        f"{msg}\n"
        f"Nuevo SL: {sl:,.2f} USDT\n"
        f"Nuevo TP: {tp:,.2f} USDT"
    )


def _tg_close(side: str, pair: str, price: float, pnl: float, pnl_pct: float,
              reason: str, balance: float):
    if pnl >= 0:
        emoji = "✅"
        res = "GANANCIA"
    else:
        emoji = "❌"
        res = "PÉRDIDA"
    reason_es = {"TAKE_PROFIT": "Take Profit alcanzado", "STOP_LOSS": "Stop Loss tocado",
                 "SENAL_BAJISTA": "Señal bajista", "SENAL_ALCISTA": "Señal alcista"}.get(reason, reason)
    send_telegram(
        f"{emoji} <b>CERRAR {side} — {res}</b>\n"
        f"Par: <b>{pair}</b>\n"
        f"Precio cierre: <b>{price:,.2f} USDT</b>\n"
        f"PnL: <b>{pnl:+.2f} USDT ({pnl_pct:+.2f}%)</b>\n"
        f"Motivo: {reason_es}\n"
        f"Balance: {balance:,.2f} USDT"
    )


# =============================================================================
# SCORING COMBINADO SEPARADO
# =============================================================================

def calculate_scores(technical: dict, sentiment: dict, fear_greed: dict,
                     funding: dict = None, orderbook: dict = None) -> dict:
    """
    Dos scores independientes (0-100):
      bullish_total = tech(0-50) + sentiment(0-15) + fear_greed(0-10) + funding(0-8) + orderbook(0-7)
      Max teorico: 90 → normalizado a 100.
    funding y orderbook son opcionales (neutral en backtest).
    """
    if funding is None:
        funding = {"bull_mod": 3, "bear_mod": 3}
    if orderbook is None:
        orderbook = {"bull_mod": 0, "bear_mod": 0}

    tech_bull = technical.get("bullish_score", 0)
    tech_bear = technical.get("bearish_score", 0)
    sent_bull = sentiment.get("bullish_score", 0)
    sent_bear = sentiment.get("bearish_score", 0)
    fg_bull   = fear_greed.get("bull_mod", 5)
    fg_bear   = fear_greed.get("bear_mod", 5)
    fr_bull   = funding.get("bull_mod", 3)
    fr_bear   = funding.get("bear_mod", 3)
    ob_bull   = orderbook.get("bull_mod", 0)
    ob_bear   = orderbook.get("bear_mod", 0)

    raw_bull = tech_bull + sent_bull + fg_bull + fr_bull + ob_bull
    raw_bear = tech_bear + sent_bear + fg_bear + fr_bear + ob_bear

    # Normalizar (max teorico = 50+15+10+8+7 = 90)
    bullish_total = min(100, round(raw_bull * 100 / 90))
    bearish_total = min(100, round(raw_bear * 100 / 90))

    return {
        "bullish_total": bullish_total,
        "bearish_total": bearish_total,
        "components": {
            "tech_bull": tech_bull, "tech_bear": tech_bear,
            "sent_bull": sent_bull, "sent_bear": sent_bear,
            "fg_bull": fg_bull,     "fg_bear": fg_bear,
            "fr_bull": fr_bull,     "fr_bear": fr_bear,
            "ob_bull": ob_bull,     "ob_bear": ob_bear,
        }
    }


# =============================================================================
# GESTION DE POSICIONES (LONG + SHORT)
# =============================================================================

def open_position(state: dict, pair: str, side: str, price: float,
                  atr: float, risk_profile: dict, score: int,
                  candle_date: str = None) -> Optional[str]:
    """Abre una posicion LONG o SHORT.
    candle_date: 'YYYY-MM-DD' de la vela actual (backtest); si es None
    se usa datetime.now() para el modo live."""
    now = datetime.now().isoformat()

    # Backtest pasa la fecha de la vela; live usa reset por reloj real
    if candle_date:
        if state.get("daily_date") != candle_date:
            state["daily_trades"] = 0
            state["daily_longs"] = 0
            state["daily_shorts"] = 0
            state["daily_date"] = candle_date
    else:
        reset_daily_counter(state)

    if state["position"] is not None:
        return None

    if state["daily_trades"] >= risk_profile["max_daily_trades"]:
        return None

    if score < risk_profile["min_score"]:
        return None

    # Drawdown check
    current = state["balance_usdt"]
    peak = state.get("peak_balance", current)
    if peak > 0 and (peak - current) / peak >= risk_profile["max_drawdown_pct"]:
        return "[DRAWDOWN] Bot pausado"

    # Tamano de posicion
    balance = state["balance_usdt"]
    risk_amount = balance * risk_profile["position_size_pct"]
    stop_distance = atr * risk_profile["stop_loss_atr_mult"]

    if stop_distance == 0 or price == 0 or atr == 0:
        return None

    amount = risk_amount / stop_distance
    cost = amount * price
    max_cost = balance * risk_profile["position_size_pct"] * 5
    if cost > max_cost:
        amount = max_cost / price
        cost = max_cost
    if cost > balance * 0.95:
        amount = (balance * 0.95) / price
        cost = amount * price

    # SL y TP (TP ajustado segun regimen de mercado)
    tp_base = atr * risk_profile["take_profit_atr_mult"]
    if side == "LONG":
        tp_factor  = risk_profile.get("_long_tp_factor",  1.0)
        stop_loss  = price - stop_distance
        take_profit = price + tp_base * tp_factor
    else:
        tp_factor  = risk_profile.get("_short_tp_factor", 1.0)
        stop_loss  = price + stop_distance
        take_profit = price - tp_base * tp_factor

    state["position"] = {
        "side": side,
        "entry_price": price,
        "amount": amount,
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "initial_sl_distance": stop_distance,   # suelo para el trailing ATR-dinamico
        "highest_price": price,
        "lowest_price": price,
        "opened_candle_index": state.get("current_candle_index"),
        "score_at_entry": score,
        "opened_at": now,
    }
    state["balance_usdt"] -= cost
    state["daily_trades"] += 1
    if side == "LONG":
        state["daily_longs"] = state.get("daily_longs", 0) + 1
    else:
        state["daily_shorts"] = state.get("daily_shorts", 0) + 1

    state["trades"].append({
        "pair": pair, "action": f"OPEN_{side}", "price": price,
        "amount": amount, "score": score, "time": now,
    })

    _tg_open(side, pair, price, stop_loss, take_profit, score, atr,
             trade_type=state.get("position", {}).get("trade_type", "intraday"),
             amount_usdt=cost, balance=state["balance_usdt"] + cost)
    return (
        f"ABRIR {side} {pair} | {amount:.6f} @ {price:.2f} | "
        f"SL: {stop_loss:.2f} | TP: {take_profit:.2f} | Score: {score}"
    )


def close_position(state: dict, pair: str, price: float, reason: str) -> Optional[str]:
    """Cierra la posicion actual."""
    if state["position"] is None:
        return None

    now = datetime.now().isoformat()
    pos = state["position"]
    side = pos["side"]
    entry = pos["entry_price"]
    amount = pos["amount"]

    if side == "LONG":
        pnl = (price - entry) * amount
        pnl_pct = ((price - entry) / entry) * 100
    else:
        pnl = (entry - price) * amount
        pnl_pct = ((entry - price) / entry) * 100

    # Devolver al balance
    if side == "LONG":
        state["balance_usdt"] += amount * price
    else:
        state["balance_usdt"] += (amount * entry) + pnl

    # Stats
    state["stats"]["total_pnl"] += pnl
    state["stats"][f"total_{side.lower()}s"] = state["stats"].get(f"total_{side.lower()}s", 0) + 1
    if pnl > 0:
        state["stats"]["wins"] += 1
        state["stats"]["best_trade"] = max(state["stats"]["best_trade"], pnl)
        state["stats"][f"{side.lower()}_wins"] = state["stats"].get(f"{side.lower()}_wins", 0) + 1
    else:
        state["stats"]["losses"] += 1
        state["stats"]["worst_trade"] = min(state["stats"]["worst_trade"], pnl)

    if state["balance_usdt"] > state.get("peak_balance", 0):
        state["peak_balance"] = state["balance_usdt"]
    current_dd = (state["peak_balance"] - state["balance_usdt"]) / state["peak_balance"] * 100
    if current_dd > state.get("max_drawdown_seen", 0.0):
        state["max_drawdown_seen"] = current_dd

    state["trades"].append({
        "pair": pair, "action": f"CLOSE_{side}", "price": price,
        "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
        "reason": reason, "time": now,
    })

    state["position"] = None

    # Cooldown tras SL: bloquea nuevas entradas durante 4 velas (~1h en 15m)
    # para evitar volver a entrar inmediatamente en un mercado adverso
    if reason == "STOP_LOSS":
        state["sl_cooldown_until"] = state.get("current_candle_index", 0) + 4

    _tg_close(side, pair, price, pnl, pnl_pct, reason, state["balance_usdt"])
    return (
        f"CERRAR {side} {pair} | @ {price:.2f} | Motivo: {reason} | "
        f"PnL: {pnl:+.2f} USDT ({pnl_pct:+.2f}%) | Balance: {state['balance_usdt']:.2f}"
    )


def check_sl_tp(state: dict, pair: str, current_price: float, risk_profile: dict,
                atr: float = 0, scores: Optional[dict] = None) -> Optional[str]:
    """Stop-loss, take-profit y trailing stop.

    Mejoras respecto a la version anterior:
    - Trailing stop basado en ATR actual (se ajusta a la volatilidad del momento,
      no a la distancia fija del momento de entrada).
    - TP adaptativo: si el precio llega al TP pero la senal sigue siendo fuerte,
      se extiende el TP en 1xATR en vez de cerrar (hasta max_tp_extensions veces).
    """
    if state["position"] is None:
        return None

    pos  = state["position"]
    side = pos["side"]
    sl   = pos["stop_loss"]
    tp   = pos["take_profit"]

    # --- Trailing stop con distancia fija + break-even automatico ---
    # 1. Cuando la posicion alcanza +1xATR de beneficio, el SL sube a break-even
    #    (precio de entrada). Desde ese momento el trade no puede terminar en perdida.
    # 2. Una vez en break-even o por encima, aplica trailing con la distancia original
    #    de entrada para acompañar el precio sin apretarlo en consolidaciones.
    if risk_profile["trailing_stop"]:
        sl_distance = pos.get("initial_sl_distance", 0)
        entry        = pos["entry_price"]
        if sl_distance > 0:
            # Break-even mas tarde en bull/bear (correcciones mas bruscas)
            be_mult = risk_profile.get("_breakeven_mult", 1.0)

            if side == "LONG":
                if not pos.get("breakeven_set") and current_price >= entry + sl_distance * be_mult:
                    if entry > sl:
                        pos["stop_loss"] = round(entry, 2)
                        sl = entry
                    pos["breakeven_set"] = True
                    _tg_update(pair, side, "🛡️ SL movido a break-even (trade asegurado)", sl, pos["take_profit"])

                if current_price > pos.get("highest_price", current_price):
                    pos["highest_price"] = current_price
                    new_sl = current_price - sl_distance
                    if new_sl > sl:
                        pos["stop_loss"] = round(new_sl, 2)
                        sl = new_sl
                        _tg_update(pair, side, f"📈 Trailing SL subido (precio: {current_price:,.2f})", sl, pos["take_profit"])
            else:  # SHORT
                if not pos.get("breakeven_set") and current_price <= entry - sl_distance * be_mult:
                    if entry < sl:
                        pos["stop_loss"] = round(entry, 2)
                        sl = entry
                    pos["breakeven_set"] = True
                    _tg_update(pair, side, "🛡️ SL movido a break-even (trade asegurado)", sl, pos["take_profit"])

                if current_price < pos.get("lowest_price", current_price):
                    pos["lowest_price"] = current_price
                    new_sl = current_price + sl_distance
                    if new_sl < sl:
                        pos["stop_loss"] = round(new_sl, 2)
                        sl = new_sl
                        _tg_update(pair, side, f"📉 Trailing SL bajado (precio: {current_price:,.2f})", sl, pos["take_profit"])

    # --- Stop loss ---
    if side == "LONG" and current_price <= sl:
        return close_position(state, pair, current_price, "STOP_LOSS")
    if side == "SHORT" and current_price >= sl:
        return close_position(state, pair, current_price, "STOP_LOSS")

    # --- Take profit adaptativo ---
    tp_hit = (side == "LONG" and current_price >= tp) or \
             (side == "SHORT" and current_price <= tp)

    if tp_hit:
        extensions     = pos.get("tp_extensions", 0)
        # Extensiones base + extra segun regimen (bull da 1 extra en longs, bear en shorts)
        extra = risk_profile.get("_long_max_ext", 0) if side == "LONG" else risk_profile.get("_short_max_ext", 0)
        max_extensions = risk_profile.get("max_tp_extensions", 0) + extra

        # Comprobar si la senal sigue justificando extender
        signal_ok = False
        if scores and atr and atr > 0 and extensions < max_extensions:
            bull = scores.get("bullish_total", 0)
            bear = scores.get("bearish_total", 0)
            min_s = risk_profile["min_score"]
            if side == "LONG"  and bull >= min_s and bull > bear:
                signal_ok = True
            elif side == "SHORT" and bear >= min_s and bear > bull:
                signal_ok = True

        if signal_ok:
            # Extender TP un ATR adicional y subir SL al TP anterior (asegura beneficio)
            extension_size = atr * risk_profile["take_profit_atr_mult"]
            if side == "LONG":
                new_tp = tp + extension_size
                # SL sube al TP anterior: si gira, al menos cerramos en ese nivel
                if tp > sl:
                    pos["stop_loss"] = round(tp, 2)
            else:
                new_tp = tp - extension_size
                if tp < sl:
                    pos["stop_loss"] = round(tp, 2)

            pos["take_profit"]  = round(new_tp, 2)
            pos["tp_extensions"] = extensions + 1
            score_val = scores.get("bullish_total", 0) if side == "LONG" else scores.get("bearish_total", 0)
            _tg_update(pair, side,
                       f"🚀 TP extendido x{extensions+1} (score={score_val}, señal sigue fuerte)",
                       pos["stop_loss"], pos["take_profit"])
            return (f"[TP+{extensions+1}] Senal sigue fuerte (score={score_val}), "
                    f"TP extendido a {new_tp:.2f} | SL asegurado en {pos['stop_loss']:.2f}")

        return close_position(state, pair, current_price, "TAKE_PROFIT")

    return None


# =============================================================================
# DECISION ENGINE
# =============================================================================

def make_decision(state: dict, pair: str, price: float, atr: float,
                  scores: dict, risk_profile: dict, verbose: bool = True,
                  entry_advantage: int = 15, close_threshold: Optional[int] = None,
                  min_hold_candles: int = 0, current_candle_index: Optional[int] = None,
                  technical: Optional[dict] = None, timestamp=None) -> Optional[str]:
    """
    Maquina de estados:
      FLAT  -> puede abrir LONG o SHORT
      LONG  -> puede cerrar si senal bajista fuerte
      SHORT -> puede cerrar si senal alcista fuerte
    """
    bull_score = scores["bullish_total"]
    bear_score = scores["bearish_total"]
    min_score = risk_profile["min_score"]
    position = state["position"]

    # Si no se especifica, el umbral de cierre es 15 puntos inferior al de entrada.
    if close_threshold is None:
        close_threshold = max(min_score - 15, 35)

    # Permanencia minima: solo bloquea cierres por senal contraria;
    # SL y TP se siguen respetando siempre.
    hold_candles = 0
    if position and current_candle_index is not None:
        opened_index = position.get("opened_candle_index")
        if opened_index is not None:
            hold_candles = max(0, current_candle_index - opened_index)
    can_close_by_signal = hold_candles >= min_hold_candles

    if position is None:
        # Cooldown post-SL
        sl_cooldown = state.get("sl_cooldown_until", 0)
        current_idx = current_candle_index or 0
        if current_idx > 0 and current_idx < sl_cooldown:
            return None

        # FLAT — aplica filtro fin de semana si hay timestamp disponible
        ts = timestamp if timestamp is not None else datetime.now()
        tech = technical or {}

        # Filtro de sesion: bloquear entradas en apertura NYSE y Londres
        if is_volatile_session(ts):
            return None

        can_long, long_min  = apply_weekend_filter(tech, "LONG",  bull_score, bear_score, risk_profile, ts)
        can_short, short_min = apply_weekend_filter(tech, "SHORT", bull_score, bear_score, risk_profile, ts)

        quality_long  = check_signal_quality(tech, "LONG")
        quality_short = check_signal_quality(tech, "SHORT")

        # Ajuste de regimen: min_score distinto para LONG y SHORT (igual que backtest)
        regime_long_min  = long_min  + risk_profile.get("_long_min_bonus",  0)
        regime_short_min = short_min + risk_profile.get("_short_min_bonus", 0)

        # HTF filter: penaliza entradas contra la tendencia de 4h
        htf_trend = tech.get("details", {}).get("htf_trend", "lateral")
        htf_long_penalty  = 20 if htf_trend == "bajista" else 0
        htf_short_penalty = 20 if htf_trend == "alcista" else 0
        eff_long_min  = regime_long_min  + htf_long_penalty
        eff_short_min = regime_short_min + htf_short_penalty

        # Consolidacion: ATR contraido → umbral mas alto
        if tech.get("details", {}).get("consolidacion", False):
            eff_long_min  += 10
            eff_short_min += 10

        if (can_long and bull_score >= eff_long_min
                and bull_score > bear_score + entry_advantage
                and quality_long):
            if verbose:
                prefix = "[FDS-RANGO] " if is_weekend(ts) else ""
                htf_note = f" [HTF:{htf_trend}]" if htf_long_penalty else ""
                logger.decision(pair, bull_score, bear_score, eff_long_min, None,
                              f"{prefix}ABRIR LONG (bull={bull_score} >= {eff_long_min}, ventaja={bull_score - bear_score}){htf_note}")
            return open_position(state, pair, "LONG", price, atr, risk_profile, bull_score)

        elif (can_short and bear_score >= eff_short_min
                and bear_score > bull_score + entry_advantage
                and quality_short):
            if verbose:
                prefix = "[FDS-RANGO] " if is_weekend(ts) else ""
                htf_note = f" [HTF:{htf_trend}]" if htf_short_penalty else ""
                logger.decision(pair, bull_score, bear_score, eff_short_min, None,
                              f"{prefix}ABRIR SHORT (bear={bear_score} >= {eff_short_min}, ventaja={bear_score - bull_score}){htf_note}")
            return open_position(state, pair, "SHORT", price, atr, risk_profile, bear_score)

        else:
            if verbose:
                logger.decision(pair, bull_score, bear_score, min_score, None,
                              f"HOLD (scores insuficientes o sin ventaja clara)")
            return None

    elif position["side"] == "LONG":
        if can_close_by_signal and bear_score >= close_threshold and bear_score > bull_score + entry_advantage:
            if verbose:
                logger.decision(pair, bull_score, bear_score, min_score, position,
                              f"CERRAR LONG (bear={bear_score} >= {close_threshold})")
            return close_position(state, pair, price, "SENAL_BAJISTA")
        else:
            if verbose:
                unrealized = (price - position["entry_price"]) * position["amount"]
                logger.decision(pair, bull_score, bear_score, min_score, position,
                              f"MANTENER LONG (PnL: {unrealized:+.2f})")
            return None

    elif position["side"] == "SHORT":
        if can_close_by_signal and bull_score >= close_threshold and bull_score > bear_score + entry_advantage:
            if verbose:
                logger.decision(pair, bull_score, bear_score, min_score, position,
                              f"CERRAR SHORT (bull={bull_score} >= {close_threshold})")
            return close_position(state, pair, price, "SENAL_ALCISTA")
        else:
            if verbose:
                unrealized = (position["entry_price"] - price) * position["amount"]
                logger.decision(pair, bull_score, bear_score, min_score, position,
                              f"MANTENER SHORT (PnL: {unrealized:+.2f})")
            return None

    return None


# =============================================================================
# BACKTESTING
# =============================================================================

def run_backtest(exchange, pair: str, timeframe: str, days: int, risk_profile: dict,
                 entry_advantage: int, close_threshold: Optional[int],
                 min_hold_candles: int, news_file: Optional[str] = None,
                 data_file: Optional[str] = None,
                 _df_override: Optional[object] = None,
                 _daily_sentiment: Optional[dict] = None,
                 auto_regime: bool = False):
    """Backtesting con datos historicos.
    data_file: CSV precacheado. _df_override: DataFrame ya cargado (uso interno
    del optimizer para evitar I/O en cada combinacion)."""
    logger.log("=" * 70)
    logger.log(f"  BACKTESTING - {pair}")
    logger.log(f"  Periodo: {days} dias | Timeframe: {timeframe}")
    logger.log(f"  Perfil: min_score={risk_profile['min_score']} "
              f"SL={risk_profile['stop_loss_atr_mult']}xATR "
              f"TP={risk_profile['take_profit_atr_mult']}xATR")
    logger.log("=" * 70)

    if _df_override is not None:
        df = _df_override.copy()
    elif data_file and Path(data_file).exists():
        logger.log(f"Cargando datos desde cache: {data_file}")
        df = pd.read_csv(data_file, parse_dates=["timestamp"])
    else:
        df = fetch_historical_ohlcv(exchange, pair, timeframe, days)

    if len(df) < 200:
        logger.log(f"ERROR: Solo {len(df)} velas. Se necesitan minimo 200.", "ERROR")
        return

    # Estado limpio
    state = {
        "balance_usdt": 1000.0,
        "position": None,
        "trades": [],
        "daily_trades": 0,
        "daily_longs": 0,
        "daily_shorts": 0,
        "daily_date": "",
        "stats": {
            "wins": 0, "losses": 0, "total_pnl": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "total_longs": 0, "total_shorts": 0,
            "long_wins": 0, "short_wins": 0,
        },
        "peak_balance": 1000.0,
        "created_at": datetime.now().isoformat(),
    }

    # Sentimiento historico: inyectado por el optimizer, o cargado desde fichero
    if _daily_sentiment is not None:
        daily_sentiment = _daily_sentiment
    elif news_file:
        daily_sentiment = load_daily_sentiment(news_file)
        logger.log(f"Sentimiento historico cargado desde {news_file} "
                  f"({len(daily_sentiment)} dias con noticias)")
    else:
        daily_sentiment = {}
        logger.log("Sin --news-file: usando sentimiento neutral fijo (comportamiento anterior)")

    sentiment_neutral = {"bullish_score": 7, "bearish_score": 7, "sentiment": "neutral", "news": []}
    fear_greed = {"value": 50, "label": "neutral", "bull_mod": 5, "bear_mod": 5}

    start_idx = 200
    total_candles = len(df)
    trades_log = []

    # Pre-computar todos los indicadores de una sola vez (O(n) en vez de O(n*k))
    df = precompute_indicators(df)

    logger.log(f"Procesando {total_candles - start_idx} velas...")
    logger.log("")

    for i in range(start_idx, total_candles):
        current_price = float(df["close"].iloc[i])
        current_time = df["timestamp"].iloc[i]

        # Reset diario
        current_day = current_time.strftime("%Y-%m-%d")
        if state["daily_date"] != current_day:
            state["daily_trades"] = 0
            state["daily_longs"] = 0
            state["daily_shorts"] = 0
            state["daily_date"] = current_day

        # Indice de vela actual: lo usamos para respetar min-hold-candles
        state["current_candle_index"] = i

        # Tecnico (usa filas pre-calculadas, sin recalcular indicadores)
        technical = analyze_technical(None, row=df.iloc[i], prev_row=df.iloc[i - 1])
        sentiment = daily_sentiment.get(current_day, sentiment_neutral)
        scores = calculate_scores(technical, sentiment, fear_greed)
        atr = technical.get("details", {}).get("atr", 0)

        # Régimen automático: recalcular por vela si --regime auto
        if auto_regime:
            detected = detect_regime_auto(df.iloc[i])
            if detected != risk_profile.get("_regime"):
                risk_profile = apply_regime(risk_profile, detected)

        # SL/TP (recibe ATR y scores para trailing adaptativo y TP extensible)
        sl_tp_msg = check_sl_tp(state, pair, current_price, risk_profile, atr=atr, scores=scores)
        if sl_tp_msg:
            logger.log(f"  [{current_time}] >> {sl_tp_msg}")

        # Decision (sin verbose para no saturar)
        bull_score = scores["bullish_total"]
        bear_score = scores["bearish_total"]
        min_score = risk_profile["min_score"]
        effective_close_threshold = close_threshold if close_threshold is not None else max(min_score - 15, 35)
        position = state["position"]

        result = None

        if position is None:
            # Cooldown post-SL: no entrar durante 4 velas tras un stop loss
            sl_cooldown = state.get("sl_cooldown_until", 0)
            if i < sl_cooldown:
                continue

            # Filtro de sesion: no entrar en apertura NYSE (14:30-15:10 UTC) ni Londres (08:00-08:30 UTC)
            if is_volatile_session(current_time):
                continue

            # Filtro fin de semana: ajusta min_score y exige condicion de rango BB
            can_long, long_min = apply_weekend_filter(
                technical, "LONG", bull_score, bear_score, risk_profile, current_time)
            can_short, short_min = apply_weekend_filter(
                technical, "SHORT", bull_score, bear_score, risk_profile, current_time)

            # Ajuste de regimen: min_score distinto para LONG y SHORT
            regime_long_min  = long_min  + risk_profile.get("_long_min_bonus",  0)
            regime_short_min = short_min + risk_profile.get("_short_min_bonus", 0)

            # HTF filter: penaliza entradas contra la tendencia de 4h
            htf_trend = technical.get("details", {}).get("htf_trend", "lateral")
            htf_long_penalty  = 20 if htf_trend == "bajista" else 0
            htf_short_penalty = 20 if htf_trend == "alcista" else 0

            # News shock: dia con noticias muy extremas rebaja el umbral alineado
            news_shock = sentiment.get("shock")
            shock_long_bonus  = 15 if news_shock == "bull" else 0
            shock_short_bonus = 15 if news_shock == "bear" else 0

            eff_long_min  = regime_long_min  + htf_long_penalty  - shock_long_bonus
            eff_short_min = regime_short_min + htf_short_penalty - shock_short_bonus

            # Consolidacion: ATR contraido → señales poco fiables, subir umbral
            if technical.get("details", {}).get("consolidacion", False):
                eff_long_min  += 10
                eff_short_min += 10

            if (can_long and bull_score >= eff_long_min
                    and bull_score > bear_score + entry_advantage
                    and check_signal_quality(technical, "LONG")):
                trade_type   = classify_trade(technical, "LONG", scores)
                active_prof  = apply_regime(RISK_PROFILES["swing"], risk_profile.get("_regime", "neutral")) \
                               if trade_type == "swing" else risk_profile
                active_hold  = active_prof.get("_swing_min_hold", min_hold_candles) \
                               if trade_type == "swing" else min_hold_candles
                result = open_position(state, pair, "LONG", current_price, atr, active_prof, bull_score, current_day)
                if state["position"]:
                    state["position"]["trade_type"]       = trade_type
                    state["position"]["min_hold_candles"] = active_hold
                    if state["trades"]:
                        state["trades"][-1]["trade_type"] = trade_type
            elif (can_short and bear_score >= eff_short_min
                    and bear_score > bull_score + entry_advantage
                    and check_signal_quality(technical, "SHORT")):
                trade_type   = classify_trade(technical, "SHORT", scores)
                active_prof  = apply_regime(RISK_PROFILES["swing"], risk_profile.get("_regime", "neutral")) \
                               if trade_type == "swing" else risk_profile
                active_hold  = active_prof.get("_swing_min_hold", min_hold_candles) \
                               if trade_type == "swing" else min_hold_candles
                result = open_position(state, pair, "SHORT", current_price, atr, active_prof, bear_score, current_day)
                if state["position"]:
                    state["position"]["trade_type"]       = trade_type
                    state["position"]["min_hold_candles"] = active_hold
                    if state["trades"]:
                        state["trades"][-1]["trade_type"] = trade_type
        elif position["side"] == "LONG":
            hold_candles = i - state["position"].get("opened_candle_index", i) if state["position"] else 0
            pos_min_hold = state["position"].get("min_hold_candles", min_hold_candles)
            can_close_by_signal = hold_candles >= pos_min_hold
            if can_close_by_signal and bear_score >= effective_close_threshold and bear_score > bull_score + entry_advantage:
                result = close_position(state, pair, current_price, "SENAL_BAJISTA")
        elif position["side"] == "SHORT":
            hold_candles = i - state["position"].get("opened_candle_index", i) if state["position"] else 0
            pos_min_hold = state["position"].get("min_hold_candles", min_hold_candles)
            can_close_by_signal = hold_candles >= pos_min_hold
            if can_close_by_signal and bull_score >= effective_close_threshold and bull_score > bear_score + entry_advantage:
                result = close_position(state, pair, current_price, "SENAL_ALCISTA")

        if result:
            logger.log(f"  [{current_time}] Bull:{bull_score:3d} Bear:{bear_score:3d} | {result}")

        # Progreso cada 1000 velas
        if (i - start_idx) % 1000 == 0 and i > start_idx:
            pct = (i - start_idx) / (total_candles - start_idx) * 100
            logger.log(f"  ... {pct:.0f}% ({i - start_idx}/{total_candles - start_idx} velas) "
                      f"Balance: {state['balance_usdt']:.2f}")

    # Cerrar posicion abierta al final
    if state["position"] is not None:
        final_price = float(df["close"].iloc[-1])
        result = close_position(state, pair, final_price, "FIN_BACKTEST")
        if result:
            logger.log(f"  [FIN] >> {result}")

    # RESULTADOS
    stats = state["stats"]
    total_trades = stats["wins"] + stats["losses"]
    final_balance = state["balance_usdt"]
    total_return = ((final_balance - 1000) / 1000) * 100

    logger.log("")
    logger.log("=" * 70)
    logger.log("  RESULTADOS DEL BACKTEST")
    logger.log("=" * 70)
    logger.log(f"  Periodo:         {df['timestamp'].iloc[start_idx]} -> {df['timestamp'].iloc[-1]}")
    logger.log(f"  Velas:           {total_candles - start_idx}")
    logger.log(f"  Balance inicial: 1000.00 USDT")
    logger.log(f"  Balance final:   {final_balance:.2f} USDT")
    logger.log(f"  Rendimiento:     {total_return:+.2f}%")
    logger.log(f"  PnL total:       {stats['total_pnl']:+.2f} USDT")
    logger.log(f"  Peak balance:    {state['peak_balance']:.2f} USDT")
    max_dd = state.get("max_drawdown_seen", 0.0)
    logger.log(f"  Max drawdown:    {max_dd:.1f}%")
    logger.log(f"")
    logger.log(f"  Total trades:    {total_trades}")
    logger.log(f"  Wins:            {stats['wins']}")
    logger.log(f"  Losses:          {stats['losses']}")
    if total_trades > 0:
        logger.log(f"  Win Rate:        {stats['wins']/total_trades*100:.1f}%")
        avg_pnl = stats['total_pnl'] / total_trades
        logger.log(f"  PnL medio/trade: {avg_pnl:+.2f} USDT")
    logger.log(f"  Longs:           {stats.get('total_longs', 0)} (wins: {stats.get('long_wins', 0)})")
    logger.log(f"  Shorts:          {stats.get('total_shorts', 0)} (wins: {stats.get('short_wins', 0)})")
    logger.log(f"  Mejor trade:     {stats['best_trade']:+.2f} USDT")
    logger.log(f"  Peor trade:      {stats['worst_trade']:+.2f} USDT")
    logger.log("=" * 70)

    # Guardar (solo cuando se llama directamente, no desde el optimizer)
    if _df_override is None:
        results_file = f"backtest_{pair.replace('/', '_')}_{days}d.json"
        save_state(state, results_file)
        logger.log(f"  Detalle en: {results_file}")
        logger.log(f"  Log en: {logger.log_file}")

    return state


# =============================================================================
# MODO LIVE
# =============================================================================

def fetch_funding_oi(exchange, pair: str) -> dict:
    """Obtiene funding rate y open interest de futuros perpetuos.
    Funding negativo = shorts pagando a longs = señal alcista contrarian.
    OI en cache porque cambia despacio (actualizacion cada 15 min en live)."""
    try:
        futures_pair = pair if ":" in pair else pair.replace("/USDT", "/USDT:USDT")
        fr_data = exchange.fetch_funding_rate(futures_pair)
        fr = fr_data.get("fundingRate", 0) or 0
        # Scoring: funding muy negativo = alcista, muy positivo = bajista
        if fr < -0.0002:
            bull_mod, bear_mod = 8, 0
        elif fr < -0.0001:
            bull_mod, bear_mod = 6, 1
        elif fr < 0:
            bull_mod, bear_mod = 4, 2
        elif fr < 0.0002:
            bull_mod, bear_mod = 3, 3
        elif fr < 0.0005:
            bull_mod, bear_mod = 1, 6
        else:
            bull_mod, bear_mod = 0, 8
        return {"funding_rate": fr, "bull_mod": bull_mod, "bear_mod": bear_mod}
    except Exception:
        return {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3}


def fetch_orderbook_signals(exchange, pair: str, current_price: float) -> dict:
    """Detecta muros de liquidez en el order book (bid/ask walls).
    Un muro de bids bajo el precio = soporte fuerte (alcista).
    Un muro de asks sobre el precio = resistencia fuerte (bajista)."""
    try:
        ob = exchange.fetch_order_book(pair, 50)
        bids = [(b[0], b[0] * b[1]) for b in ob["bids"] if b[1] > 0]
        asks = [(a[0], a[0] * a[1]) for a in ob["asks"] if a[1] > 0]
        if not bids or not asks:
            return {"support_walls": [], "resistance_walls": [], "bull_mod": 0, "bear_mod": 0}
        bid_mean = sum(b[1] for b in bids) / len(bids)
        ask_mean = sum(a[1] for a in asks) / len(asks)
        # Muro = nivel con notional > 3x la media
        support_walls    = [b[0] for b in bids if b[1] > 3 * bid_mean]
        resistance_walls = [a[0] for a in asks if a[1] > 3 * ask_mean]
        bull_mod = bear_mod = 0
        # Precio cerca (0.5%) de un muro de soporte por debajo
        for w in support_walls:
            if current_price * 0.995 <= w <= current_price:
                bull_mod = 7; break
        # Precio cerca (0.5%) de un muro de resistencia por encima
        for w in resistance_walls:
            if current_price <= w <= current_price * 1.005:
                bear_mod = 7; break
        return {
            "support_walls": support_walls[:5],
            "resistance_walls": resistance_walls[:5],
            "bull_mod": bull_mod,
            "bear_mod": bear_mod,
        }
    except Exception:
        return {"support_walls": [], "resistance_walls": [], "bull_mod": 0, "bear_mod": 0}


def fetch_htf_context(exchange, pair: str) -> dict:
    """Descarga las ultimas 60 velas de 4h y devuelve la tendencia HTF para el modo live."""
    try:
        ohlcv = exchange.fetch_ohlcv(pair, "4h", limit=60)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["ema_9"]  = ta.ema(df["close"], length=9)
        df["ema_21"] = ta.ema(df["close"], length=21)
        df["ema_50"] = ta.ema(df["close"], length=50)
        df["rsi"]    = ta.rsi(df["close"], length=14)
        last = df.iloc[-1]
        e9, e21, e50 = last.get("ema_9"), last.get("ema_21"), last.get("ema_50")
        if pd.notna(e9) and pd.notna(e21) and pd.notna(e50):
            if e9 > e21 > e50:
                trend = "alcista"
            elif e9 < e21 < e50:
                trend = "bajista"
            else:
                trend = "lateral"
        else:
            trend = "calculando"
        rsi_val = round(last.get("rsi", 50), 1) if pd.notna(last.get("rsi")) else 50
        return {"htf_trend": trend, "htf_rsi": rsi_val}
    except Exception:
        return {"htf_trend": "lateral", "htf_rsi": 50}


def run_live(exchange, pair: str, timeframe: str, interval: int, risk_profile: dict,
             entry_advantage: int, close_threshold: Optional[int],
             min_hold_candles: int, profile_name: Optional[str] = None):
    """Ejecucion en tiempo real (paper trading por defecto, real con --live)."""
    slug = profile_name or pair.replace("/", "_")
    state_file = f"paper_{slug}_state.json"
    state = load_state(state_file)

    # Log especifico por perfil para poder comparar varios en paralelo
    if profile_name:
        logger.log_file = f"paper_{slug}.log"

    print("\n" + "=" * 70)
    print(f"  Bot de Trading v3.0 - LONG & SHORT  [perfil: {slug}]")
    print(f"  Par: {pair}")
    print(f"  Exchange: {exchange.id} | Timeframe: {timeframe}")
    print(f"  Riesgo: score_min={risk_profile['min_score']} | "
          f"SL={risk_profile['stop_loss_atr_mult']}xATR | "
          f"TP={risk_profile['take_profit_atr_mult']}xATR")
    print(f"  Balance: {state['balance_usdt']:.2f} USDT | PnL: {state['stats']['total_pnl']:+.2f}")
    print(f"  Trailing stop: {'SI' if risk_profile['trailing_stop'] else 'NO'}")
    print(f"  Max trades/dia: {risk_profile['max_daily_trades']}")
    if state["position"]:
        pos = state["position"]
        print(f"  Posicion abierta: {pos['side']} desde {pos['entry_price']:.2f}")
    print(f"  Log: {logger.log_file}")
    print(f"  Estado: {state_file}")
    print(f"  Ctrl+C para detener")
    print("=" * 70 + "\n")

    # Guarda los parametros del perfil en el estado para que compare_profiles.py los muestre
    state["risk_profile"] = {
        "min_score":            risk_profile.get("min_score"),
        "stop_loss_atr_mult":   risk_profile.get("stop_loss_atr_mult"),
        "take_profit_atr_mult": risk_profile.get("take_profit_atr_mult"),
    }

    # Caches
    sentiment_cache  = {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral", "news": []}
    fear_greed_cache = {"value": 50, "label": "neutral", "bull_mod": 5, "bear_mod": 5}
    htf_cache        = {"htf_trend": "lateral", "htf_rsi": 50}
    funding_cache    = {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3}
    ob_cache         = {"support_walls": [], "resistance_walls": [], "bull_mod": 0, "bear_mod": 0}
    last_sentiment = datetime.min
    last_fg        = datetime.min
    last_htf       = datetime.min
    last_funding   = datetime.min
    last_ob        = datetime.min

    while True:
        try:
            now = datetime.now()

            # HTF context (cada 4 horas)
            if now - last_htf > timedelta(hours=4):
                htf_cache = fetch_htf_context(exchange, pair)
                last_htf  = now
                logger.log(f"[HTF-4h] Tendencia: {htf_cache['htf_trend']} | RSI: {htf_cache['htf_rsi']}")

            # Fear & Greed (cada 10 min)
            if now - last_fg > timedelta(minutes=10):
                fear_greed_cache = fetch_fear_greed()
                last_fg = now
                logger.log(f"[F&G] Index: {fear_greed_cache['value']} ({fear_greed_cache['label']}) "
                          f"-> Bull+{fear_greed_cache['bull_mod']} Bear+{fear_greed_cache['bear_mod']}")

            # Sentimiento (cada 5 min)
            if now - last_sentiment > timedelta(minutes=5):
                # Siempre BTC como proxy: mayor cobertura y es el indicador macro de todo crypto
                sentiment_cache = fetch_sentiment("BTC/USDT")
                last_sentiment = now
                if sentiment_cache.get("news"):
                    logger.log(f"[NEWS] {sentiment_cache['sentiment']} "
                              f"(bull:{sentiment_cache['bullish_score']} bear:{sentiment_cache['bearish_score']})")
                    for n in sentiment_cache["news"][:3]:
                        logger.log(f"  [{n['sentiment']}] {n['title']}")

            # Funding Rate (cada 15 min)
            if now - last_funding > timedelta(minutes=15):
                funding_cache = fetch_funding_oi(exchange, pair)
                last_funding = now
                fr = funding_cache.get("funding_rate", 0)
                logger.log(f"[FUNDING] Rate: {fr*100:.4f}% -> Bull+{funding_cache['bull_mod']} Bear+{funding_cache['bear_mod']}")

            # Datos
            df = fetch_ohlcv(exchange, pair, timeframe)
            state["current_candle_index"] = int(df["timestamp"].iloc[-1].timestamp())
            current_price = float(df["close"].iloc[-1])
            state["current_candle_index"] = int(df["timestamp"].iloc[-1].timestamp())

            # Order Book (cada ciclo, datos en tiempo real)
            if now - last_ob > timedelta(minutes=1):
                ob_cache = fetch_orderbook_signals(exchange, pair, current_price)
                last_ob = now
                if ob_cache["bull_mod"] > 0:
                    logger.log(f"[OB] Muro soporte detectado: {ob_cache['support_walls'][:2]}")
                elif ob_cache["bear_mod"] > 0:
                    logger.log(f"[OB] Muro resistencia detectado: {ob_cache['resistance_walls'][:2]}")

            # SL/TP
            # Analisis (va primero para tener ATR y scores disponibles para check_sl_tp)
            technical = analyze_technical(df)
            # Inyectar contexto HTF (viene del cache de 4h, no del df de 15m)
            technical["details"]["htf_trend"] = htf_cache["htf_trend"]
            technical["details"]["htf_rsi"]   = htf_cache["htf_rsi"]
            scores = calculate_scores(technical, sentiment_cache, fear_greed_cache, funding_cache, ob_cache)
            atr = technical.get("details", {}).get("atr", 0)

            sl_tp_msg = check_sl_tp(state, pair, current_price, risk_profile, atr=atr, scores=scores)
            if sl_tp_msg:
                logger.log(f">> {sl_tp_msg}")

            # Info posicion
            pos_info = "FLAT"
            if state["position"]:
                pos = state["position"]
                if pos["side"] == "LONG":
                    unrealized = (current_price - pos["entry_price"]) * pos["amount"]
                else:
                    unrealized = (pos["entry_price"] - current_price) * pos["amount"]
                pos_info = (f"{pos['side']} PnL:{unrealized:+.2f} "
                          f"SL:{pos['stop_loss']:.0f} TP:{pos['take_profit']:.0f}")

            # Log principal
            ts = now.strftime("%H:%M:%S")
            details = technical.get("details", {})
            comp = scores["components"]
            logger.log(
                f"[{ts}] {pair} {current_price:.2f} | "
                f"Bull:{scores['bullish_total']:3d} Bear:{scores['bearish_total']:3d} | "
                f"T[{comp['tech_bull']}/{comp['tech_bear']}] "
                f"S[{comp['sent_bull']}/{comp['sent_bear']}] "
                f"F[{comp['fg_bull']}/{comp['fg_bear']}] "
                f"FR[{comp['fr_bull']}/{comp['fr_bear']}] "
                f"OB[{comp['ob_bull']}/{comp['ob_bear']}] | "
                f"{details.get('trend', '?')} RSI:{details.get('rsi', '?')} | "
                f"{pos_info}"
            )

            # Trades hoy
            reset_daily_counter(state)
            logger.log(f"  Trades hoy: {state['daily_trades']}/{risk_profile['max_daily_trades']} | "
                      f"Drawdown: {((state.get('peak_balance',1000) - state['balance_usdt']) / state.get('peak_balance',1000) * 100):.1f}%")

            # Decision
            msg = make_decision(
                state, pair, current_price, atr, scores, risk_profile,
                entry_advantage=entry_advantage,
                close_threshold=close_threshold,
                min_hold_candles=min_hold_candles,
                current_candle_index=state["current_candle_index"],
                technical=technical,
            )
            if msg:
                logger.log(f">> {msg}")

            save_state(state, state_file)

        except KeyboardInterrupt:
            print("\n")
            logger.log("=" * 70)
            logger.log("Bot detenido")
            logger.log(f"Balance: {state['balance_usdt']:.2f} USDT")
            logger.log(f"PnL: {state['stats']['total_pnl']:+.2f} USDT")
            s = state["stats"]
            logger.log(f"Win/Loss: {s['wins']}/{s['losses']}")
            if s["wins"] + s["losses"] > 0:
                logger.log(f"Win Rate: {s['wins']/(s['wins']+s['losses'])*100:.1f}%")
            logger.log(f"Longs: {s.get('total_longs',0)} (wins: {s.get('long_wins',0)})")
            logger.log(f"Shorts: {s.get('total_shorts',0)} (wins: {s.get('short_wins',0)})")
            if state["position"]:
                logger.log(f"Posicion abierta: {state['position']['side']} "
                          f"desde {state['position']['entry_price']:.2f}")
            logger.log(f"Estado: {state_file}")
            logger.log(f"Log: {logger.log_file}")
            logger.log("=" * 70)
            save_state(state, state_file)
            break

        except Exception as e:
            logger.log(f"[ERROR] {e}", "ERROR")

        time.sleep(interval)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Bot Trading v3.0 - Long & Short + Backtest")
    parser.add_argument("--pair", default="BTC/USDT",
                        help="Par (ej. BTC/USDT, ETH/USDT, SOL/USDT)")
    parser.add_argument("--exchange", default="bybit",
                        help="Exchange: bybit, kraken, okx, bitget")
    parser.add_argument("--risk", default="moderate",
                        choices=["conservative", "moderate", "aggressive"],
                        help="Perfil de riesgo")
    parser.add_argument("--regime", default="neutral",
                        choices=["neutral", "bull", "bear", "auto"],
                        help="Regimen de mercado: neutral/bull/bear o 'auto' para deteccion automatica via EMA semanal")
    parser.add_argument("--timeframe", default="15m",
                        help="Temporalidad: 1m, 5m, 15m, 1h, 4h")
    parser.add_argument("--interval", type=int, default=60,
                        help="Segundos entre ciclos (modo live)")
    parser.add_argument("--backtest", action="store_true",
                        help="Ejecutar backtesting")
    parser.add_argument("--days", type=int, default=365,
                        help="Dias de historico para backtest")
    parser.add_argument("--live", action="store_true",
                        help="Modo real (requiere API keys)")
    parser.add_argument("--stop-loss", type=float,
                        help="Override: multiplicador ATR para SL")
    parser.add_argument("--take-profit", type=float,
                        help="Override: multiplicador ATR para TP")
    parser.add_argument("--min-score", type=int,
                        help="Override: score minimo (0-100)")
    parser.add_argument("--entry-advantage", type=int, default=15,
                        help="Ventaja minima entre score alcista y bajista para abrir")
    parser.add_argument("--close-threshold", type=int, default=None,
                        help="Score minimo de senal contraria para cerrar")
    parser.add_argument("--min-hold-candles", type=int, default=0,
                        help="Velas minimas antes de cerrar por senal contraria")
    parser.add_argument("--max-daily-trades", type=int, default=None,
                        help="Maximo de operaciones diarias")
    parser.add_argument("--data-file", default=None,
                        help="CSV con datos OHLCV precacheados (evita descargar del exchange)")
    parser.add_argument("--news-file", default=None,
                        help="JSON de noticias historicas (de fetch_historical_news.py) para el backtest")
    parser.add_argument("--name", default=None,
                        help="Nombre del perfil (paper trading): identifica estado y log. Ej: --name bull_mod")
    parser.add_argument("--silent", action="store_true",
                        help="Suprime notificaciones Telegram por trade (usar con modo multi-bot)")
    args = parser.parse_args()

    if args.silent:
        global TELEGRAM_SILENT
        TELEGRAM_SILENT = True

    # Risk con overrides
    auto_regime = args.regime == "auto"
    risk_profile = apply_regime(RISK_PROFILES[args.risk], "neutral" if auto_regime else args.regime)
    if args.stop_loss:
        risk_profile["stop_loss_atr_mult"] = args.stop_loss
    if args.take_profit:
        risk_profile["take_profit_atr_mult"] = args.take_profit
    if args.min_score is not None:
        risk_profile["min_score"] = args.min_score
    if args.max_daily_trades is not None:
        risk_profile["max_daily_trades"] = args.max_daily_trades

    if not 0 <= risk_profile["min_score"] <= 100:
        parser.error("min-score debe estar entre 0 y 100")
    if risk_profile["max_daily_trades"] < 1:
        parser.error("max-daily-trades debe ser mayor que 0")

    if args.entry_advantage < 0 or args.min_hold_candles < 0:
        parser.error("entry-advantage y min-hold-candles no pueden ser negativos")
    if args.close_threshold is not None and not 0 <= args.close_threshold <= 100:
        parser.error("close-threshold debe estar entre 0 y 100")

    # Exchange
    exchange_class = getattr(ccxt, args.exchange)
    config = {}
    if args.live:
        config["apiKey"] = os.environ.get("EXCHANGE_API_KEY", "")
        config["secret"] = os.environ.get("EXCHANGE_SECRET", "")
        if not config["apiKey"]:
            print("ERROR: --live requiere EXCHANGE_API_KEY y EXCHANGE_SECRET")
            return
    exchange = exchange_class(config)

    # Ejecutar
    if args.backtest:
        run_backtest(
            exchange, args.pair, args.timeframe, args.days, risk_profile,
            args.entry_advantage, args.close_threshold, args.min_hold_candles,
            news_file=args.news_file,
            data_file=args.data_file,
            auto_regime=auto_regime,
        )
    else:
        run_live(
            exchange, args.pair, args.timeframe, args.interval, risk_profile,
            args.entry_advantage, args.close_threshold, args.min_hold_candles,
            profile_name=args.name,
        )


if __name__ == "__main__":
    main()
