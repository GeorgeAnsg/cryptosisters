"""
bot_core.py — Infraestructura compartida del bot de trading v6
==============================================================
Contiene todo lo que es independiente de la estrategia:
  - Perfiles de riesgo y regímenes de mercado
  - Logger, estado, persistencia
  - Gestión de posiciones (abrir, cerrar, SL/TP trailing)
  - Notificaciones Telegram
  - Loop principal run_live() y run_backtest()

Las estrategias (bot_intraday.py, bot_swing.py) implementan:
    get_signal(df_ltf, htf_context, live_extras) -> Signal

La interfaz Signal es un dataclass importado desde aquí.
"""

import ccxt
import json
import os
import time
import requests
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# =============================================================================
# PERFILES DE RIESGO
# =============================================================================

RISK_PROFILES = {
    "moderate": {
        "risk_pct":               0.02,   # % del capital que se arriesga por trade (pérdida si SL toca)
        "max_cost_pct":           0.35,   # máximo % del balance comprometido por posición
        "stop_loss_atr_mult":     2.5,
        "take_profit_atr_mult":   4.0,
        "min_score":              58,
        "entry_advantage":        15,     # ventaja mínima sobre el score contrario
        "max_daily_trades":       6,
        "max_drawdown_pct":       0.10,
        "max_daily_loss_pct":     0.03,   # circuit breaker: pausa si pierde >3% en el día
        "trailing_stop":          True,
        "max_tp_extensions":      2,
        "weekend_mode":           "range",
        "weekend_min_score_bonus": 10,
        "min_vol_ratio":          0.0,
    },
    "aggressive": {
        "risk_pct":               0.04,
        "max_cost_pct":           0.30,
        "stop_loss_atr_mult":     2.5,
        "take_profit_atr_mult":   3.0,
        "min_score":              50,
        "entry_advantage":        10,
        "max_daily_trades":       10,
        "max_drawdown_pct":       0.20,
        "max_daily_loss_pct":     0.06,
        "trailing_stop":          True,
        "max_tp_extensions":      3,
        "weekend_mode":           "trend",
        "weekend_min_score_bonus": 5,
        "min_vol_ratio":          0.0,
    },
}

# =============================================================================
# REGÍMENES DE MERCADO
# =============================================================================

MARKET_REGIMES = {
    "neutral": {
        "long_min_bonus":  0,
        "short_min_bonus": 0,
        "long_tp_factor":  1.0,
        "short_tp_factor": 1.0,
        "long_max_ext":    0,
        "short_max_ext":   0,
        "breakeven_mult":  1.0,
    },
    "bull": {
        "long_min_bonus":  -5,
        "short_min_bonus": +20,
        "long_tp_factor":  1.4,
        "short_tp_factor": 0.8,
        "long_max_ext":    1,
        "short_max_ext":   0,
        "breakeven_mult":  1.5,
    },
    "bear": {
        "long_min_bonus":  +20,
        "short_min_bonus": -5,
        "long_tp_factor":  0.8,
        "short_tp_factor": 1.4,
        "long_max_ext":    0,
        "short_max_ext":   1,
        "breakeven_mult":  1.5,
    },
}


def apply_regime(risk_profile: dict, regime: str) -> dict:
    """Aplica los ajustes del régimen sobre una copia del perfil."""
    rp = dict(risk_profile)
    mods = MARKET_REGIMES.get(regime, MARKET_REGIMES["neutral"])
    rp["_long_min_bonus"]  = mods["long_min_bonus"]
    rp["_short_min_bonus"] = mods["short_min_bonus"]
    rp["_long_tp_factor"]  = mods["long_tp_factor"]
    rp["_short_tp_factor"] = mods["short_tp_factor"]
    rp["_long_max_ext"]    = mods["long_max_ext"]
    rp["_short_max_ext"]   = mods["short_max_ext"]
    rp["_breakeven_mult"]  = mods["breakeven_mult"]
    rp["_regime"]          = regime
    return rp


# =============================================================================
# SEÑAL — interfaz entre estrategias y el core
# =============================================================================

@dataclass
class Signal:
    """Resultado del análisis de una estrategia.

    Campos:
      bull_score / bear_score : puntuación final (0-100) de cada dirección
      technical               : dict con 'details' y metadatos de análisis
      htf_blocks_long         : True si el HTF veta completamente los longs
      htf_blocks_short        : True si el HTF veta completamente los shorts
      regime                  : régimen detectado automáticamente ('bull'/'bear'/'neutral')
    """
    bull_score:      int
    bear_score:      int
    technical:       dict = field(default_factory=dict)
    htf_blocks_long:  bool = False
    htf_blocks_short: bool = False
    regime:          str  = "neutral"


# =============================================================================
# LOGGER
# =============================================================================

