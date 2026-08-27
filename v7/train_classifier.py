"""
V7 Phase 2 — Train ML classifier on top-10 SHAP features.

Goal: filter out low-quality trades to push WR from 38.3% → 44%+
Strategy: use probability threshold calibration to trade only high-confidence setups.

Run: python v7/train_classifier.py
"""

import sys
import json
import pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, accuracy_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("  XGBoost not found — using RF only. Install with: pip install xgboost")

CSV_PATH = ROOT / "v7" / "data" / "trade_features.csv"
OUT_DIR  = ROOT / "v7" / "models"
OUT_DIR.mkdir(exist_ok=True)

# Top-10 features from SHAP analysis (Fase 1)
TOP10_FEATURES = [
    "htf_rsi",
    "ema200_ratio",
    "adx_dmp_norm",
    "hurst_acf1",
    "bear_score",
    "adx",
    "vol_ratio",
    "stochrsi_d",
    "stochrsi_k",
    "ema50_ratio",
]

# Extended set: top-10 + a few more that might help in combination
TOP16_FEATURES = TOP10_FEATURES + [
    "adx_dmn_norm",
    "net_score",
    "macd_h_norm",
    "bull_score",
    "ema9_ratio",
    "ema21_ratio",
]


def load_data(feature_cols):
    df = pd.read_csv(CSV_PATH, parse_dates=["entry_ts"])
    df = df.sort_values("entry_ts").reset_index(drop=True)
    X  = df[feature_cols].fillna(0).values
    y  = df["won"].values
    print(f"  {len(df)} trades | WR={y.mean()*100:.1f}% | Features={len(feature_cols)}")
    return df, X, y


def threshold_analysis(clf, X_test, y_test, thresholds=None):
    """For each threshold t, trades with P(win)>t are taken. Report WR and coverage."""
    if thresholds is None:
        thresholds = np.arange(0.35, 0.70, 0.025)
    proba = clf.predict_proba(X_test)[:, 1]
    rows  = []
    for t in thresholds:
        mask = proba >= t
        n    = mask.sum()
        wr   = y_test[mask].mean() * 100 if n > 0 else 0
        cov  = n / len(y_test) * 100
        rows.append({"threshold": round(t, 3), "n_trades": n, "wr_pct": round(wr, 1), "coverage_pct": round(cov, 1)})
    return pd.DataFrame(rows)


def walk_forward_eval(X, y, feature_cols, n_splits=5, label="RF"):
    """Full walk-forward evaluation with threshold analysis on each fold."""
    tscv   = TimeSeriesSplit(n_splits=n_splits)
    fold_results = []

    print(f"\n  Walk-forward CV — {label} ({n_splits} folds):")
    print(f"  {'Fold':<6} {'AUC':>6} {'WR@0.50':>9} {'WR@0.55':>9} {'WR@0.60':>9} {'cov@0.55':>9}")
    print("  " + "-" * 55)

    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]

        if label == "RF":
            clf = RandomForestClassifier(n_estimators=300, max_depth=7, min_samples_leaf=15,
                                         class_weight="balanced", random_state=42)
        else:  # XGB
            clf = XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.05,
                                subsample=0.8, colsample_bytree=0.8,
                                scale_pos_weight=(y_tr == 0).sum() / (y_tr == 1).sum(),
                                eval_metric="auc", random_state=42, verbosity=0)

        clf.fit(X_tr, y_tr)
        proba = clf.predict_proba(X_te)[:, 1]
        auc   = roc_auc_score(y_te, proba)

        def wr_at(t):
            mask = proba >= t
            n = mask.sum()
            if n == 0:
                return 0.0, 0.0
            return y_te[mask].mean() * 100, n / len(y_te) * 100

        wr50, _    = wr_at(0.50)
        wr55, c55  = wr_at(0.55)
        wr60, _    = wr_at(0.60)

        print(f"  {fold+1:<6} {auc:>6.3f} {wr50:>8.1f}% {wr55:>8.1f}% {wr60:>8.1f}% {c55:>8.1f}%")
        fold_results.append({"fold": fold+1, "auc": auc, "wr50": wr50, "wr55": wr55, "wr60": wr60, "cov55": c55})

    df_res = pd.DataFrame(fold_results)
    print(f"  {'mean':<6} {df_res['auc'].mean():>6.3f} {df_res['wr50'].mean():>8.1f}% "
          f"{df_res['wr55'].mean():>8.1f}% {df_res['wr60'].mean():>8.1f}% {df_res['cov55'].mean():>8.1f}%")
    return df_res


