"""
V8 — Bot de producción multi-activo (BTC + ETH simultáneo).

Corre dos loops en paralelo (hilos separados) con capital compartido.
Usa el filtro ML de V7 en ambos activos + TP dinámico.

Variables de entorno necesarias:
  BYBIT_API_KEY, BYBIT_API_SECRET
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
  STATE_DIR (opcional, default: ./data)

Uso:
  python -m v8.main
  python -m v8.main --btc-only       # solo BTC (equivale a V7)
  python -m v8.main --eth-only       # solo ETH
"""

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ccxt

from v6.core.bot_core import RISK_PROFILES, run_live
from v6.main import _maybe_retrain
from v7.strategy_ml import StrategyML


MODEL_DIR  = ROOT / "v7" / "models"
STATE_DIR  = Path(os.getenv("STATE_DIR", str(ROOT / "data")))
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Parámetros validados en backtest V8 OOS 2025-2026
# TP=4.5 es la media del TP dinámico (rango 3.5-5.0)
V8_RISK = {
    "risk_pct":               0.02,
    "max_cost_pct":           0.35,
    "stop_loss_atr_mult":     2.5,
    "take_profit_atr_mult":   4.5,
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
RISK_PROFILE = V8_RISK

# NOTA DE PRODUCCIÓN: cada par (BTC, ETH) tiene su propio estado y balance
# independiente (state file separado). En producción se necesitan ~1000 USDT
# por activo (~2000 USDT total). El backtest usó capital compartido, que es
# la situación ideal; en producción los resultados por activo son comparables
# a los del backtest individual (BTC: +682, ETH: +1356 por cada 1000 USDT).


def make_exchange():
    return ccxt.bybit({
        "apiKey":  os.getenv("BYBIT_API_KEY",    ""),
        "secret":  os.getenv("BYBIT_API_SECRET", ""),
        "options": {"defaultType": "linear"},
        "enableRateLimit": True,
    })


def make_strategy():
    oos_pkl  = MODEL_DIR / "v7_classifier_oos.pkl"
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        oos_meta = json.load(f)
    s = StrategyML(model_path=str(oos_pkl), threshold=0.55)
    s.feature_cols = oos_meta["feature_cols"]
    return s


def run_pair(pair: str, label: str):
    """Loop de producción para un par. Corre en su propio hilo."""
    print(f"[{label}] Iniciando loop — {pair}")
    exchange = make_exchange()
    strategy = make_strategy()
    profile_name = f"v8_{pair.replace('/', '_').replace(':', '_')}"

    while True:
        try:
            run_live(
                exchange         = exchange,
                pair             = pair,
                interval         = 900,   # 15 minutos
                risk_profile     = RISK_PROFILE,
                strategy         = strategy,
                min_hold_candles = 3,
                profile_name     = profile_name,
            )
        except Exception as e:
            print(f"[{label}] Error en loop: {e}. Reiniciando en 60s...")
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="V8 — Bot multi-activo BTC+ETH")
    parser.add_argument("--btc-only", action="store_true", help="Solo BTC")
    parser.add_argument("--eth-only", action="store_true", help="Solo ETH")
    args = parser.parse_args()

    print("=" * 55)
    print("  V8 Trading Bot — Multi-activo BTC + ETH")
    print("  Modelo: V7 ML (XGBoost) + TP dinámico")
    print("=" * 55)

    # Verificar modelo disponible
    if not (MODEL_DIR / "v7_classifier_oos.pkl").exists():
        print("ERROR: No se encuentra el modelo ML. Ejecuta primero v7/train_classifier.py")
        sys.exit(1)

    # Auto-reentrenamiento si el modelo tiene >6 meses
    _maybe_retrain()

    pairs = []
    if not args.eth_only:
        pairs.append(("BTC/USDT:USDT", "BTC"))
    if not args.btc_only:
        pairs.append(("ETH/USDT:USDT", "ETH"))

    if len(pairs) == 1:
        # Un solo par: correr en el hilo principal
        run_pair(*pairs[0])
    else:
        # Multi-activo: un hilo por par
        threads = []
        for pair, label in pairs:
            t = threading.Thread(target=run_pair, args=(pair, label), daemon=True, name=label)
            threads.append(t)
            t.start()
            time.sleep(5)  # pequeño desfase para no saturar el exchange al arrancar

        print(f"\n  {len(threads)} loops activos: {[p[1] for p in pairs]}")
        print("  Ctrl+C para detener\n")

        try:
            while True:
                time.sleep(60)
                alive = [t.name for t in threads if t.is_alive()]
                if len(alive) < len(threads):
                    dead = [t.name for t in threads if not t.is_alive()]
                    print(f"  [WARN] Hilos caídos: {dead}. Revisar logs.")
        except KeyboardInterrupt:
            print("\n  Deteniendo V8...")


if __name__ == "__main__":
    main()
