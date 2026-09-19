"""
Idea del usuario, 14-sept-2026: una racha de techos (o suelos) cada vez mas
altos (bajos) y seguidos en el tiempo es señal de tendencia fuerte -- y
cuando esa racha se ROMPE (aparece un techo mas bajo que el anterior,
tras una racha ya valida), es un buen momento para cerrar una posicion que
dependia de esa tendencia. Verificado cualitativamente con un caso real
(ETH, feb-marzo 2024: techos cada 1-2 dias, cada uno mas alto, con
probabilidad subiendo de forma sostenida 0.42->0.57).

100% CAUSAL: solo compara cada techo/suelo con los anteriores YA
confirmados en el pasado, nunca con el futuro. Es interpretacion de una
SECUENCIA de patrones ya detectados por el motor -- el propio usuario lo
identifico como un filtro de contexto, no un motor nuevo.

Definicion exacta (para no dejarla "a ojo"):
- Se recorren los techos (o suelos) confirmados en orden cronologico.
- `racha_len` cuenta cuantos seguidos son cada uno MAS ALTO (bajo) que el
  anterior Y a menos de `M` dias del anterior. Si no se cumple alguna de
  las dos cosas, la racha se corta y vuelve a empezar en 1.
- El dia en que la racha se corta HABIENDO llegado antes a `N` o mas
  (racha_len >= N antes de romperse), se marca ese dia como "racha rota"
  -- ese es el momento de cerrar una posicion que dependia de la
  tendencia.

Uso en `salidas/`: `racha_rota_techo` se usa como señal de cierre para
posiciones LARGAS (dependen de que el precio siga subiendo -- si la racha
de techos crecientes se rompe, la tendencia que sostenia el largo se
rompio). `racha_rota_suelo`, simetrico, para posiciones CORTAS.

Se prueba SOLA esta idea (sin señal contraria, sin trailing, sin cambio de
regimen -- ya descartados hoy). Metrica: exceso sobre comprar-y-aguantar
el mismo periodo (observacion 0011). Validacion cruzada de siempre: ETH
ajusta, BTC confirma. Config de salidas/ ya aceptada: k_atr_stop=2.5,
r_fijo=3.0, dias_maximo=45.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_suelo import minimos_aparentes
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from entradas.doble_techo import maximos_aparentes
from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.comparacion_salida_fija_vs_dinamica import _candidatos
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

K_ATR_STOP, R_FIJO, DIAS_MAXIMO = 2.5, 3.0, 45
N_GRID = [2, 3, 4, 5]
M_GRID = [3, 5, 7, 10, 15]


def _puntos_confirmados(df, aparentes_fn, en_vivo_fn):
    """[(idx, precio)] de cada maximo/minimo aparente que el sistema causal
    pudo puntuar -- mismo criterio que el mapa de probabilidad de hoy."""
    close = df["close"].to_numpy()
    out = []
    for idx in aparentes_fn(close):
        if en_vivo_fn(df, idx, dia_transcurrido=0) is not None:
            out.append((idx, close[idx]))
    return out


def _racha_rota(puntos, n_len: int, m_dias: int, n_total: int, direccion_favorable: str = "creciente") -> np.ndarray:
    """`direccion_favorable="creciente"` para techos (largo: quiero techos cada vez
    mas altos, la racha se rompe con uno mas bajo). `direccion_favorable="decreciente"`
    para suelos (corto: quiero suelos cada vez mas bajos, la racha se rompe con uno
    mas alto) -- el BUG del 14-sept-2026 usaba "creciente" para los dos, comprobando
    la direccion equivocada para los cortos (una racha de suelos SUBIENDO, que es
    señal de tendencia ALCISTA, no bajista -- nunca protegia a un corto de verdad)."""
    rota = np.zeros(n_total, dtype=bool)
    racha_len = 1
    anterior = None
    for idx, precio in puntos:
        if anterior is not None:
            dias = idx - anterior[0]
            va_a_favor = (precio > anterior[1]) if direccion_favorable == "creciente" else (precio < anterior[1])
            if va_a_favor and dias <= m_dias:
                racha_len += 1
            else:
                if racha_len >= n_len:
                    rota[idx] = True
                racha_len = 1
        anterior = (idx, precio)
    return rota


def _excesos(df, candidatos, atr, racha_rota_techo, racha_rota_suelo):
    close = df["close"].to_numpy()
    excesos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, K_ATR_STOP, R_FIJO)
        # largo depende de que suban los techos; corto depende de que bajen los suelos
        senal = racha_rota_techo if direccion == "largo" else racha_rota_suelo
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
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_racha_tendencia")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_racha_tendencia")

    print("=== ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    n_eth = len(eth)
    puntos_techo_eth = _puntos_confirmados(eth, maximos_aparentes, en_vivo_techo)
    puntos_suelo_eth = _puntos_confirmados(eth, minimos_aparentes, en_vivo_suelo)

    base_eth = _resumen(_excesos(eth, cand_eth, atr_eth, None, None))
    print(f"SIN racha (base): {base_eth}")

    resultados = []
    for n_len in N_GRID:
        for m_dias in M_GRID:
            rota_techo = _racha_rota(puntos_techo_eth, n_len, m_dias, n_eth)
            rota_suelo = _racha_rota(puntos_suelo_eth, n_len, m_dias, n_eth, direccion_favorable="decreciente")
            r = _resumen(_excesos(eth, cand_eth, atr_eth, rota_techo, rota_suelo))
            resultados.append({"n_len": n_len, "m_dias": m_dias, **r})

    resultados.sort(key=lambda r: -r["exceso_medio"])
    print("\nTop 8 configs (N=longitud de racha, M=dias max entre puntos):")
    for r in resultados[:8]:
        print(" ", r)

    mejor = resultados[0]
    en_borde_n = mejor["n_len"] in (min(N_GRID), max(N_GRID))
    en_borde_m = mejor["m_dias"] in (min(M_GRID), max(M_GRID))
    print(f"mejor: {mejor} -- N {'EN EL BORDE' if en_borde_n else 'dentro'}, M {'EN EL BORDE' if en_borde_m else 'dentro'}")

    print("\n=== BTC (confirmacion, sin tocar N/M ganadores de ETH) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    n_btc = len(btc)
    puntos_techo_btc = _puntos_confirmados(btc, maximos_aparentes, en_vivo_techo)
    puntos_suelo_btc = _puntos_confirmados(btc, minimos_aparentes, en_vivo_suelo)

    base_btc = _resumen(_excesos(btc, cand_btc, atr_btc, None, None))
    rota_techo_btc = _racha_rota(puntos_techo_btc, mejor["n_len"], mejor["m_dias"], n_btc)
    rota_suelo_btc = _racha_rota(puntos_suelo_btc, mejor["n_len"], mejor["m_dias"], n_btc, direccion_favorable="decreciente")
    ganador_btc = _resumen(_excesos(btc, cand_btc, atr_btc, rota_techo_btc, rota_suelo_btc))
    print(f"SIN racha (base) en BTC: {base_btc}")
    print(f"N={mejor['n_len']}, M={mejor['m_dias']} (ganador de ETH) en BTC: {ganador_btc}")


if __name__ == "__main__":
    main()
