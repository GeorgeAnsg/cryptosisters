"""Descarga velas SOL/USDT:USDT 15m desde Bybit y guarda en data/sol_15m_full.csv"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ccxt
import pandas as pd

exchange = ccxt.bybit({"options": {"defaultType": "linear"}, "enableRateLimit": True})

pair     = "SOL/USDT:USDT"
tf       = "15m"
since    = exchange.parse8601("2022-01-01T00:00:00Z")
out_file = ROOT / "data" / "sol_15m_full.csv"

print(f"Descargando {pair} {tf} desde 2022-01-01...")
all_ohlcv = []
while True:
    batch = exchange.fetch_ohlcv(pair, tf, since=since, limit=1000)
    if not batch:
        break
    all_ohlcv += batch
    since = batch[-1][0] + 1
    last_ts = pd.Timestamp(batch[-1][0], unit="ms")
    print(f"  {last_ts.date()} — {len(all_ohlcv):,} velas", end="\r")
    if last_ts >= pd.Timestamp.now() - pd.Timedelta(minutes=15):
        break
    time.sleep(exchange.rateLimit / 1000)

df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
df.drop_duplicates("timestamp", inplace=True)
df.sort_values("timestamp", inplace=True)
df.to_csv(out_file, index=False)
print(f"\nGuardado: {out_file} ({len(df):,} velas, {df['timestamp'].min().date()} → {df['timestamp'].max().date()})")
