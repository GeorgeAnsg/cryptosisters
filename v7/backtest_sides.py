"""
V7 — Backtest with separate LONG and SHORT ML models.

OOS test period: 2025-01-01 → 2026-08-24.
Tests multiple combinations of LONG/SHORT thresholds.

Run: python v7/backtest_sides.py
"""

import sys, json, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from v6.core.bot_core import (
    Signal, load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v6.core.bot_sentiment import load_fear_greed_sentiment
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import StrategyML, _build_feature_vector

LOCAL_CSV  = ROOT / "data" / "btc_15m_full.csv"
TEST_START = "2025-01-01"
MODEL_DIR  = ROOT / "v7" / "models"

BASE_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}


class StrategyDual(Strategy15m):
    """
    Uses separate ML models for LONG and SHORT signals.
    Each model has its own threshold.
    Setting a threshold to None disables ML for that direction.
    """
    def __init__(self, long_clf, long_feats, long_t, short_clf, short_feats, short_t):
        super().__init__()
        self.long_clf   = long_clf
        self.long_feats = long_feats
        self.long_t     = long_t
        self.short_clf  = short_clf
        self.short_feats = short_feats
        self.short_t    = short_t
        self.stats = {"long_checked": 0, "long_blocked": 0,
                      "short_checked": 0, "short_blocked": 0}

    def get_signal(self, df_ltf, live_extras, row=None, min_score=58):
        signal = super().get_signal(df_ltf, live_extras, row=row)

        bull = signal.bull_score
        bear = signal.bear_score
        htf_long  = signal.htf_blocks_long
        htf_short = signal.htf_blocks_short

        bull_candidate = bull > bear and not htf_long
        bear_candidate = bear > bull and not htf_short

        actual_row = row if row is not None else df_ltf.iloc[-1]

        # LONG gate
        if bull_candidate and self.long_t is not None:
            self.stats["long_checked"] += 1
            fvec = _build_feature_vector(actual_row, signal, "LONG", self.long_feats)
            prob = self.long_clf.predict_proba([fvec])[0][1]
            if prob < self.long_t:
                self.stats["long_blocked"] += 1
                htf_long = True

        # SHORT gate
        if bear_candidate and self.short_t is not None:
            self.stats["short_checked"] += 1
            fvec = _build_feature_vector(actual_row, signal, "SHORT", self.short_feats)
            prob = self.short_clf.predict_proba([fvec])[0][1]
            if prob < self.short_t:
                self.stats["short_blocked"] += 1
                htf_short = True

        return Signal(
            bull_score=bull, bear_score=bear,
            technical=signal.technical,
            htf_blocks_long=htf_long,
            htf_blocks_short=htf_short,
            regime=signal.regime,
        )


