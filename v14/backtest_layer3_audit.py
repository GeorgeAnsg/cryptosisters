"""
V14 — Audit completo de Layer 3: ¿qué componentes ayudan y cuáles perjudican?

Para cada señal de Layer 3, compara:
  - Señal en NEUTRO (como llevan los backtests hasta ahora)
  - Señal con datos REALES históricos

Si real < neutro → la señal está perjudicando al bot en live.

Componentes analizados:
  Fear & Greed   — data/fear_greed_historical.csv
  Funding rate   — data/funding_rate_historical.csv
  OI (ROC)       — data/oi_historical_4h.csv

Run: venv/bin/python -m v14.backtest_layer3_audit
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

MODEL_DIR = ROOT / "v13" / "models"

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

# ── Loaders de datos históricos ───────────────────────────────────────────────

def load_fg():
    df = pd.read_csv(ROOT / "data" / "fear_greed_historical.csv")
    df["dt"] = pd.to_datetime(df["date"], format="%d-%m-%Y", utc=True)
    return df.set_index("dt")["value"].sort_index()

def load_funding():
    df = pd.read_csv(ROOT / "data" / "funding_rate_historical.csv")
    df["dt"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    return df.set_index("dt")["funding_rate"].sort_index()

def load_oi():
    df = pd.read_csv(ROOT / "data" / "oi_historical_4h.csv")
    df["dt"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    s = df.set_index("dt")["open_interest"].sort_index()
    # ROC 24h (6 candles de 4h)
    roc = s.pct_change(6) * 100
    return roc

# ── Conversores a mods ────────────────────────────────────────────────────────

def fg_to_mods(v):
    if v is None or np.isnan(v):
        return {"bull_mod": 5, "bear_mod": 5}
    v = int(v)
    if v >= 75: return {"bull_mod": 2, "bear_mod": 8}
    if v >= 55: return {"bull_mod": 7, "bear_mod": 3}
    if v >= 45: return {"bull_mod": 5, "bear_mod": 5}
    if v >= 25: return {"bull_mod": 3, "bear_mod": 7}
    return           {"bull_mod": 8, "bear_mod": 2}

def funding_to_mods(rate):
    if rate is None or np.isnan(rate):
        return {"bull_mod": 3, "bear_mod": 3, "funding_rate": 0.0}
    if rate > 0.0015: return {"bull_mod": 0, "bear_mod": 8, "funding_rate": rate}
    if rate > 0.0008: return {"bull_mod": 1, "bear_mod": 6, "funding_rate": rate}
    if rate > 0.0003: return {"bull_mod": 3, "bear_mod": 4, "funding_rate": rate}
    if rate >= -0.0003: return {"bull_mod": 4, "bear_mod": 3, "funding_rate": rate}
    if rate >= -0.0008: return {"bull_mod": 6, "bear_mod": 1, "funding_rate": rate}
    return                     {"bull_mod": 8, "bear_mod": 0, "funding_rate": rate}

def oi_to_mods(roc):
    if roc is None or np.isnan(roc):
        return {"bull_mod": 0, "bear_mod": 0}
    if roc > 5:   return {"bull_mod": 2, "bear_mod": 3}   # OI subiendo rápido → crowded
    if roc > 2:   return {"bull_mod": 2, "bear_mod": 2}
    if roc > -2:  return {"bull_mod": 0, "bear_mod": 0}   # estable → neutro
    if roc > -5:  return {"bull_mod": 2, "bear_mod": 1}
    return               {"bull_mod": 4, "bear_mod": 0}   # OI bajando rápido → squeeze

# ── Build extras según modo ───────────────────────────────────────────────────

def build_extras(mode, ts, fg_s, funding_s, oi_s):
    # base siempre neutro
    extras = {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
        "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }

    if mode == "fg_real":
        try:
            idx = fg_s.index.asof(ts.normalize())
            if idx is not pd.NaT:
                m = fg_to_mods(fg_s[idx])
                extras["fear_greed"] = {**m, "value": int(fg_s[idx]), "label": "real"}
        except Exception: pass

    elif mode == "funding_real":
        try:
            idx = funding_s.index.asof(ts)
            if idx is not pd.NaT:
                extras["funding"] = funding_to_mods(funding_s[idx])
        except Exception: pass

    elif mode == "oi_real":
        try:
            idx = oi_s.index.asof(ts)
            if idx is not pd.NaT:
                m = oi_to_mods(oi_s[idx])
                extras["macro_corr"] = m  # OI goes into macro_corr slot
        except Exception: pass

    elif mode == "all_real":
        try:
            idx = fg_s.index.asof(ts.normalize())
            if idx is not pd.NaT:
                m = fg_to_mods(fg_s[idx])
                extras["fear_greed"] = {**m, "value": int(fg_s[idx]), "label": "real"}
        except Exception: pass
        try:
            idx = funding_s.index.asof(ts)
            if idx is not pd.NaT:
                extras["funding"] = funding_to_mods(funding_s[idx])
        except Exception: pass
        try:
            idx = oi_s.index.asof(ts)
            if idx is not pd.NaT:
                m = oi_to_mods(oi_s[idx])
                extras["macro_corr"] = m
        except Exception: pass

    return extras


def run(df, pair, mode, fg_s, funding_s, oi_s):
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

        extras = build_extras(mode, ts, fg_s, funding_s, oi_s)
        signal = strat.get_signal(df_slice, extras, row=row)
        rp = apply_regime(rp_base, signal.regime)
        rp["take_profit_atr_mult"] = _dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0) or 0

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
    ("OOS 2025-26",  "2025-01-01", "2026-09-01"),  # el que más importa
]
DATASETS = [
    (ROOT / "data" / "btc_15m_full.csv",  "BTC"),
    (ROOT / "data" / "eth_2023_2026.csv", "ETH"),
    (ROOT / "data" / "xrp_15m_full.csv",  "XRP"),
]

CONFIGS = [
    ("Baseline neutro",  "neutral"),
    ("+ FG real",        "fg_real"),
    ("+ Funding real",   "funding_real"),
    ("+ OI real",        "oi_real"),
    ("Todo real",        "all_real"),
]


def main():
    fg_s      = load_fg()
    funding_s = load_funding()
    oi_s      = load_oi()
    print(f"F&G: {len(fg_s)} días | Funding: {len(funding_s)} registros | OI: {len(oi_s)} registros")

    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            all_dfs[pair] = df

    print(f"\nAudit Layer 3  |  Pares: {', '.join(all_dfs)}\n")
    print("  (+ = mejor que baseline, - = peor)\n")

    for period_name, start, end in PERIODS:
        print(f"\n{'='*68}")
        print(f"  PERIODO: {period_name}  ({start} → {end})")
        print(f"{'='*68}")
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
                r = run(df, pair, mode, fg_s, funding_s, oi_s)
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
