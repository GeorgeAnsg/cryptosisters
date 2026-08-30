"""
V13 — Backtest comparativo: 3 formas de integrar VEXP en V12.

Estrategias probadas:
  baseline — V12 puro (sin VEXP)
  A        — Score bonus: +10 al score cuando VEXP tiene FVG activo en la misma dirección
  B        — FVG entry: si hay FVG activo, espera retroceso al FVG antes de entrar
  C        — SL ajustado: cuando VEXP confirma, usa 1.5×ATR en vez de 2.5×ATR

Periodos: Bear 2022 / Bull 2023-24 / OOS 2025-26

Run: python -m v13.backtest
"""

import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

import v6.core.bot_core as _bc
_bc.send_telegram = lambda *a, **k: None
_bc._tg_open      = lambda *a, **k: None
_bc._tg_update    = lambda *a, **k: None
_bc._tg_close     = lambda *a, **k: None

from v6.core.bot_core import (
    load_state, apply_regime, reset_daily_counter,
    check_sl_tp, make_decision, close_position,
)
from v6.core.bot_indicators import precompute_indicators
from v7.strategy_ml import StrategyML

from vexp.smc import (
    calc_atr, find_swings, get_recent_swings,
    detect_sweep, detect_fvg, check_fvg_entry,
    SWING_STRENGTH, MAX_FVG_WAIT, MAX_DISP_WAIT,
)

MODEL_DIR = ROOT / "v7" / "models"

_TP_MAP = {
    ("bull",    True):  5.0, ("bull",    False): 4.5,
    ("neutral", True):  3.5, ("neutral", False): 3.5,
    ("bear",    True):  4.5, ("bear",    False): 4.0,
}

def _dynamic_tp(signal):
    try:
        adx = float(signal.technical.get("details", {}).get("adx", 0) or 0)
    except Exception:
        adx = 0.0
    return _TP_MAP.get((signal.regime, adx >= 25), 4.0)

def _live_extras():
    return {
        "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
        "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
        "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
        "orderbook":  {"bull_mod": 0, "bear_mod": 0},
        "macro_corr": {"bull_mod": 0, "bear_mod": 0},
    }

def make_ml_strategy():
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        meta = json.load(f)
    s = StrategyML(model_path=str(MODEL_DIR / "v7_classifier_oos.pkl"), threshold=0.55)
    s.feature_cols = meta["feature_cols"]
    return s

def _base_risk():
    return {
        "risk_pct": 0.05, "max_cost_pct": 0.87,
        "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.5,
        "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
        "max_drawdown_pct": 0.25, "max_daily_loss_pct": 0.03,
        "trailing_stop": True, "trailing_step_mult": 1.0, "max_tp_extensions": 1,
        "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
    }

VEXP_SCORE_BONUS = 10   # A: puntos extra al score cuando VEXP confirma
VEXP_SL_MULT     = 1.5  # C: stop loss ajustado cuando VEXP confirma


class VexpState:
    """Máquina de estados VEXP (sweep → FVG) corriendo en paralelo."""

    def __init__(self, df_raw: pd.DataFrame):
        self.swing_highs, self.swing_lows = find_swings(df_raw, strength=SWING_STRENGTH)
        self.df_raw = df_raw
        self.pending_sweep = None
        self.pending_fvg   = None

    def step(self, i: int, atr_val: float):
        """Avanza un paso. Devuelve el FVG activo (o None)."""
        df = self.df_raw
        ts = df.iloc[i]["timestamp"]

        # Caducar FVG si lleva demasiado tiempo esperando
        if self.pending_fvg is not None:
            if i > self.pending_fvg.formed_at + MAX_FVG_WAIT:
                self.pending_fvg  = None
                self.pending_sweep = None

        # Caducar sweep si no aparece displacement
        if self.pending_sweep is not None and self.pending_fvg is None:
            if i > self.pending_sweep.idx + MAX_DISP_WAIT:
                self.pending_sweep = None

        # Fase 2: buscar displacement + FVG
        if self.pending_sweep is not None and self.pending_fvg is None:
            fvg = detect_fvg(df, self.pending_sweep, i)
            if fvg is not None:
                self.pending_fvg  = fvg
                self.pending_sweep = None

        # Fase 1: buscar sweep (solo si sin setup activo)
        if self.pending_sweep is None and self.pending_fvg is None:
            sh_list, sl_list = get_recent_swings(df, i, self.swing_highs, self.swing_lows)
            if sh_list or sl_list:
                sweep = detect_sweep(df, i, sh_list, sl_list, atr_val)
                if sweep is not None:
                    self.pending_sweep = sweep

        return self.pending_fvg

    def invalidate(self):
        """Llamar cuando se abre un trade — resetea el FVG consumido."""
        self.pending_fvg   = None
        self.pending_sweep = None


