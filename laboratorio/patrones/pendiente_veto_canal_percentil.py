"""
Variante de deteccion, 16-sept-2026: refinamiento de `pendiente_veto_canal.py`.

Diagnostico previo (ver `laboratorio/patrones/diagnostico_xrp_calidad.py` y
la sesion del 16-sept): exigir un umbral de calidad ABSOLUTO
(`probabilidad_forma >= 0.5`, ajustado en ETH) perjudica a XRP porque sus
canales ASCENDENTES puntuan sistematicamente peor que los de ETH/BTC --
las tres monedas tienen sus subidas mas "sucias" que sus bajadas, pero en
XRP la brecha es mas dura de compensar porque la moneda lleva mucho tiempo
en tendencia de fondo bajista (idea del propio usuario, 16-sept-2026): sus
rallies de recuperacion son mas parecidos a un "pump" brusco que a una
subida ordenada, así que precisamente los tramos donde el canal SI acierta
en detectar que la recuperacion sigue viva quedan por debajo de una vara de
medir calibrada con el comportamiento de Ethereum.

Solucion: en vez de un umbral absoluto (0.5, un numero fijo elegido en una
sola moneda y aplicado igual a las demas -- el "absoluto" que la
metodologia de `deteccion-flexible-patrones` prohibe), exigir que el canal
este entre los MEJORES DE SU PROPIA MONEDA: un percentil calculado contra
el historial de canales confirmados de esa misma moneda y esa misma
direccion, no contra un numero fijo. Asi cada moneda se compara contra su
propio nivel de "limpieza habitual" en vez de contra el de Ethereum.

Calculo estrictamente CAUSAL: el percentil de un canal se calcula solo
contra los canales confirmados ANTERIORES a el (nunca se usa un canal
futuro para juzgar uno pasado). Con menos de `min_historial` canales
previos no hay base suficiente para juzgar "es de los mejores" -- en ese
caso el dia NO se marca como tendencia confirmada (se comporta como la
version sin filtro de canal: pendiente_acelerada actua con normalidad).

**Correccion 16-sept-2026 (misma sesion, misma tarde):** la primera
version comparaba cada canal contra TODO el historial de la moneda desde
2018 -- eso perjudicaba justo a Bitcoin 2023, el caso que motivo toda la
investigacion, porque Bitcoin tuvo un puñado de subidas excepcionalmente
"limpias" en 2019 y 2020 (pre-halving, todavia un mercado muy joven y sin
la liquidez de ahora) que fijan un listón de calidad altisimo PARA
SIEMPRE, aunque hayan pasado 4-5 años y el propio Bitcoin ya no sea el
mismo activo (mucho mas maduro, ya no dobla su precio como entonces).
Sustituido por una VENTANA de historial reciente (`ventana_historial`
canales previos, no todo el historial) -- asi el "nivel habitual" de cada
moneda se actualiza con el tiempo en vez de quedar anclado a su mejor
momento historico.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.pendiente_veto_canal import simular_cuenta_veto_canal
from motores import canal_ascendente, canal_descendente

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}

MIN_HISTORIAL = 5  # canales previos necesarios antes de confiar en el percentil
VENTANA_HISTORIAL = 15  # cuantos canales previos recientes se usan como referencia (no todo el historial)


def _confirmados_ordenados(df, direccion):
    """Deteccion de canales (cara) separada del calculo de percentil/ventana
    (barato) -- para poder barrer ventana_historial/percentil_umbral en un
    grid sin recalcular canales en cada combinacion."""
    cands = canal_ascendente.calcular(df) if direccion == "largo" else canal_descendente.calcular(df)
    return sorted([c for c in cands if c.confirmado], key=lambda c: c.idx_confirmacion)


def _activo_desde_confirmados(confirmados, n, percentil_umbral, ventana_historial=VENTANA_HISTORIAL,
                               extension_dias=0, min_historial=MIN_HISTORIAL, piso_absoluto=0.0):
    """`piso_absoluto` (16-sept-2026): el percentil puro SIEMPRE deja pasar
    una fraccion fija de canales, incluso en un tramo entero de canales
    mediocres (el "menos malo de los malos" sigue colandose) -- diagnosticado
    tras ver que el percentil relativo (ventana=20) resultaba MENOS
    significativo en el control de Monte Carlo de BTC que el umbral
    absoluto, pese a marcar MENOS dias en total (45.7% vs 52.4%): no es
    cuestion de cuantos dias se marcan, sino de que el percentil no exige
    ningun minimo real. Combinar ambos: exigir percentil alto Y una calidad
    absoluta minima (aunque bastante mas laxa que 0.5, que ya sabemos que
    penaliza a XRP)."""
    activo = np.zeros(n, dtype=bool)
    historial = []
    for c in confirmados:
        ventana = historial[-ventana_historial:] if ventana_historial else historial
        if len(ventana) >= min_historial:
            rank = sum(1 for v in ventana if v <= c.probabilidad_forma) / len(ventana)
            pasa = rank >= percentil_umbral and c.probabilidad_forma >= piso_absoluto
        else:
            pasa = False
        if pasa:
            fin = min(c.idx_confirmacion + extension_dias, n - 1)
            activo[c.idx_fondo1:fin + 1] = True
        historial.append(c.probabilidad_forma)
    return activo


def _en_tendencia_confirmada_percentil(df, direccion, percentil_umbral, extension_dias=0,
                                        min_historial=MIN_HISTORIAL, ventana_historial=VENTANA_HISTORIAL):
    confirmados = _confirmados_ordenados(df, direccion)
    return _activo_desde_confirmados(confirmados, len(df), percentil_umbral, ventana_historial,
                                      extension_dias, min_historial)


def _total_por_moneda(df, atr, rt, rs, pend, fechas, en_largo, en_corto, cand_por_año=None):
    if cand_por_año is None:
        cand_por_año = {año: candidatos_por_año(df, año) for año in AÑOS}
    total = 0.0
    por_año = {}
    for año in AÑOS:
        cap = simular_cuenta_veto_canal(df, cand_por_año[año], atr, rt, rs, pend, fechas, en_largo, en_corto)
        por_año[año] = round(cap, 2)
        total += cap
    return total, por_año


if __name__ == "__main__":
    print("=== 1) AJUSTE en ETH: grid 2D ventana_historial x percentil_umbral ===")
    df_eth, atr_e, rt_e, rs_e, pend_e, cl_e, cc_e = cargar("ETHUSDT")
    fechas_e = df_eth["open_time"]
    cand_eth = {año: candidatos_por_año(df_eth, año) for año in AÑOS}
    n_eth = len(df_eth)

    conf_largo_eth = _confirmados_ordenados(df_eth, "largo")
    conf_corto_eth = _confirmados_ordenados(df_eth, "corto")

    VENTANAS = [8, 12, 15, 20, 25, 9999]  # 9999 = "todo el historial", para ver el contraste
    PERCENTILES = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    resultados_eth = {}
    for v in VENTANAS:
        for p in PERCENTILES:
            en_l = _activo_desde_confirmados(conf_largo_eth, n_eth, p, ventana_historial=v)
            en_c = _activo_desde_confirmados(conf_corto_eth, n_eth, p, ventana_historial=v)
            total, _ = _total_por_moneda(df_eth, atr_e, rt_e, rs_e, pend_e, fechas_e, en_l, en_c, cand_eth)
            resultados_eth[(v, p)] = total
        fila = "  ".join(f"p={p}:{resultados_eth[(v,p)]:.0f}" for p in PERCENTILES)
        print(f"  ventana={v:5d}  {fila}")

    ganador = max(resultados_eth, key=resultados_eth.get)
    v_g, p_g = ganador
    print(f"GANADOR ETH: ventana_historial={v_g}, percentil_umbral={p_g} -> {resultados_eth[ganador]:.2f}")
    if p_g in (PERCENTILES[0], PERCENTILES[-1]) or v_g in (VENTANAS[0], VENTANAS[-2]):
        print("  AVISO: el ganador esta en el borde de algun rango probado -- posible artefacto.")

    print()
    print(f"=== 2) CONFIRMACION congelada (ventana={v_g}, percentil={p_g}, sin tocar nada) ===")
    for nombre in ("BTC", "XRP"):
        cargador = MONEDAS[nombre]
        df, atr, rt, rs, pend, cl, cc = cargador()
        fechas = df["open_time"]
        conf_l = _confirmados_ordenados(df, "largo")
        conf_c = _confirmados_ordenados(df, "corto")
        en_l = _activo_desde_confirmados(conf_l, len(df), p_g, ventana_historial=v_g)
        en_c = _activo_desde_confirmados(conf_c, len(df), p_g, ventana_historial=v_g)
        total, por_año = _total_por_moneda(df, atr, rt, rs, pend, fechas, en_l, en_c)
        print(f"  {nombre}: TOTAL={total:.2f}  por_año={por_año}  "
              f"dias_en_largo={int(en_l.sum())}  dias_en_corto={int(en_c.sum())}")
