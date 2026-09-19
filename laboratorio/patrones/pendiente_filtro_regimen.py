import sys
sys.path.insert(0, "/Users/jorgeansotegui/Desktop/corvus4")
import numpy as np
from laboratorio.patrones.canal_sobre_sistema_completo import cargar
from laboratorio.patrones.prueba_multi_anio import AÑOS, candidatos_por_año
from motores import regimen_mercado as rm
import sys as _s
_s.path.insert(0, "/tmp")
from laboratorio.patrones.pendiente_filtro_lateral import simular_cuenta_filtrada, UMBRAL_PENDIENTE

# En vez del canal lateral ad-hoc (sin graduar, sin validacion cruzada propia),
# usamos el motor YA GRADUADO motores/regimen_mercado.py: NEUTRO = ni bajista
# ni alcista marcado -- candidato natural a "mercado lateral" con infraestructura
# ya validada (aunque el propio ALCISTA de ese motor esta marcado como "menos
# probado" en su docstring -- lo tenemos en cuenta al leer el resultado).

def _en_neutro(df):
    n = len(df)
    sma200 = df["close"].rolling(200).mean()
    activo = np.zeros(n, dtype=bool)
    for i in range(n):
        tipo, score = rm.clasificar(df, i, sma200)
        if tipo == rm.TipoRegimen.NEUTRO:
            activo[i] = True
    return activo


print("=== ETH: pendiente=1.5 fijo, filtro = regimen NEUTRO (motor ya graduado) ===")
df, atr, rt, rs, pend, cl, cc = cargar("ETHUSDT")
fechas = df["open_time"]
en_neutro = _en_neutro(df)
total = 0.0
por_año = {}
for año in AÑOS:
    cand = candidatos_por_año(df, año)
    cap, tr = simular_cuenta_filtrada(df, cand, atr, rt, rs, pend, fechas, UMBRAL_PENDIENTE, en_neutro)
    total += cap
    por_año[año] = cap
print(f"  dias NEUTRO: {en_neutro.sum()}/{len(df)} ({en_neutro.sum()/len(df)*100:.1f}%)")
for año in AÑOS:
    print(f"  {año}: {por_año[año]:.2f}")
print(f"  TOTAL={total:.2f}  (ref: BASE=9490.02, pendiente sin filtro=10662.53, filtro canal lateral(0.8)=9962.61)")

print("\n=== BTC: mismo filtro, congelado (sin tocar nada) ===")
df2, atr2, rt2, rs2, pend2, cl2, cc2 = cargar("BTCUSDT")
fechas2 = df2["open_time"]
en_neutro2 = _en_neutro(df2)
total2 = 0.0
por_año2 = {}
for año in AÑOS:
    cand = candidatos_por_año(df2, año)
    cap, tr = simular_cuenta_filtrada(df2, cand, atr2, rt2, rs2, pend2, fechas2, UMBRAL_PENDIENTE, en_neutro2)
    total2 += cap
    por_año2[año] = cap
print(f"  dias NEUTRO: {en_neutro2.sum()}/{len(df2)} ({en_neutro2.sum()/len(df2)*100:.1f}%)")
for año in AÑOS:
    print(f"  {año}: {por_año2[año]:.2f}")
print(f"  TOTAL={total2:.2f}  (ref: BASE=8863.09 (2023 BASE=2161), pendiente sin filtro total=8882.40 (2023=1612.98), filtro canal lateral(0.8) total=9065.31 (2023=1864))")
