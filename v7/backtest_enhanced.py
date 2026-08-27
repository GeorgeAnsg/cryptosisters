"""
V7 Enhanced — TP dinámico + Kelly sizing.

TP dinámico: ajusta el take-profit según régimen + fuerza de tendencia (ADX).
Kelly sizing: ajusta el riesgo por trade según probabilidad ML.

Evalúa cada mejora por separado y combinadas — OOS 2025-2026.

Run: python v7/backtest_enhanced.py
"""

import sys, json, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from v6.core.bot_core import (
    load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v6.core.bot_sentiment import load_fear_greed_sentiment
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import StrategyML

LOCAL_CSV  = ROOT / "data" / "btc_15m_full.csv"
MODEL_DIR  = ROOT / "v7" / "models"
TEST_START = "2025-01-01"

BASE_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

# ── TP dinámico ───────────────────────────────────────────────────────────────
# Lógica: en tendencias fuertes (bull + ADX alto) dejamos correr más.
#         En mercados laterales (neutral) recogemos antes.
TP_DYNAMIC = {
    # (regime, adx_strong) → tp_mult
    ("bull",    True):  5.0,   # tendencia alcista + fuerza → dejar correr
    ("bull",    False): 4.5,   # alcista pero débil → algo más de margen
    ("neutral", True):  3.5,   # lateral con impulso → recoger pronto
    ("neutral", False): 3.5,
    ("bear",    True):  4.5,   # bajista + fuerza → shorts corren más
    ("bear",    False): 4.0,
}

ADX_STRONG_THRESHOLD = 25.0


def dynamic_tp(signal) -> float:
    regime = signal.regime
    try:
        adx = float(signal.technical.get("details", {}).get("adx", 0) or 0)
    except (TypeError, ValueError):
        adx = 0.0
    strong = adx >= ADX_STRONG_THRESHOLD
    return TP_DYNAMIC.get((regime, strong), 4.0)


# ── Kelly sizing ──────────────────────────────────────────────────────────────
# Escala el risk_pct según la confianza del modelo ML.
# Rango: 1.0% (señal débil) → 2.5% (señal muy fuerte).
def kelly_risk(prob: float) -> float:
    if prob is None:
        return 0.02   # sin ML: riesgo base
    if prob < 0.58:
        return 0.015  # señal apenas supera threshold → posición pequeña
    if prob < 0.65:
        return 0.020  # señal media → posición normal
    if prob < 0.72:
        return 0.025  # señal fuerte → posición algo mayor
    return 0.030      # señal muy fuerte → máximo permitido


def run_bt(df, strategy, use_dynamic_tp=False, use_kelly=False,
           pair="BTC/USDT:USDT"):
    fg_path = ROOT / "data" / "fear_greed_historical.json"
    fg_data = load_fear_greed_sentiment(str(fg_path)) if fg_path.exists() else {}

    state = load_state("__nonexistent__")
    state["peak_balance"] = state["balance_usdt"]
    peak_eq = 1000.0; max_dd_eq = 0.0
    n = len(df)

    for i in range(100, n):
        row      = df.iloc[i]
        ts       = pd.Timestamp(row["timestamp"])
        date_str = str(ts.date())
        reset_daily_counter(state, date_str)
        state["current_candle_index"] = i

        current_price = float(row["close"])
        df_slice      = df.iloc[max(0, i - 299):i + 1]
        day_fg = fg_data.get(date_str, {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"})
        live_extras = {
            "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
            "fear_greed": day_fg,
            "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
            "orderbook":  {"bull_mod": 0, "bear_mod": 0},
            "macro_corr": {"bull_mod": 0, "bear_mod": 0},
        }

        signal = strategy.get_signal(df_slice, live_extras, row=row)

        # Construir risk_profile con ajustes opcionales
        rp = apply_regime(BASE_RISK, signal.regime)

        if use_dynamic_tp:
            rp["take_profit_atr_mult"] = dynamic_tp(signal)

        if use_kelly and hasattr(strategy, "_last_prob"):
            rp["risk_pct"] = kelly_risk(strategy._last_prob)

        atr = signal.technical.get("details", {}).get("atr", 0)
        check_sl_tp(state, pair, current_price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, current_price, atr, signal, rp,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

        bal = state["balance_usdt"]
        pos = state.get("position")
        equity = bal + pos["amount"] * pos["entry_price"] if pos else bal
        if equity > peak_eq: peak_eq = equity
        dd = (peak_eq - equity) / peak_eq * 100
        if dd > max_dd_eq: max_dd_eq = dd

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END_OF_BACKTEST")

    total = state["stats"]["wins"] + state["stats"]["losses"]
    wr    = state["stats"]["wins"] / total * 100 if total else 0
    pnl   = state["balance_usdt"] - 1000
    return {
        "pnl": round(pnl, 2), "wr": round(wr, 1),
        "trades": total, "dd": round(max_dd_eq, 1),
    }


if __name__ == "__main__":
    print(f"\n[V7 Enhanced] OOS {TEST_START} → 2026-08-24")
    print(f"  Cargando datos...")

    df_raw = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df_oos = df_raw[df_raw["timestamp"] >= TEST_START].reset_index(drop=True)
    df_oos = precompute_indicators(df_oos)
    print(f"  {len(df_oos):,} velas\n")

    oos_pkl  = MODEL_DIR / "v7_classifier_oos.pkl"
    oos_meta = json.load(open(MODEL_DIR / "v7_classifier_oos_meta.json"))

    def make_v7():
        s = StrategyML(model_path=str(oos_pkl), threshold=0.55)
        s.feature_cols = oos_meta["feature_cols"]
        return s

    results = []

    def bench(label, strategy, dtp=False, kelly=False):
        r = run_bt(df_oos, strategy, use_dynamic_tp=dtp, use_kelly=kelly)
        results.append({"label": label, **r})
        print(f"  {label:<45}  PnL={r['pnl']:>+8.2f}  WR={r['wr']:>5.1f}%  "
              f"Trades={r['trades']:4}  DD={r['dd']:.1f}%")

    print("── Baseline ──")
    bench("V6  sin ML",                  Strategy15m())
    bench("V7  ML@0.55  (actual)",       make_v7())

    print("\n── TP dinámico ──")
    bench("V7  ML + TP dinámico",        make_v7(), dtp=True)

    print("\n── Kelly sizing ──")
    bench("V7  ML + Kelly",              make_v7(), kelly=True)

    print("\n── Combinado ──")
    bench("V7  ML + TP dinámico + Kelly",make_v7(), dtp=True, kelly=True)

    # Resumen
    base_v6 = next(r for r in results if "V6" in r["label"])["pnl"]
    base_v7 = next(r for r in results if "actual" in r["label"])["pnl"]

    print(f"\n{'='*72}")
    print(f"  RANKING OOS | V6={base_v6:+.0f}  V7_actual={base_v7:+.0f}")
    print(f"{'='*72}")
    print(f"  {'Config':<45} {'PnL':>9}  {'WR':>6}  {'Trades':>7}  {'DD':>6}  {'vs V7':>7}")
    print(f"  {'─'*70}")
    for r in sorted(results, key=lambda x: -x["pnl"]):
        dv7 = r["pnl"] - base_v7
        print(f"  {r['label']:<45} {r['pnl']:>+9.2f}  {r['wr']:>5.1f}%  {r['trades']:>7}  "
              f"{r['dd']:>5.1f}%  {dv7:>+7.0f}")
    print(f"{'='*72}")
