"""
V10 — Trailing step dinámico: Opción B (ADX) y Opción A (score entrada).
Sin filtro de horas. OOS 2025-01-01 → hoy.

Opción B — ADX al abrir/mantener posición:
  ADX < 20  → step_mult 0.5  (ranging, asegura rápido)
  ADX 20-30 → step_mult 1.0  (normal)
  ADX > 30  → step_mult 1.5  (trending fuerte, deja correr)

Opción A — Score en el momento de entrada:
  score 58-65 → step_mult 0.5
  score 65-75 → step_mult 1.0
  score 75+   → step_mult 1.5

Run: python v10/dynamic_trailing_test.py
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

TP_DYNAMIC_MAP = {
    ("bull",    True):  5.0, ("bull",    False): 4.5,
    ("neutral", True):  3.5, ("neutral", False): 3.5,
    ("bear",    True):  4.5, ("bear",    False): 4.0,
}

def dynamic_tp(signal):
    try:
        raw = signal.technical.get("details", {}).get("adx", 0) or 0
        adx = float(str(raw).split()[0]) if isinstance(raw, str) else float(raw)
    except: adx = 0.0
    return TP_DYNAMIC_MAP.get((signal.regime, adx >= 25), 4.0)

def get_adx(signal):
    try:
        raw = signal.technical.get("details", {}).get("adx", 0) or 0
        return float(str(raw).split()[0]) if isinstance(raw, str) else float(raw)
    except: return 0.0

def step_from_adx(adx, thresholds=(20, 30), mults=(0.5, 1.0, 1.5)):
    if adx < thresholds[0]: return mults[0]
    if adx < thresholds[1]: return mults[1]
    return mults[2]

def step_from_score(score, thresholds=(65, 75), mults=(0.5, 1.0, 1.5)):
    if score < thresholds[0]: return mults[0]
    if score < thresholds[1]: return mults[1]
    return mults[2]

def make_strategy():
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    s.feature_cols = meta["feature_cols"]
    return s

BASE_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

MODE_FIXED   = "fixed_1.0"
MODE_ADX     = "adx"
MODE_SCORE   = "score"

def run_single(df, pair, mode, adx_thresh=(20,30), adx_mults=(0.5,1.0,1.5),
               score_thresh=(65,75), score_mults=(0.5,1.0,1.5)):
    trail_moves = 0
    tp_exts = 0
    step_log = []

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
    entry_score = None  # para modo SCORE

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
            rp = apply_regime(BASE_RISK.copy(), signal.regime)
            rp["take_profit_atr_mult"] = dynamic_tp(signal)
            atr = signal.technical.get("details", {}).get("atr", 0)

            had_pos = state.get("position") is not None

            # Calcular step_mult dinámico
            if mode == MODE_FIXED:
                rp["trailing_step_mult"] = 1.0

            elif mode == MODE_ADX:
                adx = get_adx(signal)
                rp["trailing_step_mult"] = step_from_adx(adx, adx_thresh, adx_mults)
                step_log.append(rp["trailing_step_mult"])

            elif mode == MODE_SCORE:
                if state.get("position") and entry_score is not None:
                    # Mantener el step_mult del momento de entrada durante toda la vida del trade
                    rp["trailing_step_mult"] = entry_score
                else:
                    rp["trailing_step_mult"] = 1.0

            check_sl_tp(state, pair, price, rp, atr=atr,
                        scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})

            make_decision(state, pair, price, atr, signal, rp,
                          verbose=False, min_hold_candles=0,
                          current_candle_index=i, winrate_table={}, timestamp=ts)

            # Registrar score de entrada para modo SCORE
            if mode == MODE_SCORE:
                just_opened = not had_pos and state.get("position") is not None
                just_closed = had_pos and state.get("position") is None
                if just_opened:
                    entry_sc = max(signal.bull_score, signal.bear_score)
                    entry_score = step_from_score(entry_sc, score_thresh, score_mults)
                if just_closed:
                    entry_score = None

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
    trades_list = [t for t in state["trades"] if t["action"].startswith("CLOSE_")]
    pnls = [t["pnl"] for t in trades_list if "pnl" in t]
    wins_p  = [p for p in pnls if p > 0]
    loses_p = [p for p in pnls if p <= 0]
    pf = abs(sum(wins_p) / sum(loses_p)) if sum(loses_p) != 0 else 99.0
    notifs = round((trail_moves + tp_exts) / total, 1) if total else 0

    avg_step = round(sum(step_log)/len(step_log), 2) if step_log else 1.0

    return {
        "pnl": round(state["balance_usdt"] - 1000, 2),
        "wr": round(wr, 1),
        "trades": total,
        "dd": round(max_dd, 1),
        "pf": round(pf, 2),
        "notifs": notifs,
        "avg_step": avg_step,
    }

if __name__ == "__main__":
    print(f"\n{'='*70}")
    print(f"  TRAILING DINÁMICO — OOS {TEST_START} → hoy | Sin filtro horas")
    print(f"{'='*70}\n")

    print("  Cargando datos...")
    df_btc = pd.read_csv(LOCAL_BTC, parse_dates=["timestamp"])
    df_btc = df_btc[df_btc["timestamp"] >= TEST_START].reset_index(drop=True)
    df_btc = precompute_indicators(df_btc)

    df_eth = pd.read_csv(LOCAL_ETH, parse_dates=["timestamp"])
    df_eth = df_eth[df_eth["timestamp"] >= TEST_START].reset_index(drop=True)
    df_eth = precompute_indicators(df_eth)
    print(f"  BTC: {len(df_btc):,} | ETH: {len(df_eth):,} velas\n")

    # Variantes a probar
    configs = [
        # label, mode, kwargs
        ("Baseline step=1.0 (fijo)",       MODE_FIXED,  {}),
        # Opción B — ADX, distintos umbrales/mults
        ("B1  ADX <20→0.5 20-30→1.0 >30→1.5", MODE_ADX, dict(adx_thresh=(20,30), adx_mults=(0.5,1.0,1.5))),
        ("B2  ADX <25→0.5 25-35→1.0 >35→1.5", MODE_ADX, dict(adx_thresh=(25,35), adx_mults=(0.5,1.0,1.5))),
        ("B3  ADX <20→0.75 20-30→1.0 >30→1.5",MODE_ADX, dict(adx_thresh=(20,30), adx_mults=(0.75,1.0,1.5))),
        ("B4  ADX <20→1.0 20-30→1.0 >30→1.5", MODE_ADX, dict(adx_thresh=(20,30), adx_mults=(1.0,1.0,1.5))),
        ("B5  ADX <20→0.5 >20→1.5 (2 zonas)",  MODE_ADX, dict(adx_thresh=(20,20), adx_mults=(0.5,1.5,1.5))),
        # Opción A — Score, distintos umbrales
        ("A1  score <65→0.5 65-75→1.0 >75→1.5",MODE_SCORE, dict(score_thresh=(65,75), score_mults=(0.5,1.0,1.5))),
        ("A2  score <70→0.5 70-80→1.0 >80→1.5",MODE_SCORE, dict(score_thresh=(70,80), score_mults=(0.5,1.0,1.5))),
        ("A3  score <65→0.75 65-75→1.0 >75→1.5",MODE_SCORE, dict(score_thresh=(65,75), score_mults=(0.75,1.0,1.5))),
        ("A4  score <65→1.0 >65→1.5 (2 zonas)",  MODE_SCORE, dict(score_thresh=(65,65), score_mults=(1.0,1.5,1.5))),
    ]

    print(f"  {'Config':<42} {'PnL BTC':>8} {'WR':>6} {'DD':>5}  {'PnL ETH':>8} {'WR':>6} {'DD':>5}  {'Total':>8}  {'Av/tr':>5}")
    print(f"  {'─'*100}")

    results = {}
    for label, mode, kwargs in configs:
        btc = run_single(df_btc.copy(), "BTC/USDT:USDT", mode, **kwargs)
        eth = run_single(df_eth.copy(), "ETH/USDT:USDT", mode, **kwargs)
        combined = btc["pnl"] + eth["pnl"]
        results[label] = (btc, eth, combined)
        notifs = round((btc["notifs"] + eth["notifs"]) / 2, 1)
        print(f"  {label:<42} {btc['pnl']:>+8.0f} {btc['wr']:>5.1f}% {btc['dd']:>4.1f}%  "
              f"{eth['pnl']:>+8.0f} {eth['wr']:>5.1f}% {eth['dd']:>4.1f}%  "
              f"{combined:>+8.0f}  {notifs:>5.1f}")

    print(f"\n  {'─'*100}")
    best_label = max(results, key=lambda l: results[l][2])
    btc, eth, combined = results[best_label]
    print(f"\n  MEJOR: {best_label}")
    print(f"  BTC {btc['pnl']:+.0f} | ETH {eth['pnl']:+.0f} | Total {combined:+.0f} USDT")
    print(f"  BTC WR {btc['wr']}% | ETH WR {eth['wr']}%")
    print(f"  Avisos/trade: BTC {btc['notifs']} | ETH {eth['notifs']}\n")
