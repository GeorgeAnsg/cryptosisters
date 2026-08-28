"""
V11 — Backtest con entradas por orden límite (limit entry).

En vez de entrar a mercado al precio de cierre de la vela señal,
se coloca una orden límite X% por debajo (LONG) o por encima (SHORT).
Si el precio toca el límite en las siguientes N velas → entrada al precio límite.
Si no → trade cancelado.

Compara 4 configs:
  V10 baseline       — entrada a mercado, step_mult=1.0
  V11 offset=0.10%   — límite 0.10% de mejora
  V11 offset=0.20%   — límite 0.20% de mejora
  V11 offset=0.35%   — límite 0.35% de mejora

Cada config con timeout de 4 velas (1h) y 8 velas (2h).

Run: python v11/backtest.py
"""

import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import v6.core.bot_core as _bc
_bc._tg_update = lambda *a, **k: None

from v6.core.bot_core import (
    load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v7.strategy_ml import StrategyML

LOCAL_BTC  = ROOT / "data" / "btc_15m_full.csv"
LOCAL_ETH  = ROOT / "data" / "eth_2023_2026.csv"
LOCAL_SOL  = ROOT / "data" / "sol_15m_full.csv"
MODEL_DIR  = ROOT / "v7" / "models"
TEST_START = "2025-01-01"

V10_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}
TP_DYNAMIC = {
    ("bull", True): 5.0, ("bull", False): 4.5,
    ("neutral", True): 3.5, ("neutral", False): 3.5,
    ("bear", True): 4.5, ("bear", False): 4.0,
}

def dynamic_tp(signal):
    try:
        raw = signal.technical.get("details", {}).get("adx", 0) or 0
        adx = float(str(raw).split()[0]) if isinstance(raw, str) else float(raw)
    except: adx = 0.0
    return TP_DYNAMIC.get((signal.regime, adx >= 25), 4.0)

def make_strategy():
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    s.feature_cols = meta["feature_cols"]
    return s


def run_market(df, pair):
    """V10 baseline — entrada a mercado."""
    state = load_state("__nonexistent__")
    peak_eq = 1000.0; max_dd = 0.0
    strat = make_strategy()

    for i in range(100, len(df)):
        row = df.iloc[i]
        ts  = pd.Timestamp(row["timestamp"])
        reset_daily_counter(state, str(ts.date()))
        state["current_candle_index"] = i
        price = float(row["close"])
        df_slice = df.iloc[max(0, i-299):i+1]
        live_extras = _live_extras()
        signal = strat.get_signal(df_slice, live_extras, row=row)
        rp = apply_regime(V10_RISK, signal.regime)
        rp["take_profit_atr_mult"] = dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0)
        check_sl_tp(state, pair, price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, price, atr, signal, rp,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)
        pos = state.get("position")
        eq  = state["balance_usdt"] + pos["amount"]*pos["entry_price"] if pos else state["balance_usdt"]
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")
    return _stats(state, max_dd)


