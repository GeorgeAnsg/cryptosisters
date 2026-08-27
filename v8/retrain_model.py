"""
V8 — Pipeline de reentrenamiento periódico del modelo ML.

Uso (lanzar cada 6 meses aprox.):
    python v8/retrain_model.py
    python v8/retrain_model.py --train-months 24 --holdout-months 6

Qué hace:
  1. Carga datos históricos (btc_15m_full.csv + eth_2023_2026.csv)
  2. Extrae trades y sus resultados con la estrategia V7 (sin filtro ML,
     para capturar todas las señales y etiquetarlas win/loss)
  3. Usa ventana deslizante: entrena en los últimos TRAIN_MONTHS,
     valida en los siguientes HOLDOUT_MONTHS
  4. Compara AUC/WR del modelo nuevo vs el actual
  5. Guarda el nuevo modelo si no empeora al actual
"""

import sys, json, pickle, argparse, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from datetime import datetime
from xgboost import XGBClassifier

from v6.core.bot_core import load_state, apply_regime, reset_daily_counter, check_sl_tp, make_decision, close_position
from v6.core.bot_indicators import precompute_indicators
from v6.strategies.strategy_15m import Strategy15m
from v7.strategy_ml import _build_feature_vector

MODEL_DIR  = ROOT / "v7" / "models"
V8_MODEL   = ROOT / "v8" / "models"
V8_MODEL.mkdir(exist_ok=True)

with open(MODEL_DIR / "v7_classifier_oos_meta.json") as _f:
    FEATURE_COLS = json.load(_f)["feature_cols"]

BASE_RISK = {
    "risk_pct": 0.02, "max_cost_pct": 0.35,
    "stop_loss_atr_mult": 2.5, "take_profit_atr_mult": 4.0,
    "min_score": 58, "entry_advantage": 15, "max_daily_trades": 6,
    "max_drawdown_pct": 0.10, "max_daily_loss_pct": 0.03,
    "trailing_stop": True, "max_tp_extensions": 2,
    "weekend_mode": "range", "weekend_min_score_bonus": 10, "min_vol_ratio": 0.0,
}


# ── Extracción de trades etiquetados ──────────────────────────────────────────

def extract_labeled_trades(df: pd.DataFrame, pair: str) -> pd.DataFrame:
    """
    Corre la estrategia base (sin ML) y extrae cada trade con:
      - Features en el momento de entrada
      - Resultado: 1 = win, 0 = loss
    """
    strategy = Strategy15m()
    state    = load_state("__x__")
    records  = []

    pending_entry = None  # (features, side) esperando cierre

    for i in range(100, len(df)):
        row      = df.iloc[i]
        ts       = pd.Timestamp(row["timestamp"])
        reset_daily_counter(state, str(ts.date()))
        state["current_candle_index"] = i

        current_price = float(row["close"])
        df_slice      = df.iloc[max(0, i - 299):i + 1]
        live_extras = {
            "sentiment":  {"bullish_score": 0, "bearish_score": 0, "sentiment": "neutral"},
            "fear_greed": {"bull_mod": 5, "bear_mod": 5, "value": 50, "label": "neutral"},
            "funding":    {"funding_rate": 0.0, "bull_mod": 3, "bear_mod": 3},
            "orderbook":  {"bull_mod": 0, "bear_mod": 0},
            "macro_corr": {"bull_mod": 0, "bear_mod": 0},
        }
        signal = strategy.get_signal(df_slice, live_extras, row=row)
        rp     = apply_regime(BASE_RISK, signal.regime)
        atr    = signal.technical.get("details", {}).get("atr", 0)

        # Si hay posición abierta y se va a cerrar, capturar resultado
        had_position = state.get("position") is not None
        check_sl_tp(state, pair, current_price, rp, atr=atr,
                    scores={"bullish_total": signal.bull_score, "bearish_total": signal.bear_score})
        make_decision(state, pair, current_price, atr, signal, rp,
                      verbose=False, min_hold_candles=0,
                      current_candle_index=i, winrate_table={}, timestamp=ts)

        # Si teníamos posición y ahora no → se cerró → etiquetar
        if pending_entry and not state.get("position"):
            last_trade = next(
                (t for t in reversed(state["trades"]) if t["action"].startswith("CLOSE_")), None
            )
            if last_trade:
                label = 1 if last_trade["pnl"] > 0 else 0
                records.append({**pending_entry, "label": label, "pnl": last_trade["pnl"]})
            pending_entry = None

        # Si abrimos posición nueva → capturar features de entrada
        if not had_position and state.get("position"):
            pos  = state["position"]
            side = pos["side"]
            fv   = _build_feature_vector(row, signal, side, FEATURE_COLS)
            pending_entry = {f: v for f, v in zip(FEATURE_COLS, fv)}
            pending_entry["side"] = side
            pending_entry["timestamp"] = str(ts)

    # Cerrar posición pendiente
    if state.get("position"):
        close_position(state, pair, float(df.iloc[-1]["close"]), "END")
        if pending_entry:
            last_trade = next(
                (t for t in reversed(state["trades"]) if t["action"].startswith("CLOSE_")), None
            )
            if last_trade:
                label = 1 if last_trade["pnl"] > 0 else 0
                records.append({**pending_entry, "label": label, "pnl": last_trade["pnl"]})

    return pd.DataFrame(records)


