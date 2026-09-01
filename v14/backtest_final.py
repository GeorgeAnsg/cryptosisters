"""
V14 — Comparativa definitiva: V13 producción vs V14 propuesta.

V13 producción = lo que corre en live ahora mismo:
  - Fear & Greed real histórico
  - Funding rate real histórico
  - OI desactivado

V14 propuesta = cambios confirmados por audit:
  - DVOL reemplaza Fear & Greed
  - Funding en neutro (3/3 fijo)
  - OI desactivado

Run: venv/bin/python -m v14.backtest_final
"""

import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

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

MODEL_DIR  = ROOT / "v13" / "models"
DVOL_FILE  = ROOT / "data" / "btc_dvol_1h.csv"
FG_FILE    = ROOT / "data" / "fear_greed_historical.csv"
FUND_FILE  = ROOT / "data" / "funding_rate_historical.csv"

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

def load_dvol():
    df = pd.read_csv(DVOL_FILE, header=None,
                     names=["timestamp_ms","open","high","low","close"], skiprows=1)
    df["dt"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    return df.drop_duplicates("dt").set_index("dt")["close"].sort_index()

def load_fg():
    df = pd.read_csv(FG_FILE)
    df["dt"] = pd.to_datetime(df["date"], format="%d-%m-%Y", utc=True)
    return df.set_index("dt")["value"].sort_index()

def load_funding():
    df = pd.read_csv(FUND_FILE)
    df["dt"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    return df.set_index("dt")["funding_rate"].sort_index()

def fg_to_mods(v):
    if v is None: return {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"}
    v = int(v)
    if v >= 75: return {"bull_mod": 2, "bear_mod": 8, "value": v, "label": "extreme_greed"}
    if v >= 55: return {"bull_mod": 7, "bear_mod": 3, "value": v, "label": "greed"}
    if v >= 45: return {"bull_mod": 5, "bear_mod": 5, "value": v, "label": "neutral"}
    if v >= 25: return {"bull_mod": 3, "bear_mod": 7, "value": v, "label": "fear"}
    return           {"bull_mod": 8, "bear_mod": 2, "value": v, "label": "extreme_fear"}

def funding_real(rate):
    if rate is None or np.isnan(rate):
        return {"bull_mod": 3, "bear_mod": 3, "funding_rate": 0.0}
    if rate > 0.0015: return {"bull_mod": 0, "bear_mod": 8, "funding_rate": rate}
    if rate > 0.0008: return {"bull_mod": 1, "bear_mod": 6, "funding_rate": rate}
    if rate > 0.0003: return {"bull_mod": 3, "bear_mod": 4, "funding_rate": rate}
    if rate >= -0.0003: return {"bull_mod": 4, "bear_mod": 3, "funding_rate": rate}
    if rate >= -0.0008: return {"bull_mod": 6, "bear_mod": 1, "funding_rate": rate}
    return                     {"bull_mod": 8, "bear_mod": 0, "funding_rate": rate}

def build_extras(mode, ts, dvol_s, fg_s, funding_s):
    extras = {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }

    if mode == "v13_live":
        # F&G real
        fg_val = None
        try:
            idx = fg_s.index.asof(ts.normalize())
            if idx is not pd.NaT: fg_val = int(fg_s[idx])
        except Exception: pass
        extras["fear_greed"] = fg_to_mods(fg_val)
        # Funding real
        rate = None
        try:
            idx = funding_s.index.asof(ts)
            if idx is not pd.NaT: rate = float(funding_s[idx])
        except Exception: pass
        extras["funding"] = funding_real(rate)

    elif mode == "v14":
        # DVOL reemplaza F&G
        dvol_val = None
        try:
            idx = dvol_s.index.asof(ts)
            if idx is not pd.NaT: dvol_val = float(dvol_s[idx])
        except Exception: pass
        ds = dvol_score(dvol_val)
        extras["fear_greed"] = {
            "bull_mod": ds["bull_mod"], "bear_mod": ds["bear_mod"],
            "value": dvol_val or 55, "label": ds["label"],
        }
        # Funding neutro
        extras["funding"] = {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3}

    return extras


def run(df, pair, mode, dvol_s, fg_s, funding_s):
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

        extras = build_extras(mode, ts, dvol_s, fg_s, funding_s)
        signal = strat.get_signal(df_slice, extras, row=row)
        rp = apply_regime(rp_base, signal.regime)
        rp["take_profit_atr_mult"] = _dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0) or 0

        # Risk factor DVOL en V14
        if mode == "v14":
            try:
                idx = dvol_s.index.asof(ts)
                if idx is not pd.NaT:
                    rf = dvol_score(float(dvol_s[idx]))["risk_factor"]
                    if rf < 1.0:
                        rp = dict(rp)
                        rp["risk_pct"] = rp["risk_pct"] * rf
            except Exception: pass

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
CONFIGS = [
    ("V13 producción", "v13_live"),
    ("V14 propuesta",  "v14"),
]


def main():
    dvol_s    = load_dvol()
    fg_s      = load_fg()
    funding_s = load_funding()

    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            all_dfs[pair] = df

    print(f"\n{'='*70}")
    print(f"  COMPARATIVA DEFINITIVA: V13 producción vs V14 propuesta")
    print(f"  Pares: {', '.join(all_dfs)}")
    print(f"{'='*70}")
    print(f"\n  V13 producción: F&G real + Funding real + OI desactivado")
    print(f"  V14 propuesta:  DVOL (reemplaza F&G) + Funding neutro + OI desactivado\n")

    grand_totals = {label: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
                    for label, _ in CONFIGS}

    for period_name, start, end in PERIODS:
        print(f"\n{'─'*68}")
        print(f"  {period_name}  ({start} → {end})")
        print(f"{'─'*68}")
        print(f"  {'Config':<22} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>7}")
        print(f"  {'-'*22} {'-'*8} {'-'*7} {'-'*6} {'-'*7}")

        period_totals = {label: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
                         for label, _ in CONFIGS}

        for pair, df_full in all_dfs.items():
            df = df_full[(df_full["timestamp"] >= start) & (df_full["timestamp"] < end)].reset_index(drop=True)
            if len(df) < 300: continue
            df = precompute_indicators(df)
            for label, mode in CONFIGS:
                r = run(df, pair, mode, dvol_s, fg_s, funding_s)
                for t in (period_totals[label], grand_totals[label]):
                    t["pnl"]    += r["pnl"]
                    t["trades"] += r["trades"]
                    t["wins"]   += round(r["trades"] * r["wr"] / 100)
                    t["dd"]      = max(t["dd"], r["dd"])

        ref_pnl = None
        for label, _ in CONFIGS:
            t = period_totals[label]
            wr = t["wins"] / t["trades"] * 100 if t["trades"] else 0
            diff = f"  ({t['pnl']-ref_pnl:+.0f})" if ref_pnl is not None else ""
            print(f"  {label:<22} {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>6.1f}%{diff}")
            if ref_pnl is None: ref_pnl = t["pnl"]

    # Resumen global
    print(f"\n{'='*68}")
    print(f"  RESUMEN GLOBAL (3 periodos + 3 pares combinados)")
    print(f"{'='*68}")
    print(f"  {'Config':<22} {'PnL total':>10} {'Trades':>7} {'WR':>6} {'DD máx':>7}")
    print(f"  {'-'*22} {'-'*10} {'-'*7} {'-'*6} {'-'*7}")
    ref_pnl = None
    for label, _ in CONFIGS:
        t = grand_totals[label]
        wr = t["wins"] / t["trades"] * 100 if t["trades"] else 0
        diff = f"  ({t['pnl']-ref_pnl:+.0f})" if ref_pnl is not None else ""
        print(f"  {label:<22} {t['pnl']:>10.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>6.1f}%{diff}")
        if ref_pnl is None: ref_pnl = t["pnl"]
    print()


if __name__ == "__main__":
    main()
