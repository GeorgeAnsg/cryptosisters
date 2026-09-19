"""15-sept-2026: repeticion de `canal_como_senal_salida.py` (que salio
"no mejora, descartar" contra el `salidas/stop_objetivo.py` BASICO) --
correccion pedida por el usuario en dos frentes:

1. Comparar contra el sistema de verdad en uso (K_ATR_STOP=1.2, R_FIJO=4.0,
   caida_relativa=30% para racha rota, venta parcial 20%/50%), ver
   `sistema_confirmado_switch_14sept2026.py` -- no el basico generico.
2. No descartar tras una unica variante -- se prueban 3 formas distintas
   de meter canal-en-contra:
     A) BASE: solo racha rota (como esta hoy, sin tocar).
     B) CANAL_DIRECTO: canal en contra confirmado corta EL MISMO DIA, sin
        pasar por el filtro de histeresis de pendiente de racha rota
        (es una señal geometrica especifica y rara, no ruido de pendiente
        del que haya que protegerse igual que de racha rota).
     C) COMBINADA: sale por lo que dispare antes entre racha rota Y canal
        directo.

Metrica: retorno medio POR OPERACION AISLADA (leccion de la observacion
0010 de task-observer, ya aplicada en barrido_señales_salida.py -- la
cuenta secuencial mezcla capacidad con calidad de señal). Candidatos:
poblacion completa de Desarrollo (igual que barrido_señales_salida.py),
no solo un año. Ajuste en ETH, confirmacion en BTC sin retocar nada.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.patrones.barrido_racha_tendencia import _puntos_confirmados, _racha_rota
from laboratorio.patrones.prueba_racha_filtrada_por_pendiente import _pendiente_atr
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.prueba_cuenta_1000e_v3_racha import N_LEN, M_DIAS
from motores import canal_ascendente, canal_descendente
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 1.2, 4.0, 45  # sistema confirmado 14-sept-2026
UMBRAL_CAIDA_RELATIVA_PENDIENTE = 0.30
UMBRAL_GANANCIA_VENTA_PARCIAL, PORCENTAJE_VENTA_PARCIAL = 0.20, 0.50
UMBRAL_PROB_CANAL_GRID = [0.0, 0.4, 0.5, 0.6, 0.7]


def _candidatos(df):
    """Candidatos REALES de doble techo/doble suelo (no todo minimo/maximo
    aparente -- ese conjunto mas amplio es solo para calcular la racha,
    ver _puntos_confirmados) -- mismo criterio que prueba_multi_anio.candidatos_por_año."""
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


def _canal_en_contra(df) -> tuple[np.ndarray, np.ndarray]:
    n = len(df)
    prob_largo = np.full(n, np.nan)  # largo sufre canal DESCENDENTE en contra
    prob_corto = np.full(n, np.nan)  # corto sufre canal ASCENDENTE en contra
    for c in canal_descendente.calcular(df):
        if c.confirmado:
            prob_largo[c.idx_confirmacion] = np.nanmax([prob_largo[c.idx_confirmacion], c.probabilidad_forma])
    for c in canal_ascendente.calcular(df):
        if c.confirmado:
            prob_corto[c.idx_confirmacion] = np.nanmax([prob_corto[c.idx_confirmacion], c.probabilidad_forma])
    return prob_largo, prob_corto


def simular_trade(df, idx_entrada, direccion, precio_entrada, niveles, dias_maximo,
                   racha_rota, canal_directo, pendiente, usar_venta_parcial=True):
    """Igual mecanica que sistema_confirmado_switch_14sept2026.simular_trade,
    con UNA rama nueva: `canal_directo` (booleano) corta EL MISMO DIA sin
    pasar por la histeresis de pendiente -- precedencia stop > objetivo >
    canal_directo > racha_rota (con histeresis) > tiempo_maximo."""
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
            return _resultado(i, niveles.stop, "stop", fraccion_restante, pnl_parcial_por_unidad)
        if toca_objetivo:
            return _resultado(i, niveles.objetivo, "objetivo", fraccion_restante, pnl_parcial_por_unidad)

        if canal_directo is not None and canal_directo[i]:
            return _resultado(i, close[i], "canal_en_contra", fraccion_restante, pnl_parcial_por_unidad)

        if racha_rota is not None and racha_rota[i]:
            p = pendiente[i]
            if np.isnan(p):
                return _resultado(i, close[i], "racha_rota", fraccion_restante, pnl_parcial_por_unidad)
            if direccion == "largo":
                pendiente_extremo = max(pendiente_extremo, p)
                honra = pendiente_extremo <= 0 or p <= pendiente_extremo * (1 - UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            else:
                pendiente_extremo = min(pendiente_extremo, p)
                honra = pendiente_extremo >= 0 or p >= pendiente_extremo * (1 - UMBRAL_CAIDA_RELATIVA_PENDIENTE)
            if honra:
                return _resultado(i, close[i], "racha_rota", fraccion_restante, pnl_parcial_por_unidad)
        else:
            p = pendiente[i]
            if not np.isnan(p):
                pendiente_extremo = max(pendiente_extremo, p) if direccion == "largo" else min(pendiente_extremo, p)
    return _resultado(fin, close[fin], "tiempo_maximo", fraccion_restante, pnl_parcial_por_unidad)


def _resultado(idx_salida, precio_salida, motivo, fraccion_restante, pnl_parcial_por_unidad):
    return dict(idx_salida=idx_salida, precio_salida=precio_salida, motivo=motivo,
                fraccion_restante=fraccion_restante, pnl_parcial_por_unidad=pnl_parcial_por_unidad)


def _retorno_pct(precio_entrada, direccion, r):
    signo = 1 if direccion == "largo" else -1
    ret_resto = r["fraccion_restante"] * signo * (r["precio_salida"] - precio_entrada) / precio_entrada
    ret_parcial = r["pnl_parcial_por_unidad"] / precio_entrada
    return (ret_resto + ret_parcial) * 100


def _retornos(df, candidatos, atr, racha_rota_techo, racha_rota_suelo, canal_largo, canal_corto, pendiente, umbral):
    close = df["close"].to_numpy()
    senal_canal_largo = np.nan_to_num(canal_largo, nan=-1) >= umbral if umbral is not None else None
    senal_canal_corto = np.nan_to_num(canal_corto, nan=-1) >= umbral if umbral is not None else None
    retornos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        racha = racha_rota_techo if direccion == "largo" else racha_rota_suelo
        canal_dir = None if senal_canal_largo is None else (senal_canal_largo if direccion == "largo" else senal_canal_corto)
        r = simular_trade(df, idx, direccion, close[idx], niveles, DIAS_MAXIMO, racha, canal_dir, pendiente)
        if r is not None:
            retornos.append(_retorno_pct(close[idx], direccion, r))
    return retornos


def _preparar(df):
    atr = atr_absoluto(df)
    n = len(df)
    puntos_techo = _puntos_confirmados(df, maximos_aparentes, en_vivo_techo)
    puntos_suelo = _puntos_confirmados(df, minimos_aparentes, en_vivo_suelo)
    racha_rota_techo = _racha_rota(puntos_techo, N_LEN, M_DIAS, n, direccion_favorable="creciente")
    racha_rota_suelo = _racha_rota(puntos_suelo, N_LEN, M_DIAS, n, direccion_favorable="decreciente")
    pendiente = _pendiente_atr(df, atr)
    canal_largo, canal_corto = _canal_en_contra(df)
    return atr, racha_rota_techo, racha_rota_suelo, pendiente, canal_largo, canal_corto


def main():
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="canal_senal_salida_sc_eth")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="canal_senal_salida_sc_btc")

    print("=== ETH (ajuste) -- sistema confirmado (K_ATR_STOP=1.2, R=4.0, venta parcial 20%/50%) ===")
    cand_eth = _candidatos(eth)
    atr_eth, rt_eth, rs_eth, pend_eth, cl_eth, cc_eth = _preparar(eth)

    base_eth = np.mean(_retornos(eth, cand_eth, atr_eth, rt_eth, rs_eth, cl_eth, cc_eth, pend_eth, umbral=None))
    print(f"candidatos: {len(cand_eth)}  A) BASE (solo racha rota): retorno_medio={base_eth:.3f}%\n")

    print("B) CANAL_DIRECTO (sustituye racha rota, corte inmediato), por umbral de probabilidad_forma:")
    resultados_b = []
    for umbral in UMBRAL_PROB_CANAL_GRID:
        rets = _retornos(eth, cand_eth, atr_eth, np.zeros_like(rt_eth), np.zeros_like(rs_eth), cl_eth, cc_eth, pend_eth, umbral)
        m = float(np.mean(rets))
        resultados_b.append({"umbral": umbral, "retorno_medio": round(m, 3)})
        print(f"  umbral={umbral}: retorno_medio={m:.3f}%", "-- MEJORA" if m > base_eth else "-- empeora")
    mejor_b = max(resultados_b, key=lambda r: r["retorno_medio"])

    print("\nC) COMBINADA (racha rota Y canal directo, lo que dispare antes), por umbral:")
    resultados_c = []
    for umbral in UMBRAL_PROB_CANAL_GRID:
        rets = _retornos(eth, cand_eth, atr_eth, rt_eth, rs_eth, cl_eth, cc_eth, pend_eth, umbral)
        m = float(np.mean(rets))
        resultados_c.append({"umbral": umbral, "retorno_medio": round(m, 3)})
        print(f"  umbral={umbral}: retorno_medio={m:.3f}%", "-- MEJORA" if m > base_eth else "-- empeora")
    mejor_c = max(resultados_c, key=lambda r: r["retorno_medio"])

    ganador = max(
        [("A_base", base_eth, None), ("B_canal_directo", mejor_b["retorno_medio"], mejor_b["umbral"]),
         ("C_combinada", mejor_c["retorno_medio"], mejor_c["umbral"])],
        key=lambda t: t[1],
    )
    print(f"\nGanador en ETH: {ganador[0]} ({ganador[1]:.3f}%, umbral={ganador[2]})\n")

    print("=== CONFIRMACION EN BTC (variante y umbral de ETH, sin retocar) ===")
    cand_btc = _candidatos(btc)
    atr_btc, rt_btc, rs_btc, pend_btc, cl_btc, cc_btc = _preparar(btc)
    base_btc = np.mean(_retornos(btc, cand_btc, atr_btc, rt_btc, rs_btc, cl_btc, cc_btc, pend_btc, umbral=None))
    print(f"candidatos BTC: {len(cand_btc)}  BASE: retorno_medio={base_btc:.3f}%")

    nombre, _valor_eth, umbral_ganador = ganador
    if nombre == "A_base":
        ret_btc = base_btc
    elif nombre == "B_canal_directo":
        ret_btc = np.mean(_retornos(btc, cand_btc, atr_btc, np.zeros_like(rt_btc), np.zeros_like(rs_btc), cl_btc, cc_btc, pend_btc, umbral_ganador))
    else:
        ret_btc = np.mean(_retornos(btc, cand_btc, atr_btc, rt_btc, rs_btc, cl_btc, cc_btc, pend_btc, umbral_ganador))
    veredicto = "MEJORA sobre la base -- candidata seria" if ret_btc > base_btc else "NO mejora la base -- descartar"
    print(f"{nombre} (umbral={umbral_ganador}) en BTC: retorno_medio={ret_btc:.3f}% vs base BTC {base_btc:.3f}% -- {veredicto}")


if __name__ == "__main__":
    main()
