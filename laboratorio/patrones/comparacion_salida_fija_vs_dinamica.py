"""
Comparacion salida FIJA vs DINAMICA (R escalado por probabilidad_total),
usando `salidas/stop_objetivo.py`. Idea del usuario, 13-sept-2026: un
patron mas fuerte (probabilidad_total_si_confirma mas alta) quizas merece
un objetivo mas ambicioso -- se comprueba, no se asume, con un barrido de
configuraciones (no un solo R por variante, ver
`skill:deteccion-flexible-patrones`, "no absolutos").

Disciplina de validacion cruzada del proyecto (ver
`feedback_validacion_cruzada_solo_eth` en la memoria persistente): el
barrido de configuraciones se hace SOLO en ETH; los mejores parametros de
cada variante se confirman despues en BTC SIN TOCAR NADA. Solo particion
Desarrollo (`cargar_ohlcv_lab`, sin pedir acceso a Validacion/Reserva).

Poblacion de entrada: los techo2/fondo2 YA CONFIRMADOS por
`motores.detectar()` (mismo criterio usado y corregido el 12-sept-2026 en
`entradas/`, ver docstring de `entradas/doble_techo.py`) -- usa
informacion retrospectiva solo para decidir QUE puntos estudiar, no para
la decision de entrada en si (la entrada real sigue siendo dia 0).

REVISION 13-sept-2026 (segunda vuelta): la primera version de esta
comparacion tenia dos problemas encontrados DESPUES de correrla, no antes
(ver observacion 0008 de task-observer):
1. El ganador de las dos variantes caia en el extremo superior del rango
   probado en varios parametros (r_fijo, r_max, dias_maximo, e incluso
   k_atr_stop) -- se amplian aqui todos los rangos hasta que el ganador ya
   no este en el borde, o hasta entender por que crece sin limite.
2. "Retorno medio sin ajustar" puede estar premiando simplemente "esperar
   mas tiempo" en un mercado con sesgo alcista de fondo, no una salida
   genuinamente mejor. Se anade un ratio riesgo/recompensa (retorno medio
   / desviacion tipica de los retornos, tipo Sharpe por operacion, NO un
   Calmar de curva de capital -- eso exigiria decidir el orden y
   solapamiento de las operaciones, que es trabajo de `cartera/`, fuera
   del alcance de `salidas/`) como metrica secundaria, y se reportan
   ambas por separado en vez de asumir que coinciden.
"""
import sys

sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")

import numpy as np

from entradas.doble_suelo import calcular_en_vivo as en_vivo_suelo
from entradas.doble_techo import calcular_en_vivo as en_vivo_techo
from laboratorio.datos_lab import cargar_ohlcv_lab
from motores import doble_suelo as suelo_motor
from motores import doble_techo as techo_motor
from motores.volatilidad import atr_absoluto
from salidas.stop_objetivo import calcular_niveles_dinamicos, calcular_niveles_fijos, simular_trade

K_ATR_STOP_GRID = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
R_FIJO_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
R_MIN_GRID = [0.5, 1.0, 1.5, 2.0, 2.5]
R_MAX_GRID = [3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]
DIAS_MAXIMO_GRID = [15, 30, 45, 60, 90, 120]

# nombres de los parametros que se consideran "en el borde" del rango
# probado -- se comprueba automaticamente para no repetir el error de dar
# un ganador por bueno sin mirar donde cae.
_BORDES = {
    "k_atr_stop": (min(K_ATR_STOP_GRID), max(K_ATR_STOP_GRID)),
    "r_fijo": (min(R_FIJO_GRID), max(R_FIJO_GRID)),
    "r_min": (min(R_MIN_GRID), max(R_MIN_GRID)),
    "r_max": (min(R_MAX_GRID), max(R_MAX_GRID)),
    "dias_maximo": (min(DIAS_MAXIMO_GRID), max(DIAS_MAXIMO_GRID)),
}


def _en_el_borde(config: dict) -> list[str]:
    return [
        f"{clave}={config[clave]} (borde={borde})"
        for clave, borde in _BORDES.items()
        if clave in config and config[clave] in borde
    ]


def _candidatos(df):
    """[(idx, direccion, probabilidad_total_si_confirma), ...] para
    techo (corto) y suelo (largo) juntos."""
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


def _retornos_fija(df, candidatos, atr, k_atr_stop, r_fijo, dias_maximo):
    close = df["close"].to_numpy()
    retornos = []
    for idx, direccion, _prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_fijos(close[idx], atr[idx], direccion, k_atr_stop, r_fijo)
        t = simular_trade(df, idx, direccion, close[idx], niveles, dias_maximo)
        if t is not None:
            retornos.append(t.retorno_pct)
    return retornos


def _retornos_dinamica(df, candidatos, atr, k_atr_stop, r_min, r_max, dias_maximo):
    close = df["close"].to_numpy()
    retornos = []
    for idx, direccion, prob in candidatos:
        if np.isnan(atr[idx]):
            continue
        niveles = calcular_niveles_dinamicos(close[idx], atr[idx], direccion, k_atr_stop, r_min, r_max, prob)
        t = simular_trade(df, idx, direccion, close[idx], niveles, dias_maximo)
        if t is not None:
            retornos.append(t.retorno_pct)
    return retornos


