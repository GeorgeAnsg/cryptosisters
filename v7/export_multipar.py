"""
V7 — Exporta trade features para BTC + ETH + SOL combinados.
Usa Strategy15m (v6) como generador de señales base.
El ML se entrena para filtrar los trades de Strategy15m.

Output: v7/data/trade_features_multipar.csv

Run: python v7/export_multipar.py
"""
import sys, csv, math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from v6.core.bot_core import (
    load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v6.core.bot_sentiment import load_fear_greed_sentiment
from v6.strategies.strategy_15m import Strategy15m

RISK_PROFILE = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}

DATASETS = [
    ("BTC/USDT:USDT", ROOT / "data" / "btc_15m_full.csv"),
    ("ETH/USDT:USDT", ROOT / "data" / "eth_2023_2026.csv"),
    ("SOL/USDT:USDT", ROOT / "data" / "sol_15m_full.csv"),
]
START_DATE = "2023-01-01"
OUT_PATH   = ROOT / "v7" / "data" / "trade_features_multipar.csv"

FEATURE_COLS = [
    "ema9_ratio", "ema21_ratio", "ema50_ratio", "ema200_ratio",
    "rsi", "stochrsi_k", "stochrsi_d", "macd_h_norm",
    "adx", "adx_dmp_norm", "adx_dmn_norm", "bb_pct", "vol_ratio",
    "atr_contracted", "bull_engulf", "bear_engulf", "hammer", "shooting_star",
    "three_bull", "three_bear", "ms_bull", "ms_bear",
    "near_channel_top", "near_channel_bot", "hurst_acf1",
    "bull_score", "bear_score", "net_score", "regime_enc", "htf_rsi", "side_enc",
]


