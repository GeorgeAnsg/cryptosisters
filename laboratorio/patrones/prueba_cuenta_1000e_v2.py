"""
Repite la prueba original del usuario ("con mil euros en un año, ¿qué
hace?", ver `prueba_cuenta_1000e.py`) pero con las dos capas ya
construidas y cerradas del 14-sept-2026:

- `salidas/stop_objetivo.py` con la config moderada aceptada: k_atr_stop=2.5,
  r_fijo=3.0, dias_maximo=45, señal de patrón contrario con umbral=0.7
  (ver salidas/README.md, "CERRADO por ahora").
- `tamano/tamano.py::calcular_tamano()` con la config conservadora aceptada:
  riesgo_base_pct=0.02, multiplicador_min=0.9, multiplicador_max=1.1 (ver
  tamano/README.md, "CERRADO por ahora, config conservadora aceptada") --
  sustituye el `RIESGO_PCT` fijo del 2% sin ajuste por ATR ni por
  probabilidad que usaba la version original de esta prueba.

Esto NO es un barrido ni un experimento de ajuste -- es una comprobacion
de cordura de las dos capas juntas, con los parametros YA decididos, antes
de pasar a `cartera/`. Mismo periodo que la prueba original: candidatos de
entrada en 2024 (el ultimo año civil completo de la particion Desarrollo),
usando el historico completo para que ATH/regimen se calculen bien.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

CAPITAL_INICIAL = 1000.0

# config de salidas/ ya aceptada (salidas/README.md)
K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45
UMBRAL_CONTRARIA = 0.7

# config de tamano/ ya aceptada (tamano/README.md)
RIESGO_BASE_PCT = 0.02
MULTIPLICADOR_MIN, MULTIPLICADOR_MAX = 0.9, 1.1

AÑO = 2024


def _candidatos_2024(df):
    fechas = df["open_time"]
    out = []
    for c in techo_motor.detectar(df):
        if fechas.iloc[c.idx_techo2].year != AÑO:
            continue
        r = en_vivo_techo(df, c.idx_techo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_techo2, "corto", r.probabilidad_total_si_confirma))
    for c in suelo_motor.detectar(df):
        if fechas.iloc[c.idx_fondo2].year != AÑO:
            continue
        r = en_vivo_suelo(df, c.idx_fondo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_fondo2, "largo", r.probabilidad_total_si_confirma))
    return sorted(out, key=lambda c: c[0])


def _serie_señal_contraria(df):
    n = len(df)
    contraria_para_corto = np.zeros(n, dtype=bool)
    contraria_para_largo = np.zeros(n, dtype=bool)
    close = df["close"].to_numpy()
    for idx in minimos_aparentes(close):
        r = en_vivo_suelo(df, idx, dia_transcurrido=0)
        if r is not None and r.probabilidad_total_si_confirma >= UMBRAL_CONTRARIA:
            contraria_para_corto[idx] = True
    for idx in maximos_aparentes(close):
        r = en_vivo_techo(df, idx, dia_transcurrido=0)
        if r is not None and r.probabilidad_total_si_confirma >= UMBRAL_CONTRARIA:
            contraria_para_largo[idx] = True
    return contraria_para_corto, contraria_para_largo


def _simular_cuenta(df, candidatos, atr, contraria_corto, contraria_largo):
    close = df["close"].to_numpy()
    fechas = df["open_time"]
    capital = CAPITAL_INICIAL
    curva = [(fechas.iloc[0], capital)]
    trades = []
    idx_libre_desde = 0

    for idx, direccion, prob in candidatos:
        if idx < idx_libre_desde or np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = contraria_corto if direccion == "corto" else contraria_largo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is None:
            continue

        pos = calcular_tamano(capital, niveles.riesgo, prob, RIESGO_BASE_PCT,
                               MULTIPLICADOR_MIN, MULTIPLICADOR_MAX)
        signo = 1 if direccion == "largo" else -1
        pnl = pos.unidades * (t.precio_salida - t.precio_entrada) * signo
        capital += pnl
        curva.append((fechas.iloc[t.idx_salida], capital))
        trades.append({
            "entrada": str(fechas.iloc[idx].date()), "direccion": direccion,
            "probabilidad": round(prob, 3), "multiplicador": pos.multiplicador_probabilidad,
            "riesgo_dinero_eur": round(pos.riesgo_dinero, 2), "motivo": t.motivo,
            "retorno_pct_precio": round(t.retorno_pct, 2), "pnl_eur": round(pnl, 2),
            "capital_tras": round(capital, 2),
        })
        idx_libre_desde = t.idx_salida + 1

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    motivos = {}
    for tr in trades:
        motivos[tr["motivo"]] = motivos.get(tr["motivo"], 0) + 1
    return capital, trades, drawdown_max_pct, motivos


def main():
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_cuenta_1000e_v2")
        atr = atr_absoluto(df)
        cand = _candidatos_2024(df)
        contraria_corto, contraria_largo = _serie_señal_contraria(df)

        print(f"\n=== {moneda} -- candidatos en 2024: {len(cand)} ===")
        capital, trades, dd, motivos = _simular_cuenta(df, cand, atr, contraria_corto, contraria_largo)

        print(f"Capital inicial: {CAPITAL_INICIAL:.2f} eur -- Capital final: {capital:.2f} eur "
              f"({(capital / CAPITAL_INICIAL - 1) * 100:+.1f}%)")
        print(f"Operaciones ejecutadas: {len(trades)} -- Drawdown máximo: {dd:.2f}% -- motivos: {motivos}")
        if trades:
            riesgos = [t["riesgo_dinero_eur"] for t in trades]
            mults = [t["multiplicador"] for t in trades]
            print(f"Riesgo por operación -- min={min(riesgos):.2f}€ max={max(riesgos):.2f}€ "
                  f"media={np.mean(riesgos):.2f}€ (multiplicador min={min(mults):.3f} max={max(mults):.3f})")
            print("\nDetalle de operaciones:")
            for t in trades:
                print(" ", t)


if __name__ == "__main__":
    main()