def run(df: pd.DataFrame, pair: str, mode: str) -> dict:
    """
    mode: 'baseline' | 'A' | 'B' | 'C'
    """
    state  = load_state("__nonexistent__")
    strat  = make_ml_strategy()
    peak_eq = 1000.0
    max_dd  = 0.0
    rp_base = _base_risk()

    # VEXP ATR y estado
    atr_series = calc_atr(df, period=14)
    vexp = VexpState(df)

    # Estado para modo B (FVG entry pendiente)
    fvg_pending_entry = None  # {'fvg': ..., 'rp': ..., 'signal': ..., 'atr': ..., 'since': i}

    for i in range(100, len(df)):
        row = df.iloc[i]
        ts  = pd.Timestamp(row["timestamp"])
        reset_daily_counter(state, str(ts.date()))
        state["current_candle_index"] = i
        price = float(row["close"])
        df_slice = df.iloc[max(0, i-299):i+1]

        atr_val = float(atr_series.iloc[i]) if not np.isnan(atr_series.iloc[i]) else 0.0

        signal = strat.get_signal(df_slice, _live_extras(), row=row)
        rp = apply_regime(rp_base, signal.regime)
        rp["take_profit_atr_mult"] = _dynamic_tp(signal)
        atr = signal.technical.get("details", {}).get("atr", 0) or 0

        # Avanzar VEXP
        active_fvg = vexp.step(i, atr_val) if mode != "baseline" else None

        # ── Modo B: gestionar entrada pendiente en FVG ────────────────────────
        if mode == "B" and fvg_pending_entry is not None:
            fpe = fvg_pending_entry
            # Cancelar si el FVG caducó o el trade ya se abrió por otro motivo
            if state.get("position") is not None:
                fvg_pending_entry = None
            elif i > fpe["since"] + MAX_FVG_WAIT or active_fvg is None:
                fvg_pending_entry = None
            else:
                # Comprobar si el precio toca el FVG
                fvg = fpe["fvg"]
                touched = False
                if fvg.side == "LONG"  and price <= fvg.fvg_high and price >= fvg.fvg_low:
                    touched = True
                elif fvg.side == "SHORT" and price >= fvg.fvg_low and price <= fvg.fvg_high:
                    touched = True

                if touched:
                    # Ejecutar entrada con el rp guardado
                    make_decision(state, pair, price, fpe["atr"], fpe["signal"], fpe["rp"],
                                  verbose=False, min_hold_candles=3,
                                  current_candle_index=i, winrate_table={}, timestamp=ts)
                    vexp.invalidate()
                    fvg_pending_entry = None

        check_sl_tp(state, pair, price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})

        if state.get("position") is None and fvg_pending_entry is None:
            # ── Aplicar modificaciones según modo ─────────────────────────────
            rp_call = dict(rp)

            if active_fvg is not None:
                fvg_dir = active_fvg.side  # 'LONG' o 'SHORT'

                if mode == "A":
                    # Bonus de score si VEXP confirma la dirección
                    if fvg_dir == "LONG":
                        signal.bull_score = min(100, signal.bull_score + VEXP_SCORE_BONUS)
                    else:
                        signal.bear_score = min(100, signal.bear_score + VEXP_SCORE_BONUS)

                elif mode == "B":
                    # Guardar entrada pendiente en FVG; no llamar make_decision ahora
                    fvg_pending_entry = {
                        "fvg":    active_fvg,
                        "rp":     rp_call,
                        "signal": signal,
                        "atr":    atr,
                        "since":  i,
                    }
                    # Calcular equity y continuar sin make_decision
                    pos = state.get("position")
                    eq  = state["balance_usdt"] + pos["amount"] * pos["entry_price"] if pos else state["balance_usdt"]
                    if eq > peak_eq: peak_eq = eq
                    dd = (peak_eq - eq) / peak_eq * 100
                    if dd > max_dd: max_dd = dd
                    continue

                elif mode == "C":
                    # SL más ajustado cuando VEXP confirma misma dirección
                    bull_winning = signal.bull_score > signal.bear_score
                    if (fvg_dir == "LONG" and bull_winning) or (fvg_dir == "SHORT" and not bull_winning):
                        rp_call["stop_loss_atr_mult"] = VEXP_SL_MULT

            make_decision(state, pair, price, atr, signal, rp_call,
                          verbose=False, min_hold_candles=3,
                          current_candle_index=i, winrate_table={}, timestamp=ts)

            # Si se abrió un trade en modo A/C, invalidar FVG
            if mode in ("A", "C") and state.get("position") is not None and active_fvg is not None:
                vexp.invalidate()

        # Equity tracking
        pos = state.get("position")
        eq  = state["balance_usdt"] + pos["amount"] * pos["entry_price"] if pos else state["balance_usdt"]
        if eq > peak_eq: peak_eq = eq
        dd = (peak_eq - eq) / peak_eq * 100
        if dd > max_dd: max_dd = dd

    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")

    st = state["stats"]
    total = st["wins"] + st["losses"]
    wr = st["wins"] / total * 100 if total else 0

    return {"pnl": round(state["balance_usdt"] - 1000, 2), "wr": round(wr, 1),
            "trades": total, "dd": round(max_dd, 1)}


