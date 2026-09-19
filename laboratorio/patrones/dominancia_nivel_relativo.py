"""
Dominancia BTC/(BTC+ETH+XRP) -- variante de NIVEL, no de velocidad --
15-sept-2026, a peticion del usuario tras ver que la variante de rotacion
(dominancia_proxy.py) fallaba.

Diferencia con dominancia_proxy.py: aquel media CUANTO CAMBIA la
dominancia en una ventana corta (10-30 dias) -- un evento raro y corto,
que es justo la clase de señal que la lección 0022/0024 dice que no
funciona (horizonte parecido al del propio evento de 5 dias que se
quiere filtrar). Esta version mide, en cambio, si la dominancia esta
ANORMALMENTE ALTA O BAJA respecto a su propia media de largo plazo --
un rasgo lento, del mismo tipo de horizonte que el regimen SMA200 que si
funciono. Es una hipotesis distinta, no una repeticion de la anterior.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
from laboratorio.patrones.dominancia_proxy import construir_dominancia


def _distancia_relativa(dominancia, fechas_df, ventana_larga):
    dom = dominancia.reindex(fechas_df).to_numpy()
    media_larga = dominancia.rolling(ventana_larga).mean().reindex(fechas_df).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        dist = (dom - media_larga) / media_larga
    return dist


def _en_extremo_dominancia(dominancia, fechas_df, ventana_larga, umbral_abs):
    dist = _distancia_relativa(dominancia, fechas_df, ventana_larga)
    activo = np.abs(dist) >= umbral_abs
    return np.nan_to_num(activo, nan=0.0).astype(bool)


def _candidatos_todos_los_años(df):
    return {año: candidatos_por_año(df, año) for año in AÑOS}


def _total(df, atr, rt, rs, pend, fechas, activo, cand_por_año):
    total = 0.0
    for año in AÑOS:
        cap, tr = simular_cuenta_filtrada(df, cand_por_año[año], atr, rt, rs, pend, fechas, 1.5, activo)
        total += cap
    return total


if __name__ == "__main__":
    dominancia = construir_dominancia()
    print(f"Dominancia: {dominancia.index.min().date()} -> {dominancia.index.max().date()}, "
          f"min={dominancia.min():.3f} max={dominancia.max():.3f}")

    VENTANA_LARGA_GRID = [60, 100, 150, 200, 300]
    UMBRAL_GRID = [0.01, 0.02, 0.03, 0.05, 0.08]

    print("\n=== AJUSTE en ETH (grid ventana_larga x umbral de distancia relativa) ===")
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    fechas = df["open_time"]
    cand_eth = _candidatos_todos_los_años(df)
    mejor = None
    for ventana in VENTANA_LARGA_GRID:
        for umbral in UMBRAL_GRID:
            activo = _en_extremo_dominancia(dominancia, fechas, ventana, umbral)
            total = _total(df, atr, rt, rs, pend, fechas, activo, cand_eth)
            print(f"  ventana_larga={ventana:3d} umbral={umbral}: total={total:.2f}  (dias marcados: {activo.sum()}/{len(df)})")
            if mejor is None or total > mejor[0]:
                mejor = (total, ventana, umbral)
    print(f"GANADOR ETH: {mejor}")
    print("  (ref ETH: BASE=9490.02, pendiente sin filtro=10662.53, regimen NEUTRO fijo=10440.01, dominancia-rotacion=10662.53)")

    ventana_g, umbral_g = mejor[1], mejor[2]
    print(f"\n=== CONFIRMACIÓN congelada (ventana_larga={ventana_g}, umbral={umbral_g}) en BTC y XRP ===")
    for nombre, cargador in [("BTC", lambda: cargar("BTCUSDT")), ("XRP", cargar_xrp)]:
        dfx, atrx, rtx, rsx, pendx, clx, ccx = cargador()
        fechasx = dfx["open_time"]
        activo = _en_extremo_dominancia(dominancia, fechasx, ventana_g, umbral_g)
        cand_x = _candidatos_todos_los_años(dfx)
        por_año = {}
        total = 0.0
        for año in AÑOS:
            if (fechasx.dt.year == año).sum() <= 300:
                continue
            cap, tr = simular_cuenta_filtrada(dfx, cand_x[año], atrx, rtx, rsx, pendx, fechasx, 1.5, activo)
            por_año[año] = round(cap, 2)
            total += cap
        ref = "BASE=8863.09 (2023=2161), sin_filtro=8882.40 (2023=1612.98), regimen=8951.12 (2023=2111.85)" if nombre == "BTC" \
            else "BASE=7222.06 (2022=1515,2023=1482), sin_filtro=7222.06(?), regimen=7242.19 (2022=1519,2023=1624)"
        print(f"  {nombre} TOTAL={total:.2f}  por_año={por_año}  (dias marcados: {activo.sum()}/{len(dfx)})")
        print(f"    ref: {ref}")

    print("\nFIN", flush=True)
