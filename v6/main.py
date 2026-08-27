"""
main.py — Punto de entrada para los bots v6
============================================
Uso:
  python -m v6.main --pair BTC/USDT:USDT --strategy 15m --profile aggressive
  python -m v6.main --pair BTC/USDT:USDT --strategy 1h  --profile moderate
  python -m v6.main --pair BTC/USDT:USDT --strategy 15m --profile aggressive --backtest --days 180

Estrategias:
  15m — señales de momentum en 15m, filtro HTF 4h
  1h  — señales de tendencia en 1h,  filtro HTF 1D

Perfiles disponibles: moderate, aggressive
"""

import argparse
import ccxt
import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from v6.core.bot_core import RISK_PROFILES, run_live, run_backtest
from v6.strategies.strategy_15m import Strategy15m
from v6.strategies.strategy_1h  import Strategy1h

ROOT = Path(__file__).resolve().parents[1]
_RETRAIN_INTERVAL_DAYS = 180  # 6 meses


def _maybe_retrain():
    """
    Comprueba si el modelo tiene más de 6 meses. Si sí, lanza el
    reentrenamiento en segundo plano (no bloquea el bot).
    """
    meta_path = ROOT / "v7" / "models" / "v7_classifier_oos_meta.json"
    if not meta_path.exists():
        return

    try:
        with open(meta_path) as _mf:
            meta = json.load(_mf)
        trained_on = meta.get("trained_on", "")
        if not trained_on:
            return
        trained_date = datetime.strptime(trained_on, "%Y%m%d")
        age_days = (datetime.now() - trained_date).days
        if age_days < _RETRAIN_INTERVAL_DAYS:
            print(f"[AutoRetrain] Modelo tiene {age_days} días — no es necesario reentrenar aún "
                  f"(próximo en {_RETRAIN_INTERVAL_DAYS - age_days} días)")
            return

        print(f"[AutoRetrain] Modelo tiene {age_days} días (>{_RETRAIN_INTERVAL_DAYS}). "
              f"Lanzando reentrenamiento en segundo plano...")

        def _run():
            result = subprocess.run(
                ["python", str(ROOT / "v8" / "retrain_model.py"),
                 "--train-months", "24", "--holdout-months", "6"],
                capture_output=True, text=True, cwd=str(ROOT)
            )
            if result.returncode == 0:
                print("[AutoRetrain] ✓ Reentrenamiento completado.")
                print(result.stdout[-500:] if result.stdout else "")
            else:
                print("[AutoRetrain] ✗ Error en reentrenamiento:")
                print(result.stderr[-300:] if result.stderr else "")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    except Exception as e:
        print(f"[AutoRetrain] Error al verificar modelo: {e}")

STRATEGIES = {
    "15m": Strategy15m,
    "1h":  Strategy1h,
}

MIN_HOLD_CANDLES = {
    "15m": 3,   # mínimo 45min en posición
    "1h":  4,   # mínimo 4h en posición
}


def main():
    parser = argparse.ArgumentParser(description="Trading bot v6")
    parser.add_argument("--pair",     required=True, help="Par, ej: BTC/USDT:USDT")
    parser.add_argument("--strategy", required=True, choices=STRATEGIES.keys())
    parser.add_argument("--profile",  required=True, choices=RISK_PROFILES.keys())
    parser.add_argument("--backtest", action="store_true", help="Modo backtest")
    parser.add_argument("--days",     type=int, default=180, help="Días de backtest")
    parser.add_argument("--silent",   action="store_true", help="Sin Telegram")
    args = parser.parse_args()

    # Silenciar Telegram en backtest o si se pasa --silent
    if args.silent or args.backtest:
        os.environ["TELEGRAM_SILENT"] = "1"
        import v6.core.bot_core as _bc
        _bc.TELEGRAM_SILENT = True

    api_key    = os.getenv("BYBIT_API_KEY",    "")
    api_secret = os.getenv("BYBIT_API_SECRET", "")
    exchange   = ccxt.bybit({
        "apiKey":  api_key,
        "secret":  api_secret,
        "options": {"defaultType": "linear"},
    })

    strategy     = STRATEGIES[args.strategy]()
    risk_profile = RISK_PROFILES[args.profile]
    min_hold     = MIN_HOLD_CANDLES[args.strategy]
    profile_name = f"{args.pair}_{args.strategy}_{args.profile}"

    # Auto-reentrenamiento: comprueba si el modelo necesita actualizarse
    if not args.backtest:
        _maybe_retrain()

    if args.backtest:
        run_backtest(
            exchange         = exchange,
            pair             = args.pair,
            days             = args.days,
            risk_profile     = risk_profile,
            strategy         = strategy,
            min_hold_candles = min_hold,
        )
    else:
        _tf_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(strategy.timeframe, 900)
        run_live(
            exchange         = exchange,
            pair             = args.pair,
            interval         = _tf_seconds,
            risk_profile     = risk_profile,
            strategy         = strategy,
            min_hold_candles = min_hold,
            profile_name     = profile_name,
        )


if __name__ == "__main__":
    main()
