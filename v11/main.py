"""
V11 — Bot de producción: BTC + ETH + SOL.

Novedades respecto a V10:
  1. SOL/USDT:USDT añadido como tercer par.
  2. EXCHANGE_MODE=quantfury — el Telegram incluye cuánto "poder de trading"
     usar en cada trade según tu depósito en QuantFury (QUANTFURY_DEPOSIT).
  3. EXCHANGE_MODE=bybit — ejecuta órdenes automáticamente via API (futuro).

Variables de entorno:
  BYBIT_API_KEY, BYBIT_API_SECRET
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
  STATE_DIR                — directorio de estado (default: ./data)

  EXCHANGE_MODE            — quantfury (default) | bybit
  QUANTFURY_DEPOSIT        — euros depositados en QuantFury (default: 100)
  QUANTFURY_RISK_PCT       — % del depósito a arriesgar por trade (default: 2)

  TRADING_HOURS_ENABLED    — true/false (default: false = opera 24h)
  TRADING_HOUR_START       — hora inicio Madrid (default: 8)
  TRADING_HOUR_END         — hora fin Madrid (default: 23)
  TRAILING_STEP_MULT       — 0.0–2.0 (default: 1.0)
  MAX_TP_EXTENSIONS        — 0, 1, 2… (default: 1)

Uso:
  python -m v11.main
  python -m v11.main --btc-only
  python -m v11.main --eth-only
  python -m v11.main --sol-only
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

import v6.core.bot_core as _bc
from v6.core.bot_core import RISK_PROFILES, run_live
from v6.main import _maybe_retrain
from v7.strategy_ml import StrategyML

try:
    from zoneinfo import ZoneInfo
    _MADRID_TZ = ZoneInfo("Europe/Madrid")
    def _now_madrid():
        return datetime.now(_MADRID_TZ)
except Exception:
    from datetime import timezone, timedelta
    _MADRID_TZ = timezone(timedelta(hours=2))
    def _now_madrid():
        return datetime.now(_MADRID_TZ)


MODEL_DIR = ROOT / "v7" / "models"
STATE_DIR = Path(os.getenv("STATE_DIR", str(ROOT / "data")))
STATE_DIR.mkdir(parents=True, exist_ok=True)

# ── Modo de exchange ───────────────────────────────────────────────────────────
EXCHANGE_MODE      = os.getenv("EXCHANGE_MODE", "quantfury").lower()
QUANTFURY_DEPOSIT  = float(os.getenv("QUANTFURY_DEPOSIT",  "100"))
QUANTFURY_RISK_PCT = float(os.getenv("QUANTFURY_RISK_PCT", "2"))

# ── Filtro de horas ────────────────────────────────────────────────────────────
TRADING_HOURS_ENABLED = os.getenv("TRADING_HOURS_ENABLED", "false").lower() == "true"
TRADING_HOUR_START    = int(os.getenv("TRADING_HOUR_START", "8"))
TRADING_HOUR_END      = int(os.getenv("TRADING_HOUR_END",   "23"))

# ── Trailing ───────────────────────────────────────────────────────────────────
TRAILING_STEP_MULT = float(os.getenv("TRAILING_STEP_MULT", "1.0"))
MAX_TP_EXTENSIONS  = int(os.getenv("MAX_TP_EXTENSIONS",    "1"))

V11_RISK = {
    "risk_pct":                0.02,
    "max_cost_pct":            0.35,
    "stop_loss_atr_mult":      2.5,
    "take_profit_atr_mult":    4.5,
    "min_score":               58,
    "entry_advantage":         15,
    "max_daily_trades":        6,
    "max_drawdown_pct":        0.10,
    "max_daily_loss_pct":      0.03,
    "trailing_stop":           True,
    "trailing_step_mult":      TRAILING_STEP_MULT,
    "max_tp_extensions":       MAX_TP_EXTENSIONS,
    "weekend_mode":            "range",
    "weekend_min_score_bonus": 10,
    "min_vol_ratio":           0.0,
}
RISK_PROFILE = V11_RISK


# ── Modo QuantFury: añade línea de sizing al Telegram de apertura ─────────────
def _quantfury_power_line(price: float, sl: float) -> str:
    """Calcula cuánto poder de trading usar en QuantFury para este trade."""
    sl_pct = abs(price - sl) / price
    if sl_pct <= 0:
        return ""
    risk_eur        = QUANTFURY_DEPOSIT * QUANTFURY_RISK_PCT / 100
    power_to_use    = risk_eur / sl_pct
    return (
        f"\n💶 <b>QuantFury</b>: usa <b>{power_to_use:,.0f}€</b> de poder\n"
        f"   ({risk_eur:.1f}€ en riesgo = {QUANTFURY_RISK_PCT}% de {QUANTFURY_DEPOSIT:.0f}€ depósito)"
    )

if EXCHANGE_MODE == "quantfury":
    _orig_tg_open = _bc._tg_open

    def _tg_open_qf(side, pair, price, sl, tp, score, atr,
                    trade_type="intraday", amount_usdt=0, balance=0):
        _orig_tg_open(side, pair, price, sl, tp, score, atr, trade_type, amount_usdt, balance)
        # Enviar línea de QuantFury como mensaje de seguimiento
        qf_line = _quantfury_power_line(price, sl)
        if qf_line:
            _bc.send_telegram(
                f"💶 <b>QuantFury sizing</b> — {side} {pair}\n"
                f"Poder a usar: <b>{abs(price-sl)/price and QUANTFURY_DEPOSIT*QUANTFURY_RISK_PCT/100/abs(price-sl)*price:,.0f}€</b>\n"
                f"Riesgo: {QUANTFURY_DEPOSIT*QUANTFURY_RISK_PCT/100:.1f}€ "
                f"({QUANTFURY_RISK_PCT}% de {QUANTFURY_DEPOSIT:.0f}€ depositados)\n"
                f"SL distancia: {abs(price-sl)/price*100:.2f}%"
            )

    _bc._tg_open = _tg_open_qf


def _is_trading_hours() -> bool:
    h = _now_madrid().hour
    return TRADING_HOUR_START <= h < TRADING_HOUR_END


class HoursFilterStrategy:
    def __init__(self, inner: StrategyML):
        self._inner       = inner
        self.timeframe    = inner.timeframe
        self.htf          = getattr(inner, "htf", None)
        self.feature_cols = inner.feature_cols

    def get_signal(self, df, live_extras, row=None):
        signal = self._inner.get_signal(df, live_extras, row=row)
        if TRADING_HOURS_ENABLED and not _is_trading_hours():
            signal.bull_score = 0
            signal.bear_score = 0
        return signal


def make_exchange():
    return ccxt.bybit({
        "apiKey":  os.getenv("BYBIT_API_KEY",    ""),
        "secret":  os.getenv("BYBIT_API_SECRET", ""),
        "options": {"defaultType": "linear"},
        "enableRateLimit": True,
    })


def make_strategy():
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        oos_meta = json.load(f)
    inner = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    inner.feature_cols = oos_meta["feature_cols"]
    return HoursFilterStrategy(inner)


def run_pair(pair: str, label: str):
    print(f"[{label}] V11 iniciando — {pair}")
    exchange = make_exchange()
    strategy = make_strategy()
    profile_name = f"v11_{pair.replace('/', '_').replace(':', '_')}"

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
    parser = argparse.ArgumentParser(description="V11 — Bot BTC+ETH+SOL")
    parser.add_argument("--btc-only", action="store_true")
    parser.add_argument("--eth-only", action="store_true")
    parser.add_argument("--sol-only", action="store_true")
    args = parser.parse_args()

    print("=" * 62)
    print("  V11 Trading Bot — Configuración activa")
    print("=" * 62)
    print(f"  Modo exchange     {EXCHANGE_MODE.upper()}")
    if EXCHANGE_MODE == "quantfury":
        print(f"  Depósito QF       {QUANTFURY_DEPOSIT:.0f}€  →  riesgo {QUANTFURY_RISK_PCT}%/trade = {QUANTFURY_DEPOSIT*QUANTFURY_RISK_PCT/100:.1f}€")
    if TRADING_HOURS_ENABLED:
        print(f"  Horario           {TRADING_HOUR_START:02d}:00 – {TRADING_HOUR_END:02d}:00 Madrid")
    else:
        print("  Horario           24h (sin filtro)")
    print(f"  Trailing step     {TRAILING_STEP_MULT}× ATR")
    print(f"  Máx TP ext.       {MAX_TP_EXTENSIONS}")
    print("=" * 62)
    print()
    print("  Variables de entorno disponibles:")
    print("    EXCHANGE_MODE          quantfury|bybit   (default: quantfury)")
    print("    QUANTFURY_DEPOSIT      euros depositados (default: 100)")
    print("    QUANTFURY_RISK_PCT     % riesgo/trade    (default: 2)")
    print("    TRADING_HOURS_ENABLED  true|false        (default: false)")
    print("    TRADING_HOUR_START     hora inicio       (default: 8)")
    print("    TRADING_HOUR_END       hora fin          (default: 23)")
    print("    TRAILING_STEP_MULT     0.0–2.0           (default: 1.0)")
    print("    MAX_TP_EXTENSIONS      0,1,2…            (default: 1)")
    print("=" * 62)

    if not (MODEL_DIR / "v7_classifier_oos.pkl").exists():
        print("ERROR: Modelo ML no encontrado.")
        sys.exit(1)

    _maybe_retrain()

    pairs = []
    if not args.eth_only and not args.sol_only:
        pairs.append(("BTC/USDT:USDT", "BTC"))
    if not args.btc_only and not args.sol_only:
        pairs.append(("ETH/USDT:USDT", "ETH"))
    if not args.btc_only and not args.eth_only:
        pairs.append(("SOL/USDT:USDT", "SOL"))

    if len(pairs) == 1:
        run_pair(*pairs[0])
    else:
        threads = []
        for pair, label in pairs:
            t = threading.Thread(target=run_pair, args=(pair, label), daemon=True, name=label)
            threads.append(t)
            t.start()
            time.sleep(5)

        print(f"\n  Pares activos: {[p[1] for p in pairs]}")
        print("  Ctrl+C para detener\n")

        try:
            while True:
                time.sleep(60)
                alive = [t.name for t in threads if t.is_alive()]
                if len(alive) < len(threads):
                    dead = [t.name for t in threads if not t.is_alive()]
                    print(f"  [WARN] Hilos caídos: {dead}. Revisar logs.")
        except KeyboardInterrupt:
            print("\n  Deteniendo V11...")


if __name__ == "__main__":
    main()
