"""
bot_intraday.py — Estrategia intraday (v6)
==========================================
Timeframe base: 15m
HTF: 4h como veto duro (bloquea entradas contra la tendencia de 4h)

Parámetros típicos:
  SL: 1.5-2×ATR  |  TP: 3-5×ATR  |  Duración: 1-8h

Diferencia clave respecto a v5:
  - Si HTF 4h es bajista → htf_blocks_long = True (veto total, no penalización)
  - Si HTF 4h es alcista → htf_blocks_short = True
  - En neutral/parcial → no bloquea (la penalización del v5 ya no existe)

Uso:
    from v6.strategies.bot_intraday import IntradayStrategy
    strategy = IntradayStrategy()
    signal = strategy.get_signal(df_slice, live_extras)
"""

from v6.core.bot_indicators import (
    analyze_ltf, detect_regime_auto, compute_indicators,
)
from v6.core.bot_risk import calculate_scores
from v6.core.bot_core import Signal

import pandas as pd


class Strategy15m:
    """Estrategia intraday 15m con filtro HTF 4h duro."""

    timeframe = "15m"

    # --- HTF veto: qué tendencias 4h bloquean qué dirección ---
    # "alcista" bloquea shorts, "bajista" bloquea longs, "lateral"/"parcial" no bloquea
    _HTF_BLOCKS_LONG  = {"bajista"}
    _HTF_BLOCKS_SHORT = {"alcista"}

    def get_signal(self, df_ltf: pd.DataFrame, live_extras: dict,
                   row=None) -> Signal:
        """Calcula la señal intraday.

        Parámetros:
          df_ltf      : DataFrame de velas 15m (con indicadores precalculados en backtest,
                        o velas raw en live — en live se llama a compute_indicators aquí)
          live_extras : {"sentiment": ..., "fear_greed": ..., "funding": ...,
                         "orderbook": ..., "macro_corr": ...}
          row         : Si no es None (modo backtest), usa esta fila directamente sin recalcular.

        Returns Signal con htf_blocks_long / htf_blocks_short como vetos duros.
        """
        if row is not None:
            # Modo backtest: indicadores ya precalculados
            prev_row = df_ltf.iloc[-2] if len(df_ltf) >= 2 else row
            tech = analyze_ltf(row, prev_row)
            regime = detect_regime_auto(row)
        else:
            # Modo live: calcular indicadores sobre la ventana
            df_with_ind = compute_indicators(df_ltf)
            last     = df_with_ind.iloc[-1]
            prev     = df_with_ind.iloc[-2] if len(df_with_ind) >= 2 else last
            tech     = analyze_ltf(last, prev)
            regime   = detect_regime_auto(last)

        # HTF 4h — veto duro
        htf_trend    = tech["details"].get("htf_trend", "lateral")
        daily_strong = tech["details"].get("htf_1d_strong", "lateral")  # d_ema50 vs d_ema100 (lento)
        htf_blocks_long  = htf_trend in self._HTF_BLOCKS_LONG
        htf_blocks_short = htf_trend in self._HTF_BLOCKS_SHORT
        # Veto compuesto: 4h parcial + tendencia diaria SOSTENIDA (meses, no semanas) = bloqueo
        if htf_trend == "bajista parcial" and daily_strong == "bajista":
            htf_blocks_long = True
        if htf_trend == "alcista parcial" and daily_strong == "alcista":
            htf_blocks_short = True

        # Scoring combinado
        scores = calculate_scores(
            technical   = tech,
            sentiment   = live_extras.get("sentiment",  {"bullish_score": 0, "bearish_score": 0}),
            fear_greed  = live_extras.get("fear_greed", {"bull_mod": 5, "bear_mod": 5}),
            funding     = live_extras.get("funding",    {"bull_mod": 3, "bear_mod": 3}),
            orderbook   = live_extras.get("orderbook",  {"bull_mod": 0, "bear_mod": 0}),
            macro_corr  = live_extras.get("macro_corr", {"bull_mod": 0, "bear_mod": 0}),
            oi          = live_extras.get("oi",         {"bull_mod": 3, "bear_mod": 3}),
        )

        # Marcar tipo de trade en technical para que open_position lo registre
        tech["trade_type"] = "intraday"

        return Signal(
            bull_score       = scores["bullish_total"],
            bear_score       = scores["bearish_total"],
            technical        = tech,
            htf_blocks_long  = htf_blocks_long,
            htf_blocks_short = htf_blocks_short,
            regime           = regime,
        )
