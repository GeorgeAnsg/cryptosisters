import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
import pandas as pd
from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp

# No hay presupuesto para la API de pago de CoinGecko (la gratuita solo da
# 365 dias de historico). Proxy sin coste, con datos ya en el proyecto:
# indice de precio BTC frente a (BTC+ETH+XRP), cada uno reindexado a 100 en
# la fecha comun mas antigua. No es la dominancia oficial (esa pesa por
# market cap, no por precio), pero captura la misma idea -- "¿BTC gana o
# pierde terreno frente a las otras dos?" -- con lo que ya tenemos.

def construir_dominancia():
    dfb, *_ = cargar("BTCUSDT")
    dfe, *_ = cargar("ETHUSDT")
    dfx, *_ = cargar_xrp()
    common = sorted(set(dfb["open_time"]) & set(dfe["open_time"]) & set(dfx["open_time"]))
    common = pd.DatetimeIndex(common)
    b = dfb.set_index("open_time")["close"].reindex(common)
    e = dfe.set_index("open_time")["close"].reindex(common)
    x = dfx.set_index("open_time")["close"].reindex(common)
    b_idx = b / b.iloc[0] * 100
    e_idx = e / e.iloc[0] * 100
    x_idx = x / x.iloc[0] * 100
    dominancia = b_idx / (b_idx + e_idx + x_idx)
    return pd.Series(dominancia.to_numpy(), index=common)


def _pendiente_dominancia(dominancia, fechas_df, ventana):
    dom_por_fecha = dominancia.reindex(fechas_df).to_numpy()
    n = len(dom_por_fecha)
    slope = np.full(n, np.nan)
    for i in range(ventana, n):
        a, b = dom_por_fecha[i - ventana], dom_por_fecha[i]
        if a == a and b == b:
            slope[i] = b - a
    return slope


def _en_rotacion_fuerte(dominancia, fechas_df, ventana, umbral_abs):
    """True los dias donde la dominancia BTC/(BTC+ETH+XRP) cambia fuerte (rotacion de capital) -- ahi se suspende el corte."""
    slope = _pendiente_dominancia(dominancia, fechas_df, ventana)
    return np.abs(slope) >= umbral_abs


if __name__ == "__main__":
    dominancia = construir_dominancia()
    print(f"Dominancia BTC/(BTC+ETH+XRP): {dominancia.index.min().date()} -> {dominancia.index.max().date()}, "
          f"min={dominancia.min():.3f} max={dominancia.max():.3f} media={dominancia.mean():.3f}")

    VENTANA_GRID = [10, 20, 30]
    UMBRAL_GRID = [0.005, 0.01, 0.02, 0.03, 0.05]

    print("\n=== AJUSTE en ETH ===")
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    fechas = df["open_time"]
    mejor = None
    for ventana in VENTANA_GRID:
        for umbral in UMBRAL_GRID:
            en_rot = _en_rotacion_fuerte(dominancia, fechas, ventana, umbral)
            en_rot = np.nan_to_num(en_rot, nan=0.0).astype(bool)
            total = 0.0
            for año in AÑOS:
                cand = candidatos_por_año(df, año)
                cap, tr = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, 1.5, en_rot)
                total += cap
            print(f"  ventana={ventana:2d} umbral={umbral}: total={total:.2f}  (dias suspendidos: {en_rot.sum()}/{len(df)})")
            if mejor is None or total > mejor[0]:
                mejor = (total, ventana, umbral)
    print(f"GANADOR ETH: {mejor}")
    print("  (ref ETH: BASE=9490.02, pendiente sin filtro=10662.53, regimen NEUTRO fijo=10440.01)")

    ventana_g, umbral_g = mejor[1], mejor[2]
    print(f"\n=== CONFIRMACIÓN congelada (ventana={ventana_g}, umbral={umbral_g}) en BTC y XRP ===")
    for nombre, cargador in [("BTCUSDT", lambda: cargar("BTCUSDT")), ("XRP", cargar_xrp)]:
        dfx, atrx, rtx, rsx, pendx, clx, ccx = cargador()
        fechasx = dfx["open_time"]
        en_rot = _en_rotacion_fuerte(dominancia, fechasx, ventana_g, umbral_g)
        en_rot = np.nan_to_num(en_rot, nan=0.0).astype(bool)
        años_validos = [a for a in AÑOS if (fechasx.dt.year == a).sum() > 300]
        total = 0.0
        for año in años_validos:
            cand = candidatos_por_año(dfx, año)
            cap, tr = simular_cuenta_filtrada(dfx, cand, atrx, rtx, rsx, pendx, fechasx, 1.5, en_rot)
            total += cap
        ref = "BASE=8863.09, regimen fijo=8951.12" if nombre == "BTCUSDT" else "BASE=7222.06, regimen fijo=7242.19"
        print(f"  {nombre} TOTAL={total:.2f}  (dias suspendidos: {en_rot.sum()}/{len(dfx)})  ref {ref}")
