"""
V7 Phase 1 — SHAP feature importance analysis.

Trains a Random Forest on the 1883-trade dataset and computes SHAP values
to identify which of the 31 features actually predict trade outcome.

Run: python v7/shap_analysis.py
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

CSV_PATH = ROOT / "v7" / "data" / "trade_features.csv"
OUT_DIR  = ROOT / "v7" / "data"

FEATURE_COLS = [
    "ema9_ratio", "ema21_ratio", "ema50_ratio", "ema200_ratio",
    "rsi", "stochrsi_k", "stochrsi_d",
    "macd_h_norm",
    "adx", "adx_dmp_norm", "adx_dmn_norm",
    "bb_pct",
    "vol_ratio",
    "atr_contracted",
    "bull_engulf", "bear_engulf", "hammer", "shooting_star",
    "three_bull", "three_bear",
    "ms_bull", "ms_bear",
    "near_channel_top", "near_channel_bot",
    "hurst_acf1",
    "bull_score", "bear_score", "net_score",
    "regime_enc",
    "htf_rsi",
    "side_enc",
]


def load_data():
    df = pd.read_csv(CSV_PATH, parse_dates=["entry_ts", "exit_ts"])
    df = df.sort_values("entry_ts").reset_index(drop=True)
    print(f"  Loaded {len(df)} trades | WR={df['won'].mean()*100:.1f}%")
    print(f"  Date range: {df['entry_ts'].iloc[0].date()} → {df['entry_ts'].iloc[-1].date()}")
    return df


def walk_forward_cv(X: np.ndarray, y: np.ndarray, n_splits=5) -> list[float]:
    """Temporal cross-validation — never trains on future data."""
    tscv   = TimeSeriesSplit(n_splits=n_splits)
    aucs   = []
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]
        clf = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=20,
                                     class_weight="balanced", random_state=42)
        clf.fit(X_tr, y_tr)
        proba = clf.predict_proba(X_te)[:, 1]
        auc   = roc_auc_score(y_te, proba)
        aucs.append(auc)
        print(f"    Fold {fold+1}: AUC={auc:.3f}  n_test={len(y_te)}  WR_pred={proba.mean():.2f}")
    return aucs


def shap_importance(X: np.ndarray, y: np.ndarray, feature_names: list) -> pd.DataFrame:
    """Train RF on full data and compute SHAP values."""
    clf = RandomForestClassifier(n_estimators=300, max_depth=7, min_samples_leaf=15,
                                 class_weight="balanced", random_state=42)
    clf.fit(X, y)
    explainer   = shap.TreeExplainer(clf)
    shap_values = explainer.shap_values(X)

    # Handle both old API (list of arrays) and new API (Explanation object / 3D array)
    if isinstance(shap_values, list):
        sv = shap_values[1]  # class 1
    elif hasattr(shap_values, "values"):
        sv = shap_values.values
        if sv.ndim == 3:
            sv = sv[:, :, 1]  # class 1
    else:
        sv = shap_values
        if sv.ndim == 3:
            sv = sv[:, :, 1]
    mean_abs = np.abs(sv).mean(axis=0)

    importance = pd.DataFrame({
        "feature":      feature_names,
        "shap_abs":     mean_abs,
        "rf_importance": clf.feature_importances_,
    }).sort_values("shap_abs", ascending=False).reset_index(drop=True)

    return importance, clf


def print_report(importance: pd.DataFrame, wfcv_aucs: list[float]):
    print("\n" + "=" * 55)
    print("  FEATURE IMPORTANCE — SHAP (class 1 = WIN)")
    print("=" * 55)
    print(f"  {'Rank':<5} {'Feature':<22} {'SHAP abs':>10}  {'RF imp':>8}")
    print("  " + "-" * 50)
    for rank, row in importance.iterrows():
        marker = " ◀" if rank < 10 else ""
        print(f"  {rank+1:<5} {row['feature']:<22} {row['shap_abs']:>10.4f}  {row['rf_importance']:>8.4f}{marker}")

    print(f"\n  Walk-forward AUC: {np.mean(wfcv_aucs):.3f} ± {np.std(wfcv_aucs):.3f}")
    print(f"  (AUC 0.5 = random, >0.55 = predictive, >0.60 = useful)")

    top10 = importance["feature"].iloc[:10].tolist()
    bottom5 = importance["feature"].iloc[-5:].tolist()
    print(f"\n  TOP 10 features for V7 ML:")
    for i, f in enumerate(top10, 1):
        print(f"    {i:2}. {f}")
    print(f"\n  BOTTOM 5 (consider removing):")
    for f in bottom5:
        print(f"    - {f}")
    print("=" * 55)


if __name__ == "__main__":
    print(f"\n[V7 SHAP] Feature importance analysis")
    print(f"  Input: {CSV_PATH}\n")

    df = load_data()

    X = df[FEATURE_COLS].fillna(0).values
    y = df["won"].values

    print(f"\n  Walk-forward CV ({len(X)} samples, 5 folds)...")
    wfcv_aucs = walk_forward_cv(X, y)

    print(f"\n  Computing SHAP values (full dataset)...")
    importance, clf = shap_importance(X, y, FEATURE_COLS)

    print_report(importance, wfcv_aucs)

    # Save ranked feature list
    out_csv = OUT_DIR / "feature_importance.csv"
    importance.to_csv(out_csv, index=False)
    print(f"\n  Saved → {out_csv}")

    # Also save LONG vs SHORT analysis
    for side, side_enc in [("LONG", 1), ("SHORT", -1)]:
        df_s = df[df["side_enc"] == side_enc]
        if len(df_s) < 50:
            continue
        X_s = df_s[FEATURE_COLS].fillna(0).values
        y_s = df_s["won"].values
        _, clf_s = shap_importance(X_s, y_s, FEATURE_COLS)
        wr = y_s.mean() * 100
        print(f"  {side}: n={len(df_s)}, WR={wr:.1f}% (RF in-sample acc={accuracy_score(y_s, clf_s.predict(X_s))*100:.0f}%)")

    print(f"\n[V7 SHAP] Done. Review results, then move to Phase 2: train V7 classifier.")
