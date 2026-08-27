"""
V7 — Backtest completo 2023-2026.

Compara V6 vs V7 ML desde el mismo punto de partida.
Nota: para V7, el periodo 2023-2024 es in-sample (el modelo vio esos datos
al entrenar). Solo 2025-2026 es OOS real. Se reportan ambos por separado.

Run: python v7/backtest_full.py
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

BASE_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}


def run_bt(df, strategy, pair="BTC/USDT:USDT"):
    fg_path = ROOT / "data" / "fear_greed_historical.json"
    fg_data = load_fear_greed_sentiment(str(fg_path)) if fg_path.exists() else {}

    state = load_state("__nonexistent__")
    state["peak_balance"] = state["balance_usdt"]
    peak = state["balance_usdt"]
    max_dd = 0.0
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
        rp_eff = apply_regime(BASE_RISK, signal.regime)
        atr    = signal.technical.get("details", {}).get("atr", 0)
        check_sl_tp(state, pair, current_price, rp_eff, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, current_price, atr, signal, rp_eff,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

        bal = state["balance_usdt"]
        if bal > peak:
            peak = bal
        dd = (peak - bal) / peak * 100
        if dd > max_dd:
            max_dd = dd

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END_OF_BACKTEST")

    total = state["stats"]["wins"] + state["stats"]["losses"]
    wr    = state["stats"]["wins"] / total * 100 if total else 0
    pnl   = state["balance_usdt"] - 1000
    return {
        "pnl":    round(pnl, 2),
        "wr":     round(wr, 1),
        "trades": total,
        "max_dd": round(max_dd, 1),
        "wins":   state["stats"]["wins"],
        "losses": state["stats"]["losses"],
    }


if __name__ == "__main__":
    print(f"\n[V7] Backtest completo — cargando datos...")
    df_raw = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df_raw = df_raw.sort_values("timestamp").reset_index(drop=True)

    START_FULL = df_raw["timestamp"].iloc[0].strftime("%Y-%m-%d")
    END        = df_raw["timestamp"].iloc[-1].strftime("%Y-%m-%d")
    OOS_START  = "2025-01-01"

    print(f"  Datos: {START_FULL} → {END} ({len(df_raw):,} velas)")
    print(f"  Precomputando indicadores...")
    df_full = precompute_indicators(df_raw)

    df_oos = df_full[df_full["timestamp"] >= OOS_START].reset_index(drop=True)

    # Cargar modelos
    oos_pkl  = MODEL_DIR / "v7_classifier_oos.pkl"
    oos_meta = json.load(open(MODEL_DIR / "v7_classifier_oos_meta.json"))

    def make_v7():
        s = StrategyML(model_path=str(oos_pkl), threshold=0.55)
        s.feature_cols = oos_meta["feature_cols"]
        return s

    v6 = Strategy15m()

    results = {}

    print(f"\n── Periodo completo {START_FULL} → {END} ──")

    r = run_bt(df_full, v6)
    results["V6 completo"] = r
    print(f"  V6:  PnL={r['pnl']:>+9.2f}  Trades={r['trades']:4}  WR={r['wr']:.1f}%  MaxDD={r['max_dd']:.1f}%")

    v7 = make_v7()
    r = run_bt(df_full, v7)
    results["V7 completo"] = r
    s = v7._ml_stats
    print(f"  V7:  PnL={r['pnl']:>+9.2f}  Trades={r['trades']:4}  WR={r['wr']:.1f}%  MaxDD={r['max_dd']:.1f}%"
          f"  [ML bloqueó {s['blocked']}/{s['checked']} = {s['blocked']/s['checked']*100:.0f}%]")

    print(f"\n── OOS únicamente {OOS_START} → {END} ──")

    r = run_bt(df_oos, Strategy15m())
    results["V6 OOS"] = r
    print(f"  V6:  PnL={r['pnl']:>+9.2f}  Trades={r['trades']:4}  WR={r['wr']:.1f}%  MaxDD={r['max_dd']:.1f}%")

    v7b = make_v7()
    r = run_bt(df_oos, v7b)
    results["V7 OOS"] = r
    s = v7b._ml_stats
    print(f"  V7:  PnL={r['pnl']:>+9.2f}  Trades={r['trades']:4}  WR={r['wr']:.1f}%  MaxDD={r['max_dd']:.1f}%"
          f"  [ML bloqueó {s['blocked']}/{s['checked']} = {s['blocked']/s['checked']*100:.0f}%]")

    # Resumen final
    v6c  = results["V6 completo"]
    v7c  = results["V7 completo"]
    v6o  = results["V6 OOS"]
    v7o  = results["V7 OOS"]

    print(f"""
{'='*65}
  RESUMEN FINAL
{'='*65}
  Referencia externa (datos 2021-2026, capital 1000 USDT):
    V4 producción:   +2718 USDT  WR=40.9%  2506 trades  DD=9.2%

  Periodo completo {START_FULL} → {END} (capital 1000 USDT):
    V6:  {v6c['pnl']:>+8.2f} USDT  WR={v6c['wr']:.1f}%  {v6c['trades']} trades  DD={v6c['max_dd']:.1f}%
    V7:  {v7c['pnl']:>+8.2f} USDT  WR={v7c['wr']:.1f}%  {v7c['trades']} trades  DD={v7c['max_dd']:.1f}%
    Mejora vs V6: {v7c['pnl']-v6c['pnl']:>+.0f} USDT

  OOS real {OOS_START} → {END} (capital 1000 USDT):
    V6:  {v6o['pnl']:>+8.2f} USDT  WR={v6o['wr']:.1f}%  {v6o['trades']} trades  DD={v6o['max_dd']:.1f}%
    V7:  {v7o['pnl']:>+8.2f} USDT  WR={v7o['wr']:.1f}%  {v7o['trades']} trades  DD={v7o['max_dd']:.1f}%
    Mejora vs V6: {v7o['pnl']-v6o['pnl']:>+.0f} USDT  ({v7o['pnl']/v6o['pnl']:.1f}×)
{'='*65}
  NOTA: V7 periodo completo incluye 2023-2024 (IN-SAMPLE para el ML).
  Solo el resultado OOS es estadísticamente válido para inferir edge real.
{'='*65}
""")
