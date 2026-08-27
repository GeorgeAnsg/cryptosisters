"""
validation.py — Validación estadística de la estrategia v6
============================================================
Tres técnicas:
  1. Walk-Forward Optimization (WFO) — parámetros entrenados en ventana pasada,
     validados en el siguiente período. Confirma que no hay overfitting temporal.
  2. Monte Carlo sobre trades — permuta 10k veces la secuencia de trades para
     estimar la distribución real del drawdown máximo.
  3. Deflated Sharpe Ratio — ajusta el Sharpe por el nº de estrategias probadas.

Uso:
    python -m v6.tools.validation --profile moderate --layer3
"""
import argparse, sys, time
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import ccxt
from v6.core.bot_core   import RISK_PROFILES, run_backtest
from v6.core.bot_indicators import precompute_indicators
from v6.core.bot_layer3 import get_layer3_extras
from v6.strategies.strategy_15m import Strategy15m

WARMUP = 600

class _StrategyL3(Strategy15m):
    def get_signal(self, df_ltf, live_extras, row=None):
        _row = row if row is not None else df_ltf.iloc[-1]
        ts   = _row.get("timestamp") if hasattr(_row, "get") else getattr(_row, "timestamp", None)
        if ts is not None and hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if ts is not None:
            live_extras = get_layer3_extras(ts)
        return super().get_signal(df_ltf, live_extras, row=row)


# =============================================================================
# UTILS
# =============================================================================

def _slice_period(df_full, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start)
    end_ts   = pd.Timestamp(end) + pd.Timedelta(days=1)
    mask     = (df_full["timestamp"] >= start_ts) & (df_full["timestamp"] < end_ts)
    idx_start = df_full.index[mask].min() if mask.any() else None
    if idx_start is None:
        return pd.DataFrame()
    idx_slice = max(0, idx_start - WARMUP)
    df = df_full.iloc[idx_slice:].copy()
    return df[df["timestamp"] < end_ts].reset_index(drop=True)


def _run_bt(exchange, df, risk_profile, strategy) -> dict:
    if len(df) < WARMUP + 10:
        return {"pnl": 0, "wr": 0, "trades": 0, "dd": 0, "trade_pnls": []}
    result = run_backtest(exchange=exchange, pair="BTC/USDT:USDT", days=0,
                          risk_profile=risk_profile, strategy=strategy,
                          min_hold_candles=3, _df_override=df)
    stats  = result["stats"]
    total  = stats["wins"] + stats["losses"]
    wr     = stats["wins"] / total * 100 if total else 0
    closed = [t["pnl"] for t in result.get("trades", []) if "pnl" in t]
    return {"pnl": stats["total_pnl"], "wr": wr, "trades": total,
            "dd": result["max_drawdown_seen"], "trade_pnls": closed}


def _make_profile(base, ms, sl, tp):
    p = dict(base)
    p["min_score"] = ms; p["stop_loss_atr_mult"] = sl; p["take_profit_atr_mult"] = tp
    return p


# =============================================================================
# 1. WALK-FORWARD OPTIMIZATION
# =============================================================================

WFO_GRID = {
    "min_score":            [52, 55, 58, 62],
    "stop_loss_atr_mult":   [1.5, 2.0, 2.5],
    "take_profit_atr_mult": [4.0, 5.0, 6.0],
}
# 36 combos — más rápido que el optimizer completo

WFO_FOLDS = [
    # (train_start, train_end, validate_start, validate_end)
    ("2021-09-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2021-09-01", "2023-12-31", "2023-10-01", "2024-03-31"),
    ("2021-09-01", "2024-06-30", "2025-01-01", "2025-05-31"),
]


