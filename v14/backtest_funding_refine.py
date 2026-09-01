"""
V14 — Refinamiento del funding rate.

¿Podemos mejorar la señal de funding en lugar de ignorarla?

Configs:
  Baseline neutro      — funding fijo 3/3 (ignorado)
  Funding real         — lógica actual (umbral absoluto fijo)
  Funding percentil    — umbral dinámico: percentil de las últimas 2 semanas
  Funding ROC          — tasa de cambio: funding subiendo/bajando rápido
  Funding percentil+ROC — combinación de ambos refinamientos

Run: venv/bin/python -m v14.backtest_funding_refine
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
FUNDING_FILE = ROOT / "data" / "funding_rate_historical.csv"

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

def load_funding():
    df = pd.read_csv(FUNDING_FILE)
    df["dt"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    return df.set_index("dt")["funding_rate"].sort_index()

# ── Lógica actual (umbral absoluto fijo) ──────────────────────────────────────
def funding_real(rate):
    if rate is None or np.isnan(rate):
        return {"bull_mod": 3, "bear_mod": 3, "funding_rate": 0.0}
    if rate > 0.0015: return {"bull_mod": 0, "bear_mod": 8, "funding_rate": rate}
    if rate > 0.0008: return {"bull_mod": 1, "bear_mod": 6, "funding_rate": rate}
    if rate > 0.0003: return {"bull_mod": 3, "bear_mod": 4, "funding_rate": rate}
    if rate >= -0.0003: return {"bull_mod": 4, "bear_mod": 3, "funding_rate": rate}
    if rate >= -0.0008: return {"bull_mod": 6, "bear_mod": 1, "funding_rate": rate}
    return                     {"bull_mod": 8, "bear_mod": 0, "funding_rate": rate}

# ── Funding percentil dinámico (ventana 14 días = 42 registros de 8h) ─────────
WINDOW_PERIODS = 42  # 14 días × 3 registros/día

def funding_percentil(rate, funding_series, ts):
    if rate is None or np.isnan(rate):
        return {"bull_mod": 3, "bear_mod": 3, "funding_rate": 0.0}
    try:
        # Ventana de las últimas 2 semanas antes de ts
        window_start = ts - pd.Timedelta(days=14)
        window = funding_series[(funding_series.index >= window_start) &
                                (funding_series.index <= ts)]
        if len(window) < 10:
            return funding_real(rate)
        pct = float((window < rate).mean() * 100)
    except Exception:
        return funding_real(rate)

    # Señal basada en percentil relativo, no en valor absoluto
    if pct > 90:   return {"bull_mod": 0, "bear_mod": 8, "funding_rate": rate}  # extremo alto
    if pct > 75:   return {"bull_mod": 1, "bear_mod": 6, "funding_rate": rate}  # alto
    if pct > 55:   return {"bull_mod": 3, "bear_mod": 4, "funding_rate": rate}  # elevado
    if pct > 45:   return {"bull_mod": 4, "bear_mod": 3, "funding_rate": rate}  # normal
    if pct > 25:   return {"bull_mod": 5, "bear_mod": 2, "funding_rate": rate}  # bajo
    return                {"bull_mod": 7, "bear_mod": 0, "funding_rate": rate}  # extremo bajo

# ── Funding ROC (cambio respecto a hace 3 registros = 24h) ────────────────────
def funding_roc(rate, funding_series, ts):
    if rate is None or np.isnan(rate):
        return {"bull_mod": 3, "bear_mod": 3, "funding_rate": 0.0}
    try:
        # Valor de hace ~24h
        ts_prev = ts - pd.Timedelta(hours=24)
        idx_prev = funding_series.index.asof(ts_prev)
        if idx_prev is pd.NaT:
            return {"bull_mod": 3, "bear_mod": 3, "funding_rate": rate}
        prev_rate = float(funding_series[idx_prev])
        roc = rate - prev_rate  # cambio absoluto en 24h
    except Exception:
        return {"bull_mod": 3, "bear_mod": 3, "funding_rate": rate}

    # Nivel base del funding + ajuste por dirección del cambio
    base = funding_real(rate)
    if roc > 0.0005:   # subiendo rápido → más presión alcista que se puede revertir
        base = dict(base)
        base["bear_mod"] = min(8, base["bear_mod"] + 2)
        base["bull_mod"] = max(0, base["bull_mod"] - 1)
    elif roc < -0.0005:  # bajando rápido → presión liberada → más alcista
        base = dict(base)
        base["bull_mod"] = min(8, base["bull_mod"] + 2)
        base["bear_mod"] = max(0, base["bear_mod"] - 1)
    return base

# ── Percentil + ROC combinados ────────────────────────────────────────────────
def funding_percentil_roc(rate, funding_series, ts):
    pct_mod = funding_percentil(rate, funding_series, ts)
    try:
        ts_prev = ts - pd.Timedelta(hours=24)
        idx_prev = funding_series.index.asof(ts_prev)
        if idx_prev is pd.NaT:
            return pct_mod
        prev_rate = float(funding_series[idx_prev])
        roc = rate - prev_rate
    except Exception:
        return pct_mod

    result = dict(pct_mod)
    if roc > 0.0005:
        result["bear_mod"] = min(8, result["bear_mod"] + 2)
        result["bull_mod"] = max(0, result["bull_mod"] - 1)
    elif roc < -0.0005:
        result["bull_mod"] = min(8, result["bull_mod"] + 2)
        result["bear_mod"] = max(0, result["bear_mod"] - 1)
    return result


def build_extras(mode, ts, funding_series):
    extras = {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }

    if mode == "neutro":
        extras["funding"] = {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3}
        return extras

    rate = None
    try:
        idx = funding_series.index.asof(ts)
        if idx is not pd.NaT:
            rate = float(funding_series[idx])
    except Exception:
        pass

    if mode == "real":
        extras["funding"] = funding_real(rate)
    elif mode == "percentil":
        extras["funding"] = funding_percentil(rate, funding_series, ts)
    elif mode == "roc":
        extras["funding"] = funding_roc(rate, funding_series, ts)
    elif mode == "percentil_roc":
        extras["funding"] = funding_percentil_roc(rate, funding_series, ts)

    return extras


def run(df, pair, mode, funding_series):
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

        extras = build_extras(mode, ts, funding_series)
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
    ("Bear 2022",   "2022-01-01", "2023-01-01"),
    ("OOS 2025-26", "2025-01-01", "2026-09-01"),
]
DATASETS = [
    (ROOT / "data" / "btc_15m_full.csv",  "BTC"),
    (ROOT / "data" / "eth_2023_2026.csv", "ETH"),
    (ROOT / "data" / "xrp_15m_full.csv",  "XRP"),
]
CONFIGS = [
    ("Baseline neutro",    "neutro"),
    ("Funding real",       "real"),
    ("Funding percentil",  "percentil"),
    ("Funding ROC",        "roc"),
    ("Percentil + ROC",    "percentil_roc"),
]


def main():
    funding_series = load_funding()
    print(f"Funding: {len(funding_series)} registros "
          f"({funding_series.index[0].date()} → {funding_series.index[-1].date()})")

    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            all_dfs[pair] = df

    print(f"\nRefinamiento funding rate  |  Pares: {', '.join(all_dfs)}\n")

    for period_name, start, end in PERIODS:
        print(f"\n{'='*68}")
        print(f"  PERIODO: {period_name}  ({start} → {end})")
        print(f"{'='*68}")
        print(f"  {'Config':<24} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6}")
        print(f"  {'-'*24} {'-'*8} {'-'*7} {'-'*6} {'-'*6}")

        totals = {label: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
                  for label, _ in CONFIGS}

        for pair, df_full in all_dfs.items():
            df = df_full[(df_full["timestamp"] >= start) & (df_full["timestamp"] < end)].reset_index(drop=True)
            if len(df) < 300:
                continue
            df = precompute_indicators(df)
            for label, mode in CONFIGS:
                r = run(df, pair, mode, funding_series)
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
            print(f"  {label:<24} {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>5.1f}%{diff}")
            if ref_pnl is None:
                ref_pnl = t["pnl"]

    print()


if __name__ == "__main__":
    main()
