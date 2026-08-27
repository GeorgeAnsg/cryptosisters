"""
V7 — Train separate ML models for LONG and SHORT trades.

Goal: ≥50% WR per direction (out-of-sample).
Train on 2023-2024, evaluate on 2025-2026.

Run: python v7/train_by_side.py
"""

import sys, json, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

CSV_PATH  = ROOT / "v7" / "data" / "trade_features.csv"
OUT_DIR   = ROOT / "v7" / "models"
TRAIN_END = "2025-01-01"

# Feature set: top-10 from SHAP (side_enc dropped — models are direction-specific now)
# Also drop net_score since it's derived from bull/bear relative to side
LONG_FEATURES = [
    "htf_rsi", "ema200_ratio", "adx_dmp_norm", "hurst_acf1",
    "bear_score", "adx", "vol_ratio", "stochrsi_d", "stochrsi_k", "ema50_ratio",
    "rsi", "macd_h_norm", "bull_score", "ema21_ratio", "ms_bull",
]

SHORT_FEATURES = [
    "htf_rsi", "ema200_ratio", "adx_dmn_norm", "hurst_acf1",
    "bull_score", "adx", "vol_ratio", "stochrsi_d", "stochrsi_k", "ema50_ratio",
    "rsi", "macd_h_norm", "bear_score", "ema21_ratio", "ms_bear",
]


def threshold_table(proba, y, thresholds=None):
    if thresholds is None:
        thresholds = np.arange(0.40, 0.75, 0.025)
    rows = []
    for t in thresholds:
        mask = proba >= t
        n    = mask.sum()
        wr   = y[mask].mean() * 100 if n > 0 else 0
        cov  = n / len(y) * 100
        rows.append({"t": round(t, 3), "n": n, "wr": round(wr, 1), "cov": round(cov, 1)})
    return pd.DataFrame(rows)


def train_side(side: str, df: pd.DataFrame, feature_cols: list):
    print(f"\n{'='*55}")
    print(f"  {side} MODEL")
    print(f"{'='*55}")

    df_s     = df[df["side"] == side].sort_values("entry_ts").reset_index(drop=True)
    df_train = df_s[df_s["entry_ts"] < TRAIN_END]
    df_test  = df_s[df_s["entry_ts"] >= TRAIN_END]

    print(f"  Train: {len(df_train)} trades | WR={df_train['won'].mean()*100:.1f}%  ({df_train['entry_ts'].iloc[0].date()} → {TRAIN_END})")
    print(f"  Test:  {len(df_test)} trades  | WR={df_test['won'].mean()*100:.1f}%  ({TRAIN_END} → 2026-08-24)")

    X_tr = df_train[feature_cols].fillna(0).values
    y_tr = df_train["won"].values
    X_te = df_test[feature_cols].fillna(0).values
    y_te = df_test["won"].values

    clf = XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.04,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_tr == 0).sum() / max((y_tr == 1).sum(), 1),
        eval_metric="auc", random_state=42, verbosity=0,
    )
    clf.fit(X_tr, y_tr)

    proba_tr = clf.predict_proba(X_tr)[:, 1]
    proba_te = clf.predict_proba(X_te)[:, 1]
    auc_tr   = roc_auc_score(y_tr, proba_tr)
    auc_te   = roc_auc_score(y_te, proba_te)
    print(f"\n  AUC — train: {auc_tr:.3f}  |  OOS: {auc_te:.3f}")

    tbl = threshold_table(proba_te, y_te)
    print(f"\n  Threshold calibration (OOS = {TRAIN_END} → 2026-08-24):")
    print(f"  {'t':>6}  {'n':>5}  {'WR':>7}  {'cov':>7}  {'edge/R':>8}")
    for _, row in tbl.iterrows():
        wr  = row["wr"] / 100
        # edge with R:R=1.6 (SL=2.5, TP=4.0)
        edge = wr * 1.6 - (1 - wr) * 1.0
        marker = " ◀ ≥50%" if row["wr"] >= 50.0 else ""
        print(f"  {row['t']:>6.3f}  {row['n']:>5.0f}  {row['wr']:>6.1f}%  {row['cov']:>6.1f}%  {edge:>+8.3f}{marker}")

    # Find optimal threshold: ≥50% WR with max coverage
    candidates = tbl[(tbl["wr"] >= 50.0) & (tbl["n"] >= 20)]
    if candidates.empty:
        best_t = tbl.loc[tbl["wr"].idxmax(), "t"]
        best_wr = tbl.loc[tbl["wr"].idxmax(), "wr"]
        print(f"\n  WARNING: No threshold reaches 50% WR. Best: t={best_t:.3f} WR={best_wr:.1f}%")
    else:
        best_row = candidates.loc[candidates["cov"].idxmax()]
        best_t   = best_row["t"]
        best_wr  = best_row["wr"]
        best_n   = int(best_row["n"])
        print(f"\n  → Optimal threshold: {best_t:.3f} | WR={best_wr:.1f}% | n={best_n} trades OOS")

    return clf, best_t, feature_cols, auc_te


if __name__ == "__main__":
    print(f"\n[V7] Training side-specific models (LONG + SHORT)")
    print(f"  Train: 2023-01-01 → {TRAIN_END}  |  Test: {TRAIN_END} → 2026-08-24\n")

    df = pd.read_csv(CSV_PATH, parse_dates=["entry_ts"])
    df = df.sort_values("entry_ts").reset_index(drop=True)
    print(f"  Total trades: {len(df)} | LONG: {(df['side']=='LONG').sum()} | SHORT: {(df['side']=='SHORT').sum()}")

    clf_long,  t_long,  feat_long,  auc_long  = train_side("LONG",  df, LONG_FEATURES)
    clf_short, t_short, feat_short, auc_short = train_side("SHORT", df, SHORT_FEATURES)

    # Save models
    for side, clf, t, feats, auc in [
        ("long",  clf_long,  t_long,  feat_long,  auc_long),
        ("short", clf_short, t_short, feat_short, auc_short),
    ]:
        pkl_path  = OUT_DIR / f"v7_clf_{side}.pkl"
        meta_path = OUT_DIR / f"v7_clf_{side}_meta.json"
        with open(pkl_path,  "wb") as f: pickle.dump(clf, f)
        with open(meta_path, "w")  as f: json.dump({
            "side": side.upper(), "model_type": "XGB",
            "model_path": str(pkl_path),
            "feature_cols": feats, "threshold": round(t, 3),
            "oos_auc": round(auc, 3), "train_end": TRAIN_END,
        }, f, indent=2)
        print(f"\n  Saved: {pkl_path.name}  (threshold={t:.3f}, OOS AUC={auc:.3f})")

    print(f"\n[V7] Done. Next: python v7/backtest_sides.py")
