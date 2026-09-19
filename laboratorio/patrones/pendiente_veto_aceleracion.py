"""
Variante de deteccion, 17-sept-2026: mecanismo DISTINTO al veto por canal
(pendiente_veto_canal*.py, agotado sin generalizar) y al veto por volumen
(pendiente_veto_volumen.py, descartado -- un corte real casi nunca
coincide con volumen bajo, ver registro/intentos.jsonl). Aqui se prueba
"aceleracion de la aceleracion": no solo cuanto se ha movido el precio
(`pendiente`, la velocidad -- ver `salidas/pendiente_acelerada.py`), sino
si ese movimiento SIGUE ganando fuerza o ya esta perdiendola.

Idea: `pendiente[i] = (close[i]-close[i-5])/atr[i]` es una velocidad. Su
propia variacion en el tiempo (`pendiente[i] - pendiente[i-k]`) es una
aceleracion -- positiva si la velocidad de caida/subida sigue
intensificandose, negativa/cercana a cero si ya esta frenando. Un corte
de pendiente_acelerada que ocurre CUANDO la caida todavia esta acelerando
(la "aceleracion de la aceleracion" sigue siendo fuerte en la misma
direccion) es mas creible que uno que ocurre cuando el movimiento ya
esta perdiendo fuelle -- en ese segundo caso, podria estar a punto de
agotarse justo antes de rebotar.

A diferencia del volumen (direccion-agnostico), esto SI depende de la
direccion, igual que el canal: para un largo (corte con pendiente muy
negativa) se exige que la propia pendiente siga bajando (mas negativa
que hace `ventana_derivada` dias); para un corto, que siga subiendo.

Causal: la segunda derivada en el dia i solo usa pendiente[i] y
pendiente[i-ventana_derivada], ambas ya conocidas en el dia i.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np

from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.pendiente_veto_canal import simular_cuenta_veto_canal

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}


def _segunda_derivada(pendiente, ventana_derivada):
    """pendiente[i] - pendiente[i-ventana_derivada], causal. NaN donde
    cualquiera de las dos pendientes involucradas sea NaN (arranque)."""
    n = len(pendiente)
    seg = np.full(n, np.nan)
    seg[ventana_derivada:] = pendiente[ventana_derivada:] - pendiente[:-ventana_derivada]
    return seg


def _no_confirma_aceleracion(pendiente, umbral_aceleracion, ventana_derivada):
    """Dos mascaras (largo, corto): True el dia en que la propia pendiente
    NO esta acelerando lo suficiente en la direccion que confirmaria el
    corte -- ese dia, el corte de pendiente_acelerada no se confia (se
    veta). NaN (arranque, sin historial suficiente) -> no veta, se
    comporta como sin filtro."""
    seg = _segunda_derivada(pendiente, ventana_derivada)
    con_valor = ~np.isnan(seg)
    no_confirma_largo = np.where(con_valor, seg > -umbral_aceleracion, False)
    no_confirma_corto = np.where(con_valor, seg < umbral_aceleracion, False)
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
    print("=== 1) AJUSTE en ETH: grid 2D ventana_derivada x umbral_aceleracion ===")
    df_eth, atr_e, rt_e, rs_e, pend_e, cl_e, cc_e = cargar("ETHUSDT")
    fechas_e = df_eth["open_time"]
    cand_eth = {año: candidatos_por_año(df_eth, año) for año in AÑOS}

    VENTANAS = [2, 3, 5, 8]
    UMBRALES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]
    resultados = {}
    for v in VENTANAS:
        for u in UMBRALES:
            no_l, no_c = _no_confirma_aceleracion(pend_e, u, v)
            total, _ = _total_por_moneda(df_eth, atr_e, rt_e, rs_e, pend_e, fechas_e, no_l, no_c, cand_eth)
            resultados[(v, u)] = total
        fila = "  ".join(f"u={u}:{resultados[(v,u)]:.0f}" for u in UMBRALES)
        print(f"  ventana_derivada={v}  {fila}")

    ganador = max(resultados, key=resultados.get)
    v_g, u_g = ganador
    print(f"GANADOR ETH: ventana_derivada={v_g}, umbral_aceleracion={u_g} -> {resultados[ganador]:.2f}")
    if u_g in (UMBRALES[0], UMBRALES[-1]) or v_g in (VENTANAS[0], VENTANAS[-1]):
        print("  AVISO: el ganador esta en el borde de algun rango probado -- habria que extender el grid.")

    print()
    print(f"=== 2) CONFIRMACION congelada (ventana_derivada={v_g}, umbral_aceleracion={u_g}, sin tocar nada) ===")
    for nombre in ("BTC", "XRP"):
        cargador = MONEDAS[nombre]
        df, atr, rt, rs, pend, cl, cc = cargador()
        fechas = df["open_time"]
        no_l, no_c = _no_confirma_aceleracion(pend, u_g, v_g)
        total, por_año = _total_por_moneda(df, atr, rt, rs, pend, fechas, no_l, no_c)
        print(f"  {nombre}: TOTAL={total:.2f}  por_año={por_año}  "
              f"dias_vetados_largo={int(no_l.sum())}  dias_vetados_corto={int(no_c.sum())}/{len(df)}")
