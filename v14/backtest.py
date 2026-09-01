"""
V14 — Backtest comparativo: Kelly dinámico + filtro ATR extremo.

Configs probadas:
  V13 baseline   — riesgo fijo 5%, sin filtros extra
  A — Kelly ML   — escala risk_pct según probabilidad raw del modelo (0.03-0.09%)
  B — ATR pct    — reduce riesgo cuando ATR está en percentil extremo (>92% o <8%)
  C — A + B      — Kelly + ATR combinados

Kelly: usa strat._last_prob (prob XGBoost del trade concreto) para escalar riesgo.
  prob 0.55-0.60 → 3%   prob 0.60-0.65 → 4%   prob 0.65-0.70 → 5%
  prob 0.70-0.75 → 7%   prob 0.75+     → 9%

ATR percentil: calcula percentil 200-vela del ATR. Si >92% → reduce riesgo 40%.
  Si <8% → reduce riesgo 40% (mercado demasiado quieto, TP inalcanzable).

Run: python -m v14.backtest
"""

import sys, json
import numpy as np
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

def _live_extras():
    return {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
        "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }

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

# ── Kelly: escala risk_pct según probabilidad ML ───────────────────────────────
_KELLY_TIERS = [
    (0.75, 0.09),
    (0.70, 0.07),
    (0.65, 0.05),
    (0.60, 0.04),
    (0.00, 0.03),
]

def kelly_risk(prob: float) -> float:
    for threshold, risk in _KELLY_TIERS:
        if prob >= threshold:
            return risk
    return 0.03

# ── ATR percentil: ventana rolling 200 velas ──────────────────────────────────
ATR_WINDOW   = 200
ATR_HIGH_PCT = 92   # muy volátil → reducir
ATR_LOW_PCT  =  8   # muy quieto  → reducir

def _atr_series(df: pd.DataFrame) -> pd.Series:
    atr_col = "atr" if "atr" in df.columns else None
    if atr_col:
        return df[atr_col]
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(14).mean()

def _atr_percentile(atr_series: pd.Series, i: int) -> float:
    start = max(0, i - ATR_WINDOW)
    window = atr_series.iloc[start:i+1].dropna()
    if len(window) < 20:
        return 50.0
    current = atr_series.iloc[i]
    return float((window < current).mean() * 100)


def run(df: pd.DataFrame, pair: str, use_kelly: bool, use_atr_filter: bool) -> dict:
    state   = load_state("__nonexistent__")
    strat   = make_strategy()
    peak_eq = 1000.0
    max_dd  = 0.0
    rp_base = _base_risk()
    atr_ser = _atr_series(df)

    for i in range(100, len(df)):
        row = df.iloc[i]
        ts  = pd.Timestamp(row["timestamp"])
        reset_daily_counter(state, str(ts.date()))
        state["current_candle_index"] = i
        price = float(row["close"])
        df_slice = df.iloc[max(0, i-299):i+1]

        signal = strat.get_signal(df_slice, _live_extras(), row=row)
        rp = apply_regime(rp_base, signal.regime)
        rp["take_profit_atr_mult"] = _dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0) or 0

        # ── Kelly dinámico ────────────────────────────────────────────────────
        if use_kelly and getattr(strat, "_last_prob", None) is not None:
            rp = dict(rp)
            rp["risk_pct"] = kelly_risk(strat._last_prob)

        # ── Filtro ATR percentil ──────────────────────────────────────────────
        if use_atr_filter and state.get("position") is None:
            pct = _atr_percentile(atr_ser, i)
            if pct > ATR_HIGH_PCT or pct < ATR_LOW_PCT:
                rp = dict(rp)
                rp["risk_pct"] = rp.get("risk_pct", 0.05) * 0.6  # reducir 40%

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
    ("V13 baseline",   False, False),
    ("A — Kelly ML",   True,  False),
    ("B — ATR pct",    False, True),
    ("C — Kelly+ATR",  True,  True),
]


def main():
    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            all_dfs[pair] = df

    print(f"\nV14 — Kelly dinámico + filtro ATR extremo  |  Pares: {', '.join(all_dfs)}\n")

    for period_name, start, end in PERIODS:
        print(f"\n{'='*66}")
        print(f"  PERIODO: {period_name}  ({start} → {end})")
        print(f"{'='*66}")
        print(f"  {'Config':<22} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6}")
        print(f"  {'-'*22} {'-'*8} {'-'*7} {'-'*6} {'-'*6}")

        totals = {label: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
                  for label, *_ in CONFIGS}

        for pair, df_full in all_dfs.items():
            df = df_full[(df_full["timestamp"] >= start) & (df_full["timestamp"] < end)].reset_index(drop=True)
            if len(df) < 300:
                continue
            df = precompute_indicators(df)

            for label, kelly, atr_f in CONFIGS:
                r = run(df, pair, kelly, atr_f)
                t = totals[label]
                t["pnl"]    += r["pnl"]
                t["trades"] += r["trades"]
                t["wins"]   += round(r["trades"] * r["wr"] / 100)
                t["dd"]      = max(t["dd"], r["dd"])

        ref_pnl = None
        for label, *_ in CONFIGS:
            t = totals[label]
            wr = t["wins"] / t["trades"] * 100 if t["trades"] else 0
            diff = f"  ({t['pnl']-ref_pnl:+.0f})" if ref_pnl is not None else ""
            print(f"  {label:<22} {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>5.1f}%{diff}")
            if ref_pnl is None:
                ref_pnl = t["pnl"]

    print()


if __name__ == "__main__":
    main()
