"""
V10 — Grid search sobre trailing_step_mult y max_tp_extensions.
Sin filtro de horas. OOS 2025-01-01 → hoy.

Run: python v10/grid_search.py
"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import v6.core.bot_core as _bc
_bc._tg_update = lambda *a, **k: None

from v6.core.bot_core import (
    load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v7.strategy_ml import StrategyML

LOCAL_BTC  = ROOT / "data" / "btc_15m_full.csv"
LOCAL_ETH  = ROOT / "data" / "eth_2023_2026.csv"
MODEL_DIR  = ROOT / "v7" / "models"
TEST_START = "2025-01-01"

TP_DYNAMIC = {
    ("bull",    True):  5.0, ("bull",    False): 4.5,
    ("neutral", True):  3.5, ("neutral", False): 3.5,
    ("bear",    True):  4.5, ("bear",    False): 4.0,
}

def dynamic_tp(signal):
    try:
        raw = signal.technical.get("details", {}).get("adx", 0) or 0
        adx = float(str(raw).split()[0]) if isinstance(raw, str) else float(raw)
    except: adx = 0.0
    return TP_DYNAMIC.get((signal.regime, adx >= 25), 4.0)

def make_strategy():
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    s.feature_cols = meta["feature_cols"]
    return s

def run_single(df, pair, step_mult, max_tp_ext):
    risk = {
        "risk_pct": 0.02, "max_cost_pct": 0.35,
        "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
        "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
        "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
        "trailing_stop": True,
        "trailing_step_mult": step_mult,
        "max_tp_extensions": max_tp_ext,
        "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
    }

    trail_moves = 0
    tp_exts = 0
    orig = _bc._tg_update
    def count(p, side, msg, sl, tp, **kw):
        nonlocal trail_moves, tp_exts
        if "Trailing" in msg: trail_moves += 1
        if "TP extendido" in msg: tp_exts += 1
    _bc._tg_update = count

    state = load_state("__nonexistent__")
    peak_eq = 1000.0
    max_dd  = 0.0
    strat = make_strategy()

    try:
        for i in range(100, len(df)):
            row = df.iloc[i]
            ts  = pd.Timestamp(row["timestamp"])
            reset_daily_counter(state, str(ts.date()))
            state["current_candle_index"] = i
            price = float(row["close"])
            df_slice = df.iloc[max(0, i-299):i+1]
            live_extras = {
                "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
                "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
                "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
                "orderbook":  {"bull_mod": 0, "bear_mod": 0},
                "macro_corr": {"bull_mod": 0, "bear_mod": 0},
            }
            signal = strat.get_signal(df_slice, live_extras, row=row)
            rp = apply_regime(risk, signal.regime)
            rp["take_profit_atr_mult"] = dynamic_tp(signal)
            atr = signal.technical.get("details", {}).get("atr", 0)

            check_sl_tp(state, pair, price, rp, atr=atr,
                        scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
            make_decision(state, pair, price, atr, signal, rp,
                          verbose=False, min_hold_candles=0,
                          current_candle_index=i, winrate_table={}, timestamp=ts)

            pos = state.get("position")
            eq  = state["balance_usdt"] + pos["amount"] * pos["entry_price"] if pos else state["balance_usdt"]
            if eq > peak_eq: peak_eq = eq
            dd = (peak_eq - eq) / peak_eq * 100
            if dd > max_dd: max_dd = dd
    finally:
        _bc._tg_update = orig

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")

    st = state["stats"]
    total = st["wins"] + st["losses"]
    wr = st["wins"] / total * 100 if total else 0
    trades = [t for t in state["trades"] if t["action"].startswith("CLOSE_")]
    pnls = [t["pnl"] for t in trades if "pnl" in t]
    wins_pnl  = [p for p in pnls if p > 0]
    loses_pnl = [p for p in pnls if p <= 0]
    pf = abs(sum(wins_pnl) / sum(loses_pnl)) if sum(loses_pnl) != 0 else 99.0
    notifs = round((trail_moves + tp_exts) / total, 1) if total else 0
    return {
        "pnl": round(state["balance_usdt"] - 1000, 2),
        "wr": round(wr, 1),
        "trades": total,
        "dd": round(max_dd, 1),
        "pf": round(pf, 2),
        "notifs": notifs,
    }

if __name__ == "__main__":
    print(f"\n{'='*75}")
    print(f"  GRID SEARCH trailing_step_mult × max_tp_extensions — OOS {TEST_START}")
    print(f"  Sin filtro de horas. BTC + ETH.")
    print(f"{'='*75}\n")

    df_btc = pd.read_csv(LOCAL_BTC, parse_dates=["timestamp"])
    df_btc = df_btc[df_btc["timestamp"] >= TEST_START].reset_index(drop=True)
    df_btc = precompute_indicators(df_btc)

    df_eth = pd.read_csv(LOCAL_ETH, parse_dates=["timestamp"])
    df_eth = df_eth[df_eth["timestamp"] >= TEST_START].reset_index(drop=True)
    df_eth = precompute_indicators(df_eth)

    STEP_MULTS = [0.0, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0]
    TP_EXTS    = [1, 2]

    hdr = f"  {'Config':<28} {'PnL BTC':>8} {'WR':>6} {'DD':>5} {'Avisos':>7}  {'PnL ETH':>8} {'WR':>6} {'DD':>5} {'Avisos':>7}"
    sep = "  " + "─" * (len(hdr) - 2)
    print(hdr)
    print(sep)

    best_combined = -9999
    best_cfg = None

    for tp_ext in TP_EXTS:
        first_in_group = True
        for sm in STEP_MULTS:
            label = f"step={sm:.2f} tp_ext={tp_ext}"
            btc = run_single(df_btc.copy(), "BTC/USDT:USDT", sm, tp_ext)
            eth = run_single(df_eth.copy(), "ETH/USDT:USDT", sm, tp_ext)
            combined = btc["pnl"] + eth["pnl"]
            if first_in_group:
                print()
                first_in_group = False
            print(f"  {label:<28} {btc['pnl']:>+8.0f} {btc['wr']:>5.1f}% {btc['dd']:>4.1f}% {btc['notifs']:>6.1f}  "
                  f"{eth['pnl']:>+8.0f} {eth['wr']:>5.1f}% {eth['dd']:>4.1f}% {eth['notifs']:>6.1f}  "
                  f"[total={combined:+.0f}]")
            if combined > best_combined:
                best_combined = combined
                best_cfg = (sm, tp_ext, btc, eth)

    print(f"\n{sep}")
    sm, tp_ext, btc, eth = best_cfg
    print(f"\n  MEJOR CONFIG: trailing_step_mult={sm}  max_tp_extensions={tp_ext}")
    print(f"  BTC: {btc['pnl']:+.0f} USDT | WR {btc['wr']}% | DD {btc['dd']}% | {btc['notifs']} avisos/trade")
    print(f"  ETH: {eth['pnl']:+.0f} USDT | WR {eth['wr']}% | DD {eth['dd']}% | {eth['notifs']} avisos/trade")
    print(f"  Combined: {best_combined:+.0f} USDT\n")