def run_bt(df, strategy, pair="BTC/USDT:USDT"):
    fg_path = ROOT / "data" / "fear_greed_historical.json"
    fg_data = load_fear_greed_sentiment(str(fg_path)) if fg_path.exists() else {}
    state   = load_state("__nonexistent__")
    state["peak_balance"] = state["balance_usdt"]
    n = len(df)

    for i in range(100, n):
        row      = df.iloc[i]
        ts       = pd.Timestamp(row["timestamp"])
        date_str = str(ts.date())
        reset_daily_counter(state, date_str)
        state["current_candle_index"] = i

        current_price = float(row["close"])
        df_slice      = df.iloc[max(0, i - 299):i + 1]
        day_fg = fg_data.get(date_str, {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"})
        live_extras = {
            "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
            "fear_greed": day_fg,
            "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
            "orderbook":  {"bull_mod": 0, "bear_mod": 0},
            "macro_corr": {"bull_mod": 0, "bear_mod": 0},
        }

        signal = strategy.get_signal(df_slice, live_extras, row=row)
        rp_eff = apply_regime(BASE_RISK, signal.regime)
        atr    = signal.technical.get("details", {}).get("atr", 0)
        check_sl_tp(state, pair, current_price, rp_eff, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, current_price, atr, signal, rp_eff,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END_OF_BACKTEST")

    total = state["stats"]["wins"] + state["stats"]["losses"]
    wr    = state["stats"]["wins"] / total * 100 if total else 0
    pnl   = state["balance_usdt"] - 1000
    longs  = state["stats"].get("total_longs", "?")
    shorts = state["stats"].get("total_shorts", "?")
    return {"pnl": round(pnl, 2), "wr": round(wr, 1), "trades": total,
            "longs": longs, "shorts": shorts}


if __name__ == "__main__":
    print(f"\n[V7 Directional] OOS backtest — {TEST_START} → 2026-08-24")

    df_raw = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df_oos = df_raw[df_raw["timestamp"] >= TEST_START].reset_index(drop=True)
    print(f"  {len(df_oos):,} candles | Precomputing indicators...\n")
    df_oos = precompute_indicators(df_oos)

    # Load models
    with open(MODEL_DIR / "v7_clf_long.pkl",  "rb") as f: clf_long  = pickle.load(f)
    with open(MODEL_DIR / "v7_clf_short.pkl", "rb") as f: clf_short = pickle.load(f)
    meta_long  = json.load(open(MODEL_DIR / "v7_clf_long_meta.json"))
    meta_short = json.load(open(MODEL_DIR / "v7_clf_short_meta.json"))

    feat_long  = meta_long["feature_cols"]
    feat_short = meta_short["feature_cols"]

    # OOS single model (reference from previous session)
    with open(MODEL_DIR / "v7_classifier_oos.pkl", "rb") as f: clf_oos = pickle.load(f)
    meta_oos = json.load(open(MODEL_DIR / "v7_classifier_oos_meta.json"))

    print("  Loading models:")
    print(f"    LONG  model  → threshold calibration OOS: AUC={meta_long['oos_auc']}")
    print(f"    SHORT model  → threshold calibration OOS: AUC={meta_short['oos_auc']}")

    results = []

    def bench(label, strategy):
        if hasattr(strategy, "stats"):
            strategy.stats = {"long_checked": 0, "long_blocked": 0,
                              "short_checked": 0, "short_blocked": 0}
        if hasattr(strategy, "_ml_stats"):
            strategy._ml_stats = {"checked": 0, "passed": 0, "blocked": 0}
        r = run_bt(df_oos, strategy)
        results.append({"label": label, **r})

        detail = ""
        if hasattr(strategy, "stats") and strategy.stats["long_checked"]:
            s = strategy.stats
            lc, lb = s["long_checked"], s["long_blocked"]
            sc, sb = s["short_checked"], s["short_blocked"]
            detail = (f"  [L: {lb}/{lc} blk={lb/lc*100:.0f}%"
                      f"  S: {sb}/{sc} blk={sb/sc*100:.0f}%]")
        elif hasattr(strategy, "_ml_stats") and strategy._ml_stats["checked"]:
            s = strategy._ml_stats
            detail = f"  [ML: {s['blocked']}/{s['checked']} blk={s['blocked']/s['checked']*100:.0f}%]"

        print(f"  {label:<45}  PnL: {r['pnl']:>+8.2f}  Trades:{r['trades']:4}  WR:{r['wr']:.1f}%{detail}")

    # ── Baselines ──
    print("── Baselines ──")
    bench("V6 (no ML)", Strategy15m())
    v7_oos = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    v7_oos.feature_cols = meta_oos["feature_cols"]
    bench("V7 combined@0.55 (reference)", v7_oos)

    # ── Directional combos ──
    print("\n── Directional models ──")

    combos = [
        # (label, long_t, short_t)
        # long_t=None = no ML filter on longs
        ("LONG:none  + SHORT:0.40",  None,  0.40),
        ("LONG:none  + SHORT:0.45",  None,  0.45),
        ("LONG:none  + SHORT:0.50",  None,  0.50),
        ("LONG:none  + SHORT:0.55",  None,  0.55),
        ("LONG:0.40  + SHORT:0.40",  0.40,  0.40),
        ("LONG:0.45  + SHORT:0.40",  0.45,  0.40),
        ("LONG:0.50  + SHORT:0.40",  0.50,  0.40),
        ("LONG:0.55  + SHORT:0.40",  0.55,  0.40),
        ("LONG:0.60  + SHORT:0.40",  0.60,  0.40),
        ("LONG:0.65  + SHORT:0.40",  0.65,  0.40),
        ("LONG:0.675 + SHORT:0.40",  0.675, 0.40),
        ("LONG:0.50  + SHORT:0.50",  0.50,  0.50),
        ("LONG:0.55  + SHORT:0.50",  0.55,  0.50),
        ("LONG:0.60  + SHORT:0.50",  0.60,  0.50),
        ("LONG:0.50  + SHORT:0.55",  0.50,  0.55),
        ("LONG:none  + SHORT:0.60",  None,  0.60),
        ("LONG:0.55  + SHORT:0.55",  0.55,  0.55),
    ]

    for label, lt, st in combos:
        strat = StrategyDual(clf_long, feat_long, lt, clf_short, feat_short, st)
        bench(label, strat)

    # ── Summary ──
    baseline_v6  = next(r for r in results if r["label"] == "V6 (no ML)")["pnl"]
    baseline_v7  = next(r for r in results if "reference" in r["label"])["pnl"]

    print("\n" + "=" * 80)
    print(f"  OOS RESULTS ({TEST_START} → 2026-08-24) | V6={baseline_v6:+.0f}  V7ref={baseline_v7:+.0f}")
    print("=" * 80)
    print(f"  {'Strategy':<45} {'PnL':>9}  {'Trades':>7}  {'WR':>6}  {'vs V6':>7}  {'vs V7':>7}")
    print("  " + "-" * 77)
    for r in sorted(results, key=lambda x: -x["pnl"]):
        dv6 = r["pnl"] - baseline_v6
        dv7 = r["pnl"] - baseline_v7
        print(f"  {r['label']:<45} {r['pnl']:>+9.2f}  {r['trades']:>7}  {r['wr']:>5.1f}%  {dv6:>+7.0f}  {dv7:>+7.0f}")
    print("=" * 80)
