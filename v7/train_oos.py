"""
V7 — Proper out-of-sample evaluation.

Training window : 2023-01-01 → 2024-12-31  (2 years)
Test window     : 2025-01-01 → 2026-08-24  (held-out)

The model never sees 2025+ data during training.
"""

import sys
import json
import pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

from v6.core.bot_core import run_backtest
from v6.core.bot_indicators import precompute_indicators
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import StrategyML

CSV_PATH  = ROOT / "v7" / "data" / "trade_features.csv"
LOCAL_CSV = ROOT / "data" / "btc_15m_full.csv"
OUT_DIR   = ROOT / "v7" / "models"
OUT_DIR.mkdir(exist_ok=True)

TRAIN_END  = "2025-01-01"
TEST_START = "2025-01-01"

TOP10_FEATURES = [
    "htf_rsi", "ema200_ratio", "adx_dmp_norm", "hurst_acf1",
    "bear_score", "adx", "vol_ratio", "stochrsi_d", "stochrsi_k", "ema50_ratio",
]

RISK_PROFILE = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}


def train_on_window(df_features: pd.DataFrame, train_end: str):
    df_train = df_features[df_features["entry_ts"] < train_end]
    X = df_train[TOP10_FEATURES].fillna(0).values
    y = df_train["won"].values
    wr = y.mean() * 100
    print(f"\n  Training set: {len(df_train)} trades | WR={wr:.1f}% | up to {train_end}")

    clf = XGBClassifier(n_estimators=400, max_depth=5, learning_rate=0.04,
                        subsample=0.8, colsample_bytree=0.8,
                        scale_pos_weight=(y == 0).sum() / max((y == 1).sum(), 1),
                        eval_metric="auc", random_state=42, verbosity=0)
    clf.fit(X, y)

    # In-sample check
    proba = clf.predict_proba(X)[:, 1]
    print(f"  In-sample AUC: {roc_auc_score(y, proba):.3f}")

    # Quick OOS check on test-set features only (not backtest)
    df_features_parsed = pd.read_csv(CSV_PATH, parse_dates=["entry_ts"])
    df_test = df_features_parsed[df_features_parsed["entry_ts"] >= TEST_START]
    if len(df_test) > 0:
        X_te = df_test[TOP10_FEATURES].fillna(0).values
        y_te = df_test["won"].values
        proba_te = clf.predict_proba(X_te)[:, 1]
        auc_oos = roc_auc_score(y_te, proba_te)
        wr_test = y_te.mean() * 100

        print(f"  Test-set  AUC (feature-only, 2025+): {auc_oos:.3f} | WR={wr_test:.1f}% | n={len(df_test)}")

        for t in [0.50, 0.55, 0.60]:
            mask = proba_te >= t
            if mask.sum() > 0:
                wr_t = y_te[mask].mean() * 100
                cov  = mask.sum() / len(y_te) * 100
                print(f"    threshold={t:.2f}  WR={wr_t:.1f}%  coverage={cov:.1f}%  n={mask.sum()}")

    return clf


def run_backtest_period(label: str, strategy, df: pd.DataFrame):
    result = run_backtest(
        exchange=None, pair="BTC/USDT:USDT", days=0,
        risk_profile=RISK_PROFILE, strategy=strategy, _df_override=df,
    )
    stats = result["stats"]
    total = stats["wins"] + stats["losses"]
    wr    = stats["wins"] / total * 100 if total else 0
    pnl   = result["final_balance"] - 1000
    print(f"  {label:<35}  PnL: {pnl:+8.2f}  Trades: {total:4}  WR: {wr:.1f}%")
    if hasattr(strategy, "print_ml_stats"):
        strategy.print_ml_stats()
    return {"label": label, "pnl": round(pnl, 2), "trades": total, "wr": round(wr, 1)}


if __name__ == "__main__":
    print(f"\n[V7 OOS] Proper out-of-sample evaluation")
    print(f"  Train: 2023-01-01 → {TRAIN_END}  |  Test: {TEST_START} → 2026-08-24\n")

    # Load features (already have them from Phase 1)
    df_feat = pd.read_csv(CSV_PATH, parse_dates=["entry_ts"])
    df_feat = df_feat.sort_values("entry_ts").reset_index(drop=True)

    # Train model only on pre-2025 data
    clf = train_on_window(df_feat, TRAIN_END)

    # Save this OOS-safe model
    oos_model_path = OUT_DIR / "v7_classifier_oos.pkl"
    oos_meta_path  = OUT_DIR / "v7_classifier_oos_meta.json"
    with open(oos_model_path, "wb") as f:
        pickle.dump(clf, f)
    meta_oos = {
        "model_type":   "XGB",
        "model_path":   str(oos_model_path),
        "feature_cols": TOP10_FEATURES,
        "threshold":    0.55,
        "train_period": f"2023-01-01 → {TRAIN_END}",
        "test_period":  f"{TEST_START} → 2026-08-24",
    }
    with open(oos_meta_path, "w") as f:
        json.dump(meta_oos, f, indent=2)

    # Load test period candle data
    print(f"\n  Loading backtest data for test period ({TEST_START}→2026-08-24)...")
    df_raw = pd.read_csv(LOCAL_CSV, parse_dates=["timestamp"])
    df_test = df_raw[df_raw["timestamp"] >= TEST_START].reset_index(drop=True)
    print(f"  {len(df_test):,} candles | Precomputing indicators...")
    df_test = precompute_indicators(df_test)

    print(f"\n─── OOS Backtest results ({TEST_START} → 2026-08-24) ───")

    v6 = Strategy15m()
    r_v6 = run_backtest_period("V6 baseline (no ML)", v6, df_test)

    for t in [0.50, 0.55, 0.60]:
        ml_strat = StrategyML(model_path=str(oos_model_path), threshold=t)
        # override feature cols to match OOS model
        ml_strat.feature_cols = TOP10_FEATURES
        r = run_backtest_period(f"V7 ML OOS (threshold={t:.2f})", ml_strat, df_test)

    print("\n" + "=" * 60)
    print("  NOTE: These results are truly out-of-sample.")
    print("  The ML model was trained on 2023-2024 ONLY.")
    print("  It had NEVER seen 2025-2026 data during training.")
    print("=" * 60)
