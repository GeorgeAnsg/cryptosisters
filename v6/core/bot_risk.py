"""
bot_risk.py — Scoring, win-rate learning y calendario macro (v6)
================================================================
Responsabilidades:
  - calculate_scores(): combina scoring técnico + sentimiento + F&G + funding + OB + macro
  - Win-rate learning: build/load/save/merge tablas de win-rate por condición
  - get_learned_bonus(): ajuste de umbral basado en histórico
  - Calendario macro: FOMC, CPI, NFP → ventana ±2h de alta precaución
"""

import json
import ast
from datetime import datetime, date, timedelta, timezone


# =============================================================================
# SCORING COMBINADO
# =============================================================================

def calculate_scores(technical: dict, sentiment: dict, fear_greed: dict,
                     funding: dict = None, orderbook: dict = None,
                     macro_corr: dict = None, oi: dict = None) -> dict:
    """Dos scores independientes (0-100).

    Componentes:
      tech      (0-50)  | sentiment (0-15) | fear_greed (0-10)
      funding   (0-8)   | orderbook  (0-7) | macro_corr  (0-8)
      oi        (0-5)   — refuerza la señal dominante según momentum de OI
    Max teórico: 103 → normalizado a 100.
    """
    if funding is None:    funding    = {"bull_mod": 3, "bear_mod": 3}
    if orderbook is None:  orderbook  = {"bull_mod": 0, "bear_mod": 0}
    if macro_corr is None: macro_corr = {"bull_mod": 0, "bear_mod": 0}
    if oi is None:         oi         = {"bull_mod": 0, "bear_mod": 0}  # desactivado: necesita precio sincronizado

    tech_bull = technical.get("bullish_score", 0)
    tech_bear = technical.get("bearish_score", 0)
    sent_bull = sentiment.get("bullish_score", 0)
    sent_bear = sentiment.get("bearish_score", 0)
    fg_bull   = fear_greed.get("bull_mod", 5)
    fg_bear   = fear_greed.get("bear_mod", 5)
    fr_bull   = funding.get("bull_mod", 3)
    fr_bear   = funding.get("bear_mod", 3)
    ob_bull   = orderbook.get("bull_mod", 0)
    ob_bear   = orderbook.get("bear_mod", 0)
    mc_bull   = macro_corr.get("bull_mod", 0)
    mc_bear   = macro_corr.get("bear_mod", 0)
    oi_bull   = oi.get("bull_mod", 0)
    oi_bear   = oi.get("bear_mod", 0)

    raw_bull = tech_bull + sent_bull + fg_bull + fr_bull + ob_bull + mc_bull + oi_bull
    raw_bear = tech_bear + sent_bear + fg_bear + fr_bear + ob_bear + mc_bear + oi_bear

    bull_total = min(100, round(raw_bull * 100 / 98))
    bear_total = min(100, round(raw_bear * 100 / 98))

    return {
        "bullish_total": bull_total,
        "bearish_total": bear_total,
        "components": {
            "tech_bull": tech_bull, "tech_bear": tech_bear,
            "sent_bull": sent_bull, "sent_bear": sent_bear,
            "fg_bull":   fg_bull,   "fg_bear":   fg_bear,
            "fr_bull":   fr_bull,   "fr_bear":   fr_bear,
            "ob_bull":   ob_bull,   "ob_bear":   ob_bear,
            "mc_bull":   mc_bull,   "mc_bear":   mc_bear,
            "oi_bull":   oi_bull,   "oi_bear":   oi_bear,
        }
    }


# =============================================================================
# WIN-RATE LEARNING
# =============================================================================

def _make_condition_key(side: str, regime: str, rsi: float) -> tuple:
    rsi_b = "low" if rsi < 40 else ("high" if rsi > 65 else "mid")
    reg_b = regime if regime in ("bull", "bear", "neutral") else "neutral"
    return (side, reg_b, rsi_b)


def build_winrate_table(trades: list, min_trades: int = 8) -> dict:
    """Construye tabla de win-rate por condición de entrada."""
    buckets: dict = {}
    for t in trades:
        key = t.get("_condition_key")
        if not key:
            continue
        if key not in buckets:
            buckets[key] = {"wins": 0, "total": 0}
        buckets[key]["total"] += 1
        if t.get("pnl", 0) > 0:
            buckets[key]["wins"] += 1
    return {
        key: {"wr": round(c["wins"] / c["total"], 3), "n": c["total"]}
        for key, c in buckets.items()
        if c["total"] >= min_trades
    }


