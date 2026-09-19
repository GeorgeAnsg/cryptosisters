"""
Primera prueba de `cartera/`: qué pasa si se permite más de UNA posición
abierta a la vez, en vez del límite actual (esperar a que se cierre la
anterior para poder abrir la siguiente).

Motivado por la revisión visual del 14/15-sept-2026: en la subida de
04-feb a 11-mar-2024, el sistema descartó 4 candidatos de largo con
probabilidad 0.79-0.96 solo porque ya había un corto abierto -- ver
salidas/README.md y cartera/README.md, que ya fijaba (8-sept-2026, antes
de escribir código) un límite operativo de 5 posiciones simultáneas
decidido por el usuario. Aquí se prueba ESE límite, y se compara con un
rango alrededor (1, 2, 3, 5, 10) para no aceptarlo como bueno solo porque
ya estaba escrito en el plan -- regla de "no absolutos" del proyecto.

Importante -- lo que este script NO hace todavía (fuera de alcance por
ahora, ver cartera/README.md):
- No hay arbitraje por calidad de motor (solo hay un motor -- doble
  suelo/techo -- nada que arbitrar entre varios todavía).
- No hay multiplicador de riesgo de cartera por correlación/volatilidad
  errática -- cada posición se dimensiona de forma independiente con
  `tamano/calcular_tamano()`, usando el capital YA REALIZADO (cerrado) en
  el momento de abrir, igual que la versión de una sola posición -- el
  riesgo de varias posiciones abiertas a la vez moviéndose juntas
  (correlación) no está limitado aquí, es precisamente el "riesgo de
  cartera" que el plan deja pendiente.
- Universo de candidatos: mismo doble suelo/techo de siempre, un único
  activo (ETH, confirmación en BTC). Multi-activo (BTC+ETH a la vez) es
  la siguiente pregunta, no esta.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import (
    CAPITAL_INICIAL, DIAS_MAXIMO, K_ATR_STOP, MULTIPLICADOR_MAX,
    MULTIPLICADOR_MIN, R_FIJO, RIESGO_BASE_PCT, candidatos_2024, señales_racha,
)
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

MAX_POSICIONES_GRID = [1, 2, 3, 5, 10]


def _resolver_trades(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, max_posiciones):
    """Admite un candidato si hay hueco (< max_posiciones abiertas en ese momento).
    Sin arbitraje por calidad -- orden cronológico simple, primero en llegar,
    primero en ocupar hueco (no hay más de un motor todavía que arbitrar)."""
    close = df["close"].to_numpy()
    admitidos, descartados = [], 0
    abiertas = []  # lista de idx_salida de posiciones activas

    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        abiertas = [fin for fin in abiertas if fin >= idx]  # purga las ya cerradas
        if len(abiertas) >= max_posiciones:
            descartados += 1
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is None:
            continue
        abiertas.append(t.idx_salida)
        admitidos.append({"idx_entrada": idx, "idx_salida": t.idx_salida, "direccion": direccion,
                           "probabilidad": prob, "riesgo": niveles.riesgo,
                           "precio_entrada": t.precio_entrada, "precio_salida": t.precio_salida,
                           "motivo": t.motivo, "retorno_pct": t.retorno_pct})
    return admitidos, descartados


def _simular_capital(df, admitidos):
    """Recorre entradas Y salidas en orden cronológico -- el tamaño de cada
    posición se decide con el capital YA REALIZADO en su momento de entrada
    (cierres previos), el pnl se aplica en el momento real de su cierre."""
    fechas = df["open_time"]
    eventos = []
    for i, tr in enumerate(admitidos):
        eventos.append((tr["idx_entrada"], 0, i, "entrada"))
        eventos.append((tr["idx_salida"], 1, i, "salida"))
    eventos.sort()  # a igual idx, entrada (0) antes que salida (1)

    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    unidades = {}
    for idx, _orden, i, tipo in eventos:
        tr = admitidos[i]
        if tipo == "entrada":
            pos = calcular_tamano(capital, tr["riesgo"], tr["probabilidad"],
                                   RIESGO_BASE_PCT, MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
            unidades[i] = pos.unidades
        else:
            signo = 1 if tr["direccion"] == "largo" else -1
            pnl = unidades[i] * (tr["precio_salida"] - tr["precio_entrada"]) * signo
            capital += pnl
            tr["pnl_eur"] = round(pnl, 2)
            curva.append((fechas.iloc[idx], capital))

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    return capital, drawdown_max_pct


def main():
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_cartera_multiposicion")
        atr = atr_absoluto(df)
        cand = candidatos_2024(df)
        racha_rota_techo, racha_rota_suelo = señales_racha(df)

        print(f"\n=== {moneda} -- candidatos en 2024: {len(cand)} ===")
        for max_pos in MAX_POSICIONES_GRID:
            admitidos, descartados = _resolver_trades(df, cand, atr, racha_rota_techo, racha_rota_suelo, max_pos)
            capital, dd = _simular_capital(df, admitidos)
            ganadoras = sum(1 for t in admitidos if t.get("pnl_eur", 0) > 0)
            print(f"  max_posiciones={max_pos:2d}: {len(admitidos):2d} ejecutadas "
                  f"({ganadoras} ganadoras, {descartados} descartadas por hueco) -- "
                  f"capital final {capital:.2f}€ ({(capital / CAPITAL_INICIAL - 1) * 100:+.1f}%) -- "
                  f"drawdown máx {dd:.2f}%")


if __name__ == "__main__":
    main()
