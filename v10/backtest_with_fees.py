"""
V10 — Backtest OOS con y sin comisiones Bybit.

Comisiones Bybit Futures (taker):
  Abrir:  0.055% del nocional
  Cerrar: 0.055% del nocional
  Total:  0.110% por trade completo (roundtrip)

Run: python v10/backtest_with_fees.py
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
LOCAL_SOL  = ROOT / "data" / "sol_15m_full.csv"
MODEL_DIR  = ROOT / "v7" / "models"
TEST_START = "2025-01-01"

BYBIT_TAKER_FEE = 0.00055  # 0.055%

V10_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

TP_DYNAMIC = {
    ("bull", True): 5.0, ("bull", False): 4.5,
    ("neutral", True): 3.5, ("neutral", False): 3.5,
    ("bear", True): 4.5, ("bear", False): 4.0,
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

def run(df, pair, apply_fees=False):
    state = load_state("__nonexistent__")
    peak_eq = 1000.0; max_dd = 0.0
    strat = make_strategy()
    total_fees = 0.0

    for i in range(100, len(df)):
        row = df.iloc[i]
        ts = pd.Timestamp(row["timestamp"])
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
        rp = apply_regime(V10_RISK, signal.regime)
        rp["take_profit_atr_mult"] = dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0)

        had_pos = state.get("position") is not None
        check_sl_tp(state, pair, price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, price, atr, signal, rp,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

        # Comisiones: apertura
        just_opened = not had_pos and state.get("position") is not None
        just_closed = had_pos and state.get("position") is None

        if apply_fees:
            if just_opened:
                pos = state["position"]
                notional = pos["amount"] * pos["entry_price"]
                fee = notional * BYBIT_TAKER_FEE
                state["balance_usdt"] -= fee
                total_fees += fee
            elif just_closed:
                # fee al cerrar sobre el precio de cierre
                fee = price * abs(state.get("_last_amount", 0)) * BYBIT_TAKER_FEE
                # fallback: estimar via último trade
                trades_closed = [t for t in state["trades"] if t["action"].startswith("CLOSE_")]
                if trades_closed:
                    last = trades_closed[-1]
                    # notional aproximado: recuperamos de la posición si estaba guardada
                    pass
                state["balance_usdt"] -= fee
                total_fees += fee

        # Guardar amount para la comisión de cierre
        if just_opened:
            state["_last_amount"] = state["position"]["amount"]

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
    pnls = [t["pnl"] for t in state["trades"] if t["action"].startswith("CLOSE_") and "pnl" in t]
    wins_p  = [p for p in pnls if p > 0]
    loses_p = [p for p in pnls if p <= 0]
    pf = abs(sum(wins_p)/sum(loses_p)) if sum(loses_p) != 0 else 99.0
    long_wr  = st["long_wins"]  / st["total_longs"]  * 100 if st["total_longs"]  else 0
    short_wr = st["short_wins"] / st["total_shorts"] * 100 if st["total_shorts"] else 0

    return {
        "pnl":    round(state["balance_usdt"] - 1000, 2),
        "wr":     round(wr, 1),
        "trades": total,
        "dd":     round(max_dd, 1),
        "pf":     round(pf, 2),
        "long_wr":  round(long_wr, 1),
        "short_wr": round(short_wr, 1),
        "fees":   round(total_fees, 2),
        "avg_win":  round(sum(wins_p)/len(wins_p) if wins_p else 0, 2),
        "avg_loss": round(sum(loses_p)/len(loses_p) if loses_p else 0, 2),
    }

if __name__ == "__main__":
    print(f"\n{'='*65}")
    print(f"  V10 BACKTEST CON COMISIONES BYBIT — OOS {TEST_START} → hoy")
    print(f"  Taker fee: 0.055% por lado (0.110% roundtrip)")
    print(f"{'='*65}\n")

    datasets = [
        ("BTC", LOCAL_BTC, "BTC/USDT:USDT"),
        ("ETH", LOCAL_ETH, "ETH/USDT:USDT"),
        ("SOL", LOCAL_SOL, "SOL/USDT:USDT"),
    ]

    print("  Cargando datos...")
    dfs = {}
    for label, path, pair in datasets:
        df = pd.read_csv(path, parse_dates=["timestamp"])
        df = df[df["timestamp"] >= TEST_START].reset_index(drop=True)
        dfs[label] = (precompute_indicators(df), pair)
    print()

    print(f"  {'Par':<5} {'Sin fees':>10} {'Con fees':>10} {'Coste fees':>11}  {'WR':>6}  {'DD':>5}  {'PF':>6}  {'Long WR':>8}  {'Short WR':>9}")
    print(f"  {'─'*80}")

    total_sin = total_con = total_fees = 0
    for label, (df, pair) in dfs.items():
        sin = run(df.copy(), pair, apply_fees=False)
        con = run(df.copy(), pair, apply_fees=True)
        diff = con["pnl"] - sin["pnl"]
        total_sin  += sin["pnl"]
        total_con  += con["pnl"]
        total_fees += abs(diff)
        print(f"  {label:<5} {sin['pnl']:>+10.0f} {con['pnl']:>+10.0f} {diff:>+11.0f}  "
              f"{con['wr']:>5.1f}%  {con['dd']:>4.1f}%  {con['pf']:>6.2f}  "
              f"{con['long_wr']:>7.1f}%  {con['short_wr']:>8.1f}%")

    print(f"  {'─'*80}")
    print(f"  {'TOTAL':<5} {total_sin:>+10.0f} {total_con:>+10.0f} {total_con-total_sin:>+11.0f}")
    print(f"\n  Las comisiones representan {abs(total_con-total_sin)/total_sin*100:.1f}% de reducción sobre el PnL bruto.")
    print(f"  Promedio de coste por par: {total_fees/3:.0f} USDT/año\n")
