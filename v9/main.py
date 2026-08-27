"""
V9 — Shadow mode: V8 + filtro de orderbook heatmap.

Corre en paralelo con V8 live pero NO ejecuta órdenes reales.
Logea qué habría hecho diferente: trades bloqueados o TP ajustados.

Uso:
    python -m v9.main              # shadow BTC + ETH
    python -m v9.main --btc-only   # solo BTC
    SHADOW_LOG=./data/v9_shadow.jsonl python -m v9.main

Variables de entorno:
    BYBIT_API_KEY, BYBIT_API_SECRET  — para leer precios (no ordena nada)
    HEATMAP_URL                      — base URL del endpoint heatmap
    WALL_MIN_NOTIONAL                — notional mínimo para considerar muro (default: 1000000)
    SHADOW_LOG                       — ruta del log JSONL (default: ./data/v9_shadow.jsonl)
    STATE_DIR                        — directorio de estado (default: ./data)
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
import pandas as pd

from v6.core.bot_core import (
    load_state, save_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision,
)
from v6.core.bot_indicators import precompute_indicators
from v6.main import _maybe_retrain
from v7.strategy_ml import StrategyML
from v9.orderbook_filter import adjust_tp_for_walls

MODEL_DIR  = ROOT / "v7" / "models"
STATE_DIR  = Path(os.getenv("STATE_DIR", str(ROOT / "data")))
SHADOW_LOG = Path(os.getenv("SHADOW_LOG", str(STATE_DIR / "v9_shadow.jsonl")))

STATE_DIR.mkdir(parents=True, exist_ok=True)

V9_RISK = {
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

_log_lock = threading.Lock()


def _log(record: dict):
    record["ts"] = datetime.utcnow().isoformat()
    line = json.dumps(record, ensure_ascii=False)
    with _log_lock:
        with open(SHADOW_LOG, "a") as f:
            f.write(line + "\n")
    print(f"[V9-shadow] {line}")


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


def _tp_price_from_atr(entry: float, side: str, atr: float, mult: float) -> float:
    """Calcula el precio de TP dado entry, ATR y multiplicador."""
    if side == "long":
        return entry + atr * mult
    return entry - atr * mult


def shadow_loop(pair: str, label: str):
    """
    Loop shadow para un par. Lee datos reales de mercado, genera señales
    con la misma lógica que V8, aplica el filtro de orderbook encima,
    y logea diferencias — pero NO ejecuta órdenes.
    """
    print(f"[{label}] V9 shadow iniciado — {pair}")
    exchange   = make_exchange()
    strategy   = make_strategy()
    slug       = f"v9_shadow_{pair.replace('/', '_').replace(':', '_')}"
    state_file = str(STATE_DIR / f"{slug}_state.json")
    state      = load_state(state_file)
    tf         = "15m"
    limit     = 300

    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(pair, tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = precompute_indicators(df)

            ts    = pd.Timestamp(df.iloc[-1]["timestamp"])
            date_str = str(ts.date())
            reset_daily_counter(state, date_str)
            state["current_candle_index"] = len(df) - 1

            current_price = float(df.iloc[-1]["close"])
            live_extras = {
                "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
                "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
                "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
                "orderbook":  {"bull_mod": 0, "bear_mod": 0},
                "macro_corr": {"bull_mod": 0, "bear_mod": 0},
            }

            signal = strategy.get_signal(df, live_extras, row=df.iloc[-1])
            rp     = apply_regime(V9_RISK, signal.regime)
            atr    = signal.technical.get("details", {}).get("atr", 0) or 0

            # Simular check SL/TP (sobre estado shadow, no opera)
            check_sl_tp(state, pair, current_price, rp, atr=atr,
                        scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})

            # Detectar si V8 habría abierto posición
            had_position = state.get("position") is not None
            make_decision(state, pair, current_price, atr, signal, rp,
                          verbose=False, min_hold_candles=3,
                          current_candle_index=len(df) - 1,
                          winrate_table={}, timestamp=ts)

            opened_position = not had_position and state.get("position") is not None

            if opened_position:
                pos  = state["position"]
                side = pos["side"]  # "long" | "short"
                tp_mult    = rp.get("take_profit_atr_mult", 4.5)
                proposed_tp = _tp_price_from_atr(current_price, side, atr, tp_mult)

                # Filtro V9: ¿hay muro entre entry y TP?
                wall_result = adjust_tp_for_walls(
                    side=side,
                    entry_price=current_price,
                    proposed_tp=proposed_tp,
                    pair=pair,
                )

                if wall_result.skip_trade:
                    # V8 habría entrado — V9 habría bloqueado
                    _log({
                        "event":          "BLOCKED",
                        "pair":           pair,
                        "side":           side,
                        "entry_price":    current_price,
                        "proposed_tp":    round(proposed_tp, 2),
                        "wall_price":     wall_result.nearest_wall_price,
                        "wall_notional":  wall_result.nearest_wall_notional,
                        "reason":         wall_result.reason,
                        "bull_score":     signal.bull_score,
                        "bear_score":     signal.bear_score,
                        "regime":         signal.regime,
                    })
                elif wall_result.adjusted_tp != wall_result.original_tp:
                    # V8 habría entrado con TP original — V9 habría ajustado TP
                    _log({
                        "event":         "TP_ADJUSTED",
                        "pair":          pair,
                        "side":          side,
                        "entry_price":   current_price,
                        "original_tp":   round(proposed_tp, 2),
                        "adjusted_tp":   wall_result.adjusted_tp,
                        "wall_price":    wall_result.nearest_wall_price,
                        "wall_notional": wall_result.nearest_wall_notional,
                        "reason":        wall_result.reason,
                        "bull_score":    signal.bull_score,
                        "bear_score":    signal.bear_score,
                        "regime":        signal.regime,
                    })
                else:
                    # Sin diferencia respecto a V8
                    _log({
                        "event":       "PASS",
                        "pair":        pair,
                        "side":        side,
                        "entry_price": current_price,
                        "tp":          round(proposed_tp, 2),
                        "reason":      "sin_muros",
                    })

        except Exception as e:
            print(f"[{label}] Error: {e}")
        finally:
            save_state(state, state_file)

        time.sleep(900)  # esperar hasta la siguiente vela de 15m


def main():
    parser = argparse.ArgumentParser(description="V9 shadow — V8 + orderbook filter")
    parser.add_argument("--btc-only", action="store_true")
    parser.add_argument("--eth-only", action="store_true")
    args = parser.parse_args()

    print("=" * 55)
    print("  V9 Shadow Bot — V8 + Orderbook Heatmap Filter")
    print(f"  Log: {SHADOW_LOG}")
    print(f"  Muro mínimo: ${float(os.getenv('WALL_MIN_NOTIONAL', '1000000')):,.0f} notional")
    print("=" * 55)

    _maybe_retrain()

    pairs = []
    if not args.eth_only:
        pairs.append(("BTC/USDT:USDT", "BTC"))
    if not args.btc_only:
        pairs.append(("ETH/USDT:USDT", "ETH"))

    if len(pairs) == 1:
        shadow_loop(*pairs[0])
    else:
        threads = []
        for pair, label in pairs:
            t = threading.Thread(target=shadow_loop, args=(pair, label), daemon=True, name=label)
            threads.append(t)
            t.start()
            time.sleep(3)

        print(f"\n  {len(threads)} pares en shadow: {[p[1] for p in pairs]}")
        print("  Ctrl+C para detener\n")

        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n  Deteniendo V9 shadow...")


if __name__ == "__main__":
    main()
