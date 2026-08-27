"""
V7 — ML-filtered strategy wrapper.

Wraps Strategy15m and adds a pre-trade ML classifier gate.
Only trades pass that the XGBoost model rates with P(win) >= threshold.
"""

import math
import pickle
import json
import numpy as np
from pathlib import Path

from v6.strategies.strategy_15m import Strategy15m
from v6.core.bot_core import Signal

ROOT      = Path(__file__).resolve().parents[1]
META_PATH = ROOT / "v7" / "models" / "v7_classifier_meta.json"


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _build_feature_vector(row, signal, side: str, feature_cols: list) -> list:
    """Build feature vector matching train_classifier.py's _extract_features."""
    price = _safe_float(row.get("close"), 1.0)
    atr   = _safe_float(row.get("atr"),   1.0) or 1.0

    ema9   = _safe_float(row.get("ema_9"),   price)
    ema21  = _safe_float(row.get("ema_21"),  price)
    ema50  = _safe_float(row.get("ema_50"),  price)
    ema200 = _safe_float(row.get("ema_200"), price)

    bb_pct_raw = row.get("BBP_20_2.0")
    if bb_pct_raw is None or (isinstance(bb_pct_raw, float) and math.isnan(bb_pct_raw)):
        bbl = _safe_float(row.get("BBL_20_2.0"), price - atr)
        bbu = _safe_float(row.get("BBU_20_2.0"), price + atr)
        bb_pct = (price - bbl) / (bbu - bbl) if bbu > bbl else 0.5
    else:
        bb_pct = _safe_float(bb_pct_raw, 0.5)

    macd_h = _safe_float(row.get("MACDh_12_26_9"), 0.0)
    adx    = _safe_float(row.get("adx"), 0.0)
    adx_p  = _safe_float(row.get("adx_dmp"), 0.0)
    adx_n  = _safe_float(row.get("adx_dmn"), 0.0)

    regime_map = {"bull": 1, "neutral": 0, "bear": -1}
    regime_enc = regime_map.get(signal.regime, 0)

    details = signal.technical.get("details", {})
    htf_rsi = _safe_float(details.get("htf_rsi"), 50.0)

    net_score = signal.bull_score - signal.bear_score if side == "LONG" else signal.bear_score - signal.bull_score

    all_features = {
        "ema9_ratio":       ema9  / price,
        "ema21_ratio":      ema21 / price,
        "ema50_ratio":      ema50 / price,
        "ema200_ratio":     ema200 / price,
        "rsi":              _safe_float(row.get("rsi"), 50.0),
        "stochrsi_k":       _safe_float(row.get("stochrsi_k"), 50.0),
        "stochrsi_d":       _safe_float(row.get("stochrsi_d"), 50.0),
        "macd_h_norm":      macd_h / atr,
        "adx":              adx,
        "adx_dmp_norm":     adx_p / (adx + 1e-9),
        "adx_dmn_norm":     adx_n / (adx + 1e-9),
        "bb_pct":           bb_pct,
        "vol_ratio":        _safe_float(row.get("vol_ratio"), 1.0),
        "atr_contracted":   _safe_float(row.get("atr_contracted"), 0.0),
        "bull_engulf":      _safe_float(row.get("bull_engulf"), 0.0),
        "bear_engulf":      _safe_float(row.get("bear_engulf"), 0.0),
        "hammer":           _safe_float(row.get("hammer"), 0.0),
        "shooting_star":    _safe_float(row.get("shooting_star"), 0.0),
        "three_bull":       _safe_float(row.get("three_bull"), 0.0),
        "three_bear":       _safe_float(row.get("three_bear"), 0.0),
        "ms_bull":          _safe_float(row.get("ms_bull"), 0.0),
        "ms_bear":          _safe_float(row.get("ms_bear"), 0.0),
        "near_channel_top": _safe_float(row.get("near_channel_top"), 0.0),
        "near_channel_bot": _safe_float(row.get("near_channel_bot"), 0.0),
        "hurst_acf1":       _safe_float(row.get("hurst_acf1"), 0.5),
        "bull_score":       signal.bull_score,
        "bear_score":       signal.bear_score,
        "net_score":        net_score,
        "regime_enc":       regime_enc,
        "htf_rsi":          htf_rsi,
        "side_enc":         1 if side == "LONG" else -1,
    }
    return [all_features[f] for f in feature_cols]