class Logger:
    def __init__(self, log_file: str = "bot_decisions.log"):
        self.log_file = log_file

    def log(self, message: str, level: str = "INFO"):
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] {message}"
        print(line)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")

    def decision(self, pair: str, bull: int, bear: int, min_s: int,
                 position: Optional[dict], reason: str):
        ts      = datetime.now().strftime("%H:%M:%S")
        pos_str = "FLAT"
        if position:
            pos_str = f"{position['side']} desde {position['entry_price']:.2f}"
        line = (f"[{ts}] [{pair}] Estado:{pos_str} | "
                f"Bull:{bull:3d} Bear:{bear:3d} Min:{min_s} | >> {reason}")
        print(line)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")


logger = Logger()

# =============================================================================
# ESTADO
# =============================================================================

def load_state(path: str) -> dict:
    if Path(path).exists():
        with open(path, "r") as f:
            return json.load(f)
    return {
        "balance_usdt":   1000.0,
        "position":       None,
        "trades":         [],
        "daily_trades":   0,
        "daily_longs":    0,
        "daily_shorts":   0,
        "daily_date":     datetime.now().strftime("%Y-%m-%d"),
        "daily_loss_usdt": 0.0,    # para circuit breaker diario
        "stats": {
            "wins": 0, "losses": 0, "total_pnl": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "total_longs": 0, "total_shorts": 0,
            "long_wins": 0, "short_wins": 0,
        },
        "peak_balance":   1000.0,
        "created_at":     datetime.now().isoformat(),
    }


def save_state(state: dict, path: str):
    with open(path, "w") as f:
        json.dump(state, f, indent=2, default=str)


def reset_daily_counter(state: dict, candle_date: str = None):
    today = candle_date or datetime.now().strftime("%Y-%m-%d")
    if state.get("daily_date") != today:
        state["daily_trades"]   = 0
        state["daily_longs"]    = 0
        state["daily_shorts"]   = 0
        state["daily_loss_usdt"] = 0.0
        state["daily_date"]     = today


# =============================================================================
# DATOS DE MERCADO
# =============================================================================