def run_wfo(exchange, df_full, base_profile, strategy, use_l3: bool):
    print("\n" + "=" * 70)
    print("  WALK-FORWARD OPTIMIZATION (3 folds)")
    print("  Grid: {} combinaciones por fold".format(
        len(list(product(*WFO_GRID.values())))))
    print("=" * 70)

    keys   = list(WFO_GRID.keys())
    combos = list(product(*[WFO_GRID[k] for k in keys]))
    fold_best_params = []

    for fold_i, (tr_s, tr_e, va_s, va_e) in enumerate(WFO_FOLDS, 1):
        print(f"\n  Fold {fold_i}: train [{tr_s}→{tr_e}] | validate [{va_s}→{va_e}]")
        df_train    = _slice_period(df_full, tr_s, tr_e)
        df_validate = _slice_period(df_full, va_s, va_e)

        # Buscar mejores params en train
        best_score, best_combo = -1e9, None
        for i, combo in enumerate(combos, 1):
            ms, sl, tp = combo
            rp = _make_profile(base_profile, ms, sl, tp)
            r  = _run_bt(exchange, df_train.copy(), rp, strategy)
            sc = r["pnl"] - 15 * (1 if r["pnl"] < 0 else 0) - max(0, r["dd"] - 8) * 10
            if sc > best_score:
                best_score = sc; best_combo = combo

        ms_b, sl_b, tp_b = best_combo
        print(f"    Mejor en train: ms={ms_b} sl={sl_b} tp={tp_b} (score={best_score:.0f})")

        # Validar en el siguiente período
        rp_best = _make_profile(base_profile, ms_b, sl_b, tp_b)
        rv = _run_bt(exchange, df_validate.copy(), rp_best, strategy)
        print(f"    Validación:     PnL={rv['pnl']:+.0f} USDT | WR={rv['wr']:.1f}% | "
              f"Trades={rv['trades']} | DD={rv['dd']:.1f}%")
        fold_best_params.append((best_combo, rv["pnl"]))

    # Estabilidad de parámetros
    all_ms  = [p[0][0] for p in fold_best_params]
    all_sl  = [p[0][1] for p in fold_best_params]
    all_tp  = [p[0][2] for p in fold_best_params]
    val_pnls = [p[1] for p in fold_best_params]

    print(f"\n  Estabilidad de parámetros:")
    print(f"    min_score óptimo por fold: {all_ms}  {'✓ estable' if len(set(all_ms)) <= 2 else '⚠ inestable'}")
    print(f"    SL óptimo por fold:        {all_sl}  {'✓ estable' if len(set(all_sl)) <= 2 else '⚠ inestable'}")
    print(f"    TP óptimo por fold:        {all_tp}  {'✓ estable' if len(set(all_tp)) <= 2 else '⚠ inestable'}")
    print(f"    Validación PnL por fold:   {[f'{p:+.0f}' for p in val_pnls]}")
    print(f"    PnL total validación:      {sum(val_pnls):+.0f} USDT  "
          f"({'✓ positivo' if sum(val_pnls) > 0 else '⚠ negativo'})")


# =============================================================================
# 2. MONTE CARLO — DRAWDOWN
# =============================================================================

def run_monte_carlo(trade_pnls: list, initial_balance: float = 1000.0,
                    n_sim: int = 10_000):
    if not trade_pnls:
        print("\n  [Monte Carlo] Sin trades para simular.")
        return

    print("\n" + "=" * 70)
    print(f"  MONTE CARLO DRAWDOWN ({n_sim:,} simulaciones | {len(trade_pnls)} trades)")
    print("=" * 70)

    pnls    = np.array(trade_pnls)
    max_dds = np.zeros(n_sim)

    for i in range(n_sim):
        perm   = np.random.permutation(pnls)
        equity = initial_balance + np.cumsum(perm)
        peak   = np.maximum.accumulate(np.concatenate([[initial_balance], equity]))
        dd_abs = peak[1:] - equity
        dd_pct = dd_abs / peak[1:] * 100
        max_dds[i] = dd_pct.max()

    print(f"  Drawdown máximo esperado (percentiles):")
    print(f"    p50  (mediana):    {np.percentile(max_dds, 50):.1f}%")
    print(f"    p75:               {np.percentile(max_dds, 75):.1f}%")
    print(f"    p90:               {np.percentile(max_dds, 90):.1f}%")
    print(f"    p95 (worst-case):  {np.percentile(max_dds, 95):.1f}%")
    print(f"    Promedio:          {max_dds.mean():.1f}%")

    p95 = np.percentile(max_dds, 95)
    if p95 < 10:
        verdict = "✓ EXCELENTE — riesgo muy controlado"
    elif p95 < 15:
        verdict = "✓ BUENO — riesgo aceptable"
    elif p95 < 20:
        verdict = "⚠ MODERADO — considerar reducir tamaño"
    else:
        verdict = "✗ ALTO — revisar sizing"
    print(f"\n  Veredicto p95: {verdict}")

    # Probabilidad de DD > 10% y > 15%
    prob_10 = (max_dds > 10).mean() * 100
    prob_15 = (max_dds > 15).mean() * 100
    print(f"  Prob DD > 10%: {prob_10:.1f}%  |  Prob DD > 15%: {prob_15:.1f}%")


# =============================================================================
# 3. DEFLATED SHARPE RATIO
# =============================================================================

