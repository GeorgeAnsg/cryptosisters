"""
optimizer.py — Búsqueda de parámetros óptimos para la estrategia 15m (v6)
=========================================================================
Prueba combinaciones de min_score, SL y TP sobre los 6 períodos históricos.
Indicadores precalculados UNA sola vez; solo el loop de trading varía.

Uso:
    python -m v6.tools.optimizer --profile moderate
    python -m v6.tools.optimizer --profile moderate --layer3
"""
import argparse, sys, time
from pathlib import Path
from itertools import product

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import ccxt
from v6.core.bot_core   import RISK_PROFILES, run_backtest, Signal
from v6.core.bot_indicators import precompute_indicators, analyze_layer1, detect_regime_auto
from v6.core.bot_risk       import calculate_scores
from v6.core.bot_layer3     import get_layer3_extras
from v6.strategies.strategy_15m import Strategy15m

PERIODS = [
    ("Sep-Nov 2021",  "Bull final",   "2021-09-01", "2021-11-30"),
    ("2022",          "Bear duro",    "2022-01-01", "2022-12-31"),
    ("2023",          "Acumulación",  "2023-01-01", "2023-12-31"),
    ("Oct23-Mar24",   "Bull run",     "2023-10-01", "2024-03-31"),
    ("Ene-May 2025",  "Corrección",   "2025-01-01", "2025-05-31"),
    ("Jun25-Ago26",   "Recuperación", "2025-06-01", "2026-08-26"),
]

# ─── GRID DE PARÁMETROS ────────────────────────────────────────────────────
GRID = {
    "min_score":              [48, 52, 55, 58, 62],
    "stop_loss_atr_mult":     [1.2, 1.5, 2.0, 2.5],
    "take_profit_atr_mult":   [3.5, 4.0, 5.0, 6.0],
}
# ──────────────────────────────────────────────────────────────────────────

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


def _make_profile(base: dict, min_score: int, sl: float, tp: float) -> dict:
    p = dict(base)
    p["min_score"]              = min_score
    p["stop_loss_atr_mult"]     = sl
    p["take_profit_atr_mult"]   = tp
    return p


