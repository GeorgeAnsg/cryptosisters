"""
Barrido del umbral de la señal de patrón contrario y de los días de
persistencia del cambio de régimen -- pendiente que quedó abierto tras
`prueba_cuenta_1000e.py`: las dos ideas se probaron con UN SOLO valor fijo
cada una (umbral=0.5, persistencia=3 días), violación de "no absolutos"
que podía estar ocultando que la idea sí ayuda con otro valor.

Métrica: retorno medio POR OPERACIÓN AISLADA (sin restricción de
solapamiento) -- la lección de la observación 0010 de task-observer: el
capital de una cuenta secuencial mezcla la calidad de la salida con
cuántas operaciones caben, así que para juzgar la señal en sí hay que
medir aislado. No se usa sharpe por operación aquí (ver observación 0009,
penaliza la dispersión buena) -- solo retorno medio, con el mismo aviso de
"vigilar el borde del rango" de la observación 0008.

Disciplina de validación cruzada del proyecto: barrido en ETH (Desarrollo,
población completa de técho2/fondo2 confirmados, no solo 2024 como en la
prueba de la cuenta -- aquí interesa la muestra más grande posible),
confirmación en BTC sin retocar nada.

k_atr_stop/r_fijo/dias_maximo se dejan FIJOS en la config moderada ya
usada en `prueba_cuenta_1000e.py` (2.5 / 3.0 / 45) -- a propósito, para
aislar el efecto de la señal nueva sin mezclarlo con el problema (todavía
sin resolver) del barrido de R (ver `salidas/README.md`).
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
from motores import regimen_mercado
from motores.regimen_mercado import TipoRegimen
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45  # config moderada, ver docstring
UMBRAL_CONTRARIA_GRID = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
DIAS_PERSISTENCIA_GRID = [1, 2, 3, 4, 5, 7, 10, 15]


def _candidatos(df):
    out = []
    for c in techo_motor.detectar(df):
        r = en_vivo_techo(df, c.idx_techo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_techo2, "corto", r.probabilidad_total_si_confirma))
    for c in suelo_motor.detectar(df):
        r = en_vivo_suelo(df, c.idx_fondo2, dia_transcurrido=0)
        if r is not None:
            out.append((c.idx_fondo2, "largo", r.probabilidad_total_si_confirma))
    return out


def _prob_contraria(df):
    """prob_para_corto[i] = probabilidad del candidato de SUELO en vivo si
    el dia i es un minimo aparente, si no NaN. Y viceversa para largo."""
    n = len(df)
    close = df["close"].to_numpy()
    prob_para_corto = np.full(n, np.nan)
    prob_para_largo = np.full(n, np.nan)
    for idx in minimos_aparentes(close):
        r = en_vivo_suelo(df, idx, dia_transcurrido=0)
        if r is not None:
            prob_para_corto[idx] = r.probabilidad_total_si_confirma
    for idx in maximos_aparentes(close):
        r = en_vivo_techo(df, idx, dia_transcurrido=0)
        if r is not None:
            prob_para_largo[idx] = r.probabilidad_total_si_confirma
    return prob_para_corto, prob_para_largo


def _desfavorable_regimen(df):
    n = len(df)
    sma200 = df["close"].rolling(200).mean()
    desfav_corto = np.zeros(n, dtype=bool)
    desfav_largo = np.zeros(n, dtype=bool)
    for i in range(n):
        tipo, _s = regimen_mercado.clasificar(df, i, sma200)
        desfav_corto[i] = tipo != TipoRegimen.BAJISTA
        desfav_largo[i] = tipo != TipoRegimen.ALCISTA
    return desfav_corto, desfav_largo


def _retornos(df, candidatos, atr, **kwargs):
    close = df["close"].to_numpy()
    retornos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        t = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, **kwargs)
        if t is not None:
            retornos.append(t.retorno_pct)
    return retornos


def _barrer_contraria(df, candidatos, atr, prob_corto, prob_largo):
    resultados = []
    for umbral in UMBRAL_CONTRARIA_GRID:
        senal_corto = prob_corto >= umbral
        senal_largo = prob_largo >= umbral
        retornos = []
        for idx, direccion, _prob in candidatos:
            if np.isnan(atr[idx]):
                continue
            senal = senal_corto if direccion == "corto" else senal_largo
            niveles = calcular_niveles_fijos(df["close"].to_numpy()[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
            t = simular_trade(df, idx, direccion, df["close"].to_numpy()[idx], niveles, DIAS_MAXIMO,
                               senal_externa=senal)
            if t is not None:
                retornos.append(t.retorno_pct)
        resultados.append({"umbral_contraria": umbral, "n": len(retornos),
                            "retorno_medio": round(float(np.mean(retornos)), 3)})
    return resultados


def _barrer_regimen(df, candidatos, atr, desfav_corto, desfav_largo):
    resultados = []
    for dias in DIAS_PERSISTENCIA_GRID:
        retornos = []
        for idx, direccion, _prob in candidatos:
            if np.isnan(atr[idx]):
                continue
            cond = desfav_corto if direccion == "corto" else desfav_largo
            niveles = calcular_niveles_fijos(df["close"].to_numpy()[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
            t = simular_trade(df, idx, direccion, df["close"].to_numpy()[idx], niveles, DIAS_MAXIMO,
                               condicion_persistente=cond, dias_persistencia=dias)
            if t is not None:
                retornos.append(t.retorno_pct)
        resultados.append({"dias_persistencia": dias, "n": len(retornos),
                            "retorno_medio": round(float(np.mean(retornos)), 3)})
    return resultados


def _en_el_borde(valor, grid):
    return valor in (min(grid), max(grid))


def main():
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_señales_salida")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_señales_salida")

    print("=== BARRIDO EN ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    base_eth = np.mean(_retornos(eth, cand_eth, atr_eth))
    print(f"candidatos ETH: {len(cand_eth)} -- BASE (sin señal): retorno_medio={base_eth:.3f}%")

    prob_corto_eth, prob_largo_eth = _prob_contraria(eth)
    r_contraria_eth = _barrer_contraria(eth, cand_eth, atr_eth, prob_corto_eth, prob_largo_eth)
    print("\nSeñal de patrón contrario, por umbral:")
    for r in r_contraria_eth:
        print(" ", r)
    mejor_contraria = max(r_contraria_eth, key=lambda r: r["retorno_medio"])
    print(f"  mejor: {mejor_contraria} -- {'EN EL BORDE' if _en_el_borde(mejor_contraria['umbral_contraria'], UMBRAL_CONTRARIA_GRID) else 'dentro del rango'}")

    desfav_corto_eth, desfav_largo_eth = _desfavorable_regimen(eth)
    r_regimen_eth = _barrer_regimen(eth, cand_eth, atr_eth, desfav_corto_eth, desfav_largo_eth)
    print("\nCambio de régimen, por días de persistencia:")
    for r in r_regimen_eth:
        print(" ", r)
    mejor_regimen = max(r_regimen_eth, key=lambda r: r["retorno_medio"])
    print(f"  mejor: {mejor_regimen} -- {'EN EL BORDE' if _en_el_borde(mejor_regimen['dias_persistencia'], DIAS_PERSISTENCIA_GRID) else 'dentro del rango'}")

    print("\n=== CONFIRMACION EN BTC (sin tocar los parametros ganadores de ETH) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    base_btc = np.mean(_retornos(btc, cand_btc, atr_btc))
    print(f"candidatos BTC: {len(cand_btc)} -- BASE (sin señal): retorno_medio={base_btc:.3f}%")

    prob_corto_btc, prob_largo_btc = _prob_contraria(btc)
    senal_corto_btc = prob_corto_btc >= mejor_contraria["umbral_contraria"]
    senal_largo_btc = prob_largo_btc >= mejor_contraria["umbral_contraria"]
    ret_contraria_btc = []
    for idx, direccion, _p in cand_btc:
        if np.isnan(atr_btc[idx]):
            continue
        senal = senal_corto_btc if direccion == "corto" else senal_largo_btc
        niveles = calcular_niveles_fijos(btc["close"].to_numpy()[idx], atr_btc[idx], direccion, K_ATR_STOP, R_FIJO)
        t = simular_trade(btc, idx, direccion, btc["close"].to_numpy()[idx], niveles, DIAS_MAXIMO, senal_externa=senal)
        if t is not None:
            ret_contraria_btc.append(t.retorno_pct)
    print(f"\nMejor umbral_contraria de ETH ({mejor_contraria['umbral_contraria']}) en BTC: "
          f"retorno_medio={np.mean(ret_contraria_btc):.3f}% (n={len(ret_contraria_btc)}) vs base BTC {base_btc:.3f}%")

    desfav_corto_btc, desfav_largo_btc = _desfavorable_regimen(btc)
    ret_regimen_btc = []
    for idx, direccion, _p in cand_btc:
        if np.isnan(atr_btc[idx]):
            continue
        cond = desfav_corto_btc if direccion == "corto" else desfav_largo_btc
        niveles = calcular_niveles_fijos(btc["close"].to_numpy()[idx], atr_btc[idx], direccion, K_ATR_STOP, R_FIJO)
        t = simular_trade(btc, idx, direccion, btc["close"].to_numpy()[idx], niveles, DIAS_MAXIMO,
                           condicion_persistente=cond, dias_persistencia=mejor_regimen["dias_persistencia"])
        if t is not None:
            ret_regimen_btc.append(t.retorno_pct)
    print(f"Mejor dias_persistencia de ETH ({mejor_regimen['dias_persistencia']}) en BTC: "
          f"retorno_medio={np.mean(ret_regimen_btc):.3f}% (n={len(ret_regimen_btc)}) vs base BTC {base_btc:.3f}%")


if __name__ == "__main__":
    main()
