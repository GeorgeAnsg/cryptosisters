import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar, simular_cuenta_con_canal
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, simular_trade_filtrado
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
import laboratorio.patrones.sistema_confirmado_switch_14sept2026 as sc
from salidas.stop_objetivo import calcular_niveles_fijos

UMBRAL_PENDIENTE = 1.5

# Hipotesis: un movimiento fuerte con volumen POR ENCIMA de su propia media
# reciente es mas fiable (real) que el mismo movimiento con volumen flojo --
# ya demostrado el factor mas importante en doble techo/suelo (leccion 2 de
# la skill deteccion-flexible-patrones). Comparar volumen contra su propia
# media movil ya normaliza por activo sin ningun numero fijo por moneda.
def _volumen_relativo(df, ventana):
    vol = df["volume"].to_numpy()
    media = df["volume"].rolling(ventana).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = vol / media
    return rel


def _en_volumen_bajo(df, ventana, ratio_umbral):
    """True los dias donde el volumen NO confirma (por debajo del umbral) -- ahi se suspende el corte."""
    rel = _volumen_relativo(df, ventana)
    n = len(df)
    activo = np.zeros(n, dtype=bool)
    for i in range(n):
        if rel[i] != rel[i]:  # NaN (calentamiento)
            continue
        if rel[i] < ratio_umbral:
            activo[i] = True
    return activo


if __name__ == "__main__":
    VENTANA_GRID = [10, 20, 30]
    RATIO_GRID = [0.8, 1.0, 1.2, 1.5, 2.0]

    print("=== AJUSTE en ETH: grid (ventana_volumen x ratio_minimo) ===")
    df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
    fechas = df["open_time"]
    mejor = None
    for ventana in VENTANA_GRID:
        for ratio in RATIO_GRID:
            en_vol_bajo = _en_volumen_bajo(df, ventana, ratio)
            total = 0.0
            for año in AÑOS:
                cand = candidatos_por_año(df, año)
                cap, tr = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, en_vol_bajo)
                total += cap
            print(f"  ventana={ventana:2d} ratio_min={ratio}: total={total:.2f}  (dias suspendidos: {en_vol_bajo.sum()}/{len(df)})")
            if mejor is None or total > mejor[0]:
                mejor = (total, ventana, ratio)
    print(f"GANADOR ETH: ventana={mejor[1]} ratio_min={mejor[2]} -> {mejor[0]:.2f}")
    print("  (ref ETH: BASE=9490.02, pendiente sin filtro=10662.53, regimen NEUTRO fijo=10440.01)")

    ventana_g, ratio_g = mejor[1], mejor[2]

    print(f"\n=== CONFIRMACIÓN congelada (ventana={ventana_g}, ratio_min={ratio_g}) en BTC ===")
    dfb, atrb, rtb, rsb, pendb, clb, ccb = cargar("BTCUSDT")
    fechasb = dfb["open_time"]
    en_vb = _en_volumen_bajo(dfb, ventana_g, ratio_g)
    totalb = 0.0
    for año in AÑOS:
        cand = candidatos_por_año(dfb, año)
        cap, tr = simular_cuenta_filtrada(dfb, cand, atrb, rtb, rsb, pendb, fechasb, UMBRAL_PENDIENTE, en_vb)
        totalb += cap
        print(f"  {año}: {cap:.2f}")
    print(f"  BTC TOTAL={totalb:.2f}  (dias suspendidos: {en_vb.sum()}/{len(dfb)})  ref BASE=8863.09, regimen fijo=8951.12")

    print(f"\n=== CONFIRMACIÓN congelada (ventana={ventana_g}, ratio_min={ratio_g}) en XRP ===")
    dfx, atrx, rtx, rsx, pendx, clx, ccx = cargar_xrp()
    fechasx = dfx["open_time"]
    años_xrp = [a for a in AÑOS if (fechasx.dt.year == a).sum() > 300]
    en_vx = _en_volumen_bajo(dfx, ventana_g, ratio_g)
    totalx = 0.0
    for año in años_xrp:
        cand = candidatos_por_año(dfx, año)
        cap, tr = simular_cuenta_filtrada(dfx, cand, atrx, rtx, rsx, pendx, fechasx, UMBRAL_PENDIENTE, en_vx)
        totalx += cap
        print(f"  {año}: {cap:.2f}")
    print(f"  XRP TOTAL={totalx:.2f}  (dias suspendidos: {en_vx.sum()}/{len(dfx)})  ref BASE=7222.06, regimen fijo=7242.19")