# ── Entrenamiento ──────────────────────────────────────────────────────────────

def train_model(df_trades: pd.DataFrame) -> XGBClassifier:
    X = df_trades[FEATURE_COLS].values
    y = df_trades["label"].values
    clf = XGBClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        min_child_weight=5, gamma=1,
        eval_metric="logloss", random_state=42,
        verbosity=0,
    )
    clf.fit(X, y)
    return clf


def evaluate_model(clf, df_trades: pd.DataFrame, threshold: float = 0.55):
    X = df_trades[FEATURE_COLS].values
    y = df_trades["label"].values
    probs = clf.predict_proba(X)[:, 1]
    mask  = probs >= threshold
    if mask.sum() == 0:
        return {"auc": 0, "wr_filtered": 0, "coverage": 0}
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(y, probs)
    wr  = y[mask].mean() * 100
    cov = mask.mean() * 100
    return {"auc": round(auc, 3), "wr_filtered": round(wr, 1), "coverage": round(cov, 1)}


# ── Actualización de datos ────────────────────────────────────────────────────

def _refresh_if_stale(csv_path: Path, pair: str, stale_days: int = 30) -> None:
    """Descarga velas recientes si el CSV no existe o su última vela es antigua."""
    import ccxt as _ccxt

    exchange = _ccxt.bybit({"enableRateLimit": True})
    futures_symbol = pair + ":USDT"  # e.g. ETH/USDT → ETH/USDT:USDT

    existing_df = None
    since_ms = None

    if csv_path.exists():
        existing_df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        if not existing_df.empty:
            last_ts = existing_df["timestamp"].max()
            age_days = (pd.Timestamp.now() - last_ts).days
            if age_days <= stale_days:
                print(f"    [{pair}] Datos frescos ({age_days}d). Sin descarga.")
                return
            print(f"    [{pair}] Actualizando desde {last_ts.date()} ({age_days}d)...")
            since_ms = int(last_ts.timestamp() * 1000) + 1
    else:
        print(f"    [{pair}] {csv_path.name} no encontrado — descarga 3 años...")
        since_ms = int((pd.Timestamp.now() - pd.DateOffset(years=3)).timestamp() * 1000)

    all_candles = []
    while True:
        candles = exchange.fetch_ohlcv(futures_symbol, "15m", since=since_ms, limit=1000)
        if not candles:
            break
        all_candles.extend(candles)
        since_ms = candles[-1][0] + 1
        if len(candles) < 1000:
            break
        time.sleep(0.3)

    if not all_candles:
        print(f"    [{pair}] Sin nuevas velas disponibles.")
        return

    new_df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    new_df["timestamp"] = pd.to_datetime(new_df["timestamp"], unit="ms")

    if existing_df is not None:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    else:
        combined = new_df

    combined.to_csv(csv_path, index=False)
    print(f"    [{pair}] Guardado: {len(combined)} velas en {csv_path.name}")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-months",   type=int, default=24, help="Meses de entrenamiento (default: 24)")
    parser.add_argument("--holdout-months", type=int, default=6,  help="Meses de validación (default: 6)")
    parser.add_argument("--force",          action="store_true",   help="Guardar aunque empeore el AUC")
    args = parser.parse_args()

    today      = pd.Timestamp.now()
    holdout_start = today - pd.DateOffset(months=args.holdout_months)
    train_start   = holdout_start - pd.DateOffset(months=args.train_months)

    print(f"\n{'='*65}")
    print(f"  V8 REENTRENAMIENTO PERIÓDICO")
    print(f"  Train:   {train_start.date()} → {holdout_start.date()} ({args.train_months} meses)")
    print(f"  Holdout: {holdout_start.date()} → {today.date()} ({args.holdout_months} meses)")
    print(f"{'='*65}\n")

    # Cargar datos — descarga ETH fresco si el CSV existente es antiguo
    eth_csv = ROOT / "data" / "eth_2023_2026.csv"
    _refresh_if_stale(eth_csv, "ETH/USDT")

    pairs = [
        ("BTC/USDT:USDT", ROOT / "data" / "btc_15m_full.csv"),
        ("ETH/USDT:USDT", eth_csv),
    ]

    all_train  = []
    all_holdout = []

    for pair, csv_path in pairs:
        print(f"  Extrayendo trades de {pair}...")
        df_raw = pd.read_csv(csv_path, parse_dates=["timestamp"])

        df_train_raw = df_raw[
            (df_raw["timestamp"] >= train_start) &
            (df_raw["timestamp"] <  holdout_start)
        ].reset_index(drop=True)
        df_hold_raw = df_raw[
            df_raw["timestamp"] >= holdout_start
        ].reset_index(drop=True)

        if len(df_train_raw) < 1000:
            print(f"    ⚠ Datos insuficientes en train para {pair}, skipping")
            continue
        if len(df_hold_raw) < 500:
            print(f"    ⚠ Datos insuficientes en holdout para {pair}, skipping")
            continue

        df_train_raw = precompute_indicators(df_train_raw)
        df_hold_raw  = precompute_indicators(df_hold_raw)

        trades_train = extract_labeled_trades(df_train_raw, pair)
        trades_hold  = extract_labeled_trades(df_hold_raw, pair)

        print(f"    Train: {len(trades_train)} trades (WR={trades_train['label'].mean()*100:.1f}%)")
        print(f"    Hold:  {len(trades_hold)} trades (WR={trades_hold['label'].mean()*100:.1f}%)")
        all_train.append(trades_train)
        all_holdout.append(trades_hold)

    if not all_train:
        print("  ✗ No hay datos suficientes para reentrenar. Fin.")
        sys.exit(1)

    df_train_all = pd.concat(all_train, ignore_index=True)
    df_hold_all  = pd.concat(all_holdout, ignore_index=True)

    print(f"\n  Total train: {len(df_train_all)} trades | holdout: {len(df_hold_all)} trades")

    # Entrenar nuevo modelo
    print("\n  Entrenando nuevo modelo...")
    new_clf = train_model(df_train_all)
    new_eval = evaluate_model(new_clf, df_hold_all)
    print(f"  Nuevo modelo — AUC={new_eval['auc']} | WR@0.55={new_eval['wr_filtered']}% | "
          f"Coverage={new_eval['coverage']}%")

    # Comparar con modelo actual
    current_pkl  = MODEL_DIR / "v7_classifier_oos.pkl"
    with open(MODEL_DIR / "v7_classifier_oos_meta.json") as f:
        current_meta = json.load(f)
    with open(current_pkl, "rb") as f:
        current_clf = pickle.load(f)
    current_eval = evaluate_model(current_clf, df_hold_all)
    print(f"  Modelo actual — AUC={current_eval['auc']} | WR@0.55={current_eval['wr_filtered']}% | "
          f"Coverage={current_eval['coverage']}%")

    # Decisión
    improved = new_eval["auc"] >= current_eval["auc"] - 0.01  # tolerancia -1%
    if improved or args.force:
        tag = datetime.now().strftime("%Y%m%d")
        out_pkl  = V8_MODEL / f"v8_clf_{tag}.pkl"
        out_meta = V8_MODEL / f"v8_clf_{tag}_meta.json"
        with open(out_pkl, "wb") as f:
            pickle.dump(new_clf, f)
        meta = {
            "model_type":    "XGBoost",
            "feature_cols":  FEATURE_COLS,
            "threshold":     0.55,
            "train_start":   str(train_start.date()),
            "train_end":     str(holdout_start.date()),
            "holdout_start": str(holdout_start.date()),
            "auc_holdout":   new_eval["auc"],
            "wr_holdout":    new_eval["wr_filtered"],
            "trained_on":    tag,
        }
        with open(out_meta, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"\n  ✓ Nuevo modelo guardado: {out_pkl.name}")
        print(f"    AUC: {current_eval['auc']} → {new_eval['auc']} "
              f"({'↑' if new_eval['auc'] > current_eval['auc'] else '='} {new_eval['auc']-current_eval['auc']:+.3f})")

        # Actualizar modelo V7 en producción y marcar fecha de entrenamiento
        import shutil
        shutil.copy(out_pkl, current_pkl)
        current_meta.update({
            "auc_holdout":   new_eval["auc"],
            "wr_holdout":    new_eval["wr_filtered"],
            "trained_on":    tag,
            "train_start":   str(train_start.date()),
            "train_end":     str(holdout_start.date()),
        })
        with open(MODEL_DIR / "v7_classifier_oos_meta.json", "w") as f:
            json.dump(current_meta, f, indent=2)
        print(f"    ✓ Modelo V7 en producción actualizado y fecha registrada ({tag})")
    else:
        print(f"\n  ✗ El nuevo modelo empeora el AUC ({current_eval['auc']} → {new_eval['auc']})")
        print(f"    Modelo actual conservado. Usa --force para guardar igualmente.")

    print(f"\n{'='*65}\n")