class StrategyML(Strategy15m):
    """Strategy15m + ML gate: only passes trades with P(win) >= threshold."""

    def __init__(self, model_path: str = None, threshold: float = None):
        super().__init__()
        self.clf          = None
        self.feature_cols = []
        self.threshold    = 0.55
        self._ml_stats    = {"checked": 0, "passed": 0, "blocked": 0}
        self._load_model(model_path)
        if threshold is not None:
            self.threshold = threshold

    def _load_model(self, model_path=None):
        try:
            with open(META_PATH) as f:
                meta = json.load(f)
            path = model_path or meta["model_path"]
            with open(path, "rb") as f:
                self.clf = pickle.load(f)
            self.feature_cols = meta["feature_cols"]
            self.threshold    = meta.get("threshold", 0.55)
            print(f"[StrategyML] Loaded {meta['model_type']} | threshold={self.threshold} | "
                  f"features={len(self.feature_cols)} | CV WR@0.55={meta.get('cv_wr55_mean')}%")
        except Exception as e:
            print(f"[StrategyML] WARNING: could not load model ({e}). Running without ML filter.")

    def get_signal(self, df_ltf, live_extras, row=None, min_score: int = 58):
        signal = super().get_signal(df_ltf, live_extras, row=row)

        if self.clf is None:
            return signal

        # Only apply ML gate if the signal is strong enough to trigger a trade
        bull_candidate = signal.bull_score >= min_score and not signal.htf_blocks_long
        bear_candidate = signal.bear_score >= min_score and not signal.htf_blocks_short

        if not bull_candidate and not bear_candidate:
            return signal

        # Use the row passed (backtest) or last row of df_ltf (live)
        actual_row = row if row is not None else df_ltf.iloc[-1]

        self._last_prob = None  # reset each signal evaluation

        if bull_candidate:
            fv   = _build_feature_vector(actual_row, signal, "LONG", self.feature_cols)
            prob = self.clf.predict_proba([fv])[0][1]
            self._ml_stats["checked"] += 1
            if prob < self.threshold:
                self._ml_stats["blocked"] += 1
                signal = Signal(
                    bull_score       = signal.bull_score,
                    bear_score       = signal.bear_score,
                    technical        = signal.technical,
                    htf_blocks_long  = True,
                    htf_blocks_short = signal.htf_blocks_short,
                    regime           = signal.regime,
                )
            else:
                self._ml_stats["passed"] += 1
                self._last_prob = prob  # exponer para Kelly sizing

        if bear_candidate and not signal.htf_blocks_short:
            fv   = _build_feature_vector(actual_row, signal, "SHORT", self.feature_cols)
            prob = self.clf.predict_proba([fv])[0][1]
            self._ml_stats["checked"] += 1
            if prob < self.threshold:
                self._ml_stats["blocked"] += 1
                signal = Signal(
                    bull_score       = signal.bull_score,
                    bear_score       = signal.bear_score,
                    technical        = signal.technical,
                    htf_blocks_long  = signal.htf_blocks_long,
                    htf_blocks_short = True,
                    regime           = signal.regime,
                )
            else:
                self._ml_stats["passed"] += 1
                self._last_prob = prob  # exponer para Kelly sizing

        return signal

    def print_ml_stats(self):
        s = self._ml_stats
        total = s["checked"]
        if total == 0:
            print("[StrategyML] No signals checked.")
            return
        pct_block = s["blocked"] / total * 100
        print(f"[StrategyML] Signals: checked={total} | passed={s['passed']} | "
              f"blocked={s['blocked']} ({pct_block:.0f}%)")
