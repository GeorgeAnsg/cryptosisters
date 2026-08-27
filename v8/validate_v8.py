"""
V8 — Validación estadística completa del portfolio multi-activo.

Compara V6 / V7 BTC / V8 BTC+ETH con:
  1. Resultados OOS directos
  2. Monte Carlo (2000 paths)
  3. Sharpe + DSR

Run: python v8/validate_v8.py
"""

import sys, json, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

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
N_SIM      = 2000

BASE_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

TP_DYNAMIC = {
    ("bull", True): 5.0, ("bull", False): 4.5,
    ("neutral", True): 3.5, ("neutral", False): 3.5,
    ("bear", True): 4.5, ("bear", False): 4.0,
}


def dynamic_tp(signal):
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


# ── Backtests que devuelven trade_pnls ────────────────────────────────────────

def run_single(df, strategy, pair, use_dtp=True):
    state   = load_state("__x__")
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
        if use_dtp:
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
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")

    total  = state["stats"]["wins"] + state["stats"]["losses"]
    wr     = state["stats"]["wins"] / total * 100 if total else 0
    pnl    = state["balance_usdt"] - 1000
    trades = [t["pnl"] for t in state["trades"] if t["action"].startswith("CLOSE_")]
    return {
        "pnl": round(pnl, 2), "wr": round(wr, 1),
        "trades": total, "dd": round(max_dd, 1), "trade_pnls": trades,
    }


