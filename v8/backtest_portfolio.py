"""
V8 — Backtest multi-activo simultáneo (BTC + ETH).

Capital compartido: 1000 USDT. Ambos activos corren en paralelo con el modelo
V7 ML. Pueden tener posiciones abiertas al mismo tiempo. El balance es único
y se comparte entre los dos activos.

Objetivo: ver si más oportunidades de trading mejoran el Sharpe y el PnL total
respecto a correr solo BTC.

Run: python v8/backtest_portfolio.py
"""

import sys, json, pickle, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

from v6.core.bot_core import (
    load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import StrategyML

LOCAL_BTC  = ROOT / "data" / "btc_15m_full.csv"
LOCAL_ETH  = ROOT / "data" / "eth_2023_2026.csv"
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

TP_DYNAMIC = {
    ("bull",    True):  5.0,
    ("bull",    False): 4.5,
    ("neutral", True):  3.5,
    ("neutral", False): 3.5,
    ("bear",    True):  4.5,
    ("bear",    False): 4.0,
}


def dynamic_tp(signal) -> float:
    try:
        adx = float(signal.technical.get("details", {}).get("adx", 0) or 0)
    except (TypeError, ValueError):
        adx = 0.0
    return TP_DYNAMIC.get((signal.regime, adx >= 25), 4.0)


def make_v7():
    oos_pkl = MODEL_DIR / "v7_classifier_oos.pkl"
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        oos_meta = json.load(f)
    s = StrategyML(model_path=str(oos_pkl), threshold=0.55)
    s.feature_cols = oos_meta["feature_cols"]
    return s


# ── Portfolio backtest engine ──────────────────────────────────────────────────

def make_state():
    """Estado limpio para un activo."""
    s = load_state("__x__")
    s["peak_balance"] = s["balance_usdt"]
    return s


def step_asset(state, df, i, strategy, pair, shared_balance, use_dtp=True):
    """
    Ejecuta un paso del backtest para UN activo.
    shared_balance es el balance real (compartido entre activos).
    Devuelve (pnl_delta, cerró_posición).
    """
    row      = df.iloc[i]
    ts       = pd.Timestamp(row["timestamp"])
    date_str = str(ts.date())
    reset_daily_counter(state, date_str)
    state["current_candle_index"] = i
    state["balance_usdt"] = shared_balance  # sincronizar con pool compartido

    current_price = float(row["close"])
    df_slice      = df.iloc[max(0, i - 299):i + 1]
    live_extras = {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
        "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }

    signal = strategy.get_signal(df_slice, live_extras, row=row)
    rp     = apply_regime(BASE_RISK, signal.regime)
    if use_dtp:
        rp["take_profit_atr_mult"] = dynamic_tp(signal)

    atr = signal.technical.get("details", {}).get("atr", 0)

    bal_before = state["balance_usdt"]
    check_sl_tp(state, pair, current_price, rp, atr=atr,
                scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
    make_decision(state, pair, current_price, atr, signal, rp,
                  verbose=False, min_hold_candles=0,
                  current_candle_index=i, winrate_table={}, timestamp=ts)

    delta = state["balance_usdt"] - bal_before
    return delta


def run_portfolio(df_btc, df_eth, strategy_btc, strategy_eth):
    """
    Backtest multi-activo con capital compartido.
    Los dos DataFrames deben tener los mismos timestamps (15m).
    """
    # Alinear por timestamp
    df_btc = df_btc.set_index("timestamp")
    df_eth = df_eth.set_index("timestamp")
    common_ts = df_btc.index.intersection(df_eth.index)
    df_btc = df_btc.loc[common_ts].reset_index()
    df_eth = df_eth.loc[common_ts].reset_index()

    shared_balance = 1000.0
    state_btc = make_state()
    state_eth = make_state()

    peak_eq  = 1000.0
    max_dd   = 0.0
    n        = len(df_btc)

    for i in range(100, n):
        # Procesar BTC
        delta_btc = step_asset(state_btc, df_btc, i, strategy_btc,
                                "BTC/USDT:USDT", shared_balance)
        shared_balance += delta_btc

        # Procesar ETH (con el balance ya actualizado por BTC)
        delta_eth = step_asset(state_eth, df_eth, i, strategy_eth,
                                "ETH/USDT:USDT", shared_balance)
        shared_balance += delta_eth

        # Equity total = balance libre + valor de posiciones abiertas
        pos_btc = state_btc.get("position")
        pos_eth = state_eth.get("position")
        eq = shared_balance
        if pos_btc:
            price_btc = float(df_btc.iloc[i]["close"])
            eq += pos_btc["amount"] * price_btc
        if pos_eth:
            price_eth = float(df_eth.iloc[i]["close"])
            eq += pos_eth["amount"] * price_eth

        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    # Cerrar posiciones al final
    if state_btc.get("position"):
        p = float(df_btc.iloc[-1]["close"])
        close_position(state_btc, "BTC/USDT:USDT", p, "END_OF_BACKTEST")
        shared_balance = state_btc["balance_usdt"]
    if state_eth.get("position"):
        p = float(df_eth.iloc[-1]["close"])
        close_position(state_eth, "ETH/USDT:USDT", p, "END_OF_BACKTEST")
        shared_balance += (state_eth["balance_usdt"] - shared_balance)

    btc_trades = state_btc["stats"]["wins"] + state_btc["stats"]["losses"]
    eth_trades = state_eth["stats"]["wins"] + state_eth["stats"]["losses"]
    total      = btc_trades + eth_trades
    wins       = state_btc["stats"]["wins"] + state_eth["stats"]["wins"]
    wr         = wins / total * 100 if total else 0
    pnl        = shared_balance - 1000.0

    return {
        "pnl":        round(pnl, 2),
        "wr":         round(wr, 1),
        "trades":     total,
        "btc_trades": btc_trades,
        "eth_trades": eth_trades,
        "dd":         round(max_dd, 1),
    }


def run_single(df, strategy, pair):
    """Backtest de un solo activo (referencia)."""
    state   = make_state()
    peak_eq = 1000.0; max_dd = 0.0

    for i in range(100, len(df)):
        row      = df.iloc[i]
        ts       = pd.Timestamp(row["timestamp"])
        reset_daily_counter(state, str(ts.date()))
        state["current_candle_index"] = i
        current_price = float(row["close"])
        df_slice = df.iloc[max(0, i - 299):i + 1]
        live_extras = {
            "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
            "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
            "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
            "orderbook":  {"bull_mod": 0, "bear_mod": 0},
            "macro_corr": {"bull_mod": 0, "bear_mod": 0},
        }
        signal = strategy.get_signal(df_slice, live_extras, row=row)
        rp = apply_regime(BASE_RISK, signal.regime)
        rp["take_profit_atr_mult"] = dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0)
        check_sl_tp(state, pair, current_price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, current_price, atr, signal, rp,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)
        pos    = state.get("position")
        equity = state["balance_usdt"] + pos["amount"] * pos["entry_price"] if pos else state["balance_usdt"]
        if equity > peak_eq: peak_eq = equity
        dd = (peak_eq - equity) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END_OF_BACKTEST")

    total = state["stats"]["wins"] + state["stats"]["losses"]
    wr    = state["stats"]["wins"] / total * 100 if total else 0
    return {
        "pnl": round(state["balance_usdt"] - 1000, 2),
        "wr":  round(wr, 1), "trades": total, "dd": round(max_dd, 1),
    }


if __name__ == "__main__":
    print(f"\n{'='*68}")
    print(f"  V8 — BACKTEST MULTI-ACTIVO | OOS {TEST_START} → 2026-08-24")
    print(f"  Capital compartido: 1000 USDT | Modelo: V7 ML + TP dinámico")
    print(f"{'='*68}\n")

    # Cargar datos
    print("  Cargando datos...")
    df_btc_raw = pd.read_csv(LOCAL_BTC, parse_dates=["timestamp"])
    df_eth_raw = pd.read_csv(LOCAL_ETH, parse_dates=["timestamp"])

    df_btc_oos = df_btc_raw[df_btc_raw["timestamp"] >= TEST_START].reset_index(drop=True)
    df_eth_oos = df_eth_raw[df_eth_raw["timestamp"] >= TEST_START].reset_index(drop=True)

    df_btc_oos = precompute_indicators(df_btc_oos)
    df_eth_oos = precompute_indicators(df_eth_oos)

    print(f"  BTC: {len(df_btc_oos):,} velas | ETH: {len(df_eth_oos):,} velas\n")

    # ── Referencia: cada activo por separado ──────────────────────────────────
    print("── REFERENCIA — activos por separado (V7 ML + TP dinámico) ──")
    r_btc = run_single(df_btc_oos.copy(), make_v7(), "BTC/USDT:USDT")
    print(f"  BTC solo   PnL={r_btc['pnl']:>+8.0f}  WR={r_btc['wr']:>5.1f}%  "
          f"Trades={r_btc['trades']:>4}  DD={r_btc['dd']:.1f}%")

    r_eth = run_single(df_eth_oos.copy(), make_v7(), "ETH/USDT:USDT")
    print(f"  ETH solo   PnL={r_eth['pnl']:>+8.0f}  WR={r_eth['wr']:>5.1f}%  "
          f"Trades={r_eth['trades']:>4}  DD={r_eth['dd']:.1f}%")

    r_naive = {"pnl": r_btc["pnl"] + r_eth["pnl"],
               "trades": r_btc["trades"] + r_eth["trades"]}
    print(f"  Suma naive PnL={r_naive['pnl']:>+8.0f}  (2000 USDT capital)")

    # ── V8: Portfolio real (capital compartido) ───────────────────────────────
    print(f"\n── V8 PORTFOLIO — capital compartido 1000 USDT ──")
    r_v8 = run_portfolio(
        df_btc_oos.copy(), df_eth_oos.copy(),
        make_v7(), make_v7()
    )
    print(f"  V8 Portfolio  PnL={r_v8['pnl']:>+8.0f}  WR={r_v8['wr']:>5.1f}%  "
          f"Trades={r_v8['trades']:>4}  DD={r_v8['dd']:.1f}%")
    print(f"    BTC trades: {r_v8['btc_trades']} | ETH trades: {r_v8['eth_trades']}")

    # ── Resumen comparativo ───────────────────────────────────────────────────
    print(f"\n{'='*68}")
    print(f"  COMPARATIVA FINAL (misma base de 1000 USDT)")
    print(f"{'='*68}")
    print(f"  {'Config':<30} {'PnL':>8} {'WR':>7} {'Trades':>7} {'DD':>7}")
    print(f"  {'─'*58}")
    print(f"  {'V7 BTC solo':<30} {r_btc['pnl']:>+8.0f} {r_btc['wr']:>6.1f}% {r_btc['trades']:>7} {r_btc['dd']:>6.1f}%")
    print(f"  {'V7 ETH solo':<30} {r_eth['pnl']:>+8.0f} {r_eth['wr']:>6.1f}% {r_eth['trades']:>7} {r_eth['dd']:>6.1f}%")
    print(f"  {'V8 BTC+ETH (1000 USDT)':<30} {r_v8['pnl']:>+8.0f} {r_v8['wr']:>6.1f}% {r_v8['trades']:>7} {r_v8['dd']:>6.1f}% ★")
    print(f"\n  Mejora V8 vs V7 BTC: {r_v8['pnl'] - r_btc['pnl']:+.0f} USDT con el mismo capital inicial")
    print(f"{'='*68}\n")
