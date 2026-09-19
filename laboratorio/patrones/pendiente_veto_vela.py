"""
Variante de deteccion, 17-sept-2026: tercer mecanismo distinto (tras
canal y volumen -- ver `registro/intentos.jsonl`), esta vez usando la
FORMA de la vela del propio dia del corte, no su volumen ni el contexto
de tendencia.

Idea: `pendiente_acelerada` corta cuando el CIERRE de hoy esta muy lejos
del cierre de hace 5 dias (ver `salidas/pendiente_acelerada.py`), pero no
mira DONDE cerro el precio dentro del rango del propio dia. Un largo que
se corta por caida fuerte, si el dia cierra cerca de su MAXIMO (mecha
larga por abajo, "rechazo" de precios mas bajos), sugiere que el mercado
ya recompro esa caida dentro del mismo dia -- el corte podria estar
disparandose justo en el peor momento, antes de un rebote. Si en cambio
el dia cierra cerca de su MINIMO (sin mecha de rechazo), la caida parece
mas genuina y continuada.

cierre_relativo = (close-low)/(high-low) en [0,1]: 0 = cerro en el
minimo del dia, 1 = cerro en el maximo. Direccion-especifico, igual que
el canal (no agnostico como el volumen): un largo se veta si
cierre_relativo es ALTO (rechazo alcista pese a la caida de 5 dias); un
corto se veta si es BAJO (rechazo bajista pese a la subida de 5 dias).

Causal: usa solo el OHLC del propio dia i, ya cerrado en el momento en
que `pendiente_acelerada` evaluaria el corte ese mismo dia.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.pendiente_veto_canal import simular_cuenta_veto_canal

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}


def _cierre_relativo(df):
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    rango = high - low
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = (close - low) / rango
    return np.where(rango > 0, rel, np.nan)


def _no_confirma_vela(df, umbral_vela):
    """Dos mascaras (largo, corto): True el dia en que la forma de la
    vela contradice el corte -- rechazo en contra de la direccion del
    movimiento de 5 dias que dispararia pendiente_acelerada. NaN
    (rango del dia = 0, no deberia pasar en cripto pero por seguridad)
    -> no veta."""
    rel = _cierre_relativo(df)
    con_valor = ~np.isnan(rel)
    no_confirma_largo = np.where(con_valor, rel > umbral_vela, False)
    no_confirma_corto = np.where(con_valor, rel < (1 - umbral_vela), False)
    return no_confirma_largo, no_confirma_corto


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
    print("=== 1) AJUSTE en ETH: grid de umbral_vela ===")
    df_eth, atr_e, rt_e, rs_e, pend_e, cl_e, cc_e = cargar("ETHUSDT")
    fechas_e = df_eth["open_time"]
    cand_eth = {año: candidatos_por_año(df_eth, año) for año in AÑOS}

    GRID = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
    resultados = {}
    for u in GRID:
        no_l, no_c = _no_confirma_vela(df_eth, u)
        total, _ = _total_por_moneda(df_eth, atr_e, rt_e, rs_e, pend_e, fechas_e, no_l, no_c, cand_eth)
        resultados[u] = total
        print(f"  umbral_vela={u}: total={total:.2f}  (vetados_largo={int(no_l.sum())}  vetados_corto={int(no_c.sum())})")

    ganador = max(resultados, key=resultados.get)
    print(f"GANADOR ETH: umbral_vela={ganador} -> {resultados[ganador]:.2f}")
    if ganador in (GRID[0], GRID[-1]):
        print("  AVISO: el ganador esta en el borde del rango probado -- habria que extender el grid.")

    print()
    print(f"=== 2) CONFIRMACION congelada (umbral_vela={ganador}, sin tocar nada) ===")
    for nombre in ("BTC", "XRP"):
        cargador = MONEDAS[nombre]
        df, atr, rt, rs, pend, cl, cc = cargador()
        fechas = df["open_time"]
        no_l, no_c = _no_confirma_vela(df, ganador)
        total, por_año = _total_por_moneda(df, atr, rt, rs, pend, fechas, no_l, no_c)
        print(f"  {nombre}: TOTAL={total:.2f}  por_año={por_año}  "
              f"dias_vetados_largo={int(no_l.sum())}  dias_vetados_corto={int(no_c.sum())}/{len(df)}")
