"""
v7/validate_full.py — Validación estadística completa V4 vs V6 vs V7

Período OOS 2025-01-01 → 2026-08-24 (datos nunca vistos por el modelo V7).

Tests:
  1. Backtest comparativo V4-like / V6 / V7 ML / V7 ML+TP dinámico
  2. Monte Carlo bootstrap (1000 paths) → DD p95, PnL p5/p50/p95, % paths positivos
  3. Sharpe Ratio anualizado + t-test (¿PnL > 0 con significancia estadística?)
  4. DSR — Deflated Sharpe Ratio (corrige selección de thresholds)

Run: python v7/validate_full.py
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
from v6.core.bot_sentiment import load_fear_greed_sentiment
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import StrategyML

LOCAL_CSV  = ROOT / "data" / "btc_15m_full.csv"
MODEL_DIR  = ROOT / "v7" / "models"
TEST_START = "2025-01-01"
N_SIMULATIONS = 2000

# ── Configuraciones ────────────────────────────────────────────────────────────

# V4-like: parámetros que aproximan el bot de producción (SL=1.5, TP=4.0, sin HTF)
V4_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 1.5, "take_profit_atr_mult": 4.0,
    "min_score": 52, "entry_advantage": 10, "max_daily_trades": 6,
    "max_drawdown_pct": 0.15, "max_daily_loss_pct": 0.05,
    "trailing_stop": False, "max_tp_extensions": 0,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

# V6 final
V6_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

# ── TP dinámico ────────────────────────────────────────────────────────────────
TP_DYNAMIC = {
    ("bull",    True):  5.0,
    ("bull",    False): 4.5,
    ("neutral", True):  3.5,
    ("neutral", False): 3.5,
    ("bear",    True):  4.5,
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


# ── Backtest engine ────────────────────────────────────────────────────────────

def run_bt(df, strategy, base_risk, use_dynamic_tp=False, pair="BTC/USDT:USDT"):
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
        rp     = apply_regime(base_risk, signal.regime)

        if use_dynamic_tp:
            rp["take_profit_atr_mult"] = dynamic_tp(signal)

        atr = signal.technical.get("details", {}).get("atr", 0)
        check_sl_tp(state, pair, current_price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, current_price, atr, signal, rp,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

        bal    = state["balance_usdt"]
        pos    = state.get("position")
        equity = bal + pos["amount"] * pos["entry_price"] if pos else bal
        if equity > peak_eq: peak_eq = equity
        dd = (peak_eq - equity) / peak_eq * 100
        if dd > max_dd_eq: max_dd_eq = dd

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END_OF_BACKTEST")

    total  = state["stats"]["wins"] + state["stats"]["losses"]
    wr     = state["stats"]["wins"] / total * 100 if total else 0
    pnl    = state["balance_usdt"] - 1000
    trades = [t["pnl"] for t in state["trades"] if t["action"].startswith("CLOSE_")]

    return {
        "pnl":    round(pnl, 2),
        "wr":     round(wr, 1),
        "trades": total,
        "dd":     round(max_dd_eq, 1),
        "trade_pnls": trades,
    }


# ── Estadísticas ───────────────────────────────────────────────────────────────

def monte_carlo(trade_pnls, n=N_SIMULATIONS, initial=1000.0, seed=42):
    rng = np.random.default_rng(seed)
    arr = np.array(trade_pnls)
    final_pnls, max_dds = [], []

    for _ in range(n):
        sampled = rng.choice(arr, size=len(arr), replace=True)
        equity  = np.concatenate([[initial], initial + np.cumsum(sampled)])
        peak    = np.maximum.accumulate(equity)
        dds     = (peak - equity) / peak * 100
        max_dds.append(dds.max())
        final_pnls.append(equity[-1] - initial)

    fp = np.array(final_pnls)
    md = np.array(max_dds)
    return {
        "pnl_p5":   round(np.percentile(fp,  5), 1),
        "pnl_p50":  round(np.percentile(fp, 50), 1),
        "pnl_p95":  round(np.percentile(fp, 95), 1),
        "pct_pos":  round(np.mean(fp > 0) * 100, 1),
        "dd_p50":   round(np.percentile(md, 50), 1),
        "dd_p95":   round(np.percentile(md, 95), 1),
    }


def sharpe_and_dsr(trade_pnls, n_thresholds_tested=10):
    """
    Sharpe anualizado + t-test + DSR (Deflated Sharpe Ratio).

    DSR (Bailey & López de Prado 2012, simplificado):
      Ajusta el t-stat por haber probado múltiples thresholds/configs.
      DSR = Φ(t_stat - z_k)  donde z_k = E[max(Z₁,...,Zₖ)] bajo H₀.
      Si DSR > 95% → skill genuino ajustado por selección.

    Thresholds probados para V7: t=0.50, 0.525, 0.55, 0.575, 0.60, 0.625,
      0.65, 0.675, 0.70, 0.725  → k=10 configs (conservador).
    """
    arr = np.array(trade_pnls)
    n   = len(arr)
    if n < 5 or arr.std() == 0:
        return {"sr": 0, "sr_ann": 0, "t_stat": 0, "p_value": 1, "dsr": 0}

    mean_ret = arr.mean()
    std_ret  = arr.std(ddof=1)
    sr       = mean_ret / std_ret

    # Anualizar: ~252 trading days/year, trades/day ≈ n / 570 (570 días en OOS)
    trading_days = 570
    trades_per_day = n / trading_days
    sr_ann = sr * np.sqrt(trades_per_day * 252)

    # t-test: ¿es la media de retornos estadísticamente > 0?
    t_stat, p_value = scipy_stats.ttest_1samp(arr, 0)

    # DSR: corregir por selección de threshold
    # Bajo H₀ (verdadero SR=0), el t-stat del mejor de k ensayos independientes
    # tiene valor esperado z_k (aproximación de Gumbel):
    k = n_thresholds_tested
    z_k = ((1 - np.euler_gamma) * scipy_stats.norm.ppf(1 - 1/k) +
            np.euler_gamma      * scipy_stats.norm.ppf(1 - 1/(k * np.e)))

    # DSR = probabilidad de que el t_stat supere z_k (corrección por selección)
    dsr = scipy_stats.norm.cdf(t_stat - z_k)

    return {
        "sr":      round(sr, 3),
        "sr_ann":  round(sr_ann, 2),
        "t_stat":  round(t_stat, 2),
        "p_value": round(p_value, 4),
        "dsr":     round(dsr * 100, 1),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*72}")
    print(f"  VALIDACIÓN ESTADÍSTICA COMPLETA — OOS {TEST_START} → 2026-08-24")
    print(f"  Monte Carlo: {N_SIMULATIONS:,} simulaciones | Bootstrap con reemplazamiento")
    print(f"{'='*72}\n")

    df_raw = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df_oos = df_raw[df_raw["timestamp"] >= TEST_START].reset_index(drop=True)
    df_oos = precompute_indicators(df_oos)
    print(f"  Datos: {len(df_oos):,} velas ({TEST_START} → 2026-08-24)\n")

    oos_pkl  = MODEL_DIR / "v7_classifier_oos.pkl"
    oos_meta = json.load(open(MODEL_DIR / "v7_classifier_oos_meta.json"))

    def make_v7():
        s = StrategyML(model_path=str(oos_pkl), threshold=0.55)
        s.feature_cols = oos_meta["feature_cols"]
        return s

    configs = [
        ("V4-like",           Strategy15m(), V4_RISK, False),
        ("V6",                Strategy15m(), V6_RISK, False),
        ("V7 ML@0.55",        make_v7(),     V6_RISK, False),
        ("V7 ML + TP dinám.", make_v7(),     V6_RISK, True),
    ]

    all_results = []

    for label, strategy, risk, dtp in configs:
        print(f"  Ejecutando {label}...")
        r = run_bt(df_oos, strategy, risk, use_dynamic_tp=dtp)
        mc = monte_carlo(r["trade_pnls"])
        st = sharpe_and_dsr(r["trade_pnls"])
        all_results.append({"label": label, **r, "mc": mc, "st": st})
        print(f"    → PnL={r['pnl']:+.0f} | WR={r['wr']}% | Trades={r['trades']} | DD={r['dd']}%")

    # ── Tabla 1: Resultados básicos ────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  TABLA 1 — RESULTADOS OOS (2025-2026)")
    print(f"{'='*72}")
    print(f"  {'Estrategia':<22} {'PnL':>8} {'WR':>7} {'Trades':>7} {'DD real':>8}")
    print(f"  {'─'*60}")
    for r in all_results:
        star = " ★" if "V7 ML + TP" in r["label"] else ""
        print(f"  {r['label']:<22} {r['pnl']:>+8.0f} {r['wr']:>6.1f}% {r['trades']:>7} {r['dd']:>7.1f}%{star}")

    # ── Tabla 2: Monte Carlo ───────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  TABLA 2 — MONTE CARLO ({N_SIMULATIONS:,} paths bootstrap)")
    print(f"  Pregunta: si el orden de trades fuera aleatorio, ¿qué rango de resultados veríamos?")
    print(f"{'='*72}")
    print(f"  {'Estrategia':<22} {'PnL p5':>8} {'PnL p50':>8} {'PnL p95':>8} {'% pos':>7} {'DD p50':>7} {'DD p95':>7}")
    print(f"  {'─'*72}")
    for r in all_results:
        mc = r["mc"]
        star = " ★" if "V7 ML + TP" in r["label"] else ""
        print(f"  {r['label']:<22} {mc['pnl_p5']:>+8.0f} {mc['pnl_p50']:>+8.0f} {mc['pnl_p95']:>+8.0f} "
              f"{mc['pct_pos']:>6.1f}% {mc['dd_p50']:>6.1f}% {mc['dd_p95']:>6.1f}%{star}")

    # ── Tabla 3: Sharpe + DSR ──────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  TABLA 3 — SHARPE RATIO + DSR (Deflated Sharpe Ratio)")
    print(f"  DSR >95% = skill genuino incluso ajustando por múltiples configs probadas")
    print(f"{'='*72}")
    print(f"  {'Estrategia':<22} {'SR_ann':>7} {'t-stat':>7} {'p-value':>8} {'DSR':>6} {'Veredicto'}")
    print(f"  {'─'*72}")
    for r in all_results:
        st  = r["st"]
        p   = st["p_value"]
        dsr = st["dsr"]
        if dsr >= 95 and p < 0.05:
            verdict = "✓ SKILL GENUINO"
        elif dsr >= 80 and p < 0.10:
            verdict = "~ PROBABLE SKILL"
        elif p < 0.05:
            verdict = "~ Significativo (corr. selección pendiente)"
        else:
            verdict = "✗ No significativo"
        star = " ★" if "V7 ML + TP" in r["label"] else ""
        print(f"  {r['label']:<22} {st['sr_ann']:>7.2f} {st['t_stat']:>7.2f} {p:>8.4f} {dsr:>5.1f}% {verdict}{star}")

    # ── Referencia V4 producción ───────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  REFERENCIA — V4 PRODUCCIÓN (5 años 2021-2026, NO validado estadísticamente)")
    print(f"  PnL: +2718 USDT (+271.8%) | WR: 40.9% | DD: 9.2% | Trades: 2506")
    print(f"  En el mismo período OOS (2025-2026): ver V4-like arriba")
    print(f"{'='*72}")

    # ── Resumen ────────────────────────────────────────────────────────────────
    best = max(all_results, key=lambda x: x["pnl"])
    mc_b = best["mc"]
    st_b = best["st"]
    print(f"""
  RESUMEN EJECUTIVO
  ─────────────────
  Mejor config OOS: {best['label']}
    • PnL real:    {best['pnl']:+.0f} USDT en 1.5 años
    • WR:          {best['wr']}%
    • DD real:     {best['dd']}%
    • MC p5/p95:   {mc_b['pnl_p5']:+.0f} / {mc_b['pnl_p95']:+.0f} USDT ({mc_b['pct_pos']:.0f}% paths positivos)
    • DD p95 (MC): {mc_b['dd_p95']:.1f}% (peor caso esperado en 2000 simulaciones)
    • SR anual:    {st_b['sr_ann']:.2f} | p-value={st_b['p_value']:.4f} | DSR={st_b['dsr']:.1f}%
""")
