"""
V10 — Backtest OOS con parámetros de producción:
  - trailing_step_mult=1.0 (SL solo se mueve si mejora ≥1×ATR)
  - max_tp_extensions=1
  - Filtro de horas: solo abre posiciones entre 08:00-23:00 Madrid (UTC+2)

Compara contra V8 baseline para cuantificar el impacto de los cambios.

Run: python v10/backtest.py
"""

import sys, json, pickle
from pathlib import Path
from datetime import timezone, timedelta
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

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

MADRID = timezone(timedelta(hours=2))  # CEST (verano). En invierno sería +1.
HOUR_START, HOUR_END = 8, 23

V8_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "trailing_step_mult": 0.0, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

V10_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

TP_DYNAMIC = {
    ("bull",    True):  5.0, ("bull",    False): 4.5,
    ("neutral", True):  3.5, ("neutral", False): 3.5,
    ("bear",    True):  4.5, ("bear",    False): 4.0,
}

def dynamic_tp(signal):
    try:
        raw = signal.technical.get("details", {}).get("adx", 0) or 0
        adx = float(str(raw).split()[0]) if isinstance(raw, str) else float(raw)
    except (ValueError, TypeError):
        adx = 0.0
    return TP_DYNAMIC.get((signal.regime, adx >= 25), 4.0)

def make_strategy():
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    s.feature_cols = meta["feature_cols"]
    return s

def is_trading_hours(ts: pd.Timestamp) -> bool:
    h = ts.tz_localize("UTC").astimezone(MADRID).hour
    return HOUR_START <= h < HOUR_END

def run_single(df, strategy, pair, risk, apply_hours_filter=False):
    state   = load_state("__nonexistent__")
    peak_eq = 1000.0
    max_dd  = 0.0
    trail_moves = 0
    tp_exts     = 0

    # Patch temporal para contar notificaciones de trailing
    import v6.core.bot_core as _bc
    _orig_tg = _bc._tg_update
    def _count_tg(p, side, msg, sl, tp, **kw):
        nonlocal trail_moves, tp_exts
        if "Trailing" in msg: trail_moves += 1
        if "TP extendido" in msg: tp_exts += 1
    _bc._tg_update = _count_tg

    try:
        for i in range(100, len(df)):
            row = df.iloc[i]
            ts  = pd.Timestamp(row["timestamp"])
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
            rp = apply_regime(risk, signal.regime)
            rp["take_profit_atr_mult"] = dynamic_tp(signal)
            atr = signal.technical.get("details", {}).get("atr", 0)

            check_sl_tp(state, pair, current_price, rp, atr=atr,
                        scores={"bullish_total": signal.bull_score,
                                "bearish_total": signal.bear_score})

            # Filtro de horas: bloquear apertura fuera del horario
            if apply_hours_filter and not is_trading_hours(ts):
                signal.bull_score = 0
                signal.bear_score = 0

            make_decision(state, pair, current_price, atr, signal, rp,
                          verbose=False, min_hold_candles=0,
                          current_candle_index=i, winrate_table={}, timestamp=ts)

            pos    = state.get("position")
            equity = state["balance_usdt"] + pos["amount"] * pos["entry_price"] if pos else state["balance_usdt"]
            if equity > peak_eq: peak_eq = equity
            dd = (peak_eq - equity) / peak_eq * 100
            if dd > max_dd: max_dd = dd
    finally:
        _bc._tg_update = _orig_tg

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")

    st    = state["stats"]
    total = st["wins"] + st["losses"]
    wr    = st["wins"] / total * 100 if total else 0

    trades = [t for t in state["trades"] if t["action"].startswith("CLOSE_")]
    pnls   = [t["pnl"] for t in trades if "pnl" in t]
    wins_pnl  = [p for p in pnls if p > 0]
    loses_pnl = [p for p in pnls if p <= 0]
    avg_win  = sum(wins_pnl)  / len(wins_pnl)  if wins_pnl  else 0
    avg_loss = sum(loses_pnl) / len(loses_pnl) if loses_pnl else 0
    profit_factor = abs(sum(wins_pnl) / sum(loses_pnl)) if sum(loses_pnl) != 0 else float("inf")

    long_wr  = st["long_wins"]  / st["total_longs"]  * 100 if st["total_longs"]  else 0
    short_wr = st["short_wins"] / st["total_shorts"] * 100 if st["total_shorts"] else 0

    return {
        "pnl":          round(state["balance_usdt"] - 1000, 2),
        "wr":           round(wr, 1),
        "trades":       total,
        "wins":         st["wins"],
        "losses":       st["losses"],
        "dd":           round(max_dd, 1),
        "best_trade":   round(st["best_trade"], 2),
        "worst_trade":  round(st["worst_trade"], 2),
        "avg_win":      round(avg_win, 2),
        "avg_loss":     round(avg_loss, 2),
        "profit_factor":round(profit_factor, 2),
        "long_trades":  st["total_longs"],
        "long_wr":      round(long_wr, 1),
        "short_trades": st["total_shorts"],
        "short_wr":     round(short_wr, 1),
        "trail_moves":  trail_moves,
        "tp_exts":      tp_exts,
        "notifs_per_trade": round((trail_moves + tp_exts) / total, 1) if total else 0,
    }


