"""
Resuelve el problema dejado abierto en `comparacion_salida_fija_vs_dinamica.py`
(ver `salidas/README.md`, "Estado 14-sept-2026"): el retorno medio y el
sharpe por operacion (simetrico) empujaban a extremos opuestos del rango de
R/k_atr_stop/dias_maximo -- diagnosticado como que la desviacion tipica
simetrica castiga la dispersion BUENA (ganar mas de lo esperado) igual que
la mala, lo cual esta mal para una salida con objetivo lejano (asimetrica
por diseno). Registrado como observacion 0009 de task-observer.

Solo se barre la variante FIJA -- la comparacion anterior ya establecio con
solidez (misma direccion en ETH y BTC, en las dos metricas de esa ronda)
que R fijo bate a R dependiente de la probabilidad, asi que la dinamica
queda descartada y no hace falta repetirla aqui.

Metrica nueva: SORTINO por operacion = retorno_medio / desviacion NEGATIVA
(solo con los retornos por debajo de 0 -- MAR=0, "no perder dinero" como
referencia, no la media de la muestra). A diferencia del sharpe por
operacion, un retorno grande y positivo no cuenta como "riesgo": solo las
perdidas aportan a la desviacion. Se reportan las tres metricas
(retorno_medio, sharpe_operacion, sortino_operacion) para poder comparar
en que se diferencian, no solo una.

Misma disciplina de siempre: barrido en ETH, confirmacion en BTC sin
retocar nada; se avisa automaticamente si el ganador cae en el borde del
rango probado (observacion 0008).
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from laboratorio.datos_lab import cargar_ohlcv_lab
from laboratorio.patrones.comparacion_salida_fija_vs_dinamica import _candidatos
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_fijos, simular_trade

# HALLAZGO 14-sept-2026, tras ampliar el rango una vez: ni retorno medio ni
# sharpe ni sortino convergen a un optimo interior -- las tres siguen
# empujando hacia R y dias_maximo cada vez mas grandes sin limite. Esto ya
# no es "falta rango": un objetivo cada vez mas lejano con un plazo cada vez
# mas largo tiende a "comprar y aguantar", que gana casi siempre en una
# muestra con sesgo alcista de fondo (Desarrollo = mayormente bull market).
# Ninguna de las tres metricas comparaba contra el baseline correcto
# (compra-y-aguantar el MISMO numero de dias que la operacion real estuvo
# abierta) -- viola la leccion ya conocida del proyecto ("comparar siempre
# contra el baseline correcto", skill:deteccion-flexible-patrones, leccion
# 6). Se corrige aqui: la metrica ya no es el retorno de la operacion, es el
# EXCESO sobre ese benchmark -- asi alargar el plazo o el objetivo deja de
# ganar automaticamente por sesgo alcista de fondo.


def _retornos_fija(df, candidatos, atr, k_atr_stop, r_fijo, dias_maximo):
    """Retorno de la operacion MENOS el retorno de comprar/vender y aguantar
    el mismo numero de dias (mismo idx_entrada, mismo idx_salida real) --
    aisla el valor añadido de la regla de salida frente al mero paso del
    tiempo en un mercado con tendencia."""
    close = df["close"].to_numpy()
    excesos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, k_atr_stop, r_fijo)
        t = simular_trade(df, idx, direccion, close[idx], niveles, dias_maximo)
        if t is None:
            continue
        signo = 1 if direccion == "largo" else -1
        retorno_benchmark = (close[t.idx_salida] - close[t.idx_entrada]) / close[t.idx_entrada] * 100 * signo
        excesos.append(t.retorno_pct - retorno_benchmark)
    return excesos

# Rangos ampliados el 14-sept-2026: con el rango anterior (k_atr_stop
# 1.5-6.0, r_fijo 1.0-10.0, dias_maximo 15-120), el ganador por Sortino caia
# en el borde en las TRES dimensiones (k_atr_stop minimo, r_fijo maximo,
# dias_maximo maximo) -- se amplian hasta que el optimo quede dentro, o
# hasta un limite razonable de negociacion real (mas de ~8-9 meses de
# holding period ya no es realista para este tipo de patron).
K_ATR_STOP_GRID = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
R_FIJO_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 13.0, 16.0, 20.0]
DIAS_MAXIMO_GRID = [15, 30, 45, 60, 90, 120, 150, 180, 220, 260]

_BORDES = {
    "k_atr_stop": (min(K_ATR_STOP_GRID), max(K_ATR_STOP_GRID)),
    "r_fijo": (min(R_FIJO_GRID), max(R_FIJO_GRID)),
    "dias_maximo": (min(DIAS_MAXIMO_GRID), max(DIAS_MAXIMO_GRID)),
}


def _en_el_borde(config: dict) -> list[str]:
    return [
        f"{clave}={config[clave]} (borde={borde})"
        for clave, borde in _BORDES.items()
        if clave in config and config[clave] in borde
    ]


def _resumen(ret: list[float]) -> dict:
    arr = np.array(ret)
    media = float(arr.mean())
    desv = float(arr.std(ddof=1)) if len(arr) > 1 else float("nan")
    sharpe = media / desv if desv > 0 else float("nan")

    negativos = arr[arr < 0]
    desv_negativa = float(negativos.std(ddof=1)) if len(negativos) > 1 else float("nan")
    if len(negativos) == 0:
        sortino = float("inf")
    elif desv_negativa > 0:
        sortino = media / desv_negativa
    else:
        sortino = float("nan")

    return {"n": len(arr), "retorno_medio": round(media, 3), "desv": round(desv, 3),
            "sharpe_operacion": round(sharpe, 3),
            "sortino_operacion": round(sortino, 3) if np.isfinite(sortino) else sortino}


def _barrer_fija(df, candidatos, atr):
    resultados = []
    for k in K_ATR_STOP_GRID:
        for dias in DIAS_MAXIMO_GRID:
            for r in R_FIJO_GRID:
                ret = _retornos_fija(df, candidatos, atr, k, r, dias)
                if ret:
                    resultados.append({
                        "k_atr_stop": k, "r_fijo": r, "dias_maximo": dias, **_resumen(ret),
                    })
    return resultados


def _reportar_top(resultados, metrica):
    def clave(r):
        v = r[metrica]
        if isinstance(v, float) and np.isnan(v):
            return -1e9
        return v
    resultados = sorted(resultados, key=clave, reverse=True)
    print(f"\nMejores 5 configs FIJAS por {metrica} (de {len(resultados)} probadas):")
    for r in resultados[:5]:
        print(" ", r)
    ganador = resultados[0]
    borde = _en_el_borde(ganador)
    if borde:
        print(f"  AVISO: el ganador tiene parametro(s) en el borde del rango -> {borde}")
    else:
        print("  ganador dentro del rango en todos los parametros (ninguno en el borde)")
    return ganador


def main():
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="barrido_fija_sortino")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="barrido_fija_sortino")

    print("=== BARRIDO EN ETH (ajuste, solo variante FIJA) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    print(f"candidatos ETH: {len(cand_eth)}")

    resultados_eth = _barrer_fija(eth, cand_eth, atr_eth)

    print("\n--- Ranking por RETORNO MEDIO ---")
    mejor_retorno = _reportar_top(resultados_eth, "retorno_medio")
    print("\n--- Ranking por SHARPE POR OPERACION (simetrico, referencia) ---")
    mejor_sharpe = _reportar_top(resultados_eth, "sharpe_operacion")
    print("\n--- Ranking por SORTINO POR OPERACION (solo penaliza perdidas) ---")
    mejor_sortino = _reportar_top(resultados_eth, "sortino_operacion")

    print("\n=== CONFIRMACION EN BTC (sin tocar los parametros ganadores de ETH) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    print(f"candidatos BTC: {len(cand_btc)}")

    for etiqueta, ganador in [
        ("RETORNO MEDIO", mejor_retorno),
        ("SHARPE POR OPERACION", mejor_sharpe),
        ("SORTINO POR OPERACION", mejor_sortino),
    ]:
        ret_btc = _retornos_fija(
            btc, cand_btc, atr_btc, ganador["k_atr_stop"], ganador["r_fijo"], ganador["dias_maximo"])
        r_btc = _resumen(ret_btc)
        print(f"\n-- ganador por {etiqueta}: {ganador} --")
        print(f"   en BTC -> {r_btc}")


if __name__ == "__main__":
    main()
