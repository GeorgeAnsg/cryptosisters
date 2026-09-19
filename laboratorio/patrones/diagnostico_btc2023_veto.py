"""
Diagnostico (15-sept-2026): ¿por que el veto de doble_horizonte (pendiente
larga de 22 dias, umbral 0.5) no toca ni un solo corte de BTC 2023, pese
a ser el año mas alcista de los tres estudiados (+154.5%)?
"""
import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import candidatos_por_año
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, UMBRAL_PENDIENTE
from laboratorio.patrones.pendiente_doble_horizonte import _pendiente_ventana

df, atr, rt, rs, pend, cl, cc = cargar("BTCUSDT")
fechas = df["open_time"]
close = df["close"].to_numpy()
pend_larga = _pendiente_ventana(df, atr, 22)

sin_filtro = np.zeros(len(df), dtype=bool)
cand = candidatos_por_año(df, 2023)
_, trades = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, sin_filtro)
cortes = [t for t in trades if t["motivo"] == "pendiente_acelerada"]

print(f"{'fecha':12s} {'direccion':6s} {'pendiente_corta':>16s} {'pendiente_larga22':>18s} {'umbral_veto=0.5':>16s} {'vetaria?'}")
for t in cortes:
    idx = fechas[fechas == t["fecha_salida"]].index
    if len(idx) == 0:
        idx_match = np.flatnonzero(fechas.dt.strftime("%Y-%m-%d").to_numpy() == t["fecha_salida"])
        if len(idx_match) == 0:
            print(f"  no encontrado indice para {t['fecha_salida']}")
            continue
        i = int(idx_match[0])
    else:
        i = int(idx[0])
    pc, pl = pend[i], pend_larga[i]
    direccion = t["direccion"]
    larga_muy_a_favor = (pl >= 0.5) if direccion == "largo" else (pl <= -0.5)
    print(f"{t['fecha_salida']:12s} {direccion:6s} {pc:16.3f} {pl:18.3f} {'>=0.5' if direccion=='largo' else '<=-0.5':>16s} {'SI vetaria' if larga_muy_a_favor else 'no veta'}")

print(f"\nRango de pendiente_larga(22) en 2023: min={np.nanmin(pend_larga[(fechas.dt.year==2023).to_numpy()]):.3f} max={np.nanmax(pend_larga[(fechas.dt.year==2023).to_numpy()]):.3f}")
print(f"Rango de ATR(14) en 2023: min={np.nanmin(atr[(fechas.dt.year==2023).to_numpy()]):.1f} max={np.nanmax(atr[(fechas.dt.year==2023).to_numpy()]):.1f}")
print(f"Precio BTC en 2023: min={np.nanmin(close[(fechas.dt.year==2023).to_numpy()]):.0f} max={np.nanmax(close[(fechas.dt.year==2023).to_numpy()]):.0f}")
