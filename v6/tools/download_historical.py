"""
Descarga datos históricos de OHLCV para un período específico.
Uso:
    python3 download_historical.py --pair BTC/USDT --from 2023-10-01 --to 2024-03-31 --out bull_2023_2024.csv
    python3 download_historical.py --pair BTC/USDT --from 2025-08-01 --to 2026-08-25 --out bear_2025_2026.csv
"""
import ccxt
import pandas as pd
import argparse
from datetime import datetime, timezone

def download(pair: str, start: str, end: str, timeframe: str, out: str):
    exchange = ccxt.bybit({"enableRateLimit": True})
    since = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    all_rows = []
    limit = 1000
    print(f"Descargando {pair} {timeframe} desde {start} hasta {end}...")

    while since < end_ts:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        all_rows.extend(ohlcv)
        since = ohlcv[-1][0] + 1
        print(f"  {len(all_rows)} velas descargadas...", end="\r")

    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
    df = df[df["timestamp"] <= pd.Timestamp(end)]
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    df.to_csv(out, index=False)
    print(f"\nGuardado: {out} ({len(df)} velas, {df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair",      default="BTC/USDT")
    parser.add_argument("--from",     dest="start", required=True)
    parser.add_argument("--to",       dest="end",   required=True)
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--out",      required=True)
    args = parser.parse_args()
    download(args.pair, args.start, args.end, args.timeframe, args.out)
