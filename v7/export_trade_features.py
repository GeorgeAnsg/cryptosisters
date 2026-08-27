"""
V7 Phase 1 — Export trade feature dataset.

Runs the V6 backtest loop for 2023-2026 with a thin feature-capture hook.
Outputs: v7/data/trade_features.csv

Each row = one completed trade:
  - Raw numeric indicators at candle of entry
  - Signal scores + regime
  - Side (LONG=1, SHORT=-1)
  - Target: won (1) or lost (0)
"""

import sys
import csv
import math
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v6.core.bot_core import (
    load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
    fetch_historical_ohlcv,
)
from v6.core.bot_indicators import precompute_indicators
from v6.core.bot_sentiment import load_fear_greed_sentiment
from v6.strategies.strategy_15m import Strategy15m

# ── Config ────────────────────────────────────────────────────────────────────

RISK_PROFILE = {
    "risk_pct":               0.02,
    "max_cost_pct":           0.35,
    "stop_loss_atr_mult":     2.5,
    "take_profit_atr_mult":   4.0,
    "min_score":              58,
    "entry_advantage":        15,
    "max_daily_trades":       6,
    "max_drawdown_pct":       0.10,
    "max_daily_loss_pct":     0.03,
    "trailing_stop":          True,
    "max_tp_extensions":      2,
    "weekend_mode":           "range",
    "weekend_min_score_bonus": 10,
    "min_vol_ratio":          0.0,
}

PAIR       = "BTC/USDT:USDT"
START_DATE = "2023-01-01"   # only post-ETF era for ML training
OUT_PATH   = ROOT / "v7" / "data" / "trade_features.csv"

FEATURE_COLS = [
    # Price-relative EMA ratios
    "ema9_ratio", "ema21_ratio", "ema50_ratio", "ema200_ratio",
    # Momentum
    "rsi", "stochrsi_k", "stochrsi_d",
    # MACD (normalised by ATR)
    "macd_h_norm",
    # Trend
    "adx", "adx_dmp_norm", "adx_dmn_norm",
    # Bollinger position 0-1
    "bb_pct",
    # Volume
    "vol_ratio",
    # ATR contraction
    "atr_contracted",
    # Candle patterns (binary)
    "bull_engulf", "bear_engulf", "hammer", "shooting_star",
    "three_bull", "three_bear",
    # Market structure (binary)
    "ms_bull", "ms_bear",
    # Support/resistance proximity
    "near_channel_top", "near_channel_bot",
    # Hurst mean-reversion indicator
    "hurst_acf1",
    # Signal scores
    "bull_score", "bear_score",
    # Net score in direction of trade (positive = signal aligned)
    "net_score",
    # Regime encoding: bull=1, neutral=0, bear=-1
    "regime_enc",
    # HTF 4h RSI
    "htf_rsi",
    # Side: LONG=1, SHORT=-1
    "side_enc",
]


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _extract_features(row: pd.Series, signal, side: str) -> dict:
    """Extract numerical features from a df row + signal at trade entry."""
    price = _safe_float(row.get("close"), 1.0)
    atr   = _safe_float(row.get("atr"),   1.0) or 1.0

    # EMA ratios relative to price
    ema9  = _safe_float(row.get("ema_9"),   price)
    ema21 = _safe_float(row.get("ema_21"),  price)
    ema50 = _safe_float(row.get("ema_50"),  price)
    ema200= _safe_float(row.get("ema_200"), price)

    # Bollinger: use BBP (percent B) if available, else compute
    bb_pct_raw = row.get("BBP_20_2.0")
    if bb_pct_raw is None or (isinstance(bb_pct_raw, float) and math.isnan(bb_pct_raw)):
        bbl = _safe_float(row.get("BBL_20_2.0"), price - atr)
        bbu = _safe_float(row.get("BBU_20_2.0"), price + atr)
        bb_pct = (price - bbl) / (bbu - bbl) if bbu > bbl else 0.5
    else:
        bb_pct = _safe_float(bb_pct_raw, 0.5)

    macd_h = _safe_float(row.get("MACDh_12_26_9"), 0.0)
    adx    = _safe_float(row.get("adx"),   0.0)
    adx_p  = _safe_float(row.get("adx_dmp"), 0.0)
    adx_n  = _safe_float(row.get("adx_dmn"), 0.0)

    regime_map = {"bull": 1, "neutral": 0, "bear": -1}
    regime_enc = regime_map.get(signal.regime, 0)

    details     = signal.technical.get("details", {})
    htf_rsi     = _safe_float(details.get("htf_rsi"), 50.0)

    net_score = signal.bull_score - signal.bear_score if side == "LONG" else signal.bear_score - signal.bull_score

    return {
        "ema9_ratio":    ema9  / price,
        "ema21_ratio":   ema21 / price,
        "ema50_ratio":   ema50 / price,
        "ema200_ratio":  ema200 / price,
        "rsi":           _safe_float(row.get("rsi"), 50.0),
        "stochrsi_k":    _safe_float(row.get("stochrsi_k"), 50.0),
        "stochrsi_d":    _safe_float(row.get("stochrsi_d"), 50.0),
        "macd_h_norm":   macd_h / atr,
        "adx":           adx,
        "adx_dmp_norm":  adx_p / (adx + 1e-9),
        "adx_dmn_norm":  adx_n / (adx + 1e-9),
        "bb_pct":        bb_pct,
        "vol_ratio":     _safe_float(row.get("vol_ratio"), 1.0),
        "atr_contracted":_safe_float(row.get("atr_contracted"), 0.0),
        "bull_engulf":   _safe_float(row.get("bull_engulf"), 0.0),
        "bear_engulf":   _safe_float(row.get("bear_engulf"), 0.0),
        "hammer":        _safe_float(row.get("hammer"), 0.0),
        "shooting_star": _safe_float(row.get("shooting_star"), 0.0),
        "three_bull":    _safe_float(row.get("three_bull"), 0.0),
        "three_bear":    _safe_float(row.get("three_bear"), 0.0),
        "ms_bull":       _safe_float(row.get("ms_bull"), 0.0),
        "ms_bear":       _safe_float(row.get("ms_bear"), 0.0),
        "near_channel_top": _safe_float(row.get("near_channel_top"), 0.0),
        "near_channel_bot": _safe_float(row.get("near_channel_bot"), 0.0),
        "hurst_acf1":    _safe_float(row.get("hurst_acf1"), 0.5),
        "bull_score":    signal.bull_score,
        "bear_score":    signal.bear_score,
        "net_score":     net_score,
        "regime_enc":    regime_enc,
        "htf_rsi":       htf_rsi,
        "side_enc":      1 if side == "LONG" else -1,
    }


