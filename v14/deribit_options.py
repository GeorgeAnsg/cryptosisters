"""
V14 — Datos de volatilidad implícita BTC desde Deribit.

Fuente: API pública de Deribit (sin autenticación).
Dato principal: DVOL (índice de volatilidad implícita 30d, similar al VIX de crypto).

Lógica de scoring:
  DVOL < 40  → mercado complaciente / baja vol → +3 bull (tendencias limpias)
  DVOL 40-60 → régimen normal → neutro
  DVOL 60-75 → volatilidad elevada → -3 bull, reducir riesgo 20%
  DVOL > 75  → pánico / evento extremo → -5 bull, +3 bear, reducir riesgo 40%
  DVOL > 100 → pánico extremo → -8 bull, +5 bear, reducir riesgo 50%

Históricamente (2022-2026):
  Media: 57.8, p25: 48, p50: 56, p75: 65, max: 139 (FTX nov 2022)
  >80: solo 6.3% del tiempo (eventos de tail risk)
"""

import time
import urllib.request
import json
import logging

logger = logging.getLogger(__name__)

_DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"

# Caché sencilla: refrescar máximo cada 15 minutos
_cache: dict = {"dvol": None, "ts": 0}
_CACHE_TTL = 900  # segundos


def get_current_dvol(timeout: float = 5.0) -> float | None:
    """Devuelve el valor actual del DVOL BTC (índice de volatilidad implícita 30d)."""
    now = time.time()
    if _cache["dvol"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["dvol"]

    try:
        end_ms = int(now * 1000)
        start_ms = end_ms - 7_200_000  # últimas 2h
        url = f"{_DVOL_URL}?currency=BTC&resolution=3600&start_timestamp={start_ms}&end_timestamp={end_ms}"
        req = urllib.request.Request(url, headers={"User-Agent": "tradingbot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        rows = data["result"]["data"]
        if not rows:
            return None
        dvol = float(rows[-1][4])  # close del último candle
        _cache["dvol"] = dvol
        _cache["ts"] = now
        return dvol
    except Exception as e:
        logger.warning(f"[DVOL] Error fetching: {e}")
        return None


def dvol_score(dvol: float | None) -> dict:
    """
    Convierte el valor DVOL en modificadores de score y factor de riesgo.

    Calibrado para reemplazar Fear & Greed: el régimen normal (DVOL 40-65)
    aporta 5 bull + 5 bear, igual que F&G neutro, para no eliminar trades.
    La dirección se ajusta en extremos; el tamaño se reduce con DVOL alto.

    Distribución histórica 2022-2026:
      <40: 18%  |  40-65: 56%  |  65-80: 19%  |  >80: 6%

    Returns:
        dict con claves:
          bull_mod    — puntos a añadir al score alcista
          bear_mod    — puntos a añadir al score bajista
          risk_factor — multiplicador sobre risk_pct (1.0 = sin cambio)
          label       — descripción del régimen de volatilidad
    """
    if dvol is None:
        return {"bull_mod": 5, "bear_mod": 5, "risk_factor": 1.0, "label": "unknown"}

    if dvol > 100:
        # Pánico extremo (FTX, flash crash): reducir tamaño agresivamente
        return {"bull_mod": 3, "bear_mod": 6, "risk_factor": 0.50, "label": "panic_extreme"}
    elif dvol > 80:
        # Miedo alto: mercado muy volátil, reducir tamaño
        return {"bull_mod": 3, "bear_mod": 6, "risk_factor": 0.65, "label": "panic"}
    elif dvol > 65:
        # Volatilidad elevada: incertidumbre, ligero sesgo bajista
        return {"bull_mod": 4, "bear_mod": 5, "risk_factor": 0.80, "label": "elevated"}
    elif dvol > 40:
        # Rango normal: neutral, misma base que F&G neutro
        return {"bull_mod": 5, "bear_mod": 5, "risk_factor": 1.00, "label": "normal"}
    else:
        # Volatilidad baja: mercado trending, favorece momentum
        return {"bull_mod": 7, "bear_mod": 3, "risk_factor": 1.00, "label": "low_vol"}


def fetch_dvol_history(start_ts: int, end_ts: int, resolution: int = 3600) -> list[tuple[int, float]]:
    """
    Descarga histórico de DVOL entre dos timestamps Unix (segundos).
    Devuelve lista de (timestamp_ms, dvol_close).
    Útil para backtest.
    """
    STEP = 1000 * resolution
    all_rows = []
    curr = start_ts
    while curr < end_ts:
        curr_end = min(curr + STEP, end_ts)
        url = f"{_DVOL_URL}?currency=BTC&resolution={resolution}&start_timestamp={curr*1000}&end_timestamp={curr_end*1000}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tradingbot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.load(r)
            rows = data["result"]["data"]
            if rows:
                all_rows.extend((r[0], float(r[4])) for r in rows)
                curr = rows[-1][0] // 1000 + resolution
            else:
                curr = curr_end
        except Exception as e:
            logger.warning(f"[DVOL] history fetch error: {e}")
            curr = curr_end
        time.sleep(0.15)
    return all_rows


if __name__ == "__main__":
    dvol = get_current_dvol()
    print(f"BTC DVOL actual: {dvol:.1f}%" if dvol else "Error fetching DVOL")
    if dvol:
        s = dvol_score(dvol)
        print(f"Score → bull_mod={s['bull_mod']:+d}, bear_mod={s['bear_mod']:+d}, "
              f"risk_factor={s['risk_factor']:.0%}, régimen={s['label']}")
