"""
Backtest: weekend_min_score_bonus +10 (actual) vs -5 (propuesto)

Compara cómo cambia el rendimiento al bajar el umbral de scores en fin de semana.
Run: python -m v12.backtest_weekend
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
TEST_START = "2025-01-01"

_TP_MAP = {
    ("bull",    True):  5.0, ("bull",    False): 4.5,
    ("neutral", True):  3.5, ("neutral", False): 3.5,
    ("bear",    True):  4.5, ("bear",    False): 4.0,
}

def _dynamic_tp(signal):
    try:
        adx = float(str(signal.technical.get("details", {}).get("atr", 0) or 0).split()[0])
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

def make_strategy():
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    s.feature_cols = meta["feature_cols"]
    return s

def _make_risk(weekend_bonus, weekend_mode="range"):
    return {
        "risk_pct": 0.05, "max_cost_pct": 0.87,
        "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
        "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
        "max_drawdown_pct": 0.25, "max_daily_loss_pct": 0.03,
        "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
        "weekend_mode": weekend_mode, "weekend_min_score_bonus": weekend_bonus, "min_vol_ratio": 0.0,
    }

def _patch_bb(bb_threshold):
    """Patch apply_weekend_filter en bot_indicators (importación local dentro de make_decision)."""
    import v6.core.bot_indicators as _ind
    from v6.core.bot_indicators import is_weekend
    _orig = _ind.apply_weekend_filter

    def _patched(technical, side, bull_score, bear_score, risk_profile, timestamp):
        weekend_mode = risk_profile.get("weekend_mode", "range")
        bonus        = risk_profile.get("weekend_min_score_bonus", 10)
        base_min     = risk_profile["min_score"]
        if not is_weekend(timestamp):
            return True, base_min
        if weekend_mode is None:
            return False, base_min
        effective_min = base_min + bonus
        if weekend_mode == "trend":
            return True, effective_min
        details = technical.get("details", {})
        price   = details.get("price", 0)
        bbl     = technical.get("bbl")
        bbu     = technical.get("bbu")
        if not bbl or not bbu or (bbu - bbl) == 0:
            return False, effective_min
        bb_pos = (price - bbl) / (bbu - bbl)
        if side == "LONG":
            return bb_pos <= bb_threshold, effective_min
        else:
            return bb_pos >= (1 - bb_threshold), effective_min

    _ind.apply_weekend_filter = _patched
    return _orig

def _restore_bb(orig):
    import v6.core.bot_indicators as _ind
    _ind.apply_weekend_filter = orig

def run(df, pair, risk_params, label):
    state = load_state("__nonexistent__")
    strat = make_strategy()
    peak_eq = 1000.0
    max_dd = 0.0
    weekend_trades = 0

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

        had_pos = state.get("position") is not None
        check_sl_tp(state, pair, price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, price, atr, signal, rp,
                      verbose=False, min_hold_candles=3,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

        opened = not had_pos and state.get("position") is not None
        if opened and ts.weekday() >= 5:  # sábado=5, domingo=6
            weekend_trades += 1

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

    return {
        "label":           label,
        "pnl":             round(state["balance_usdt"] - 1000, 2),
        "wr":              round(wr, 1),
        "trades":          total,
        "dd":              round(max_dd, 1),
        "pf":              round(pf, 2),
        "weekend_trades":  weekend_trades,
    }


def load_df(path):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[df["timestamp"] >= TEST_START].reset_index(drop=True)
    return precompute_indicators(df)


def print_table(results, pair):
    print(f"\n{'='*62}")
    print(f"  {pair} — desde {TEST_START}")
    print(f"{'='*62}")
    print(f"  {'Config':<28} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6} {'PF':>6} {'Wknd':>6}")
    print(f"  {'-'*28} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
    for r in results:
        print(f"  {r['label']:<28} {r['pnl']:>8.0f} {r['trades']:>7} {r['wr']:>5.1f}% {r['dd']:>5.1f}% {r['pf']:>6.2f} {r['weekend_trades']:>6}")
    print()


def print_total(all_results_by_config):
    """all_results_by_config: dict label → list of result dicts (one per pair)"""
    print(f"\n{'='*62}")
    print(f"  TOTAL (BTC + ETH + SOL) — desde {TEST_START}")
    print(f"{'='*62}")
    print(f"  {'Config':<28} {'PnL':>8} {'Trades':>7} {'WR':>6} {'MaxDD':>6} {'Wknd':>6}")
    print(f"  {'-'*28} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6}")
    for label, results in all_results_by_config.items():
        total_pnl     = sum(r["pnl"] for r in results)
        total_trades  = sum(r["trades"] for r in results)
        total_wknd    = sum(r["weekend_trades"] for r in results)
        total_wins    = sum(round(r["trades"] * r["wr"] / 100) for r in results)
        avg_wr        = total_wins / total_trades * 100 if total_trades else 0
        max_dd        = max(r["dd"] for r in results)
        print(f"  {label:<28} {total_pnl:>8.0f} {total_trades:>7} {avg_wr:>5.1f}% {max_dd:>5.1f}% {total_wknd:>6}")
    print()


def main():
    datasets = [
        (ROOT / "data" / "btc_15m_full.csv",  "BTC"),
        (ROOT / "data" / "eth_2023_2026.csv",  "ETH"),
        (ROOT / "data" / "sol_15m_full.csv",   "SOL"),
    ]
    # (bonus, weekend_mode, label)
    # weekend_mode="range" → BB extremos (actual)
    # weekend_mode="trend" → sin filtro BB, solo score bonus
    # weekend_mode=None    → sin operar en fines de semana
    configs = [
        (+10, "range",  "Actual       range+BB, min=68 wknd"),
        ( +5, "trend",  "Intermedio   trend,    min=63 wknd"),
        (  0, "trend",  "Permisivo    trend,    min=58 wknd"),
        (None, None,    "Sin wknd     (no opera fines de semana)"),
    ]

    all_results_by_config = {label: [] for _, _, label in configs}

    for path, pair in datasets:
        if not path.exists():
            print(f"[SKIP] {pair}: {path} no encontrado")
            continue
        print(f"\n[{pair}] Cargando datos...")
        df = load_df(path)
        print(f"  {len(df)} velas desde {TEST_START}")

        results = []
        for bonus, wmode, label in configs:
            print(f"  Corriendo {label}...")
            r = run(df, pair, _make_risk(bonus or 0, weekend_mode=wmode), label)
            results.append(r)
            all_results_by_config[label].append(r)

        print_table(results, pair)

    print_total(all_results_by_config)


if __name__ == "__main__":
    main()