def run_portfolio(df_btc, df_eth, strategy_btc, strategy_eth):
    """Portfolio con capital compartido. Devuelve también trade_pnls combinados."""
    df_btc = df_btc.set_index("timestamp")
    df_eth = df_eth.set_index("timestamp")
    common = df_btc.index.intersection(df_eth.index)
    df_btc = df_btc.loc[common].reset_index()
    df_eth = df_eth.loc[common].reset_index()

    shared = 1000.0
    state_btc = load_state("__x__")
    state_eth = load_state("__x__")
    peak_eq = 1000.0; max_dd = 0.0
    n = len(df_btc)

    for i in range(100, n):
        for df_a, state_a, pair_a, strat_a in [
            (df_btc, state_btc, "BTC/USDT:USDT", strategy_btc),
            (df_eth, state_eth, "ETH/USDT:USDT", strategy_eth),
        ]:
            row = df_a.iloc[i]
            ts  = pd.Timestamp(row["timestamp"])
            reset_daily_counter(state_a, str(ts.date()))
            state_a["current_candle_index"] = i
            state_a["balance_usdt"] = shared
            current_price = float(row["close"])
            df_slice = df_a.iloc[max(0, i - 299):i + 1]
            live_extras = {
                "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
                "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
                "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
                "orderbook":  {"bull_mod": 0, "bear_mod": 0},
                "macro_corr": {"bull_mod": 0, "bear_mod": 0},
            }
            bal_before = shared
            signal = strat_a.get_signal(df_slice, live_extras, row=row)
            rp = apply_regime(BASE_RISK, signal.regime)
            rp["take_profit_atr_mult"] = dynamic_tp(signal)
            atr = signal.technical.get("details", {}).get("atr", 0)
            check_sl_tp(state_a, pair_a, current_price, rp, atr=atr,
                        scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
            make_decision(state_a, pair_a, current_price, atr, signal, rp,
                          verbose=False, min_hold_candles=0,
                          current_candle_index=i, winrate_table={}, timestamp=ts)
            shared += state_a["balance_usdt"] - bal_before

        # Equity total
        pos_b = state_btc.get("position")
        pos_e = state_eth.get("position")
        eq = shared
        if pos_b: eq += pos_b["amount"] * float(df_btc.iloc[i]["close"])
        if pos_e: eq += pos_e["amount"] * float(df_eth.iloc[i]["close"])
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    if state_btc.get("position"):
        close_position(state_btc, "BTC/USDT:USDT", float(df_btc.iloc[-1]["close"]), "END")
        shared += state_btc["balance_usdt"] - shared
    if state_eth.get("position"):
        state_eth["balance_usdt"] = shared
        close_position(state_eth, "ETH/USDT:USDT", float(df_eth.iloc[-1]["close"]), "END")
        shared = state_eth["balance_usdt"]

    all_trades = (
        [t["pnl"] for t in state_btc["trades"] if t["action"].startswith("CLOSE_")] +
        [t["pnl"] for t in state_eth["trades"] if t["action"].startswith("CLOSE_")]
    )
    wins   = state_btc["stats"]["wins"] + state_eth["stats"]["wins"]
    total  = (state_btc["stats"]["wins"] + state_btc["stats"]["losses"] +
              state_eth["stats"]["wins"] + state_eth["stats"]["losses"])
    wr     = wins / total * 100 if total else 0

    return {
        "pnl": round(shared - 1000, 2), "wr": round(wr, 1),
        "trades": total, "dd": round(max_dd, 1), "trade_pnls": all_trades,
    }


# ── Monte Carlo + DSR ─────────────────────────────────────────────────────────

def monte_carlo(trade_pnls, n=N_SIM, initial=1000.0, seed=42):
    rng = np.random.default_rng(seed)
    arr = np.array(trade_pnls)
    final_pnls, max_dds = [], []
    for _ in range(n):
        s  = rng.choice(arr, size=len(arr), replace=True)
        eq = np.concatenate([[initial], initial + np.cumsum(s)])
        pk = np.maximum.accumulate(eq)
        max_dds.append(((pk - eq) / pk * 100).max())
        final_pnls.append(eq[-1] - initial)
    fp, md = np.array(final_pnls), np.array(max_dds)
    return {
        "pnl_p5":  round(np.percentile(fp,  5), 1),
        "pnl_p50": round(np.percentile(fp, 50), 1),
        "pnl_p95": round(np.percentile(fp, 95), 1),
        "pct_pos": round(np.mean(fp > 0) * 100, 1),
        "dd_p50":  round(np.percentile(md, 50), 1),
        "dd_p95":  round(np.percentile(md, 95), 1),
    }


def sharpe_dsr(trade_pnls, k=10):
    arr = np.array(trade_pnls)
    n   = len(arr)
    if n < 5 or arr.std() == 0:
        return {"sr_ann": 0, "t_stat": 0, "p_value": 1, "dsr": 0}
    sr  = arr.mean() / arr.std(ddof=1)
    sr_ann = sr * np.sqrt((n / 570) * 252)
    t_stat, p_value = scipy_stats.ttest_1samp(arr, 0)
    z_k = ((1 - np.euler_gamma) * scipy_stats.norm.ppf(1 - 1/k) +
            np.euler_gamma      * scipy_stats.norm.ppf(1 - 1/(k * np.e)))
    dsr = scipy_stats.norm.cdf(t_stat - z_k)
    return {
        "sr_ann":  round(sr_ann, 2),
        "t_stat":  round(t_stat, 2),
        "p_value": round(p_value, 4),
        "dsr":     round(dsr * 100, 1),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*72}")
    print(f"  V8 VALIDACIÓN ESTADÍSTICA | OOS {TEST_START} → 2026-08-24")
    print(f"  Monte Carlo: {N_SIM:,} simulaciones")
    print(f"{'='*72}\n")

    df_btc_raw = pd.read_csv(LOCAL_BTC, parse_dates=["timestamp"])
    df_eth_raw = pd.read_csv(LOCAL_ETH, parse_dates=["timestamp"])
    df_btc_oos = precompute_indicators(df_btc_raw[df_btc_raw["timestamp"] >= TEST_START].reset_index(drop=True))
    df_eth_oos = precompute_indicators(df_eth_raw[df_eth_raw["timestamp"] >= TEST_START].reset_index(drop=True))
    print(f"  Datos cargados: BTC {len(df_btc_oos):,} | ETH {len(df_eth_oos):,} velas\n")

    configs = [
        ("V6 sin ML",          "single_btc", Strategy15m(),       None),
        ("V7 ML BTC",          "single_btc", make_v7(),           None),
        ("V7 ML ETH",          "single_eth", make_v7(),           None),
        ("V8 BTC+ETH ★",       "portfolio",  make_v7(),           make_v7()),
    ]

    all_results = []
    for label, mode, strat_a, strat_b in configs:
        print(f"  Ejecutando {label}...")
        if mode == "single_btc":
            r = run_single(df_btc_oos.copy(), strat_a, "BTC/USDT:USDT")
        elif mode == "single_eth":
            r = run_single(df_eth_oos.copy(), strat_a, "ETH/USDT:USDT")
        else:
            r = run_portfolio(df_btc_oos.copy(), df_eth_oos.copy(), strat_a, strat_b)
        mc = monte_carlo(r["trade_pnls"])
        st = sharpe_dsr(r["trade_pnls"])
        all_results.append({"label": label, **r, "mc": mc, "st": st})
        print(f"    PnL={r['pnl']:+.0f} | WR={r['wr']}% | Trades={r['trades']} | DD={r['dd']}%")

    # ── Tabla 1 ────────────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  TABLA 1 — RESULTADOS OOS (base: 1000 USDT)")
    print(f"{'='*72}")
    print(f"  {'Estrategia':<22} {'PnL':>8} {'WR':>7} {'Trades':>7} {'DD':>8}")
    print(f"  {'─'*55}")
    for r in all_results:
        star = " ★" if "★" in r["label"] else ""
        print(f"  {r['label']:<22} {r['pnl']:>+8.0f} {r['wr']:>6.1f}% {r['trades']:>7} {r['dd']:>7.1f}%{star}")

    # ── Tabla 2 ────────────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  TABLA 2 — MONTE CARLO ({N_SIM:,} paths)")
    print(f"{'='*72}")
    print(f"  {'Estrategia':<22} {'PnL p5':>8} {'PnL p50':>8} {'PnL p95':>8} {'% pos':>7} {'DD p95':>7}")
    print(f"  {'─'*68}")
    for r in all_results:
        mc = r["mc"]
        star = " ★" if "★" in r["label"] else ""
        print(f"  {r['label']:<22} {mc['pnl_p5']:>+8.0f} {mc['pnl_p50']:>+8.0f} {mc['pnl_p95']:>+8.0f} "
              f"{mc['pct_pos']:>6.1f}% {mc['dd_p95']:>6.1f}%{star}")

    # ── Tabla 3 ────────────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  TABLA 3 — SHARPE + DSR")
    print(f"{'='*72}")
    print(f"  {'Estrategia':<22} {'SR_ann':>7} {'t-stat':>7} {'p-value':>8} {'DSR':>6}  Veredicto")
    print(f"  {'─'*72}")
    for r in all_results:
        st = r["st"]
        if st["dsr"] >= 95 and st["p_value"] < 0.05:
            verdict = "✓ SKILL GENUINO"
        elif st["dsr"] >= 80:
            verdict = "~ PROBABLE SKILL"
        else:
            verdict = "✗ No significativo"
        star = " ★" if "★" in r["label"] else ""
        print(f"  {r['label']:<22} {st['sr_ann']:>7.2f} {st['t_stat']:>7.2f} {st['p_value']:>8.4f} "
              f"{st['dsr']:>5.1f}%  {verdict}{star}")

    # ── Resumen ────────────────────────────────────────────────────────────────
    best = next(r for r in all_results if "★" in r["label"])
    v7   = next(r for r in all_results if r["label"] == "V7 ML BTC")
    mc_b = best["mc"]
    st_b = best["st"]
    print(f"""
  RESUMEN V8
  ──────────
  V8 BTC+ETH portfolio vs V7 BTC solo:
    PnL:     {v7['pnl']:+.0f} → {best['pnl']:+.0f} USDT  ({best['pnl']-v7['pnl']:+.0f} extra con mismo capital)
    SR_ann:  {v7['st']['sr_ann']:.2f}  →  {st_b['sr_ann']:.2f}
    DD:      {v7['dd']:.1f}%  →  {best['dd']:.1f}%
    MC 100%: {"SÍ" if mc_b['pct_pos'] == 100 else "NO"} ({mc_b['pct_pos']:.0f}% paths positivos)
    DD p95:  {mc_b['dd_p95']:.1f}% (peor caso en {N_SIM} simulaciones)
    DSR:     {st_b['dsr']:.1f}%  {"✓" if st_b['dsr'] >= 95 else "~"}
""")
