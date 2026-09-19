"""18-sept-2026: version corregida de analyze_headline_sentiment
(v6/core/bot_sentiment.py, proyecto tr) para los mensajes de Telegram de
Cointelegraph -- ver memoria persistente project_corvus4_mecanismo_noticias.

El original hace `kw in texto` (substring), lo que produce coincidencias
por FRAGMENTO igual que el bug ya corregido en noticias_categorias.py:
"ban" dentro de "bankrupt"/"bank" (33 titulares), "hack" dentro de
"hackathon" (95), "ath" dentro de "marathon"/"hackathon" (21), "gain"
dentro de "against" (31), "fine" dentro de "finance"/"define" (29), etc.
-- medido sobre ETH 2021-2024 (GDELT). Aqui se reutiliza la misma tecnica
de palabra completa + sufijos verbales ya validada en noticias_categorias.py
en vez de duplicar logica nueva.

NOTA: el bug original sigue vivo en trading_bot_v4.py y trading_bot_v5.py
(proyecto tr) -- no se toca aqui porque es codigo de otro proyecto y no
hay ningun bot corriendo en vivo ahora mismo, pero queda pendiente si esa
version se retoma."""
from __future__ import annotations

from laboratorio.patrones.noticias_categorias import _patron_palabra_completa

BULLISH_KEYWORDS = [
    "bull", "bullish", "surge", "soar", "rally", "breakout", "moon",
    "all-time high", "ath", "pump", "gain", "growth", "adoption",
    "approved", "approval", "etf approved", "institutional",
    "partnership", "upgrade", "launch", "milestone", "record",
    "accumulation", "recovery", "support held", "inflows",
    "whale buying", "short squeeze", "golden cross",
]

BEARISH_KEYWORDS = [
    "bear", "bearish", "crash", "dump", "plunge", "drop", "sell-off",
    "selloff", "hack", "hacked", "exploit", "vulnerability", "ban",
    "banned", "regulation", "fine", "penalty", "lawsuit", "fraud",
    "scam", "rug pull", "rugpull", "bankruptcy", "insolvent",
    "liquidation", "fear", "panic", "collapse", "warning",
    "outflows", "whale selling", "death cross", "breakdown",
]

_PATRONES_BULL = [_patron_palabra_completa(kw) for kw in BULLISH_KEYWORDS]
_PATRONES_BEAR = [_patron_palabra_completa(kw) for kw in BEARISH_KEYWORDS]


def analyze_headline_sentiment(titulo: str) -> int:
    """+1 alcista, -1 bajista, 0 neutro/empate -- palabra completa, no
    fragmento (ver docstring del modulo)."""
    t = titulo.lower()
    bull = sum(1 for p in _PATRONES_BULL if p.search(t))
    bear = sum(1 for p in _PATRONES_BEAR if p.search(t))
    if bull > bear:
        return 1
    if bear > bull:
        return -1
    return 0