if __name__ == "__main__":
    print(f"\n{'='*70}")
    print(f"  V10 BACKTEST — OOS {TEST_START} → hoy")
    print(f"  Comparativa V8 vs V10 (trailing suavizado + filtro horas)")
    print(f"{'='*70}\n")

    print("  Cargando datos...")
    df_btc = pd.read_csv(LOCAL_BTC, parse_dates=["timestamp"])
    df_btc = df_btc[df_btc["timestamp"] >= TEST_START].reset_index(drop=True)
    df_btc = precompute_indicators(df_btc)

    df_eth = pd.read_csv(LOCAL_ETH, parse_dates=["timestamp"])
    df_eth = df_eth[df_eth["timestamp"] >= TEST_START].reset_index(drop=True)
    df_eth = precompute_indicators(df_eth)

    print(f"  BTC: {len(df_btc):,} velas | ETH: {len(df_eth):,} velas\n")

    strat = make_strategy()

    # Config intermedia: solo horario (trailing igual que V8)
    HOURS_ONLY_RISK = {**V8_RISK, "trailing_step_mult": 0.0, "max_tp_extensions": 2}
    # Config intermedia: solo trailing suavizado (sin filtro horario)
    TRAIL_ONLY_RISK = {**V10_RISK}

    configs = [
        ("V8  BTC  baseline",        df_btc, "BTC/USDT:USDT", V8_RISK,        False),
        ("    BTC  solo horario",     df_btc, "BTC/USDT:USDT", HOURS_ONLY_RISK, True),
        ("    BTC  solo trailing",    df_btc, "BTC/USDT:USDT", TRAIL_ONLY_RISK, False),
        ("V10 BTC  trail+horas",      df_btc, "BTC/USDT:USDT", V10_RISK,        True),
        ("V8  ETH  baseline",        df_eth, "ETH/USDT:USDT", V8_RISK,        False),
        ("    ETH  solo horario",     df_eth, "ETH/USDT:USDT", HOURS_ONLY_RISK, True),
        ("    ETH  solo trailing",    df_eth, "ETH/USDT:USDT", TRAIL_ONLY_RISK, False),
        ("V10 ETH  trail+horas",      df_eth, "ETH/USDT:USDT", V10_RISK,        True),
    ]

    results = {}
    for label, df, pair, risk, hours in configs:
        print(f"  Calculando {label}...")
        results[label] = run_single(df.copy(), make_strategy(), pair, risk, hours)

    def show(label, r):
        print(f"\n  ┌─ {label}")
        print(f"  │  PnL total      {r['pnl']:>+8.0f} USDT")
        print(f"  │  Win rate       {r['wr']:>7.1f}%  ({r['wins']}W / {r['losses']}L)")
        print(f"  │  Long WR        {r['long_wr']:>7.1f}%  ({r['long_trades']} trades)")
        print(f"  │  Short WR       {r['short_wr']:>7.1f}%  ({r['short_trades']} trades)")
        print(f"  │  Trades totales {r['trades']:>7}")
        print(f"  │  Max drawdown   {r['dd']:>7.1f}%")
        print(f"  │  Mejor trade    {r['best_trade']:>+8.2f} USDT")
        print(f"  │  Peor trade     {r['worst_trade']:>+8.2f} USDT")
        print(f"  │  Avg ganancia   {r['avg_win']:>+8.2f} USDT")
        print(f"  │  Avg pérdida    {r['avg_loss']:>+8.2f} USDT")
        print(f"  │  Profit factor  {r['profit_factor']:>8.2f}")
        print(f"  └  Avisos/trade   {r['notifs_per_trade']:>7.1f}  (trail={r['trail_moves']} TP_ext={r['tp_exts']})")

    print(f"\n{'─'*55}")
    for label in results:
        show(label, results[label])

    print(f"\n{'='*65}")
    print(f"  ¿QUÉ AFECTA MÁS A LAS GANANCIAS?")
    print(f"{'─'*65}")
    print(f"  {'Config':<26} {'PnL':>8}  {'WR':>6}  {'Trades':>7}  {'DD':>5}  {'Avisos':>6}")
    print(f"  {'─'*60}")
    for label, r in results.items():
        print(f"  {label:<26} {r['pnl']:>+8.0f}  {r['wr']:>5.1f}%  {r['trades']:>7}  "
              f"{r['dd']:>4.1f}%  {r['notifs_per_trade']:>6.1f}")
    print(f"{'='*65}\n")
