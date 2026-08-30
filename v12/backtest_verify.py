"""
V12 — Backtest de verificación multi-periodo.

Compara V12 actual vs V12 con nuevo weekend_mode="trend" + bonus=0
en tres periodos de mercado para confirmar que el cambio no rompe nada.

Run: python -m v12.backtest_verify
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

def _make_risk(weekend_mode="range", weekend_bonus=10):
    return {
        "risk_pct": 0.05, "max_cost_pct": 0.87,
        "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
        "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
        "max_drawdown_pct": 0.25, "max_daily_loss_pct": 0.03,
        "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
        "weekend_mode": weekend_mode, "weekend_min_score_bonus": weekend_bonus, "min_vol_ratio": 0.0,
    }

CONFIGS = [
    ("V12 actual   (range+BB, wknd_min=68)", _make_risk("range", 10), False),
    ("V12 régimen  (trend+58 neutral/bear)", _make_risk("range", 10), True),
    ("V12 nuevo    (trend,    wknd_min=58)", _make_risk("trend",  0), False),
]

PERIODS = [
    ("Bear 2022",    "2022-01-01", "2023-01-01"),
    ("Bull 2023-24", "2023-01-01", "2025-01-01"),
    ("OOS 2025-26",  "2025-01-01", "2026-09-01"),
]

DATASETS = [
    (ROOT / "data" / "btc_15m_full.csv",  "BTC"),
    (ROOT / "data" / "eth_2023_2026.csv", "ETH"),
    (ROOT / "data" / "sol_15m_full.csv",  "SOL"),
]


def run(df, pair, risk_params, regime_filter=False):
    """
    regime_filter=True: en fin de semana, usa trend+58 solo si régimen != bull.
    En bull weekend mantiene el comportamiento actual (range+BB conservador).
    """
    state = load_state("__nonexistent__")
    strat = make_strategy()
    peak_eq = 1000.0
    max_dd = 0.0

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

        # Filtro de régimen para fin de semana
        if regime_filter and ts.weekday() >= 5:
            if signal.regime == "bull":
                rp["weekend_mode"] = "range"   # conservador en bull
                rp["weekend_min_score_bonus"] = 10
            else:
                rp["weekend_mode"] = "trend"   # permisivo en neutral/bear
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
    pnls = [t["pnl"] for t in state.get("trades", []) if t.get("action", "").startswith("CLOSE_") and "pnl" in t]
    wins_p  = [p for p in pnls if p > 0]
    loses_p = [p for p in pnls if p <= 0]
    pf = abs(sum(wins_p) / sum(loses_p)) if loses_p else 99.0

    return {"pnl": round(state["balance_usdt"] - 1000, 2), "wr": round(wr, 1),
            "trades": total, "dd": round(max_dd, 1), "pf": round(pf, 2)}


def load_df(path, start, end):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[(df["timestamp"] >= start) & (df["timestamp"] < end)].reset_index(drop=True)
    return precompute_indicators(df) if len(df) > 200 else None


def main():
    # Cargar todos los datos una vez
    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df_full = pd.read_csv(path)
            df_full["timestamp"] = pd.to_datetime(df_full["timestamp"])
            all_dfs[pair] = df_full

    for period_name, start, end in PERIODS:
        print(f"\n{'='*70}")
        print(f"  PERIODO: {period_name}  ({start} → {end})")
        print(f"{'='*70}")
        print(f"  {'Config':<40} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6} {'PF':>5}")
        print(f"  {'-'*40} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*5}")

        # Acumulador por config
        totals = {label: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0, "pairs": 0}
                  for label, _, _ in CONFIGS}

        for pair, df_full in all_dfs.items():
            df = df_full[(df_full["timestamp"] >= start) & (df_full["timestamp"] < end)].reset_index(drop=True)
            if len(df) < 300:
                continue
            df = precompute_indicators(df)

            for label, risk, regime_f in CONFIGS:
                r = run(df, pair, risk, regime_filter=regime_f)
                t = totals[label]
                t["pnl"]    += r["pnl"]
                t["trades"] += r["trades"]
                t["wins"]   += round(r["trades"] * r["wr"] / 100)
                t["dd"]      = max(t["dd"], r["dd"])
                t["pairs"]  += 1

        for label, t in totals.items():
            if t["trades"] == 0:
                print(f"  {label:<40} {'—':>8} {'—':>7} {'—':>6} {'—':>6} {'—':>5}")
                continue
            wr = t["wins"] / t["trades"] * 100
            print(f"  {label:<40} {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>5.1f}% {'—':>5}")

    print()


if __name__ == "__main__":
    main()