def compute_deflated_sharpe(trade_pnls: list, n_trials: int = 80,
                             initial_balance: float = 1000.0):
    """
    Bailey & Lopez de Prado (2014): ajusta el Sharpe por el nº de estrategias probadas.
    Con N trials, la probabilidad de encontrar un Sharpe alto por azar aumenta.
    """
    if not trade_pnls:
        return

    print("\n" + "=" * 70)
    print(f"  DEFLATED SHARPE RATIO (N pruebas = {n_trials})")
    print("=" * 70)

    pnls   = np.array(trade_pnls)
    T      = len(pnls)
    mean_r = pnls.mean()
    std_r  = pnls.std(ddof=1)

    if std_r == 0:
        print("  [DSR] Desviación estándar cero — no calculable")
        return

    sharpe = (mean_r / std_r) * np.sqrt(T)  # Sharpe anualizado proxy

    # Expected max Sharpe under repeated testing (Bailey & Lopez de Prado)
    # E[max SR] ≈ (1 - gamma) * Z^-1(1 - 1/N) + gamma * Z^-1(1 - 1/(N*e))
    # Simplificado: ajuste por sqrt(2 * log(N)) - log(log(N) + log(4*pi)) / (2*sqrt(2*log(N)))
    from scipy import stats as _stats
    _N   = n_trials
    _mu  = (1 - 0.5772) / np.sqrt(_N)        # approx expected max under H0
    _sig = np.pi / (6 * np.sqrt(_N))
    expected_max_sr = _mu + _sig * np.sqrt(2 * np.log(_N))  # Gumbel approx

    # Probabilidad de que el Sharpe observado sea mayor que el esperado por azar
    psr  = _stats.norm.cdf((sharpe - expected_max_sr) / (1 + sharpe**2 / (2*T)))

    print(f"  Sharpe ratio observado:   {sharpe:.3f}")
    print(f"  Expected max SR (N={_N}): {expected_max_sr:.3f}")
    print(f"  Probabilidad de skill:    {psr:.1%}")
    print(f"  Trades usados:            {T}")

    if psr >= 0.95:
        verdict = "✓ EXCELENTE — muy probablemente skill real, no suerte"
    elif psr >= 0.80:
        verdict = "✓ BUENO — señal estadística significativa"
    elif psr >= 0.60:
        verdict = "⚠ MODERADO — posible overfitting parcial"
    else:
        verdict = "✗ BAJO — probablemente overfitting sobre datos históricos"
    print(f"  Veredicto: {verdict}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="moderate", choices=RISK_PROFILES.keys())
    parser.add_argument("--layer3",  action="store_true")
    parser.add_argument("--wfo",     action="store_true", help="Solo WFO (más lento)")
    args = parser.parse_args()

    exchange = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "linear"}})

    csv_path = ROOT / "data" / "btc_15m_full.csv"
    print(f"Cargando {csv_path.name}...", end=" ", flush=True)
    df_raw = pd.read_csv(csv_path, parse_dates=["timestamp"])
    print(f"{len(df_raw):,} velas")

    print("Precalculando indicadores...", end=" ", flush=True)
    t0 = time.time()
    df_full = precompute_indicators(df_raw)
    print(f"OK ({time.time()-t0:.1f}s)")

    base_profile = dict(RISK_PROFILES[args.profile])
    strategy     = _StrategyL3() if args.layer3 else Strategy15m()
    l3_label     = " + L3" if args.layer3 else ""
    print(f"\nPerfil: {args.profile}{l3_label}")

    # ── Recoger trades del backtest completo (para Monte Carlo + DSR) ─────────
    all_period_pnls = []
    FULL_PERIODS = [
        ("2021-09-01", "2026-08-26"),
    ]
    print("\nEjecutando backtest completo para recoger trades...", end=" ", flush=True)
    df_all = _slice_period(df_full, "2021-09-01", "2026-08-26")
    r_all  = _run_bt(exchange, df_all, base_profile, strategy)
    all_period_pnls = r_all["trade_pnls"]
    print(f"OK ({len(all_period_pnls)} trades cerrados, PnL={r_all['pnl']:+.0f} USDT)")

    # ── Monte Carlo ───────────────────────────────────────────────────────────
    run_monte_carlo(all_period_pnls)

    # ── Deflated Sharpe Ratio ─────────────────────────────────────────────────
    compute_deflated_sharpe(all_period_pnls, n_trials=80)

    # ── Walk-Forward (lento — opcional) ───────────────────────────────────────
    if args.wfo:
        run_wfo(exchange, df_full, base_profile, strategy, use_l3=args.layer3)

    print()


if __name__ == "__main__":
    main()
