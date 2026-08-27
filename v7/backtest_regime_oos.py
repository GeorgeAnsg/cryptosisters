"""
V7 Phase 3 — Regime-switching, OOS-only evaluation.

Test period: 2025-01-01 → 2026-08-24 (model trained on 2023-2024, never saw this).
Compares V6 baseline vs V7 ML vs V7 ML + regime-switching configs.

Key fix vs backtest_regime.py: only tests TP/SL adjustments ADDITIVE to V6 regime,
not replacing them. V6's apply_regime() already handles long_tp_factor etc.
"""

import sys, json, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from v6.core.bot_core import (
    Signal, load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v6.core.bot_sentiment import load_fear_greed_sentiment
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import StrategyML

LOCAL_CSV  = ROOT / "data" / "btc_15m_full.csv"
TEST_START = "2025-01-01"

BASE_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

# Regime-switching configs — only tune what makes sense per regime
# Note: V6's apply_regime already adjusts TP factors (long_tp_factor in bull=1.4 etc.)
# So we only override the base multipliers OR signal exit behavior.
REGIME_CONFIGS = {
    # A: only disable signal-based exits in aligned regime
    "A_no_signal_exit": {
        "bull":    {"_signal_exit_long": False},
        "bear":    {"_signal_exit_short": False},
        "neutral": {},
    },
    # B: disable exits + tighter SL in bull (trend supports, can afford tighter)
    "B_bull_tight_sl": {
        "bull":    {"_signal_exit_long": False, "stop_loss_atr_mult": 2.0},
        "bear":    {"_signal_exit_short": False, "stop_loss_atr_mult": 2.5},
        "neutral": {},
    },
    # C: disable exits + tighter TP in neutral (ranging market — take profit sooner)
    "C_neutral_tp": {
        "bull":    {"_signal_exit_long": False},
        "bear":    {"_signal_exit_short": False},
        "neutral": {"take_profit_atr_mult": 3.0, "stop_loss_atr_mult": 2.0},
    },
    # D: all of the above combined
    "D_combined": {
        "bull":    {"_signal_exit_long": False,  "stop_loss_atr_mult": 2.0},
        "bear":    {"_signal_exit_short": False,  "stop_loss_atr_mult": 2.5},
        "neutral": {"take_profit_atr_mult": 3.0, "stop_loss_atr_mult": 2.0},
    },
    # E: disable ALL signal exits (even neutral) — see if it helps or hurts
    "E_no_exits_all": {
        "bull":    {"_signal_exit_long": False,  "_signal_exit_short": False},
        "bear":    {"_signal_exit_long": False,  "_signal_exit_short": False},
        "neutral": {"_signal_exit_long": False,  "_signal_exit_short": False},
    },
}


def _apply_regime_v7(base_profile: dict, regime: str, regime_config: dict) -> dict:
    rp = apply_regime(base_profile, regime)
    rp.update(regime_config.get(regime, {}))
    rp["_regime"] = regime
    return rp


def _suppress_signal_exit(signal: Signal, side_open: str, rp: dict) -> Signal:
    ms        = rp.get("min_score", 58)
    close_thr = max(ms - 15, 35)
    bull = signal.bull_score
    bear = signal.bear_score
    modified = False

    if side_open == "LONG" and rp.get("_signal_exit_long") is False:
        if bear >= close_thr:
            bear     = close_thr - 1
            modified = True
    if side_open == "SHORT" and rp.get("_signal_exit_short") is False:
        if bull >= close_thr:
            bull     = close_thr - 1
            modified = True

    if not modified:
        return signal
    return Signal(
        bull_score=bull, bear_score=bear,
        technical=signal.technical,
        htf_blocks_long=signal.htf_blocks_long,
        htf_blocks_short=signal.htf_blocks_short,
        regime=signal.regime,
    )


def run_bt(df: pd.DataFrame, strategy, base_risk: dict, regime_config: dict,
           pair: str = "BTC/USDT:USDT") -> dict:
    _root    = ROOT
    _fg_path = _root / "data" / "fear_greed_historical.json"
    fg_data  = load_fear_greed_sentiment(str(_fg_path)) if _fg_path.exists() else {}

    state = load_state("__nonexistent__")
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
            "sentiment": {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
            "fear_greed": day_fg,
            "funding":   {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
            "orderbook": {"bull_mod": 0, "bear_mod": 0},
            "macro_corr": {"bull_mod": 0, "bear_mod": 0},
        }

        signal = strategy.get_signal(df_slice, live_extras, row=row)
        rp_eff = _apply_regime_v7(base_risk, signal.regime, regime_config)
        atr    = signal.technical.get("details", {}).get("atr", 0)
        check_sl_tp(state, pair, current_price, rp_eff, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})

        pos = state.get("position")
        if pos:
            signal = _suppress_signal_exit(signal, pos["side"], rp_eff)

        make_decision(state, pair, current_price, atr, signal, rp_eff,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END_OF_BACKTEST")

    total = state["stats"]["wins"] + state["stats"]["losses"]
    wr    = state["stats"]["wins"] / total * 100 if total else 0
    pnl   = state["balance_usdt"] - 1000
    return {"pnl": round(pnl, 2), "wr": round(wr, 1), "trades": total}


if __name__ == "__main__":
    print(f"\n[V7 Phase 3 OOS] Regime-switching — test period: {TEST_START} → 2026-08-24")

    df_raw = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df_oos = df_raw[df_raw["timestamp"] >= TEST_START].reset_index(drop=True)
    print(f"  {len(df_oos):,} candles | Precomputing indicators...\n")
    df_oos = precompute_indicators(df_oos)

    oos_meta = json.load(open(ROOT / "v7" / "models" / "v7_classifier_oos_meta.json"))
    oos_pkl  = ROOT / "v7" / "models" / "v7_classifier_oos.pkl"

    results = []

    def bench(label, strategy, cfg):
        if hasattr(strategy, "_ml_stats"):
            strategy._ml_stats = {"checked": 0, "passed": 0, "blocked": 0}
        r = run_bt(df_oos, strategy, BASE_RISK, cfg)
        results.append({"label": label, **r})
        ml = ""
        if hasattr(strategy, "_ml_stats") and strategy._ml_stats["checked"]:
            s = strategy._ml_stats
            ml = f"  [ML: {s['blocked']}/{s['checked']} blocked {s['blocked']/s['checked']*100:.0f}%]"
        print(f"  {label:<40}  PnL: {r['pnl']:>+8.2f}  Trades: {r['trades']:4}  WR: {r['wr']:.1f}%{ml}")

    v6 = Strategy15m()
    def fresh_v7():
        s = StrategyML(model_path=str(oos_pkl), threshold=0.55)
        s.feature_cols = oos_meta["feature_cols"]
        return s

    print("── V6 and V7 ML (no regime-switching) ──")
    bench("V6 baseline",             v6,        {})
    bench("V7 ML@0.55 (no regime)",  fresh_v7(), {})

    print("\n── V6 + regime-switching (no ML) ──")
    for name, cfg in REGIME_CONFIGS.items():
        bench(f"V6 + {name}", v6, cfg)

    print("\n── V7 ML + regime-switching ──")
    for name, cfg in REGIME_CONFIGS.items():
        bench(f"V7 ML + {name}", fresh_v7(), cfg)

    # Sort and summarize
    baseline = next(r for r in results if r["label"] == "V6 baseline")["pnl"]
    ml_base  = next(r for r in results if r["label"] == "V7 ML@0.55 (no regime)")["pnl"]

    print("\n" + "=" * 72)
    print(f"  OOS RESULTS ({TEST_START} → 2026-08-24)  |  V6 baseline: {baseline:+.0f} USDT")
    print("=" * 72)
    print(f"  {'Strategy':<40} {'PnL':>9}  {'Trades':>7}  {'WR':>6}  {'vs V6':>7}")
    print("  " + "-" * 68)
    for r in sorted(results, key=lambda x: -x["pnl"]):
        delta = r["pnl"] - baseline
        print(f"  {r['label']:<40} {r['pnl']:>+9.2f}  {r['trades']:>7}  {r['wr']:>5.1f}%  {delta:>+7.0f}")
    print("=" * 72)

    best = max(results, key=lambda x: x["pnl"])
    print(f"\n  Best config: {best['label']} → PnL={best['pnl']:+.2f} (+{best['pnl']-baseline:.0f} vs V6, +{best['pnl']-ml_base:.0f} vs V7 ML)")
