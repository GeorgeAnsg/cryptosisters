"""
V12 Shadow — corre en paralelo con V12 live pero NO ejecuta órdenes.

Utiliza exactamente los mismos parámetros, pares y modelo que V12 live.
Encima aplica el filtro de orderbook heatmap y logea qué habría hecho diferente:
  BLOCKED    — V11 habría abierto, el heatmap lo habría bloqueado.
  TP_ADJUSTED — V11 habría abierto con TP X, el heatmap lo habría bajado a Y.
  PASS       — Sin diferencia (sin muros relevantes en el camino).

Variables de entorno (mismas que V11):
  BYBIT_API_KEY, BYBIT_API_SECRET
  HEATMAP_URL           — base URL del endpoint heatmap
  WALL_MIN_NOTIONAL     — notional mínimo para considerar muro (default: 1_000_000)
  TRADING_HOURS_ENABLED — true/false (default: false)
  TRADING_HOUR_START    — hora inicio Madrid (default: 8)
  TRADING_HOUR_END      — hora fin Madrid (default: 23)
  TRAILING_STEP_MULT    — igual que V11 (default: 1.0)
  MAX_TP_EXTENSIONS     — igual que V11 (default: 1)
  SHADOW_LOG            — ruta del log JSONL (default: ./data/v12_shadow.jsonl)
  STATE_DIR             — directorio de estado (default: ./data)

Uso:
  python -m v12.shadow
  python -m v12.shadow --btc-only
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ccxt
import pandas as pd

import v6.core.bot_core as _bc
from v6.core.bot_core import (
    load_state, save_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision,
)
from v6.core.bot_indicators import precompute_indicators
from v6.main import _maybe_retrain
from v7.strategy_ml import StrategyML
from v9.orderbook_filter import adjust_tp_for_walls

MODEL_DIR  = ROOT / "v13" / "models"
STATE_DIR  = Path(os.getenv("STATE_DIR",  str(ROOT / "data")))
SHADOW_LOG = Path(os.getenv("SHADOW_LOG", str(STATE_DIR / "v12_shadow.jsonl")))
STATE_DIR.mkdir(parents=True, exist_ok=True)

# ── Mismos params que V12 live ─────────────────────────────────────────────────
TRAILING_STEP_MULT = float(os.getenv("TRAILING_STEP_MULT", "1.0"))
MAX_TP_EXTENSIONS  = int(os.getenv("MAX_TP_EXTENSIONS",    "1"))
RISK_PROFILE_NAME  = os.getenv("RISK_PROFILE", "agresivo").lower()

_RISK_PROFILES = {
    "conservador": {"tiers": [(0, 0.02, 0.35)],                                          "max_drawdown": 0.10},
    "moderado":    {"tiers": [(75, 0.07, 1.0), (65, 0.05, 0.87), (0, 0.03, 0.52)],      "max_drawdown": 0.15},
    "agresivo":    {"tiers": [(75, 0.12, 1.0), (65, 0.08, 1.0), (0, 0.05, 0.87)],       "max_drawdown": 0.25},
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

# ── TP dinámico (igual que V11) ────────────────────────────────────────────────
_TP_MAP = {
    ("bull",    True):  5.0, ("bull",    False): 4.5,
    ("neutral", True):  3.5, ("neutral", False): 3.5,
    ("bear",    True):  4.5, ("bear",    False): 4.0,
}

def _dynamic_tp(signal) -> float:
    try:
        adx = float(str(signal.technical.get("details", {}).get("adx", 0) or 0).split()[-1])
    except Exception:
        adx = 0.0
    return _TP_MAP.get((signal.regime, adx >= 25), 4.0)


def _tp_from_atr(entry: float, side: str, atr: float, mult: float) -> float:
    return entry + atr * mult if side.upper() == "LONG" else entry - atr * mult


_log_lock = threading.Lock()

def _log(record: dict):
    record["ts"] = datetime.now(UTC).isoformat()
    line = json.dumps(record, ensure_ascii=False)
    with _log_lock:
        with open(SHADOW_LOG, "a") as f:
            f.write(line + "\n")
    print(f"[V12-shadow] {line}")


def make_exchange():
    return ccxt.bybit({
        "apiKey":  os.getenv("BYBIT_API_KEY",    ""),
        "secret":  os.getenv("BYBIT_API_SECRET", ""),
        "options": {"defaultType": "linear"},
        "enableRateLimit": True,
    })


def make_strategy():
    with open(MODEL_DIR / "v13_classifier_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v13_classifier.pkl"), threshold=0.53)
    s.feature_cols = meta["feature_cols"]
    return s


def shadow_loop(pair: str, label: str):
    print(f"[{label}] V12 shadow iniciado — {pair}")
    exchange   = make_exchange()
    strategy   = make_strategy()
    slug       = f"v12_shadow_{pair.replace('/', '_').replace(':', '_')}"
    state_file = str(STATE_DIR / f"{slug}_state.json")
    state      = load_state(state_file)

    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(pair, "15m", limit=300)
            df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = precompute_indicators(df)

            ts       = pd.Timestamp(df.iloc[-1]["timestamp"])
            date_str = str(ts.date())
            reset_daily_counter(state, date_str)
            state["current_candle_index"] = state.get("current_candle_index", 0) + 1

            price = float(df.iloc[-1]["close"])
            live_extras = {
                "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
                "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
                "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
                "orderbook":  {"bull_mod": 0, "bear_mod": 0},
                "macro_corr": {"bull_mod": 0, "bear_mod": 0},
            }

            signal = strategy.get_signal(df, live_extras, row=df.iloc[-1])
            rp     = apply_regime(V12_RISK, signal.regime)
            rp["take_profit_atr_mult"] = _dynamic_tp(signal)
            atr    = signal.technical.get("details", {}).get("atr", 0) or 0

            # Filtro de régimen para fin de semana
            if ts.weekday() >= 5:
                if signal.regime == "bull":
                    rp["weekend_mode"]            = "trend"
                    rp["weekend_min_score_bonus"] = 0
                    rp["risk_pct"]                = 0.02
                    signal.bear_score = 0  # solo LONG en bull market fin de semana
                else:
                    rp["weekend_mode"]            = "trend"
                    rp["weekend_min_score_bonus"] = 0

            check_sl_tp(state, pair, price, rp, atr=atr,
                        scores={"bullish_total": signal.bull_score,
                                "bearish_total": signal.bear_score})

            had_position = state.get("position") is not None
            make_decision(state, pair, price, atr, signal, rp,
                          verbose=False, min_hold_candles=3,
                          current_candle_index=state["current_candle_index"],
                          winrate_table={}, timestamp=ts)
            opened = not had_position and state.get("position") is not None

            if opened:
                pos  = state["position"]
                side = pos["side"]
                proposed_tp = _tp_from_atr(price, side, atr, rp["take_profit_atr_mult"])

                wall = adjust_tp_for_walls(
                    side=side,
                    entry_price=price,
                    proposed_tp=proposed_tp,
                    pair=pair,
                )

                base = {
                    "pair":        pair,
                    "side":        side,
                    "entry_price": price,
                    "proposed_tp": round(proposed_tp, 4),
                    "bull_score":  signal.bull_score,
                    "bear_score":  signal.bear_score,
                    "regime":      signal.regime,
                }

                if wall.skip_trade:
                    _log({**base, "event": "BLOCKED",
                          "wall_price": wall.nearest_wall_price,
                          "wall_notional": wall.nearest_wall_notional,
                          "reason": wall.reason})
                elif wall.adjusted_tp != wall.original_tp:
                    _log({**base, "event": "TP_ADJUSTED",
                          "adjusted_tp": wall.adjusted_tp,
                          "wall_price": wall.nearest_wall_price,
                          "wall_notional": wall.nearest_wall_notional,
                          "reason": wall.reason})
                else:
                    _log({**base, "event": "PASS", "reason": "sin_muros"})

        except Exception as e:
            print(f"[{label}] Error: {e}")
        finally:
            save_state(state, state_file)

        time.sleep(900)


def main():
    parser = argparse.ArgumentParser(description="CORVUS Shadow — orderbook heatmap filter")
    parser.add_argument("--btc-only",  action="store_true")
    parser.add_argument("--eth-only",  action="store_true")
    parser.add_argument("--link-only", action="store_true")
    parser.add_argument("--aave-only", action="store_true")
    parser.add_argument("--inj-only",  action="store_true")
    args = parser.parse_args()

    tier_str = "/".join(f"{int(r*100)}%" for _, r, _ in reversed(_ACTIVE_PROFILE["tiers"]))
    print("=" * 62)
    print("  CORVUS Shadow — live + Orderbook Heatmap Filter")
    print(f"  Perfil de riesgo  {RISK_PROFILE_NAME.upper()}  ({tier_str} por score)")
    print(f"  Max drawdown      {int(_ACTIVE_PROFILE['max_drawdown']*100)}%")
    print(f"  Pares: BTC + ETH + LINK + AAVE + INJ | step={TRAILING_STEP_MULT} | max_tp_ext={MAX_TP_EXTENSIONS}")
    print(f"  Log:   {SHADOW_LOG}")
    print(f"  Muro mínimo: ${float(os.getenv('WALL_MIN_NOTIONAL','1000000')):,.0f} notional")
    print("=" * 62)

    # Shadow es silencioso — no envía Telegram, solo logs JSONL
    _bc.send_telegram = lambda *a, **kw: None
    _bc._tg_open      = lambda *a, **kw: None
    _bc._tg_update    = lambda *a, **kw: None
    _bc._tg_close     = lambda *a, **kw: None

    _maybe_retrain()

    pairs = []
    others = args.eth_only or args.link_only or args.aave_only or args.inj_only
    if not others:
        pairs.append(("BTC/USDT:USDT", "BTC"))
    if not args.btc_only and not args.link_only and not args.aave_only and not args.inj_only:
        pairs.append(("ETH/USDT:USDT", "ETH"))
    if not args.btc_only and not args.eth_only and not args.aave_only and not args.inj_only:
        pairs.append(("LINK/USDT:USDT", "LINK"))
    if not args.btc_only and not args.eth_only and not args.link_only and not args.inj_only:
        pairs.append(("AAVE/USDT:USDT", "AAVE"))
    if not args.btc_only and not args.eth_only and not args.link_only and not args.aave_only:
        pairs.append(("INJ/USDT:USDT", "INJ"))

    if len(pairs) == 1:
        shadow_loop(*pairs[0])
    else:
        threads = [threading.Thread(target=shadow_loop, args=p, daemon=True) for p in pairs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()


if __name__ == "__main__":
    main()
