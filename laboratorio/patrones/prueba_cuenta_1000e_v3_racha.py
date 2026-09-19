"""
Version persistida de la cuenta de 2024 con la señal aceptada a fecha
15-sept-2026: racha rota (N=4, M=5, `direccion_favorable` explicito y
corregido -- ver salidas/README.md y observacion 0015) en vez de la señal
contraria (RETRACTADA, ver salidas/README.md). Sustituye a
`prueba_cuenta_1000e_v2.py`, que quedo desactualizada (seguia usando la
señal contraria) -- leccion del propio proyecto (skill
deteccion-flexible-patrones, leccion 7): un resultado solo es reproducible
si el script que lo produjo esta en el repositorio, no solo en el
historial de una conversacion. Esta version genero los numeros usados en
el HTML de revision visual (19 operaciones, 13 ganadoras, 1153.10 eur).

Sigue siendo UNA sola posicion abierta a la vez (limite que `cartera/`
todavia no resuelve) -- es la base sobre la que se compara cualquier
version futura que permita varias posiciones simultaneas.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade
from tamano.tamano import calcular_tamano

CAPITAL_INICIAL = 1000.0

# config de salidas/ ya aceptada (salidas/README.md) + racha rota (N=4, M=5)
K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45
N_LEN, M_DIAS = 4, 5

# config de tamano/ ya aceptada (tamano/README.md)
RIESGO_BASE_PCT = 0.02
MULTIPLICADOR_MIN, MULTIPLICADOR_MAX = 0.9, 1.1

AÑO = 2024


def candidatos_2024(df):
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


def señales_racha(df):
    """largo depende de que sigan subiendo los techos; corto de que sigan bajando los suelos."""
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    return racha_rota_techo, racha_rota_suelo


def simular_cuenta_una_posicion(df, candidatos, atr, racha_rota_techo, racha_rota_suelo):
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
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
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
            "entrada": str(fechas.iloc[idx].date()), "salida": str(fechas.iloc[t.idx_salida].date()),
            "direccion": direccion, "probabilidad": round(prob, 3),
            "riesgo_dinero_eur": round(pos.riesgo_dinero, 2), "motivo": t.motivo,
            "retorno_pct_precio": round(t.retorno_pct, 2), "pnl_eur": round(pnl, 2),
            "capital_tras": round(capital, 2),
        })
        idx_libre_desde = t.idx_salida + 1

    valores = np.array([c for _, c in curva])
    pico = np.maximum.accumulate(valores)
    drawdown_max_pct = float(((valores - pico) / pico).min()) * 100 if len(valores) > 1 else 0.0
    return capital, trades, drawdown_max_pct


def main():
    for moneda in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(moneda, "1d", estrategia="prueba_cuenta_1000e_v3_racha")
        atr = atr_absoluto(df)
        cand = candidatos_2024(df)
        racha_rota_techo, racha_rota_suelo = señales_racha(df)

        print(f"\n=== {moneda} -- candidatos en 2024: {len(cand)} ===")
        capital, trades, dd = simular_cuenta_una_posicion(df, cand, atr, racha_rota_techo, racha_rota_suelo)
        ganadoras = sum(1 for t in trades if t["pnl_eur"] > 0)

        print(f"Capital inicial: {CAPITAL_INICIAL:.2f} eur -- Capital final: {capital:.2f} eur "
              f"({(capital / CAPITAL_INICIAL - 1) * 100:+.1f}%)")
        print(f"Operaciones ejecutadas: {len(trades)} ({ganadoras} ganadoras) -- Drawdown máximo: {dd:.2f}%")


if __name__ == "__main__":
    main()