def _merge_winrate_tables(initial: dict, live: dict, min_live_trades: int = 8) -> dict:
    """Combina tabla inicial (entrenamiento) con tabla live (experiencia real).
    Un bucket live sobreescribe el inicial solo si tiene >= min_live_trades trades."""
    merged = dict(initial)
    for key, entry in live.items():
        if entry.get("n", 0) >= min_live_trades:
            merged[key] = entry
    return merged


def get_learned_bonus(side: str, regime: str, rsi: float, table: dict) -> int:
    """Ajuste de umbral de entrada (-6..+6) según win-rate histórico.

    Positivo → condición ganadora → umbral más bajo (más fácil entrar).
    Negativo → condición perdedora → umbral más alto (más difícil entrar).
    """
    if not table:
        return 0
    key   = _make_condition_key(side, regime, rsi)
    entry = table.get(key)
    if not entry:
        return 0
    wr = entry["wr"]
    if wr >= 0.68: return 6
    if wr >= 0.58: return 3
    if wr <= 0.32: return -6
    if wr <= 0.42: return -3
    return 0


def save_winrate_table(table: dict, path: str) -> None:
    serializable = {str(k): v for k, v in table.items()}
    with open(path, "w") as f:
        json.dump(serializable, f, indent=2)


def load_winrate_table(path: str) -> dict:
    try:
        with open(path) as f:
            raw = json.load(f)
        return {ast.literal_eval(k): v for k, v in raw.items()}
    except Exception:
        return {}


# =============================================================================
# CALENDARIO MACRO — FOMC, CPI, NFP
# =============================================================================

def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    days_ahead = (4 - d.weekday()) % 7
    return d + timedelta(days=days_ahead)


FOMC_DATES = {
    2023: ["2023-02-01","2023-03-22","2023-05-03","2023-06-14",
           "2023-07-26","2023-09-20","2023-11-01","2023-12-13"],
    2024: ["2024-01-31","2024-03-20","2024-05-01","2024-06-12",
           "2024-07-31","2024-09-18","2024-11-07","2024-12-18"],
    2025: ["2025-01-29","2025-03-19","2025-05-07","2025-06-18",
           "2025-07-30","2025-09-17","2025-11-05","2025-12-17"],
    2026: ["2026-01-28","2026-03-18","2026-05-06","2026-06-17",
           "2026-07-29","2026-09-16","2026-11-04","2026-12-09"],
}
FOMC_HOUR_UTC = 14

CPI_DATES = {
    2023: ["2023-01-12","2023-02-14","2023-03-14","2023-04-12",
           "2023-05-10","2023-06-13","2023-07-12","2023-08-10",
           "2023-09-13","2023-10-12","2023-11-14","2023-12-12"],
    2024: ["2024-01-11","2024-02-13","2024-03-12","2024-04-10",
           "2024-05-15","2024-06-12","2024-07-11","2024-08-14",
           "2024-09-11","2024-10-10","2024-11-13","2024-12-11"],
    2025: ["2025-01-15","2025-02-12","2025-03-12","2025-04-10",
           "2025-05-13","2025-06-11","2025-07-15","2025-08-12",
           "2025-09-10","2025-10-15","2025-11-13","2025-12-10"],
    2026: ["2026-01-14","2026-02-11","2026-03-11","2026-04-09",
           "2026-05-13","2026-06-10","2026-07-15","2026-08-12",
           "2026-09-09","2026-10-14","2026-11-12","2026-12-09"],
}
CPI_HOUR_UTC = 12


def get_macro_events(year: int) -> list:
    events = []
    for month in range(1, 13):
        d  = _first_friday(year, month)
        dt = datetime(d.year, d.month, d.day, 12, 30, tzinfo=timezone.utc)
        events.append((dt, "NFP"))
    for ds in FOMC_DATES.get(year, []):
        dt = datetime.fromisoformat(ds).replace(hour=FOMC_HOUR_UTC, tzinfo=timezone.utc)
        events.append((dt, "FOMC"))
    for ds in CPI_DATES.get(year, []):
        dt = datetime.fromisoformat(ds).replace(hour=CPI_HOUR_UTC, tzinfo=timezone.utc)
        events.append((dt, "CPI"))
    return events


def is_macro_event_window(ts, window_hours: float = 2.0) -> tuple:
    """True si ts está dentro de ±window_hours de cualquier evento macro."""
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    window = timedelta(hours=window_hours)
    for y in (ts.year - 1, ts.year, ts.year + 1):
        for event_dt, label in get_macro_events(y):
            if abs(ts - event_dt) <= window:
                return True, label
    return False, None