def run_backtest_export(exchange, pair: str, risk_profile: dict, strategy,
                        start_date: str, df_override=None) -> list[dict]:
    """Run backtest with feature capture. Returns list of completed trade dicts."""
    from v6.core.bot_sentiment import load_fear_greed_sentiment
    from v6.core.bot_risk import load_winrate_table

    timeframe = strategy.timeframe
    _root     = Path(__file__).resolve().parents[1]

    if df_override is not None:
        df_full = df_override.copy()
    else:
        # Load full history then filter
        df_full = fetch_historical_ohlcv(exchange, pair, timeframe, days=1500)
        df_full = precompute_indicators(df_full)

    # Filter to start_date
    start_ts = pd.Timestamp(start_date)
    df_full  = df_full[df_full["timestamp"] >= start_ts].reset_index(drop=True)
    print(f"  Dataset: {len(df_full):,} candles from {start_date}")

    _fg_path = _root / "data" / "fear_greed_historical.json"
    fg_data  = load_fear_greed_sentiment(str(_fg_path)) if _fg_path.exists() else {}

    state = load_state("__nonexistent__")
    state["peak_balance"] = state["balance_usdt"]

    warmup = 100
    n      = len(df_full)

    # Use running counters instead of scanning state["trades"] on every candle
    n_opens  = 0   # total OPEN_ events ever
    n_closes = 0   # total CLOSE_ events ever
    open_seq = 0   # monotonic key for pending_opens dict

    pending_opens: dict = {}    # open_seq → entry data
    completed_trades: list[dict] = []

    def _process_new_close(ts, current_price):
        last_close = next(
            (t for t in reversed(state["trades"]) if t["action"].startswith("CLOSE_")), None
        )
        if last_close is None:
            return
        side_c = last_close["action"].replace("CLOSE_", "")
        pnl    = last_close.get("pnl", 0.0)
        match_key = None
        for k in sorted(pending_opens.keys(), reverse=True):
            if pending_opens[k]["side"] == side_c:
                match_key = k
                break
        if match_key is not None:
            entry_data = pending_opens.pop(match_key)
            record = {
                "entry_ts":    entry_data["entry_ts"],
                "exit_ts":     str(ts),
                "side":        side_c,
                "entry_price": entry_data["entry_price"],
                "exit_price":  current_price,
                "pnl":         round(pnl, 4),
                "won":         1 if pnl > 0 else 0,
                "close_reason": last_close.get("reason", ""),
            }
            record.update(entry_data["features"])
            completed_trades.append(record)

    for i in range(warmup, n):
        row      = df_full.iloc[i]
        ts       = pd.Timestamp(row["timestamp"])
        date_str = str(ts.date())

        reset_daily_counter(state, date_str)
        state["current_candle_index"] = i

        current_price = float(row["close"])
        df_slice      = df_full.iloc[max(0, i - 299):i + 1]

        day_fg = fg_data.get(date_str, {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"})
        live_extras = {
            "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
            "fear_greed": day_fg,
            "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
            "orderbook":  {"bull_mod": 0, "bear_mod": 0},
            "macro_corr": {"bull_mod": 0, "bear_mod": 0},
        }

        signal = strategy.get_signal(df_slice, live_extras, row=row)
        rp_eff = apply_regime(risk_profile, signal.regime)
        atr    = signal.technical.get("details", {}).get("atr", 0)
        scores = {"bullish_total": signal.bull_score, "bearish_total": signal.bear_score}

        # ── check_sl_tp can close positions via SL/TP ─────────────────────────
        n_closes_before_sltp = len(state["trades"])
        check_sl_tp(state, pair, current_price, rp_eff, atr=atr, scores=scores)
        # Did a SL/TP close fire?
        for t in state["trades"][n_closes_before_sltp:]:
            if t["action"].startswith("CLOSE_"):
                n_closes += 1
                _process_new_close(ts, current_price)

        # ── make_decision can open or close positions ─────────────────────────
        n_trades_before = len(state["trades"])

        make_decision(
            state, pair, current_price, atr, signal, rp_eff,
            verbose=False,
            min_hold_candles=0,
            current_candle_index=i,
            winrate_table={},
            timestamp=ts,
        )

        for t in state["trades"][n_trades_before:]:
            if t["action"].startswith("OPEN_"):
                n_opens  += 1
                open_seq += 1
                side = t["action"].replace("OPEN_", "")
                pending_opens[open_seq] = {
                    "features":    _extract_features(row, signal, side),
                    "side":        side,
                    "entry_price": current_price,
                    "entry_ts":    str(ts),
                }
            elif t["action"].startswith("CLOSE_"):
                n_closes += 1
                _process_new_close(ts, current_price)

    # Force-close any remaining open position
    if state.get("position"):
        close_position(state, pair, float(df_full.iloc[-1]["close"]), "END_OF_BACKTEST")

    total = len(completed_trades)
    wins  = sum(1 for t in completed_trades if t["won"] == 1)
    print(f"  Captured {total} completed trades | WR={wins/total*100:.1f}%" if total else "  No trades captured")
    return completed_trades


def save_csv(trades: list[dict], path: Path):
    if not trades:
        print("  Nothing to save.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    all_keys = ["entry_ts", "exit_ts", "side", "entry_price", "exit_price",
                "pnl", "won", "close_reason"] + FEATURE_COLS
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"  Saved → {path}  ({len(trades)} rows)")


if __name__ == "__main__":
    import ccxt

    exchange = ccxt.bybit({"enableRateLimit": True})
    strategy = Strategy15m()

    print(f"\n[V7] Exporting trade features for ML training")
    print(f"     Pair: {PAIR} | From: {START_DATE}")
    print(f"     Features: {len(FEATURE_COLS)} columns\n")

    trades = run_backtest_export(
        exchange   = exchange,
        pair       = PAIR,
        risk_profile = RISK_PROFILE,
        strategy   = strategy,
        start_date = START_DATE,
    )
    save_csv(trades, OUT_PATH)
    print("\n[V7] Done. Run SHAP analysis with v7/shap_analysis.py next.")