def run_limit(df, pair, offset_pct, timeout_candles):
    """
    Simula entradas por orden límite.
    Offset: % de mejora sobre el precio de señal.
    Timeout: máx velas para que se ejecute el límite.
    Aproximación con datos 15m: si el LOW de la vela toca el límite → fill.
    """
    strat = make_strategy()
    n = len(df)

    # Pre-computar señales para todas las velas (para saber dónde entrar)
    signals_cache = {}

    # Estado manual del backtest (no usamos run_live, simulamos nosotros)
    balance    = 1000.0
    peak_eq    = 1000.0
    max_dd     = 0.0
    position   = None     # dict con entry_price, sl, tp, side, amount, sl_dist, tp_extensions
    pending    = None     # dict: {limit_price, side, signal, rp, atr, candle_open}
    wins = losses = 0
    total_longs = total_shorts = 0
    long_wins = short_wins = 0
    best_trade = worst_trade = 0.0
    all_pnls = []
    skipped = filled = 0

    for i in range(100, n):
        row   = df.iloc[i]
        price = float(row["close"])
        low   = float(row["low"])
        high  = float(row["high"])
        ts    = pd.Timestamp(row["timestamp"])

        # ── Gestión de posición abierta ────────────────────────────────────────
        if position is not None:
            pos = position
            sl, tp = pos["sl"], pos["tp"]
            side   = pos["side"]

            # Comprobar SL/TP con high/low de la vela
            hit_sl = (side == "LONG"  and low  <= sl) or (side == "SHORT" and high >= sl)
            hit_tp = (side == "LONG"  and high >= tp) or (side == "SHORT" and low  <= tp)

            if hit_sl or hit_tp:
                exit_price = sl if hit_sl else tp
                pnl = (exit_price - pos["entry"]) * pos["amount"] if side == "LONG" \
                      else (pos["entry"] - exit_price) * pos["amount"]
                balance += pnl
                all_pnls.append(pnl)
                if pnl > 0:
                    wins += 1
                    if side == "LONG":  long_wins  += 1
                    else:               short_wins += 1
                    if pnl > best_trade:  best_trade  = pnl
                else:
                    losses += 1
                    if pnl < worst_trade: worst_trade = pnl
                position = None
                pending  = None  # cancelar cualquier límite pendiente

        # ── Comprobar si el límite pendiente se ejecuta ────────────────────────
        if position is None and pending is not None:
            candles_waited = i - pending["candle_open"]
            lp = pending["limit_price"]
            side = pending["side"]
            filled_now = (side == "LONG"  and low  <= lp) or \
                         (side == "SHORT" and high >= lp)

            if filled_now:
                # Calcular SL/TP desde el precio de entrada (el límite)
                entry  = lp
                atr    = pending["atr"]
                rp     = pending["rp"]
                sl_dist = atr * rp["stop_loss_atr_mult"]
                tp_dist = atr * rp["take_profit_atr_mult"]
                sl = entry - sl_dist if side == "LONG" else entry + sl_dist
                tp = entry + tp_dist if side == "LONG" else entry - tp_dist
                cost   = entry * min(rp["risk_pct"] * balance / sl_dist, balance * rp["max_cost_pct"] / entry)
                amount = cost / entry
                position = {"side": side, "entry": entry, "sl": sl, "tp": tp,
                            "amount": amount, "entry_price": entry}
                if side == "LONG": total_longs  += 1
                else:              total_shorts += 1
                pending = None
                filled += 1

            elif candles_waited >= timeout_candles:
                pending = None
                skipped += 1

        # ── Generar señal y crear límite si no hay posición ni límite ──────────
        if position is None and pending is None:
            df_slice = df.iloc[max(0, i-299):i+1]
            live = _live_extras()
            signal = strat.get_signal(df_slice, live, row=row)
            rp = apply_regime(V10_RISK, signal.regime)
            rp["take_profit_atr_mult"] = dynamic_tp(signal)
            atr = signal.technical.get("details", {}).get("atr", 0) or 1.0

            bs, brs = signal.bull_score, signal.bear_score
            min_sc  = rp["min_score"]
            adv     = rp["entry_advantage"]

            want_long  = bs >= min_sc and bs - brs >= adv
            want_short = brs >= min_sc and brs - bs >= adv

            if want_long or want_short:
                side = "LONG" if want_long else "SHORT"
                if side == "LONG":
                    lp = price * (1 - offset_pct / 100)
                else:
                    lp = price * (1 + offset_pct / 100)
                pending = {
                    "limit_price": lp, "side": side,
                    "signal": signal, "rp": rp, "atr": atr,
                    "candle_open": i,
                }

        # ── Equity y drawdown ──────────────────────────────────────────────────
        eq = balance + position["amount"] * position["entry"] if position else balance
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    # Cerrar posición abierta al final
    if position:
        exit_price = float(df.iloc[-1]["close"])
        pnl = (exit_price - position["entry"]) * position["amount"] if position["side"] == "LONG" \
              else (position["entry"] - exit_price) * position["amount"]
        balance += pnl
        all_pnls.append(pnl)
        if pnl > 0: wins += 1
        else:       losses += 1

    total = wins + losses
    wr    = wins / total * 100 if total else 0
    wins_p  = [p for p in all_pnls if p > 0]
    loses_p = [p for p in all_pnls if p <= 0]
    pf = abs(sum(wins_p)/sum(loses_p)) if sum(loses_p) != 0 else 99.0
    fill_rate = filled / (filled + skipped) * 100 if (filled + skipped) > 0 else 0

    return {
        "pnl":       round(balance - 1000, 2),
        "wr":        round(wr, 1),
        "trades":    total,
        "dd":        round(max_dd, 1),
        "pf":        round(pf, 2),
        "fill_rate": round(fill_rate, 1),
        "filled":    filled,
        "skipped":   skipped,
    }


