"""
bot_layer3.py — Señales externas Layer 3 (v6)
===============================================
Señales:
  1. Fear & Greed Index  — alternative.me (diario, contrarian en extremos)
  2. Funding Rate        — Bybit perpetuos cada 8h (contrarian en extremos)
  3. Ciclo Halving BTC   — macro overlay hardcoded (sin API)

Cada señal devuelve {"bull_mod": int, "bear_mod": int} listo para calculate_scores().
En modo backtest, precarga CSVs históricos y resuelve por fecha.
En modo live, llama a las APIs en tiempo real.
"""

import csv
import json
import urllib.request
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# =============================================================================
# HALVING CYCLE — macro overlay sin API
# =============================================================================

# Fecha del último halving (conocida, fija)
_HALVING_2024 = datetime(2024, 4, 19, tzinfo=timezone.utc)
_HALVING_2028 = datetime(2028, 4, 18, tzinfo=timezone.utc)  # estimado

def get_halving_phase(ts: datetime) -> dict:
    """
    Fases del ciclo de 4 años (basadas en días desde el último halving):
      pre_halving       (< -365 días): macro neutral, mercado indefinido
      pre_halving_run   (-365 a 0):    rally pre-halving histórico, sesgo alcista
      expansion         (0 a 365):     bull post-halving, sesgo alcista fuerte
      peak_zone         (365 a 540):   zona de techo, precaución
      bear              (540 a 730):   mercado bajista, sesgo bajista
      recuperacion      (730+):        recuperación gradual

    Returns {"bull_mod": int, "bear_mod": int, "phase": str, "days_since_halving": int}
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    # Halving de referencia (el más reciente anterior a ts)
    if ts >= _HALVING_2028:
        halving_ref = _HALVING_2028
    else:
        halving_ref = _HALVING_2024

    days = (ts - halving_ref).days

    if days < -365:
        phase, bull, bear = "pre_halving",      2, 2
    elif days < 0:
        phase, bull, bear = "pre_halving_run",  5, 1  # rally pre-halving
    elif days < 365:
        phase, bull, bear = "expansion",        6, 0
    elif days < 540:
        phase, bull, bear = "peak_zone",        2, 4
    elif days < 730:
        phase, bull, bear = "bear",             0, 6
    else:
        phase, bull, bear = "recuperacion",     3, 1

    return {"bull_mod": bull, "bear_mod": bear,
            "phase": phase, "days_since_halving": days}


# =============================================================================
# FEAR & GREED — carga CSV histórico para backtest
# =============================================================================

class FearGreedLoader:
    """Carga el CSV histórico de F&G y resuelve por fecha en O(log n)."""

    def __init__(self, csv_path: Path = None):
        if csv_path is None:
            csv_path = ROOT / "data" / "fear_greed_historical.csv"
        self._dates: list[int] = []   # timestamp unix (midnight UTC)
        self._values: list[int] = []  # 0-100
        self._loaded = False
        self._path = csv_path

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        with open(self._path) as f:
            for row in csv.DictReader(f):
                # formato: "DD-MM-YYYY" o "YYYY-MM-DD"
                raw = row["date"].strip()
                try:
                    if "-" in raw and len(raw.split("-")[0]) == 2:
                        dt = datetime.strptime(raw, "%d-%m-%Y").replace(tzinfo=timezone.utc)
                    else:
                        dt = datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    self._dates.append(int(dt.timestamp()))
                    self._values.append(int(row["value"]))
                except Exception:
                    pass

    def get(self, ts: datetime, phase: str = "neutral") -> dict:
        """Devuelve {"bull_mod": int, "bear_mod": int, "fg_value": int} para la fecha de ts."""
        self._load()
        if not self._dates:
            return {"bull_mod": 5, "bear_mod": 5, "fg_value": 50}

        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_day = int(datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc).timestamp())

        idx = bisect_right(self._dates, ts_day) - 1
        idx = max(0, min(idx, len(self._values) - 1))
        val = self._values[idx]

        return _fg_to_mods(val, phase=phase)


def _fg_to_mods(val: int, phase: str = "neutral") -> dict:
    """
    F&G → modificadores de score, consciente de la fase del ciclo.

    La interpretación contrarian clásica (Extreme Greed = vender) solo es válida cerca
    del techo del ciclo (peak_zone/bear). En fases bull (pre_halving_run, expansion)
    el Extreme Greed es señal de momentum, no de reversión.

    Fases bull    (pre_halving_run, expansion, recuperacion):
      Extreme Fear (<20):  bull+10, bear+0  (oportunidad de compra)
      Fear (20-39):        bull+7,  bear+2
      Neutral (40-59):     bull+5,  bear+5
      Greed (60-79):       bull+5,  bear+5  (momentum normal, neutral)
      Extreme Greed (≥80): bull+5,  bear+5  (momentum bull, no penalizar)

    Fase peak_zone:
      Extreme Fear:        bull+8,  bear+1
      Fear:                bull+6,  bear+3
      Neutral:             bull+5,  bear+5
      Greed:               bull+2,  bear+7  (distribución probable)
      Extreme Greed (≥80): bull+0,  bear+10 (señal de techo fuerte)

    Fase bear:
      Extreme Fear:        bull+7,  bear+2  (bounce contrarian, más débil)
      Fear:                bull+5,  bear+4
      Neutral:             bull+4,  bear+5
      Greed:               bull+1,  bear+8
      Extreme Greed:       bull+0,  bear+10
    """
    _bull_phases = {"pre_halving_run", "expansion", "recuperacion"}
    _is_bull  = phase in _bull_phases
    _is_peak  = phase == "peak_zone"

    if val < 20:
        if _is_bull:  return {"bull_mod": 10, "bear_mod": 0,  "fg_value": val}
        if _is_peak:  return {"bull_mod": 8,  "bear_mod": 1,  "fg_value": val}
        return              {"bull_mod": 7,  "bear_mod": 2,  "fg_value": val}  # bear
    if val < 40:
        if _is_bull:  return {"bull_mod": 7,  "bear_mod": 2,  "fg_value": val}
        if _is_peak:  return {"bull_mod": 6,  "bear_mod": 3,  "fg_value": val}
        return              {"bull_mod": 5,  "bear_mod": 4,  "fg_value": val}
    if val < 60:
        return {"bull_mod": 5, "bear_mod": 5, "fg_value": val}  # neutral en todas las fases
    if val < 80:
        if _is_bull:  return {"bull_mod": 5,  "bear_mod": 5,  "fg_value": val}  # momentum
        if _is_peak:  return {"bull_mod": 2,  "bear_mod": 7,  "fg_value": val}
        return              {"bull_mod": 1,  "bear_mod": 8,  "fg_value": val}
    # Extreme Greed ≥80
    if _is_bull:   return {"bull_mod": 5,  "bear_mod": 5,  "fg_value": val}  # momentum, no penalizar
    if _is_peak:   return {"bull_mod": 0,  "bear_mod": 10, "fg_value": val}  # señal de techo
    return               {"bull_mod": 0,  "bear_mod": 10, "fg_value": val}


def get_fear_greed_live() -> dict:
    """Descarga F&G actual de alternative.me (modo live)."""
    try:
        url = "https://api.alternative.me/fng/?limit=1&format=json"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        val = int(data["data"][0]["value"])
        return _fg_to_mods(val)
    except Exception:
        return {"bull_mod": 5, "bear_mod": 5, "fg_value": 50}


# =============================================================================
# FUNDING RATE — carga CSV histórico para backtest
# =============================================================================

class FundingRateLoader:
    """Carga el CSV histórico de funding rate y resuelve por timestamp en O(log n)."""

    def __init__(self, csv_path: Path = None):
        if csv_path is None:
            csv_path = ROOT / "data" / "funding_rate_historical.csv"
        self._timestamps: list[int] = []   # ms
        self._rates: list[float] = []
        self._loaded = False
        self._path = csv_path

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        with open(self._path) as f:
            for row in csv.DictReader(f):
                try:
                    self._timestamps.append(int(row["timestamp_ms"]))
                    self._rates.append(float(row["funding_rate"]))
                except Exception:
                    pass

    def get(self, ts: datetime, phase: str = "neutral") -> dict:
        """Devuelve {"bull_mod": int, "bear_mod": int, "funding_rate": float}."""
        self._load()
        if not self._timestamps:
            return {"bull_mod": 3, "bear_mod": 3, "funding_rate": 0.0}

        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_ms = int(ts.timestamp() * 1000)

        idx = bisect_right(self._timestamps, ts_ms) - 1
        idx = max(0, min(idx, len(self._rates) - 1))
        rate = self._rates[idx]

        return _funding_to_mods(rate, phase=phase)


def _funding_to_mods(rate: float, phase: str = "neutral") -> dict:
    """
    Funding rate → modificadores, consciente de la fase del ciclo.

    En fases bull (pre_halving_run, expansion) el funding positivo es normal —
    los umbrales de "peligro" se elevan para no penalizar innecesariamente los longs.

    Fases bull:
      > +0.15%:  bull+0, bear+7  (sobreextensión real incluso en bull)
      > +0.08%:  bull+2, bear+5
      > +0.03%:  bull+4, bear+4  (ligeramente caliente pero aceptable)
      -0.03%..+0.03%: bull+4, bear+3 (normal en bull)
      < -0.03%:  bull+7, bear+0  (shorts dominantes = señal muy alcista)

    Fases neutral/peak/bear:
      > +0.10%:  bull+0, bear+8
      > +0.05%:  bull+1, bear+6
      > +0.02%:  bull+3, bear+4
      neutral:   bull+3, bear+3
      < -0.02%:  bull+5, bear+1
      < -0.05%:  bull+8, bear+0
    """
    _bull_phases = {"pre_halving_run", "expansion", "recuperacion"}
    if phase in _bull_phases:
        if rate > 0.0015:    return {"bull_mod": 0, "bear_mod": 7, "funding_rate": rate}
        if rate > 0.0008:    return {"bull_mod": 2, "bear_mod": 5, "funding_rate": rate}
        if rate > 0.0003:    return {"bull_mod": 4, "bear_mod": 4, "funding_rate": rate}
        if rate >= -0.0003:  return {"bull_mod": 4, "bear_mod": 3, "funding_rate": rate}
        return                      {"bull_mod": 7, "bear_mod": 0, "funding_rate": rate}
    else:
        if rate > 0.0010:    return {"bull_mod": 0, "bear_mod": 8, "funding_rate": rate}
        if rate > 0.0005:    return {"bull_mod": 1, "bear_mod": 6, "funding_rate": rate}
        if rate > 0.0002:    return {"bull_mod": 3, "bear_mod": 4, "funding_rate": rate}
        if rate >= -0.0002:  return {"bull_mod": 3, "bear_mod": 3, "funding_rate": rate}
        if rate >= -0.0005:  return {"bull_mod": 5, "bear_mod": 1, "funding_rate": rate}
        return                      {"bull_mod": 8, "bear_mod": 0, "funding_rate": rate}


def get_funding_rate_live(symbol: str = "BTCUSDT") -> dict:
    """Descarga funding rate actual de Bybit (modo live)."""
    try:
        url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        rate = float(data["result"]["list"][0]["fundingRate"])
        return _funding_to_mods(rate)
    except Exception:
        return {"bull_mod": 3, "bear_mod": 3, "funding_rate": 0.0}


# =============================================================================
# FUNDING RATE TIMING — ajuste por ciclo de cobro (00:00 / 08:00 / 16:00 UTC)
# =============================================================================

def _funding_timing_adj(ts: datetime, funding_rate: float) -> dict:
    """
    Ajuste temporal basado en el ciclo de cobro del funding.

    Los funding positivos altos hacen que los longs cierren posiciones en los
    30 minutos previos al cobro (para no pagar). Esto crea presión bajista pre-cobro
    y una recuperación post-cobro cuando esa presión desaparece.

    Aplica solo si |funding| supera un umbral mínimo.
    """
    _FUNDING_HOURS = [0, 8, 16]  # UTC
    cur_min = ts.hour * 60 + ts.minute

    mins_to_next  = min(((h * 60 - cur_min) % 1440) for h in _FUNDING_HOURS)
    mins_since    = min(((cur_min - h * 60) % 1440) for h in _FUNDING_HOURS)

    # Sin ajuste si funding bajo
    if abs(funding_rate) < 0.0003:
        return {"bull_adj": 0, "bear_adj": 0, "timing": "normal"}

    if funding_rate > 0.0008:          # funding positivo alto
        if mins_to_next <= 30:         # longs cerrando → presión bajista
            return {"bull_adj": -3, "bear_adj": 3, "timing": "pre_fund_sell"}
        if mins_since <= 30:           # presión desaparece → rebote
            return {"bull_adj": 2, "bear_adj": -2, "timing": "post_fund_buy"}
    elif funding_rate < -0.0003:       # funding negativo → shorts cerrando
        if mins_to_next <= 30:
            return {"bull_adj": 2, "bear_adj": -2, "timing": "pre_fund_short_cover"}
        if mins_since <= 30:
            return {"bull_adj": -1, "bear_adj": 1, "timing": "post_fund_neutral"}

    return {"bull_adj": 0, "bear_adj": 0, "timing": "normal"}


# =============================================================================
# HELPER: get_layer3_extras() — resuelve las 3 señales a la vez
# =============================================================================

# =============================================================================
# OPEN INTEREST — carga CSV histórico 4h para backtest
# =============================================================================

class OILoader:
    """Carga OI histórico 4h y resuelve por timestamp en O(log n).
    Guarda las últimas N velas para calcular rate-of-change."""

    _LOOKBACK = 3  # velas 4h para comparar (12h atrás)

    def __init__(self, csv_path: Path = None):
        if csv_path is None:
            csv_path = ROOT / "data" / "oi_historical_4h.csv"
        self._timestamps: list[int] = []
        self._ois: list[float] = []
        self._loaded = False
        self._path = csv_path

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        with open(self._path) as f:
            for row in csv.DictReader(f):
                try:
                    self._timestamps.append(int(row["timestamp_ms"]))
                    self._ois.append(float(row["open_interest"]))
                except Exception:
                    pass

    def get(self, ts: datetime) -> dict:
        """Devuelve {"bull_mod": int, "bear_mod": int, "oi_roc": float, "oi_signal": str}."""
        self._load()
        if not self._timestamps:
            return {"bull_mod": 3, "bear_mod": 3, "oi_roc": 0.0, "oi_signal": "sin_datos"}

        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_ms = int(ts.timestamp() * 1000)

        idx = bisect_right(self._timestamps, ts_ms) - 1
        idx = max(self._LOOKBACK, min(idx, len(self._ois) - 1))

        oi_now  = self._ois[idx]
        oi_prev = self._ois[idx - self._LOOKBACK]
        if oi_prev == 0:
            return {"bull_mod": 3, "bear_mod": 3, "oi_roc": 0.0, "oi_signal": "sin_datos"}

        roc = (oi_now - oi_prev) / oi_prev  # fracción de cambio en 12h

        return _oi_to_mods(roc)


def _oi_to_mods(roc: float) -> dict:
    """
    OI Rate of Change → modificadores.
    La señal real requiere comparar OI + dirección de precio, pero en backtest
    el OI solo ya aporta información sobre la fuerza del movimiento:

    OI sube mucho  (roc > +3%):   nuevas posiciones entrando → momentum fuerte → +5 al dominante
    OI sube algo   (+1% a +3%):   posiciones acumulándose → +3 al dominante
    OI estable     (-1% a +1%):   neutral
    OI baja algo   (-3% a -1%):   cierre de posiciones → precaución, -2 al dominante
    OI baja mucho  (< -3%):       liquidaciones / short squeeze potencial → neutro/contrarian
    """
    if roc > 0.03:
        signal = "oi_up_strong"
        return {"bull_mod": 5, "bear_mod": 5, "oi_roc": roc, "oi_signal": signal}
    if roc > 0.01:
        signal = "oi_up"
        return {"bull_mod": 4, "bear_mod": 4, "oi_roc": roc, "oi_signal": signal}
    if roc >= -0.01:
        signal = "oi_stable"
        return {"bull_mod": 3, "bear_mod": 3, "oi_roc": roc, "oi_signal": signal}
    if roc >= -0.03:
        signal = "oi_down"
        return {"bull_mod": 2, "bear_mod": 2, "oi_roc": roc, "oi_signal": signal}
    # OI baja mucho → posible short squeeze o capitulación
    signal = "oi_down_strong"
    return {"bull_mod": 3, "bear_mod": 3, "oi_roc": roc, "oi_signal": signal}


_fg_loader      = FearGreedLoader()
_funding_loader = FundingRateLoader()
_oi_loader      = OILoader()


def get_layer3_extras(ts: datetime) -> dict:
    """
    Devuelve live_extras con F&G, funding, OI y macro_corr (halving) para la fecha dada.
    F&G y funding son conscientes de la fase del ciclo para evitar señales incorrectas
    en fases bull (p.ej. Extreme Greed en bull run ≠ señal de techo).
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    halving = get_halving_phase(ts)
    phase   = halving["phase"]

    fg      = _fg_loader.get(ts, phase=phase)
    funding = _funding_loader.get(ts, phase=phase)
    oi      = _oi_loader.get(ts)

    _rate = funding.get("funding_rate", 0.0)

    return {
        "fear_greed":  fg,
        "funding":     funding,
        "oi":          oi,
        "macro_corr":  {"bull_mod": halving["bull_mod"], "bear_mod": halving["bear_mod"]},
        "sentiment":   {"bullish_score": 0, "bearish_score": 0},
        "orderbook":   {"bull_mod": 0, "bear_mod": 0},
        "_debug": {
            "fg_value":           fg.get("fg_value"),
            "funding_rate":       _rate,
            "oi_roc":             oi.get("oi_roc"),
            "oi_signal":          oi.get("oi_signal"),
            "halving_phase":      phase,
            "days_since_halving": halving["days_since_halving"],
        }
    }
