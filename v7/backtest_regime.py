"""
V7 Phase 3 — Regime-switching backtest.

Tests regime-specific parameters without touching V6 production code.
Key change: disable signal-based exits when position aligns with regime trend.

Run: python v7/backtest_regime.py
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
from dataclasses import replace

from v6.core.bot_core import (
    Signal, load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v6.core.bot_sentiment import load_fear_greed_sentiment
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import StrategyML

LOCAL_CSV  = ROOT / "data" / "btc_15m_full.csv"

# ── Base risk profile (same as V6 moderate) ────────────────────────────────
BASE_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

# ── Regime-specific overrides ───────────────────────────────────────────────
# Each regime dict defines per-regime parameter OVERRIDES.
# Keys map to risk_profile keys (applied over BASE_RISK).
# Extra key "_signal_exit": if False, don't close aligned-direction position on opposing signal.

REGIME_CONFIGS = {
    # Config A: just disable signal exits in aligned regimes
    "A_no_signal_exit": {
        "bull":    {"_signal_exit_long": False},
        "bear":    {"_signal_exit_short": False},
        "neutral": {},
    },
    # Config B: disable signal exits + tune SL/TP per regime
    "B_regime_sltp": {
        "bull": {
            "_signal_exit_long":    False,
            "stop_loss_atr_mult":   2.0,    # tighter SL: bull trend supports longs
            "take_profit_atr_mult": 4.5,    # wider TP: let bull runs extend
        },
        "bear": {
            "_signal_exit_short":   False,
            "stop_loss_atr_mult":   2.5,    # keep wider SL: bear noise
            "take_profit_atr_mult": 3.5,    # tighter TP: bears recover fast
        },
        "neutral": {
            "stop_loss_atr_mult":   2.0,
            "take_profit_atr_mult": 3.5,    # ranging market — take profit sooner
            "min_score":            60,     # higher bar in noisy lateral
        },
    },
    # Config C: B + higher min_score threshold in neutral
    "C_strict_neutral": {
        "bull": {
            "_signal_exit_long":    False,
            "stop_loss_atr_mult":   2.0,
            "take_profit_atr_mult": 4.5,
        },
        "bear": {
            "_signal_exit_short":   False,
            "stop_loss_atr_mult":   2.5,
            "take_profit_atr_mult": 3.5,
        },
        "neutral": {
            "stop_loss_atr_mult":   2.0,
            "take_profit_atr_mult": 3.5,
            "min_score":            62,
            "_signal_exit_long":    False,  # disable ALL signal exits in neutral too
            "_signal_exit_short":   False,
        },
    },
}


def _apply_regime_v7(base_profile: dict, regime: str, regime_config: dict) -> dict:
    """Apply V6 regime (for TP/SL factors) + V7 overrides."""
    rp = apply_regime(base_profile, regime)          # V6 logic (be_mult, tp_factor, etc.)
    overrides = regime_config.get(regime, {})
    rp.update(overrides)
    rp["_regime"] = regime
    return rp


def run_backtest_v7(
    df_full: pd.DataFrame,
    strategy,
    base_risk: dict,
    regime_config: dict,
    pair: str = "BTC/USDT:USDT",
) -> dict:
    """Custom backtest loop with regime-switching signal exit control."""
    _root   = ROOT
    _fg_path = _root / "data" / "fear_greed_historical.json"
    fg_data  = load_fear_greed_sentiment(str(_fg_path)) if _fg_path.exists() else {}

    state = load_state("__nonexistent__")
    state["peak_balance"] = state["balance_usdt"]

    warmup = 100
    n      = len(df_full)

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
        rp_eff = _apply_regime_v7(base_risk, signal.regime, regime_config)
        atr    = signal.technical.get("details", {}).get("atr", 0)
        scores = {"bullish_total": signal.bull_score, "bearish_total": signal.bear_score}

        # SL/TP check (uses regime-specific parameters from rp_eff)
        check_sl_tp(state, pair, current_price, rp_eff, atr=atr, scores=scores)

        # Regime-switching: suppress opposing signal when position aligned with regime
        pos = state.get("position")
        if pos:
            side_open = pos["side"]
            signal = _apply_signal_exit_gate(signal, side_open, rp_eff)

        make_decision(
            state, pair, current_price, atr, signal, rp_eff,
            verbose=False, min_hold_candles=0,
            current_candle_index=i, winrate_table={}, timestamp=ts,
        )

    # Liquidate any open position at end
    if state.get("position"):
        close_position(state, pair, float(df_full.iloc[-1]["close"]), "END_OF_BACKTEST")

    total = state["stats"]["wins"] + state["stats"]["losses"]
    wr    = state["stats"]["wins"] / total * 100 if total else 0
    pnl   = state["balance_usdt"] - 1000
    return {
        "pnl": round(pnl, 2),
        "wr":  round(wr, 1),
        "trades": total,
        "stats": state["stats"],
        "balance": state["balance_usdt"],
    }


def _apply_signal_exit_gate(signal: Signal, side_open: str, rp: dict) -> Signal:
    """
    If the regime says NOT to exit on opposing signal, suppress the opposing score
    below the close_threshold (=43) so make_decision won't trigger an early exit.
    """
    ms = rp.get("min_score", 58)
    close_thr = max(ms - 15, 35)  # same formula as make_decision

    modified = False
    bull = signal.bull_score
    bear = signal.bear_score

    # LONG open + bull regime + signal exit disabled → suppress bear
    if side_open == "LONG" and rp.get("_signal_exit_long") is False:
        if bear >= close_thr:
            bear = close_thr - 1  # just below threshold
            modified = True

    # SHORT open + bear regime + signal exit disabled → suppress bull
    if side_open == "SHORT" and rp.get("_signal_exit_short") is False:
        if bull >= close_thr:
            bull = close_thr - 1
            modified = True

    if not modified:
        return signal

    return Signal(
        bull_score       = bull,
        bear_score       = bear,
        technical        = signal.technical,
        htf_blocks_long  = signal.htf_blocks_long,
        htf_blocks_short = signal.htf_blocks_short,
        regime           = signal.regime,
    )


def load_data(start_date: str) -> pd.DataFrame:
    print(f"  Loading data from {start_date}...")
    df = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df = df[df["timestamp"] >= start_date].reset_index(drop=True)
    print(f"  {len(df):,} candles | Precomputing indicators...")
    return precompute_indicators(df)


if __name__ == "__main__":
    START = "2023-01-01"
    print(f"\n[V7 Phase 3] Regime-switching parameter search")
    print(f"  Period: {START} → 2026-08-24\n")

    df = load_data(START)

    # Plain V6 strategy (no ML gate) — true baseline
    v6 = Strategy15m()
    # V7 ML strategy (with OOS model)
    from v7.strategy_ml import StrategyML
    import json, pickle
    oos_meta = ROOT / "v7" / "models" / "v7_classifier_oos_meta.json"
    oos_pkl  = ROOT / "v7" / "models" / "v7_classifier_oos.pkl"
    v7_ml    = StrategyML(model_path=str(oos_pkl), threshold=0.55)
    v7_ml.feature_cols = json.load(open(oos_meta))["feature_cols"]

    results = []

    def bench(label, strategy, config):
        r = run_backtest_v7(df, strategy, BASE_RISK, config)
        results.append({"label": label, **r})
        ml_info = ""
        if hasattr(strategy, "_ml_stats"):
            s = strategy._ml_stats
            if s["checked"]:
                ml_info = f"  ML: {s['blocked']}/{s['checked']} blocked ({s['blocked']/s['checked']*100:.0f}%)"
            strategy._ml_stats = {"checked": 0, "passed": 0, "blocked": 0}  # reset
        print(f"  {label:<40}  PnL: {r['pnl']:>+9.2f}  Trades: {r['trades']:4}  WR: {r['wr']:.1f}%{ml_info}")

    print("─── V6 baseline (no ML, no regime-switching) ───")
    bench("V6 baseline",                         v6,    {})

    print("\n─── V7 ML only (no regime-switching) ───")
    bench("V7 ML@0.55 (no regime cfg)",          v7_ml, {})

    print("\n─── V7 ML + regime-switching configs ───")
    for cfg_name, cfg in REGIME_CONFIGS.items():
        bench(f"V7 ML + {cfg_name}", v7_ml, cfg)
        v7_ml._ml_stats = {"checked": 0, "passed": 0, "blocked": 0}

    print("\n─── Regime configs WITHOUT ML (signal exit only) ───")
    for cfg_name, cfg in REGIME_CONFIGS.items():
        bench(f"V6 + {cfg_name}", v6, cfg)

    print("\n" + "=" * 70)
    print(f"  {'Strategy':<42} {'PnL':>10}  {'Trades':>7}  {'WR':>6}")
    print("  " + "-" * 67)
    baseline_pnl = results[0]["pnl"]
    for r in sorted(results, key=lambda x: -x["pnl"]):
        delta = r["pnl"] - baseline_pnl
        marker = f" ({delta:+.0f})" if r["label"] != "V6 baseline" else " (baseline)"
        print(f"  {r['label']:<42} {r['pnl']:>+10.2f}  {r['trades']:>7}  {r['wr']:>5.1f}%{marker}")
    print("=" * 70)
