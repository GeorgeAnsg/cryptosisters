"""
Runner: export V6 trade features using local 15m data.
Run from project root: python v7/run_export.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from v6.core.bot_indicators import precompute_indicators
from v6.strategies.strategy_15m import Strategy15m
from v7.export_trade_features import run_backtest_export, save_csv, RISK_PROFILE, OUT_PATH

LOCAL_CSV  = ROOT / "data" / "btc_15m_full.csv"
START_DATE = "2023-01-01"

print(f"[V7 Export] Loading {LOCAL_CSV.name}...")
df = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
df = df[df["timestamp"] >= START_DATE].reset_index(drop=True)
print(f"  {len(df):,} candles ({df['timestamp'].iloc[0].date()} → {df['timestamp'].iloc[-1].date()})")

print("  Precomputing indicators (this takes ~30s)...")
df = precompute_indicators(df)

strategy = Strategy15m()
print("\n  Running backtest loop with feature capture...\n")

trades = run_backtest_export(
    exchange     = None,
    pair         = "BTC/USDT:USDT",
    risk_profile = RISK_PROFILE,
    strategy     = strategy,
    start_date   = START_DATE,
    df_override  = df,
)

save_csv(trades, OUT_PATH)

if trades:
    import statistics
    pnls = [t["pnl"] for t in trades]
    wr   = sum(1 for t in trades if t["won"]) / len(trades) * 100
    print(f"\n[V7 Export] Summary:")
    print(f"  Trades:     {len(trades)}")
    print(f"  Win rate:   {wr:.1f}%")
    print(f"  Total PnL:  {sum(pnls):+.2f} USDT")
    print(f"  Features:   39 columns")
    print(f"\n  Next: run v7/shap_analysis.py")
