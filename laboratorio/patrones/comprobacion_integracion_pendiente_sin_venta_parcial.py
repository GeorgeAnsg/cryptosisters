"""
Comprobacion previa a la migracion (15-sept-2026): ¿cuanto aporta la venta
parcial por si sola dentro del sistema ya validado de pendiente_acelerada?
Se usa el MISMO bucle de cuenta secuencial (mismo switch, mismo orden de
apertura/cierre) que ya paso las puertas -- solo se apaga
`usar_venta_parcial`, aislando su efecto sin cambiar nada mas. Esto
importa porque el motor generico de produccion (`salidas/stop_objetivo.py`)
todavia no soporta venta parcial -- si el hueco es grande, no se puede
migrar pendiente_acelerada sin antes añadir esa pieza al motor generico.
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, UMBRAL_PENDIENTE
from laboratorio.patrones.xrp_tercera_moneda import cargar_xrp
import numpy as np

MONEDAS = {"ETH": lambda: cargar("ETHUSDT"), "BTC": lambda: cargar("BTCUSDT"), "XRP": cargar_xrp}

for nombre, cargador in MONEDAS.items():
    df, atr, rt, rs, pend, cl, cc = cargador()
    fechas = df["open_time"]
    sin_filtro = np.zeros(len(df), dtype=bool)
    total_con_vp, total_sin_vp = 0.0, 0.0
    for año in AÑOS:
        cand = candidatos_por_año(df, año)
        cap_con, _ = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, sin_filtro, usar_venta_parcial=True)
        cap_sin, _ = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, sin_filtro, usar_venta_parcial=False)
        total_con_vp += cap_con
        total_sin_vp += cap_sin
    print(f"{nombre}: CON venta parcial = {total_con_vp:.2f}   SIN venta parcial = {total_sin_vp:.2f}   "
          f"diferencia = {total_con_vp - total_sin_vp:+.2f} ({(total_con_vp/total_sin_vp-1)*100:+.1f}%)")
