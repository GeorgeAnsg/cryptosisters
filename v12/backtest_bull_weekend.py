"""
V12 — Backtest: Solo LONG en fin de semana bull market.

Compara 3 configs en los 3 periodos:
  - V12 actual   → fin de semana bloqueado
  - V12 régimen  → trend+58 en neutral/bear wknd; bloqueado en bull wknd
  - V12 régimen+ → trend+58 en neutral/bear wknd; solo LONG en bull wknd

Run: python -m v12.backtest_bull_weekend
"""

import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import v6.core.bot_core as _bc
_bc.send_telegram = lambda *a, **k: None
_bc._tg_open      = lambda *a, **k: None
_bc._tg_update    = lambda *a, **k: None
_bc._tg_close     = lambda *a, **k: None

from v6.core.bot_core import (
    load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v7.strategy_ml import StrategyML

MODEL_DIR = ROOT / "v7" / "models"

_TP_MAP = {
    ("bull",    True):  5.0, ("bull",    False): 4.5,
    ("neutral", True):  3.5, ("neutral", False): 3.5,
    ("bear",    True):  4.5, ("bear",    False): 4.0,
}

def _dynamic_tp(signal):
    try:
        adx = float(signal.technical.get("details", {}).get("adx", 0) or 0)
    except Exception:
        adx = 0.0
    return _TP_MAP.get((signal.regime, adx >= 25), 4.0)

def _live_extras():
    return {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
        "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }

def make_strategy():
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    s.feature_cols = meta["feature_cols"]
    return s

def _make_risk():
    return {
        "risk_pct": 0.05, "max_cost_pct": 0.87,
        "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
        "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
        "max_drawdown_pct": 0.25, "max_daily_loss_pct": 0.03,
        "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
        "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
    }

# Modos de fin de semana en bull:
#   "block"     → comportamiento actual (range+BB bloqueado)
#   "long_only" → trend pero zerifica bear_score → solo LONG

def run(df, pair, regime_filter=False, bull_wknd="block"):
    state = load_state("__nonexistent__")
    strat = make_strategy()
    peak_eq = 1000.0
    max_dd = 0.0
    risk_params = _make_risk()

    for i in range(100, len(df)):
        row = df.iloc[i]
        ts  = pd.Timestamp(row["timestamp"])
        reset_daily_counter(state, str(ts.date()))
        state["current_candle_index"] = i
        price = float(row["close"])
        df_slice = df.iloc[max(0, i-299):i+1]

        signal = strat.get_signal(df_slice, _live_extras(), row=row)
        rp = apply_regime(risk_params, signal.regime)
        rp["take_profit_atr_mult"] = _dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0) or 0

        is_wknd = ts.weekday() >= 5

        if is_wknd:
            if signal.regime == "bull":
                if bull_wknd == "long_only":
                    # Habilitar fin de semana pero bloquear SHORT
                    rp["weekend_mode"] = "trend"
                    rp["weekend_min_score_bonus"] = 0
                    signal.bear_score = 0  # impide entradas SHORT
                else:
                    # block: comportamiento actual
                    rp["weekend_mode"] = "range"
                    rp["weekend_min_score_bonus"] = 10
            elif regime_filter:
                # neutral/bear en fin de semana → permisivo
                rp["weekend_mode"] = "trend"
                rp["weekend_min_score_bonus"] = 0

        check_sl_tp(state, pair, price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, price, atr, signal, rp,
                      verbose=False, min_hold_candles=3,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

        pos = state.get("position")
        eq = state["balance_usdt"] + pos["amount"] * pos["entry_price"] if pos else state["balance_usdt"]
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")

    st = state["stats"]
    total = st["wins"] + st["losses"]
    wr = st["wins"] / total * 100 if total else 0

    return {"pnl": round(state["balance_usdt"] - 1000, 2), "wr": round(wr, 1),
            "trades": total, "dd": round(max_dd, 1)}


CONFIGS = [
    ("V12 actual   (wknd bloqueado)",      False, "block"),
    ("V12 régimen  (solo neutral/bear)",   True,  "block"),
    ("V12 régimen+ (neutral/bear + LONG)", True,  "long_only"),
]

PERIODS = [
    ("Bear 2022",    "2022-01-01", "2023-01-01"),
    ("Bull 2023-24", "2023-01-01", "2025-01-01"),
    ("OOS 2025-26",  "2025-01-01", "2026-09-01"),
]

DATASETS = [
    (ROOT / "data" / "btc_15m_full.csv",  "BTC"),
    (ROOT / "data" / "eth_2023_2026.csv", "ETH"),
    (ROOT / "data" / "xrp_15m_full.csv",  "XRP"),
]


def main():
    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            all_dfs[pair] = df

    for period_name, start, end in PERIODS:
        print(f"\n{'='*70}")
        print(f"  PERIODO: {period_name}  ({start} → {end})")
        print(f"{'='*70}")
        print(f"  {'Config':<42} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6}")
        print(f"  {'-'*42} {'-'*8} {'-'*7} {'-'*6} {'-'*6}")

        totals = {label: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
                  for label, _, _ in CONFIGS}

        for pair, df_full in all_dfs.items():
            df = df_full[(df_full["timestamp"] >= start) & (df_full["timestamp"] < end)].reset_index(drop=True)
            if len(df) < 300:
                continue
            df = precompute_indicators(df)

            for label, regime_f, bull_wknd in CONFIGS:
                r = run(df, pair, regime_filter=regime_f, bull_wknd=bull_wknd)
                t = totals[label]
                t["pnl"]    += r["pnl"]
                t["trades"] += r["trades"]
                t["wins"]   += round(r["trades"] * r["wr"] / 100)
                t["dd"]      = max(t["dd"], r["dd"])

        for label, t in totals.items():
            if t["trades"] == 0:
                print(f"  {label:<42} {'—':>8} {'—':>7} {'—':>6} {'—':>6}")
                continue
            wr = t["wins"] / t["trades"] * 100
            print(f"  {label:<42} {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>5.1f}%")

    print()


if __name__ == "__main__":
    main()