def _run_period(exchange, df_full, label, start, end, risk_profile, strategy) -> dict:
    start_ts = pd.Timestamp(start)
    end_ts   = pd.Timestamp(end) + pd.Timedelta(days=1)
    mask     = (df_full["timestamp"] >= start_ts) & (df_full["timestamp"] < end_ts)
    idx_start = df_full.index[mask].min() if mask.any() else None
    if idx_start is None:
        return {"pnl": 0, "wr": 0, "trades": 0, "dd": 0}

    idx_slice = max(0, idx_start - WARMUP)
    df_p = df_full.iloc[idx_slice:].copy()
    df_p = df_p[df_p["timestamp"] < end_ts].reset_index(drop=True)
    if len(df_p) < WARMUP + 10:
        return {"pnl": 0, "wr": 0, "trades": 0, "dd": 0}

    result  = run_backtest(exchange=exchange, pair="BTC/USDT:USDT", days=0,
                           risk_profile=risk_profile, strategy=strategy,
                           min_hold_candles=3, _df_override=df_p)
    stats   = result["stats"]
    total_t = stats["wins"] + stats["losses"]
    wr      = stats["wins"] / total_t * 100 if total_t else 0
    return {"pnl": stats["total_pnl"], "wr": wr,
            "trades": total_t, "dd": result["max_drawdown_seen"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="moderate", choices=RISK_PROFILES.keys())
    parser.add_argument("--layer3",  action="store_true")
    args = parser.parse_args()

    exchange = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "linear"}})

    # ── Cargar y precomputar UNA sola vez ──────────────────────────────────
    csv_path = ROOT / "data" / "btc_15m_full.csv"
    print(f"Cargando {csv_path.name}...", end=" ", flush=True)
    df_raw = pd.read_csv(csv_path, parse_dates=["timestamp"])
    print(f"{len(df_raw):,} velas")

    print("Precalculando indicadores (una sola vez)...", end=" ", flush=True)
    t0 = time.time()
    df_full = precompute_indicators(df_raw)
    print(f"OK ({time.time()-t0:.1f}s)")

    base_profile = dict(RISK_PROFILES[args.profile])
    strategy_cls = _StrategyL3 if args.layer3 else Strategy15m
    l3_label     = " + L3" if args.layer3 else ""
    strategy     = strategy_cls()

    keys   = list(GRID.keys())
    values = list(GRID.values())
    combos = list(product(*values))
    total  = len(combos)

    print(f"\nGrid search: {total} combinaciones | perfil base: {args.profile}{l3_label}")
    print(f"  min_score: {GRID['min_score']}")
    print(f"  SL×ATR:    {GRID['stop_loss_atr_mult']}")
    print(f"  TP×ATR:    {GRID['take_profit_atr_mult']}")
    print()

    results = []
    for i, combo in enumerate(combos, 1):
        ms, sl, tp = combo
        rp = _make_profile(base_profile, ms, sl, tp)

        period_pnls = []
        max_dd_any  = 0
        total_trades = 0
        neg_periods  = 0

        for label, _market, start, end in PERIODS:
            r = _run_period(exchange, df_full, label, start, end, rp, strategy)
            period_pnls.append(r["pnl"])
            max_dd_any   = max(max_dd_any, r["dd"])
            total_trades += r["trades"]
            if r["pnl"] < 0:
                neg_periods += 1

        total_pnl = sum(period_pnls)
        # Puntuación compuesta: PnL total, penalizar períodos negativos y DD alto
        score = total_pnl - (neg_periods * 15) - max(0, max_dd_any - 8) * 10

        results.append({
            "min_score": ms, "sl": sl, "tp": tp,
            "total_pnl": total_pnl, "max_dd": max_dd_any,
            "neg_periods": neg_periods, "total_trades": total_trades,
            "score": score, "periods": period_pnls,
        })

        # Progreso cada 10 combos
        if i % 10 == 0 or i == total:
            best_so_far = max(results, key=lambda x: x["score"])
            print(f"  [{i:3d}/{total}] mejor hasta ahora: "
                  f"ms={best_so_far['min_score']} sl={best_so_far['sl']} "
                  f"tp={best_so_far['tp']} → PnL={best_so_far['total_pnl']:+.0f} "
                  f"DD={best_so_far['max_dd']:.1f}%")

    # ── Resultados ─────────────────────────────────────────────────────────
    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:15]

    labels_short = ["S-N21", "2022", "2023", "O23-M24", "E-M25", "J25-A26"]

    print(f"\n{'='*90}")
    print(f"  TOP 15 COMBINACIONES (ordenadas por score compuesto)")
    print(f"  Score = PnL total − 15×períodos_negativos − exceso_DD×10")
    print(f"{'='*90}")
    header = f"  {'Rk':>2}  {'MS':>4}  {'SL':>5}  {'TP':>5}  {'PnL':>8}  {'DD':>6}  {'Neg':>4}  {'Trd':>5}  "
    header += "  ".join(f"{l:>7}" for l in labels_short)
    print(header)
    print("─" * 90)
    for rk, r in enumerate(top, 1):
        periods_str = "  ".join(f"{p:>+7.0f}" for p in r["periods"])
        print(f"  {rk:>2}  {r['min_score']:>4}  {r['sl']:>5.1f}  {r['tp']:>5.1f}  "
              f"{r['total_pnl']:>+8.0f}  {r['max_dd']:>5.1f}%  {r['neg_periods']:>4}  "
              f"{r['total_trades']:>5}  {periods_str}")

    best = results[0]
    print(f"\n{'='*90}")
    print(f"  PARÁMETROS ÓPTIMOS:")
    print(f"    min_score:            {best['min_score']}")
    print(f"    stop_loss_atr_mult:   {best['sl']}")
    print(f"    take_profit_atr_mult: {best['tp']}")
    print(f"    → PnL total: {best['total_pnl']:+.0f} USDT  |  Max DD: {best['max_dd']:.1f}%  "
          f"|  Períodos negativos: {best['neg_periods']}/6")

    # Comparar vs parámetros actuales
    current = next((r for r in results
                    if r["min_score"] == base_profile["min_score"]
                    and r["sl"] == base_profile["stop_loss_atr_mult"]
                    and r["tp"] == base_profile["take_profit_atr_mult"]), None)
    if current:
        print(f"\n  Parámetros actuales (ms={base_profile['min_score']} "
              f"sl={base_profile['stop_loss_atr_mult']} "
              f"tp={base_profile['take_profit_atr_mult']}): "
              f"PnL={current['total_pnl']:+.0f} USDT")
        print(f"  Mejora del óptimo vs actual: "
              f"{best['total_pnl'] - current['total_pnl']:+.0f} USDT")
    print(f"{'='*90}\n")


if __name__ == "__main__":
    main()
