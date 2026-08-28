"""
V10 — Bot de producción para ejecución manual (BTC + ETH).

Diferencias respecto a V8:
  1. SL/TP fijos al abrir posición — sin trailing stop, sin extensiones de TP.
     El usuario coloca la orden en QuantFury una vez y no la toca hasta el cierre.
  2. Filtro de horas — solo abre posiciones dentro del horario configurado
     (por defecto 08:00-23:00 hora Madrid). Fuera de ese horario analiza
     el mercado pero no genera señales nuevas.

Variables de entorno:
  BYBIT_API_KEY, BYBIT_API_SECRET
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
  STATE_DIR                — directorio de estado (default: ./data)
  TRADING_HOUR_START       — hora inicio en Madrid (default: 8)
  TRADING_HOUR_END         — hora fin en Madrid (default: 23)

Uso:
  python -m v10.main
  python -m v10.main --btc-only
  python -m v10.main --eth-only
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ccxt

from v6.core.bot_core import RISK_PROFILES, run_live
from v6.main import _maybe_retrain
from v7.strategy_ml import StrategyML

try:
    from zoneinfo import ZoneInfo
    _MADRID_TZ = ZoneInfo("Europe/Madrid")
    def _now_madrid():
        return datetime.now(_MADRID_TZ)
except Exception:
    # Fallback si tzdata no está instalado: usa UTC+2 fijo
    from datetime import timezone, timedelta
    _MADRID_TZ = timezone(timedelta(hours=2))
    def _now_madrid():
        return datetime.now(_MADRID_TZ)


MODEL_DIR = ROOT / "v7" / "models"
STATE_DIR = Path(os.getenv("STATE_DIR", str(ROOT / "data")))
STATE_DIR.mkdir(parents=True, exist_ok=True)

TRADING_HOUR_START = int(os.getenv("TRADING_HOUR_START", "8"))
TRADING_HOUR_END   = int(os.getenv("TRADING_HOUR_END",   "23"))

# Parámetros V10: trailing suavizado (1-2 avisos/trade) + 1 extensión TP
# trailing_step_mult=1.0 → el SL solo se mueve cuando mejora ≥1× distancia
# inicial (≈1 ATR). Eso reduce los avisos de 5+ a 1-2 por trade.
V10_RISK = {
    "risk_pct":                0.02,
    "max_cost_pct":            0.35,
    "stop_loss_atr_mult":      2.5,
    "take_profit_atr_mult":    4.5,
    "min_score":               58,
    "entry_advantage":         15,
    "max_daily_trades":        6,
    "max_drawdown_pct":        0.10,
    "max_daily_loss_pct":      0.03,
    "trailing_stop":           True,    # ← activo pero con paso grande
    "trailing_step_mult":      1.0,     # ← mueve SL solo si mejora ≥1× ATR
    "max_tp_extensions":       1,       # ← máximo 1 extensión de TP
    "weekend_mode":            "range",
    "weekend_min_score_bonus": 10,
    "min_vol_ratio":           0.0,
}
RISK_PROFILE = V10_RISK


def _is_trading_hours() -> bool:
    """True si la hora actual en Madrid está dentro del horario permitido."""
    h = _now_madrid().hour
    return TRADING_HOUR_START <= h < TRADING_HOUR_END


class HoursFilterStrategy:
    """
    Wrapper sobre StrategyML que devuelve señal neutra fuera del horario
    de trading, evitando que el bot abra posiciones nuevas.
    Las posiciones ya abiertas siguen gestionadas (check_sl_tp no usa la señal).
    """

    def __init__(self, inner: StrategyML):
        self._inner = inner
        # Reexponer atributos que bot_core necesita
        self.timeframe    = inner.timeframe
        self.htf          = getattr(inner, "htf", None)
        self.feature_cols = inner.feature_cols

    def get_signal(self, df, live_extras, row=None):
        signal = self._inner.get_signal(df, live_extras, row=row)
        if not _is_trading_hours():
            # Anular scores para que make_decision no abra posición nueva
            signal.bull_score = 0
            signal.bear_score = 0
            # Mantener el regime para que apply_regime funcione
        return signal


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
    inner = StrategyML(model_path=str(oos_pkl), threshold=0.55)
    inner.feature_cols = oos_meta["feature_cols"]
    return HoursFilterStrategy(inner)


def run_pair(pair: str, label: str):
    """Loop de producción para un par."""
    print(f"[{label}] V10 iniciando — {pair}")
    print(f"[{label}] Horario: {TRADING_HOUR_START:02d}:00-{TRADING_HOUR_END:02d}:00 Madrid | "
          f"trailing_step=1.0×ATR | max_tp_ext=1")
    exchange = make_exchange()
    strategy = make_strategy()
    profile_name = f"v10_{pair.replace('/', '_').replace(':', '_')}"

    while True:
        try:
            run_live(
                exchange         = exchange,
                pair             = pair,
                interval         = 900,
                risk_profile     = RISK_PROFILE,
                strategy         = strategy,
                min_hold_candles = 3,
                profile_name     = profile_name,
            )
        except Exception as e:
            print(f"[{label}] Error: {e}. Reiniciando en 60s...")
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="V10 — Bot manual BTC+ETH")
    parser.add_argument("--btc-only", action="store_true")
    parser.add_argument("--eth-only", action="store_true")
    args = parser.parse_args()

    print("=" * 55)
    print("  V10 Trading Bot — Ejecución manual QuantFury")
    print(f"  Horario: {TRADING_HOUR_START:02d}:00-{TRADING_HOUR_END:02d}:00 Madrid")
    print("  Trailing suavizado (≥1 ATR) | Máx 1 extensión TP")
    print("=" * 55)

    if not (MODEL_DIR / "v7_classifier_oos.pkl").exists():
        print("ERROR: Modelo ML no encontrado. Ejecuta v7/train_classifier.py primero.")
        sys.exit(1)

    _maybe_retrain()

    pairs = []
    if not args.eth_only:
        pairs.append(("BTC/USDT:USDT", "BTC"))
    if not args.btc_only:
        pairs.append(("ETH/USDT:USDT", "ETH"))

    if len(pairs) == 1:
        run_pair(*pairs[0])
    else:
        threads = []
        for pair, label in pairs:
            t = threading.Thread(target=run_pair, args=(pair, label), daemon=True, name=label)
            threads.append(t)
            t.start()
            time.sleep(5)

        print(f"\n  {len(threads)} pares activos: {[p[1] for p in pairs]}")
        print("  Ctrl+C para detener\n")

        try:
            while True:
                time.sleep(60)
                alive = [t.name for t in threads if t.is_alive()]
                if len(alive) < len(threads):
                    dead = [t.name for t in threads if not t.is_alive()]
                    print(f"  [WARN] Hilos caídos: {dead}. Revisar logs.")
        except KeyboardInterrupt:
            print("\n  Deteniendo V10...")


if __name__ == "__main__":
    main()
