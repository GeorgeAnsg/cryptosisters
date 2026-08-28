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
RISK_PROFILE_NAME  = os.getenv("RISK_PROFILE", "agresivo").lower()

# Perfiles de riesgo: (score_min, risk_pct, max_cost_pct)
_RISK_PROFILES = {
    "conservador": {
        "tiers":          [(0, 0.02, 0.35)],
        "qf_options":     [(2, "🟢")],
        "max_drawdown":   0.10,
    },
    "moderado": {
        "tiers":          [(75, 0.07, 1.0), (65, 0.05, 0.87), (0, 0.03, 0.52)],
        "qf_options":     [(3, "🟡"), (5, "🟠"), (7, "🔴")],
        "max_drawdown":   0.15,
    },
    "agresivo": {
        "tiers":          [(75, 0.12, 1.0), (65, 0.08, 1.0), (0, 0.05, 0.87)],
        "qf_options":     [(5, "🟡"), (8, "🟠"), (12, "🔴")],
        "max_drawdown":   0.25,
    },
}
_ACTIVE_PROFILE = _RISK_PROFILES.get(RISK_PROFILE_NAME, _RISK_PROFILES["agresivo"])

# ── Filtro de horas ────────────────────────────────────────────────────────────
TRADING_HOURS_ENABLED = os.getenv("TRADING_HOURS_ENABLED", "false").lower() == "true"
TRADING_HOUR_START    = int(os.getenv("TRADING_HOUR_START", "8"))
TRADING_HOUR_END      = int(os.getenv("TRADING_HOUR_END",   "23"))

# ── Trailing ───────────────────────────────────────────────────────────────────
TRAILING_STEP_MULT = float(os.getenv("TRAILING_STEP_MULT", "1.0"))
MAX_TP_EXTENSIONS  = int(os.getenv("MAX_TP_EXTENSIONS",    "1"))

def _tier_for_score(score: float) -> tuple:
    """Devuelve (risk_pct, max_cost_pct) del perfil activo según el score."""
    for min_score, risk, cap in _ACTIVE_PROFILE["tiers"]:
        if score >= min_score:
            return risk, cap
    return _ACTIVE_PROFILE["tiers"][-1][1], _ACTIVE_PROFILE["tiers"][-1][2]


V11_RISK = {
    "risk_pct":                _ACTIVE_PROFILE["tiers"][-1][1],
    "max_cost_pct":            _ACTIVE_PROFILE["tiers"][-1][2],
    "stop_loss_atr_mult":      2.5,
    "take_profit_atr_mult":    4.5,
    "min_score":               58,
    "entry_advantage":         15,
    "max_daily_trades":        6,
    "max_drawdown_pct":        _ACTIVE_PROFILE["max_drawdown"],
    "max_daily_loss_pct":      0.03,
    "trailing_stop":           True,
    "trailing_step_mult":      TRAILING_STEP_MULT,
    "max_tp_extensions":       MAX_TP_EXTENSIONS,
    "weekend_mode":            "range",
    "weekend_min_score_bonus": 10,
    "min_vol_ratio":           0.0,
}
RISK_PROFILE = V11_RISK


# ── Modo QuantFury: añade opciones de sizing al Telegram de apertura ──────────
def _quantfury_sizing_msg(side: str, pair: str, price: float, sl: float, tp: float, score: float) -> str:
    """Genera mensaje con opciones de riesgo del perfil activo + recomendación por score."""
    sl_pct = abs(price - sl) / price
    if sl_pct <= 0:
        return ""

    options = _ACTIVE_PROFILE["qf_options"]
    tiers   = _ACTIVE_PROFILE["tiers"]

    # Recomendación: tier más alto que el score alcanza
    recommended_risk = tiers[-1][1]  # fallback: tier más bajo
    for min_score, risk, _ in tiers:
        if score >= min_score:
            recommended_risk = risk
            break

    recommended_pct = int(recommended_risk * 100)
    if score >= 75:
        rec_reason = f"señal muy fuerte (score {score:.0f})"
    elif score >= 65:
        rec_reason = f"señal sólida (score {score:.0f})"
    else:
        rec_reason = f"señal moderada (score {score:.0f})"

    rr = abs(tp - price) / abs(price - sl) if abs(price - sl) > 0 else 0

    profile_label = RISK_PROFILE_NAME.capitalize()
    lines = [
        f"💶 <b>QuantFury sizing</b> [{profile_label}] — {side.upper()} {pair}",
        f"SL distancia: {sl_pct*100:.2f}%  |  R/R: {rr:.1f}x\n",
    ]
    for risk_pct, emoji in options:
        risk_eur = QUANTFURY_DEPOSIT * risk_pct / 100
        power    = risk_eur / sl_pct
        tag = "  ← <b>recomendado</b>" if risk_pct == recommended_pct else ""
        lines.append(f"{emoji} <b>{risk_pct}% riesgo</b>: {power:,.0f}€ poder  ({risk_eur:.1f}€ en juego){tag}")
    lines.append(f"\n💡 {rec_reason}")
    return "\n".join(lines)

if EXCHANGE_MODE == "quantfury":
    _orig_tg_open = _bc._tg_open

    def _tg_open_qf(side, pair, price, sl, tp, score, atr,
                    trade_type="intraday", amount_usdt=0, balance=0):
        _orig_tg_open(side, pair, price, sl, tp, score, atr, trade_type, amount_usdt, balance)
        msg = _quantfury_sizing_msg(side, pair, price, sl, tp, score)
        if msg:
            _bc.send_telegram(msg)

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

    tiers   = _ACTIVE_PROFILE["tiers"]
    options = _ACTIVE_PROFILE["qf_options"]
    tier_str = "/".join(f"{int(r*100)}%" for _, r, _ in reversed(tiers))

    print("=" * 62)
    print("  V11 Trading Bot — Configuración activa")
    print("=" * 62)
    print(f"  Modo exchange     {EXCHANGE_MODE.upper()}")
    if EXCHANGE_MODE == "quantfury":
        print(f"  Depósito QF       {QUANTFURY_DEPOSIT:.0f}€")
    print(f"  Perfil de riesgo  {RISK_PROFILE_NAME.upper()}")
    print(f"    Riesgo/trade    {tier_str} (por score de señal)")
    print(f"    Max drawdown    {int(_ACTIVE_PROFILE['max_drawdown']*100)}%")
    opt_str = "  /  ".join(f"{r}% ({e})" for r, e in options)
    print(f"    Opciones QF     {opt_str}")
    if TRADING_HOURS_ENABLED:
        print(f"  Horario           {TRADING_HOUR_START:02d}:00 – {TRADING_HOUR_END:02d}:00 Madrid")
    else:
        print("  Horario           24h (sin filtro)")
    print(f"  Trailing step     {TRAILING_STEP_MULT}× ATR")
    print(f"  Máx TP ext.       {MAX_TP_EXTENSIONS}")
    print("=" * 62)
    print()
    print("  Variables de entorno disponibles:")
    print("    EXCHANGE_MODE          quantfury|bybit         (default: quantfury)")
    print("    QUANTFURY_DEPOSIT      euros depositados       (default: 100)")
    print("    RISK_PROFILE           conservador|moderado|agresivo (default: agresivo)")
    print("    TRADING_HOURS_ENABLED  true|false              (default: false)")
    print("    TRADING_HOUR_START     hora inicio             (default: 8)")
    print("    TRADING_HOUR_END       hora fin                (default: 23)")
    print("    TRAILING_STEP_MULT     0.0–2.0                 (default: 1.0)")
    print("    MAX_TP_EXTENSIONS      0,1,2…                  (default: 1)")
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
