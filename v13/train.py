"""
V13 — Reentrenamiento del modelo ML.

Diferencias respecto al v7 OOS:
  · Ventana de entrenamiento extendida: 2023-01-01 → 2026-01-01 (3 años)
  · OOS real: 2026-01-01 → presente (~8 meses del ciclo bull actual)
  · Usa trade_features_multipar.csv (BTC + ETH + SOL)

Run: python -m v13.train
"""

import sys, json, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

FEATURES_CSV = ROOT / "v7" / "data" / "trade_features_multipar.csv"
OUT_DIR      = ROOT / "v13" / "models"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_START = "2023-01-01"
TRAIN_END   = "2026-01-01"
TEST_START  = "2026-01-01"

FEATURE_COLS = [
    "htf_rsi", "ema200_ratio", "adx_dmp_norm", "hurst_acf1",
    "bear_score", "adx", "vol_ratio", "stochrsi_d", "stochrsi_k", "ema50_ratio",
]


def main():
    print(f"\n[V13] Reentrenamiento del modelo ML")
    print(f"  Entrenamiento : {TRAIN_START} → {TRAIN_END}")
    print(f"  OOS (test)    : {TEST_START} → presente\n")

    df = pd.read_csv(FEATURES_CSV, parse_dates=["entry_ts"])
    df = df.sort_values("entry_ts").reset_index(drop=True)

    # Verificar features disponibles
    missing = [f for f in FEATURE_COLS if f not in df.columns]
    if missing:
        print(f"  [WARN] Features no disponibles: {missing}")
        feature_cols = [f for f in FEATURE_COLS if f in df.columns]
    else:
        feature_cols = FEATURE_COLS

    # Dividir train / test
    df_train = df[(df["entry_ts"] >= TRAIN_START) & (df["entry_ts"] < TRAIN_END)]
    df_test  = df[df["entry_ts"] >= TEST_START]

    print(f"  Trades entrenamiento : {len(df_train)}  (WR={df_train['won'].mean()*100:.1f}%)")
    print(f"  Trades test OOS      : {len(df_test)}   (WR={df_test['won'].mean()*100:.1f}%)\n")

    X_train = df_train[feature_cols].fillna(0).values
    y_train = df_train["won"].values
    X_test  = df_test[feature_cols].fillna(0).values
    y_test  = df_test["won"].values

    # Entrenamiento
    clf = XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.04,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
        eval_metric="auc", random_state=42, verbosity=0,
    )
    clf.fit(X_train, y_train)

    # Métricas in-sample
    proba_train = clf.predict_proba(X_train)[:, 1]
    auc_train   = roc_auc_score(y_train, proba_train)
    print(f"  AUC in-sample  : {auc_train:.3f}")

    if len(df_test) > 10:
        proba_test = clf.predict_proba(X_test)[:, 1]
        auc_test   = roc_auc_score(y_test, proba_test)
        print(f"  AUC OOS (2026) : {auc_test:.3f}\n")

        print(f"  {'Umbral':>8} {'WR':>8} {'Cobertura':>10} {'Trades':>8}")
        print(f"  {'-'*8} {'-'*8} {'-'*10} {'-'*8}")
        for t in [0.50, 0.52, 0.55, 0.57, 0.60]:
            mask = proba_test >= t
            n    = mask.sum()
            if n > 5:
                wr  = y_test[mask].mean() * 100
                cov = n / len(y_test) * 100
                print(f"  {t:>8.2f} {wr:>7.1f}% {cov:>9.1f}% {n:>8}")
    else:
        print("  [WARN] Pocos trades en periodo OOS para evaluar.")

    # Guardar modelo
    model_path = OUT_DIR / "v13_classifier.pkl"
    meta_path  = OUT_DIR / "v13_classifier_meta.json"

    with open(model_path, "wb") as f:
        pickle.dump(clf, f)

    meta = {
        "model_type":   "XGB",
        "model_path":   str(model_path),
        "feature_cols": feature_cols,
        "threshold":    0.55,
        "train_period": f"{TRAIN_START} → {TRAIN_END}",
        "test_period":  f"{TEST_START} → presente",
        "trained_on":   pd.Timestamp.now().strftime("%Y%m%d"),
        "train_trades": len(df_train),
        "test_trades":  len(df_test),
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n  Modelo guardado: {model_path}")
    print(f"  Meta guardada  : {meta_path}")

    # Comparar con v7 actual
    print(f"\n  ─── Comparación con modelo actual (v7) ───")
    print(f"  v7  : entrenado en 2023-2025  |  CV WR@0.55 = 54.1%")

    if len(df_test) > 10:
        mask_55 = proba_test >= 0.55
        if mask_55.sum() > 0:
            wr_55 = y_test[mask_55].mean() * 100
            print(f"  v13 : entrenado en 2023-2026  |  WR@0.55 OOS = {wr_55:.1f}%  (n={mask_55.sum()})")

    print()


if __name__ == "__main__":
    main()