def _resumen(ret: list[float]) -> dict:
    arr = np.array(ret)
    media = float(arr.mean())
    desv = float(arr.std(ddof=1)) if len(arr) > 1 else float("nan")
    sharpe = media / desv if desv > 0 else float("nan")
    return {"n": len(arr), "retorno_medio": round(media, 3), "desv": round(desv, 3),
            "sharpe_operacion": round(sharpe, 3)}


def _barrer(df, candidatos, atr):
    resultados_fija, resultados_dinamica = [], []
    for k in K_ATR_STOP_GRID:
        for dias in DIAS_MAXIMO_GRID:
            for r in R_FIJO_GRID:
                ret = _retornos_fija(df, candidatos, atr, k, r, dias)
                if ret:
                    resultados_fija.append({
                        "k_atr_stop": k, "r_fijo": r, "dias_maximo": dias, **_resumen(ret),
                    })
            for r_min in R_MIN_GRID:
                for r_max in R_MAX_GRID:
                    if r_max <= r_min:
                        continue
                    ret = _retornos_dinamica(df, candidatos, atr, k, r_min, r_max, dias)
                    if ret:
                        resultados_dinamica.append({
                            "k_atr_stop": k, "r_min": r_min, "r_max": r_max, "dias_maximo": dias, **_resumen(ret),
                        })
    return resultados_fija, resultados_dinamica


def _reportar_top(nombre, resultados, metrica):
    resultados = sorted(resultados, key=lambda r: -r[metrica] if not np.isnan(r[metrica]) else 1e9)
    print(f"\nMejores 5 configs {nombre} por {metrica} (de {len(resultados)} probadas):")
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
    eth = cargar_ohlcv_lab("ETHUSDT", "1d", estrategia="comparacion_salida_fija_vs_dinamica_v2")
    btc = cargar_ohlcv_lab("BTCUSDT", "1d", estrategia="comparacion_salida_fija_vs_dinamica_v2")

    print("=== BARRIDO EN ETH (ajuste) ===")
    cand_eth = _candidatos(eth)
    atr_eth = atr_absoluto(eth)
    print(f"candidatos ETH (techo+suelo confirmados con probabilidad calculable): {len(cand_eth)}")

    fija, dinamica = _barrer(eth, cand_eth, atr_eth)

    print(f"\nMedia de TODAS las configs fijas en ETH: "
          f"retorno={np.mean([r['retorno_medio'] for r in fija]):.3f}% "
          f"sharpe={np.nanmean([r['sharpe_operacion'] for r in fija]):.3f}")
    print(f"Media de TODAS las configs dinamicas en ETH: "
          f"retorno={np.mean([r['retorno_medio'] for r in dinamica]):.3f}% "
          f"sharpe={np.nanmean([r['sharpe_operacion'] for r in dinamica]):.3f}")

    print("\n--- Ranking por RETORNO MEDIO (sin ajustar por riesgo) ---")
    mejor_fija_retorno = _reportar_top("FIJAS", fija, "retorno_medio")
    mejor_dinamica_retorno = _reportar_top("DINAMICAS", dinamica, "retorno_medio")

    print("\n--- Ranking por SHARPE POR OPERACION (retorno / desviacion) ---")
    mejor_fija_sharpe = _reportar_top("FIJAS", fija, "sharpe_operacion")
    mejor_dinamica_sharpe = _reportar_top("DINAMICAS", dinamica, "sharpe_operacion")

    print("\n=== CONFIRMACION EN BTC (sin tocar los parametros ganadores de ETH) ===")
    cand_btc = _candidatos(btc)
    atr_btc = atr_absoluto(btc)
    print(f"candidatos BTC (techo+suelo confirmados con probabilidad calculable): {len(cand_btc)}")

    for etiqueta, mejor_fija, mejor_dinamica in [
        ("RETORNO MEDIO", mejor_fija_retorno, mejor_dinamica_retorno),
        ("SHARPE POR OPERACION", mejor_fija_sharpe, mejor_dinamica_sharpe),
    ]:
        print(f"\n-- ganadores por {etiqueta} --")
        ret_fija_btc = _retornos_fija(
            btc, cand_btc, atr_btc, mejor_fija["k_atr_stop"], mejor_fija["r_fijo"], mejor_fija["dias_maximo"])
        ret_dinamica_btc = _retornos_dinamica(
            btc, cand_btc, atr_btc, mejor_dinamica["k_atr_stop"], mejor_dinamica["r_min"],
            mejor_dinamica["r_max"], mejor_dinamica["dias_maximo"])
        r_fija_btc, r_dinamica_btc = _resumen(ret_fija_btc), _resumen(ret_dinamica_btc)
        print(f"  FIJA {mejor_fija} en BTC -> {r_fija_btc}")
        print(f"  DINAMICA {mejor_dinamica} en BTC -> {r_dinamica_btc}")


if __name__ == "__main__":
    main()
