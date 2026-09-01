"""
V14 — Backtest: DVOL reemplaza completamente a Fear & Greed.

Configs:
  V13 + FG neutro  — Fear & Greed fijo en 5/5 (baseline real de todos los backtests)
  V13 + FG real    — Fear & Greed histórico real (lo que hace el bot en live)
  V14 DVOL         — Fear & Greed desactivado, DVOL calibrado en su lugar

Run: venv/bin/python -m v14.backtest_dvol_replace
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
from v14.deribit_options import dvol_score

MODEL_DIR = ROOT / "v13" / "models"
DVOL_FILE = ROOT / "data" / "btc_dvol_1h.csv"
FG_FILE   = ROOT / "data" / "fear_greed_historical.csv"

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

def _fg_to_mods(fg_value):
    if fg_value is None:
        return {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"}
    if fg_value >= 75:
        return {"bull_mod": 2, "bear_mod": 8, "value": fg_value, "label": "extreme_greed"}
    elif fg_value >= 55:
        return {"bull_mod": 7, "bear_mod": 3, "value": fg_value, "label": "greed"}
    elif fg_value >= 45:
        return {"bull_mod": 5, "bear_mod": 5, "value": fg_value, "label": "neutral"}
    elif fg_value >= 25:
        return {"bull_mod": 3, "bear_mod": 7, "value": fg_value, "label": "fear"}
    else:
        return {"bull_mod": 8, "bear_mod": 2, "value": fg_value, "label": "extreme_fear"}

def _build_extras(mode: str, fg_val, dvol_val) -> dict:
    extras = {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }
    if mode == "fg_neutral":
        extras["fear_greed"] = {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"}
    elif mode == "fg_real":
        extras["fear_greed"] = _fg_to_mods(fg_val)
    elif mode == "dvol":
        ds = dvol_score(dvol_val)
        # DVOL ocupa el slot de fear_greed
        extras["fear_greed"] = {
            "bull_mod": ds["bull_mod"], "bear_mod": ds["bear_mod"],
            "value": dvol_val or 55, "label": ds["label"],
        }
    return extras

def _base_risk():
    return {
        "risk_pct": 0.05, "max_cost_pct": 0.87,
        "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
        "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
        "max_drawdown_pct": 0.25, "max_daily_loss_pct": 0.03,
        "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
        "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
    }

def make_strategy():
    with open(MODEL_DIR / "v13_classifier_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v13_classifier.pkl"), threshold=0.55)
    s.feature_cols = meta["feature_cols"]
    return s

def load_dvol_series():
    df = pd.read_csv(DVOL_FILE, header=None,
                     names=["timestamp_ms","open","high","low","close"], skiprows=1)
    df["dt"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    return df.drop_duplicates("dt").set_index("dt")["close"].sort_index()

def load_fg_series():
    df = pd.read_csv(FG_FILE)
    df["dt"] = pd.to_datetime(df["date"], format="%d-%m-%Y", utc=True)
    return df.set_index("dt")["value"].sort_index()


def run(df, pair, mode, dvol_series, fg_series):
    state   = load_state("__nonexistent__")
    strat   = make_strategy()
    peak_eq = 1000.0
    max_dd  = 0.0
    rp_base = _base_risk()
    df_ts   = pd.to_datetime(df["timestamp"], utc=True)

    for i in range(100, len(df)):
        row   = df.iloc[i]
        ts    = df_ts.iloc[i]
        reset_daily_counter(state, str(ts.date()))
        state["current_candle_index"] = i
        price = float(row["close"])
        df_slice = df.iloc[max(0, i-299):i+1]

        fg_val, dvol_val = None, None
        if mode == "fg_real":
            try:
                idx = fg_series.index.asof(ts.normalize())
                if idx is not pd.NaT:
                    fg_val = int(fg_series[idx])
            except Exception:
                pass
        if mode == "dvol":
            try:
                idx = dvol_series.index.asof(ts)
                if idx is not pd.NaT:
                    dvol_val = float(dvol_series[idx])
            except Exception:
                pass

        extras = _build_extras(mode, fg_val, dvol_val)
        signal = strat.get_signal(df_slice, extras, row=row)
        rp = apply_regime(rp_base, signal.regime)
        rp["take_profit_atr_mult"] = _dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0) or 0

        # Risk factor del DVOL (solo en modo dvol)
        if mode == "dvol" and dvol_val is not None:
            rf = dvol_score(dvol_val)["risk_factor"]
            if rf < 1.0:
                rp = dict(rp)
                rp["risk_pct"] = rp["risk_pct"] * rf

        check_sl_tp(state, pair, price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, price, atr, signal, rp,
                      verbose=False, min_hold_candles=3,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

        pos = state.get("position")
        eq  = state["balance_usdt"] + pos["amount"] * pos["entry_price"] if pos else state["balance_usdt"]
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")

    st = state["stats"]
    total = st["wins"] + st["losses"]
    wr = st["wins"] / total * 100 if total else 0
    return {"pnl": round(state["balance_usdt"] - 1000, 2),
            "wr": round(wr, 1), "trades": total, "dd": round(max_dd, 1)}


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

# (label, mode)
CONFIGS = [
    ("V13 FG neutro",  "fg_neutral"),   # baseline histórico
    ("V13 FG real",    "fg_real"),       # lo que hace el bot live
    ("V14 DVOL",       "dvol"),          # DVOL reemplaza FG
]


def main():
    dvol_series = load_dvol_series()
    fg_series   = load_fg_series()
    print(f"DVOL: {len(dvol_series)} h | F&G: {len(fg_series)} días")

    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            all_dfs[pair] = df

    print(f"\nDVOL reemplaza Fear&Greed  |  Pares: {', '.join(all_dfs)}\n")

    for period_name, start, end in PERIODS:
        print(f"\n{'='*66}")
        print(f"  PERIODO: {period_name}  ({start} → {end})")
        print(f"{'='*66}")
        print(f"  {'Config':<22} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6}")
        print(f"  {'-'*22} {'-'*8} {'-'*7} {'-'*6} {'-'*6}")

        totals = {label: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
                  for label, _ in CONFIGS}

        for pair, df_full in all_dfs.items():
            df = df_full[(df_full["timestamp"] >= start) & (df_full["timestamp"] < end)].reset_index(drop=True)
            if len(df) < 300:
                continue
            df = precompute_indicators(df)

            for label, mode in CONFIGS:
                r = run(df, pair, mode, dvol_series, fg_series)
                t = totals[label]
                t["pnl"]    += r["pnl"]
                t["trades"] += r["trades"]
                t["wins"]   += round(r["trades"] * r["wr"] / 100)
                t["dd"]      = max(t["dd"], r["dd"])

        ref_pnl = None
        for label, _ in CONFIGS:
            t = totals[label]
            wr = t["wins"] / t["trades"] * 100 if t["trades"] else 0
            diff = f"  ({t['pnl']-ref_pnl:+.0f})" if ref_pnl is not None else ""
            print(f"  {label:<22} {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>5.1f}%{diff}")
            if ref_pnl is None:
                ref_pnl = t["pnl"]

    print()


if __name__ == "__main__":
    main()