def _live_extras():
    return {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
        "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }


def _stats(state, max_dd):
    st    = state["stats"]
    total = st["wins"] + st["losses"]
    wr    = st["wins"] / total * 100 if total else 0
    pnls  = [t["pnl"] for t in state["trades"] if t["action"].startswith("CLOSE_") and "pnl" in t]
    wins_p  = [p for p in pnls if p > 0]
    loses_p = [p for p in pnls if p <= 0]
    pf = abs(sum(wins_p)/sum(loses_p)) if sum(loses_p) != 0 else 99.0
    return {
        "pnl":    round(state["balance_usdt"] - 1000, 2),
        "wr":     round(wr, 1),
        "trades": total,
        "dd":     round(max_dd, 1),
        "pf":     round(pf, 2),
        "fill_rate": 100.0,
        "filled": total,
        "skipped": 0,
    }


if __name__ == "__main__":
    print(f"\n{'='*72}")
    print(f"  V11 BACKTEST — LIMIT ENTRY vs MARKET ENTRY | OOS {TEST_START} → hoy")
    print(f"  Offset: % de mejora sobre precio señal | Timeout: velas de espera")
    print(f"{'='*72}\n")

    datasets = [
        ("BTC", LOCAL_BTC, "BTC/USDT:USDT"),
        ("ETH", LOCAL_ETH, "ETH/USDT:USDT"),
        ("SOL", LOCAL_SOL, "SOL/USDT:USDT"),
    ]

    print("  Cargando datos...")
    dfs = {}
    for label, path, pair in datasets:
        df = pd.read_csv(path, parse_dates=["timestamp"])
        df = df[df["timestamp"] >= TEST_START].reset_index(drop=True)
        dfs[label] = (precompute_indicators(df), pair)
    print()

    OFFSETS  = [0.10, 0.20, 0.35]
    TIMEOUTS = [4, 8]   # velas × 15m = 1h / 2h

    hdr = f"  {'Config':<32} {'BTC PnL':>8} {'WR':>6} {'ETH PnL':>8} {'WR':>6} {'SOL PnL':>8} {'WR':>6} {'Total':>8}  {'Fill%':>6}"
    sep = "  " + "─" * (len(hdr)-2)
    print(hdr)
    print(sep)

    # Baseline V10
    print()
    btc_b = run_market(dfs["BTC"][0].copy(), dfs["BTC"][1])
    eth_b = run_market(dfs["ETH"][0].copy(), dfs["ETH"][1])
    sol_b = run_market(dfs["SOL"][0].copy(), dfs["SOL"][1])
    tot_b = btc_b["pnl"] + eth_b["pnl"] + sol_b["pnl"]
    print(f"  {'V10 baseline (mercado)':<32} {btc_b['pnl']:>+8.0f} {btc_b['wr']:>5.1f}% "
          f"{eth_b['pnl']:>+8.0f} {eth_b['wr']:>5.1f}% "
          f"{sol_b['pnl']:>+8.0f} {sol_b['wr']:>5.1f}% "
          f"{tot_b:>+8.0f}  {'100%':>6}")

    best = {"total": tot_b, "label": "V10 baseline"}

    for timeout in TIMEOUTS:
        print()
        for offset in OFFSETS:
            label = f"V11 {offset:.2f}% timeout={timeout}v ({timeout//4}h)"
            results = {}
            for par, (df, pair) in dfs.items():
                results[par] = run_limit(df.copy(), pair, offset, timeout)
            tot = sum(r["pnl"] for r in results.values())
            avg_fill = sum(r["fill_rate"] for r in results.values()) / 3
            print(f"  {label:<32} "
                  f"{results['BTC']['pnl']:>+8.0f} {results['BTC']['wr']:>5.1f}% "
                  f"{results['ETH']['pnl']:>+8.0f} {results['ETH']['wr']:>5.1f}% "
                  f"{results['SOL']['pnl']:>+8.0f} {results['SOL']['wr']:>5.1f}% "
                  f"{tot:>+8.0f}  {avg_fill:>5.1f}%")
            if tot > best["total"]:
                best = {"total": tot, "label": label, "results": results}

    print(f"\n{sep}")
    if best["label"] == "V10 baseline":
        print(f"\n  RESULTADO: El limit entry NO mejora. V10 con mercado sigue siendo óptimo.")
    else:
        r = best["results"]
        print(f"\n  MEJOR CONFIG: {best['label']}")
        print(f"  BTC {r['BTC']['pnl']:+.0f} (WR {r['BTC']['wr']}%, fill {r['BTC']['fill_rate']}%)")
        print(f"  ETH {r['ETH']['pnl']:+.0f} (WR {r['ETH']['wr']}%, fill {r['ETH']['fill_rate']}%)")
        print(f"  SOL {r['SOL']['pnl']:+.0f} (WR {r['SOL']['wr']}%, fill {r['SOL']['fill_rate']}%)")
        print(f"  Total: {best['total']:+.0f} vs V10 baseline {tot_b:+.0f} "
              f"({'+'}{best['total']-tot_b:.0f} = {(best['total']-tot_b)/tot_b*100:+.1f}%)")
    print()