def fetch_ohlcv(exchange, pair: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_historical_ohlcv(exchange, pair: str, timeframe: str, days: int) -> pd.DataFrame:
    logger.log(f"Descargando {days} días de datos para {pair} ({timeframe})...")
    all_data = []
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    limit = 1000
    while True:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        all_data.extend(ohlcv)
        since = ohlcv[-1][0] + 1
        if len(ohlcv) < limit:
            break
        time.sleep(0.2)
        pct = min(100, len(all_data) / (days * 96) * 100)
        print(f"\r  Descargando... {len(all_data)} velas ({pct:.0f}%)", end="", flush=True)
    print()
    df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    logger.log(f"Descargadas {len(df)} velas ({df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]})")
    return df


# =============================================================================
# POSICIONES
# =============================================================================

def calc_position_size(balance: float, risk_pct: float, price: float,
                       sl_distance: float, max_cost_pct: float = 0.30) -> tuple[float, float]:
    """Calcula el tamaño de posición con riesgo fijo en USDT.

    El riesgo por trade es siempre risk_pct × balance, independientemente
    de la volatilidad. El tamaño se ajusta al ATR del momento para que si
    el SL se activa, la pérdida sea exactamente ese importe.

    Returns (amount_units, cost_usdt).
    """
    if price <= 0 or sl_distance <= 0:
        return 0.0, 0.0
    risk_usdt = balance * risk_pct
    amount    = risk_usdt / sl_distance           # unidades (BTC, ETH…)
    cost      = amount * price                    # USDT invertidos (valor nocional)
    # Cap: nunca comprometer más del max_cost_pct del balance (margen para futuros)
    max_cost  = balance * max_cost_pct
    if cost > max_cost:
        amount = max_cost / price
        cost   = max_cost
    return amount, cost


def open_position(state: dict, pair: str, side: str, price: float,
                  atr: float, risk_profile: dict, score: int,
                  candle_date: str = None, trade_type: str = "intraday",
                  _cond_key: tuple = None) -> Optional[str]:
    """Abre una posición LONG o SHORT."""
    reset_daily_counter(state, candle_date)

    if state["position"] is not None:
        return None
    if state["daily_trades"] >= risk_profile["max_daily_trades"]:
        return None

    # Drawdown máximo acumulado
    current = state["balance_usdt"]
    peak    = state.get("peak_balance", current)
    if peak > 0 and (peak - current) / peak >= risk_profile["max_drawdown_pct"]:
        return "[DRAWDOWN] Bot pausado por drawdown máximo"

    # Circuit breaker diario
    max_daily_loss = state["balance_usdt"] * risk_profile.get("max_daily_loss_pct", 0.05)
    if state.get("daily_loss_usdt", 0.0) >= max_daily_loss:
        return "[CIRCUIT-BREAKER] Pérdida diaria máxima alcanzada"

    # ── Conviction multipliers (score-based) ─────────────────────────────────
    # Score bajo (barely above min): 75% size, tight SL/TP
    # Score medio (10-20 above min): 100% size, normal SL/TP
    # Score alto (20+ above min):    125% size, wider TP
    _min_score  = risk_profile.get("min_score", 55)
    _margin     = max(0, score - _min_score)
    if _margin < 10:
        _size_mult, _sl_mult, _tp_mult = 0.75, 0.90, 0.90
    elif _margin < 20:
        _size_mult, _sl_mult, _tp_mult = 1.00, 1.00, 1.00
    else:
        _size_mult, _sl_mult, _tp_mult = 1.25, 1.10, 1.20

    sl_distance = atr * risk_profile["stop_loss_atr_mult"] * _sl_mult
    amount, cost = calc_position_size(
        state["balance_usdt"], risk_profile["risk_pct"] * _size_mult, price, sl_distance,
        max_cost_pct=risk_profile.get("max_cost_pct", 0.30),
    )
    if amount <= 0:
        return None

    tp_base    = atr * risk_profile["take_profit_atr_mult"] * _tp_mult
    tp_factor  = risk_profile.get(f"_{'long' if side == 'LONG' else 'short'}_tp_factor", 1.0)
    if side == "LONG":
        stop_loss   = price - sl_distance
        take_profit = price + tp_base * tp_factor
    else:
        stop_loss   = price + sl_distance
        take_profit = price - tp_base * tp_factor

    state["position"] = {
        "side":                side,
        "entry_price":         price,
        "amount":              amount,
        "stop_loss":           round(stop_loss, 2),
        "take_profit":         round(take_profit, 2),
        "initial_sl_distance": sl_distance,
        "highest_price":       price,
        "lowest_price":        price,
        "opened_candle_index": state.get("current_candle_index"),
        "score_at_entry":      score,
        "conviction_mult":     _size_mult,
        "opened_at":           datetime.now().isoformat(),
        "trade_type":          trade_type,
        "_condition_key":      _cond_key,
    }
    state["balance_usdt"] -= cost
    state["daily_trades"] += 1
    if side == "LONG":
        state["daily_longs"] = state.get("daily_longs", 0) + 1
    else:
        state["daily_shorts"] = state.get("daily_shorts", 0) + 1

    state["trades"].append({
        "pair": pair, "action": f"OPEN_{side}", "price": price,
        "amount": amount, "score": score, "time": datetime.now().isoformat(),
        "trade_type": trade_type,
    })
    _tg_open(side, pair, price, stop_loss, take_profit, score, atr, trade_type, cost,
             state["balance_usdt"] + cost)
    return (f"ABRIR {side} {pair} | {amount:.6f} @ {price:.2f} | "
            f"SL:{stop_loss:.2f} TP:{take_profit:.2f} | Score:{score} | Riesgo:{cost*sl_distance/price:.2f}$")


def close_position(state: dict, pair: str, price: float, reason: str) -> Optional[str]:
    """Cierra la posición actual."""
    if state["position"] is None:
        return None

    pos   = state["position"]
    side  = pos["side"]
    entry = pos["entry_price"]
    amount = pos["amount"]

    if side == "LONG":
        pnl     = (price - entry) * amount
        pnl_pct = (price - entry) / entry * 100
        state["balance_usdt"] += amount * price
    else:
        pnl     = (entry - price) * amount
        pnl_pct = (entry - price) / entry * 100
        state["balance_usdt"] += (amount * entry) + pnl

    # Stats
    state["stats"]["total_pnl"] += pnl
    state["stats"][f"total_{side.lower()}s"] = state["stats"].get(f"total_{side.lower()}s", 0) + 1
    if pnl > 0:
        state["stats"]["wins"] += 1
        state["stats"]["best_trade"] = max(state["stats"]["best_trade"], pnl)
        state["stats"][f"{side.lower()}_wins"] = state["stats"].get(f"{side.lower()}_wins", 0) + 1
    else:
        state["stats"]["losses"] += 1
        state["stats"]["worst_trade"] = min(state["stats"]["worst_trade"], pnl)
        state["daily_loss_usdt"] = state.get("daily_loss_usdt", 0.0) + abs(pnl)

    if state["balance_usdt"] > state.get("peak_balance", 0):
        state["peak_balance"] = state["balance_usdt"]
    current_dd = (state["peak_balance"] - state["balance_usdt"]) / state["peak_balance"] * 100
    if current_dd > state.get("max_drawdown_seen", 0.0):
        state["max_drawdown_seen"] = current_dd

    state["trades"].append({
        "pair": pair, "action": f"CLOSE_{side}", "price": price,
        "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
        "reason": reason, "time": datetime.now().isoformat(),
        "_condition_key": pos.get("_condition_key"),
    })
    state["position"] = None

    if reason == "STOP_LOSS":
        state["sl_cooldown_until"] = state.get("current_candle_index", 0) + 4

    _tg_close(side, pair, price, pnl, pnl_pct, reason, state["balance_usdt"])
    return (f"CERRAR {side} {pair} @ {price:.2f} | Motivo:{reason} | "
            f"PnL:{pnl:+.2f}$ ({pnl_pct:+.2f}%) | Balance:{state['balance_usdt']:.2f}")


def check_sl_tp(state: dict, pair: str, current_price: float,
                risk_profile: dict, atr: float = 0,
                scores: Optional[dict] = None) -> Optional[str]:
    """Stop-loss, take-profit y trailing stop con break-even automático."""
    if state["position"] is None:
        return None

    pos  = state["position"]
    side = pos["side"]
    sl   = pos["stop_loss"]
    tp   = pos["take_profit"]

    if risk_profile["trailing_stop"]:
        sl_dist = pos.get("initial_sl_distance", 0)
        entry   = pos["entry_price"]
        be_mult = risk_profile.get("_breakeven_mult", 1.0)

        if side == "LONG":
            _pnl_f = (current_price - entry) * pos.get("amount", 0)
            if not pos.get("breakeven_set") and current_price >= entry + sl_dist * be_mult:
                if entry > sl:
                    pos["stop_loss"] = round(entry, 2)
                    sl = entry
                pos["breakeven_set"] = True
                _tg_update(pair, side, "🛡️ SL → break-even", sl, pos["take_profit"], pnl_float=_pnl_f)
            if current_price > pos.get("highest_price", current_price):
                pos["highest_price"] = current_price
                new_sl = current_price - sl_dist
                if new_sl > sl:
                    pos["stop_loss"] = round(new_sl, 2)
                    sl = new_sl
                    _tg_update(pair, side, f"📈 Trailing SL subido ({current_price:,.2f})", sl, pos["take_profit"], pnl_float=_pnl_f)
        else:
            _pnl_f = (entry - current_price) * pos.get("amount", 0)
            if not pos.get("breakeven_set") and current_price <= entry - sl_dist * be_mult:
                if entry < sl:
                    pos["stop_loss"] = round(entry, 2)
                    sl = entry
                pos["breakeven_set"] = True
                _tg_update(pair, side, "🛡️ SL → break-even", sl, pos["take_profit"], pnl_float=_pnl_f)
            if current_price < pos.get("lowest_price", current_price):
                pos["lowest_price"] = current_price
                new_sl = current_price + sl_dist
                if new_sl < sl:
                    pos["stop_loss"] = round(new_sl, 2)
                    sl = new_sl
                    _tg_update(pair, side, f"📉 Trailing SL bajado ({current_price:,.2f})", sl, pos["take_profit"], pnl_float=_pnl_f)

    # Stop loss
    if side == "LONG" and current_price <= sl:
        return close_position(state, pair, current_price, "STOP_LOSS")
    if side == "SHORT" and current_price >= sl:
        return close_position(state, pair, current_price, "STOP_LOSS")

    # Take profit adaptativo
    tp_hit = (side == "LONG" and current_price >= tp) or \
             (side == "SHORT" and current_price <= tp)
    if tp_hit:
        extensions  = pos.get("tp_extensions", 0)
        extra       = risk_profile.get(f"_{'long' if side == 'LONG' else 'short'}_max_ext", 0)
        max_ext     = risk_profile.get("max_tp_extensions", 0) + extra
        signal_ok   = False
        if scores and atr > 0 and extensions < max_ext:
            bull = scores.get("bullish_total", 0)
            bear = scores.get("bearish_total", 0)
            ms   = risk_profile["min_score"]
            if side == "LONG"  and bull >= ms and bull > bear:
                signal_ok = True
            elif side == "SHORT" and bear >= ms and bear > bull:
                signal_ok = True
        if signal_ok:
            ext_size = atr * risk_profile["take_profit_atr_mult"]
            if side == "LONG":
                new_tp = tp + ext_size
                if tp > sl:
                    pos["stop_loss"] = round(tp, 2)
            else:
                new_tp = tp - ext_size
                if tp < sl:
                    pos["stop_loss"] = round(tp, 2)
            pos["take_profit"]   = round(new_tp, 2)
            pos["tp_extensions"] = extensions + 1
            sc_val = scores.get("bullish_total" if side == "LONG" else "bearish_total", 0)
            _tg_update(pair, side, f"🚀 TP extendido x{extensions+1} (score={sc_val})",
                       pos["stop_loss"], pos["take_profit"])
            return f"[TP+{extensions+1}] TP → {new_tp:.2f} | SL asegurado {pos['stop_loss']:.2f}"
        return close_position(state, pair, current_price, "TAKE_PROFIT")

    return None


# =============================================================================
# DECISION ENGINE
# =============================================================================

def make_decision(state: dict, pair: str, price: float, atr: float,
                  signal: "Signal", risk_profile: dict,
                  verbose: bool = True,
                  min_hold_candles: int = 0,
                  current_candle_index: Optional[int] = None,
                  winrate_table: Optional[dict] = None,
                  timestamp=None) -> Optional[str]:
    """
    Motor de decisiones. Recibe un Signal de la estrategia y decide si
    abrir, cerrar o mantener la posición.

    Cambios respecto a v5:
      - htf_blocks_long / htf_blocks_short son vetos duros (no penalizaciones)
      - Circuit breaker diario integrado en open_position
    """
    from v6.core.bot_risk import get_learned_bonus, _make_condition_key

    bull  = signal.bull_score
    bear  = signal.bear_score
    tech  = signal.technical
    ms    = risk_profile["min_score"]
    ea    = risk_profile.get("entry_advantage", 15)
    pos   = state["position"]

    close_threshold = max(ms - 15, 35)

    hold_candles = 0
    if pos and current_candle_index is not None:
        opened = pos.get("opened_candle_index")
        if opened is not None:
            hold_candles = max(0, current_candle_index - opened)
    can_close_by_signal = hold_candles >= min_hold_candles

    scores = {"bullish_total": bull, "bearish_total": bear}

    # ── Cerrar posición abierta ──────────────────────────────────────────────
    if pos is not None:
        side = pos["side"]
        if can_close_by_signal:
            if side == "LONG"  and bear >= close_threshold and bear > bull + ea:
                if verbose:
                    logger.decision(pair, bull, bear, ms, pos, f"CERRAR LONG — señal bajista (bear={bear})")
                return close_position(state, pair, price, "SENAL_BAJISTA")
            if side == "SHORT" and bull >= close_threshold and bull > bear + ea:
                if verbose:
                    logger.decision(pair, bull, bear, ms, pos, f"CERRAR SHORT — señal alcista (bull={bull})")
                return close_position(state, pair, price, "SENAL_ALCISTA")
        if verbose:
            logger.decision(pair, bull, bear, ms, pos, "MANTENER posición")
        return None

    # ── Abrir posición ───────────────────────────────────────────────────────
    ts = timestamp if timestamp is not None else datetime.now()

    # Cooldown post-SL
    sl_cooldown = state.get("sl_cooldown_until", 0)
    if current_candle_index and current_candle_index < sl_cooldown:
        return None

    # Filtro de sesión volátil (apertura NYSE/Londres)
    from v6.core.bot_indicators import is_volatile_session
    if is_volatile_session(ts):
        return None

    # Filtro de volumen
    min_vol = risk_profile.get("min_vol_ratio", 0.0)
    if min_vol > 0 and tech.get("details", {}).get("vol_ratio", 1.0) < min_vol:
        return None

    # Ajustes de régimen sobre el umbral mínimo
    long_min  = ms + risk_profile.get("_long_min_bonus",  0)
    short_min = ms + risk_profile.get("_short_min_bonus", 0)

    # HTF — veto duro (v6: bloquea completamente, no penaliza)
    if signal.htf_blocks_long:
        long_min = 9999
    if signal.htf_blocks_short:
        short_min = 9999

    # Consolidación: umbral más alto en mercados apretados
    if tech.get("details", {}).get("consolidacion", False):
        long_min  += 10
        short_min += 10

    # Aprendizaje adaptativo
    _wt      = winrate_table or {}
    _rsi     = tech.get("details", {}).get("rsi", 50)
    _regime  = risk_profile.get("_regime", "neutral")
    long_min  -= get_learned_bonus("LONG",  _regime, _rsi, _wt)
    short_min -= get_learned_bonus("SHORT", _regime, _rsi, _wt)

    from v6.core.bot_indicators import check_signal_quality, is_weekend, apply_weekend_filter
    can_long,  l_min = apply_weekend_filter(tech, "LONG",  bull, bear, risk_profile, ts)
    can_short, s_min = apply_weekend_filter(tech, "SHORT", bull, bear, risk_profile, ts)
    # apply_weekend_filter devuelve su propio umbral; tomamos el mayor de los dos
    long_min  = max(long_min,  l_min)
    short_min = max(short_min, s_min)

    q_long  = check_signal_quality(tech, "LONG")
    q_short = check_signal_quality(tech, "SHORT")

    if can_long and bull >= long_min and bull > bear + ea and q_long:
        if verbose:
            logger.decision(pair, bull, bear, long_min, None,
                            f"ABRIR LONG (bull={bull} >= {long_min}, htf_block={signal.htf_blocks_long})")
        _ckey = _make_condition_key("LONG", _regime, _rsi)
        trade_type = tech.get("trade_type", "intraday")
        return open_position(state, pair, "LONG", price, atr, risk_profile, bull,
                             _cond_key=_ckey, trade_type=trade_type)

    if can_short and bear >= short_min and bear > bull + ea and q_short:
        if verbose:
            logger.decision(pair, bull, bear, short_min, None,
                            f"ABRIR SHORT (bear={bear} >= {short_min}, htf_block={signal.htf_blocks_short})")
        _ckey = _make_condition_key("SHORT", _regime, _rsi)
        trade_type = tech.get("trade_type", "intraday")
        return open_position(state, pair, "SHORT", price, atr, risk_profile, bear,
                             _cond_key=_ckey, trade_type=trade_type)

    if verbose:
        logger.decision(pair, bull, bear, ms, None, "HOLD — scores insuficientes")
    return None


# =============================================================================
# TELEGRAM
# =============================================================================

TELEGRAM_SILENT = os.environ.get("TELEGRAM_SILENT", "0") == "1"


def send_telegram(message: str):
    if TELEGRAM_SILENT:
        return
    token   = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def _tg_open(side: str, pair: str, price: float, sl: float, tp: float,
             score: int, atr: float, trade_type: str = "intraday",
             amount_usdt: float = 0, balance: float = 0):
    emoji   = "📈" if side == "LONG" else "📉"
    dir_es  = "LONG (compra)" if side == "LONG" else "SHORT (venta)"
    type_tag = " 🔥 <b>[SWING]</b>" if trade_type == "swing" else ""
    size_ln  = ""
    if amount_usdt > 0 and balance > 0:
        size_ln = f"Inversión: <b>{amount_usdt:,.2f} USDT ({amount_usdt/balance*100:.1f}%)</b>\n"
    send_telegram(
        f"{emoji} <b>SEÑAL {dir_es}</b>{type_tag}\n"
        f"Par: <b>{pair}</b>\n"
        f"Precio entrada: <b>{price:,.2f} USDT</b>\n"
        f"{size_ln}"
        f"Stop Loss:   {sl:,.2f} USDT  ({abs(price-sl)/price*100:.2f}%)\n"
        f"Take Profit: {tp:,.2f} USDT  ({abs(tp-price)/price*100:.2f}%)\n"
        f"Score: {score} | ATR: {atr:.0f}"
    )


def _tg_update(pair: str, side: str, msg: str, sl: float, tp: float,
               pnl_float: float = None):
    pnl_ln = f"PnL flotante: <b>{pnl_float:+.2f} USDT</b>\n" if pnl_float is not None else ""
    send_telegram(
        f"⚙️ <b>ACTUALIZACIÓN {side} {pair}</b>\n"
        f"{msg}\n"
        f"{pnl_ln}"
        f"Nuevo SL: {sl:,.2f} USDT\n"
        f"Nuevo TP: {tp:,.2f} USDT"
    )


def _tg_close(side: str, pair: str, price: float, pnl: float,
              pnl_pct: float, reason: str, balance: float):
    emoji   = "✅" if pnl >= 0 else "❌"
    res     = "GANANCIA" if pnl >= 0 else "PÉRDIDA"
    reason_es = {
        "TAKE_PROFIT":   "Take Profit alcanzado",
        "STOP_LOSS":     "Stop Loss tocado",
        "SENAL_BAJISTA": "Señal bajista",
        "SENAL_ALCISTA": "Señal alcista",
    }.get(reason, reason)
    send_telegram(
        f"{emoji} <b>CERRAR {side} — {res}</b>\n"
        f"Par: <b>{pair}</b>\n"
        f"Precio cierre: <b>{price:,.2f} USDT</b>\n"
        f"PnL: <b>{pnl:+.2f} USDT ({pnl_pct:+.2f}%)</b>\n"
        f"Motivo: {reason_es}\n"
        f"Balance: {balance:,.2f} USDT"
    )


# =============================================================================
# RUN LIVE
# =============================================================================

def run_live(exchange, pair: str, interval: int, risk_profile: dict,
             strategy, min_hold_candles: int = 0,
             profile_name: Optional[str] = None):
    """Loop principal para modo live (paper trading).

    strategy : objeto que implementa get_signal(df_ltf, htf_context, live_extras) -> Signal
               y la propiedad .timeframe (str, e.g. '15m' o '1h')
    """
    from v6.core.bot_risk import (
        load_winrate_table, _merge_winrate_tables, build_winrate_table, save_winrate_table,
    )
    from v6.core.bot_sentiment import (
        fetch_sentiment, fetch_fear_greed, fetch_macro_correlations, fetch_funding_oi,
        fetch_orderbook_signals,
    )

    slug       = profile_name or pair.replace("/", "_")
    state_file = f"paper_{slug}_state.json"
    state      = load_state(state_file)
    timeframe  = strategy.timeframe

    _state_dir       = os.getenv("STATE_DIR", ".")
    _live_wrt_path   = os.path.join(_state_dir, f"winrate_{slug}.json")
    _init_wrt_path   = f"winrate_{slug}.json"
    _init_wrt        = load_winrate_table(_init_wrt_path)
    if os.path.exists(_live_wrt_path) and _live_wrt_path != _init_wrt_path:
        _live_wrt = load_winrate_table(_live_wrt_path)
    else:
        _live_wrt = dict(_init_wrt)
    _prev_close_count = len([t for t in state.get("trades", []) if t["action"].startswith("CLOSE_")])

    if profile_name:
        logger.log_file = f"paper_{slug}.log"

    print("\n" + "=" * 70)
    print(f"  Bot v6 [{strategy.__class__.__name__}] — {pair} ({timeframe}) — perfil: {slug}")
    print(f"  MS={risk_profile['min_score']} | SL={risk_profile['stop_loss_atr_mult']}×ATR | "
          f"TP={risk_profile['take_profit_atr_mult']}×ATR | Risk={risk_profile['risk_pct']*100:.1f}%/trade")
    print(f"  Balance: {state['balance_usdt']:.2f} USDT | PnL: {state['stats']['total_pnl']:+.2f}")
    print("=" * 70 + "\n")

    # Caches para datos externos
    sentiment_cache  = {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral", "news": []}
    fear_greed_cache = {"value": 50, "label": "neutral", "bull_mod": 5, "bear_mod": 5}
    funding_cache    = {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3}
    ob_cache         = {"support_walls": [], "resistance_walls": [], "bull_mod": 0, "bear_mod": 0}
    macro_corr_cache = {"bull_mod": 0, "bear_mod": 0, "detail": {}}
    last_sentiment   = datetime.min
    last_fg          = datetime.min
    last_funding     = datetime.min
    last_ob          = datetime.min
    last_macro       = datetime.min

    while True:
        try:
            now = datetime.now()

            # Actualización Fear & Greed (cada 10 min)
            if now - last_fg > timedelta(minutes=10):
                fear_greed_cache = fetch_fear_greed()
                last_fg = now

            # Sentimiento noticias (cada 5 min)
            if now - last_sentiment > timedelta(minutes=5):
                sentiment_cache = fetch_sentiment("BTC/USDT")
                last_sentiment = now

            # Funding Rate (cada 15 min)
            if now - last_funding > timedelta(minutes=15):
                funding_cache = fetch_funding_oi(exchange, pair)
                last_funding = now

            # Macro correlaciones (cada 60 min)
            if now - last_macro > timedelta(minutes=60):
                macro_corr_cache = fetch_macro_correlations()
                last_macro = now

            # Datos LTF y señal de la estrategia
            df_ltf = fetch_ohlcv(exchange, pair, timeframe, limit=300)
            state["current_candle_index"] = int(df_ltf["timestamp"].iloc[-1].timestamp())
            current_price = float(df_ltf["close"].iloc[-1])

            # Order book (cada minuto)
            if now - last_ob > timedelta(minutes=1):
                ob_cache = fetch_orderbook_signals(exchange, pair, current_price)
                last_ob = now

            live_extras = {
                "sentiment":   sentiment_cache,
                "fear_greed":  fear_greed_cache,
                "funding":     funding_cache,
                "orderbook":   ob_cache,
                "macro_corr":  macro_corr_cache,
            }
            signal = strategy.get_signal(df_ltf, live_extras)

            atr    = signal.technical.get("details", {}).get("atr", 0)
            scores = {"bullish_total": signal.bull_score, "bearish_total": signal.bear_score}

            # SL/TP primero (siempre se evalúan)
            sl_tp_msg = check_sl_tp(state, pair, current_price, risk_profile, atr=atr, scores=scores)
            if sl_tp_msg:
                logger.log(f">> {sl_tp_msg}")

            # Aprendizaje adaptativo: actualizar tabla si hay cierres nuevos
            close_count = len([t for t in state.get("trades", []) if t["action"].startswith("CLOSE_")])
            if close_count > _prev_close_count:
                new_live = build_winrate_table(state["trades"])
                _live_wrt = _merge_winrate_tables(_init_wrt, new_live)
                save_winrate_table(_live_wrt, _live_wrt_path)
                _prev_close_count = close_count

            # Decisión de trading
            decision = make_decision(
                state, pair, current_price, atr, signal, risk_profile,
                min_hold_candles=min_hold_candles,
                current_candle_index=state["current_candle_index"],
                winrate_table=_live_wrt,
                timestamp=now,
            )
            if decision:
                logger.log(f">> {decision}")

            save_state(state, state_file)

        except KeyboardInterrupt:
            logger.log("Bot detenido por el usuario")
            save_state(state, state_file)
            break
        except Exception as e:
            logger.log(f"Error en ciclo: {e}", level="ERROR")

        time.sleep(interval)


# =============================================================================
# RUN BACKTEST
# =============================================================================

def run_backtest(exchange, pair: str, days: int, risk_profile: dict,
                 strategy, entry_advantage: int = 15,
                 min_hold_candles: int = 0, auto_regime: bool = True,
                 _df_override: Optional[pd.DataFrame] = None,
                 _daily_sentiment: Optional[dict] = None,
                 _daily_macro_corr: Optional[dict] = None,
                 continuous_learning: bool = False) -> dict:
    """Backtesting sobre datos históricos.

    strategy : misma interfaz que en run_live — get_signal(df_slice, live_extras) -> Signal
    """
    from v6.core.bot_risk import (
        load_winrate_table, build_winrate_table, _merge_winrate_tables, save_winrate_table,
        get_learned_bonus, _make_condition_key,
    )
    from v6.core.bot_sentiment import load_fear_greed_sentiment

    timeframe = strategy.timeframe

    _root = Path(__file__).resolve().parents[2]  # tr/

    if _df_override is not None:
        df_full = _df_override.copy()
    else:
        df_full = fetch_historical_ohlcv(exchange, pair, timeframe, days)
        if timeframe == "1h":
            from v6.strategies.bot_swing import _precompute_1h_indicators
            df_full = _precompute_1h_indicators(df_full)
        else:
            from v6.core.bot_indicators import precompute_indicators
            df_full = precompute_indicators(df_full)

    _fg_path = _root / "data" / "fear_greed_historical.json"
    fg_data  = load_fear_greed_sentiment(str(_fg_path)) if _fg_path.exists() else {}
    daily_sent  = _daily_sentiment or {}
    daily_macro = _daily_macro_corr or {}

    state = load_state("__nonexistent__")   # estado fresco (fuerza defaults)
    state["peak_balance"] = state["balance_usdt"]

    slug = pair.replace("/", "_").replace(":", "_")
    _wrt_path   = _root / "results" / f"winrate_{slug}_moderate.json"
    initial_wrt = load_winrate_table(str(_wrt_path)) if _wrt_path.exists() else {}
    live_wrt    = dict(initial_wrt) if continuous_learning else {}

    warmup = 100
    n      = len(df_full)

    for i in range(warmup, n):
        row  = df_full.iloc[i]
        prev = df_full.iloc[i - 1]
        ts   = pd.Timestamp(row["timestamp"])
        date_str = str(ts.date())

        reset_daily_counter(state, date_str)
        state["current_candle_index"] = i

        current_price = float(row["close"])
        df_slice = df_full.iloc[max(0, i - 299):i + 1]

        # Datos externos del día (backtest usa datos históricos cacheados)
        day_sent  = daily_sent.get(date_str, {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"})
        day_fg    = fg_data.get(date_str,    {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"})
        day_macro = daily_macro.get(date_str, {"bull_mod": 0, "bear_mod": 0})

        live_extras = {
            "sentiment":  day_sent,
            "fear_greed": day_fg,
            "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
            "orderbook":  {"bull_mod": 0, "bear_mod": 0},
            "macro_corr": day_macro,
        }

        signal = strategy.get_signal(df_slice, live_extras, row=row)

        if auto_regime:
            rp_effective = apply_regime(risk_profile, signal.regime)
        else:
            rp_effective = risk_profile

        atr    = signal.technical.get("details", {}).get("atr", 0)
        scores = {"bullish_total": signal.bull_score, "bearish_total": signal.bear_score}

        sl_tp_msg = check_sl_tp(state, pair, current_price, rp_effective, atr=atr, scores=scores)
        if sl_tp_msg:
            logger.log(f"[BT] {sl_tp_msg}")

        if continuous_learning:
            close_count = len([t for t in state.get("trades", []) if t["action"].startswith("CLOSE_")])
            if close_count > 0 and close_count % 5 == 0:
                new_live = build_winrate_table(state["trades"])
                live_wrt = _merge_winrate_tables(initial_wrt, new_live)

        make_decision(
            state, pair, current_price, atr, signal, rp_effective,
            verbose=False,
            min_hold_candles=min_hold_candles,
            current_candle_index=i,
            winrate_table=live_wrt if continuous_learning else {},
            timestamp=ts,
        )

    # Si queda posición abierta al final del backtest, liquidar a último precio
    if state.get("position"):
        pos   = state["position"]
        last_price = float(df_full.iloc[-1]["close"])
        close_position(state, pair, last_price, "END_OF_BACKTEST")

    total_trades = state["stats"]["wins"] + state["stats"]["losses"]
    wr = state["stats"]["wins"] / total_trades * 100 if total_trades else 0
    logger.log(
        f"[BACKTEST] PnL={state['stats']['total_pnl']:+.2f} USDT | "
        f"WR={wr:.1f}% | Trades={total_trades} | "
        f"DD={state.get('max_drawdown_seen', 0):.1f}%"
    )
    return {
        "stats":              state["stats"],
        "final_balance":      state["balance_usdt"],
        "max_drawdown_seen":  state.get("max_drawdown_seen", 0.0),
        "trades":             state["trades"],
    }
