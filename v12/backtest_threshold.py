"""
V12 — Sweep de umbrales de score y ML threshold.

Prueba combinaciones de min_score y ml_threshold en OOS 2025-26
con el filtro de régimen activado.

Run: python -m v12.backtest_threshold
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

def make_strategy(ml_threshold):
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=ml_threshold)
    s.feature_cols = meta["feature_cols"]
    return s

def _make_risk(min_score):
    return {
        "risk_pct": 0.05, "max_cost_pct": 0.87,
        "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
        "min_score": min_score, "entry_advantage": 15, "max_daily_trades": 6,
        "max_drawdown_pct": 0.25, "max_daily_loss_pct": 0.03,
        "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
        "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
    }

def run(df, pair, min_score, ml_threshold):
    state = load_state("__nonexistent__")
    strat = make_strategy(ml_threshold)
    peak_eq = 1000.0
    max_dd = 0.0
    risk_params = _make_risk(min_score)

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

        # Filtro de régimen en fin de semana
        if ts.weekday() >= 5:
            if signal.regime == "bull":
                rp["weekend_mode"] = "range"
                rp["weekend_min_score_bonus"] = 10
            else:
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
    pnls = [t["pnl"] for t in state.get("trades", []) if t.get("action", "").startswith("CLOSE_") and "pnl" in t]
    wins_p  = [p for p in pnls if p > 0]
    loses_p = [p for p in pnls if p <= 0]
    pf = abs(sum(wins_p) / sum(loses_p)) if loses_p else 99.0

    return {"pnl": round(state["balance_usdt"] - 1000, 2), "wr": round(wr, 1),
            "trades": total, "dd": round(max_dd, 1), "pf": round(pf, 2)}


DATASETS = [
    (ROOT / "data" / "btc_15m_full.csv",  "BTC"),
    (ROOT / "data" / "eth_2023_2026.csv", "ETH"),
    (ROOT / "data" / "xrp_15m_full.csv",  "XRP"),
]

START = "2025-01-01"
END   = "2026-09-01"

# Combinaciones a probar: (min_score, ml_threshold)
COMBOS = [
    (55, 0.55),
    (58, 0.55),   # actual
    (60, 0.55),
    (63, 0.55),
    (65, 0.55),
    (58, 0.57),
    (58, 0.60),
    (60, 0.57),
    (60, 0.60),
    (63, 0.57),
]


def main():
    # Cargar datos una vez
    all_dfs = {}
    for path, pair in DATASETS:
        if not path.exists():
            print(f"[SKIP] {pair}: {path} no encontrado")
            continue
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df[(df["timestamp"] >= START) & (df["timestamp"] < END)].reset_index(drop=True)
        if len(df) > 300:
            all_dfs[pair] = precompute_indicators(df)
            print(f"[{pair}] {len(all_dfs[pair])} velas cargadas")

    pairs = list(all_dfs.keys())
    print(f"\nPeriodo: {START} → {END}  |  Pares: {', '.join(pairs)}")
    print(f"Filtro de régimen: ACTIVO (trend+58 en fin de semana si régimen ≠ bull)\n")

    header = f"  {'min_score':>9} {'ml_thr':>6} | {'PnL':>8} {'Trades':>7} {'WR':>6} {'MaxDD':>6} {'PF':>5}"
    print(header)
    print("  " + "-"*9 + " " + "-"*6 + "-+-" + "-"*8 + " " + "-"*7 + " " + "-"*6 + " " + "-"*6 + " " + "-"*5)

    best_pnl = -999999
    best_combo = None

    for min_score, ml_thr in COMBOS:
        totals = {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
        for pair, df in all_dfs.items():
            r = run(df, pair, min_score, ml_thr)
            totals["pnl"]    += r["pnl"]
            totals["trades"] += r["trades"]
            totals["wins"]   += round(r["trades"] * r["wr"] / 100)
            totals["dd"]      = max(totals["dd"], r["dd"])

        t = totals
        wr = t["wins"] / t["trades"] * 100 if t["trades"] else 0
        pf_total = "—"  # no calculamos PF total fácilmente

        marker = " ← actual" if (min_score == 58 and ml_thr == 0.55) else ""
        print(f"  {min_score:>9} {ml_thr:>6.2f} | {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>5.1f}% {'—':>5}{marker}")

        if t["pnl"] > best_pnl:
            best_pnl = t["pnl"]
            best_combo = (min_score, ml_thr)

    print(f"\n  Mejor PnL total: min_score={best_combo[0]}, ml_threshold={best_combo[1]:.2f} → {best_pnl:.0f}")
    print()


if __name__ == "__main__":
    main()