PERIODS = [
    ("Bear 2022",    "2022-01-01", "2023-01-01"),
    ("Bull 2023-24", "2023-01-01", "2025-01-01"),
    ("OOS 2025-26",  "2025-01-01", "2026-09-01"),
]

DATASETS = [
    (ROOT / "data" / "btc_15m_full.csv", "BTC"),
]

MODES = [
    ("baseline", "V12 puro                    "),
    ("A",        "A — Score bonus (+10 VEXP)  "),
    ("B",        "B — FVG entry timing        "),
    ("C",        "C — SL ajustado (1.5x VEXP) "),
]


def main():
    all_dfs = {}
    for path, pair in DATASETS:
        if path.exists():
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            all_dfs[pair] = df
        else:
            print(f"[SKIP] {pair}: no encontrado")

    print(f"\nV13 — Comparativa de integración VEXP × V12")
    print(f"Par(es): {', '.join(all_dfs.keys())}\n")

    for period_name, start, end in PERIODS:
        print(f"\n{'='*66}")
        print(f"  PERIODO: {period_name}  ({start} → {end})")
        print(f"{'='*66}")
        print(f"  {'Config':<36} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6}")
        print(f"  {'-'*36} {'-'*8} {'-'*7} {'-'*6} {'-'*6}")

        totals = {mode: {"pnl": 0, "trades": 0, "wins": 0, "dd": 0.0}
                  for mode, _ in MODES}

        for pair, df_full in all_dfs.items():
            df = df_full[(df_full["timestamp"] >= start) & (df_full["timestamp"] < end)].reset_index(drop=True)
            if len(df) < 300:
                continue
            df = precompute_indicators(df)

            for mode, label in MODES:
                print(f"  [{pair}] {label.strip()}...", end=" ", flush=True)
                r = run(df, pair, mode)
                print(f"PnL={r['pnl']:,.0f}")
                t = totals[mode]
                t["pnl"]    += r["pnl"]
                t["trades"] += r["trades"]
                t["wins"]   += round(r["trades"] * r["wr"] / 100)
                t["dd"]      = max(t["dd"], r["dd"])

        print(f"\n  {'Config':<36} {'PnL':>8} {'Trades':>7} {'WR':>6} {'DD':>6}")
        print(f"  {'-'*36} {'-'*8} {'-'*7} {'-'*6} {'-'*6}")
        baseline_pnl = totals["baseline"]["pnl"]
        for mode, label in MODES:
            t = totals[mode]
            wr = t["wins"] / t["trades"] * 100 if t["trades"] else 0
            diff = f"  (+{t['pnl']-baseline_pnl:.0f})" if mode != "baseline" else ""
            print(f"  {label:<36} {t['pnl']:>8.0f} {t['trades']:>7} {wr:>5.1f}% {t['dd']:>5.1f}%{diff}")

    print()


if __name__ == "__main__":
    main()
