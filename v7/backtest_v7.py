"""
V7 — Full backtest with ML-filtered strategy.
Compares V7 (ML gate) vs V6 baseline on same 2023-2026 data.

Run: python v7/backtest_v7.py
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from v6.core.bot_core import run_backtest, RISK_PROFILES
from v6.core.bot_indicators import precompute_indicators
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import StrategyML

LOCAL_CSV  = ROOT / "data" / "btc_15m_full.csv"
START_DATE = "2023-01-01"

RISK_PROFILE = {
    "risk_pct":               0.02,
    "max_cost_pct":           0.35,
    "stop_loss_atr_mult":     2.5,
    "take_profit_atr_mult":   4.0,
    "min_score":              58,
    "entry_advantage":        15,
    "max_daily_trades":       6,
    "max_drawdown_pct":       0.10,
    "max_daily_loss_pct":     0.03,
    "trailing_stop":          True,
    "max_tp_extensions":      2,
    "weekend_mode":           "range",
    "weekend_min_score_bonus": 10,
    "min_vol_ratio":          0.0,
}


def load_local_data(start_date: str) -> pd.DataFrame:
    print(f"  Loading {LOCAL_CSV.name}...")
    df = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df = df[df["timestamp"] >= start_date].reset_index(drop=True)
    print(f"  {len(df):,} candles ({df['timestamp'].iloc[0].date()} → {df['timestamp'].iloc[-1].date()})")
    print("  Precomputing indicators...")
    return precompute_indicators(df)


def run_and_report(label: str, strategy, df: pd.DataFrame):
    print(f"\n─── {label} ───")
    result = run_backtest(
        exchange     = None,
        pair         = "BTC/USDT:USDT",
        days         = 0,
        risk_profile = RISK_PROFILE,
        strategy     = strategy,
        _df_override = df,
    )
    stats  = result["stats"]
    total  = stats["wins"] + stats["losses"]
    wr     = stats["wins"] / total * 100 if total else 0
    pnl    = result["final_balance"] - 1000
    longs  = stats.get("total_longs", 0)
    shorts = stats.get("total_shorts", 0)
    lw     = stats.get("long_wins", 0)
    sw     = stats.get("short_wins", 0)

    print(f"  PnL:    {pnl:+.2f} USDT  (balance: {result['final_balance']:.2f})")
    print(f"  Trades: {total} | WR: {wr:.1f}%  (L: {longs} W{lw}  S: {shorts} W{sw})")

    if hasattr(strategy, "print_ml_stats"):
        strategy.print_ml_stats()

    return {"label": label, "pnl": round(pnl, 2), "trades": total, "wr": round(wr, 1),
            "longs": longs, "shorts": shorts}


if __name__ == "__main__":
    print(f"\n[V7 Backtest] Comparing V6 vs V7 (ML-filtered)")
    print(f"  Period: {START_DATE} → 2026-08-24\n")

    df = load_local_data(START_DATE)

    # Baseline: V6 (no ML filter)
    v6_strategy = Strategy15m()
    r_v6 = run_and_report("V6 baseline (no ML)", v6_strategy, df)

    # V7: ML-filtered with threshold=0.55
    v7_strategy = StrategyML(threshold=0.55)
    r_v7_55 = run_and_report("V7 ML (threshold=0.55)", v7_strategy, df)

    # V7: ML-filtered with threshold=0.50 (more trades, lower bar)
    v7_strategy_50 = StrategyML(threshold=0.50)
    r_v7_50 = run_and_report("V7 ML (threshold=0.50)", v7_strategy_50, df)

    # V7: ML-filtered with threshold=0.60 (fewer but higher quality)
    v7_strategy_60 = StrategyML(threshold=0.60)
    r_v7_60 = run_and_report("V7 ML (threshold=0.60)", v7_strategy_60, df)

    print("\n" + "=" * 60)
    print("  SUMMARY (2023-2026)")
    print("=" * 60)
    print(f"  {'Strategy':<30} {'PnL':>8}  {'Trades':>7}  {'WR':>6}")
    print("  " + "-" * 57)
    for r in [r_v6, r_v7_50, r_v7_55, r_v7_60]:
        marker = " ◀" if r["label"].startswith("V7") and r["pnl"] > r_v6["pnl"] else ""
        print(f"  {r['label']:<30} {r['pnl']:>+8.2f}  {r['trades']:>7}  {r['wr']:>5.1f}%{marker}")
    print("=" * 60)
    print(f"\n  V6 baseline: +{r_v6['pnl']:.0f} USDT")
    best_v7 = max([r_v7_50, r_v7_55, r_v7_60], key=lambda x: x["pnl"])
    delta = best_v7["pnl"] - r_v6["pnl"]
    print(f"  Best V7:     +{best_v7['pnl']:.0f} USDT  ({delta:+.0f} vs V6) — {best_v7['label']}")
