"""
backtest_periods.py — Backtest por períodos de mercado
Uso:
    python -m v6.tools.backtest_periods --pair BTC/USDT:USDT --strategy 15m --profile moderate
    python -m v6.tools.backtest_periods ... --layer1     # Layer 1 aislado
    python -m v6.tools.backtest_periods ... --layer3     # Layer 1+2+3 completo
"""
import argparse
import sys
from pathlib import Path

import ccxt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from v6.core.bot_core import RISK_PROFILES, run_backtest, Signal
from v6.core.bot_indicators import precompute_indicators, analyze_layer1, detect_regime_auto
from v6.core.bot_risk import calculate_scores
from v6.core.bot_layer3 import get_layer3_extras
from v6.strategies.strategy_15m import Strategy15m
from v6.strategies.strategy_1h import Strategy1h

STRATEGIES = {"15m": Strategy15m, "1h": Strategy1h}


class _Strategy15mL3(Strategy15m):
    """L1+2 completo + Layer 3 real (F&G + funding rate + halving cycle).
    En cada vela lee el timestamp y resuelve los extras de L3 desde los CSVs históricos."""

    def get_signal(self, df_ltf, live_extras, row=None):
        _row = row if row is not None else df_ltf.iloc[-1]
        ts   = _row.get("timestamp") if hasattr(_row, "get") else getattr(_row, "timestamp", None)
        if ts is not None and hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if ts is not None:
            live_extras = get_layer3_extras(ts)
        return super().get_signal(df_ltf, live_extras, row=row)


class _Strategy15mL1Only(Strategy15m):
    """Variante que usa analyze_layer1 (sin HTF veto, sin patrones 1h) pero CON régimen.
    Esto permite una comparación justa con la estrategia completa (Layer 1+2)."""
    def get_signal(self, df_ltf, live_extras, row=None):
        _row = row if row is not None else df_ltf.iloc[-1]
        prev_row = df_ltf.iloc[-2] if len(df_ltf) >= 2 else _row
        tech   = analyze_layer1(_row, prev_row)
        regime = detect_regime_auto(_row)
        scores = calculate_scores(
            technical  = tech,
            sentiment  = live_extras.get("sentiment",  {"bullish_score": 0, "bearish_score": 0}),
            fear_greed = live_extras.get("fear_greed", {"bull_mod": 5, "bear_mod": 5}),
            funding    = live_extras.get("funding",    {"bull_mod": 3, "bear_mod": 3}),
            orderbook  = live_extras.get("orderbook",  {"bull_mod": 0, "bear_mod": 0}),
            macro_corr = live_extras.get("macro_corr", {"bull_mod": 0, "bear_mod": 0}),
            oi         = live_extras.get("oi",         {"bull_mod": 3, "bear_mod": 3}),
        )
        return Signal(
            bull_score       = scores["bullish_total"],
            bear_score       = scores["bearish_total"],
            technical        = tech,
            regime           = regime,
            htf_blocks_long  = False,  # sin veto HTF — solo Layer 1
            htf_blocks_short = False,
        )

PERIODS = [
    ("Sep-Nov 2021",  "Bull final",    "2021-09-01", "2021-11-30"),
    ("2022",          "Bear duro",     "2022-01-01", "2022-12-31"),
    ("2023",          "Acumulación",   "2023-01-01", "2023-12-31"),
    ("Oct23-Mar24",   "Bull run",      "2023-10-01", "2024-03-31"),
    ("Ene-May 2025",  "Corrección",    "2025-01-01", "2025-05-31"),
    ("Jun25-Ago26",   "Recuperación",  "2025-06-01", "2026-08-26"),
]

CSV_MAP = {
    ("BTC/USDT:USDT", "15m"): ROOT / "data" / "btc_15m_full.csv",
    ("BTC/USDT:USDT", "1h"):  ROOT / "data" / "btc_1h_full.csv",
    ("ETH/USDT:USDT", "15m"): ROOT / "data" / "eth_2023_2026.csv",
    ("ETH/USDT:USDT", "1h"):  ROOT / "data" / "eth_1h_2023_2026.csv",
    ("XRP/USDT:USDT", "15m"): ROOT / "data" / "xrp_15m_full.csv",
    ("XRP/USDT:USDT", "1h"):  ROOT / "data" / "xrp_1h_full.csv",
    ("HYPE/USDT:USDT","15m"): ROOT / "data" / "hype_15m_full.csv",
    ("HYPE/USDT:USDT","1h"):  ROOT / "data" / "hype_1h_full.csv",
}

