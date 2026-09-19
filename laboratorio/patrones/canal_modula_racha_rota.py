"""15-sept-2026: idea del usuario -- no sustituir racha rota por canal
(eso ya se probo, empataba en el mejor caso, y perdia la proteccion real
que racha rota aporta contra el stop completo). En vez de eso, usar canal
para MODULAR que tan sensible es racha rota segun el contexto:

- Canal A FAVOR reciente (largo + ascendente confirmado, o corto +
  descendente confirmado): racha rota se vuelve MAS PERMISIVA -- exige una
  caida de pendiente mayor antes de cortar (el contexto dice que la
  subida/bajada sigue siendo sana).
- Canal EN CONTRA reciente (largo + descendente confirmado, o corto +
  ascendente confirmado): racha rota se vuelve MAS SENSIBLE -- corta con
  menos caida de pendiente (el contexto ya avisa de problema antes de que
  la pendiente lo confirme del todo).
- Sin canal reciente: umbral base de siempre (30%).

"Reciente" = canal confirmado en los ultimos VENTANA_RECIENTE_DIAS dias
(grid, no absoluto). Los umbrales FAVOR/CONTRA tambien se barren en grid.

Metodologia identica a canal_senal_salida_sistema_confirmado.py: mismo
stop/objetivo (K_ATR_STOP=1.2, R_FIJO=4.0), retorno por operacion aislada,
barrido en ETH, confirmacion en BTC sin retocar nada.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import N_LEN, M_DIAS
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import maximos_aparentes
from motores import canal_ascendente, canal_descendente
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 1.2, 4.0, 45
UMBRAL_BASE = 0.30
UMBRAL_GANANCIA_VENTA_PARCIAL, PORCENTAJE_VENTA_PARCIAL = 0.20, 0.50

VENTANA_RECIENTE_GRID = [5, 10, 15, 20]
UMBRAL_FAVOR_GRID = [0.30, 0.40, 0.50, 0.60]   # >= UMBRAL_BASE: mas permisivo
UMBRAL_CONTRA_GRID = [0.10, 0.15, 0.20, 0.30]  # <= UMBRAL_BASE: mas sensible


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
    return sorted(out, key=lambda c: c[0])


def _dias_confirmados(df, motor) -> np.ndarray:
    """Array booleano: True el dia exacto en que un canal (de ese motor)
    confirma su ruptura."""
    n = len(df)
    out = np.zeros(n, dtype=bool)
    for c in motor.calcular(df):
        if c.confirmado:
            out[c.idx_confirmacion] = True
    return out


def _reciente(confirmados: np.ndarray, ventana: int) -> np.ndarray:
    """True si hubo una confirmacion en los ultimos `ventana` dias
    (incluyendo hoy) -- causal, solo mira hacia atras."""
    n = len(confirmados)
    out = np.zeros(n, dtype=bool)
    ultimo = -10**9
    for i in range(n):
        if confirmados[i]:
            ultimo = i
        out[i] = (i - ultimo) <= ventana
    return out


def _preparar(df):
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    asc_confirmado = _dias_confirmados(df, canal_ascendente)
    desc_confirmado = _dias_confirmados(df, canal_descendente)
    return atr, racha_rota_techo, racha_rota_suelo, pendiente, asc_confirmado, desc_confirmado


def simular_trade(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                   racha_rota, pendiente, favor_reciente, contra_reciente,
                   umbral_favor, umbral_contra, usar_venta_parcial=True):
    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n = len(df)
    fin = min(idx_entrada + dias_maximo, n - 1)
    if fin <= idx_entrada:
        return None
    venta_hecha = False
    fraccion_restante = 1.0
    pnl_parcial_por_unidad = 0.0
    pendiente_extremo = 0.0
    for i in range(idx_entrada + 1, fin + 1):
        if usar_venta_parcial and not venta_hecha:
            ganancia_pct = (high[i] - precio_entrada) / precio_entrada if direccion == "largo" \
                else (precio_entrada - low[i]) / precio_entrada
            if ganancia_pct >= UMBRAL_GANANCIA_VENTA_PARCIAL:
                venta_hecha = True
                precio_vp = precio_entrada * (1 + UMBRAL_GANANCIA_VENTA_PARCIAL) if direccion == "largo" \
                    else precio_entrada * (1 - UMBRAL_GANANCIA_VENTA_PARCIAL)
                signo = 1 if direccion == "largo" else -1
                pnl_parcial_por_unidad = PORCENTAJE_VENTA_PARCIAL * signo * (precio_vp - precio_entrada)
                fraccion_restante = 1.0 - PORCENTAJE_VENTA_PARCIAL

        toca_stop = low[i] <= niveles.stop if direccion == "largo" else high[i] >= niveles.stop
        toca_objetivo = high[i] >= niveles.objetivo if direccion == "largo" else low[i] <= niveles.objetivo
        if toca_stop:
            return _res(i, niveles.stop, "stop", fraccion_restante, pnl_parcial_por_unidad)
        if toca_objetivo:
            return _res(i, niveles.objetivo, "objetivo", fraccion_restante, pnl_parcial_por_unidad)

        if racha_rota[i]:
            p = pendiente[i]
            if np.isnan(p):
                return _res(i, close[i], "racha_rota", fraccion_restante, pnl_parcial_por_unidad)
            umbral = umbral_contra if contra_reciente[i] else (umbral_favor if favor_reciente[i] else UMBRAL_BASE)
            if direccion == "largo":
                pendiente_extremo = max(pendiente_extremo, p)
                honra = pendiente_extremo <= 0 or p <= pendiente_extremo * (1 - umbral)
            else:
                pendiente_extremo = min(pendiente_extremo, p)
                honra = pendiente_extremo >= 0 or p >= pendiente_extremo * (1 - umbral)
            if honra:
                return _res(i, close[i], "racha_rota", fraccion_restante, pnl_parcial_por_unidad)
        else:
            p = pendiente[i]
            if not np.isnan(p):
                pendiente_extremo = max(pendiente_extremo, p) if direccion == "largo" else min(pendiente_extremo, p)
    return _res(fin, close[fin], "tiempo_maximo", fraccion_restante, pnl_parcial_por_unidad)


def _res(idx_salida, precio_salida, motivo, fraccion_restante, pnl_parcial_por_unidad):
    return dict(idx_salida=idx_salida, precio_salida=precio_salida, motivo=motivo,
                fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)


def _retorno_pct(precio_entrada, direccion, r):
    signo = 1 if direccion == "largo" else -1
    ret_resto = r["fraccion_restante"] * signo * (r["precio_salida"] - precio_entrada) / precio_entrada
    ret_parcial = r["pnl_parcial_por_unidad"] / precio_entrada
    return (ret_resto + ret_parcial) * 100


def _retornos(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, pendiente,
              favor_largo, contra_largo, favor_corto, contra_corto, umbral_favor, umbral_contra):
    close = df["close"].to_numpy()
    retornos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        racha = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        favor = favor_largo if direccion == "largo" else favor_corto
        contra = contra_largo if direccion == "largo" else contra_corto
        r = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, racha, pendiente,
                           favor, contra, umbral_favor, umbral_contra)
        if r is not None:
            retornos.append(_retorno_pct(close[idx], direccion, r))
    return retornos


def main():
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_modula_racha_eth")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_modula_racha_btc")

    atr_eth, rt_eth, rs_eth, pend_eth, asc_eth, desc_eth = _preparar(eth)
    cand_eth = _candidatos(eth)

    base_eth = np.mean(_retornos(eth, cand_eth, atr_eth, rt_eth, rs_eth, pend_eth,
                                  np.zeros(len(eth), bool), np.zeros(len(eth), bool),
                                  np.zeros(len(eth), bool), np.zeros(len(eth), bool), UMBRAL_BASE, UMBRAL_BASE))
    print(f"=== ETH (ajuste), candidatos={len(cand_eth)} ===")
    print(f"BASE (racha rota, umbral fijo 30%): retorno_medio={base_eth:.3f}%\n")

    print("Barrido ventana_reciente x umbral_favor x umbral_contra:")
    resultados = []
    for ventana in VENTANA_RECIENTE_GRID:
        favor_largo = _reciente(asc_eth, ventana); contra_largo = _reciente(desc_eth, ventana)
        favor_corto = _reciente(desc_eth, ventana); contra_corto = _reciente(asc_eth, ventana)
        for uf in UMBRAL_FAVOR_GRID:
            for uc in UMBRAL_CONTRA_GRID:
                rets = _retornos(eth, cand_eth, atr_eth, rt_eth, rs_eth, pend_eth,
                                  favor_largo, contra_largo, favor_corto, contra_corto, uf, uc)
                m = float(np.mean(rets))
                resultados.append({"ventana": ventana, "umbral_favor": uf, "umbral_contra": uc, "retorno_medio": round(m, 3)})

    mejores = sorted(resultados, key=lambda r: -r["retorno_medio"])[:8]
    for r in mejores:
        print(" ", r, "-- MEJORA" if r["retorno_medio"] > base_eth else "-- empeora")
    mejor = mejores[0]
    print(f"\nMejor combo: {mejor} vs base {base_eth:.3f}%")

    print("\n=== CONFIRMACION EN BTC (combo de ETH, sin retocar) ===")
    atr_btc, rt_btc, rs_btc, pend_btc, asc_btc, desc_btc = _preparar(btc)
    cand_btc = _candidatos(btc)
    base_btc = np.mean(_retornos(btc, cand_btc, atr_btc, rt_btc, rs_btc, pend_btc,
                                  np.zeros(len(btc), bool), np.zeros(len(btc), bool),
                                  np.zeros(len(btc), bool), np.zeros(len(btc), bool), UMBRAL_BASE, UMBRAL_BASE))
    favor_largo_b = _reciente(asc_btc, mejor["ventana"]); contra_largo_b = _reciente(desc_btc, mejor["ventana"])
    favor_corto_b = _reciente(desc_btc, mejor["ventana"]); contra_corto_b = _reciente(asc_btc, mejor["ventana"])
    rets_btc = _retornos(btc, cand_btc, atr_btc, rt_btc, rs_btc, pend_btc,
                          favor_largo_b, contra_largo_b, favor_corto_b, contra_corto_b,
                          mejor["umbral_favor"], mejor["umbral_contra"])
    ret_btc = float(np.mean(rets_btc))
    veredicto = "MEJORA sobre la base -- candidata seria" if ret_btc > base_btc else "NO mejora la base -- descartar"
    print(f"BASE BTC: {base_btc:.3f}%   CON MODULACION: {ret_btc:.3f}% -- {veredicto}")


if __name__ == "__main__":
    main()