def _safe(v, default=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except: return default


def _extract(row, signal, side):
    price = _safe(row.get("close"), 1.0)
    atr   = _safe(row.get("atr"), 1.0) or 1.0
    ema9  = _safe(row.get("ema_9"),   price)
    ema21 = _safe(row.get("ema_21"),  price)
    ema50 = _safe(row.get("ema_50"),  price)
    ema200= _safe(row.get("ema_200"), price)
    bb_raw = row.get("BBP_20_2.0")
    if bb_raw is None or (isinstance(bb_raw, float) and math.isnan(bb_raw)):
        bbl = _safe(row.get("BBL_20_2.0"), price - atr)
        bbu = _safe(row.get("BBU_20_2.0"), price + atr)
        bb_pct = (price - bbl) / (bbu - bbl) if bbu > bbl else 0.5
    else:
        bb_pct = _safe(bb_raw, 0.5)
    adx = _safe(row.get("adx"), 0.0)
    net = signal.bull_score - signal.bear_score if side == "LONG" else signal.bear_score - signal.bull_score
    details = signal.technical.get("details", {})
    return {
        "ema9_ratio":    ema9  / price,
        "ema21_ratio":   ema21 / price,
        "ema50_ratio":   ema50 / price,
        "ema200_ratio":  ema200 / price,
        "rsi":           _safe(row.get("rsi"), 50.0),
        "stochrsi_k":    _safe(row.get("stochrsi_k"), 50.0),
        "stochrsi_d":    _safe(row.get("stochrsi_d"), 50.0),
        "macd_h_norm":   _safe(row.get("MACDh_12_26_9"), 0.0) / atr,
        "adx":           adx,
        "adx_dmp_norm":  _safe(row.get("adx_dmp"), 0.0) / (adx + 1e-9),
        "adx_dmn_norm":  _safe(row.get("adx_dmn"), 0.0) / (adx + 1e-9),
        "bb_pct":        bb_pct,
        "vol_ratio":     _safe(row.get("vol_ratio"), 1.0),
        "atr_contracted":_safe(row.get("atr_contracted"), 0.0),
        "bull_engulf":   _safe(row.get("bull_engulf"), 0.0),
        "bear_engulf":   _safe(row.get("bear_engulf"), 0.0),
        "hammer":        _safe(row.get("hammer"), 0.0),
        "shooting_star": _safe(row.get("shooting_star"), 0.0),
        "three_bull":    _safe(row.get("three_bull"), 0.0),
        "three_bear":    _safe(row.get("three_bear"), 0.0),
        "ms_bull":       _safe(row.get("ms_bull"), 0.0),
        "ms_bear":       _safe(row.get("ms_bear"), 0.0),
        "near_channel_top": _safe(row.get("near_channel_top"), 0.0),
        "near_channel_bot": _safe(row.get("near_channel_bot"), 0.0),
        "hurst_acf1":    _safe(row.get("hurst_acf1"), 0.5),
        "bull_score":    signal.bull_score,
        "bear_score":    signal.bear_score,
        "net_score":     net,
        "regime_enc":    {"bull": 1, "neutral": 0, "bear": -1}.get(signal.regime, 0),
        "htf_rsi":       _safe(details.get("htf_rsi"), 50.0),
        "side_enc":      1 if side == "LONG" else -1,
    }


def export_pair(pair, csv_path, strategy):
    print(f"\n  [{pair}] Cargando datos...")
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    df = df[df["timestamp"] >= START_DATE].reset_index(drop=True)
    df = precompute_indicators(df)
    print(f"  [{pair}] {len(df):,} velas desde {START_DATE}")

    fg_path = ROOT / "data" / "fear_greed_historical.json"
    fg_data = load_fear_greed_sentiment(str(fg_path)) if fg_path.exists() else {}

    state = load_state("__nonexistent__")
    pending_opens = {}
    completed = []
    open_seq = 0

    def _process_close(ts, price):
        last = next((t for t in reversed(state["trades"]) if t["action"].startswith("CLOSE_")), None)
        if not last: return
        side_c = last["action"].replace("CLOSE_", "")
        pnl    = last.get("pnl", 0.0)
        key    = next((k for k in sorted(pending_opens, reverse=True)
                       if pending_opens[k]["side"] == side_c), None)
        if key is not None:
            entry = pending_opens.pop(key)
            completed.append({
                "entry_ts": entry["entry_ts"], "exit_ts": str(ts),
                "side": side_c, "entry_price": entry["entry_price"],
                "exit_price": price, "pnl": round(pnl, 4),
                "won": 1 if pnl > 0 else 0,
                "close_reason": last.get("reason", ""),
                **entry["features"],
            })

    for i in range(100, len(df)):
        row   = df.iloc[i]
        ts    = pd.Timestamp(row["timestamp"])
        price = float(row["close"])
        reset_daily_counter(state, str(ts.date()))
        state["current_candle_index"] = i
        df_slice = df.iloc[max(0, i-299):i+1]
        day_fg = fg_data.get(str(ts.date()), {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"})
        live_extras = {
            "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
            "fear_greed": day_fg,
            "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
            "orderbook":  {"bull_mod": 0, "bear_mod": 0},
            "macro_corr": {"bull_mod": 0, "bear_mod": 0},
        }
        signal = strategy.get_signal(df_slice, live_extras, row=row)
        rp = apply_regime(RISK_PROFILE, signal.regime)
        atr = signal.technical.get("details", {}).get("atr", 0)
        scores = {"bullish_total": signal.bull_score, "bearish_total": signal.bear_score}

        n_before = len(state["trades"])
        check_sl_tp(state, pair, price, rp, atr=atr, scores=scores)
        for t in state["trades"][n_before:]:
            if t["action"].startswith("CLOSE_"): _process_close(ts, price)

        n_before = len(state["trades"])
        make_decision(state, pair, price, atr, signal, rp, verbose=False,
                      min_hold_candles=0, current_candle_index=i, winrate_table={}, timestamp=ts)
        for t in state["trades"][n_before:]:
            if t["action"].startswith("OPEN_"):
                open_seq += 1
                side = t["action"].replace("OPEN_", "")
                pending_opens[open_seq] = {
                    "features": _extract(row, signal, side),
                    "side": side, "entry_price": price, "entry_ts": str(ts),
                }
            elif t["action"].startswith("CLOSE_"):
                _process_close(ts, price)

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")

    wins = sum(1 for t in completed if t["won"])
    pct  = wins/len(completed)*100 if completed else 0
    print(f"  [{pair}] {len(completed)} trades capturados | WR bruto={pct:.1f}%")
    return completed


if __name__ == "__main__":
    import v6.core.bot_core as _bc
    _bc._tg_update = lambda *a, **k: None

    print(f"\n{'='*60}")
    print(f"  EXPORTANDO TRADE FEATURES — BTC + ETH + SOL")
    print(f"  Desde {START_DATE}. Strategy15m (v6) como base.")
    print(f"{'='*60}")

    strategy = Strategy15m()
    all_trades = []

    for pair, csv_path in DATASETS:
        if not csv_path.exists():
            print(f"  [{pair}] AVISO: {csv_path} no existe, saltando.")
            continue
        trades = export_pair(pair, csv_path, strategy)
        all_trades += trades

    if not all_trades:
        print("  No hay trades. Saliendo.")
        sys.exit(1)

    # Guardar CSV combinado
    all_keys = ["entry_ts", "exit_ts", "side", "entry_price", "exit_price",
                "pnl", "won", "close_reason"] + FEATURE_COLS
    with open(OUT_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_trades)

    total_wins = sum(1 for t in all_trades if t["won"])
    print(f"\n  TOTAL: {len(all_trades)} trades | WR bruto={total_wins/len(all_trades)*100:.1f}%")
    print(f"  Guardado → {OUT_PATH}")
    print(f"\n  Siguiente paso: python v7/train_oos.py --features {OUT_PATH}\n")
