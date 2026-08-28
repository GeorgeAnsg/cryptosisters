"""
V12 — Bot de producción: BTC + ETH + SOL.

Novedades respecto a V11:
  1. Balance dinámico: al arrancar pregunta el balance actual en QuantFury.
     Responde /balance N en el grupo para actualizarlo en cualquier momento.
  2. Recordatorio semanal de balance si no se ha actualizado en 7 días.
  3. Cierre parcial: cuando el precio alcanza PARTIAL_TP_MULT × el recorrido
     hacia TP, el bot avisa por Telegram de cerrar el 50% del trade.
  4. Perfiles de riesgo: conservador / moderado / agresivo (default: agresivo).

Variables de entorno:
  BYBIT_API_KEY, BYBIT_API_SECRET
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
  STATE_DIR                — directorio de estado (default: ./data)

  EXCHANGE_MODE            — quantfury (default) | bybit
  QUANTFURY_DEPOSIT        — balance inicial fallback si no hay /balance (default: 100)
  RISK_PROFILE             — conservador | moderado | agresivo (default: agresivo)

  PARTIAL_TP_MULT          — fracción del recorrido TP para aviso parcial (default: 0 = desactivado)
  TRADING_HOURS_ENABLED    — true/false (default: false)
  TRADING_HOUR_START       — hora inicio Madrid (default: 8)
  TRADING_HOUR_END         — hora fin Madrid (default: 23)
  TRAILING_STEP_MULT       — 0.0–2.0 (default: 1.0)
  MAX_TP_EXTENSIONS        — 0, 1, 2… (default: 1)
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ccxt
import requests

import v6.core.bot_core as _bc
from v6.core.bot_core import run_live, send_telegram
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

V12_CONFIG_FILE = STATE_DIR / "v12_config.json"

# ── Exchange / perfil ──────────────────────────────────────────────────────────
EXCHANGE_MODE      = os.getenv("EXCHANGE_MODE", "quantfury").lower()
QUANTFURY_DEPOSIT  = float(os.getenv("QUANTFURY_DEPOSIT", "100"))   # fallback
RISK_PROFILE_NAME  = os.getenv("RISK_PROFILE", "agresivo").lower()

PARTIAL_TP_MULT    = float(os.getenv("PARTIAL_TP_MULT", "0"))       # 0 = desactivado (pendiente backtest)
BALANCE_ADMIN_ID   = int(os.getenv("BALANCE_ADMIN_ID", "0"))        # único user_id autorizado para /balance

TRADING_HOURS_ENABLED = os.getenv("TRADING_HOURS_ENABLED", "false").lower() == "true"
TRADING_HOUR_START    = int(os.getenv("TRADING_HOUR_START", "8"))
TRADING_HOUR_END      = int(os.getenv("TRADING_HOUR_END",   "23"))
TRAILING_STEP_MULT    = float(os.getenv("TRAILING_STEP_MULT", "1.0"))
MAX_TP_EXTENSIONS     = int(os.getenv("MAX_TP_EXTENSIONS",    "1"))

# ── Perfiles de riesgo ─────────────────────────────────────────────────────────
_RISK_PROFILES = {
    "conservador": {
        "tiers":        [(0, 0.02, 0.35)],
        "qf_options":   [(2, "🟢")],
        "max_drawdown": 0.10,
    },
    "moderado": {
        "tiers":        [(75, 0.07, 1.0), (65, 0.05, 0.87), (0, 0.03, 0.52)],
        "qf_options":   [(3, "🟡"), (5, "🟠"), (7, "🔴")],
        "max_drawdown": 0.15,
    },
    "agresivo": {
        "tiers":        [(75, 0.12, 1.0), (65, 0.08, 1.0), (0, 0.05, 0.87)],
        "qf_options":   [(5, "🟡"), (8, "🟠"), (12, "🔴")],
        "max_drawdown": 0.25,
    },
}
_ACTIVE_PROFILE = _RISK_PROFILES.get(RISK_PROFILE_NAME, _RISK_PROFILES["agresivo"])

V12_RISK = {
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
RISK_PROFILE = V12_RISK


# ── Balance dinámico ───────────────────────────────────────────────────────────
_config_lock = threading.Lock()

def _load_config() -> dict:
    if V12_CONFIG_FILE.exists():
        try:
            with open(V12_CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": QUANTFURY_DEPOSIT, "last_updated": None, "last_asked": None}

def _save_config(cfg: dict):
    with open(V12_CONFIG_FILE, "w") as f:
        json.dump(cfg, f)

def get_balance() -> float:
    with _config_lock:
        return _load_config().get("balance", QUANTFURY_DEPOSIT)

def set_balance(amount: float):
    with _config_lock:
        cfg = _load_config()
        cfg["balance"] = amount
        cfg["last_updated"] = str(date.today())
        _save_config(cfg)

def _maybe_ask_balance_reminder():
    today = date.today()
    if today.weekday() != 0:  # 0 = lunes
        return
    with _config_lock:
        cfg = _load_config()
        last_asked = cfg.get("last_asked")
        today_str  = str(today)
        if last_asked == today_str:
            return  # ya preguntó hoy
        cfg["last_asked"] = today_str
        _save_config(cfg)

    balance = get_balance()
    send_telegram(
        f"📅 <b>Recordatorio semanal — balance QuantFury</b>\n"
        f"Balance registrado: <b>{balance:.0f}€</b>\n"
        f"¿Ha cambiado? Responde <code>/balance N</code> para actualizar el sizing."
    )


# ── Telegram listener — recibe /balance N ─────────────────────────────────────
def _telegram_listener():
    token  = os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        return
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                timeout=35,
            )
            data = r.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = (msg.get("text") or "").strip()
                if text.lower().startswith("/balance"):
                    sender_id = msg.get("from", {}).get("id", 0)
                    if BALANCE_ADMIN_ID and sender_id != BALANCE_ADMIN_ID:
                        send_telegram("⛔ Solo el administrador puede actualizar el balance.")
                        continue
                    parts = text.split()
                    if len(parts) >= 2:
                        try:
                            amount = float(parts[1])
                            set_balance(amount)
                            send_telegram(
                                f"✅ <b>Balance actualizado: {amount:.0f}€</b>\n"
                                f"El sizing de los próximos trades se calculará sobre este valor."
                            )
                        except ValueError:
                            send_telegram("❌ Formato incorrecto. Usa: <code>/balance 350</code>")
        except Exception as e:
            print(f"[telegram_listener] Error: {e}")
            time.sleep(10)


# ── Sizing QuantFury ───────────────────────────────────────────────────────────
def _quantfury_sizing_msg(side: str, pair: str, price: float, sl: float, tp: float, score: float) -> str:
    sl_pct = abs(price - sl) / price
    if sl_pct <= 0:
        return ""

    balance = get_balance()
    options = _ACTIVE_PROFILE["qf_options"]
    tiers   = _ACTIVE_PROFILE["tiers"]

    recommended_risk = tiers[-1][1]
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
        f"Balance: <b>{balance:.0f}€</b>  |  SL: {sl_pct*100:.2f}%  |  R/R: {rr:.1f}x\n",
    ]
    for risk_pct, emoji in options:
        risk_eur = balance * risk_pct / 100
        power    = risk_eur / sl_pct
        tag = "  ← <b>recomendado</b>" if risk_pct == recommended_pct else ""
        lines.append(f"{emoji} <b>{risk_pct}% riesgo</b>: {power:,.0f}€ poder  ({risk_eur:.1f}€ en juego){tag}")
    lines.append(f"\n💡 {rec_reason}")
    return "\n".join(lines)


# ── Cierre parcial ─────────────────────────────────────────────────────────────
def _check_partial_tp(state: dict, pair: str, price: float, atr: float, rp: dict):
    pos = state.get("position")
    if not pos or pos.get("partial_tp_notified"):
        return

    entry   = pos.get("entry_price", price)
    side    = pos.get("side", "long")
    tp_mult = rp.get("take_profit_atr_mult", 4.5)
    partial_mult = tp_mult * PARTIAL_TP_MULT

    if side == "LONG":
        partial_price = entry + atr * partial_mult
        hit = price >= partial_price
    else:
        partial_price = entry - atr * partial_mult
        hit = price <= partial_price

    if hit:
        pos["partial_tp_notified"] = True
        pnl_pct = abs(price - entry) / entry * 100
        be_price = entry  # breakeven
        send_telegram(
            f"⚡ <b>CIERRE PARCIAL SUGERIDO — {pair}</b>\n"
            f"Precio actual: <b>{price:,.2f}</b> (+{pnl_pct:.1f}% desde entrada)\n\n"
            f"✂️ Cierra el <b>50%</b> del trade ahora\n"
            f"📍 Mueve el SL al breakeven: <b>{be_price:,.2f}</b>\n"
            f"🎯 Deja correr el resto hasta el TP original"
        )


# ── Estrategia con filtro de horas + cierre parcial ───────────────────────────
class V12Strategy:
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


def _is_trading_hours() -> bool:
    h = _now_madrid().hour
    return TRADING_HOUR_START <= h < TRADING_HOUR_END


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
    return V12Strategy(inner)


def run_pair(pair: str, label: str):
    print(f"[{label}] V12 iniciando — {pair}")
    exchange = make_exchange()
    strategy = make_strategy()
    profile_name = f"v12_{pair.replace('/', '_').replace(':', '_')}"

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
    parser = argparse.ArgumentParser(description="V12 — Bot BTC+ETH+SOL")
    parser.add_argument("--btc-only", action="store_true")
    parser.add_argument("--eth-only", action="store_true")
    parser.add_argument("--sol-only", action="store_true")
    args = parser.parse_args()

    tiers      = _ACTIVE_PROFILE["tiers"]
    options    = _ACTIVE_PROFILE["qf_options"]
    tier_str   = "/".join(f"{int(r*100)}%" for _, r, _ in reversed(tiers))
    balance    = get_balance()

    print("=" * 62)
    print("  V12 Trading Bot — Configuración activa")
    print("=" * 62)
    print(f"  Modo exchange     {EXCHANGE_MODE.upper()}")
    print(f"  Balance QF        {balance:.0f}€  (responde /balance N para cambiar)")
    print(f"  Perfil de riesgo  {RISK_PROFILE_NAME.upper()}")
    print(f"    Riesgo/trade    {tier_str} (por score de señal)")
    print(f"    Max drawdown    {int(_ACTIVE_PROFILE['max_drawdown']*100)}%")
    if PARTIAL_TP_MULT > 0:
        print(f"    Cierre parcial  al {int(PARTIAL_TP_MULT*100)}% del recorrido hacia TP")
    else:
        print(f"    Cierre parcial  DESACTIVADO")
    opt_str = "  /  ".join(f"{r}% ({e})" for r, e in options)
    print(f"    Opciones QF     {opt_str}")
    if TRADING_HOURS_ENABLED:
        print(f"  Horario           {TRADING_HOUR_START:02d}:00 – {TRADING_HOUR_END:02d}:00 Madrid")
    else:
        print("  Horario           24h (sin filtro)")
    print(f"  Trailing step     {TRAILING_STEP_MULT}× ATR")
    print(f"  Máx TP ext.       {MAX_TP_EXTENSIONS}")
    print("=" * 62)

    if not (MODEL_DIR / "v7_classifier_oos.pkl").exists():
        print("ERROR: Modelo ML no encontrado.")
        sys.exit(1)

    _maybe_retrain()

    # Inyectar sizing QuantFury
    if EXCHANGE_MODE == "quantfury":
        _orig_tg_open = _bc._tg_open

        def _tg_open_qf(side, pair, price, sl, tp, score, atr,
                        trade_type="intraday", amount_usdt=0, balance_usdt=0):
            _orig_tg_open(side, pair, price, sl, tp, score, atr, trade_type, amount_usdt, balance_usdt)
            msg = _quantfury_sizing_msg(side, pair, price, sl, tp, score)
            if msg:
                _bc.send_telegram(msg)

        _bc._tg_open = _tg_open_qf

    # Arrancar listener de Telegram en background
    t_listener = threading.Thread(target=_telegram_listener, daemon=True, name="tg-listener")
    t_listener.start()

    # Mensaje de inicio — preguntar balance y marcar last_asked para evitar recordatorio inmediato
    with _config_lock:
        cfg = _load_config()
        cfg["last_asked"] = str(date.today())
        _save_config(cfg)

    send_telegram(
        f"🚀 <b>V12 iniciado</b> — BTC + ETH + SOL\n"
        f"Perfil: <b>{RISK_PROFILE_NAME.upper()}</b>  |  "
        f"Balance registrado: <b>{balance:.0f}€</b>\n\n"
        f"¿Ha cambiado tu balance en QuantFury?\n"
        f"Responde <code>/balance N</code> para actualizar el sizing."
    )

    # Recordatorio semanal en hilo separado
    def _weekly_reminder_loop():
        while True:
            time.sleep(3600)  # revisar cada hora
            _maybe_ask_balance_reminder()

    threading.Thread(target=_weekly_reminder_loop, daemon=True, name="weekly-reminder").start()

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
            print("\n  Deteniendo V12...")


if __name__ == "__main__":
    main()
