"""
Idea del usuario, 14-sept-2026: en vez de exigir una probabilidad alta
(0.7, ya retractada -- empeoraba) para la señal de patron contrario, cerrar
en cuanto aparezca el PRIMER patron contrario CONFIRMADO (doble techo/suelo
completo, la misma poblacion estricta que usan los candidatos de entrada),
sin exigir ninguna nota minima. Distinto de lo ya probado en
`barrido_umbral_en_ganancia.py` (umbral=0.0): aquella prueba usaba la
poblacion mas laxa de "maximos/minimos aparentes" (cualquier pico de 3
dias), esta usa la poblacion ESTRICTA de patrones ya confirmados por
`motores.detectar()` -- la misma que genera los candidatos de entrada.

Metrica: exceso sobre comprar-y-aguantar el mismo periodo (observacion
0011). Config de salidas/ ya aceptada: k_atr_stop=2.5, r_fijo=3.0,
dias_maximo=45. Validacion cruzada de siempre: ETH ajusta, BTC confirma
(aqui no hay parametro que barrer -- es una idea binaria, se compara
directamente en las dos monedas).
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.comparacion_salida_fija_vs_dinamica import _candidatos
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45


def _senales_contrarias_confirmadas(df):
    """senal_para_corto[i] = True si `i` es idx_fondo2 de CUALQUIER doble
    suelo confirmado (cierra un corto -- suelo es la señal contraria a un
    corto). Y viceversa para largo/techo."""
    n = len(df)
    senal_para_corto = np.zeros(n, dtype=bool)
    senal_para_largo = np.zeros(n, dtype=bool)
    for c in suelo_motor.detectar(df):
        senal_para_corto[c.idx_fondo2] = True
    for c in techo_motor.detectar(df):
        senal_para_largo[c.idx_techo2] = True
    return senal_para_corto, senal_para_largo


def _excesos(df, candidatos, atr, senal_corto=None, senal_largo=None):
    close = df["close"].to_numpy()
    excesos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        senal = None
        if senal_corto is not None:
            senal = senal_corto if direccion == "corto" else senal_largo
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is None:
            continue
        signo = 1 if direccion == "largo" else -1
        retorno_benchmark = (close[t.idx_salida] - close[t.idx_entrada]) / close[t.idx_entrada] * 100 * signo
        excesos.append(t.retorno_pct - retorno_benchmark)
    return excesos


def _resumen(excesos):
    arr = np.array(excesos)
    return {"n": len(arr), "exceso_medio": round(float(arr.mean()), 3),
            "exceso_mediana": round(float(np.median(arr)), 3)}


def main():
    for nombre in ["ETHUSDT", "BTCUSDT"]:
        df = cargar_ohlcv_lab(nombre, "1d", estrategia="prueba_cierre_primer_contrario")
        cand = _candidatos(df)
        atr = atr_absoluto(df)
        senal_corto, senal_largo = _senales_contrarias_confirmadas(df)

        sin = _resumen(_excesos(df, cand, atr))
        con = _resumen(_excesos(df, cand, atr, senal_corto, senal_largo))
        print(f"{nombre}")
        print(f"  SIN cierre por primer contrario: {sin}")
        print(f"  CON cierre por primer contrario confirmado (sin umbral): {con}")


if __name__ == "__main__":
    main()