def train_final_model(X, y, feature_cols, label="RF"):
    """Train on full data. Returns calibrated classifier + scaler."""
    if label == "RF":
        base = RandomForestClassifier(n_estimators=400, max_depth=7, min_samples_leaf=15,
                                      class_weight="balanced", random_state=42)
    else:
        base = XGBClassifier(n_estimators=400, max_depth=5, learning_rate=0.04,
                             subsample=0.8, colsample_bytree=0.8,
                             scale_pos_weight=(y == 0).sum() / (y == 1).sum(),
                             eval_metric="auc", random_state=42, verbosity=0)

    base.fit(X, y)

    # In-sample check
    proba = base.predict_proba(X)[:, 1]
    auc   = roc_auc_score(y, proba)
    print(f"  {label} in-sample AUC: {auc:.3f}")

    return base


def threshold_summary(rf_cv, xgb_cv=None):
    """Print recommended threshold based on CV results."""
    print("\n" + "=" * 55)
    print("  THRESHOLD RECOMMENDATION")
    print("=" * 55)
    print(f"  RF  WR@0.55 = {rf_cv['wr55'].mean():.1f}%  coverage = {rf_cv['cov55'].mean():.1f}%")
    if xgb_cv is not None:
        print(f"  XGB WR@0.55 = {xgb_cv['wr55'].mean():.1f}%  coverage = {xgb_cv['cov55'].mean():.1f}%")

    best_wr = rf_cv['wr55'].mean()
    best_cv = xgb_cv['wr55'].mean() if xgb_cv is not None else 0

    if best_wr >= best_cv:
        best_model = "RF"
        cv = rf_cv
    else:
        best_model = "XGB"
        cv = xgb_cv

    print(f"\n  → Best model: {best_model}")
    print(f"  → Recommended threshold: 0.55")
    print(f"    At this threshold:")
    print(f"    - WR improves: {cv['wr50'].mean():.1f}% → {cv['wr55'].mean():.1f}%")
    print(f"    - Trades taken: {cv['cov55'].mean():.1f}% of signals")
    print(f"    - Trades filtered out: {100-cv['cov55'].mean():.1f}% (too low confidence)")
    print("=" * 55)
    return best_model


if __name__ == "__main__":
    print(f"\n[V7 Phase 2] Training ML classifier")
    print(f"  Features: top-10 from SHAP analysis\n")

    df, X10, y = load_data(TOP10_FEATURES)
    df16, X16, _ = load_data(TOP16_FEATURES)

    print("\n── Random Forest (top-10 features) ──")
    rf_cv10 = walk_forward_eval(X10, y, TOP10_FEATURES, label="RF")

    print("\n── Random Forest (top-16 features) ──")
    rf_cv16 = walk_forward_eval(X16, y, TOP16_FEATURES, label="RF")

    if HAS_XGB:
        print("\n── XGBoost (top-10 features) ──")
        xgb_cv10 = walk_forward_eval(X10, y, TOP10_FEATURES, label="XGB")
    else:
        xgb_cv10 = None

    # Pick best feature set for RF
    rf_cv = rf_cv10 if rf_cv10['wr55'].mean() >= rf_cv16['wr55'].mean() else rf_cv16
    best_feat = TOP10_FEATURES if rf_cv10['wr55'].mean() >= rf_cv16['wr55'].mean() else TOP16_FEATURES
    X_best = X10 if rf_cv10['wr55'].mean() >= rf_cv16['wr55'].mean() else X16
    print(f"\n  Best feature set: {'top-10' if best_feat == TOP10_FEATURES else 'top-16'}")

    best_model_name = threshold_summary(rf_cv, xgb_cv10)

    # Train final model on full dataset
    print(f"\n  Training final {best_model_name} on full dataset ({len(y)} trades)...")
    if best_model_name == "RF":
        final_clf = train_final_model(X_best, y, best_feat, label="RF")
    else:
        final_clf = train_final_model(X10, y, TOP10_FEATURES, label="XGB")
        X_best = X10
        best_feat = TOP10_FEATURES

    # Save model + metadata
    model_path = OUT_DIR / f"v7_classifier_{best_model_name.lower()}.pkl"
    meta_path  = OUT_DIR / "v7_classifier_meta.json"

    with open(model_path, "wb") as f:
        pickle.dump(final_clf, f)

    meta = {
        "model_type":    best_model_name,
        "model_path":    str(model_path),
        "feature_cols":  best_feat,
        "threshold":     0.55,
        "n_train":       len(y),
        "train_wr":      round(float(y.mean()*100), 1),
        "cv_auc_mean":   round(float(rf_cv['auc'].mean()), 3),
        "cv_wr55_mean":  round(float(rf_cv['wr55'].mean()), 1),
        "cv_cov55_mean": round(float(rf_cv['cov55'].mean()), 1),
        "trained_on":    "2023-2026",
    }

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n  Saved model → {model_path}")
    print(f"  Saved meta  → {meta_path}")
    print(f"\n[V7 Phase 2] Done.")
    print(f"  → Next: integrate classifier into v7/strategy_ml.py")
    print(f"  → Run: python v7/backtest_v7.py to test full performance")