WARMUP_CANDLES = {"15m": 600, "1h": 300}  # velas de calentamiento antes del período


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair",     default="BTC/USDT:USDT")
    parser.add_argument("--strategy", default="15m", choices=STRATEGIES.keys())
    parser.add_argument("--profile",  default="moderate", choices=RISK_PROFILES.keys())
    parser.add_argument("--layer1",   action="store_true", help="Usar analyze_layer1 (sin HTF)")
    parser.add_argument("--layer3",   action="store_true", help="Activar señales L3: F&G + funding + halving")
    args = parser.parse_args()

    exchange = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "linear"}})
    if args.layer1:
        strategy = _Strategy15mL1Only()
        print("Modo: Layer 1 aislado (sin HTF veto, sin patrones 1h)")
    elif args.layer3:
        strategy = _Strategy15mL3()
        print("Modo: L1+2+3 completo (F&G + funding rate + halving cycle)")
    else:
        strategy = STRATEGIES[args.strategy]()
        print("Modo: L1+2 completo (sin Layer 3)")
    risk_profile = RISK_PROFILES[args.profile]

    csv_path = CSV_MAP.get((args.pair, args.strategy))
    if not csv_path or not csv_path.exists():
        print(f"[ERROR] No se encuentra CSV para {args.pair} {args.strategy}: {csv_path}")
        sys.exit(1)

    print(f"Cargando {csv_path.name}...", end=" ", flush=True)
    df_raw = pd.read_csv(csv_path, parse_dates=["timestamp"])
    print(f"{len(df_raw):,} velas")

    print("Precalculando indicadores (una sola vez)...", end=" ", flush=True)
    df_full = precompute_indicators(df_raw)
    print("OK")

    warmup = WARMUP_CANDLES[args.strategy]

    print()
    print(f"{'Período':<15} {'Mercado':<15} {'PnL':>12} {'%':>7} {'WR':>6} {'Trades':>7} {'DD':>6}")
    print("-" * 70)

    for label, market, start, end in PERIODS:
        # Incluir velas de calentamiento antes del período para que los indicadores estén calientes
        start_ts = pd.Timestamp(start)
        end_ts   = pd.Timestamp(end) + pd.Timedelta(days=1)

        # Buscar índice del inicio del período en el df completo
        mask_period = (df_full["timestamp"] >= start_ts) & (df_full["timestamp"] < end_ts)
        idx_start   = df_full.index[mask_period].min() if mask_period.any() else None

        if idx_start is None:
            print(f"{'  ' + label:<15} {'  ' + market:<15} {'N/D':>12}")
            continue

        # Incluir warmup antes del período para no empezar con NaNs
        idx_slice_start = max(0, idx_start - warmup)
        df_period = df_full.iloc[idx_slice_start:].copy()
        df_period = df_period[df_period["timestamp"] < end_ts].reset_index(drop=True)

        if len(df_period) < warmup + 10:
            print(f"{'  ' + label:<15} {'  ' + market:<15} {'Datos insuf.':>12}")
            continue

        result = run_backtest(
            exchange         = exchange,
            pair             = args.pair,
            days             = 0,
            risk_profile     = risk_profile,
            strategy         = strategy,
            min_hold_candles = 3 if args.strategy == "15m" else 4,
            _df_override     = df_period,
        )

        stats   = result["stats"]
        pnl     = stats["total_pnl"]
        pct     = pnl / 1000 * 100
        total_t = stats["wins"] + stats["losses"]
        wr      = stats["wins"] / total_t * 100 if total_t else 0
        dd      = result["max_drawdown_seen"]

        sign = "+" if pnl >= 0 else ""
        print(f"{label:<15} {market:<15} {sign}{pnl:>8.0f} USDT {sign}{pct:>5.1f}% {wr:>5.1f}% {total_t:>7} {dd:>5.1f}%")

    print()


if __name__ == "__main__":
    main()
