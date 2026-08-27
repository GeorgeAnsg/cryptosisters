"""
V7 — Backtest en periodo bull market (2024).

BTC pasó de ~45k a ~108k en 2024 (post-halving + ETF approval).
Compara V4 (params reales), V6, y V7 ML en el mismo periodo alcista.

NOTA: Para V7, 2024 es IN-SAMPLE (el modelo fue entrenado en 2023-2024).
Los resultados de V7 aquí están inflados — son orientativos, no válidos para inferir edge.
El único resultado OOS válido es 2025-2026 (ya medido: +628 USDT).

Run: python v7/backtest_bull.py
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

LOCAL_CSV = ROOT / "data" / "btc_15m_full.csv"
MODEL_DIR = ROOT / "v7" / "models"

# V6 params (configuración actual)
V6_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

# V4 params: SL=1.5×ATR (el diferencial clave), TP=4.0×ATR → R:R=2.67
# min_score más bajo para aproximar "sin filtros HTF agresivos"
V4_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 1.5, "take_profit_atr_mult": 4.0,
    "min_score": 52, "entry_advantage": 10, "max_daily_trades": 6,
    "max_drawdown_pct": 0.15, "max_daily_loss_pct": 0.05,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}


def run_bt(df, strategy, risk_profile, pair="BTC/USDT:USDT"):
    fg_path = ROOT / "data" / "fear_greed_historical.json"
    fg_data = load_fear_greed_sentiment(str(fg_path)) if fg_path.exists() else {}

    state = load_state("__nonexistent__")
    state["peak_balance"] = state["balance_usdt"]
    peak   = state["balance_usdt"]
    max_dd = 0.0
    n      = len(df)

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
        rp_eff = apply_regime(risk_profile, signal.regime)
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

    ml_info = ""
    if hasattr(strategy, "_ml_stats") and strategy._ml_stats["checked"]:
        s = strategy._ml_stats
        ml_info = f"  [ML bloqueó {s['blocked']}/{s['checked']} = {s['blocked']/s['checked']*100:.0f}%]"

    return {
        "pnl": round(pnl, 2), "wr": round(wr, 1),
        "trades": total, "max_dd": round(max_dd, 1),
        "ml_info": ml_info,
    }


def bench(label, df, strategy, risk, note=""):
    r = run_bt(df, strategy, risk)
    flag = " ⚠ IN-SAMPLE" if note == "IS" else (" ✓ OOS" if note == "OOS" else "")
    print(f"  {label:<28}  PnL={r['pnl']:>+9.2f}  WR={r['wr']:>5.1f}%  "
          f"Trades={r['trades']:4}  DD={r['max_dd']:>4.1f}%{r['ml_info']}{flag}")
    return r


if __name__ == "__main__":
    print(f"\n[V7] Cargando datos...")
    df_raw = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df_raw = df_raw.sort_values("timestamp").reset_index(drop=True)
    print(f"  Precomputando indicadores (paciencia)...")
    df_all = precompute_indicators(df_raw)

    # Cargar V7
    oos_pkl  = MODEL_DIR / "v7_classifier_oos.pkl"
    oos_meta = json.load(open(MODEL_DIR / "v7_classifier_oos_meta.json"))
    def make_v7():
        s = StrategyML(model_path=str(oos_pkl), threshold=0.55)
        s.feature_cols = oos_meta["feature_cols"]
        return s

    periods = {
        "2024 — Bull market puro\n  (BTC 45k→108k, post-halving + ETF)": {
            "start": "2024-01-01", "end": "2025-01-01", "v7_note": "IS",
        },
        "2023 — Recovery bull\n  (BTC 16k→45k, salida del bear)": {
            "start": "2023-01-01", "end": "2024-01-01", "v7_note": "IS",
        },
        "2025-2026 — Post-ATH corrección\n  (BTC 108k→75k→recuperación) ← OOS real": {
            "start": "2025-01-01", "end": None, "v7_note": "OOS",
        },
    }

    for period_name, cfg in periods.items():
        start = cfg["start"]
        end   = cfg["end"]
        v7n   = cfg["v7_note"]

        mask = df_all["timestamp"] >= start
        if end:
            mask &= df_all["timestamp"] < end
        df_p = df_all[mask].reset_index(drop=True)

        start_price = df_p["close"].iloc[100]
        end_price   = df_p["close"].iloc[-1]
        btc_ret     = (end_price / start_price - 1) * 100

        print(f"\n{'='*72}")
        print(f"  {period_name}")
        print(f"  BTC: {start_price:,.0f}$ → {end_price:,.0f}$  ({btc_ret:+.0f}%)")
        print(f"  {len(df_p):,} velas")
        print(f"{'='*72}")

        bench("V4-like (SL=1.5×, TP=4.0×)", df_p, Strategy15m(), V4_RISK)
        bench("V6      (SL=2.5×, TP=4.0×)", df_p, Strategy15m(), V6_RISK)
        bench("V7 ML@0.55  (SL=2.5×)     ", df_p, make_v7(),      V6_RISK, note=v7n)
        bench("V7 ML@0.55  (SL=1.5×) ★  ", df_p, make_v7(),      V4_RISK, note=v7n)

    print(f"""
{'='*72}
  NOTAS IMPORTANTES
{'='*72}
  - V4-like usa Strategy15m con params de V4 (SL=1.5, min_score=52).
    No es idéntico al V4 real (código diferente), pero aproxima su R:R.
  - V7 en 2023 y 2024 está marcado ⚠ IN-SAMPLE: el modelo fue entrenado
    con esos datos. Los resultados están inflados — no son válidos.
  - V7 en 2025-2026 está marcado ✓ OOS: único resultado estadísticamente
    válido para inferir edge real.
{'='*72}
""")
