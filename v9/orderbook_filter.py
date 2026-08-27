"""
V9 — Filtro de muros de orderbook en tiempo real.

Consulta el endpoint de heatmap propio y detecta muros significativos
(notional >= WALL_MIN_NOTIONAL) entre el precio de entrada y el TP propuesto.

Uso típico:
    from v9.orderbook_filter import adjust_tp_for_walls, WallFilterResult
    result = adjust_tp_for_walls(
        side="long",
        entry_price=80000,
        proposed_tp=82000,
        pair="BTC/USDT:USDT",
    )
    if result.skip_trade:
        # primera pared demasiado cerca — no entrar
        ...
    else:
        # usar result.adjusted_tp en lugar del TP original
        rp["take_profit_atr_mult"] = ...  # recalcular desde adjusted_tp
"""

import os
import time
from dataclasses import dataclass
from typing import Optional
import urllib.request
import urllib.parse
import json

HEATMAP_BASE_URL = os.getenv(
    "HEATMAP_URL",
    "http://tu0mtnondcwqlyno8q2ewx5p.46.224.182.44.sslip.io",
)

WALL_MIN_NOTIONAL = float(os.getenv("WALL_MIN_NOTIONAL", "1_000_000"))

# Si el primer muro está a menos de este % del entry → skip
WALL_MIN_DISTANCE_PCT = 0.8

# Rango de búsqueda alrededor del precio actual (±%)
SEARCH_RANGE_PCT = 5.0

# Lookback para los niveles del orderbook (72h en ms)
LOOKBACK_MS = 72 * 60 * 60 * 1000

# TTL de la caché local (10 segundos — misma resolución que el worker)
_CACHE_TTL_S = 10

_cache: dict[str, tuple[float, list]] = {}  # symbol → (ts, levels)


@dataclass
class WallFilterResult:
    skip_trade: bool
    adjusted_tp: float
    original_tp: float
    nearest_wall_price: Optional[float]
    nearest_wall_notional: Optional[float]
    reason: str


def _fetch_levels(symbol: str) -> list[dict]:
    """Devuelve los niveles del heatmap con caché corta (10s)."""
    now = time.time()
    if symbol in _cache:
        ts, levels = _cache[symbol]
        if now - ts < _CACHE_TTL_S:
            return levels

    params = urllib.parse.urlencode({
        "symbol":     symbol,
        "lookbackMs": LOOKBACK_MS,
        "step":       25,
    })
    url = f"{HEATMAP_BASE_URL}/api/finance/heatmap?{params}"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read())
        levels = data.get("data", {}).get("levels", [])
    except Exception as e:
        levels = []
        print(f"[OBFilter] Error al consultar heatmap: {e}")

    _cache[symbol] = (now, levels)
    return levels


def _pair_to_symbol(pair: str) -> str:
    """'BTC/USDT:USDT' → 'BTCUSDT'"""
    base = pair.split("/")[0]
    return base + "USDT"


def adjust_tp_for_walls(
    side: str,
    entry_price: float,
    proposed_tp: float,
    pair: str,
) -> WallFilterResult:
    """
    Dado un trade (side='long'|'short', entry_price, proposed_tp), busca
    el primer muro significativo entre entry y TP y ajusta el TP.

    Para LONG: busca muros ask entre entry_price y proposed_tp.
    Para SHORT: busca muros bid entre proposed_tp y entry_price.

    Retorna WallFilterResult con:
      - skip_trade=True si el primer muro está demasiado cerca del entry
      - adjusted_tp ajustado justo por debajo/encima del primer muro (si existe)
      - adjusted_tp == proposed_tp si no hay muros relevantes
    """
    symbol = _pair_to_symbol(pair)
    levels = _fetch_levels(symbol)

    if side == "long":
        walls = [
            lv for lv in levels
            if lv["side"] == "ask"
            and entry_price < lv["price"] <= proposed_tp
            and lv["notional"] >= WALL_MIN_NOTIONAL
        ]
        walls.sort(key=lambda x: x["price"])
    else:
        walls = [
            lv for lv in levels
            if lv["side"] == "bid"
            and proposed_tp <= lv["price"] < entry_price
            and lv["notional"] >= WALL_MIN_NOTIONAL
        ]
        walls.sort(key=lambda x: x["price"], reverse=True)

    if not walls:
        return WallFilterResult(
            skip_trade=False,
            adjusted_tp=proposed_tp,
            original_tp=proposed_tp,
            nearest_wall_price=None,
            nearest_wall_notional=None,
            reason="sin_muros",
        )

    nearest = walls[0]
    wall_price = nearest["price"]
    wall_notional = nearest["notional"]
    distance_pct = abs(wall_price - entry_price) / entry_price * 100

    if distance_pct < WALL_MIN_DISTANCE_PCT:
        return WallFilterResult(
            skip_trade=True,
            adjusted_tp=proposed_tp,
            original_tp=proposed_tp,
            nearest_wall_price=wall_price,
            nearest_wall_notional=wall_notional,
            reason=f"muro_demasiado_cerca ({distance_pct:.2f}% < {WALL_MIN_DISTANCE_PCT}%)",
        )

    # Ajustar TP al 99.5% del muro (justo por debajo/encima)
    if side == "long":
        adjusted_tp = wall_price * 0.995
    else:
        adjusted_tp = wall_price * 1.005

    return WallFilterResult(
        skip_trade=False,
        adjusted_tp=round(adjusted_tp, 2),
        original_tp=proposed_tp,
        nearest_wall_price=wall_price,
        nearest_wall_notional=wall_notional,
        reason=f"tp_ajustado_por_muro_en_{wall_price}",
    )
