"""
Genera winrate_{slug}.json para cada perfil ejecutando backtest en bull_2023_2024.csv.
Usar antes de desplegar a producción para que el bot tenga datos históricos desde el día 1.

Uso:
    venv/bin/python3 build_winrate.py
"""
import sys, json
import pandas as pd
import ccxt
sys.path.insert(0, ".")
import trading_bot_v5 as bot

BULL_DATA = "bull_2023_2024.csv"

CONFIGS = [
    {
        "slug":    "BTC_USDT_aggressive",
        "profile": "aggressive",
        "ms":      45,
        "ea":      25,
        "sl":      2.0,
        "tp":      4.0,
    },
    {
        "slug":    "BTC_USDT_moderate",
        "profile": "moderate",
        "ms":      50,
        "ea":      25,
        "sl":      1.5,
        "tp":      3.0,
    },
]


def main():
    exchange = ccxt.bybit({})

    print(f"Pre-cargando {BULL_DATA} ...", flush=True)
    df_raw = pd.read_csv(BULL_DATA, parse_dates=["timestamp"])
    df_pre = bot.precompute_indicators(df_raw)
    print(f"  {len(df_pre)} velas pre-calculadas.", flush=True)

    daily_macro_corr = {}
    if bot.MACRO_CORR_ENABLED and not df_pre.empty:
        start_str = str(df_pre["timestamp"].iloc[0].date())
        end_str   = str(df_pre["timestamp"].iloc[-1].date())
        print(f"Descargando macro {start_str} → {end_str} ...", flush=True)
        daily_macro_corr = bot.load_macro_correlations_historical(start_str, end_str)
        print(f"  {len(daily_macro_corr)} días de macro.", flush=True)

    for cfg in CONFIGS:
        print(f"\n{'='*60}")
        print(f"  {cfg['slug']}  —  MS={cfg['ms']} EA={cfg['ea']} SL={cfg['sl']} TP={cfg['tp']}")
        print(f"{'='*60}")

        rp = bot.RISK_PROFILES[cfg["profile"]].copy()
        rp["min_score"]            = cfg["ms"]
        rp["stop_loss_atr_mult"]   = cfg["sl"]
        rp["take_profit_atr_mult"] = cfg["tp"]
        rp = bot.apply_regime(rp, "neutral")

        state = bot.run_backtest(
            exchange, "BTC/USDT", "15m", 365,
            rp, cfg["ea"], None, 2,
            _df_override=df_pre,
            auto_regime=True,
            _daily_macro_corr=daily_macro_corr,
        )

        close_trades = [t for t in state["trades"] if t["action"].startswith("CLOSE_")]
        print(f"  Trades cerrados: {len(close_trades)}", flush=True)

        table = bot.build_winrate_table(close_trades, min_trades=5)
        print(f"  Buckets en la tabla: {len(table)}", flush=True)
        for k, v in sorted(table.items()):
            print(f"    {k}: WR={v['wr']:.1%}  n={v['n']}")

        out_path = f"winrate_{cfg['slug']}.json"
        bot.save_winrate_table(table, out_path)
        print(f"  ✅ Guardado: {out_path}", flush=True)

    print("\n✅ Win-rate tables generadas. Copiar al contenedor junto con trading_bot_v5.py.")


if __name__ == "__main__":
    main()
