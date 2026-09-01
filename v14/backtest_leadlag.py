"""
V14 — Backtest: Lead-lag BTC → ETH/XRP.

Hipótesis (paper JEDEC 2024): los retornos de BTC en t-1 predicen
significativamente los retornos de ETH/XRP en t.

Implementación como score modifier de Layer 3:
  Cuando el bot evalúa ETH o XRP, mira el retorno de BTC en la vela anterior.
  BTC +0.5% → +4 bull  para ETH/XRP (probablemente va a seguir)
  BTC +0.2% → +2 bull
  BTC -0.2% → +2 bear
  BTC -0.5% → +4 bear
  Neutro    → sin cambio

BTC siempre usa su propio precio (no lead-lag sobre sí mismo).

Run: venv/bin/python -m v14.backtest_leadlag
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

MODEL_DIR = ROOT / "v13" / "models"
DVOL_FILE = ROOT / "data" / "btc_dvol_1h.csv"
BTC_FILE  = ROOT / "data" / "btc_15m_full.csv"

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

def load_btc_returns():
    """BTC 15m returns — para usar como lead-lag en ETH/XRP."""
    df = pd.read_csv(BTC_FILE)
    df["dt"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("dt").sort_index()
    df["ret"] = df["close"].pct_change() * 100  # retorno en %
    return df["ret"]

def btc_leadlag_mods(btc_ret_prev):
    """Convierte retorno BTC en modificadores de score para altcoins."""
    if btc_ret_prev is None or np.isnan(btc_ret_prev):
        return {"bull_mod": 0, "bear_mod": 0}
    r = float(btc_ret_prev)
    if r > 0.8:    return {"bull_mod": 5, "bear_mod": 0}
    if r > 0.4:    return {"bull_mod": 3, "bear_mod": 0}
    if r > 0.15:   return {"bull_mod": 1, "bear_mod": 0}
    if r < -0.8:   return {"bull_mod": 0, "bear_mod": 5}
    if r < -0.4:   return {"bull_mod": 0, "bear_mod": 3}
    if r < -0.15:  return {"bull_mod": 0, "bear_mod": 1}
    return             {"bull_mod": 0, "bear_mod": 0}  # movimiento neutro

def build_extras(mode, ts, pair, dvol_s, btc_ret_s):
    """V14 base (DVOL + funding neutro) + lead-lag BTC opcional."""
    # DVOL reemplaza F&G
    dvol_val = None
    try:
        idx = dvol_s.index.asof(ts)
        if idx is not pd.NaT:
            dvol_val = float(dvol_s[idx])
    except Exception:
        pass
    ds = dvol_score(dvol_val)

    extras = {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "fear_greed": {"bull_mod": ds["bull_mod"], "bear_mod": ds["bear_mod"],
                       "value": dvol_val or 55, "label": ds["label"]},
        "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }

    # Lead-lag: solo para ETH y XRP (no BTC sobre sí mismo)
    if mode == "leadlag" and pair != "BTC":
        btc_ret = None
        try:
            # Retorno de BTC en la vela anterior al ts actual
            ts_prev = ts - pd.Timedelta(minutes=15)
            idx = btc_ret_s.index.asof(ts_prev)
            if idx is not pd.NaT:
                btc_ret = float(btc_ret_s[idx])
        except Exception:
            pass
        ll = btc_leadlag_mods(btc_ret)
        extras["macro_corr"] = ll  # usa el slot de macro_corr

    return extras


def run(df, pair, mode, dvol_s, btc_ret_s):
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

        extras = build_extras(mode, ts, pair, dvol_s, btc_ret_s)
        signal = strat.get_signal(df_slice, extras, row=row)
        rp = apply_regime(rp_base, signal.regime)
        rp["take_profit_atr_mult"] = _dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0) or 0

        # Risk factor DVOL
        if dvol_s is not None:
            try:
                idx = dvol_s.index.asof(ts)
                if idx is not pd.NaT:
                    rf = dvol_score(float(dvol_s[idx]))["risk_factor"]
                    if rf < 1.0:
                        rp = dict(rp)
                        rp["risk_pct"] = rp["risk_pct"] * rf
            except Exception:
                pass

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
    ("V14 base",         "base"),
    ("V14 + Lead-lag",   "leadlag"),
]


def main():
    dvol_s    = load_dvol()
    btc_ret_s = load_btc_returns()
    print(f"DVOL: {len(dvol_s)} h | BTC returns: {len(btc_ret_s)} velas 15m")
    print(f"  (Lead-lag activo solo en ETH y XRP, no en BTC)\n")

    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            all_dfs[pair] = df

    print(f"Lead-lag BTC → ETH/XRP  |  Pares: {', '.join(all_dfs)}\n")

    for period_name, start, end in PERIODS:
        print(f"\n{'='*66}")
        print(f"  PERIODO: {period_name}  ({start} → {end})")
        print(f"{'='*66}")

        # Resultados por par y total
        results = {label: {} for label, _ in CONFIGS}
        totals  = {label: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
                   for label, _ in CONFIGS}

        for pair, df_full in all_dfs.items():
            df = df_full[(df_full["timestamp"] >= start) & (df_full["timestamp"] < end)].reset_index(drop=True)
            if len(df) < 300: continue
            df = precompute_indicators(df)
            for label, mode in CONFIGS:
                r = run(df, pair, mode, dvol_s, btc_ret_s)
                results[label][pair] = r
                t = totals[label]
                t["pnl"]    += r["pnl"]
                t["trades"] += r["trades"]
                t["wins"]   += round(r["trades"] * r["wr"] / 100)
                t["dd"]      = max(t["dd"], r["dd"])

        # Mostrar por par
        print(f"\n  Por par:")
        print(f"  {'Par':<6} {'Config':<20} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6}")
        print(f"  {'-'*6} {'-'*20} {'-'*8} {'-'*7} {'-'*6} {'-'*6}")
        for pair in all_dfs:
            for label, _ in CONFIGS:
                r = results[label].get(pair)
                if r:
                    print(f"  {pair:<6} {label:<20} {r['pnl']:>8.0f} {r['trades']:>7} {r['wr']:>5.1f}% {r['dd']:>5.1f}%")

        # Total
        print(f"\n  Total combinado:")
        print(f"  {'Config':<26} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6}")
        print(f"  {'-'*26} {'-'*8} {'-'*7} {'-'*6} {'-'*6}")
        ref_pnl = None
        for label, _ in CONFIGS:
            t = totals[label]
            wr = t["wins"] / t["trades"] * 100 if t["trades"] else 0
            diff = f"  ({t['pnl']-ref_pnl:+.0f})" if ref_pnl is not None else ""
            print(f"  {label:<26} {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>5.1f}%{diff}")
            if ref_pnl is None: ref_pnl = t["pnl"]

    print()


if __name__ == "__main__":
    main()
